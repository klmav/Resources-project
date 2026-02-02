from __future__ import annotations

from typing import Optional

from ..checks.resource_plan_xlsx import (
    _active_month_cols,  # noqa: SLF001
    _find_header,  # noqa: SLF001
    _format_month_label,  # noqa: SLF001
    _is_multiple_of_half,  # noqa: SLF001
    _to_float,  # noqa: SLF001
)
from ..fixes.models import CellRef, CellUpdate, FixPlan
from ..sheets.client import SheetValues


# Excel-like fill colors (ARGB)
FILL_ORANGE = "FFFFE599"  # light orange
FILL_PURPLE = "FFD9D2E9"  # light purple
FILL_RED = "FFFFC7CE"  # light red


PM_COL = 8  # I (0-based)
EMPLOYEE_COL = 9  # J (0-based)


def plan_highlight_invalid_month_cells(
    *,
    sheet_values: SheetValues,
    sheet_name: str,
    pm_filter: Optional[str] = None,
) -> FixPlan:
    """
    Highlights invalid month cells (without changing values):
    - non-numeric values
    - negative values
    - values not multiple of 0.5
    - values exceeding workdays for month (if workdays row exists)
    """
    parsed = _find_header(sheet_values)
    if parsed is None:
        return FixPlan(sheet_name=sheet_name, description="no header", updates=[])

    header = sheet_values.values[parsed.header_row_idx]
    month_cols = _active_month_cols(parsed, header)

    # Pre-parse workdays if service row exists
    workdays: dict[int, float] = {}
    if parsed.header_row_idx > 0:
        workdays_row = sheet_values.values[parsed.header_row_idx - 1]
        for c_idx in month_cols:
            cell = workdays_row[c_idx] if c_idx < len(workdays_row) else ""
            ok, num = _to_float(cell)
            if ok and cell != "":
                workdays[c_idx] = num

    updates: list[CellUpdate] = []
    for r_idx in range(parsed.header_row_idx + 1, len(sheet_values.values)):
        row = sheet_values.values[r_idx]
        pm = row[PM_COL].strip() if PM_COL < len(row) else ""
        employee = row[EMPLOYEE_COL].strip() if EMPLOYEE_COL < len(row) else ""

        if pm_filter and pm_filter.strip():
            if pm_filter.strip().lower() not in pm.lower():
                continue

        for c_idx in month_cols:
            month_header = header[c_idx] if c_idx < len(header) else ""
            month_label = _format_month_label(month_header)
            cell = row[c_idx] if c_idx < len(row) else ""
            if cell == "":
                continue

            ok, num = _to_float(cell)
            if not ok:
                updates.append(
                    CellUpdate(
                        sheet_name=sheet_name,
                        cell=CellRef(row=r_idx + 1, col=c_idx + 1),
                        kind="highlight",
                        fill_rgb=FILL_ORANGE,
                        month_label=month_label,
                        reason=f"MONTH_CELLS_NUMERIC: не число ('{cell}').",
                        pm=pm or None,
                        person=employee or None,
                    )
                )
                continue

            if num < 0:
                updates.append(
                    CellUpdate(
                        sheet_name=sheet_name,
                        cell=CellRef(row=r_idx + 1, col=c_idx + 1),
                        kind="highlight",
                        fill_rgb=FILL_ORANGE,
                        month_label=month_label,
                        reason=f"MONTH_CELLS_NONNEGATIVE: отрицательное значение {num}.",
                        pm=pm or None,
                        person=employee or None,
                    )
                )
                continue

            if not _is_multiple_of_half(num):
                updates.append(
                    CellUpdate(
                        sheet_name=sheet_name,
                        cell=CellRef(row=r_idx + 1, col=c_idx + 1),
                        kind="highlight",
                        fill_rgb=FILL_PURPLE,
                        month_label=month_label,
                        reason=f"MONTH_CELL_NOT_HALF_STEP: {num} не кратно 0.5.",
                        pm=pm or None,
                        person=employee or None,
                    )
                )
                continue

            wd = workdays.get(c_idx)
            if wd is not None and num > wd:
                updates.append(
                    CellUpdate(
                        sheet_name=sheet_name,
                        cell=CellRef(row=r_idx + 1, col=c_idx + 1),
                        kind="highlight",
                        fill_rgb=FILL_RED,
                        month_label=month_label,
                        reason=f"ALLOCATION_EXCEEDS_WORKDAYS: {num} > {wd} (раб. дни).",
                        pm=pm or None,
                        person=employee or None,
                    )
                )

    return FixPlan(
        sheet_name=sheet_name,
        description="Highlight invalid month cells (numeric/step/nonnegative/workdays)",
        updates=updates,
    )

