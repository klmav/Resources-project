from __future__ import annotations

from src.main import format_issues_text
from src.models import Issue, IssueLocation, Severity


def test_format_issues_text_includes_top_counts_and_pm_breakdown() -> None:
    issues: list[Issue] = []
    # 120 empty-month issues across 2 PMs
    for _ in range(80):
        issues.append(
            Issue(
                severity=Severity.yellow,
                code="MONTH_CELL_EMPTY",
                message="Пустые месяцы: 01.26 (всего 1).",
                location=IssueLocation(person="Иванов Иван", pm="PM A"),
            )
        )
    for _ in range(40):
        issues.append(
            Issue(
                severity=Severity.yellow,
                code="MONTH_CELL_EMPTY",
                message="Пустые месяцы: 02.26 (всего 1).",
                location=IssueLocation(person="Петров Петр", pm="PM B"),
            )
        )
    # plus one other issue
    issues.append(
        Issue(
            severity=Severity.red,
            code="MONTH_CELL_NOT_HALF_STEP",
            message="Значение 9.66 не кратно 0.5.",
            location=IssueLocation(person="Иванов Иван", pm="PM A", week="2026-01-01"),
        )
    )

    text = format_issues_text(issues, limit=20, full=False)
    assert "Топ проблем по типу:" in text
    assert "MONTH_CELL_EMPTY" in text
    assert "Пустые месяцы (MONTH_CELL_EMPTY) по PM:" in text
    # PM A should be listed before PM B due to count
    assert "PM A: 80" in text
    assert "PM B: 40" in text
    # should be truncated
    assert "… и ещё" in text

