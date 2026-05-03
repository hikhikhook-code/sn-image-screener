"""Persistence tests for the auto-save helpers added to KeyManager.

These cover the new behaviour required by the Settings UI: every
add / edit / delete / toggle / model change must hit disk immediately
so a fresh ``KeyManager`` (i.e. an app restart) sees the same state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from sn_image_screener.services.ai.key_manager import KeyManager
from sn_image_screener.services.ai.types import (
    KeyEntry, KeyStatus, ProviderName,
)


def _entry(label: str, **overrides) -> KeyEntry:
    base = dict(
        provider=ProviderName.GEMINI,
        label=label,
        key=f"AIza-{label}",
        model="gemini-1.5-flash",
        enabled=True,
        priority=0,
        status=KeyStatus.UNTESTED,
    )
    base.update(overrides)
    return KeyEntry(**base)


def _read_back(path: Path) -> List[KeyEntry]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [KeyEntry.from_dict(d) for d in raw["keys"]]


def test_add_and_save_persists_immediately(tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    idx = km.add_and_save(_entry("primary"))
    assert idx == 0
    # File should already exist after a single add — no manual save() needed.
    assert p.exists()
    on_disk = _read_back(p)
    assert [k.label for k in on_disk] == ["primary"]
    # A fresh KeyManager (simulating app restart) must see the same key.
    km2 = KeyManager(p)
    assert km2.count() == 1
    assert km2.usable_keys()[0].label == "primary"


def test_update_and_save_persists_changes(tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("primary"))
    km.update_and_save(0, _entry("primary", model="gemini-1.5-pro"))

    km2 = KeyManager(p)
    assert km2.all()[0].model == "gemini-1.5-pro"


def test_remove_and_save_persists_deletion(tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("a"))
    km.add_and_save(_entry("b"))
    km.remove_and_save(0)

    km2 = KeyManager(p)
    assert [k.label for k in km2.all()] == ["b"]


def test_set_enabled_and_save_persists_toggle(tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("primary"))
    assert km.all()[0].enabled is True

    km.set_enabled_and_save(0, False)

    km2 = KeyManager(p)
    assert km2.all()[0].enabled is False
    # And usable_keys() should respect the disabled state on reload.
    assert km2.usable_keys() == []


def test_set_model_and_save_persists_model_change(tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("primary"))
    km.set_model_and_save(0, "gemini-2.0-flash")

    km2 = KeyManager(p)
    assert km2.all()[0].model == "gemini-2.0-flash"


def test_set_status_and_save_persists_status(tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("primary"))
    km.set_status_and_save(0, KeyStatus.ACTIVE)

    km2 = KeyManager(p)
    assert km2.all()[0].status is KeyStatus.ACTIVE


def test_listener_fires_after_save(tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    calls: List[int] = []
    km.add_listener(lambda: calls.append(km.count()))
    km.add_and_save(_entry("a"))
    km.set_enabled_and_save(0, False)
    km.set_model_and_save(0, "gemini-2.0-flash")
    km.remove_and_save(0)
    # Each helper invokes save() once → exactly one listener call each.
    assert calls == [1, 1, 1, 0]


def test_remove_listener_stops_callbacks(tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    calls: List[int] = []

    def cb() -> None:
        calls.append(km.count())

    km.add_listener(cb)
    km.add_and_save(_entry("a"))
    km.remove_listener(cb)
    km.add_and_save(_entry("b"))
    assert calls == [1]


def test_settings_round_trip_simulates_app_restart(tmp_path: Path):
    """End-to-end: add, edit, toggle, restart, verify Execution panel
    would see at least one usable key."""
    p = tmp_path / "keys.json"

    # Session 1 — user adds two keys via Settings.
    km1 = KeyManager(p)
    km1.add_and_save(_entry("primary"))
    km1.add_and_save(_entry("secondary", provider=ProviderName.OPENAI,
                            model="gpt-4o-mini"))
    # User toggles secondary off.
    km1.set_enabled_and_save(1, False)

    # Session 2 — app restart.
    km2 = KeyManager(p)
    assert km2.count() == 2
    enabled = [k for k in km2.all() if k.enabled]
    assert [k.label for k in enabled] == ["primary"]
    # The Execution panel uses usable_keys() — it must see the primary.
    km2.reset_run_state()
    assert len(km2.usable_keys()) == 1
