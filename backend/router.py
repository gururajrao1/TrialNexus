"""Zero-cost local inference router. No paid APIs, no keys, no downloads.

The core agents are pure deterministic functions and never need this router.
It exists only as an *optional* LLM enhancement: it probes a local Ollama
server (http://localhost:11434) and falls back to a deterministic stub when
Ollama is absent, so the platform always works offline.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("TrialNexusRouter")

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        text = "\n".join(lines)
    return text.strip()


def _json_repair(text: str) -> dict[str, Any]:
    """Best-effort parse of model output into a dict."""
    text = _strip_fences(text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"result": data}
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else {"result": data}
        except json.JSONDecodeError:
            pass
    return {"raw": text}


class ZeroCostRouter:
    """Local-first router: Ollama if present, deterministic stub otherwise."""

    def __init__(self, base_url: str = OLLAMA_URL, model: str = OLLAMA_MODEL) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def execute_query(
        self, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            return await self._call_ollama(messages, timeout=5.0)
        except Exception as exc:  # offline or no Ollama: deterministic path
            logger.info("Ollama unavailable (%s); using deterministic stub.", exc)
            return {
                "engine": "deterministic-local",
                "note": (
                    "No local LLM reachable. Core agents are deterministic "
                    "functions and do not need this path."
                ),
            }

    async def _call_ollama(
        self, messages: list[dict[str, str]], timeout: float
    ) -> dict[str, Any]:
        import httpx  # core dep, imported lazily

        payload = {"model": self.model, "messages": messages, "temperature": 0.1}
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(f"{self.base_url}/chat/completions", json=payload)
            res.raise_for_status()
            content = res.json()["choices"][0]["message"]["content"]
        parsed = _json_repair(content)
        parsed.setdefault("engine", f"ollama:{self.model}")
        return parsed


# Cookbook-compatible alias.
EngineRouter = ZeroCostRouter
