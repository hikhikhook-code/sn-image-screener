"""Persistent API-key manager for the AI Anatomy Inspector.

Keys are stored as JSON in the user's data directory:

    Linux:   ~/.config/sn_image_screener/api_keys.json
    macOS:   ~/Library/Application Support/sn_image_screener/api_keys.json
    Windows: %APPDATA%\\sn_image_screener\\api_keys.json

This is the desktop equivalent of "save to localStorage": it is local
to one user / one machine, recoverable, and clearly NOT a secrets
vault. The Settings UI shows a warning to that effect.

Behaviour requirements
----------------------
- max **20** keys total (across all providers)
- ordered by `priority` (ascending, i.e. priority 0 = first)
- enable / disable per key
- per-key status (untested / active / failed / rate_limited / exhausted)
- a key marked `failed` / `rate_limited` is skipped during the current
  run but stays in the file for the next session
- thread-safe save (the orchestrator updates statuses from a worker
  thread)
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

from .types import KeyEntry, KeyStatus, ProviderName, now_ts


MAX_KEYS = 20

# How long to silence a rate-limited / failed key during the current
# run before retrying it. Provider error messages sometimes carry an
# explicit "Please try again in X.Xs" hint which we honour when
# present (see _parse_retry_after_seconds).
DEFAULT_RATE_LIMIT_COOLDOWN_S = 30.0
DEFAULT_FAILURE_COOLDOWN_S = 300.0  # invalid/key/quota errors

_RETRY_AFTER_RE = re.compile(
    r"try again in\s+([0-9]+(?:\.[0-9]+)?)\s*s", re.IGNORECASE,
)


def _parse_retry_after_seconds(message: str) -> Optional[float]:
    """Pull a 'try again in N.Ns' duration out of a provider error."""
    if not message:
        return None
    m = _RETRY_AFTER_RE.search(message)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def user_data_dir(app_name: str = "sn_image_screener") -> Path:
    """Return a per-user, per-OS data directory for the app."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming")))
        return base / app_name
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name
    base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / app_name


def default_keys_path() -> Path:
    return user_data_dir() / "api_keys.json"


