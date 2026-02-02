from __future__ import annotations

from dataclasses import replace

from .models import CellUpdate


def _fill_rank(argb: str | None) -> int:
    """
    Higher rank = "more alarming" highlight.
    We keep it simple: red > orange > yellow > other/none.
    """
    if not argb:
        return 0
    v = argb.upper()
    if v == "FFFFC7CE":  # light red
        return 3
    if v == "FFFFE599":  # light orange
        return 2
    if v == "FFFFF2CC":  # light yellow
        return 1
    return 1


def merge_updates(updates: list[CellUpdate]) -> list[CellUpdate]:
    """
    Deterministically merge updates targeting the same cell/kind.

    Rules:
    - set_value dominates highlight on the same cell
    - highlight duplicates are merged: stronger color wins; reasons are concatenated
    """
    # key without kind to allow "set_value dominates"
    best_by_cell: dict[tuple[str, int, int], CellUpdate] = {}

    for u in updates:
        k = (u.sheet_name, u.cell.row, u.cell.col)
        prev = best_by_cell.get(k)
        if prev is None:
            best_by_cell[k] = u
            continue

        if prev.kind == "set_value":
            # already strongest; keep
            continue
        if u.kind == "set_value":
            best_by_cell[k] = u
            continue

        # both highlights -> merge
        reasons: list[str] = []
        if prev.reason:
            reasons.append(prev.reason)
        if u.reason and u.reason not in reasons:
            reasons.append(u.reason)
        merged_reason = " | ".join(reasons) if reasons else None

        # pick stronger color
        prev_rank = _fill_rank(prev.fill_rgb)
        new_rank = _fill_rank(u.fill_rgb)
        fill_rgb = u.fill_rgb if new_rank > prev_rank else prev.fill_rgb

        # keep metadata when missing
        pm = prev.pm or u.pm
        person = prev.person or u.person
        month_label = prev.month_label or u.month_label

        best_by_cell[k] = replace(
            prev,
            fill_rgb=fill_rgb,
            reason=merged_reason,
            pm=pm,
            person=person,
            month_label=month_label,
        )

    # stable order for application/reporting
    out = list(best_by_cell.values())
    out.sort(key=lambda x: (x.sheet_name, x.cell.row, x.cell.col, x.kind))
    return out

