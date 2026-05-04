"""Tests for the live cool-down + auto-rotation helpers on KeyManager.

These lock in the contract used by the Settings UI:

- ``set_status`` must fire ``add_listener`` callbacks even though it
  does not persist (transient cool-downs should not survive an app
  restart).
- ``cooldown_remaining_for`` must return a positive countdown for a
  rate-limited key and ``None`` once it lifts.
- ``reset_cooldown_for`` must clear the cool-down so ``next_available``
  picks the key up again.
- ``next_available`` must rotate to the next priority-ordered key when
  the highest-priority one is in cool-down, even across providers
  (this is what makes auto-rotate cross-provider).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List

from sn_image_screener.services.ai.key_manager import (
    DEFAULT_FAILURE_COOLDOWN_S, DEFAULT_RATE_LIMIT_COOLDOWN_S, KeyManager,
)
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


def test_set_status_fires_listeners_without_persisting(tmp_path: Path):
    """set_status mutates in-memory state only, but must still notify
    listeners so the Settings UI can refresh its badge live."""
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("primary"))
    fired: List[None] = []
    km.add_listener(lambda: fired.append(None))
    pre_mtime = p.stat().st_mtime_ns
    km.set_status(km.all()[0], KeyStatus.RATE_LIMITED, error="slow down")
    # Listener must have fired exactly once for the status change.
    assert len(fired) == 1
    # File must NOT have been touched \u2014 transient cool-downs should
    # not survive an app restart.
    assert p.stat().st_mtime_ns == pre_mtime


def test_cooldown_remaining_for_active_rate_limit(tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("primary"))
    km.set_status(
        km.all()[0], KeyStatus.RATE_LIMITED,
        error="please try again in 12.0s",
    )
    remaining = km.cooldown_remaining_for(km.all()[0])
    assert remaining is not None
    # Must honour the provider-supplied retry-after (12.0s) within a
    # small margin, not the 30s default.
    assert 11.0 < remaining < 14.0


def test_cooldown_remaining_for_no_cooldown(tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("primary"))
    assert km.cooldown_remaining_for(km.all()[0]) is None


def test_reset_cooldown_for_clears_state_and_notifies(tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("primary"))
    km.set_status(km.all()[0], KeyStatus.RATE_LIMITED, error="rl")
    fired: List[None] = []
    km.add_listener(lambda: fired.append(None))
    ok = km.reset_cooldown_for(km.all()[0])
    assert ok is True
    assert km.cooldown_remaining_for(km.all()[0]) is None
    # Status reset to UNTESTED so the runner won't avoid it.
    assert km.all()[0].status == KeyStatus.UNTESTED
    assert len(fired) == 1


def test_next_available_skips_cooled_down_key_and_rotates(tmp_path: Path):
    """Auto-rotate behaviour: when the highest-priority key hits a
    rate-limit, ``next_available`` must hand back the next usable key
    of any provider, not block on the rate-limited one."""
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("gemini-1", priority=0))
    km.add_and_save(_entry(
        "groq-1", provider=ProviderName.GROQ,
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        priority=1,
    ))
    # Pre-condition: gemini-1 is the lowest-priority enabled key.
    assert km.next_available().label == "gemini-1"
    # Simulate a 429 on gemini-1.
    km.set_status(km.all()[0], KeyStatus.RATE_LIMITED, error="429")
    # next_available must skip the cooled-down gemini-1 and return
    # the groq key, even though it's a different provider.
    nxt = km.next_available()
    assert nxt is not None
    assert nxt.label == "groq-1"
    assert nxt.provider == ProviderName.GROQ


def test_failure_uses_longer_cooldown_window(tmp_path: Path):
    """Invalid / quota errors get a 5-minute cooldown, not the 30s
    rate-limit window."""
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("primary"))
    km.set_status(km.all()[0], KeyStatus.FAILED, error="invalid api key")
    remaining = km.cooldown_remaining_for(km.all()[0])
    assert remaining is not None
    assert remaining > DEFAULT_RATE_LIMIT_COOLDOWN_S
    assert remaining <= DEFAULT_FAILURE_COOLDOWN_S + 1.0


def test_set_status_active_clears_cooldown(tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("primary"))
    km.set_status(km.all()[0], KeyStatus.RATE_LIMITED, error="rl")
    assert km.cooldown_remaining_for(km.all()[0]) is not None
    km.set_status(km.all()[0], KeyStatus.ACTIVE)
    assert km.cooldown_remaining_for(km.all()[0]) is None
