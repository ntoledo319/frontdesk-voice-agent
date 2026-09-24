"""Optional LLM layer.

When ``LLM_API_KEY`` is set, an OpenAI-compatible chat-completions endpoint
(OpenAI, OpenRouter, Ollama, llama.cpp server, …) is asked to extract intake
fields from messy caller utterances as strict JSON. Any failure — no key,
network error, bad JSON — silently falls back to the offline rule-based
parser, so the agent keeps working.

Stdlib only: no ``openai`` package required.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import date

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

EXTRACTION_PROMPT = """\
You are the field-extraction layer of a phone intake agent for {business}.
The business offers these services: {services}.

Today is {today}. From the caller's latest utterance, extract any of these
fields and reply with STRICT JSON only, no prose:

{{"name": str|null, "phone": str|null, "service": str|null,
  "date": "YYYY-MM-DD"|null, "time": "HH:MM (24h)"|null,
  "address": str|null, "notes": str|null}}

Rules:
- "service" must be one of the listed services, exactly as written, or null.
- Resolve relative dates ("next Friday", "tomorrow") against today's date.
- Normalize phone numbers to (XXX) XXX-XXXX.
- Use null for anything not stated. Never invent values.
"""


def _strip_json_fences(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def parse_extraction_response(text: str) -> dict[str, str]:
    """Parse an LLM extraction reply into a clean field dict.

    Tolerates markdown code fences and surrounding prose; drops nulls,
    non-strings, and unknown keys.
    """
    allowed = {"name", "phone", "service", "date", "time", "address", "notes"}
    candidate = _strip_json_fences(text)
    # If prose surrounds the JSON, grab the first balanced-looking object.
    if not candidate.startswith("{"):
        m = re.search(r"\{.*\}", candidate, re.DOTALL)
        if not m:
            raise ValueError("no JSON object in LLM response")
        candidate = m.group(0)
    raw = json.loads(candidate)
    if not isinstance(raw, dict):
        raise ValueError("LLM response is not a JSON object")
    return {
        k: v.strip()
        for k, v in raw.items()
        if k in allowed and isinstance(v, str) and v.strip()
    }


class LLMExtractor:
    """Callable extractor compatible with ``dialogue.IntakeAgent``."""

    def __init__(
        self,
        business_name: str,
        service_names: list[str],
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        today: date | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("LLM_API_KEY", "")
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL") or DEFAULT_MODEL
        self.today = today or date.today()
        self.timeout = timeout
        self.system_prompt = EXTRACTION_PROMPT.format(
            business=business_name,
            services=", ".join(service_names),
            today=self.today.isoformat(),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def __call__(self, utterance: str) -> dict[str, str]:
        if not self.enabled:
            return {}
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": utterance},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        return parse_extraction_response(content)
