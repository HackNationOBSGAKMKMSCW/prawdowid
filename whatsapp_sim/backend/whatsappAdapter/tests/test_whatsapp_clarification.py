import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from apiReading.models import Category, FetchOutcome, FetchResult, ReadingRequest, ReadingResult
from textAnalysis.clarification import ClarificationResult, DialogueTurn
from textAnalysis.container import AnalysisDataContainer
from whatsappAdapter.bot import (
    CLARIFY_CANCEL_BUTTON,
    CLARIFY_CANCELLED_TEXT,
    CLARIFY_SKIP_BUTTON,
    NOTHING_PENDING_TEXT,
    TOO_SHORT_TEXT,
    UNDERSTANDING_STATUS,
    WELCOME_TEXT,
    SprawdzToBot,
)
from whatsappAdapter.clarification import (
    MAX_CLARIFY_CHARS,
    ConversationStore,
    DemoClarifier,
    LiveClarifier,
    PendingClarification,
)
from whatsappAdapter.cloud_api import IncomingKind, IncomingMessage
from whatsappAdapter.pipeline import CheckReport, DemoPipeline
from whatsappAdapter.server import clarifier_from_environment


def reading_result(query: str) -> ReadingResult:
    now = datetime.now(UTC)
    return ReadingResult(
        request=ReadingRequest(query=query, categories=[Category.FACT_CHECK]),
        results=[
            FetchOutcome(
                source="google_fact_check",
                result=FetchResult(source="google_fact_check", items=[], fetched_at=now),
            )
        ],
        items=[],
        categories_without_source=[],
        fetched_at=now,
        duration_ms=1,
    )


class RecordingPipeline:
    mode = "live"

    def __init__(self) -> None:
        self.texts: list[str] = []

    async def check(self, text: str, progress=None) -> CheckReport:
        self.texts.append(text)
        analysis = AnalysisDataContainer(source_text=text, statements=["s"])
        return CheckReport(analysis, [reading_result("s")])


def bodies(messages: list[dict]) -> list[str]:
    return [m["text"]["body"] if m["type"] == "text" else m["type"] for m in messages]


DRONE = "Czy na prawdę spadł dron w Polsce?"
RESOLVED = "21.11.2026 w okolicach Rzeszowa spadł dron."


def incoming(text: str = "", kind: IncomingKind = IncomingKind.TEXT, **kwargs) -> IncomingMessage:
    return IncomingMessage(sender="48500", message_id="wamid.1", kind=kind, text=text, **kwargs)


def button(reply) -> IncomingMessage:
    return incoming(reply.title, kind=IncomingKind.BUTTON, button_id=reply.id)


def ask(*questions: str, **fields) -> ClarificationResult:
    defaults = {
        "missing": ["czas", "miejsce"],
        "understood_claim": "W Polsce spadł dron.",
        "resolved_claim": "W Polsce spadł dron.",
    }
    return ClarificationResult(
        needs_clarification=True, questions=list(questions), **{**defaults, **fields}
    )


def done(claim: str = RESOLVED, **fields) -> ClarificationResult:
    return ClarificationResult(
        needs_clarification=False, understood_claim=claim, resolved_claim=claim, **fields
    )


class ScriptedClarifier:
    mode = "live"

    def __init__(self, *results: ClarificationResult | Exception) -> None:
        self.results = list(results)
        self.calls: list[tuple[list[DialogueTurn], int, int]] = []

    async def assess(
        self, turns: Sequence[DialogueTurn], *, round_index: int, max_rounds: int
    ) -> ClarificationResult:
        self.calls.append((list(turns), round_index, max_rounds))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_bot(*results: ClarificationResult | Exception, **kwargs):
    pipeline = RecordingPipeline()
    clarifier = ScriptedClarifier(*results)
    return SprawdzToBot(pipeline, clarifier=clarifier, **kwargs), pipeline, clarifier


