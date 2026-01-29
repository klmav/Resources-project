from __future__ import annotations

from ..models import Issue, IssueLocation, Severity
from ..sheets.client import SheetValues
from .base import Check, CheckResult


class SheetNotEmptyCheck(Check):
    """
    MVP-заглушка: проверка что в таблице вообще есть данные.
    После того как мы поймем структуру таблицы, заменим на реальные правила.
    """

    code = "SHEET_NOT_EMPTY"

    def run(self, data: SheetValues) -> CheckResult:
        if data.values:
            return CheckResult(issues=[])

        return CheckResult(
            issues=[
                Issue(
                    severity=Severity.red,
                    code=self.code,
                    message="Таблица прочитана, но данных в выбранном диапазоне нет (пусто). Проверь диапазон/лист.",
                    location=IssueLocation(),
                    suggestion="Уточни GOOGLE_SHEET_TAB и GOOGLE_SHEET_RANGE, и убедись что в этом диапазоне есть план.",
                )
            ]
        )

