from __future__ import annotations

from src.checks.resource_plan_xlsx import (
    AllocationNotExceedWorkdaysCheck,
    EmployeeMonthSumNotExceedWorkdaysCheck,
    EmployeeRequiredWhenHasDaysCheck,
    InFlagConsistencyCheck,
    MonthCellsHalfStepCheck,
    MonthCellsRequiredCheck,
    PmRequiredWhenHasDaysCheck,
)
from src.models import Severity
from src.sheets.client import SheetValues


def _make_sheet_values_for_checks(*, row0_workdays: list[str], row1_header: list[str], rows: list[list[str]]) -> SheetValues:
    """
    Our XLSX reader includes the row above header (workdays) and then header.
    So tests follow that layout:
      row0 = workdays
      row1 = header (A/D ... months ... and a year cell like '2026.0')
      row2+ = data rows
    """
    return SheetValues(values=[row0_workdays, row1_header, *rows])


def _base_header_with_year(*, year: str = "2026.0") -> list[str]:
    """
    Mirrors the real contract:
    A role, B level, C pool, D contract, E client, F top stream, G stream, H task,
    I PM, J employee, K in?, L Sum, M year
    """
    return [
        "A/D",  # A
        "Уровень",  # B
        "Пул",  # C
        "Тип",  # D
        "Ответственный",  # E
        "Верх.стрим",  # F
        "Стрим",  # G
        "Задача",  # H
        "PM",  # I
        "Сотрудник",  # J
        "in?",  # K
        "Sum",  # L
        year,  # M
    ]

def test_month_cells_required_aggregates_per_row_only_active_year() -> None:
    # header includes months for 2025 and 2026; active year is 2026 (via "2026.0" cell)
    header = _base_header_with_year(year="2026.0") + ["2025-01-01", "2025-02-01"] + ["2026-01-01", "2026-02-01", "2026-03-01"]
    workdays = [""] * len(header)
    # workdays for 2026 months
    workdays[-3:] = ["19", "20", "21"]

    # Data row: employee + PM, in? true; leave 2026 months empty -> should produce ONE issue, listing 01.26, 02.26, 03.26
    row = ["A", "L1", "Pool", "t&m", "Client", "Top", "Stream", "Task", "PM One", "Иванов Иван", "True", "0", "0"] + [
        "",  # 2025-01 (ignored)
        "",  # 2025-02 (ignored)
        "",  # 2026-01 (required)
        "",  # 2026-02
        "",  # 2026-03
    ]

    issues = MonthCellsRequiredCheck(months_ahead=2, today=__import__("datetime").date(2026, 1, 15)).run(
        _make_sheet_values_for_checks(row0_workdays=workdays, row1_header=header, rows=[row])
    ).issues

    assert len(issues) == 1
    i = issues[0]
    assert i.code == "MONTH_CELL_EMPTY"
    assert i.severity == Severity.red
    assert i.location.pm == "PM One"
    assert i.location.person == "Иванов Иван"
    # Must list only 2026 months
    assert "01.26" in i.message
    assert "02.26" in i.message
    assert "03.26" not in i.message  # months_ahead=2 => only current+next month
    assert "2025" not in i.message


def test_month_cells_required_triggers_when_future_months_planned_but_current_next_empty() -> None:
    # Today Jan 2026 => require Jan+Feb filled if there is any plan later in 2026
    header = _base_header_with_year(year="2026.0") + ["2026-01-01", "2026-02-01", "2026-03-01"]
    workdays = [""] * len(header)
    workdays[-3:] = ["19", "20", "21"]

    # Plan starts in March only; Jan/Feb empty => should still fail forward-fill rule
    row = ["A", "L1", "Pool", "t&m", "Client", "Top", "Stream", "Task", "PM One", "Иванов Иван", "False", "0", "0", "", "", "5"]

    issues = MonthCellsRequiredCheck(months_ahead=2, today=__import__("datetime").date(2026, 1, 10)).run(
        _make_sheet_values_for_checks(row0_workdays=workdays, row1_header=header, rows=[row])
    ).issues

    assert len(issues) == 1
    assert issues[0].code == "MONTH_CELL_EMPTY"
    assert issues[0].severity == Severity.red
    # Must complain about Jan/Feb only (horizon), not Mar
    assert "01.26" in issues[0].message
    assert "02.26" in issues[0].message
    assert "03.26" not in issues[0].message


