"""Klient LLM przez FreeLLMAPI, wywoływany tak jak w sekcji „Using the API” jego README.

FreeLLMAPI (https://github.com/tashfeenahmed/freellmapi) to proxy zgodne z OpenAI przed
wieloma darmowymi dostawcami, z automatycznym przełączaniem (failover). Wzorzec z README:

    client = OpenAI(base_url="http://<host>:3001/v1", api_key="freellmapi-…")
    response = client.chat.completions.with_raw_response.create(model="auto", messages=[...])
    completion = response.parse()
    completion.choices[0].message.content
    response.headers.get("x-routed-via")      # który dostawca/model naprawdę odpowiedział

Konfiguracja wyłącznie z analysis/.env (CONTRIBUTING.md, sekcja 5):
- `OPENAI_BASE_URL`: adres FreeLLMAPI z `/v1`,
- `OPENAI_API_KEY`: zunifikowany klucz `freellmapi-…` ze strony Keys w panelu,
- `LLM_MODEL`: puste = `auto` (router wybiera), albo `auto:fast`, `auto:smart`, profil
  lub id modelu,
- `LLM_TIMEOUT_S`: opcjonalny limit czasu klienta.

Każda awaria (brak konfiguracji, timeout, błąd dostawcy, pusta odpowiedź) to `LLMError`
z `kind`; potok zamienia go na status `error`, nigdy na werdykt. Funkcje wołające model
(np. `stance.py`) przyjmują klienta jako parametr (`ChatClient`), więc testy działają bez sieci.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, sleep
from typing import Protocol
from urllib.parse import unquote

import httpx
import openai
from dotenv import load_dotenv
from openai import OpenAI

# analysis/.env: trzy poziomy nad tym plikiem (verdict -> prawdowid_analysis -> src -> analysis)
_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"

# Wartość routera z README: „let the router pick”. To nie wybór modelu, tylko delegacja do routera.
ROUTER_MODEL = "auto"
# Router FreeLLMAPI ma domyślny budżet failoveru 45 s (FALLBACK_TIME_BUDGET_MS),
# więc limit klienta musi być dłuższy, żeby nie przerywać trwającego failoveru.
DEFAULT_TIMEOUT_S = 60.0
# Statusy, przy których wybrany przez router dostawca mógł odrzucić `response_format`.
_JSON_MODE_REJECTED = (400, 422)
# Chwilowe awarie dostawcy (np. 503 „overloaded” z Gemini), po których warto ponowić.
# 429 obsługiwane osobno (`_rate_limit_wait`).
_TRANSIENT_STATUSES = (500, 502, 503, 504)
DEFAULT_RETRIES = 2
# Chwilowy limit zapytań na minutę (429 `rate_limited`): jedno ponowienie po krótkiej
# przerwie. Wyczerpany budżet (`quota_exceeded`) albo długie `Retry-After` -> bez ponowienia,
# bo czekanie tylko wydłużyłoby odpowiedź ponad cel 30 s.
DEFAULT_RATE_LIMIT_RETRIES = 1
DEFAULT_RATE_LIMIT_WAIT_S = 5.0
MAX_RATE_LIMIT_WAIT_S = 15.0


class LLMError(Exception):
    """Błąd techniczny LLM. `kind`: `config`, `connection`, `timeout`, `rate_limited`,
    `quota_exceeded`, `provider_error`, `bad_request`, `bad_response`."""

    def __init__(
        self,
        message: str,
        kind: str = "provider_error",
        *,
        status_code: int | None = None,
        retry_after_s: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code
        self.retry_after_s = retry_after_s


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    api_key: str
    model: str = ROUTER_MODEL
    timeout_s: float = DEFAULT_TIMEOUT_S
    retries: int = DEFAULT_RETRIES  # ponowienia po chwilowym 5xx (bez routera z failoverem)
    retry_backoff_s: float = 1.0  # odstęp: backoff * 2**próba
    rate_limit_retries: int = DEFAULT_RATE_LIMIT_RETRIES  # ponowienia po 429 `rate_limited`
    rate_limit_wait_s: float = DEFAULT_RATE_LIMIT_WAIT_S  # przerwa, gdy brak `Retry-After`

    @classmethod
    def from_env(cls) -> "LLMSettings":
        load_dotenv(_ENV_PATH, override=False)

        def env(name: str) -> str:
            return (os.getenv(name) or "").strip().strip('"').strip("'")

        base_url, api_key = env("OPENAI_BASE_URL"), env("OPENAI_API_KEY")
        missing = [
            n for n, v in (("OPENAI_BASE_URL", base_url), ("OPENAI_API_KEY", api_key)) if not v
        ]
        if missing:
            raise LLMError(
                f"Brak konfiguracji LLM w analysis/.env: {', '.join(missing)}", kind="config"
            )
        return cls(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            model=env("LLM_MODEL") or ROUTER_MODEL,
            timeout_s=float(env("LLM_TIMEOUT_S") or DEFAULT_TIMEOUT_S),
            retries=int(env("LLM_RETRIES") or DEFAULT_RETRIES),
            rate_limit_retries=int(env("LLM_RATE_LIMIT_RETRIES") or DEFAULT_RATE_LIMIT_RETRIES),
        )


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str  # dostawca/model z `x-routed-via`; bez nagłówka: model z odpowiedzi
    tokens_in: int
    tokens_out: int
    duration_ms: int
    requested_model: str = ""  # wysłane `model`, np. `auto`
    routed_via: str | None = None  # surowa wartość nagłówka `x-routed-via`
    fallback_attempts: int = 0  # `x-fallback-attempts`: ile razy router zmienił dostawcę

    def as_run_model(self) -> dict:
        """Wpis do `run.models` z CONTRACTS.md."""
        return {"name": self.model, "tokens_in": self.tokens_in, "tokens_out": self.tokens_out}


class ChatClient(Protocol):
    model: str

    def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResult: ...


def _error_code(exc: openai.APIStatusError) -> str:
    body = exc.body if isinstance(exc.body, dict) else {}
    err = body.get("error", body)
    return str(err.get("code") or "") if isinstance(err, dict) else ""


def _status_error(exc: openai.APIStatusError) -> LLMError:
    status, code = exc.status_code, _error_code(exc)
    if status == 429:
        kind = "quota_exceeded" if code == "quota_exceeded" else "rate_limited"
    elif status in (400, 404, 413, 422):
        kind = "bad_request"
    elif status == 504:
        kind = "timeout"
    else:
        kind = "provider_error"
    try:
        retry_after = float(exc.response.headers["retry-after"])
    except (KeyError, ValueError):
        retry_after = None
    detail = f" ({code})" if code else ""
    return LLMError(
        f"LLM zwrócił HTTP {status}{detail}",
        kind=kind,
        status_code=status,
        retry_after_s=retry_after,
    )


class FreeLLMClient:
    """Klient czatu przez FreeLLMAPI (działa też z innym API zgodnym z OpenAI)."""

    def __init__(self, settings: LLMSettings, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.model = settings.model
        self._client = OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=settings.timeout_s,
            # Failover między dostawcami robi router FreeLLMAPI; SDK nie ponawia,
            # m.in. żeby nie czekać na Retry-After przy wyczerpanym limicie.
            max_retries=0,
            http_client=http_client,
        )

    @classmethod
    def from_env(cls) -> "FreeLLMClient":
        return cls(LLMSettings.from_env())

    def _create_once(self, **kwargs):
        try:
            return self._client.chat.completions.with_raw_response.create(**kwargs)
        except openai.APITimeoutError as exc:
            raise LLMError("Przekroczono czas oczekiwania na LLM", kind="timeout") from exc
        except openai.APIConnectionError as exc:
            raise LLMError("Brak połączenia z API LLM", kind="connection") from exc
        except openai.APIStatusError as exc:
            raise _status_error(exc) from exc

    def _rate_limit_wait(self, exc: LLMError) -> float | None:
        """Przerwa przed ponowieniem po 429 albo None, gdy nie warto ponawiać."""
        if exc.kind != "rate_limited":
            return None
        wait = exc.retry_after_s
        if wait is None:
            wait = self.settings.rate_limit_wait_s
        return wait if wait <= MAX_RATE_LIMIT_WAIT_S else None

    def _create(self, **kwargs):
        transient = rate_limited = 0
        while True:
            try:
                return self._create_once(**kwargs)
            except LLMError as exc:
                wait = self._rate_limit_wait(exc)
                if wait is not None and rate_limited < self.settings.rate_limit_retries:
                    rate_limited += 1
                    sleep(wait)
                elif exc.status_code in _TRANSIENT_STATUSES and transient < self.settings.retries:
                    sleep(self.settings.retry_backoff_s * 2**transient)
                    transient += 1
                else:
                    raise

    def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResult:
        kwargs: dict = {"model": self.model, "messages": messages, "temperature": temperature}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        started = perf_counter()
        try:
            response = self._create(**kwargs)
        except LLMError as exc:
            # README: response_format jest przekazywany „per dostawca”. Gdy dostawca
            # wybrany przez router go odrzuci, ponawiamy raz bez niego (parser i tak
            # wyciąga JSON z tekstu).
            if not (json_mode and exc.status_code in _JSON_MODE_REJECTED):
                raise
            kwargs.pop("response_format")
            response = self._create(**kwargs)
        duration_ms = int((perf_counter() - started) * 1000)

        try:
            completion = response.parse()
        except Exception as exc:  # noqa: BLE001 - każda zła odpowiedź to status, nie werdykt
            raise LLMError("LLM zwrócił nieczytelną odpowiedź", kind="bad_response") from exc
        if not getattr(completion, "choices", None):
            raise LLMError("LLM zwrócił pustą odpowiedź", kind="bad_response")

        routed_via = response.headers.get("x-routed-via")
        routed_via = unquote(routed_via).strip() if routed_via else None
        try:
            attempts = int(response.headers.get("x-fallback-attempts") or 0)
        except ValueError:
            attempts = 0
        usage = completion.usage
        return LLMResult(
            text=completion.choices[0].message.content or "",
            model=routed_via or completion.model or self.model,
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            duration_ms=duration_ms,
            requested_model=self.model,
            routed_via=routed_via,
            fallback_attempts=attempts,
        )

    def list_models(self) -> list[str]:
        try:
            # Gemini (endpoint zgodny z OpenAI) zwraca id z prefiksem `models/`.
            return sorted(m.id.removeprefix("models/") for m in self._client.models.list())
        except openai.OpenAIError as exc:
            raise LLMError(
                f"Nie udało się pobrać listy modeli: {type(exc).__name__}", kind="connection"
            ) from exc


def is_router_model(model: str) -> bool:
    """`auto`, `auto:<strategia/profil>` i `fusion` to wirtualne modele routera FreeLLMAPI."""
    m = model.strip().lower()
    return m == ROUTER_MODEL or m.startswith(ROUTER_MODEL + ":") or m == "fusion"
