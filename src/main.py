from __future__ import annotations

import argparse
import sys
from typing import Iterable

from .config import get_settings
from .models import Issue, Severity
from .notifications.telegram import TelegramNotifier
from .services.audit import AuditService
from .local.xlsx_reader import XlsxParseHints, read_xlsx_as_sheet_values
from .services.audit_xlsx import run_xlsx_audit


def _configure_stdout() -> None:
    # Helps Windows terminals render Cyrillic correctly when UTF-8 is supported.
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def format_issues_text(issues: Iterable[Issue], *, limit: int = 60, full: bool = False) -> str:
    lines: list[str] = []
    issues = list(issues)

    if not issues:
        return "✅ Ошибок не найдено."

    red = [i for i in issues if i.severity == Severity.red]
    yellow = [i for i in issues if i.severity == Severity.yellow]
    info = [i for i in issues if i.severity == Severity.info]

    lines.append(f"Найдено проблем: {len(issues)} (red={len(red)}, yellow={len(yellow)}, info={len(info)})")
    lines.append("")

    # quick counts by code
    by_code: dict[str, int] = {}
    for i in issues:
        by_code[i.code] = by_code.get(i.code, 0) + 1
    top_codes = sorted(by_code.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    lines.append("Топ проблем по типу:")
    for code, cnt in top_codes:
        lines.append(f"- {code}: {cnt}")

    # high-signal breakdown for MONTH_CELL_EMPTY
    if by_code.get("MONTH_CELL_EMPTY"):
        by_pm: dict[str, int] = {}
        for i in issues:
            if i.code != "MONTH_CELL_EMPTY":
                continue
            pm = i.location.pm or "PM не указан"
            by_pm[pm] = by_pm.get(pm, 0) + 1
        lines.append("")
        lines.append("Пустые месяцы (MONTH_CELL_EMPTY) по PM:")
        for pm, cnt in sorted(by_pm.items(), key=lambda kv: (-kv[1], kv[0]))[:10]:
            lines.append(f"- {pm}: {cnt}")

    lines.append("")

    # Avoid spamming: in non-full mode, show all non-empty-month issues and only a slice of empty-month issues.
    if full:
        display = issues
    else:
        non_empty = [i for i in issues if i.code != "MONTH_CELL_EMPTY"]
        empty = [i for i in issues if i.code == "MONTH_CELL_EMPTY"]
        remaining = max(0, limit - len(non_empty))
        display = non_empty + empty[:remaining]

    shown = 0
    for i in display:
        if not full and shown >= limit:
            break
        shown += 1
        loc = []
        if i.location.person:
            loc.append(f"person={i.location.person}")
        if getattr(i.location, "pm", None):
            if i.location.pm:
                loc.append(f"pm={i.location.pm}")
        if i.location.week:
            loc.append(f"week={i.location.week}")
        if i.location.cell:
            loc.append(f"cell={i.location.cell}")
        loc_text = f" [{' '.join(loc)}]" if loc else ""

        lines.append(f"- [{i.severity}] {i.code}{loc_text}: {i.message}")
        if i.suggestion:
            lines.append(f"  suggestion: {i.suggestion}")

    if not full and len(issues) > shown:
        lines.append("")
        lines.append(f"… и ещё {len(issues) - shown} проблем(ы).")
        lines.append("Подсказка: увеличь --limit или используй --full (может быть очень длинно).")

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
    report = run_xlsx_audit(
        settings=get_settings(),
        path=args.path,
        sheet=args.sheet,
        header_row=args.header_row,
        max_cols=args.max_cols,
    )

    text = format_issues_text(report.issues, limit=args.limit, full=args.full)
    print(text)
    return 0 if report.is_ok() else 2


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
    audit_xlsx.add_argument("--limit", required=False, type=int, default=60, help="How many issues to print")
    audit_xlsx.add_argument("--full", action="store_true", help="Print all issues (can be very long)")
    audit_xlsx.set_defaults(func=cmd_audit_xlsx)

    return p


def main() -> int:
    _configure_stdout()
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

