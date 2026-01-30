from __future__ import annotations

from src.services.load import compute_person_month_load
from src.sheets.client import SheetValues


def test_compute_person_month_load_sums_rows_and_percent() -> None:
    # row0 = workdays, row1 = header, row2+ = data
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
    r1 = [""] * len(header)
    r1[9] = "Иванов Иван"
    r1[13] = "5"
    r2 = [""] * len(header)
    r2[9] = "Иванов Иван"
    r2[13] = "7.5"
    sv = SheetValues(values=[workdays, header, r1, r2])

    res = compute_person_month_load(sheet_values=sv, person_query="Иванов Иван", month_text="01.26")
    assert res is not None
    assert res.month_label == "01.26"
    assert res.planned_days == 12.5
    assert res.workdays == 20.0
    assert res.percent is not None
    assert round(res.percent, 1) == 62.5


def test_compute_person_month_load_reports_bad_cells() -> None:
    # Keep real column positions: PM=8, Employee=9, month at 13
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
    r1 = [""] * len(header)
    r1[9] = "Ivanov Ivan"
    r1[13] = "oops"
    sv = SheetValues(values=[workdays, header, r1])

    res = compute_person_month_load(sheet_values=sv, person_query="Ivanov", month_text="01.26")
    assert res is not None
    assert res.bad_cells

