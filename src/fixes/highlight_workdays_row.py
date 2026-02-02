from __future__ import annotations

from ..checks.resource_plan_xlsx import (
    _active_month_cols,  # noqa: SLF001
    _find_header,  # noqa: SLF001
    _to_float,  # noqa: SLF001
)
from ..fixes.models import CellRef, CellUpdate, FixPlan
from ..sheets.client import SheetValues


# Excel-like fill colors (ARGB)
FILL_RED = "FFFFC7CE"  # light red


def plan_highlight_invalid_workdays_row(
    *,
    sheet_values: SheetValues,
    sheet_name: str,
) -> FixPlan:
    """
    Highlights invalid cells in the "workdays in month" service row (row above header):
    - non-numeric values (e.g. #REF!, text)
    - numeric values <= 0

    Safe: does NOT change values.
    """
    parsed = _find_header(sheet_values)
    if parsed is None:
        return FixPlan(sheet_name=sheet_name, description="no header", updates=[])

    if parsed.header_row_idx <= 0:
        # no service row available
        return FixPlan(sheet_name=sheet_name, description="no workdays row", updates=[])

    workdays_row = sheet_values.values[parsed.header_row_idx - 1]
    header = sheet_values.values[parsed.header_row_idx]
    month_cols = _active_month_cols(parsed, header)

    updates: list[CellUpdate] = []
    for c_idx in month_cols:
        cell = workdays_row[c_idx] if c_idx < len(workdays_row) else ""
        ok, num = _to_float(cell)
        if not ok:
            updates.append(
                CellUpdate(
                    sheet_name=sheet_name,
                    cell=CellRef(row=parsed.header_row_idx, col=c_idx + 1),
                    kind="highlight",
                    fill_rgb=FILL_RED,
                    reason=f"WORKDAYS_ROW_NUMERIC: не число ('{cell}').",
                )
            )
            continue
        if cell != "" and num <= 0:
            updates.append(
                CellUpdate(
                    sheet_name=sheet_name,
                    cell=CellRef(row=parsed.header_row_idx, col=c_idx + 1),
                    kind="highlight",
                    fill_rgb=FILL_RED,
                    reason=f"WORKDAYS_ROW_NUMERIC: значение <= 0 ({num}).",
                )
            )

    return FixPlan(
        sheet_name=sheet_name,
        description="Highlight invalid workdays row cells (numeric and >0)",
        updates=updates,
    )