def question_text(replies: list[dict]) -> str:
    (reply,) = replies
    assert reply["type"] == "interactive" and reply["interactive"]["type"] == "button"
    ids = [b["reply"]["id"] for b in reply["interactive"]["action"]["buttons"]]
    assert ids == [CLARIFY_SKIP_BUTTON.id, CLARIFY_CANCEL_BUTTON.id]
    return reply["interactive"]["body"]["text"]


async def test_vague_event_is_answered_with_questions_instead_of_a_check() -> None:
    bot, pipeline, clarifier = make_bot(ask("Kiedy to się stało?", "Gdzie to było?"))
    statuses: list[str] = []

    async def status(line: str) -> None:
        statuses.append(line)

    body = question_text(await bot.handle(incoming(DRONE), status=status))

    assert "Rozumiem, że chodzi o: „W Polsce spadł dron.”" in body
    assert "• Kiedy to się stało?\n• Gdzie to było?" in body
    assert pipeline.texts == []
    assert statuses == [UNDERSTANDING_STATUS]
    assert clarifier.calls == [([DialogueTurn("user", DRONE)], 1, 2)]
    pending = bot.conversations.get("48500")
    assert pending is not None and pending.rounds == 1
    assert pending.turns[-1] == DialogueTurn("bot", "Kiedy to się stało?\nGdzie to było?")


async def test_answer_completes_the_claim_and_runs_the_check() -> None:
    bot, pipeline, clarifier = make_bot(ask("Kiedy i gdzie?"), done())
    await bot.handle(incoming(DRONE))

    # A short answer is fine while the bot waits for details.
    replies = await bot.handle(incoming("wczoraj"))

    assert pipeline.texts == [RESOLVED]
    assert bodies(replies)[0].startswith(f"🧩 Sprawdziłem z Twoimi szczegółami: _„{RESOLVED}”_")
    turns, round_index, _ = clarifier.calls[1]
    assert [t.text for t in turns] == [DRONE, "Kiedy i gdzie?", "wczoraj"]
    assert round_index == 2
    assert bot.conversations.get("48500") is None


async def test_follow_up_question_then_round_limit_forces_the_check() -> None:
    bot, pipeline, clarifier = make_bot(
        ask("Kiedy?"), ask("Gdzie?"), ask("Jeszcze coś?", resolved_claim=RESOLVED)
    )

    await bot.handle(incoming(DRONE))
    follow_up = question_text(await bot.handle(incoming("wczoraj")))
    await bot.handle(incoming("Rzeszów"))

    assert "Jeszcze jedno pytanie" in follow_up and "❓ Gdzie?" in follow_up
    assert [call[1] for call in clarifier.calls] == [1, 2, 3]
    assert pipeline.texts == [RESOLVED]
    assert bot.conversations.get("48500") is None


@pytest.mark.parametrize(
    "skip", [button(CLARIFY_SKIP_BUTTON), incoming("nie wiem"), incoming("Pomiń")]
)
async def test_skip_checks_the_original_message_without_details(skip) -> None:
    bot, pipeline, clarifier = make_bot(ask("Kiedy?"))
    await bot.handle(incoming(DRONE, forwarded=True))

    replies = await bot.handle(skip)

    assert pipeline.texts == [DRONE]
    assert not bodies(replies)[0].startswith("🧩")
    assert "wiadomość przekazana dalej" in bodies(replies)[-1]
    assert len(clarifier.calls) == 1


async def test_skip_after_an_answer_keeps_the_details_given_so_far() -> None:
    bot, pipeline, _ = make_bot(ask("Kiedy?"), ask("Gdzie?", resolved_claim="Wczoraj spadł dron."))
    await bot.handle(incoming(DRONE))
    await bot.handle(incoming("wczoraj"))

    await bot.handle(button(CLARIFY_SKIP_BUTTON))

    assert pipeline.texts == ["Wczoraj spadł dron."]


