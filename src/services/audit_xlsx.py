from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..checks.base import run_checks
from ..checks.resource_plan_xlsx import (
    AllocationNotExceedWorkdaysCheck,
    EmployeeMonthSumNotExceedWorkdaysCheck,
    EmployeeRequiredWhenHasDaysCheck,
    HeaderHasMonthsCheck,
    IfHasHoursThenKeyFieldsFilledCheck,
    InFlagConsistencyCheck,
    MonthCellsHalfStepCheck,
    MonthCellsNumericAndNonNegativeCheck,
    MonthCellsRequiredCheck,
    PmRequiredWhenHasDaysCheck,
    RoleCodeValidCheck,
    WorkdaysRowNumericCheck,
)
from ..config import Settings
from ..local.xlsx_reader import XlsxParseHints, read_xlsx_as_sheet_values
from ..models import Issue


@dataclass(frozen=True)
class XlsxAuditReport:
    issues: List[Issue]

    def is_ok(self) -> bool:
        return len(self.issues) == 0


def resolve_xlsx_path(path: str) -> Path:
    p = Path(path)
    if path.lower() == "auto" or not p.exists():
        candidates = sorted(Path(".").glob("*.xlsx"))
        if not candidates:
            raise FileNotFoundError(f"XLSX not found: {path}")
        return candidates[0]
    return p


def run_xlsx_audit(
    *,
    settings: Settings,
    path: str,
    sheet: Optional[str] = None,
    header_row: int | None = None,
    max_cols: int | None = None,
) -> XlsxAuditReport:
    xlsx_path = resolve_xlsx_path(path)

    data = read_xlsx_as_sheet_values(
        path=xlsx_path,
        sheet_name=sheet or None,
        hints=None
        if header_row is None and max_cols is None
        else XlsxParseHints(
            header_row=header_row,
            max_cols=max_cols,
        ),
    )

    issues = run_checks(
        checks=[
            HeaderHasMonthsCheck(),
            WorkdaysRowNumericCheck(),
            MonthCellsNumericAndNonNegativeCheck(),
            MonthCellsHalfStepCheck(),
            AllocationNotExceedWorkdaysCheck(),
            RoleCodeValidCheck(),
            InFlagConsistencyCheck(),
            IfHasHoursThenKeyFieldsFilledCheck(),
            PmRequiredWhenHasDaysCheck(),
            EmployeeRequiredWhenHasDaysCheck(),
            MonthCellsRequiredCheck(),
            EmployeeMonthSumNotExceedWorkdaysCheck(),
        ],
        data=data,
    )

    return XlsxAuditReport(issues=issues)

