from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Gpt5Config:
    api_key: str
    model: str = "gpt-5"


class Gpt5Client:
    """
    Опциональный клиент. Если пакет openai не установлен — выдаст понятную ошибку.
    """

    def __init__(self, cfg: Gpt5Config) -> None:
        self._cfg = cfg

    def summarize(self, *, system: str, prompt: str, context: dict[str, Any]) -> str:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                "LLM deps are not installed. Run: python -m pip install -r requirements-llm.txt"
            ) from e

        client = OpenAI(api_key=self._cfg.api_key)

        # Minimal "chat" style. We keep it intentionally simple for MVP.
        # (We can expand with structured outputs / tools later.)
        ctx_json = json.dumps(context, ensure_ascii=False)

        resp = client.chat.completions.create(
            model=self._cfg.model,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"{prompt}\n\nCONTEXT(JSON):\n{ctx_json}",
                },
            ],
        )

        content: Optional[str] = None
        if resp.choices and resp.choices[0].message:
            content = resp.choices[0].message.content
        return content or ""

