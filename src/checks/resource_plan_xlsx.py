from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

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
                issues.append(
                    Issue(
                        severity=Severity.yellow,
                        code=self.code,
                        message="Есть дни в месяцах, но 'in?' = False.",
                        location=IssueLocation(cell=f"R{r_idx+1}C{in_col+1}"),
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
        self._required_meta_cols = required_meta_cols or [0, 1, 2, 3, 5, 6, 7, 8, 9]

    def run(self, data: SheetValues) -> CheckResult:
        parsed = _find_header(data)
        if parsed is None:
            return CheckResult(issues=[])

        issues: List[Issue] = []
        header = data.values[parsed.header_row_idx]
        month_cols = _active_month_cols(parsed, header)
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

            for c_idx in self._required_meta_cols:
                col_name = header[c_idx] if c_idx < len(header) else f"C{c_idx+1}"
                v = row[c_idx] if c_idx < len(row) else ""
                if str(v).strip() == "":
                    issues.append(
                        Issue(
                            severity=Severity.yellow,
                            code=self.code,
                            message=f"Строка с часами, но поле '{col_name}' не заполнено.",
                            location=IssueLocation(cell=f"R{r_idx+1}C{c_idx+1}"),
                            suggestion="Заполни ключевые поля строки (сотрудник/проект/тип).",
                        )
                    )

        return CheckResult(issues=issues)