async def test_cancel_and_greeting_close_the_conversation() -> None:
    bot, pipeline, _ = make_bot(ask("Kiedy?"), ask("Kiedy?"), ask("Kiedy?"))

    await bot.handle(incoming(DRONE))
    assert bodies(await bot.handle(button(CLARIFY_CANCEL_BUTTON))) == [CLARIFY_CANCELLED_TEXT]
    await bot.handle(incoming(DRONE))
    assert bodies(await bot.handle(incoming("anuluj"))) == [CLARIFY_CANCELLED_TEXT]
    await bot.handle(incoming(DRONE))
    assert bodies(await bot.handle(incoming("cześć")))[0] == WELCOME_TEXT

    assert bot.conversations.get("48500") is None
    assert bodies(await bot.handle(button(CLARIFY_SKIP_BUTTON))) == [NOTHING_PENDING_TEXT]
    assert pipeline.texts == []


async def test_new_topic_drops_the_old_question_and_starts_over() -> None:
    new_question = "A czy szczepionki powodują autyzm?"
    bot, pipeline, clarifier = make_bot(
        ask("Kiedy?"), done(new_question, new_topic=True), done(new_question)
    )
    await bot.handle(incoming(DRONE))

    replies = await bot.handle(incoming(new_question))

    assert pipeline.texts == [new_question]
    assert not bodies(replies)[0].startswith("🧩")
    assert clarifier.calls[2][0] == [DialogueTurn("user", new_question)]


async def test_short_new_topic_is_rejected_like_any_short_message() -> None:
    bot, pipeline, _ = make_bot(ask("Kiedy?"), done("ok", new_topic=True))
    await bot.handle(incoming(DRONE))

    assert bodies(await bot.handle(incoming("ok"))) == [TOO_SHORT_TEXT]
    assert pipeline.texts == []


async def test_clarifier_failures_never_block_the_check() -> None:
    bot, pipeline, _ = make_bot(RuntimeError("llm down"))
    await bot.handle(incoming(DRONE))
    assert pipeline.texts == [DRONE]

    bot, pipeline, _ = make_bot(ask("Kiedy?"), RuntimeError("llm down"))
    await bot.handle(incoming(DRONE))
    replies = await bot.handle(incoming("wczoraj"))
    expected = f"{DRONE} (szczegóły od użytkownika: wczoraj)"
    assert pipeline.texts == [expected]
    assert expected in bodies(replies)[0]


async def test_slow_clarifier_times_out_and_checks_directly() -> None:
    class SlowClarifier:
        mode = "live"

        async def assess(self, turns, *, round_index, max_rounds):
            await asyncio.sleep(1)
            raise AssertionError("unreachable")

    pipeline = RecordingPipeline()
    bot = SprawdzToBot(pipeline, clarifier=SlowClarifier(), clarify_timeout=0.01)

    await bot.handle(incoming(DRONE))

    assert pipeline.texts == [DRONE]


