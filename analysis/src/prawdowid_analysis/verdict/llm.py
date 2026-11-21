"""Klient LLM przez API zgodne z OpenAI, dostosowany do FreeLLMAPI.

FreeLLMAPI (https://github.com/tashfeenahmed/freellmapi) to samodzielnie hostowany proxy
z jednym endpointem `/v1/chat/completions` przed wieloma darmowymi dostawcami, z
automatycznym przełączaniem (failover) przy 429/5xx. Ten klient:

- bierze konfigurację wyłącznie z analysis/.env (CONTRIBUTING.md, sekcja 5):
  `OPENAI_BASE_URL` (np. `http://<host>:3001/v1`), `OPENAI_API_KEY` (klucz `freellmapi-…`
  ze strony Keys w panelu), `LLM_MODEL` (`auto`, `auto:<profil>` albo przypięty model),
  opcjonalnie `LLM_TIMEOUT_S`. Nazwa modelu nie jest wpisana w kodzie;
- odczytuje nagłówek `X-Routed-Via: <platforma>/<model>`, bo przy `auto` dopiero on mówi,
  który model naprawdę odpowiedział (trafia do `run.models`), oraz `X-Fallback-Attempts`;
- `response_format` jest przekazywany „per dostawca”: gdy dostawca go odrzuci (400/422),
  ponawia raz bez niego. Parser w `stance.py` i tak wyciąga JSON z tekstu;
- każdą awarię zamienia na `LLMError` z `kind` (np. `quota_exceeded` przy 429 z
  wyczerpanym budżetem, z `retry_after_s`). Potok zamienia to na status `error`,
  nigdy na werdykt. Ponowień między dostawcami nie robimy: robi je router FreeLLMAPI.

Funkcje wołające model (np. `stance.py`) przyjmują klienta jako parametr (`ChatClient`),
więc w testach podstawia się atrapę bez sieci. Działa też z innym API zgodnym z OpenAI
(np. Ollama): brak nagłówków FreeLLMAPI nie jest błędem.
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote

import httpx
from dotenv import load_dotenv

# analysis/.env: trzy poziomy nad tym plikiem (verdict -> prawdowid_analysis -> src -> analysis)
_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"

# Router FreeLLMAPI ma domyślny budżet failoveru 45 s (FALLBACK_TIME_BUDGET_MS),
# więc limit klienta musi być wyraźnie dłuższy, żeby nie przerywać trwającego failoveru.
DEFAULT_TIMEOUT_S = 60.0
# Statusy, przy których dostawca mógł odrzucić `response_format`.
_JSON_MODE_REJECTED = (400, 422)


class LLMError(Exception):
    """Błąd techniczny LLM. `kind` opisuje przyczynę (do logów i `run.errors`).

    kind: `config`, `connection`, `timeout`, `rate_limited`, `quota_exceeded`,
    `provider_error`, `bad_request`, `bad_response`.
    """

    def __init__(self, message: str, kind: str = "provider_error", **extra) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code: int | None = extra.get("status_code")
        self.retry_after_s: float | None = extra.get("retry_after_s")


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    model: str
    api_key: str | None = None
    timeout_s: float = DEFAULT_TIMEOUT_S

    @classmethod
    def from_env(cls) -> "LLMSettings":
        load_dotenv(_ENV_PATH, override=False)

        def env(name: str) -> str:
            return (os.getenv(name) or "").strip()

        base_url, model = env("OPENAI_BASE_URL"), env("LLM_MODEL")
        missing = [n for n, v in (("OPENAI_BASE_URL", base_url), ("LLM_MODEL", model)) if not v]
        if missing:
            raise LLMError(
                f"Brak konfiguracji LLM w analysis/.env: {', '.join(missing)}", kind="config"
            )
        return cls(
            base_url=base_url.rstrip("/"),
            model=model,
            api_key=env("OPENAI_API_KEY") or None,
            timeout_s=float(env("LLM_TIMEOUT_S") or DEFAULT_TIMEOUT_S),
        )


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str  # model, który faktycznie odpowiedział (X-Routed-Via), inaczej z odpowiedzi
    tokens_in: int
    tokens_out: int
    duration_ms: int
    requested_model: str = ""  # wartość LLM_MODEL, np. `auto`
    fallback_attempts: int = 0  # ile razy router FreeLLMAPI przełączył dostawcę

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


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        return float(resp.headers["retry-after"])
    except (KeyError, ValueError):
        return None


def _error_code(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error")
    except ValueError:
        return ""
    return str(err.get("code") or err.get("type") or "") if isinstance(err, dict) else ""


def _http_error(resp: httpx.Response) -> LLMError:
    status, code = resp.status_code, _error_code(resp)
    if status == 429:
        kind = "quota_exceeded" if code == "quota_exceeded" else "rate_limited"
    elif status in (400, 404, 413, 422):
        kind = "bad_request"
    elif status == 504:
        kind = "timeout"
    else:
        kind = "provider_error"
    detail = f" ({code})" if code else ""
    return LLMError(
        f"LLM zwrócił HTTP {status}{detail}",
        kind=kind,
        status_code=status,
        retry_after_s=_retry_after(resp),
    )


class OpenAIChatClient:
    """Minimalny klient `/chat/completions` na httpx (bez SDK dostawcy)."""

    def __init__(self, settings: LLMSettings, http: httpx.Client | None = None) -> None:
        self.settings = settings
        self.model = settings.model
        headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
        self._http = http or httpx.Client(
            base_url=settings.base_url, headers=headers, timeout=settings.timeout_s
        )

    @classmethod
    def from_env(cls) -> "OpenAIChatClient":
        return cls(LLMSettings.from_env())

    def _post(self, body: dict) -> httpx.Response:
        try:
            return self._http.post("/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise LLMError("Przekroczono czas oczekiwania na LLM", kind="timeout") from exc
        except httpx.HTTPError as exc:
            raise LLMError(
                f"Błąd połączenia z LLM: {type(exc).__name__}", kind="connection"
            ) from exc

    def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResult:
        body: dict = {"model": self.model, "messages": messages, "temperature": temperature}
        if max_tokens:
            body["max_tokens"] = max_tokens
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        resp = self._post(body)
        if json_mode and resp.status_code in _JSON_MODE_REJECTED:
            # Dostawca wybrany przez router mógł nie obsługiwać response_format.
            body.pop("response_format")
            resp = self._post(body)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if resp.is_error:
            raise _http_error(resp)

        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMError(
                "LLM zwrócił odpowiedź, która nie jest JSON", kind="bad_response"
            ) from exc
        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            raise LLMError("LLM zwrócił pustą odpowiedź", kind="bad_response")

        usage = data.get("usage") or {}
        routed_via = unquote(resp.headers.get("x-routed-via", "")).strip()
        try:
            attempts = int(resp.headers.get("x-fallback-attempts", "0"))
        except ValueError:
            attempts = 0
        return LLMResult(
            text=(choices[0].get("message") or {}).get("content") or "",
            model=routed_via or data.get("model") or self.model,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            duration_ms=duration_ms,
            requested_model=self.model,
            fallback_attempts=attempts,
        )

    def list_models(self, available_only: bool = True) -> list[str]:
        """Modele z `/models`. W FreeLLMAPI `available=true` zwraca tylko te z aktywnym kluczem
        (bez tego katalog jest pełny); inne API ignorują ten parametr."""
        params = {"available": "true"} if available_only else None
        try:
            resp = self._http.get("/models", params=params)
            resp.raise_for_status()
            return sorted(m["id"] for m in resp.json().get("data", []))
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise LLMError(
                f"Nie udało się pobrać listy modeli: {type(exc).__name__}", kind="connection"
            ) from exc


def is_router_model(model: str) -> bool:
    """`auto`, `auto:<profil>` i `fusion` to wirtualne modele routera FreeLLMAPI,
    których nie ma na liście `/models`."""
    m = model.strip().lower()
    return m == "auto" or m.startswith("auto:") or m == "fusion"
