from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..checks.base import run_checks
from ..checks.rules import SheetNotEmptyCheck
from ..config import Settings
from ..models import Issue, IssueLocation, Severity
from ..sheets.client import SheetsClient


@dataclass(frozen=True)
class AuditReport:
    issues: List[Issue]

    def is_ok(self) -> bool:
        return len(self.issues) == 0


class AuditService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sheets = SheetsClient(settings=settings)

    def run(self) -> AuditReport:
        if not self._settings.google_sheet_id:
            return AuditReport(
                issues=[
                    Issue(
                        severity=Severity.red,
                        code="MISSING_CONFIG",
                        message="Не задан GOOGLE_SHEET_ID (id таблицы).",
                        location=IssueLocation(),
                        suggestion="Открой таблицу → скопируй id из URL и положи в GOOGLE_SHEET_ID.",
                    )
                ]
            )

        try:
            sheet_values = self._sheets.read_range()
        except Exception as e:  # noqa: BLE001 - MVP: want a user-friendly report
            return AuditReport(
                issues=[
                    Issue(
                        severity=Severity.red,
                        code="SHEETS_READ_FAILED",
                        message=f"Не смог прочитать Google Sheets: {type(e).__name__}: {e}",
                        location=IssueLocation(),
                        suggestion=(
                            "Проверь что включен Google Sheets API, "
                            "что GOOGLE_SERVICE_ACCOUNT_FILE указывает на JSON ключ, "
                            "и что таблица расшарена на email сервис-аккаунта (Viewer)."
                        ),
                    )
                ]
            )

        checks = [
            SheetNotEmptyCheck(),
        ]
        issues = run_checks(checks=checks, data=sheet_values)

        return AuditReport(issues=issues)

