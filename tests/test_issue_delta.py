from __future__ import annotations

import datetime as dt

from src.models import Issue, IssueLocation, Severity
from src.services.issue_delta import build_snapshot, compute_delta, load_snapshot


def _issue(code: str, sev: Severity) -> Issue:
    return Issue(
        severity=sev,
        code=code,
        message="m",
        location=IssueLocation(pm="PM1", person="P1", week="01.26"),
    )


def test_delta_new_resolved_and_severity_changes() -> None:
    prev_issues = [_issue("A", Severity.yellow), _issue("B", Severity.red)]
    prev = build_snapshot(issues=prev_issues, now=dt.date(2026, 1, 1))

    cur_issues = [_issue("A", Severity.red), _issue("C", Severity.info)]
    rep = compute_delta(prev=prev, current_issues=cur_issues)

    # New: C
    assert any(x.issue and x.issue.code == "C" for x in rep.new)
    # Resolved: B
    b = next((x for x in rep.resolved if x.key.startswith("B|")), None)
    assert b is not None
    assert b.prev is not None
    assert b.prev.severity == "red"
    assert b.prev.code == "B"
    # A worsened yellow -> red
    assert any(x.issue and x.issue.code == "A" for x in rep.worsened)
    # No improved
    assert not rep.improved


def test_load_snapshot_backwards_compat_string_values(tmp_path) -> None:
    # old schema: by_key maps key -> "red"
    p = tmp_path / "issue_snapshot.json"
    p.write_text('{"date":"2026-01-01","by_key":{"CODE|pm|person|01.26":"red"}}', encoding="utf-8")
    snap = load_snapshot(p)
    assert snap is not None
    it = snap.by_key["CODE|pm|person|01.26"]
    assert it.severity == "red"
    assert it.code == "CODE"

