"""Abstract base class shared by all AI vision providers.

Each concrete provider (Gemini / OpenAI / Groq) only has to implement
:meth:`Provider.analyze`; failover, JSON parsing, and tile-coordinate
translation are handled one level up in
:mod:`sn_image_screener.services.ai.run_anatomy_check`.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Optional

from ..types import ImageInput, KeyEntry, ProviderResponse


class Provider(ABC):
    """Abstract vision-capable provider."""

    name: str = "base"

    @abstractmethod
    def analyze(
        self,
        key: KeyEntry,
        image: ImageInput,
        prompt: str,
        *,
        timeout: int = 60,
    ) -> ProviderResponse:
        """Send `image` + `prompt` to the provider and return its raw text.

        Implementations MUST set:
          - ``rate_limited=True`` for HTTP 429 / quota responses
          - ``invalid_key=True`` for HTTP 401 / 403 / "invalid key" errors
          - ``error="..."`` for any non-2xx response or transport error
        and SHOULD NOT raise on network errors — return a
        :class:`ProviderResponse` with ``error`` set instead.
        """


# ---------------------------------------------------------------------------
# Helpers shared by the concrete providers
# ---------------------------------------------------------------------------

# Some models wrap their JSON in ```json ... ``` fences even when the
# prompt asks them not to. Strip those before parsing.
_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_loose(text: str) -> Optional[dict]:
    """Best-effort JSON parser for vision-model output.

    Models occasionally prepend a sentence ("Sure, here is the JSON:"),
    wrap the result in ```json fences, or append a comment. We strip
    those, find the first balanced ``{...}`` block, and try
    :func:`json.loads`. Returns ``None`` if nothing parses.
    """
    if not text:
        return None
    cleaned = _JSON_FENCE.sub("", text).strip()
    # Quick path
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Fallback: locate the first '{' and the matching '}'
    start = cleaned.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = cleaned[start:i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    return None
    return None
