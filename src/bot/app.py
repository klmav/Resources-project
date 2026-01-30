from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Iterable, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ..config import Settings
from ..llm.gpt5_client import Gpt5Client, Gpt5Config
from ..llm.prompts import SYSTEM_PROMPT, build_chat_prompt, build_summary_prompt
from ..main import format_issues_text
from ..models import Issue
from ..services.audit_xlsx import run_xlsx_audit
from ..fixes.month_empty_to_zero import plan_fill_empty_months_with_zero
from ..fixes.xlsx_apply import apply_fix_plan_to_xlsx_copy
from ..local.xlsx_reader import read_xlsx_as_sheet_values


def build_application(settings: Settings) -> Application:
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required to run bot")

    app = Application.builder().token(settings.telegram_bot_token).build()

    def _message_from_update(update: Update) -> Optional[Message]:
        if update.message is not None:
            return update.message
        if update.callback_query and update.callback_query.message:
            return update.callback_query.message
        return None

    async def _send_long(
        update: Update,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        """
        Telegram message limit is ~4096 chars. Chunk conservatively.
        Works for both command updates and callback queries.
        """
        msg = _message_from_update(update)
        if msg is None:
            return

        chunk_size = 3500
        parts = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)] or [text]
        for idx, part in enumerate(parts):
            await msg.reply_text(part, reply_markup=reply_markup if idx == 0 else None)

    def _build_llm_context(issues: Iterable[Issue]) -> dict[str, Any]:
        issues = list(issues)
        by_code: dict[str, int] = {}
        by_pm: dict[str, int] = {}

        for it in issues:
            by_code[it.code] = by_code.get(it.code, 0) + 1
            if it.code == "MONTH_CELL_EMPTY":
                pm = it.location.pm or "PM не указан"
                by_pm[pm] = by_pm.get(pm, 0) + 1

        sample: List[dict[str, Any]] = []
        for it in issues[:80]:
            sample.append(
                {
                    "severity": str(it.severity),
                    "code": it.code,
                    "message": it.message,
                    "person": it.location.person,
                    "pm": it.location.pm,
                    "week": it.location.week,
                    "cell": it.location.cell,
                    "suggestion": it.suggestion,
                }
            )

        return {
            "source": "local_xlsx",
            "policy": {
                "active_year_only": True,
                "empty_month_cell_is_error": True,
                "month_value_step": 0.5,
            },
            "counts": {
                "total": len(issues),
                "by_code": dict(sorted(by_code.items(), key=lambda kv: (-kv[1], kv[0]))),
                "empty_by_pm_top": dict(sorted(by_pm.items(), key=lambda kv: (-kv[1], kv[0]))[:15]),
            },
            "sample_issues": sample,
        }

    def _extract_pm_list(issues: Iterable[Issue]) -> List[str]:
        pms: set[str] = set()
        for it in issues:
            if it.location.pm:
                pms.add(it.location.pm)
        return sorted(pms)

    def _filter_issues_by_pm(issues: List[Issue], pm_query: str) -> List[Issue]:
        q = pm_query.strip().lower()
        if not q:
            return issues
        out: List[Issue] = []
        for it in issues:
            pm = (it.location.pm or "").strip().lower()
            if pm and (q in pm):
                out.append(it)
        return out

    def _pm_storage_key(chat_id: int) -> str:
        return f"pm_list:{chat_id}"

    def _audit_ctx_key(chat_id: int) -> str:
        return f"audit_ctx:{chat_id}"

    def _issues_key(chat_id: int) -> str:
        return f"issues:{chat_id}"

    def _fixplan_key(chat_id: int) -> str:
        return f"fixplan:{chat_id}"

    def _store_pm_list_for_chat(
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        pms: List[str],
    ) -> None:
        context.application.bot_data[_pm_storage_key(chat_id)] = pms

    def _get_pm_list_for_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> List[str]:
        val = context.application.bot_data.get(_pm_storage_key(chat_id))
        return val if isinstance(val, list) else []

    def _store_audit_context(
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        audit_ctx: dict[str, Any],
    ) -> None:
        context.application.bot_data[_audit_ctx_key(chat_id)] = audit_ctx

    def _get_audit_context(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> Optional[dict[str, Any]]:
        val = context.application.bot_data.get(_audit_ctx_key(chat_id))
        return val if isinstance(val, dict) else None

    def _store_issues(context: ContextTypes.DEFAULT_TYPE, chat_id: int, issues: List[Issue]) -> None:
        context.application.bot_data[_issues_key(chat_id)] = issues

    def _get_issues(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> List[Issue]:
        val = context.application.bot_data.get(_issues_key(chat_id))
        return val if isinstance(val, list) else []

    def _store_fixplan(context: ContextTypes.DEFAULT_TYPE, chat_id: int, plan: dict[str, Any]) -> None:
        context.application.bot_data[_fixplan_key(chat_id)] = plan

    def _get_fixplan(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> Optional[dict[str, Any]]:
        val = context.application.bot_data.get(_fixplan_key(chat_id))
        return val if isinstance(val, dict) else None

    def _pm_keyboard(
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        pms: List[str],
        *,
        action: str,
    ) -> InlineKeyboardMarkup:
        _store_pm_list_for_chat(context, chat_id, pms)

        buttons: List[List[InlineKeyboardButton]] = []
        buttons.append([InlineKeyboardButton("Все PM", callback_data=f"{action}pm:all")])

        max_items = 20
        shown = pms[:max_items]
        row: List[InlineKeyboardButton] = []
        for idx, pm in enumerate(shown):
            row.append(InlineKeyboardButton(pm, callback_data=f"{action}pm:{idx}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        if len(pms) > max_items:
            buttons.append([InlineKeyboardButton(f"…ещё {len(pms) - max_items}", callback_data="noop")])

        return InlineKeyboardMarkup(buttons)

    async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        _ = context
        text = (
            "Я бот для проверки ресурсного плана (локальная XLSX выгрузка).\n\n"
            "Команды:\n"
            "- /audit — проверить план и показать ошибки\n"
            "- /audit <ФИО PM> — аудит только по выбранному PM\n"
            "- /summary — GPT‑5: короткий план исправлений\n"
            "- /summary <ФИО PM> — summary только по выбранному PM\n"
            "- /fix preview [ФИО PM] — подготовить правки (поставить 0 в пустые ячейки на 2 мес. вперед)\n"
            "- /fix apply — применить подготовленные правки в копию XLSX\n"
            "\n"
            "Можно и без команд (просто напиши сообщением):\n"
            "- «Покажи ошибки»\n"
            "- «Покажи ошибки по менеджеру Яковлева Елена»\n"
            "- «Сделай план исправлений»\n"
            "- «Сделай план исправлений для менеджера Иванюк Полина»\n"
            "- «Обнови данные»\n"
            "- «Подготовь правки» / «Применить правки»\n"
            "- «Почему это ошибка?» (например: «Почему пустой месяц — это критично?»)\n"
        )
        await _send_long(update, text)

    async def audit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        report = run_xlsx_audit(
            settings=settings,
            path=settings.local_xlsx_path,
            sheet=settings.local_xlsx_sheet or None,
        )
        all_issues = list(report.issues)
        pm_query = " ".join(getattr(context, "args", []) or []).strip()

        msg = _message_from_update(update)
        if not pm_query and msg and msg.chat:
            pms = _extract_pm_list(all_issues)
            kb = _pm_keyboard(context, msg.chat.id, pms, action="audit")
            await _send_long(update, "Выбери PM для /audit:", reply_markup=kb)
            return

        filtered = _filter_issues_by_pm(all_issues, pm_query) if pm_query else all_issues

        if pm_query and not filtered:
            pms = _extract_pm_list(all_issues)
            hint = ", ".join(pms[:15]) if pms else "(нет PM в данных)"
            await _send_long(
                update,
                f"Не нашёл проблем по PM '{pm_query}'. Примеры доступных PM: {hint}",
            )
            return

        if msg and msg.chat:
            _store_issues(context, msg.chat.id, filtered)
            _store_audit_context(context, msg.chat.id, _build_llm_context(filtered))

        title = f"Аудит (PM: {pm_query})" if pm_query else "Аудит (все PM)"
        await _send_long(update, title + "\n\n" + format_issues_text(filtered, limit=80, full=False))

    async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not settings.openai_api_key:
            await _send_long(update, "Не задан OPENAI_API_KEY. Добавь в .env и перезапусти бота.")
            return

        report = run_xlsx_audit(
            settings=settings,
            path=settings.local_xlsx_path,
            sheet=settings.local_xlsx_sheet or None,
        )
        all_issues = list(report.issues)
        pm_query = " ".join(getattr(context, "args", []) or []).strip()

        msg = _message_from_update(update)
        if not pm_query and msg and msg.chat:
            pms = _extract_pm_list(all_issues)
            kb = _pm_keyboard(context, msg.chat.id, pms, action="summary")
            await _send_long(update, "Выбери PM для /summary:", reply_markup=kb)
            return

        filtered = _filter_issues_by_pm(all_issues, pm_query) if pm_query else all_issues
        if pm_query and not filtered:
            pms = _extract_pm_list(all_issues)
            hint = ", ".join(pms[:15]) if pms else "(нет PM в данных)"
            await _send_long(
                update,
                f"Не нашёл проблем по PM '{pm_query}'. Примеры доступных PM: {hint}",
            )
            return

        if msg and msg.chat:
            _store_issues(context, msg.chat.id, filtered)
            _store_audit_context(context, msg.chat.id, _build_llm_context(filtered))

        llm_context = _build_llm_context(filtered)
        if pm_query:
            llm_context["filter"] = {"pm": pm_query}
        prompt = build_summary_prompt(pm_filter=pm_query or None)

        def _call_llm_sync() -> str:
            client = Gpt5Client(Gpt5Config(api_key=settings.openai_api_key, model=settings.openai_model))
            return client.summarize(system=SYSTEM_PROMPT, prompt=prompt, context=llm_context)

        await _send_long(update, "Готовлю summary через GPT‑5…")
        try:
            text = await asyncio.to_thread(_call_llm_sync)
        except Exception as e:  # noqa: BLE001
            await _send_long(update, f"Ошибка при вызове GPT‑5: {type(e).__name__}: {e}")
            return

        await _send_long(update, text or "GPT‑5 вернул пустой ответ.")

    async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.callback_query:
            return

        q = update.callback_query
        await q.answer()

        data = q.data or ""
        if data == "noop":
            return

        if ":" not in data:
            return
        action, val = data.split(":", 1)
        if action not in {"auditpm", "summarypm"}:
            return

        if not q.message:
            return
        chat_id = q.message.chat_id

        report = run_xlsx_audit(
            settings=settings,
            path=settings.local_xlsx_path,
            sheet=settings.local_xlsx_sheet or None,
        )
        all_issues = list(report.issues)

        pm_query = ""
        if val != "all":
            try:
                idx = int(val)
            except ValueError:
                return
            pms = _get_pm_list_for_chat(context, chat_id)
            if idx < 0 or idx >= len(pms):
                return
            pm_query = pms[idx]

        filtered = _filter_issues_by_pm(all_issues, pm_query) if pm_query else all_issues
        _store_issues(context, chat_id, filtered)
        _store_audit_context(context, chat_id, _build_llm_context(filtered))

        if action == "auditpm":
            title = f"Аудит (PM: {pm_query})" if pm_query else "Аудит (все PM)"
            await _send_long(update, title + "\n\n" + format_issues_text(filtered, limit=80, full=False))
            return

        # summarypm
        if not settings.openai_api_key:
            await _send_long(update, "Не задан OPENAI_API_KEY. Добавь в .env и перезапусти бота.")
            return

        llm_context = _build_llm_context(filtered)
        if pm_query:
            llm_context["filter"] = {"pm": pm_query}
        prompt = build_summary_prompt(pm_filter=pm_query or None)

        def _call_llm_sync() -> str:
            client = Gpt5Client(Gpt5Config(api_key=settings.openai_api_key, model=settings.openai_model))
            return client.summarize(system=SYSTEM_PROMPT, prompt=prompt, context=llm_context)

        await _send_long(update, "Готовлю summary через GPT‑5…")
        try:
            text = await asyncio.to_thread(_call_llm_sync)
        except Exception as e:  # noqa: BLE001
            await _send_long(update, f"Ошибка при вызове GPT‑5: {type(e).__name__}: {e}")
            return
        await _send_long(update, text or "GPT‑5 вернул пустой ответ.")

    async def chat_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = _message_from_update(update)
        if msg is None or not msg.chat:
            return

        question = (msg.text or "").strip()
        if not question:
            return

        chat_id = msg.chat.id

        def _resolve_pm_from_text(issues: List[Issue], text: str) -> str:
            txt = text.lower()
            pms = _extract_pm_list(issues)
            for pm in pms:
                if pm.lower() in txt:
                    return pm
            # try "pm <name>" / "пм <name>"
            for token in ["pm", "пм"]:
                if token in txt:
                    idx = txt.find(token)
                    tail = txt[idx + len(token) :].strip(" :,-—")
                    if tail:
                        return tail
            return ""

        async def _ensure_cache() -> List[Issue]:
            cached = _get_issues(context, chat_id)
            if cached:
                return cached
            report = run_xlsx_audit(
                settings=settings,
                path=settings.local_xlsx_path,
                sheet=settings.local_xlsx_sheet or None,
            )
            issues = list(report.issues)
            _store_issues(context, chat_id, issues)
            _store_audit_context(context, chat_id, _build_llm_context(issues))
            return issues

        q = question.lower()
        issues_all = await _ensure_cache()
        pm_filter = _resolve_pm_from_text(issues_all, question)
        issues_filtered = _filter_issues_by_pm(issues_all, pm_filter) if pm_filter else issues_all

        # Intent routing (simple, deterministic):
        wants_refresh = any(k in q for k in ["обнов", "refresh", "перечитай", "reload"])
        wants_audit = any(k in q for k in ["аудит", "проверь", "провер", "ошибк", "audit"])
        wants_summary = any(k in q for k in ["summary", "саммари", "план", "что делать", "приоритет", "рекомендац"])

        if wants_refresh:
            report = run_xlsx_audit(
                settings=settings,
                path=settings.local_xlsx_path,
                sheet=settings.local_xlsx_sheet or None,
            )
            issues_new = list(report.issues)
            _store_issues(context, chat_id, issues_new)
            _store_audit_context(context, chat_id, _build_llm_context(issues_new))
            await _send_long(update, "Ок, обновил данные. Напиши: 'покажи ошибки' или 'summary'.")
            return

        wants_fix_preview = any(k in q for k in ["подготовь прав", "preview прав", "предложи прав", "fix preview"])
        wants_fix_apply = any(k in q for k in ["примен", "apply прав", "fix apply"])

        if wants_fix_preview:
            plan = plan_fill_empty_months_with_zero(
                sheet_values=read_xlsx_as_sheet_values(
                    path=settings.local_xlsx_path,
                    sheet_name=settings.local_xlsx_sheet or None,
                ),
                sheet_name=settings.local_xlsx_sheet or "(first)",
                months_ahead=2,
                pm_filter=pm_filter or None,
            )
            _store_fixplan(
                context,
                chat_id,
                {"pm": pm_filter or "", "count": len(plan.updates)},
            )
            await _send_long(
                update,
                f"Подготовил правки: {len(plan.updates)} ячеек -> 0.\n"
                "Чтобы применить: напиши «Применить правки» или /fix apply.\n"
                "Файл будет сохранен как копия (оригинал не трогаю).",
            )
            return

        if wants_fix_apply:
            plan_meta = _get_fixplan(context, chat_id)
            if not plan_meta:
                await _send_long(update, "Сначала сделай preview: «Подготовь правки» или /fix preview.")
                return
            # recompute plan to avoid stale indices / after refresh
            plan = plan_fill_empty_months_with_zero(
                sheet_values=read_xlsx_as_sheet_values(
                    path=settings.local_xlsx_path,
                    sheet_name=settings.local_xlsx_sheet or None,
                ),
                sheet_name=settings.local_xlsx_sheet or "(first)",
                months_ahead=2,
                pm_filter=(plan_meta.get("pm") or "").strip() or None,
            )
            if not plan.updates:
                await _send_long(update, "Нет правок для применения (0 ячеек).")
                return
            out_dir = Path(settings.local_xlsx_output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "resource_plan.fixed.xlsx"
            res = apply_fix_plan_to_xlsx_copy(
                input_path=settings.local_xlsx_path,
                plan=plan,
                output_path=out_path,
            )
            await _send_long(
                update,
                f"Готово. Применено правок: {res.applied_count}.\n"
                f"Сохранено в: {res.output_path}",
            )
            return

        if wants_audit:
            title = f"Аудит (PM: {pm_filter})" if pm_filter else "Аудит (все PM)"
            await _send_long(
                update,
                title + "\n\n" + format_issues_text(issues_filtered, limit=80, full=False),
            )
            return

        if wants_summary:
            if not settings.openai_api_key:
                await _send_long(
                    update,
                    "Чтобы сделать план исправлений, нужен OPENAI_API_KEY. Пока могу показать ошибки (аудит).",
                )
                return

            llm_context = _build_llm_context(issues_filtered)
            if pm_filter:
                llm_context["filter"] = {"pm": pm_filter}
            prompt = build_summary_prompt(pm_filter=pm_filter or None)

            def _call_llm_sync() -> str:
                client = Gpt5Client(Gpt5Config(api_key=settings.openai_api_key, model=settings.openai_model))
                return client.summarize(system=SYSTEM_PROMPT, prompt=prompt, context=llm_context)

            await _send_long(update, "Готовлю summary через GPT‑5…")
            try:
                text = await asyncio.to_thread(_call_llm_sync)
            except Exception as e:  # noqa: BLE001
                await _send_long(update, f"Ошибка при вызове GPT‑5: {type(e).__name__}: {e}")
                return
            await _send_long(update, text or "GPT‑5 вернул пустой ответ.")
            return

        # Fallback Q&A over current audit context (GPT-5), if enabled
        audit_ctx = _get_audit_context(context, chat_id)
        if audit_ctx is None:
            audit_ctx = _build_llm_context(issues_filtered)
            _store_audit_context(context, chat_id, audit_ctx)

        if not settings.openai_api_key:
            await _send_long(
                update,
                "Могу показать ошибки: напиши «Покажи ошибки» или используй /audit.\n"
                "Для ответов на вопросы «почему/что делать» нужен OPENAI_API_KEY.",
            )
            return

        prompt = build_chat_prompt(user_message=question)

        def _call_llm_sync() -> str:
            client = Gpt5Client(Gpt5Config(api_key=settings.openai_api_key, model=settings.openai_model))
            return client.summarize(system=SYSTEM_PROMPT, prompt=prompt, context=audit_ctx)

        try:
            text = await asyncio.to_thread(_call_llm_sync)
        except Exception as e:  # noqa: BLE001
            await _send_long(update, f"Ошибка при вызове GPT‑5: {type(e).__name__}: {e}")
            return

        await _send_long(update, text or "Не смог сформировать ответ. Попробуй переформулировать вопрос.")

    async def fix_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = _message_from_update(update)
        if msg is None or not msg.chat:
            return
        chat_id = msg.chat.id

        args = getattr(context, "args", []) or []
        if not args:
            await _send_long(update, "Используй: /fix preview [PM] или /fix apply")
            return

        sub = args[0].lower()
        pm_query = " ".join(args[1:]).strip()

        if sub == "preview":
            plan = plan_fill_empty_months_with_zero(
                sheet_values=read_xlsx_as_sheet_values(
                    path=settings.local_xlsx_path,
                    sheet_name=settings.local_xlsx_sheet or None,
                ),
                sheet_name=settings.local_xlsx_sheet or "(first)",
                months_ahead=2,
                pm_filter=pm_query or None,
            )
            _store_fixplan(context, chat_id, {"pm": pm_query, "count": len(plan.updates)})
            await _send_long(
                update,
                f"Preview правок: {len(plan.updates)} ячеек -> 0.\n"
                "Чтобы применить: /fix apply\n"
                "Файл будет сохранен как копия (оригинал не трогаю).",
            )
            return

        if sub == "apply":
            plan_meta = _get_fixplan(context, chat_id)
            if not plan_meta:
                await _send_long(update, "Сначала сделай /fix preview (можно с PM).")
                return

            plan = plan_fill_empty_months_with_zero(
                sheet_values=read_xlsx_as_sheet_values(
                    path=settings.local_xlsx_path,
                    sheet_name=settings.local_xlsx_sheet or None,
                ),
                sheet_name=settings.local_xlsx_sheet or "(first)",
                months_ahead=2,
                pm_filter=(plan_meta.get("pm") or "").strip() or None,
            )
            if not plan.updates:
                await _send_long(update, "Нет правок для применения (0 ячеек).")
                return

            out_dir = Path(settings.local_xlsx_output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "resource_plan.fixed.xlsx"
            res = apply_fix_plan_to_xlsx_copy(
                input_path=settings.local_xlsx_path,
                plan=plan,
                output_path=out_path,
            )
            await _send_long(
                update,
                f"Готово. Применено правок: {res.applied_count}.\n"
                f"Сохранено в: {res.output_path}",
            )
            return

        await _send_long(update, "Неизвестная команда. Используй: /fix preview [PM] или /fix apply")

    async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await chat_text(update, context)

    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("audit", audit_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("fix", fix_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))
    return app


def run_bot(settings: Settings) -> None:
    app = build_application(settings)
    app.run_polling(allowed_updates=Update.ALL_TYPES)
