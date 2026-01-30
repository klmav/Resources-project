from __future__ import annotations

import datetime as dt
from typing import Optional

from ..checks.resource_plan_xlsx import (
    _active_month_cols,  # noqa: SLF001 - internal reuse within our codebase
    _find_header,  # noqa: SLF001
    _forward_month_cols,  # noqa: SLF001
    _is_empty,  # noqa: SLF001
    _is_true,  # noqa: SLF001
)
from ..fixes.models import CellRef, CellUpdate, FixPlan
from ..local.xlsx_reader import read_xlsx_as_sheet_values
from ..sheets.client import SheetValues


def plan_fill_empty_months_with_zero(
    *,
    sheet_values: SheetValues,
    sheet_name: str,
    months_ahead: int = 2,
    today: Optional[dt.date] = None,
    pm_filter: Optional[str] = None,
) -> FixPlan:
    """
    For rows that are active (in?=True) OR have any plan in active year,
    ensure current+next month cells are not empty by setting empty cells to 0.
    """
    parsed = _find_header(sheet_values)
    if parsed is None:
        return FixPlan(sheet_name=sheet_name, description="no header", updates=[])

    header = sheet_values.values[parsed.header_row_idx]
    today = today or dt.date.today()
    target_month_cols = _forward_month_cols(
        parsed=parsed,
        header=header,
        today=today,
        months_ahead=months_ahead,
    )
    if not target_month_cols:
        return FixPlan(sheet_name=sheet_name, description="no target months", updates=[])

    active_year_cols = _active_month_cols(parsed, header)

    pm_col = 8  # I
    employee_col = 9  # J
    in_col = 10  # K

    updates: list[CellUpdate] = []
    for r_idx in range(parsed.header_row_idx + 1, len(sheet_values.values)):
        row = sheet_values.values[r_idx]

        pm = row[pm_col].strip() if pm_col < len(row) else ""
        employee = row[employee_col].strip() if employee_col < len(row) else ""

        if pm_filter and pm_filter.strip():
            if pm_filter.strip().lower() not in pm.lower():
                continue

        in_val = row[in_col] if in_col < len(row) else ""
        is_in = _is_true(in_val)
        has_any_plan_in_year = any(
            (not _is_empty(row[c])) if c < len(row) else False for c in active_year_cols
        )
        if not (is_in or has_any_plan_in_year):
            continue

        for c_idx in target_month_cols:
            cell = row[c_idx] if c_idx < len(row) else ""
            if _is_empty(cell):
                updates.append(
                    CellUpdate(
                        sheet_name=sheet_name,
                        cell=CellRef(row=r_idx + 1, col=c_idx + 1),
                        new_value=0,
                        reason=f"Fill empty month with 0 (horizon {months_ahead} months).",
                        pm=pm or None,
                        person=employee or None,
                    )
                )

    desc = f"Set empty current+next month cells to 0 (months_ahead={months_ahead})"
    if pm_filter:
        desc += f", pm_filter='{pm_filter}'"
    return FixPlan(sheet_name=sheet_name, description=desc, updates=updates)


def plan_fill_empty_months_with_zero_from_xlsx(
    *,
    path: str,
    sheet_name: Optional[str] = None,
    months_ahead: int = 2,
    today: Optional[dt.date] = None,
    pm_filter: Optional[str] = None,
) -> FixPlan:
    data = read_xlsx_as_sheet_values(path=path, sheet_name=sheet_name)
    # xlsx_reader includes row above header; this is enough for header detection logic.
    return plan_fill_empty_months_with_zero(
        sheet_values=data,
        sheet_name=sheet_name or "(first)",
        months_ahead=months_ahead,
        today=today,
        pm_filter=pm_filter,
    )