async def test_long_messages_links_and_examples_skip_clarification() -> None:
    bot, pipeline, clarifier = make_bot()
    long_text = "Spadł dron. " * (MAX_CLARIFY_CHARS // 12 + 1)

    await bot.handle(incoming(long_text))
    await bot.handle(incoming("https://example.org/artykul-o-dronie"))
    await bot.handle(incoming("5G", kind=IncomingKind.BUTTON, button_id="example_5g"))

    assert len(pipeline.texts) == 3
    assert clarifier.calls == []


async def test_messages_of_one_sender_are_handled_in_order() -> None:
    bot, pipeline, _ = make_bot(ask("Kiedy?"), done())

    await asyncio.gather(bot.handle(incoming(DRONE)), bot.handle(incoming("wczoraj")))

    assert pipeline.texts == [RESOLVED]


async def test_bot_without_clarifier_checks_immediately() -> None:
    pipeline = RecordingPipeline()

    await SprawdzToBot(pipeline).handle(incoming(DRONE))

    assert pipeline.texts == [DRONE]


def test_conversation_store_expires_and_limits_entries() -> None:
    now = [0.0]
    store = ConversationStore(ttl_seconds=60, max_entries=2, clock=lambda: now[0])
    pending = PendingClarification(turns=(DialogueTurn("user", DRONE),), rounds=1)

    store.put("a", pending)
    now[0] = 30
    store.put("b", pending)
    now[0] = 50
    store.put("c", pending)
    # Over the size limit the oldest conversation goes first.
    assert store.get("a") is None and len(store) == 2

    now[0] = 95  # "b" was last updated at 30, so it is past the 60 s TTL
    assert store.get("b") is None and store.get("c") is not None
    now[0] = 111
    assert store.pop("c") is None and len(store) == 0


async def test_demo_clarifier_asks_for_missing_time_and_place() -> None:
    clarifier = DemoClarifier()

    first = await clarifier.assess([DialogueTurn("user", DRONE)], round_index=1, max_rounds=2)
    timed = await clarifier.assess(
        [DialogueTurn("user", DRONE), DialogueTurn("bot", "?"), DialogueTurn("user", "wczoraj")],
        round_index=2,
        max_rounds=2,
    )
    complete = await clarifier.assess(
        [DialogueTurn("user", DRONE), DialogueTurn("user", "wczoraj koło Rzeszowa")],
        round_index=2,
        max_rounds=2,
    )

    assert first.needs_clarification and first.missing == ["czas", "miejsce"]
    assert first.understood_claim == "Spadł dron w Polsce."
    assert timed.needs_clarification and timed.missing == ["miejsce"]
    assert not complete.needs_clarification
    assert complete.resolved_claim == "Spadł dron w Polsce. Szczegóły: wczoraj koło Rzeszowa."


@pytest.mark.parametrize(
    "text",
    [
        "Czy to prawda, że szczepionki powodują autyzm?",
        "Woda wrze w temperaturze 100 stopni.",
        "Wczoraj w Gdańsku wybuchł pożar w porcie.",
    ],
)
async def test_demo_clarifier_leaves_general_or_detailed_claims_alone(text: str) -> None:
    result = await DemoClarifier().assess([DialogueTurn("user", text)], round_index=1, max_rounds=2)

    assert not result.needs_clarification


async def test_demo_clarifier_detects_declines_and_new_topics() -> None:
    clarifier = DemoClarifier()
    start = [DialogueTurn("user", DRONE), DialogueTurn("bot", "Kiedy?")]

    declined = await clarifier.assess(
        [*start, DialogueTurn("user", "Nie wiem dokładnie")], round_index=2, max_rounds=2
    )
    new_topic = await clarifier.assess(
        [*start, DialogueTurn("user", "A czy szczepionki powodują autyzm?")],
        round_index=2,
        max_rounds=2,
    )

    assert declined.user_declined and not declined.needs_clarification
    assert new_topic.new_topic and not new_topic.needs_clarification


async def test_demo_bot_runs_the_whole_loop() -> None:
    bot = SprawdzToBot(DemoPipeline(delay_seconds=0), clarifier=DemoClarifier())

    question = question_text(await bot.handle(incoming(DRONE)))
    replies = await bot.handle(incoming("wczoraj koło Rzeszowa"))

    assert "Kiedy mniej więcej" in question and "Gdzie to było" in question
    assert "Szczegóły: wczoraj koło Rzeszowa" in bodies(replies)[0]
    assert "Tryb demonstracyjny" in bodies(replies)[-1]


async def test_live_clarifier_passes_rounds_to_the_analyzer() -> None:
    seen: dict = {}

    async def assess(turns, *, round_index, max_rounds):
        seen.update(turns=turns, round_index=round_index, max_rounds=max_rounds)
        return done()

    result = await LiveClarifier(assess).assess(
        [DialogueTurn("user", DRONE)], round_index=2, max_rounds=3
    )

    assert result.resolved_claim == RESOLVED
    assert seen == {"turns": [DialogueTurn("user", DRONE)], "round_index": 2, "max_rounds": 3}


def test_clarifier_follows_the_mode_and_can_be_turned_off(monkeypatch) -> None:
    monkeypatch.delenv("SPRAWDZTO_CLARIFY", raising=False)
    assert isinstance(clarifier_from_environment(DemoPipeline()), DemoClarifier)
    assert isinstance(clarifier_from_environment(RecordingPipeline()), LiveClarifier)

    monkeypatch.setenv("SPRAWDZTO_CLARIFY", "off")
    assert clarifier_from_environment(DemoPipeline()) is None


def test_webhook_in_demo_mode_asks_and_then_checks(monkeypatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from whatsappAdapter.server import create_app

    monkeypatch.setenv("SPRAWDZTO_MODE", "demo")
    monkeypatch.delenv("SPRAWDZTO_CLARIFY", raising=False)
    client = TestClient(create_app())

    def send(message_id: str, body: str) -> list[dict]:
        message = {"from": "48500", "id": message_id, "type": "text", "text": {"body": body}}
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{"changes": [{"field": "messages", "value": {"messages": [message]}}]}],
        }
        response = client.post("/api/whatsapp/webhook", json=payload)
        assert response.status_code == 200
        return response.json()["messages"]

    question = send("wamid.1", DRONE)
    answer = send("wamid.2", "wczoraj koło Rzeszowa")

    assert question_text(question).startswith("🧩 *Chcę dobrze zrozumieć")
    assert "Sprawdziłem z Twoimi szczegółami" in bodies(answer)[0]


