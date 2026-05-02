"""Groq vision-API provider.

Groq exposes an OpenAI-compatible Chat Completions endpoint at::

    POST https://api.groq.com/openai/v1/chat/completions

so the wire format mirrors :class:`OpenAIProvider`. The only meaningful
differences are the host URL and the default vision model. The vision
roster on Groq evolves frequently (older Llama-3.2-vision models have
been deprecated); ``meta-llama/llama-4-scout-17b-16e-instruct`` is the
current vision-capable default. Override per key in Settings.
"""

from __future__ import annotations

import base64
import json

import requests

from ..types import ImageInput, KeyEntry, ProviderResponse
from .base import Provider


GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(Provider):
    name = "groq"

    def analyze(
        self,
        key: KeyEntry,
        image: ImageInput,
        prompt: str,
        *,
        timeout: int = 60,
    ) -> ProviderResponse:
        model = key.model or "meta-llama/llama-4-scout-17b-16e-instruct"
        b64 = base64.b64encode(image.data).decode("ascii")
        data_url = f"data:{image.mime};base64,{b64}"

        payload = {
            "model": model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
        }
        headers = {
            "Authorization": f"Bearer {key.key}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(
                GROQ_ENDPOINT, headers=headers,
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
        choices = data.get("choices") or []
        if not choices:
            return ProviderResponse(raw_text="", error="Empty completion")
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content
                if isinstance(part, dict)
            )
        return ProviderResponse(raw_text=content or "")

    err_text = (resp.text or "")[:500]
    if resp.status_code == 429:
        return ProviderResponse(
            raw_text="", error=f"Rate limited (HTTP 429): {err_text}",
            rate_limited=True,
        )
    if resp.status_code == 401:
        return ProviderResponse(
            raw_text="", error=f"Invalid key (HTTP 401): {err_text}",
            invalid_key=True,
        )
    return ProviderResponse(
        raw_text="", error=f"HTTP {resp.status_code}: {err_text}",
    )
