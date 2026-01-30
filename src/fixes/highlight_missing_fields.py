from __future__ import annotations

from typing import Optional

from ..checks.resource_plan_xlsx import (
    _active_month_cols,  # noqa: SLF001
    _find_header,  # noqa: SLF001
    _to_float,  # noqa: SLF001
)
from ..fixes.models import CellRef, CellUpdate, FixPlan
from ..sheets.client import SheetValues


PM_COL = 8  # I
EMPLOYEE_COL = 9  # J

# Excel-like highlight colors (ARGB)
FILL_RED = "FFFFC7CE"  # light red
FILL_YELLOW = "FFFFF2CC"  # light yellow


def plan_highlight_missing_pm_and_employee(
    *,
    sheet_values: SheetValues,
    sheet_name: str,
    pm_filter: Optional[str] = None,
) -> FixPlan:
    """
    "Fix" without auto-filling values: highlight empty PM/Employee cells when any planned days > 0.
    """
    parsed = _find_header(sheet_values)
    if parsed is None:
        return FixPlan(sheet_name=sheet_name, description="no header", updates=[])

    header = sheet_values.values[parsed.header_row_idx]
    month_cols = _active_month_cols(parsed, header)

    updates: list[CellUpdate] = []
    for r_idx in range(parsed.header_row_idx + 1, len(sheet_values.values)):
        row = sheet_values.values[r_idx]
        pm = row[PM_COL].strip() if PM_COL < len(row) else ""
        employee = row[EMPLOYEE_COL].strip() if EMPLOYEE_COL < len(row) else ""

        if pm_filter and pm_filter.strip():
            if pm_filter.strip().lower() not in pm.lower():
                continue

        has_days = False
        for c in month_cols:
            cell = row[c] if c < len(row) else ""
            ok, num = _to_float(cell)
            if ok and cell != "" and num > 0:
                has_days = True
                break
        if not has_days:
            continue

        if pm == "":
            updates.append(
                CellUpdate(
                    sheet_name=sheet_name,
                    cell=CellRef(row=r_idx + 1, col=PM_COL + 1),
                    kind="highlight",
                    fill_rgb=FILL_RED,
                    reason="Не заполнен PM при наличии запланированных дней.",
                    person=employee or None,
                )
            )

        if employee == "":
            updates.append(
                CellUpdate(
                    sheet_name=sheet_name,
                    cell=CellRef(row=r_idx + 1, col=EMPLOYEE_COL + 1),
                    kind="highlight",
                    fill_rgb=FILL_YELLOW,
                    reason="Не заполнено ФИО сотрудника при наличии запланированных дней.",
                    pm=pm or None,
                )
            )

    return FixPlan(
        sheet_name=sheet_name,
        description="Highlight missing PM/Employee for rows with planned days",
        updates=updates,
    )
