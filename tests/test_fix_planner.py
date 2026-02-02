from __future__ import annotations

import datetime as dt

from src.fixes.month_empty_to_zero import plan_fill_empty_months_with_zero
from src.fixes.highlight_missing_fields import (
    plan_highlight_missing_pm_and_employee,
    PM_COL,
    EMPLOYEE_COL,
)
from src.fixes.highlight_invalid_month_cells import plan_highlight_invalid_month_cells
from src.fixes.highlight_workdays_row import plan_highlight_invalid_workdays_row
from src.fixes.highlight_row_meta_issues import (
    IN_COL,
    plan_highlight_in_flag_inconsistent,
    plan_highlight_missing_key_fields,
    plan_highlight_role_code_invalid,
)
from src.fixes.merge_updates import merge_updates
from src.fixes.models import CellRef, CellUpdate
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


def test_plan_highlight_invalid_month_cells_flags_bad_values() -> None:
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
    workdays[13] = "20"

    row = [""] * len(header)
    row[8] = "PM One"
    row[9] = "Иванов Иван"

    # Bad values in month cell
    row_bad_not_numeric = row.copy()
    row_bad_not_numeric[13] = "oops"
    row_bad_negative = row.copy()
    row_bad_negative[13] = "-1"
    row_bad_half_step = row.copy()
    row_bad_half_step[13] = "9.66"
    row_bad_exceeds = row.copy()
    row_bad_exceeds[13] = "21"

    sv = SheetValues(
        values=[workdays, header, row_bad_not_numeric, row_bad_negative, row_bad_half_step, row_bad_exceeds]
    )
    plan = plan_highlight_invalid_month_cells(sheet_values=sv, sheet_name="S")

    assert len(plan.updates) == 4
    reasons = [u.reason for u in plan.updates]
    assert any("MONTH_CELLS_NUMERIC" in r for r in reasons)
    assert any("MONTH_CELLS_NONNEGATIVE" in r for r in reasons)
    assert any("MONTH_CELL_NOT_HALF_STEP" in r for r in reasons)
    assert any("ALLOCATION_EXCEEDS_WORKDAYS" in r for r in reasons)


def test_plan_highlight_invalid_workdays_row() -> None:
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
    workdays[13] = "oops"
    sv = SheetValues(values=[workdays, header])
    plan = plan_highlight_invalid_workdays_row(sheet_values=sv, sheet_name="S")
    assert len(plan.updates) == 1
    u = plan.updates[0]
    # service row is first row in xlsx => openpyxl row=1
    assert (u.cell.row, u.cell.col) == (1, 14)
    assert "WORKDAYS_ROW_NUMERIC" in (u.reason or "")


def test_plan_highlight_role_code_invalid() -> None:
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
    row = [""] * len(header)
    row[0] = "X"
    row[8] = "PM One"
    row[9] = "Иванов Иван"
    row[13] = "1"
    sv = SheetValues(values=[workdays, header, row])
    plan = plan_highlight_role_code_invalid(sheet_values=sv, sheet_name="S")
    assert len(plan.updates) == 1
    u = plan.updates[0]
    assert (u.cell.row, u.cell.col) == (3, 1)
    assert "ROLE_CODE_INVALID" in (u.reason or "")


def test_plan_highlight_in_flag_inconsistent() -> None:
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
    row = [""] * len(header)
    row[8] = "PM One"
    row[9] = "Иванов Иван"
    row[IN_COL] = "False"
    row[13] = "1"
    sv = SheetValues(values=[workdays, header, row])
    plan = plan_highlight_in_flag_inconsistent(sheet_values=sv, sheet_name="S")
    assert len(plan.updates) == 1
    u = plan.updates[0]
    assert (u.cell.row, u.cell.col) == (3, IN_COL + 1)
    assert "IN_FLAG_INCONSISTENT" in (u.reason or "")


def test_plan_highlight_missing_key_fields() -> None:
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
    row = [""] * len(header)
    row[0] = "A"
    row[1] = "L1"
    row[2] = ""  # missing required meta field
    row[3] = "t&m"
    row[5] = "Top"
    row[6] = "Stream"
    row[7] = "Task"
    row[8] = "PM One"
    row[9] = "Иванов Иван"
    row[13] = "1"
    sv = SheetValues(values=[workdays, header, row])
    plan = plan_highlight_missing_key_fields(sheet_values=sv, sheet_name="S")
    assert any(u.cell.col == 3 for u in plan.updates)  # column C
    assert any("KEY_FIELDS_FILLED" in (u.reason or "") for u in plan.updates)


def test_merge_updates_set_value_dominates_and_highlight_merges() -> None:
    u1 = CellUpdate(
        sheet_name="S",
        cell=CellRef(row=10, col=5),
        kind="highlight",
        fill_rgb="FFFFF2CC",
        reason="A",
    )
    u2 = CellUpdate(
        sheet_name="S",
        cell=CellRef(row=10, col=5),
        kind="highlight",
        fill_rgb="FFFFC7CE",
        reason="B",
    )
    u3 = CellUpdate(
        sheet_name="S",
        cell=CellRef(row=10, col=5),
        kind="set_value",
        new_value=0,
        reason="C",
    )
    merged = merge_updates([u1, u2, u3])
    assert len(merged) == 1
    assert merged[0].kind == "set_value"
    assert merged[0].new_value == 0

    merged2 = merge_updates([u1, u2])
    assert len(merged2) == 1
    assert merged2[0].kind == "highlight"
    assert merged2[0].fill_rgb == "FFFFC7CE"
    assert "A" in (merged2[0].reason or "")
    assert "B" in (merged2[0].reason or "")