"""Result types of the known-disinformation check."""

from typing import Literal

from pydantic import BaseModel

SOURCE_NAME = "EUvsDisinfo"


class DisinfoCase(BaseModel):
    """A documented pro-Kremlin disinformation case (EUvsDisinfo ``claim_review``)."""

    case_id: str  # the case URL: stable and unique
    title: str
    summary: str = ""  # the disinformation message as recorded by EUvsDisinfo
    disproof: str = ""  # EUvsDisinfo's response, when the database has one
    url: str
    source: str = SOURCE_NAME


class CandidateRef(BaseModel):
    case_id: str
    title: str


class StatementCheck(BaseModel):
    index: int  # 1-based, same as the verdict's claim id ``T{index}``
    statement: str
    queries: list[str] = []
    candidates: list[CandidateRef] = []
    match: DisinfoCase | None = None
    reason: str = ""


class DisinfoCheck(BaseModel):
    status: Literal["ok", "disabled", "error"]
    statements: list[StatementCheck] = []
    warnings: list[str] = []
    duration_ms: int = 0

    @property
    def matches(self) -> list[StatementCheck]:
        return [check for check in self.statements if check.match is not None]
