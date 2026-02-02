from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..models import Issue, Severity


def make_issue_key(issue: Issue) -> str:
    """
    Stable-ish fingerprint for "same problem across runs".
    We intentionally avoid cell coordinates (they may shift when rows move).
    """
    parts = [
        issue.code or "",
        (issue.location.pm or "").strip().lower(),
        (issue.location.person or "").strip().lower(),
        (issue.location.week or "").strip().lower(),
    ]
    return "|".join(parts)


@dataclass(frozen=True)
class HistoryEntry:
    first_seen: dt.date
    last_seen: dt.date
    seen_count: int
    resolved_at: Optional[dt.date] = None


def _parse_date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def _entry_from_dict(d: dict[str, Any]) -> HistoryEntry:
    return HistoryEntry(
        first_seen=_parse_date(d["first_seen"]),
        last_seen=_parse_date(d["last_seen"]),
        seen_count=int(d.get("seen_count", 0)),
        resolved_at=_parse_date(d["resolved_at"]) if d.get("resolved_at") else None,
    )


def _entry_to_dict(e: HistoryEntry) -> dict[str, Any]:
    return {
        "first_seen": e.first_seen.isoformat(),
        "last_seen": e.last_seen.isoformat(),
        "seen_count": int(e.seen_count),
        "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
    }


def load_history(path: str | Path) -> dict[str, HistoryEntry]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, HistoryEntry] = {}
    for k, v in data.items():
        if not isinstance(k, str) or not isinstance(v, dict):
            continue
        try:
            out[k] = _entry_from_dict(v)
        except Exception:
            continue
    return out


def save_history(path: str | Path, history: dict[str, HistoryEntry]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {k: _entry_to_dict(v) for k, v in history.items()}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def update_history(
    *,
    history: dict[str, HistoryEntry],
    issues: list[Issue],
    now: dt.date,
) -> dict[str, HistoryEntry]:
    """
    Updates history in-memory.
    - If issue appears and was resolved earlier -> new streak (reset first_seen).
    - If issue disappears -> mark resolved_at=now.
    """
    current_keys: set[str] = set()
    for it in issues:
        k = make_issue_key(it)
        current_keys.add(k)
        prev = history.get(k)
        if prev is None:
            history[k] = HistoryEntry(first_seen=now, last_seen=now, seen_count=1, resolved_at=None)
            continue
        if prev.resolved_at is not None:
            history[k] = HistoryEntry(first_seen=now, last_seen=now, seen_count=1, resolved_at=None)
            continue
        history[k] = HistoryEntry(
            first_seen=prev.first_seen,
            last_seen=now,
            seen_count=prev.seen_count + 1,
            resolved_at=None,
        )

    # mark resolved
    for k, prev in list(history.items()):
        if k in current_keys:
            continue
        if prev.resolved_at is None:
            history[k] = HistoryEntry(
                first_seen=prev.first_seen,
                last_seen=prev.last_seen,
                seen_count=prev.seen_count,
                resolved_at=now,
            )

    return history


def update_history_file(
    *,
    path: str | Path,
    issues: list[Issue],
    now: dt.date,
) -> dict[str, HistoryEntry]:
    history = load_history(path)
    updated = update_history(history=history, issues=issues, now=now)
    save_history(path, updated)
    return updated


@dataclass(frozen=True)
class PersistentIssue:
    key: str
    age_days: int
    issue: Issue


def find_persistent_red_issues(
    *,
    issues: list[Issue],
    history: dict[str, HistoryEntry],
    now: dt.date,
    min_days: int,
) -> list[PersistentIssue]:
    out: list[PersistentIssue] = []
    for it in issues:
        if it.severity != Severity.red:
            continue
        k = make_issue_key(it)
        ent = history.get(k)
        if ent is None or ent.resolved_at is not None:
            continue
        age = (now - ent.first_seen).days
        if age >= min_days:
            out.append(PersistentIssue(key=k, age_days=age, issue=it))
    out.sort(key=lambda x: (-x.age_days, x.issue.code))
    return out

