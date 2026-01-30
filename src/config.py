from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Google Sheets
    google_sheet_id: str = ""
    google_sheet_tab: str = "Plan"
    google_sheet_range: str = "A:Z"
    google_auth_mode: str = "service_account"
    google_service_account_file: str = "secrets/service-account.json"
    google_scopes: str = "https://www.googleapis.com/auth/spreadsheets.readonly"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Audit behavior
    stale_days: int = 3

    # Local XLSX mode (for bot / local runs)
    local_xlsx_path: str = "auto"
    local_xlsx_sheet: str = ""
    local_xlsx_output_dir: str = "out"

    # OpenAI / GPT-5 (optional)
    openai_api_key: str = ""
    openai_model: str = "gpt-5"


def _load_dotenv_if_available() -> None:
    """
    Пытаемся загрузить .env, но не делаем это обязательным (чтобы проект
    запускался даже без установки зависимостей).
    """
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv()
    except Exception:
        return


def _get_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def get_settings() -> Settings:
    _load_dotenv_if_available()
    return Settings(
        google_sheet_id=os.getenv("GOOGLE_SHEET_ID", ""),
        google_sheet_tab=os.getenv("GOOGLE_SHEET_TAB", "Plan"),
        google_sheet_range=os.getenv("GOOGLE_SHEET_RANGE", "A:Z"),
        google_auth_mode=os.getenv("GOOGLE_AUTH_MODE", "service_account"),
        google_service_account_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "secrets/service-account.json"),
        google_scopes=os.getenv("GOOGLE_SCOPES", "https://www.googleapis.com/auth/spreadsheets.readonly"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        stale_days=_get_int("STALE_DAYS", 3),
        local_xlsx_path=os.getenv("LOCAL_XLSX_PATH", "auto"),
        local_xlsx_sheet=os.getenv("LOCAL_XLSX_SHEET", ""),
        local_xlsx_output_dir=os.getenv("LOCAL_XLSX_OUTPUT_DIR", "out"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5"),
    )

