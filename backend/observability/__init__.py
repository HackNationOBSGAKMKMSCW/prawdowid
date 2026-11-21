"""Application-wide logging with zero edits in other modules.

    from observability import init
    init()  # once, at process start (API server, CLI, bot)

After ``init()`` every OpenAI SDK call, every apiReading/Diffbot HTTP request, the
textAnalysis sanitizer and the known pipeline stages are logged automatically to
``backend/logs/app.jsonl`` (JSON Lines). See README.md in this package.
"""

from .context import RequestMetrics, current, current_request_id, request_scope
from .events import log_abstain, log_event, log_prompt_injection, text_fingerprint
from .instrument import register_stage, status
from .logconfig import init, is_initialized, shutdown
from .middleware import ObservabilityMiddleware
from .tracing import stage, traced

__all__ = [
    "ObservabilityMiddleware",
    "RequestMetrics",
    "current",
    "current_request_id",
    "init",
    "is_initialized",
    "log_abstain",
    "log_event",
    "log_prompt_injection",
    "register_stage",
    "request_scope",
    "shutdown",
    "stage",
    "status",
    "text_fingerprint",
    "traced",
]
