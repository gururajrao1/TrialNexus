"""Zero-cost local inference router. No paid APIs, no keys, no downloads.

The core agents are pure deterministic functions and never need this router.
It exists only as an *optional* LLM enhancement: it probes a local Ollama
server (http://localhost:11434) and falls back to a deterministic stub when
Ollama is absent, so the platform always works offline.

Bring-your-own endpoint: set TRIALNEXUS_MODEL_BASE_URL to any
OpenAI-compatible /chat/completions URL (for example your Muse model
endpoint), TRIALNEXUS_MODEL_NAME for the model, and TRIALNEXUS_MODEL_API_KEY
when the endpoint needs one. The key lives only in the process environment —
never logged, stored, or returned. Anything the model drafts is verified
before display and fails closed.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("TrialNexusRouter")

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

MODEL_BASE_URL = os.getenv("TRIALNEXUS_MODEL_BASE_URL", OLLAMA_URL)
MODEL_NAME = os.getenv("TRIALNEXUS_MODEL_NAME", OLLAMA_MODEL)
MODEL_API_KEY = os.getenv("TRIALNEXUS_MODEL_API_KEY", "")


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
    """Local-first router: configured endpoint if present, stub otherwise."""

    def __init__(
        self,
        base_url: str = MODEL_BASE_URL,
        model: str = MODEL_NAME,
        api_key: str = MODEL_API_KEY,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    async def execute_query(
        self, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            return await self._call_model(messages, timeout=20.0)
        except Exception as exc:  # offline or no endpoint: deterministic path
            logger.info("Model endpoint unavailable (%s); using stub.", exc)
            return {
                "engine": "deterministic-local",
                "note": (
                    "No model endpoint reachable. Core agents are "
                    "deterministic functions and do not need this path."
                ),
            }

    async def _call_model(
        self, messages: list[dict[str, str]], timeout: float
    ) -> dict[str, Any]:
        import httpx  # core dep, imported lazily

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": self.model, "messages": messages, "temperature": 0.1}
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            res.raise_for_status()
            content = res.json()["choices"][0]["message"]["content"]
        parsed = _json_repair(content)
        custom = self.base_url != OLLAMA_URL.rstrip("/")
        parsed.setdefault("engine", f"{'custom' if custom else 'ollama'}:{self.model}")
        return parsed


# Cookbook-compatible alias.
EngineRouter = ZeroCostRouter
