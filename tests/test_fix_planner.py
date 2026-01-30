from __future__ import annotations

import datetime as dt

from src.fixes.month_empty_to_zero import plan_fill_empty_months_with_zero
from src.fixes.highlight_missing_fields import (
    plan_highlight_missing_pm_and_employee,
    PM_COL,
    EMPLOYEE_COL,
)
from src.sheets.client import SheetValues


def test_plan_fill_empty_months_with_zero_sets_only_horizon_cells() -> None:
    # Layout: row0 workdays, row1 header, row2 data
    header = [
        "A/D",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "PM",  # I
        "Employee",  # J
        "in?",  # K
        "Sum",
        "2026.0",
        "2026-01-01",
        "2026-02-01",
        "2026-03-01",
    ]
    workdays = [""] * len(header)
    row = [
        "A",
        "L1",
        "Pool",
        "t&m",
        "Client",
        "Top",
        "Stream",
        "Task",
        "PM One",
        "Иванов Иван",
        "False",
        "0",
        "0",
        "",  # Jan empty (should be set to 0)
        "",  # Feb empty (should be set to 0)
        "5",  # Mar planned (keeps rule active but should not be changed)
    ]
    sv = SheetValues(values=[workdays, header, row])

    plan = plan_fill_empty_months_with_zero(
        sheet_values=sv,
        sheet_name="S",
        months_ahead=2,
        today=dt.date(2026, 1, 10),
    )

    # Should set Jan+Feb only
    assert len(plan.updates) == 2
    cols = sorted([u.cell.col for u in plan.updates])
    # header indices: Jan col=14, Feb col=15, Mar col=16 (1-based)
    assert cols == [14, 15]
    month_labels = sorted([u.month_label for u in plan.updates])
    assert month_labels == ["01.26", "02.26"]


def test_plan_highlight_missing_pm_and_employee() -> None:
    header = [
        "A/D",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "PM",
        "Employee",
        "in?",
        "Sum",
        "2026.0",
        "2026-01-01",
    ]
    workdays = [""] * len(header)

    # planned days but PM missing
    row1 = [
        "A",
        "L1",
        "Pool",
        "t&m",
        "Client",
        "Top",
        "Stream",
        "Task",
        "",  # PM missing
        "Иванов Иван",
        "True",
        "0",
        "0",
        "1",
    ]
    # planned days but Employee missing
    row2 = [
        "A",
        "L1",
        "Pool",
        "t&m",
        "Client",
        "Top",
        "Stream",
        "Task",
        "PM One",
        "",  # Employee missing
        "True",
        "0",
        "0",
        "1",
    ]
    sv = SheetValues(values=[workdays, header, row1, row2])
    plan = plan_highlight_missing_pm_and_employee(sheet_values=sv, sheet_name="S")

    assert len(plan.updates) == 2
    coords = {(u.cell.row, u.cell.col, u.kind) for u in plan.updates}
    assert (3, PM_COL + 1, "highlight") in coords
    assert (4, EMPLOYEE_COL + 1, "highlight") in coords