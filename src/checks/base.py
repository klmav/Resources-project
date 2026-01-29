from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, List

from ..models import Issue
from ..sheets.client import SheetValues


@dataclass(frozen=True)
class CheckResult:
    issues: List[Issue]


class Check(ABC):
    code: str

    @abstractmethod
    def run(self, data: SheetValues) -> CheckResult:
        raise NotImplementedError


def run_checks(checks: Iterable[Check], data: SheetValues) -> List[Issue]:
    issues: List[Issue] = []
    for check in checks:
        result = check.run(data)
        issues.extend(result.issues)
    return issues

