from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..config import Settings


@dataclass(frozen=True)
class TelegramNotifier:
    settings: Settings

    def is_configured(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    def send_text(self, text: str) -> None:
        if not self.is_configured():
            return

        try:
            from telegram import Bot  # type: ignore
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                "Telegram dependencies are not installed. Install optional deps or disable Telegram notifier."
            ) from e

        async def _send() -> None:
            bot = Bot(token=self.settings.telegram_bot_token)
            await bot.send_message(chat_id=self.settings.telegram_chat_id, text=text)

        try:
            asyncio.run(_send())
        except RuntimeError:
            # If there's already a running event loop (rare for our CLI),
            # we fall back to scheduling.
            loop = asyncio.get_event_loop()
            loop.create_task(_send())

