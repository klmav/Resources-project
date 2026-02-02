from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..models import Issue, Severity
from .issue_history import make_issue_key


def _sev_rank(s: Severity) -> int:
    # higher = worse
    if s == Severity.red:
        return 3
    if s == Severity.yellow:
        return 2
    return 1


@dataclass(frozen=True)
class SnapshotItem:
    severity: str  # "red" | "yellow" | "info"
    code: str
    pm: Optional[str] = None
    person: Optional[str] = None
    week: Optional[str] = None


@dataclass(frozen=True)
class Snapshot:
    date: dt.date
    by_key: dict[str, SnapshotItem]  # key -> metadata


def load_snapshot(path: str | Path) -> Optional[Snapshot]:
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if "date" not in data or "by_key" not in data:
        return None
    if not isinstance(data["by_key"], dict):
        return None
    try:
        d = dt.datetime.strptime(str(data["date"]), "%Y-%m-%d").date()
    except Exception:
        return None
    by_key: dict[str, SnapshotItem] = {}
    for k, v in data["by_key"].items():
        if not isinstance(k, str):
            continue
        # Backward compatibility: old schema stored severity as a string.
        if isinstance(v, str):
            code, pm, person, week = (k.split("|") + ["", "", "", ""])[:4]
            by_key[k] = SnapshotItem(
                severity=v,
                code=code,
                pm=pm or None,
                person=person or None,
                week=week or None,
            )
            continue
        if isinstance(v, dict):
            sev = v.get("severity")
            if not isinstance(sev, str):
                continue
            code = v.get("code")
            if not isinstance(code, str):
                # fall back to key prefix
                code = (k.split("|") + [""])[0]
            pm = v.get("pm") if isinstance(v.get("pm"), str) else None
            person = v.get("person") if isinstance(v.get("person"), str) else None
            week = v.get("week") if isinstance(v.get("week"), str) else None
            by_key[k] = SnapshotItem(severity=sev, code=code, pm=pm, person=person, week=week)
    return Snapshot(date=d, by_key=by_key)


def save_snapshot(path: str | Path, snapshot: Snapshot) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    by_key = {
        k: {
            "severity": v.severity,
            "code": v.code,
            "pm": v.pm,
            "person": v.person,
            "week": v.week,
        }
        for k, v in snapshot.by_key.items()
    }
    data = {"date": snapshot.date.isoformat(), "by_key": by_key}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_snapshot(*, issues: list[Issue], now: dt.date) -> Snapshot:
    by_key: dict[str, SnapshotItem] = {}
    for it in issues:
        by_key[make_issue_key(it)] = SnapshotItem(
            severity=str(it.severity),
            code=it.code or "",
            pm=it.location.pm or None,
            person=it.location.person or None,
            week=it.location.week or None,
        )
    return Snapshot(date=now, by_key=by_key)


@dataclass(frozen=True)
class DeltaItem:
    key: str
    severity: Optional[str] = None
    prev_severity: Optional[str] = None
    issue: Optional[Issue] = None
    prev: Optional[SnapshotItem] = None


@dataclass(frozen=True)
class DeltaReport:
    prev_date: Optional[dt.date]
    new: list[DeltaItem]
    resolved: list[DeltaItem]
    worsened: list[DeltaItem]
    improved: list[DeltaItem]


def compute_delta(
    *,
    prev: Optional[Snapshot],
    current_issues: list[Issue],
) -> DeltaReport:
    cur_by_key: dict[str, Issue] = {make_issue_key(i): i for i in current_issues}
    cur_keys = set(cur_by_key.keys())

    prev_by_key = prev.by_key if prev else {}
    prev_keys = set(prev_by_key.keys())

    new_keys = sorted(cur_keys - prev_keys)
    resolved_keys = sorted(prev_keys - cur_keys)

    worsened: list[DeltaItem] = []
    improved: list[DeltaItem] = []
    for k in sorted(cur_keys & prev_keys):
        cur = cur_by_key[k]
        prev_item = prev_by_key.get(k)
        prev_s = prev_item.severity if prev_item else None
        cur_s = str(cur.severity)
        if not prev_s or prev_s == cur_s:
            continue
        try:
            prev_rank = _sev_rank(Severity(prev_s))
            cur_rank = _sev_rank(cur.severity)
        except Exception:
            continue
        if cur_rank > prev_rank:
            worsened.append(
                DeltaItem(key=k, severity=cur_s, prev_severity=prev_s, issue=cur, prev=prev_item)
            )
        elif cur_rank < prev_rank:
            improved.append(
                DeltaItem(key=k, severity=cur_s, prev_severity=prev_s, issue=cur, prev=prev_item)
            )

    new_items = [DeltaItem(key=k, severity=str(cur_by_key[k].severity), issue=cur_by_key[k]) for k in new_keys]
    resolved_items = [
        DeltaItem(key=k, prev_severity=prev_by_key.get(k).severity if prev_by_key.get(k) else None, prev=prev_by_key.get(k))
        for k in resolved_keys
    ]

    return DeltaReport(
        prev_date=prev.date if prev else None,
        new=new_items,
        resolved=resolved_items,
        worsened=worsened,
        improved=improved,
    )

