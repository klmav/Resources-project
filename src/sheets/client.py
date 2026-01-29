from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..config import Settings


@dataclass(frozen=True)
class SheetValues:
    """
    Сырой прямоугольник значений из Google Sheets (как возвращает API).
    Пока это упрощенная модель для MVP-каркаса.
    """

    values: List[List[str]]


class SheetsClient:
    """
    Каркас клиента Google Sheets.

    В MVP мы подключим Google Sheets API и научим этот класс:
    - читать диапазон
    - писать исправления (опционально, после подтверждения)
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._service = None

    def _get_service(self):
        if self._service is not None:
            return self._service

        if self._settings.google_auth_mode != "service_account":
            raise ValueError(
                f"Unsupported GOOGLE_AUTH_MODE='{self._settings.google_auth_mode}'. "
                "For MVP use 'service_account'."
            )

        try:
            from google.oauth2.service_account import Credentials  # type: ignore
            from googleapiclient.discovery import build  # type: ignore
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                "Google Sheets dependencies are not installed. "
                "For local XLSX mode they are not needed; for Sheets mode install google-api-python-client + google-auth."
            ) from e

        creds = Credentials.from_service_account_file(
            self._settings.google_service_account_file,
            scopes=[s.strip() for s in self._settings.google_scopes.split(",") if s.strip()],
        )
        self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        return self._service

    def read_range(self, a1_range: Optional[str] = None) -> SheetValues:
        """
        Читает диапазон в A1-формате: "<TAB>!A:Z".
        """
        if not self._settings.google_sheet_id:
            return SheetValues(values=[])

        rng = a1_range or f"{self._settings.google_sheet_tab}!{self._settings.google_sheet_range}"
        service = self._get_service()

        resp = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=self._settings.google_sheet_id, range=rng, majorDimension="ROWS")
            .execute()
        )
        values = resp.get("values", []) or []
        # приводим к str (API иногда возвращает числа)
        normalized: List[List[str]] = [[str(c) for c in row] for row in values]
        return SheetValues(values=normalized)

