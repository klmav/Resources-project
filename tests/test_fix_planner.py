from __future__ import annotations

import datetime as dt

from src.fixes.month_empty_to_zero import plan_fill_empty_months_with_zero
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