class KeyManager:
    """Load / save / iterate API keys with per-run cooldown tracking."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else default_keys_path()
        self._lock = threading.RLock()
        self._keys: List[KeyEntry] = []
        # Map from key index to the unix timestamp at which the key's
        # cooldown lifts. Anything <= now_ts() is usable again. Cleared
        # by `reset_run_state()` at the start of each run.
        self._cooldown: Dict[int, float] = {}
        # Listeners notified after every successful disk flush so other
        # parts of the UI (e.g. the AI Inspector's "Run" button enabled
        # state) refresh without polling.
        self._listeners: List[callable] = []
        self.load()

    def add_listener(self, callback) -> None:  # noqa: ANN001
        """Register ``callback`` to fire after each ``save()``."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback) -> None:  # noqa: ANN001
        with self._lock:
            try:
                self._listeners.remove(callback)
            except ValueError:
                pass

    def _notify_changed(self) -> None:
        """Fire all listeners (best-effort, errors are swallowed)."""
        # Snapshot so callbacks that re-enter (e.g. add_listener while
        # we iterate) don't break the loop.
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        with self._lock:
            if not self.path.exists():
                self._keys = []
                return
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._keys = []
                return
            self._keys = [KeyEntry.from_dict(d) for d in raw.get("keys", [])]
            self._sort_in_place()

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"keys": [k.to_dict() for k in self._keys]}
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        self._notify_changed()

    def _sort_in_place(self) -> None:
        self._keys.sort(key=lambda k: (k.priority, k.provider.value, k.label))

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def all(self) -> List[KeyEntry]:
        with self._lock:
            return list(self._keys)

    def count(self) -> int:
        with self._lock:
            return len(self._keys)

    def add(self, entry: KeyEntry) -> None:
        with self._lock:
            if len(self._keys) >= MAX_KEYS:
                raise ValueError(
                    f"Cannot add more than {MAX_KEYS} API keys. "
                    f"Remove an existing key first."
                )
            if entry.priority == 0 and self._keys:
                entry.priority = max(k.priority for k in self._keys) + 1
            self._keys.append(entry)
            self._sort_in_place()

    def remove(self, index: int) -> None:
        with self._lock:
            if 0 <= index < len(self._keys):
                self._keys.pop(index)
                # Indices shifted — drop stale cooldown entries.
                self._cooldown.clear()

    def update(self, index: int, entry: KeyEntry) -> None:
        with self._lock:
            if 0 <= index < len(self._keys):
                self._keys[index] = entry
                self._sort_in_place()

    # ------------------------------------------------------------------
    # Auto-save helpers
    #
    # The Settings UI calls these after every individual edit so the
    # user's keys are flushed to disk immediately — there is no
    # "Save" button. This avoids the previous "added a key, Execution
    # panel still says 'Add at least one API key'" footgun where the
    # rebuilt-on-save flow could lose the freshly-typed entry if the
    # window was closed without explicitly clicking Save.
    # ------------------------------------------------------------------

    def add_and_save(self, entry: KeyEntry) -> int:
        """Append ``entry`` and flush. Returns the resulting index."""
        with self._lock:
            self.add(entry)
            self.save()
            for i, k in enumerate(self._keys):
                if (
                    k.provider == entry.provider
                    and k.label == entry.label
                    and k.key == entry.key
                ):
                    return i
            return -1

    def update_and_save(self, index: int, entry: KeyEntry) -> None:
        """Replace ``index`` with ``entry`` and flush."""
        with self._lock:
            self.update(index, entry)
            self.save()

    def remove_and_save(self, index: int) -> None:
        """Remove ``index`` and flush."""
        with self._lock:
            self.remove(index)
            self.save()

    def set_enabled_and_save(self, index: int, enabled: bool) -> None:
        """Toggle the ``enabled`` flag for ``index`` and flush."""
        with self._lock:
            if 0 <= index < len(self._keys):
                self._keys[index].enabled = bool(enabled)
                self.save()

    def set_model_and_save(self, index: int, model: str) -> None:
        """Replace the ``model`` field for ``index`` and flush."""
        with self._lock:
            if 0 <= index < len(self._keys):
                self._keys[index].model = model
                self.save()

    def set_status_and_save(
        self, index: int, status: KeyStatus, error: str = "",
    ) -> None:
        """Update only the cached status for ``index`` and flush.

        Used by the Settings card after the in-line "Test" returns so
        the badge persists across app restarts.
        """
        with self._lock:
            if 0 <= index < len(self._keys):
                self._keys[index].status = status
                self._keys[index].last_error = error
                self._keys[index].last_used_at = now_ts()
                self.save()

    def set_status(
        self, key: KeyEntry, status: KeyStatus, error: str = "",
    ) -> None:
        changed = False
        with self._lock:
            for i, k in enumerate(self._keys):
                if k is key or (
                    k.provider == key.provider
                    and k.label == key.label
                    and k.key == key.key
                ):
                    self._keys[i].status = status
                    self._keys[i].last_error = error
                    self._keys[i].last_used_at = now_ts()
                    if status == KeyStatus.RATE_LIMITED:
                        # Honour provider-supplied retry-after when present;
                        # else fall back to the default rate-limit window.
                        retry = _parse_retry_after_seconds(error or "")
                        wait = retry if retry is not None \
                            else DEFAULT_RATE_LIMIT_COOLDOWN_S
                        # Add a small safety margin so two near-simultaneous
                        # retries don't both slam the API the instant the
                        # window opens.
                        self._cooldown[i] = now_ts() + wait + 0.5
                    elif status in (KeyStatus.FAILED, KeyStatus.EXHAUSTED):
                        self._cooldown[i] = now_ts() + DEFAULT_FAILURE_COOLDOWN_S
                    elif status == KeyStatus.ACTIVE:
                        self._cooldown.pop(i, None)
                    changed = True
                    break
        # Fire listeners outside the lock so the UI can refresh its
        # status badge live during a scan. We deliberately do NOT call
        # ``save()`` here — transient cooldowns (rate-limit / fail)
        # should not survive an app restart, only persist via the
        # explicit ``set_status_and_save`` path used by the in-line
        # Test button.
        if changed:
            self._notify_changed()

    def cooldown_remaining_for(self, key: KeyEntry) -> Optional[float]:
        """Seconds until the given key's cooldown lifts, or ``None``.

        Returns ``None`` if the key has no active cooldown (already
        usable). Useful for showing a live countdown on the Settings
        card while a scan is rotating between keys.
        """
        with self._lock:
            for i, k in enumerate(self._keys):
                if k is key or (
                    k.provider == key.provider
                    and k.label == key.label
                    and k.key == key.key
                ):
                    until = self._cooldown.get(i)
                    if until is None:
                        return None
                    remaining = until - now_ts()
                    return remaining if remaining > 0 else None
            return None

    def reset_cooldown_for(self, key: KeyEntry) -> bool:
        """Forcibly clear the cooldown for ``key`` and re-mark it active.

        Used by the Settings "Reset cooldown" button so users can force
        a key back into rotation before its rate-limit window expires.
        Returns True if the key was found.
        """
        changed = False
        with self._lock:
            for i, k in enumerate(self._keys):
                if k is key or (
                    k.provider == key.provider
                    and k.label == key.label
                    and k.key == key.key
                ):
                    self._cooldown.pop(i, None)
                    self._keys[i].status = KeyStatus.UNTESTED
                    self._keys[i].last_error = ""
                    changed = True
                    break
        if changed:
            self._notify_changed()
        return changed

    def reorder(self, ordering: List[int]) -> None:
        """Reorder keys based on the new priority list of indexes."""
        with self._lock:
            if sorted(ordering) != list(range(len(self._keys))):
                raise ValueError("Reorder list must be a permutation of indexes")
            new = [self._keys[i] for i in ordering]
            for i, k in enumerate(new):
                k.priority = i
            self._keys = new

    # ------------------------------------------------------------------
    # Run-time iteration
    # ------------------------------------------------------------------

    def reset_run_state(self) -> None:
        """Clear per-run cooldown — call at the start of each scan."""
        with self._lock:
            self._cooldown.clear()

    def _is_in_cooldown(self, index: int, now: float) -> bool:
        """True iff the key at `index` is still cooling down at `now`."""
        until = self._cooldown.get(index)
        if until is None:
            return False
        if until <= now:
            # Cooldown expired — remove it eagerly so we stop re-checking.
            self._cooldown.pop(index, None)
            return False
        return True

    def next_available(
        self, provider: Optional[ProviderName] = None,
    ) -> Optional[KeyEntry]:
        """Return the next enabled, non-cooldown key (lowest priority)."""
        with self._lock:
            now = now_ts()
            for i, k in enumerate(self._keys):
                if self._is_in_cooldown(i, now):
                    continue
                if not k.enabled:
                    continue
                if provider is not None and k.provider != provider:
                    continue
                return k
            return None

    def usable_keys(self) -> List[KeyEntry]:
        """All currently usable keys — enabled and not in cooldown."""
        with self._lock:
            now = now_ts()
            return [
                k for i, k in enumerate(self._keys)
                if k.enabled and not self._is_in_cooldown(i, now)
            ]

    def soonest_cooldown_expiry(self) -> Optional[float]:
        """Return the earliest cooldown-expiry timestamp, or None.

        Useful for callers that want to wait for *any* key to come back
        online instead of giving up immediately.
        """
        with self._lock:
            if not self._cooldown:
                return None
            return min(self._cooldown.values())
