"""Tests for the persistent API-key manager."""

from __future__ import annotations

from pathlib import Path

import pytest

from sn_image_screener.services.ai.key_manager import KeyManager, MAX_KEYS
from sn_image_screener.services.ai.types import (
    KeyEntry, KeyStatus, ProviderName,
)


def _key(label: str, provider=ProviderName.GEMINI, priority=0,
         enabled=True) -> KeyEntry:
    return KeyEntry(
        provider=provider, label=label, key=f"sk-{label}",
        model="m", enabled=enabled, priority=priority,
    )


def test_round_trip_save_load(tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add(_key("primary"))
    km.add(_key("secondary", provider=ProviderName.OPENAI))
    km.save()

    km2 = KeyManager(p)
    assert km2.count() == 2
    labels = sorted(k.label for k in km2.all())
    assert labels == ["primary", "secondary"]


def test_max_keys_enforced(tmp_path: Path):
    km = KeyManager(tmp_path / "keys.json")
    for i in range(MAX_KEYS):
        km.add(_key(f"k{i}"))
    with pytest.raises(ValueError):
        km.add(_key("overflow"))


def test_disabled_key_is_skipped(tmp_path: Path):
    km = KeyManager(tmp_path / "keys.json")
    km.add(_key("disabled", enabled=False))
    km.add(_key("active"))
    km.reset_run_state()
    nxt = km.next_available()
    assert nxt is not None
    assert nxt.label == "active"


def test_cooldown_after_failure(tmp_path: Path):
    km = KeyManager(tmp_path / "keys.json")
    km.add(_key("a", priority=0))
    km.add(_key("b", priority=1))
    km.reset_run_state()

    first = km.next_available()
    assert first.label == "a"

    km.set_status(first, KeyStatus.RATE_LIMITED, error="429")
    second = km.next_available()
    assert second is not None and second.label == "b"


def test_all_failed_returns_none(tmp_path: Path):
    km = KeyManager(tmp_path / "keys.json")
    km.add(_key("a", priority=0))
    km.add(_key("b", priority=1))
    km.reset_run_state()

    a = km.next_available()
    km.set_status(a, KeyStatus.FAILED, error="bad")
    b = km.next_available()
    km.set_status(b, KeyStatus.FAILED, error="bad")

    assert km.next_available() is None


def test_priority_order(tmp_path: Path):
    km = KeyManager(tmp_path / "keys.json")
    km.add(_key("low", priority=99))
    km.add(_key("high", priority=1))
    km.reset_run_state()
    assert km.next_available().label == "high"


def test_reset_run_state_lifts_cooldown(tmp_path: Path):
    km = KeyManager(tmp_path / "keys.json")
    km.add(_key("a"))
    km.reset_run_state()
    a = km.next_available()
    km.set_status(a, KeyStatus.RATE_LIMITED)
    assert km.next_available() is None
    km.reset_run_state()
    assert km.next_available() is not None
