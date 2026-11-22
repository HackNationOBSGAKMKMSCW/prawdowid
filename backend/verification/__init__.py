"""Full verification flow: claim extraction, article search, two independent assessments.

import verification

async for event in verification.stream(text, submitted_at=sent_at):
    send_to_front(event)   # "evidence", then "input_analysis" / "claims_verdict" as ready
"""

from ._analysis import AnalysisUnavailable
from .models import PartError, VerificationEvent, VerificationReport
from .service import Evidence, Stages, VerificationJob, run, start, stream

__all__ = [
    "AnalysisUnavailable",
    "Evidence",
    "PartError",
    "Stages",
    "VerificationEvent",
    "VerificationJob",
    "VerificationReport",
    "run",
    "start",
    "stream",
]
