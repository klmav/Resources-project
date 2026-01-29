from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Optional


class Severity(StrEnum):
    red = "red"
    yellow = "yellow"
    info = "info"


@dataclass(frozen=True)
class IssueLocation:
    person: Optional[str] = None
    week: Optional[str] = None
    cell: Optional[str] = None


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    message: str
    location: IssueLocation = IssueLocation()
    suggestion: Optional[str] = None

