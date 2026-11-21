"""Werdykt dla jednego twierdzenia: wywołanie modelu, walidacja JSON, ponowienie.

Przebieg:
1. Brak źródeł -> deterministyczny `brak_wystarczajacych_danych` bez wywołania modelu.
2. Model dostaje prompt systemowy (reguły R1–R16) i wiadomość z <claim> i <source>.
3. Odpowiedź musi być obiektem JSON zgodnym z `ModelVerdict`. Przy błędzie model
   dostaje jedną szansę na poprawkę z opisem błędu.
4. Wyciek identyfikatora z promptu systemowego (canary) unieważnia odpowiedź.
5. Poprawna odpowiedź przechodzi przez kontrolę deterministyczną (`checks`).
6. Awaria techniczna albo dwie niepoprawne odpowiedzi -> `blad_analizy`
   (nigdy udawany werdykt ani udawany brak danych).
"""

from collections.abc import Sequence

from pydantic import ValidationError

from .checks import apply_checks
from .llm import ChatClient, LLMError, Message, parse_json_object
from .prompts import SYSTEM_CANARY, build_user_message, system_prompt
from .schemas import VERDICT_LABELS_PL, ClaimVerdict, ModelVerdict, ReferenceSource

MAX_ATTEMPTS = 2


class InvalidModelOutput(ValueError):
    pass


def parse_model_verdict(raw: str) -> ModelVerdict:
    """Parsuje i waliduje odpowiedź modelu; zgłasza `InvalidModelOutput`."""
    if SYSTEM_CANARY in (raw or ""):
        raise InvalidModelOutput("Odpowiedź zawiera identyfikator instrukcji systemowej.")
    try:
        return ModelVerdict.model_validate(parse_json_object(raw))
    except ValueError as exc:  # także ValidationError
        if isinstance(exc, ValidationError):
            fields = sorted({".".join(map(str, e["loc"])) for e in exc.errors()})
            raise InvalidModelOutput(f"Niezgodność ze schematem w polach: {fields}") from None
        raise InvalidModelOutput(str(exc)) from None


def no_sources_verdict(claim_id: str, claim: str) -> ClaimVerdict:
    return ClaimVerdict(
        claim_id=claim_id,
        claim=claim,
        verdict="brak_wystarczajacych_danych",
        verdict_label=VERDICT_LABELS_PL["brak_wystarczajacych_danych"],
        confidence="wysoka",
        explanation=(
            "Nie znaleziono żadnego źródła wzorcowego dotyczącego tego twierdzenia, "
            "więc nie można go potwierdzić ani obalić."
        ),
        reasoning_steps=[
            "Przeszukano korpus wzorcowy, źródła podane w zapytaniu i wyniki fact-checkingu.",
            "Żadne źródło nie dotyczy tego twierdzenia; model nie był wywoływany.",
        ],
        missing_information=["Źródło wzorcowe opisujące fakty, których dotyczy twierdzenie."],
    )


def error_verdict(
    claim_id: str, claim: str, reason: str, sources: Sequence[ReferenceSource]
) -> ClaimVerdict:
    return ClaimVerdict(
        claim_id=claim_id,
        claim=claim,
        verdict="blad_analizy",
        verdict_label=VERDICT_LABELS_PL["blad_analizy"],
        confidence="niska",
        explanation=f"Nie udało się wydać werdyktu: {reason}",
        adjustments=[reason],
        source_ids=[s.source_id for s in sources],
    )


async def assess_claim(
    claim_id: str,
    claim: str,
    sources: Sequence[ReferenceSource],
    client: ChatClient,
    *,
    security_warnings: Sequence[str] = (),
) -> ClaimVerdict:
    """Werdykt dla twierdzenia; `security_warnings` pochodzą z `security.screen_claim`."""
    result = await _assess(claim_id, claim, sources, client, bool(security_warnings))
    if security_warnings:
        result = result.model_copy(update={"security_warnings": list(security_warnings)})
    return result


async def _assess(
    claim_id: str,
    claim: str,
    sources: Sequence[ReferenceSource],
    client: ChatClient,
    suspicious_claim: bool,
) -> ClaimVerdict:
    if not sources:
        return no_sources_verdict(claim_id, claim)

    messages: list[Message] = [
        {"role": "system", "content": system_prompt()},
        {
            "role": "user",
            "content": build_user_message(claim, sources, suspicious_claim=suspicious_claim),
        },
    ]
    problem = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            reply = await client.complete(messages)
        except LLMError as exc:
            return error_verdict(claim_id, claim, str(exc), sources)
        try:
            parsed = parse_model_verdict(reply.content)
        except InvalidModelOutput as exc:
            problem = str(exc)
            if attempt < MAX_ATTEMPTS:
                messages += [
                    {"role": "assistant", "content": reply.content[:6000]},
                    {
                        "role": "user",
                        "content": (
                            f"Twoja odpowiedź jest niepoprawna: {problem}. Zwróć wyłącznie "
                            "poprawny obiekt JSON zgodny ze schematem z reguły R16."
                        ),
                    },
                ]
            continue
        return apply_checks(
            claim_id=claim_id,
            claim=claim,
            parsed=parsed,
            sources=sources,
            model=reply.model,
        )
    return error_verdict(claim_id, claim, f"model nie zwrócił poprawnego JSON ({problem})", sources)
