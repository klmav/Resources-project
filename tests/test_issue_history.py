from __future__ import annotations

import datetime as dt

from src.models import Issue, IssueLocation, Severity
from src.services.issue_history import (
    find_persistent_red_issues,
    make_issue_key,
    update_history,
)


def _issue(*, code: str, pm: str, person: str, week: str, severity: Severity = Severity.red) -> Issue:
    return Issue(
        severity=severity,
        code=code,
        message="m",
        location=IssueLocation(pm=pm, person=person, week=week),
    )


def test_update_history_marks_resolved_and_resets_on_reappear() -> None:
    day1 = dt.date(2026, 1, 1)
    day2 = dt.date(2026, 1, 2)
    day10 = dt.date(2026, 1, 10)

    i = _issue(code="X", pm="PM1", person="P1", week="01.26")
    hist = update_history(history={}, issues=[i], now=day1)
    k = make_issue_key(i)
    assert k in hist
    assert hist[k].first_seen == day1
    assert hist[k].resolved_at is None

    # Disappears -> resolved
    hist = update_history(history=hist, issues=[], now=day2)
    assert hist[k].resolved_at == day2

    # Reappears later -> new streak
    hist = update_history(history=hist, issues=[i], now=day10)
    assert hist[k].resolved_at is None
    assert hist[k].first_seen == day10


def test_find_persistent_red_issues() -> None:
    day1 = dt.date(2026, 1, 1)
    day20 = dt.date(2026, 1, 21)
    i = _issue(code="X", pm="PM1", person="P1", week="01.26", severity=Severity.red)
    hist = update_history(history={}, issues=[i], now=day1)
    persistent = find_persistent_red_issues(issues=[i], history=hist, now=day20, min_days=14)
    assert persistent
    assert persistent[0].age_days >= 14

