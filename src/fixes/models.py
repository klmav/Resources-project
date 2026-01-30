from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CellRef:
    """
    1-based row/col.
    """

    row: int
    col: int


@dataclass(frozen=True)
class CellUpdate:
    sheet_name: str
    cell: CellRef
    kind: str  # "set_value" | "highlight"
    reason: str
    new_value: float | int | str | None = None
    fill_rgb: Optional[str] = None
    month_label: Optional[str] = None  # e.g. "01.26"
    pm: Optional[str] = None
    person: Optional[str] = None


@dataclass(frozen=True)
class FixPlan:
    """
    A batch of safe edits to apply.
    """

    sheet_name: str
    description: str
    updates: list[CellUpdate]