def website_client(clarifier=None):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from whatsappAdapter.server import create_app

    bot = SprawdzToBot(DemoPipeline(delay_seconds=0), clarifier=clarifier)
    return TestClient(create_app(bot))


def test_website_endpoint_runs_the_loop_without_server_state() -> None:
    client = website_client(DemoClarifier())

    first = client.post("/api/clarify", json={"turns": [{"role": "user", "text": DRONE}]})
    asked = first.json()
    assert first.status_code == 200
    assert asked["status"] == "ask"
    assert asked["missing"] == ["czas", "miejsce"]
    assert asked["skip_claim"] == DRONE
    assert asked["turns"][-1]["role"] == "bot"

    turns = [*asked["turns"], {"role": "user", "text": "wczoraj koło Rzeszowa"}]
    done_step = client.post("/api/clarify", json={"turns": turns}).json()
    assert done_step["status"] == "check"
    assert done_step["with_details"] is True
    assert done_step["claim"] == "Spadł dron w Polsce. Szczegóły: wczoraj koło Rzeszowa."


def test_website_endpoint_checks_general_claims_and_handles_a_disabled_loop() -> None:
    general = {"turns": [{"role": "user", "text": "Woda wrze w temperaturze 100 stopni."}]}

    with_loop = website_client(DemoClarifier()).post("/api/clarify", json=general).json()
    without_loop = (
        website_client(None)
        .post("/api/clarify", json={"turns": [{"role": "user", "text": DRONE}]})
        .json()
    )

    assert with_loop["status"] == "check" and with_loop["with_details"] is False
    assert with_loop["claim"] == general["turns"][0]["text"]
    assert without_loop == {**without_loop, "status": "check", "claim": DRONE}


@pytest.mark.parametrize(
    "turns",
    [
        [],
        [{"role": "bot", "text": "Kiedy?"}, {"role": "user", "text": "wczoraj"}],
        [{"role": "user", "text": DRONE}, {"role": "bot", "text": "Kiedy?"}],
        [
            {"role": "user", "text": DRONE},
            {"role": "bot", "text": "x" * 1001},
            {"role": "user", "text": "a"},
        ],
        [{"role": "user", "text": "x"}] * 6,
        [{"role": "system", "text": "x"}],
    ],
)
def test_website_endpoint_rejects_malformed_conversations(turns) -> None:
    response = website_client(DemoClarifier()).post("/api/clarify", json={"turns": turns})

    assert response.status_code == 422


def test_website_endpoint_falls_back_to_a_check_when_the_model_fails() -> None:
    client = website_client(ScriptedClarifier(RuntimeError("llm down")))

    step = client.post("/api/clarify", json={"turns": [{"role": "user", "text": DRONE}]}).json()

    assert step["status"] == "check" and step["claim"] == DRONE
