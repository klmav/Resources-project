from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Optional

from ..checks.resource_plan_xlsx import (
    _active_month_cols,  # noqa: SLF001
    _find_header,  # noqa: SLF001
    _format_month_label,  # noqa: SLF001
    _parse_month_header,  # noqa: SLF001
    _to_float,  # noqa: SLF001
)
from ..sheets.client import SheetValues


@dataclass(frozen=True)
class LoadResult:
    person: str
    month_label: str  # MM.YY
    planned_days: float
    workdays: Optional[float]
    percent: Optional[float]
    bad_cells: list[str]  # A1 refs or RnCn


_MM_YY = re.compile(r"\b(0[1-9]|1[0-2])\.(\d{2}|\d{4})\b")
_YYYY_MM = re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])\b")

_RU_MONTHS = {
    "янв": 1,
    "фев": 2,
    "мар": 3,
    "апр": 4,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "авг": 8,
    "сен": 9,
    "сент": 9,
    "окт": 10,
    "ноя": 11,
    "дек": 12,
}


def _parse_month_from_text(text: str, *, default_year: int) -> Optional[dt.date]:
    """
    Returns first-of-month date (YYYY-MM-01) from text.
    Supports: '01.26', '01.2026', '2026-01', 'январь 2026', 'в январе'.
    """
    t = (text or "").lower()

    m = _MM_YY.search(t)
    if m:
        mm = int(m.group(1))
        yy = m.group(2)
        year = int(yy) if len(yy) == 4 else 2000 + int(yy)
        return dt.date(year, mm, 1)

    m = _YYYY_MM.search(t)
    if m:
        year = int(m.group(1))
        mm = int(m.group(2))
        return dt.date(year, mm, 1)

    # Russian month name (prefix)
    # try tokens, accept "январь"/"январе" etc by prefix
    tokens = re.findall(r"[а-яё]+|\d{4}", t)
    year = None
    for tok in tokens:
        if tok.isdigit() and len(tok) == 4:
            year = int(tok)
            break
    year = year or default_year

    for tok in tokens:
        if tok.isdigit():
            continue
        for pref, mm in _RU_MONTHS.items():
            if tok.startswith(pref):
                return dt.date(year, mm, 1)

    return None


def compute_person_month_load(
    *,
    sheet_values: SheetValues,
    person_query: str,
    month_text: str,
) -> Optional[LoadResult]:
    """
    Sum planned days across all rows for a person (col J) for a selected month column.
    Percent = planned_days / workdays_in_month * 100 (if workdays available).
    """
    parsed = _find_header(sheet_values)
    if parsed is None:
        return None

    header = sheet_values.values[parsed.header_row_idx]
    active_year = parsed.active_year or dt.date.today().year
    month_dt = _parse_month_from_text(month_text, default_year=active_year)
    if month_dt is None:
        return None

    # find matching month column in active year cols
    month_cols = _active_month_cols(parsed, header)
    month_col_idx = None
    for c in month_cols:
        md = _parse_month_header(header[c])
        if md and md.year == month_dt.year and md.month == month_dt.month:
            month_col_idx = c
            break
    if month_col_idx is None:
        return None

    month_label = _format_month_label(header[month_col_idx])

    # workdays row (if present)
    workdays_val: Optional[float] = None
    if parsed.header_row_idx > 0:
        workdays_row = sheet_values.values[parsed.header_row_idx - 1]
        w_cell = workdays_row[month_col_idx] if month_col_idx < len(workdays_row) else ""
        ok, num = _to_float(w_cell)
        if ok and w_cell != "":
            workdays_val = num

    q = person_query.strip().lower()
    planned = 0.0
    bad_cells: list[str] = []

    person_col = 9  # J

    for r_idx in range(parsed.header_row_idx + 1, len(sheet_values.values)):
        row = sheet_values.values[r_idx]
        person = row[person_col].strip() if person_col < len(row) else ""
        if not person:
            continue
        if q not in person.lower():
            continue

        cell = row[month_col_idx] if month_col_idx < len(row) else ""
        if cell == "":
            continue
        ok, num = _to_float(cell)
        if not ok:
            # Use RnCn ref to avoid Excel-letter conversion duplication in service.
            bad_cells.append(f"R{r_idx+1}C{month_col_idx+1}")
            continue
        planned += num

    percent: Optional[float] = None
    if workdays_val and workdays_val > 0:
        percent = planned / workdays_val * 100.0

    return LoadResult(
        person=person_query.strip(),
        month_label=month_label,
        planned_days=planned,
        workdays=workdays_val,
        percent=percent,
        bad_cells=bad_cells,
    )

