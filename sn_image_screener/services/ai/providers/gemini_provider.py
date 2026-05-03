"""Google Gemini vision-API provider.

Uses the public REST endpoint::

    POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={KEY}

Default model: ``gemini-2.5-flash`` (cheap, fast, supports image input).
The gemini-1.5-* family is deprecated on the v1beta REST endpoint, so we
fall back to the current 2.5-flash model when a stored key has no model
set. The user can override the model per key in Settings.
"""

from __future__ import annotations

import base64
import json

import requests

from ..types import ImageInput, KeyEntry, ProviderResponse
from .base import Provider


GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class GeminiProvider(Provider):
    name = "gemini"

    def analyze(
        self,
        key: KeyEntry,
        image: ImageInput,
        prompt: str,
        *,
        timeout: int = 60,
    ) -> ProviderResponse:
        model = key.model or "gemini-2.5-flash"
        url = GEMINI_ENDPOINT.format(model=model)

        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": image.mime,
                            "data": base64.b64encode(image.data).decode("ascii"),
                        }
                    },
                ],
            }],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        try:
            resp = requests.post(
                url, params={"key": key.key},
                json=payload, timeout=timeout,
            )
        except requests.RequestException as exc:
            return ProviderResponse(raw_text="", error=f"Network error: {exc}")

        return _to_response(resp)


def _to_response(resp: requests.Response) -> ProviderResponse:
    if resp.status_code == 200:
        try:
            data = resp.json()
        except json.JSONDecodeError:
            return ProviderResponse(raw_text=resp.text or "", error="Non-JSON 200 response")
        text = _extract_text(data)
        return ProviderResponse(raw_text=text)

    err_text = (resp.text or "")[:500]
    if resp.status_code == 429:
        return ProviderResponse(
            raw_text="", error=f"Rate limited (HTTP 429): {err_text}",
            rate_limited=True,
        )
    if resp.status_code in (401, 403):
        return ProviderResponse(
            raw_text="", error=f"Invalid key (HTTP {resp.status_code}): {err_text}",
            invalid_key=True,
        )
    if resp.status_code == 400 and "API key" in err_text:
        return ProviderResponse(
            raw_text="", error=f"Invalid key (HTTP 400): {err_text}",
            invalid_key=True,
        )
    return ProviderResponse(
        raw_text="", error=f"HTTP {resp.status_code}: {err_text}",
    )


def _extract_text(data: dict) -> str:
    """Pull the text payload out of a Gemini response."""
    candidates = data.get("candidates") or []
    if not candidates:
        # Empty candidates with a `promptFeedback.blockReason` => safety block
        feedback = data.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            return ""
        return ""
    parts = candidates[0].get("content", {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts)
