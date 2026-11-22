"""Browser-facing synchronous verification and result-feedback endpoints."""

from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import socket
from collections.abc import Awaitable, Callable
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from api_adapter import InvalidVerificationResult, VerificationFailed, to_check_response
from api_models import CheckResponse, ErrorDetail, ErrorResponse, ReportRequest
from articleScraping.safe_http import is_public_address, resolve_host
from articleScraping.url_validation import InvalidUrlError, validate_url
from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from observability.context import current_request_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["checks"])

VerificationRunner = Callable[[str], Awaitable[object]]
UrlValidator = Callable[[str], Awaitable[str]]


class ApiFailure(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message


async def _validate_public_url(url: str) -> str:
    try:
        canonical = validate_url(url)
        parts = urlsplit(canonical)
        host = parts.hostname or ""
        port = parts.port or (443 if parts.scheme == "https" else 80)
        async with asyncio.timeout(5):
            addresses = await resolve_host(host, port)
    except TimeoutError:
        raise ApiFailure(422, "url_unavailable", "The website address could not be resolved.") from None
    except InvalidUrlError:
        raise ApiFailure(422, "invalid_url", "Provide a valid public HTTP(S) URL.") from None
    except (OSError, socket.gaierror):
        raise ApiFailure(422, "url_unavailable", "The website address could not be resolved.") from None

    if not addresses or not all(is_public_address(address) for address in addresses):
        raise ApiFailure(422, "unsafe_url", "The website address is not publicly accessible.")
    return canonical


def _is_bare_url(text: str) -> bool:
    candidate = text.strip()
    return candidate.startswith(("http://", "https://")) and not any(c.isspace() for c in candidate)


async def _run_verification(text: str) -> object:
    """Run the cancellable verification job under the public request deadline."""
    from verification import start

    timeout_seconds = float(os.getenv("CHECK_TIMEOUT_SECONDS", "360"))
    job = start(text)
    try:
        async with asyncio.timeout(timeout_seconds):
            return await job.report()
    except TimeoutError:
        job.cancel()
        raise ApiFailure(504, "analysis_timeout", "The analysis exceeded its time limit.") from None
    except asyncio.CancelledError:
        job.cancel()
        raise


def _record_for_admin(request: Request, text: str, report: object) -> None:
    """Rejestr panelu admina (luki, alerty) w wątku roboczym: nie opóźnia odpowiedzi.

    Awaria zapisu nigdy nie psuje odpowiedzi; worker loguje tylko typ błędu, bez tekstu.
    """
    recorder = getattr(request.app.state, "query_recorder", None)
    worker = getattr(request.app.state, "admin_worker", None)
    if recorder is None or worker is None:
        return
    # kontekst żądania (request_id z observability) przechodzi do wątku roboczego
    if not worker.submit(contextvars.copy_context().run, recorder, text, report):
        logger.warning("admin_record_dropped request_id=%s", current_request_id())


@router.get("/health", include_in_schema=False)
async def health(request: Request) -> dict[str, str]:
    await request.app.state.store.health_check()
    return {"status": "ok"}


@router.get("/check", response_model=CheckResponse, response_model_exclude_none=True)
async def check(
    request: Request,
    http_response: Response,
    text: Annotated[str, Query(min_length=1, max_length=20_000)],
) -> CheckResponse:
    verifier: VerificationRunner = request.app.state.verification_runner
    semaphore: asyncio.Semaphore = request.app.state.check_semaphore
    try:
        if semaphore.locked():
            raise ApiFailure(503, "analysis_busy", "The service is temporarily busy.") from None
        await semaphore.acquire()
        try:
            if not text.strip():
                raise ApiFailure(422, "invalid_request", "Provide non-empty text or a URL.")
            input_text = text
            input_type = "text"
            if _is_bare_url(input_text):
                validator: UrlValidator = request.app.state.url_validator
                input_text = await validator(input_text.strip())
                input_type = "url"
            elif input_text.strip().startswith(("http://", "https://")):
                raise ApiFailure(422, "invalid_url", "Submit a URL by itself or provide plain text.")

            report = await verifier(input_text)
            result_id = uuid4()
            check_response = to_check_response(
                report,
                result_id=str(result_id),
                input_type=input_type,
            )
        finally:
            semaphore.release()
        _record_for_admin(request, input_text, report)  # w tle, po zwolnieniu slotu
    except VerificationFailed as exc:
        # Which stage failed and the exception type only: never the submitted text or message.
        logger.warning(
            "analysis_part_failed request_id=%s part=%s kind=%s",
            current_request_id(),
            exc.part,
            exc.kind,
        )
        if exc.kind.lower() == "timeout":
            raise ApiFailure(504, "analysis_timeout", "The analysis exceeded its time limit.") from None
        raise ApiFailure(502, "analysis_failed", "The analysis could not be completed.") from None
    except InvalidVerificationResult:
        raise ApiFailure(502, "invalid_analysis_result", "The analysis returned an invalid result.") from None
    except ApiFailure:
        raise
    except Exception as exc:  # noqa: BLE001 - keep provider details out of public responses
        logger.error(
            "analysis_failed request_id=%s error_type=%s",
            current_request_id(),
            type(exc).__name__,
        )
        raise ApiFailure(502, "analysis_failed", "The analysis could not be completed.") from None

    try:
        await request.app.state.store.record_result(result_id, input_type)
    except Exception as exc:  # noqa: BLE001 - a result is not reportable until persisted
        logger.error(
            "result_persistence_failed request_id=%s error_type=%s",
            current_request_id(),
            type(exc).__name__,
        )
        raise ApiFailure(503, "storage_unavailable", "The result could not be stored.") from None
    http_response.headers["Cache-Control"] = "no-store"
    http_response.headers["Referrer-Policy"] = "no-referrer"
    return check_response


@router.post("/check/{result_id}/report", status_code=204)
async def report_check(result_id: UUID, body: ReportRequest, request: Request) -> Response:
    try:
        saved = await request.app.state.store.save_report(
            result_id,
            body.reason,
            body.comment,
        )
    except Exception as exc:  # noqa: BLE001 - do not expose database details
        logger.error(
            "report_persistence_failed request_id=%s error_type=%s",
            current_request_id(),
            type(exc).__name__,
        )
        raise ApiFailure(503, "storage_unavailable", "The report could not be stored.") from None
    if not saved:
        raise ApiFailure(404, "result_not_found", "The result was not found or has expired.")
    return Response(status_code=204)


def install_error_handlers(app) -> None:
    @app.exception_handler(ApiFailure)
    async def handle_api_failure(_request: Request, exc: ApiFailure) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorDetail(code=exc.code, message=exc.message),
            request_id=current_request_id(),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(exclude_none=True),
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorDetail(code="invalid_request", message="The request is invalid."),
            request_id=current_request_id(),
        )
        return JSONResponse(
            status_code=422,
            content=body.model_dump(exclude_none=True),
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_api_error request_id=%s error_type=%s",
            current_request_id(),
            type(exc).__name__,
        )
        body = ErrorResponse(
            error=ErrorDetail(code="internal_error", message="The request could not be completed."),
            request_id=current_request_id(),
        )
        return JSONResponse(
            status_code=500,
            content=body.model_dump(exclude_none=True),
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )
