from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import List, Tuple
import datetime as dt

from ..models import Issue, IssueLocation, Severity
from ..sheets.client import SheetValues
from .base import Check, CheckResult


@dataclass(frozen=True)
class ParsedHeader:
    header_row_idx: int  # 0-based within SheetValues
    month_cols: List[int]  # 0-based col indices
    meta_cols: List[int]  # 0-based col indices (non-month)
    active_year: int | None = None


def _find_header(values: SheetValues) -> ParsedHeader | None:
    """
    Finds header row by 'A/D' in col 1 and month columns in the same row.
    """
    if not values.values:
        return None
    for r_idx, row in enumerate(values.values[:30]):
        first = row[0].strip().upper() if len(row) > 0 else ""
        if first != "A/D":
            continue
        month_cols = [i for i, v in enumerate(row) if _looks_like_month(v)]
        if not month_cols:
            continue
        meta_cols = [i for i in range(len(row)) if i not in month_cols]
        active_year = _extract_active_year(row)
        return ParsedHeader(header_row_idx=r_idx, month_cols=month_cols, meta_cols=meta_cols, active_year=active_year)
    return None


def _looks_like_month(s: str) -> bool:
    # In xlsx_reader, dates become YYYY-MM-DD
    if not s:
        return False
    if len(s) != 10:
        return False
    return s[4] == "-" and s[7] == "-"


def _extract_active_year(header_row: List[str]) -> int | None:
    """
    В твоем формате M2 содержит год (например 2026). В выгрузке это обычно число вроде '2026.0'.
    Мы ищем 4-значное число в строке шапки и берем первое подходящее.
    """
    for v in header_row:
        s = str(v).strip()
        if s.endswith(".0"):
            s = s[:-2]
        if s.isdigit() and len(s) == 4:
            try:
                year = int(s)
                if 2000 <= year <= 2100:
                    return year
            except ValueError:
                continue
    return None


def _month_year(s: str) -> int | None:
    if not _looks_like_month(s):
        return None
    try:
        return int(s[:4])
    except ValueError:
        return None


def _active_month_cols(parsed: ParsedHeader, header: List[str]) -> List[int]:
    """
    Если нашли active_year — проверяем только месяцы этого года (обычно Z и дальше).
    Иначе проверяем все распознанные месяцы.
    """
    if parsed.active_year is None:
        return parsed.month_cols
    out: List[int] = []
    for c in parsed.month_cols:
        if _month_year(header[c]) == parsed.active_year:
            out.append(c)
    return out


def _to_float(cell: str) -> Tuple[bool, float]:
    """
    Parse numeric cell. Accept empty as 0? No — empty is "not set".
    Returns (ok, value).
    """
    if cell == "":
        return True, 0.0
    try:
        return True, float(cell.replace(",", "."))
    except Exception:
        return False, 0.0


def _is_empty(cell: str) -> bool:
    return str(cell).strip() == ""


def _is_multiple_of_half(x: float) -> bool:
    # accept integer or .5 steps (tolerant to floating point)
    return isclose(x * 2.0, round(x * 2.0), abs_tol=1e-9)


def _format_month_label(iso_date: str) -> str:
    """
    Converts 'YYYY-MM-DD' -> 'MM.YY' (e.g. 2026-01-01 -> 01.26)
    """
    try:
        d = dt.datetime.strptime(iso_date, "%Y-%m-%d").date()
        return f"{d.month:02d}.{d.year % 100:02d}"
    except Exception:
        return iso_date


def _month_start(d: dt.date) -> dt.date:
    return dt.date(d.year, d.month, 1)


def _add_months(d: dt.date, months: int) -> dt.date:
    # month arithmetic on first-of-month dates
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return dt.date(y, m, 1)


def _parse_month_header(iso_date: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(iso_date, "%Y-%m-%d").date()
    except Exception:
        return None


def _forward_month_cols(
    *,
    parsed: ParsedHeader,
    header: List[str],
    today: dt.date,
    months_ahead: int,
) -> List[int]:
    """
    Returns month columns for [current_month_start .. current_month_start + months_ahead-1]
    intersected with active-year month columns.
    """
    active = _active_month_cols(parsed, header)
    cur = _month_start(today)
    targets = {_add_months(cur, i) for i in range(months_ahead)}
    out: List[int] = []
    for c in active:
        md = _parse_month_header(header[c])
        if md in targets:
            out.append(c)
    return out


def _is_true(cell: str) -> bool:
    return str(cell).strip().lower() in {"true", "1", "yes", "y", "да"}


class WorkdaysRowNumericCheck(Check):
    """
    Проверяет, что в сервисной строке (строка над шапкой) для каждого месяца
    указано число рабочих дней (а не #REF!).
    """

    code = "WORKDAYS_ROW_NUMERIC"

    def run(self, data: SheetValues) -> CheckResult:
        parsed = _find_header(data)
        if parsed is None:
            return CheckResult(issues=[])

        if parsed.header_row_idx == 0:
            return CheckResult(
                issues=[
                    Issue(
                        severity=Severity.yellow,
                        code=self.code,
                        message="Не вижу сервисную строку над шапкой (рабочие дни в месяце).",
                        suggestion="Если в выгрузке есть строка 1 с рабочими днями — включим ее в парсинг.",
                    )
                ]
            )

        workdays_row = data.values[parsed.header_row_idx - 1]
        header = data.values[parsed.header_row_idx]
        month_cols = _active_month_cols(parsed, header)

        issues: List[Issue] = []
        for c_idx in month_cols:
            month = header[c_idx]
            cell = workdays_row[c_idx] if c_idx < len(workdays_row) else ""
            ok, num = _to_float(cell)
            if not ok:
                issues.append(
                    Issue(
                        severity=Severity.red,
                        code=self.code,
                        message=f"В строке рабочих дней месяц {month}: не число ('{cell}').",
                        location=IssueLocation(week=month, cell=f"R{parsed.header_row_idx}C{c_idx+1}"),
                        suggestion="Починить формулу/значение рабочих дней (должно быть число, например 19).",
                    )
                )
            elif cell != "" and num <= 0:
                issues.append(
                    Issue(
                        severity=Severity.red,
                        code=self.code,
                        message=f"В строке рабочих дней месяц {month}: значение <= 0 ({num}).",
                        location=IssueLocation(week=month, cell=f"R{parsed.header_row_idx}C{c_idx+1}"),
                        suggestion="Проверь календарь: рабочих дней обычно > 0.",
                    )
                )
        return CheckResult(issues=issues)


class AllocationNotExceedWorkdaysCheck(Check):
    """
    Если в ячейке месяца стоит число дней, оно не должно превышать рабочих дней в этом месяце (из строки 1).
    """

    code = "ALLOCATION_EXCEEDS_WORKDAYS"

    def run(self, data: SheetValues) -> CheckResult:
        parsed = _find_header(data)
        if parsed is None or parsed.header_row_idx == 0:
            return CheckResult(issues=[])

        workdays_row = data.values[parsed.header_row_idx - 1]
        header = data.values[parsed.header_row_idx]
        month_cols = _active_month_cols(parsed, header)

        # pre-parse workdays
        workdays: dict[int, float] = {}
        for c_idx in month_cols:
            cell = workdays_row[c_idx] if c_idx < len(workdays_row) else ""
            ok, num = _to_float(cell)
            if ok and cell != "":
                workdays[c_idx] = num

        issues: List[Issue] = []
        for r_idx in range(parsed.header_row_idx + 1, len(data.values)):
            row = data.values[r_idx]
            for c_idx in month_cols:
                month = header[c_idx]
                cell = row[c_idx] if c_idx < len(row) else ""
                ok, num = _to_float(cell)
                if not ok or cell == "":
                    continue
                wd = workdays.get(c_idx)
                if wd is None:
                    # workdays missing/invalid handled by WorkdaysRowNumericCheck
                    continue
                if num > wd:
                    issues.append(
                        Issue(
                            severity=Severity.red,
                            code=self.code,
                            message=f"Превышение рабочих дней: {num} > {wd} в месяце {month}.",
                            location=IssueLocation(week=month, cell=f"R{r_idx+1}C{c_idx+1}"),
                            suggestion=f"Уменьши до {wd} или меньше (рабочие дни месяца).",
                        )
                    )
        return CheckResult(issues=issues)


class PmRequiredWhenHasDaysCheck(Check):
    """
    Пустой PM (колонка I) при наличии запланированных дней (>0) — ошибка.
    """

    code = "PM_MISSING"

    def run(self, data: SheetValues) -> CheckResult:
        parsed = _find_header(data)
        if parsed is None:
            return CheckResult(issues=[])

        header = data.values[parsed.header_row_idx]
        month_cols = _active_month_cols(parsed, header)
        pm_col = 8  # I
        employee_col = 9  # J

        issues: List[Issue] = []
        for r_idx in range(parsed.header_row_idx + 1, len(data.values)):
            row = data.values[r_idx]
            pm = row[pm_col].strip() if pm_col < len(row) else ""
            employee = row[employee_col].strip() if employee_col < len(row) else ""

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
                issues.append(
                    Issue(
                        severity=Severity.red,
                        code=self.code,
                        message="Пустой PM при наличии запланированных дней.",
                        location=IssueLocation(person=employee or None, cell=f"R{r_idx+1}C{pm_col+1}"),
                        suggestion="Заполни ФИО PM (колонка I) — кто отвечает за заполнение строки.",
                    )
                )

        return CheckResult(issues=issues)


class EmployeeRequiredWhenHasDaysCheck(Check):
    """
    Пустое ФИО сотрудника (колонка J) при наличии дней (>0) — ошибка.
    """

    code = "EMPLOYEE_MISSING"

    def run(self, data: SheetValues) -> CheckResult:
        parsed = _find_header(data)
        if parsed is None:
            return CheckResult(issues=[])

        header = data.values[parsed.header_row_idx]
        month_cols = _active_month_cols(parsed, header)
        pm_col = 8
        employee_col = 9

        issues: List[Issue] = []
        for r_idx in range(parsed.header_row_idx + 1, len(data.values)):
            row = data.values[r_idx]
            pm = row[pm_col].strip() if pm_col < len(row) else ""
            employee = row[employee_col].strip() if employee_col < len(row) else ""

            has_days = False
            for c in month_cols:
                cell = row[c] if c < len(row) else ""
                ok, num = _to_float(cell)
                if ok and cell != "" and num > 0:
                    has_days = True
                    break
            if not has_days:
                continue

            if employee == "":
                issues.append(
                    Issue(
                        severity=Severity.red,
                        code=self.code,
                        message="Пустое ФИО сотрудника (колонка J) при наличии запланированных дней.",
                        location=IssueLocation(pm=pm or None, cell=f"R{r_idx+1}C{employee_col+1}"),
                        suggestion="Заполни ФИО сотрудника (колонка J) — по кому планируются трудозатраты.",
                    )
                )

        return CheckResult(issues=issues)


class EmployeeMonthSumNotExceedWorkdaysCheck(Check):
    """
    Сумма по ФИО сотрудника в месяце НЕ должна превышать количество рабочих дней в месяце.
    Это проверка на перегруз (овербукинг).

    Важно: если сотрудник "не в проекте" не отражается в документе, то сумма может быть меньше рабочих дней —
    это допустимо, и мы не считаем это ошибкой.
    (MVP: применяем на горизонте ближайших N месяцев)
    """

    code = "EMPLOYEE_MONTH_SUM_EXCEEDS_WORKDAYS"

    def __init__(self, *, months_ahead: int = 2, today: dt.date | None = None) -> None:
        self._months_ahead = months_ahead
        self._today = today

    def run(self, data: SheetValues) -> CheckResult:
        parsed = _find_header(data)
        if parsed is None or parsed.header_row_idx == 0:
            return CheckResult(issues=[])

        header = data.values[parsed.header_row_idx]
        today = self._today or dt.date.today()
        month_cols = _forward_month_cols(parsed=parsed, header=header, today=today, months_ahead=self._months_ahead)
        if not month_cols:
            return CheckResult(issues=[])

        workdays_row = data.values[parsed.header_row_idx - 1]
        workdays: dict[int, float] = {}
        for c in month_cols:
            cell = workdays_row[c] if c < len(workdays_row) else ""
            ok, num = _to_float(cell)
            if ok and cell != "":
                workdays[c] = num

        employee_col = 9
        pm_col = 8

        # aggregate
        sums: dict[str, dict[int, float]] = {}
        pms: dict[str, str] = {}

        for r_idx in range(parsed.header_row_idx + 1, len(data.values)):
            row = data.values[r_idx]
            employee = row[employee_col].strip() if employee_col < len(row) else ""
            pm = row[pm_col].strip() if pm_col < len(row) else ""
            if employee == "":
                continue
            if employee not in sums:
                sums[employee] = {c: 0.0 for c in month_cols}
            if pm and employee not in pms:
                pms[employee] = pm
            for c in month_cols:
                cell = row[c] if c < len(row) else ""
                ok, num = _to_float(cell)
                if ok and cell != "":
                    sums[employee][c] += num

        issues: List[Issue] = []
        for employee, by_month in sums.items():
            for c, total in by_month.items():
                wd = workdays.get(c)
                if wd is None:
                    continue
                if total - wd > 1e-6:
                    month = header[c]
                    issues.append(
                        Issue(
                            severity=Severity.red,
                            code=self.code,
                            message=f"Перегруз по сотруднику за месяц { _format_month_label(month) }: {total} > {wd} (рабочие дни).",
                            location=IssueLocation(person=employee, pm=pms.get(employee) or None, week=month),
                            suggestion="Уменьши план в этом месяце: сумма по всем строкам сотрудника не должна превышать рабочие дни.",
                        )
                    )

        return CheckResult(issues=issues)


class MonthCellsRequiredCheck(Check):
    """
    Пустая ячейка месяца считается ошибкой: нужно ставить число (обычно 0),
    чтобы было понятно, что план проверен и намеренно пустой.
    """

    code = "MONTH_CELL_EMPTY"

    def __init__(self, *, months_ahead: int = 2, today: dt.date | None = None) -> None:
        self._months_ahead = months_ahead
        self._today = today

    def run(self, data: SheetValues) -> CheckResult:
        parsed = _find_header(data)
        if parsed is None:
            return CheckResult(issues=[])

        header = data.values[parsed.header_row_idx]
        today = self._today or dt.date.today()
        month_cols = _forward_month_cols(parsed=parsed, header=header, today=today, months_ahead=self._months_ahead)
        if not month_cols:
            return CheckResult(issues=[])

        active_year_month_cols = _active_month_cols(parsed, header)

        # Column mapping by твоему контракту:
        # I (PM) -> index 8, J (employee) -> index 9, K (in?) -> index 10
        pm_col = 8
        employee_col = 9
        in_col = 10

        issues: List[Issue] = []
        for r_idx in range(parsed.header_row_idx + 1, len(data.values)):
            row = data.values[r_idx]

            employee = row[employee_col].strip() if employee_col < len(row) else ""
            if employee == "":
                # skip empty rows / service blocks
                continue

            in_val = row[in_col] if in_col < len(row) else ""
            is_in = _is_true(in_val)

            # Apply rule to:
            # - "active" rows (in? = True), OR
            # - rows that have any plan anywhere in the active year (so even if the work starts later,
            #   current+next months must be explicitly set, usually to 0).
            has_any_plan_in_year = any(
                (not _is_empty(row[c])) if c < len(row) else False for c in active_year_month_cols
            )
            if not (is_in or has_any_plan_in_year):
                continue

            pm = row[pm_col].strip() if pm_col < len(row) else ""

            missing_months: List[str] = []
            first_missing_cell: str | None = None
            for c_idx in month_cols:
                month = header[c_idx]
                cell = row[c_idx] if c_idx < len(row) else ""
                if _is_empty(cell):
                    missing_months.append(_format_month_label(month))
                    if first_missing_cell is None:
                        first_missing_cell = f"R{r_idx+1}C{c_idx+1}"

            if missing_months:
                preview = ", ".join(missing_months[:6])
                more = "" if len(missing_months) <= 6 else f" + ещё {len(missing_months) - 6}"
                issues.append(
                    Issue(
                        severity=Severity.red,
                        code=self.code,
                        message=f"План не заполнен на {self._months_ahead} мес. вперед: пусто в {preview}{more} (всего {len(missing_months)}).",
                        location=IssueLocation(
                            person=employee or None,
                            pm=pm or None,
                            cell=first_missing_cell,
                        ),
                        suggestion="Заполни числами (в т.ч. 0) как минимум на ближайшие 2 месяца.",
                    )
                )

        return CheckResult(issues=issues)


class MonthCellsHalfStepCheck(Check):
    """
    Значения в месячных ячейках должны быть кратны 0.5 (например 0.5, 1.5, 10.5).
    9.66 / 13.73 и т.п. считаются некорректными.
    """

    code = "MONTH_CELL_NOT_HALF_STEP"

    def run(self, data: SheetValues) -> CheckResult:
        parsed = _find_header(data)
        if parsed is None:
            return CheckResult(issues=[])

        header = data.values[parsed.header_row_idx]
        month_cols = _active_month_cols(parsed, header)

        issues: List[Issue] = []
        for r_idx in range(parsed.header_row_idx + 1, len(data.values)):
            row = data.values[r_idx]
            for c_idx in month_cols:
                month = header[c_idx]
                cell = row[c_idx] if c_idx < len(row) else ""
                if _is_empty(cell):
                    continue
                ok, num = _to_float(cell)
                if not ok:
                    # numeric problems handled by MonthCellsNumericAndNonNegativeCheck
                    continue
                if not _is_multiple_of_half(num):
                    issues.append(
                        Issue(
                            severity=Severity.red,
                            code=self.code,
                            message=f"Значение {num} в месяце {month} не кратно 0.5.",
                            location=IssueLocation(week=month, cell=f"R{r_idx+1}C{c_idx+1}"),
                            suggestion="Округли до ближайшего значения с шагом 0.5 (например 9.5 или 10.0).",
                        )
                    )
        return CheckResult(issues=issues)


class RoleCodeValidCheck(Check):
    """
    Проверяет, что роль в колонке A одна из: A, D, PM, BI.
    """

    code = "ROLE_CODE_INVALID"

    def run(self, data: SheetValues) -> CheckResult:
        parsed = _find_header(data)
        if parsed is None:
            return CheckResult(issues=[])

        header = data.values[parsed.header_row_idx]
        role_col = 0
        issues: List[Issue] = []
        allowed = {"A", "D", "PM", "BI"}

        for r_idx in range(parsed.header_row_idx + 1, len(data.values)):
            row = data.values[r_idx]
            role = (row[role_col] if role_col < len(row) else "").strip().upper()
            if role == "":
                continue
            if role not in allowed:
                issues.append(
                    Issue(
                        severity=Severity.red,
                        code=self.code,
                        message=f"Неизвестная роль '{role}' (ожидалось A/D/PM/BI).",
                        location=IssueLocation(cell=f"R{r_idx+1}C{role_col+1}"),
                        suggestion="Исправь код роли или обнови список допустимых ролей.",
                    )
                )
        return CheckResult(issues=issues)


class InFlagConsistencyCheck(Check):
    """
    Если 'in?' = False, но стоят дни в месяцах — это подозрительно (warning).
    """

    code = "IN_FLAG_INCONSISTENT"

    def run(self, data: SheetValues) -> CheckResult:
        parsed = _find_header(data)
        if parsed is None:
            return CheckResult(issues=[])

        header = data.values[parsed.header_row_idx]
        month_cols = _active_month_cols(parsed, header)
        in_col = 10  # column K (1-based), 0-based index 10
        pm_col = 8
        employee_col = 9

        issues: List[Issue] = []
        for r_idx in range(parsed.header_row_idx + 1, len(data.values)):
            row = data.values[r_idx]

            in_val = row[in_col] if in_col < len(row) else ""
            has_days = False
            for c_idx in month_cols:
                cell = row[c_idx] if c_idx < len(row) else ""
                ok, num = _to_float(cell)
                if ok and cell != "" and num > 0:
                    has_days = True
                    break

            if has_days and not _is_true(in_val):
                pm = row[pm_col].strip() if pm_col < len(row) else ""
                employee = row[employee_col].strip() if employee_col < len(row) else ""
                issues.append(
                    Issue(
                        severity=Severity.yellow,
                        code=self.code,
                        message="Есть дни в месяцах, но 'in?' = False.",
                        location=IssueLocation(
                            person=employee or None,
                            pm=pm or None,
                            cell=f"R{r_idx+1}C{in_col+1}",
                        ),
                        suggestion="Либо включи 'in?', либо обнули дни (если строка неактуальна).",
                    )
                )

        return CheckResult(issues=issues)


class HeaderHasMonthsCheck(Check):
    code = "HEADER_HAS_MONTHS"

    def run(self, data: SheetValues) -> CheckResult:
        parsed = _find_header(data)
        if parsed is None:
            return CheckResult(
                issues=[
                    Issue(
                        severity=Severity.red,
                        code=self.code,
                        message="Не смог распознать колонки месяцев (ожидались даты формата YYYY-MM-DD в шапке).",
                        suggestion="Проверь, что выгрузка содержит даты месяцев в шапке, или мы настроим парсер под твой формат.",
                    )
                ]
            )
        if len(parsed.month_cols) < 3:
            return CheckResult(
                issues=[
                    Issue(
                        severity=Severity.yellow,
                        code=self.code,
                        message=f"Распознано мало колонок месяцев: {len(parsed.month_cols)}.",
                        suggestion="Если это не ошибка, ок. Иначе уточним диапазон/лист в выгрузке.",
                    )
                ]
            )
        return CheckResult(issues=[])


class MonthCellsNumericAndNonNegativeCheck(Check):
    code = "MONTH_CELLS_NUMERIC"

    def run(self, data: SheetValues) -> CheckResult:
        parsed = _find_header(data)
        if parsed is None:
            return CheckResult(issues=[])

        issues: List[Issue] = []
        header = data.values[parsed.header_row_idx]
        month_cols = _active_month_cols(parsed, header)
        # data rows start after header
        for r_idx in range(parsed.header_row_idx + 1, len(data.values)):
            row = data.values[r_idx]
            for c_idx in month_cols:
                month = header[c_idx]
                cell = row[c_idx] if c_idx < len(row) else ""
                ok, num = _to_float(cell)
                if not ok:
                    issues.append(
                        Issue(
                            severity=Severity.red,
                            code=self.code,
                            message=f"Не число в колонке месяца {month}: '{cell}'",
                            location=IssueLocation(week=month, cell=f"R{r_idx+1}C{c_idx+1}"),
                            suggestion="Заменить на число (например 0, 10.5) или оставить пустым.",
                        )
                    )
                elif cell != "" and num < 0:
                    issues.append(
                        Issue(
                            severity=Severity.red,
                            code="MONTH_CELLS_NONNEGATIVE",
                            message=f"Отрицательное значение в месяце {month}: {num}",
                            location=IssueLocation(week=month, cell=f"R{r_idx+1}C{c_idx+1}"),
                            suggestion="Отрицательные часы обычно ошибка. Проверь и исправь.",
                        )
                    )
        return CheckResult(issues=issues)


class IfHasHoursThenKeyFieldsFilledCheck(Check):
    """
    Универсальная проверка: если в строке есть ненулевые часы в любом месяце,
    то первые несколько мета-полей должны быть заполнены.

    Мы не привязываемся к русским названиям колонок (они зависят от кодировки/шапки),
    поэтому используем позиции.
    """

    code = "KEY_FIELDS_FILLED"

    def __init__(self, required_meta_cols: List[int] | None = None) -> None:
        # Default: require A,B,C,D,F,G,H,I,J (skip E, and skip K,L as requested)
        # PM (I) и Employee (J) проверяются отдельными red-checks.
        self._required_meta_cols = required_meta_cols or [0, 1, 2, 3, 5, 6, 7]

    def run(self, data: SheetValues) -> CheckResult:
        parsed = _find_header(data)
        if parsed is None:
            return CheckResult(issues=[])

        issues: List[Issue] = []
        header = data.values[parsed.header_row_idx]
        month_cols = _active_month_cols(parsed, header)
        pm_col = 8
        employee_col = 9
        for r_idx in range(parsed.header_row_idx + 1, len(data.values)):
            row = data.values[r_idx]

            # detect if row has any hours > 0
            has_hours = False
            for c_idx in month_cols:
                cell = row[c_idx] if c_idx < len(row) else ""
                ok, num = _to_float(cell)
                if ok and cell != "" and num > 0:
                    has_hours = True
                    break

            if not has_hours:
                continue

            pm = row[pm_col].strip() if pm_col < len(row) else ""
            employee = row[employee_col].strip() if employee_col < len(row) else ""

            for c_idx in self._required_meta_cols:
                col_name = header[c_idx] if c_idx < len(header) else f"C{c_idx+1}"
                v = row[c_idx] if c_idx < len(row) else ""
                if str(v).strip() == "":
                    issues.append(
                        Issue(
                            severity=Severity.yellow,
                            code=self.code,
                            message=f"Строка с часами, но поле '{col_name}' не заполнено.",
                            location=IssueLocation(
                                person=employee or None,
                                pm=pm or None,
                                cell=f"R{r_idx+1}C{c_idx+1}",
                            ),
                            suggestion="Заполни ключевые поля строки (сотрудник/проект/тип).",
                        )
                    )

        return CheckResult(issues=issues)