def test_month_cells_half_step_flags_non_multiple_of_half() -> None:
    header = _base_header_with_year(year="2026.0") + ["2026-01-01"]
    workdays = [""] * len(header)
    workdays[-1] = "19"
    row = ["A", "L1", "Pool", "t&m", "Client", "Top", "Stream", "Task", "PM One", "Иванов Иван", "True", "0", "0", "9.66"]

    issues = MonthCellsHalfStepCheck().run(_make_sheet_values_for_checks(row0_workdays=workdays, row1_header=header, rows=[row])).issues
    assert len(issues) == 1
    assert issues[0].code == "MONTH_CELL_NOT_HALF_STEP"
    assert issues[0].severity == Severity.red


def test_allocation_not_exceed_workdays() -> None:
    header = _base_header_with_year(year="2026.0") + ["2026-01-01"]
    workdays = [""] * len(header)
    workdays[-1] = "19"
    row = ["A", "L1", "Pool", "t&m", "Client", "Top", "Stream", "Task", "PM One", "Иванов Иван", "True", "0", "0", "20"]

    issues = AllocationNotExceedWorkdaysCheck().run(_make_sheet_values_for_checks(row0_workdays=workdays, row1_header=header, rows=[row])).issues
    assert len(issues) == 1
    assert issues[0].code == "ALLOCATION_EXCEEDS_WORKDAYS"
    assert issues[0].severity == Severity.red


def test_in_flag_inconsistent_warns() -> None:
    header = _base_header_with_year(year="2026.0") + ["2026-01-01", "2026-02-01"]
    workdays = [""] * len(header)
    workdays[-2:] = ["19", "20"]
    row = ["A", "L1", "Pool", "t&m", "Client", "Top", "Stream", "Task", "PM One", "Иванов Иван", "False", "0", "0", "1", ""]

    issues = InFlagConsistencyCheck().run(_make_sheet_values_for_checks(row0_workdays=workdays, row1_header=header, rows=[row])).issues
    assert len(issues) == 1
    assert issues[0].code == "IN_FLAG_INCONSISTENT"
    assert issues[0].severity == Severity.yellow
    assert issues[0].location.pm == "PM One"
    assert issues[0].location.person == "Иванов Иван"


def test_pm_required_when_has_days() -> None:
    header = _base_header_with_year(year="2026.0") + ["2026-01-01"]
    workdays = [""] * len(header)
    workdays[-1] = "19"
    # PM empty but month has days
    row = ["A", "L1", "Pool", "t&m", "Client", "Top", "Stream", "Task", "", "Иванов Иван", "True", "0", "0", "1"]
    issues = PmRequiredWhenHasDaysCheck().run(_make_sheet_values_for_checks(row0_workdays=workdays, row1_header=header, rows=[row])).issues
    assert len(issues) == 1
    assert issues[0].code == "PM_MISSING"
    assert issues[0].severity == Severity.red


def test_employee_required_when_has_days() -> None:
    header = _base_header_with_year(year="2026.0") + ["2026-01-01"]
    workdays = [""] * len(header)
    workdays[-1] = "19"
    # Employee empty but month has days
    row = ["A", "L1", "Pool", "t&m", "Client", "Top", "Stream", "Task", "PM One", "", "True", "0", "0", "1"]
    issues = EmployeeRequiredWhenHasDaysCheck().run(_make_sheet_values_for_checks(row0_workdays=workdays, row1_header=header, rows=[row])).issues
    assert len(issues) == 1
    assert issues[0].code == "EMPLOYEE_MISSING"
    assert issues[0].severity == Severity.red


def test_employee_month_sum_not_exceed_workdays_horizon_2() -> None:
    # current Jan 2026 => check Jan+Feb
    header = _base_header_with_year(year="2026.0") + ["2026-01-01", "2026-02-01", "2026-03-01"]
    workdays = [""] * len(header)
    workdays[-3:] = ["19", "20", "21"]
    # employee has 10 + 9 in Jan => 19 ok; 21 in Feb => overload (20 workdays)
    row1 = ["A", "L1", "Pool", "t&m", "Client", "Top", "Stream", "Task1", "PM One", "Иванов Иван", "True", "0", "0", "10", "21", "0"]
    row2 = ["A", "L1", "Pool", "t&m", "Client", "Top", "Stream", "Task2", "PM One", "Иванов Иван", "True", "0", "0", "9", "", ""]
    issues = EmployeeMonthSumNotExceedWorkdaysCheck(months_ahead=2, today=__import__("datetime").date(2026, 1, 20)).run(
        _make_sheet_values_for_checks(row0_workdays=workdays, row1_header=header, rows=[row1, row2])
    ).issues
    # Should flag Feb only (Jan ok), horizon excludes Mar
    assert any(i.code == "EMPLOYEE_MONTH_SUM_EXCEEDS_WORKDAYS" and "02.26" in i.message for i in issues)
    assert not any(i.code == "EMPLOYEE_MONTH_SUM_EXCEEDS_WORKDAYS" and "03.26" in i.message for i in issues)

