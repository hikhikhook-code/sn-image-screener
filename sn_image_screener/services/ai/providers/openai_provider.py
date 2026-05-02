"""OpenAI Chat Completions vision provider.

Endpoint::

    POST https://api.openai.com/v1/chat/completions

Default model: ``gpt-4o-mini`` (multimodal). Caller can override per
key in Settings. If the user picks a model that doesn't accept images
the API returns 400 with a clear message; we surface that as the
provider error so the user can fix the model name.
"""

from __future__ import annotations

import base64
import json

import requests

from ..types import ImageInput, KeyEntry, ProviderResponse
from .base import Provider


OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider(Provider):
    name = "openai"

    def analyze(
        self,
        key: KeyEntry,
        image: ImageInput,
        prompt: str,
        *,
        timeout: int = 60,
    ) -> ProviderResponse:
        model = key.model or "gpt-4o-mini"
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
                OPENAI_ENDPOINT, headers=headers,
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
            raw_text="", error=f"Rate limited / quota (HTTP 429): {err_text}",
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
