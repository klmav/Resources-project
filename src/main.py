from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from .config import get_settings
from .models import Issue, Severity
from .notifications.telegram import TelegramNotifier
from .services.audit import AuditService
from .local.xlsx_reader import XlsxParseHints, read_xlsx_as_sheet_values
from .checks.base import run_checks
from .checks.resource_plan_xlsx import (
    HeaderHasMonthsCheck,
    WorkdaysRowNumericCheck,
    AllocationNotExceedWorkdaysCheck,
    RoleCodeValidCheck,
    InFlagConsistencyCheck,
    IfHasHoursThenKeyFieldsFilledCheck,
    MonthCellsNumericAndNonNegativeCheck,
)


def _configure_stdout() -> None:
    # Helps Windows terminals render Cyrillic correctly when UTF-8 is supported.
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def format_issues_text(issues: Iterable[Issue]) -> str:
    lines: list[str] = []
    issues = list(issues)

    if not issues:
        return "✅ Ошибок не найдено."

    red = [i for i in issues if i.severity == Severity.red]
    yellow = [i for i in issues if i.severity == Severity.yellow]
    info = [i for i in issues if i.severity == Severity.info]

    lines.append(f"Найдено проблем: {len(issues)} (red={len(red)}, yellow={len(yellow)}, info={len(info)})")
    lines.append("")

    for i in issues:
        loc = []
        if i.location.person:
            loc.append(f"person={i.location.person}")
        if i.location.week:
            loc.append(f"week={i.location.week}")
        if i.location.cell:
            loc.append(f"cell={i.location.cell}")
        loc_text = f" [{' '.join(loc)}]" if loc else ""

        lines.append(f"- [{i.severity}] {i.code}{loc_text}: {i.message}")
        if i.suggestion:
            lines.append(f"  suggestion: {i.suggestion}")

    return "\n".join(lines)


def cmd_audit(_: argparse.Namespace) -> int:
    settings = get_settings()
    report = AuditService(settings=settings).run()

    text = format_issues_text(report.issues)
    print(text)

    TelegramNotifier(settings=settings).send_text(text=text)
    return 0 if report.is_ok() else 2


def cmd_bot(_: argparse.Namespace) -> int:
    settings = get_settings()
    from .bot.app import run_bot

    run_bot(settings=settings)
    return 0


def cmd_audit_xlsx(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        # Convenience for Windows console encoding issues: allow "--path auto"
        # or any non-existing path and fallback to first .xlsx in cwd.
        candidates = sorted(Path(".").glob("*.xlsx"))
        if not candidates:
            raise FileNotFoundError(f"XLSX not found: {args.path}")
        path = candidates[0]

    data = read_xlsx_as_sheet_values(
        path=path,
        sheet_name=args.sheet,
        hints=None
        if args.header_row is None and args.max_cols is None
        else XlsxParseHints(
            header_row=args.header_row,
            max_cols=args.max_cols,
        ),
    )

    issues = run_checks(
        checks=[
            HeaderHasMonthsCheck(),
            WorkdaysRowNumericCheck(),
            MonthCellsNumericAndNonNegativeCheck(),
            AllocationNotExceedWorkdaysCheck(),
            RoleCodeValidCheck(),
            InFlagConsistencyCheck(),
            IfHasHoursThenKeyFieldsFilledCheck(),
        ],
        data=data,
    )

    text = format_issues_text(issues)
    print(text)
    return 0 if not issues else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="resource-plan-auditor")
    sub = p.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="run audit checks and print/send report")
    audit.set_defaults(func=cmd_audit)

    bot = sub.add_parser("bot", help="run Telegram bot (polling)")
    bot.set_defaults(func=cmd_bot)

    audit_xlsx = sub.add_parser("audit-xlsx", help="run checks against local XLSX export")
    audit_xlsx.add_argument("--path", required=True, help="Path to .xlsx file")
    audit_xlsx.add_argument("--sheet", required=False, help="Sheet name (default: first sheet)")
    audit_xlsx.add_argument("--header-row", required=False, type=int, help="Header row (1-based) override")
    audit_xlsx.add_argument("--max-cols", required=False, type=int, help="Max columns to read override")
    audit_xlsx.set_defaults(func=cmd_audit_xlsx)

    return p


def main() -> int:
    _configure_stdout()
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

