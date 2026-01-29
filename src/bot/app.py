from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from ..config import Settings
from ..services.audit import AuditService
from ..main import format_issues_text


def build_application(settings: Settings) -> Application:
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required to run bot")

    app = Application.builder().token(settings.telegram_bot_token).build()

    async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = (
            "Я бот для проверки ресурсного плана в Google Sheets.\n\n"
            "Команды:\n"
            "- /audit — проверить план и показать ошибки\n"
            "- /help — помощь\n"
        )
        if update.message:
            await update.message.reply_text(text)

    async def audit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        report = AuditService(settings=settings).run()
        text = format_issues_text(report.issues)
        if update.message:
            await update.message.reply_text(text)

    async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("Напиши /audit чтобы проверить план, или /help.")

    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("audit", audit_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))
    return app


def run_bot(settings: Settings) -> None:
    app = build_application(settings)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

