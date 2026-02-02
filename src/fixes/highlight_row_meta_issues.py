from __future__ import annotations

from typing import Iterable, Optional

from ..checks.resource_plan_xlsx import (
    _active_month_cols,  # noqa: SLF001
    _find_header,  # noqa: SLF001
    _is_true,  # noqa: SLF001
    _to_float,  # noqa: SLF001
)
from ..fixes.models import CellRef, CellUpdate, FixPlan
from ..sheets.client import SheetValues


# Excel-like fill colors (ARGB)
FILL_RED = "FFFFC7CE"  # light red
FILL_YELLOW = "FFFFF2CC"  # light yellow
FILL_ORANGE = "FFFFE599"  # light orange


PM_COL = 8  # I (0-based)
EMPLOYEE_COL = 9  # J (0-based)
IN_COL = 10  # K (0-based)


def _matches_pm(pm_cell: str, pm_filter: Optional[str]) -> bool:
    if not pm_filter or not pm_filter.strip():
        return True
    return pm_filter.strip().lower() in (pm_cell or "").strip().lower()


def _row_has_planned_days(
    *,
    row: list[str],
    month_cols: Iterable[int],
) -> bool:
    for c_idx in month_cols:
        cell = row[c_idx] if c_idx < len(row) else ""
        ok, num = _to_float(cell)
        if ok and cell != "" and num > 0:
            return True
    return False


def plan_highlight_role_code_invalid(
    *,
    sheet_values: SheetValues,
    sheet_name: str,
    pm_filter: Optional[str] = None,
) -> FixPlan:
    """
    Highlights invalid role codes in column A.
    Safe: does NOT change values.
    """
    parsed = _find_header(sheet_values)
    if parsed is None:
        return FixPlan(sheet_name=sheet_name, description="no header", updates=[])

    role_col = 0
    allowed = {"A", "D", "PM", "BI"}

    updates: list[CellUpdate] = []
    for r_idx in range(parsed.header_row_idx + 1, len(sheet_values.values)):
        row = sheet_values.values[r_idx]
        pm = row[PM_COL].strip() if PM_COL < len(row) else ""
        if not _matches_pm(pm, pm_filter):
            continue

        role = (row[role_col] if role_col < len(row) else "").strip().upper()
        if role and role not in allowed:
            employee = row[EMPLOYEE_COL].strip() if EMPLOYEE_COL < len(row) else ""
            updates.append(
                CellUpdate(
                    sheet_name=sheet_name,
                    cell=CellRef(row=r_idx + 1, col=role_col + 1),
                    kind="highlight",
                    fill_rgb=FILL_RED,
                    reason=f"ROLE_CODE_INVALID: неизвестная роль '{role}' (ожидалось A/D/PM/BI).",
                    pm=pm or None,
                    person=employee or None,
                )
            )

    return FixPlan(
        sheet_name=sheet_name,
        description="Highlight invalid role codes",
        updates=updates,
    )


def plan_highlight_in_flag_inconsistent(
    *,
    sheet_values: SheetValues,
    sheet_name: str,
    pm_filter: Optional[str] = None,
) -> FixPlan:
    """
    Highlights 'in?' cell (column K) when there are planned days in months but in? is not True.
    Safe: does NOT change values.
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
        if not _matches_pm(pm, pm_filter):
            continue

        if not _row_has_planned_days(row=row, month_cols=month_cols):
            continue

        in_val = row[IN_COL] if IN_COL < len(row) else ""
        if _is_true(in_val):
            continue

        employee = row[EMPLOYEE_COL].strip() if EMPLOYEE_COL < len(row) else ""
        updates.append(
            CellUpdate(
                sheet_name=sheet_name,
                cell=CellRef(row=r_idx + 1, col=IN_COL + 1),
                kind="highlight",
                fill_rgb=FILL_ORANGE,
                reason="IN_FLAG_INCONSISTENT: есть дни, но 'in?' = False.",
                pm=pm or None,
                person=employee or None,
            )
        )

    return FixPlan(
        sheet_name=sheet_name,
        description="Highlight inconsistent in? flag",
        updates=updates,
    )


def plan_highlight_missing_key_fields(
    *,
    sheet_values: SheetValues,
    sheet_name: str,
    pm_filter: Optional[str] = None,
    required_meta_cols: Optional[list[int]] = None,
) -> FixPlan:
    """
    Highlights empty key meta fields when there are planned days in any month.
    Mirrors KEY_FIELDS_FILLED check idea, but as a safe highlight-only fix.
    """
    parsed = _find_header(sheet_values)
    if parsed is None:
        return FixPlan(sheet_name=sheet_name, description="no header", updates=[])

    header = sheet_values.values[parsed.header_row_idx]
    month_cols = _active_month_cols(parsed, header)
    req = required_meta_cols or [0, 1, 2, 3, 5, 6, 7]

    updates: list[CellUpdate] = []
    for r_idx in range(parsed.header_row_idx + 1, len(sheet_values.values)):
        row = sheet_values.values[r_idx]
        pm = row[PM_COL].strip() if PM_COL < len(row) else ""
        if not _matches_pm(pm, pm_filter):
            continue

        if not _row_has_planned_days(row=row, month_cols=month_cols):
            continue

        employee = row[EMPLOYEE_COL].strip() if EMPLOYEE_COL < len(row) else ""
        for c_idx in req:
            v = row[c_idx] if c_idx < len(row) else ""
            if str(v).strip() == "":
                col_name = header[c_idx] if c_idx < len(header) else f"C{c_idx + 1}"
                updates.append(
                    CellUpdate(
                        sheet_name=sheet_name,
                        cell=CellRef(row=r_idx + 1, col=c_idx + 1),
                        kind="highlight",
                        fill_rgb=FILL_YELLOW,
                        reason=f"KEY_FIELDS_FILLED: поле '{col_name}' пустое при наличии дней.",
                        pm=pm or None,
                        person=employee or None,
                    )
                )

    return FixPlan(
        sheet_name=sheet_name,
        description="Highlight missing key meta fields for rows with planned days",
        updates=updates,
    )

