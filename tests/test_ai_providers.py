"""Tests for provider response parsing and JSON loose parser."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from sn_image_screener.services.ai.providers.base import parse_json_loose
from sn_image_screener.services.ai.providers.gemini_provider import GeminiProvider
from sn_image_screener.services.ai.providers.groq_provider import GroqProvider
from sn_image_screener.services.ai.providers.openai_provider import OpenAIProvider
from sn_image_screener.services.ai.types import (
    ImageInput, KeyEntry, ProviderName,
)


# ---------------------------------------------------------------------------
# parse_json_loose
# ---------------------------------------------------------------------------

def test_parse_clean_json():
    assert parse_json_loose('{"a": 1}') == {"a": 1}


def test_parse_fenced_json():
    text = '```json\n{"a": 1}\n```'
    assert parse_json_loose(text) == {"a": 1}


def test_parse_with_preamble():
    text = 'Sure! Here you go: {"status": "pass", "score": 95}'
    assert parse_json_loose(text) == {"status": "pass", "score": 95}


def test_parse_returns_none_on_garbage():
    assert parse_json_loose("definitely not json") is None
    assert parse_json_loose("") is None


def test_parse_handles_nested_braces():
    text = '{"outer": {"inner": [1, 2, 3]}}'
    assert parse_json_loose(text) == {"outer": {"inner": [1, 2, 3]}}


# ---------------------------------------------------------------------------
# Provider HTTP handling — mocked
# ---------------------------------------------------------------------------

def _key(provider=ProviderName.GEMINI, model="m") -> KeyEntry:
    return KeyEntry(
        provider=provider, label="test", key="sk-test",
        model=model, enabled=True, priority=0,
    )


def _img() -> ImageInput:
    return ImageInput(data=b"\xff\xd8\xff", mime="image/jpeg")


def _ok_gemini(text: str = '{"status": "pass"}') -> MagicMock:
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
    }
    return m


def _ok_oai(text: str = '{"status": "pass"}') -> MagicMock:
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {
        "choices": [{"message": {"content": text}}],
    }
    return m


def test_gemini_success():
    with patch("requests.post", return_value=_ok_gemini()):
        r = GeminiProvider().analyze(_key(), _img(), "prompt")
    assert r.error is None
    assert "pass" in r.raw_text


def test_gemini_rate_limit():
    m = MagicMock(status_code=429, text="quota exceeded")
    with patch("requests.post", return_value=m):
        r = GeminiProvider().analyze(_key(), _img(), "prompt")
    assert r.rate_limited is True
    assert r.error and "429" in r.error


def test_gemini_invalid_key():
    m = MagicMock(status_code=403, text="bad key")
    with patch("requests.post", return_value=m):
        r = GeminiProvider().analyze(_key(), _img(), "prompt")
    assert r.invalid_key is True


def test_openai_success():
    with patch("requests.post", return_value=_ok_oai()):
        r = OpenAIProvider().analyze(
            _key(provider=ProviderName.OPENAI), _img(), "prompt"
        )
    assert r.error is None
    assert r.raw_text


def test_openai_invalid_key():
    m = MagicMock(status_code=401, text="invalid")
    with patch("requests.post", return_value=m):
        r = OpenAIProvider().analyze(
            _key(provider=ProviderName.OPENAI), _img(), "prompt"
        )
    assert r.invalid_key is True


def test_groq_rate_limit():
    m = MagicMock(status_code=429, text="too many")
    with patch("requests.post", return_value=m):
        r = GroqProvider().analyze(
            _key(provider=ProviderName.GROQ), _img(), "prompt"
        )
    assert r.rate_limited is True


def test_network_error_does_not_raise():
    import requests as _req
    with patch("requests.post", side_effect=_req.ConnectionError("dns")):
        r = GeminiProvider().analyze(_key(), _img(), "prompt")
    assert r.error and "Network error" in r.error
    assert r.invalid_key is False
    assert r.rate_limited is False
