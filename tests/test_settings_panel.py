"""UI-level tests for the new Settings page.

These exercise the wiring between the SettingsPanel widget and the
auto-saving KeyManager helpers — they assert that interacting with a
card persists the change to disk and that the empty-state placeholder
hides as soon as a key is added.

Tests run headless via the ``offscreen`` Qt platform.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from sn_image_screener.services.ai.key_manager import KeyManager  # noqa: E402
from sn_image_screener.services.ai.types import (  # noqa: E402
    KeyEntry, KeyStatus, ProviderName,
)
from sn_image_screener.ui.settings_panel import (  # noqa: E402
    ApiKeyDialog, SettingsPanel,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


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


def test_settings_panel_renders_existing_keys(qapp, tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("primary"))
    km.add_and_save(_entry("secondary", provider=ProviderName.OPENAI,
                           model="gpt-4o-mini"))

    panel = SettingsPanel(km)
    assert len(panel._cards) == 2  # noqa: SLF001 — test-only access
    # Empty state should not be visible.
    assert panel._stack.currentIndex() == 0  # noqa: SLF001


def test_settings_panel_shows_empty_state_with_no_keys(qapp, tmp_path: Path):
    km = KeyManager(tmp_path / "keys.json")
    panel = SettingsPanel(km)
    assert panel._stack.currentIndex() == 1  # noqa: SLF001


def test_card_toggle_persists_immediately(qapp, tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("primary"))

    panel = SettingsPanel(km)
    card = panel._cards[0]  # noqa: SLF001
    assert card.chk_enabled.isChecked()

    card.chk_enabled.setChecked(False)
    qapp.processEvents()

    km2 = KeyManager(p)
    assert km2.all()[0].enabled is False


def test_card_model_dropdown_persists_immediately(qapp, tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    km.add_and_save(_entry("primary"))

    panel = SettingsPanel(km)
    card = panel._cards[0]  # noqa: SLF001

    # Pick a non-default supported model.
    target_model = "gemini-2.0-flash"
    for i in range(card.cb_model.count()):
        if card.cb_model.itemData(i) == target_model:
            card.cb_model.setCurrentIndex(i)
            break
    qapp.processEvents()

    km2 = KeyManager(p)
    assert km2.all()[0].model == target_model


def test_panel_signals_on_external_save(qapp, tmp_path: Path):
    p = tmp_path / "keys.json"
    km = KeyManager(p)
    panel = SettingsPanel(km)
    fired = []
    panel.keys_changed.connect(lambda: fired.append(True))

    km.add_and_save(_entry("primary"))
    qapp.processEvents()
    assert fired, "expected keys_changed to fire after a save()"


def test_dialog_default_model_is_recommended(qapp):
    dlg = ApiKeyDialog()
    # First option of the dropdown is the recommended model — its
    # display string ends with "(recommended)".
    text = dlg.cb_model.itemText(0)
    assert text.endswith("(recommended)")


def test_dialog_only_offers_supported_models(qapp):
    dlg = ApiKeyDialog()
    items = [dlg.cb_model.itemData(i) for i in range(dlg.cb_model.count())]
    # All items must be one of the known model ids — i.e. there are no
    # free-text options.
    from sn_image_screener.services.ai.models import models_for
    valid = {m.id for m in models_for(ProviderName.GEMINI)}
    for it in items:
        assert it in valid


def test_dialog_preserves_unknown_model_for_legacy_keys(qapp):
    legacy = _entry("legacy", model="some-old-model-name-not-in-registry")
    dlg = ApiKeyDialog(existing=legacy)
    items = [dlg.cb_model.itemData(i) for i in range(dlg.cb_model.count())]
    assert legacy.model in items
    # And the dialog should have it currently selected.
    assert dlg.cb_model.currentData() == legacy.model
