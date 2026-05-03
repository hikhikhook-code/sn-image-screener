"""Settings page — full panel for API key management.

Replaces the legacy cramped "AI Anatomy — API Keys" table dialog.

Layout:

    ┌─────────────────────────────────────────────────────────────┐
    │  SETTINGS                                                   │
    │  Manage API keys, providers, and models for the AI tab.     │
    │  ─ warning banner ─                                         │
    │  ┌── API KEYS ─────────────────────── [+ ADD API KEY] ──┐   │
    │  │                                                      │   │
    │  │   ╭─ card ─────────────────────────────────────────╮ │   │
    │  │   │  GEMINI · primary key       [• untested]       │ │   │
    │  │   │  AIza••••••sxJk      MODEL: ▼ gemini-2.5-flash │ │   │
    │  │   │  [✓] enabled  [TEST]  [EDIT]  [DELETE]         │ │   │
    │  │   ╰────────────────────────────────────────────────╯ │   │
    │  │                                                      │   │
    │  └──────────────────────────────────────────────────────┘   │
    └─────────────────────────────────────────────────────────────┘

Every change (add / edit / delete / enabled toggle / model dropdown)
is persisted to disk **immediately** through the auto-save helpers on
:class:`KeyManager`. There is no batched "Save" button — the previous
dialog-based flow had a footgun where users would close without
saving and the Execution panel would still complain about no keys.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QStackedLayout, QToolButton, QVBoxLayout, QWidget,
)

from ..services.ai import (
    KeyManager, MAX_KEYS, default_model_for, is_supported, models_for,
)
from ..services.ai.providers import provider_for
from ..services.ai.types import (
    ImageInput, KeyEntry, KeyStatus, ProviderName,
)
from . import theme
from .widgets import EmptyState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def settings_icon(size: int = 22) -> QIcon:
    """Brutalist gear icon for the rail Settings entry.

    Six rectangular teeth around an outlined hub — flat, 2px stroke,
    matches the existing Technical / AI Inspector icons.
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(theme.INK)
    pen.setWidth(2)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    cx, cy = size // 2, size // 2
    outer_r = (size // 2) - 2
    hub_r = max(3, outer_r // 2)
    inner_r = max(2, outer_r // 4)

    # 8 short notches around the perimeter — drawn as small radial
    # rectangles. Use simple lines so the icon stays crisp.
    import math
    teeth = 8
    notch_len = max(2, outer_r // 3)
    for i in range(teeth):
        angle = (math.pi * 2.0 * i) / teeth
        x0 = cx + int((outer_r - notch_len) * math.cos(angle))
        y0 = cy + int((outer_r - notch_len) * math.sin(angle))
        x1 = cx + int(outer_r * math.cos(angle))
        y1 = cy + int(outer_r * math.sin(angle))
        p.drawLine(x0, y0, x1, y1)

    # Outer hub circle.
    p.drawEllipse(cx - hub_r, cy - hub_r, hub_r * 2, hub_r * 2)
    # Inner spindle.
    p.drawEllipse(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)

    p.end()
    return QIcon(pm)


def _mask_key(key: str) -> str:
    """Return a privacy-preserving preview of an API key."""
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}{'•' * 8}{key[-4:]}"


_PROVIDER_BADGE = {
    ProviderName.GEMINI: ("#1F36C7", "#FFFFFF"),
    ProviderName.OPENAI: ("#0E7E3D", "#FFFFFF"),
    ProviderName.GROQ:   ("#FF4D2E", "#111111"),
}

_STATUS_TEXT = {
    KeyStatus.UNTESTED:     "untested",
    KeyStatus.ACTIVE:       "active",
    KeyStatus.FAILED:       "invalid",
    KeyStatus.RATE_LIMITED: "rate_limited",
    KeyStatus.EXHAUSTED:    "exhausted",
}

_STATUS_COLORS = {
    KeyStatus.UNTESTED:     ("#EEEEEE", "#111111"),
    KeyStatus.ACTIVE:       (theme.PASS_BG, theme.PASS_FG),
    KeyStatus.FAILED:       (theme.REJECT_BG, theme.REJECT_FG),
    KeyStatus.RATE_LIMITED: (theme.REVIEW_BG, theme.REVIEW_FG),
    KeyStatus.EXHAUSTED:    (theme.INK, theme.YELLOW),
}


# ---------------------------------------------------------------------------
# Add / Edit dialog
# ---------------------------------------------------------------------------

class ApiKeyDialog(QDialog):
    """Dialog used both for adding and editing a single API key.

    The dialog only owns *form state* — persistence happens in the
    caller via :meth:`KeyManager.add_and_save` /
    :meth:`KeyManager.update_and_save`. Pass an existing
    :class:`KeyEntry` to enter edit mode.
    """

    def __init__(
        self,
        existing: Optional[KeyEntry] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._existing = existing
        self.setWindowTitle("Edit API Key" if existing else "Add API Key")
        self.setMinimumWidth(520)
        self.setStyleSheet(
            "QDialog{background:#F4F1EA; color:#111111;}"
            "QLabel{color:#111111;}"
            "QLineEdit{background:#FFFFFF; color:#111111;"
            " border:2px solid #111111; padding:6px 8px;"
            " font-family:'JetBrains Mono', Consolas, monospace;}"
            "QLineEdit:focus{background:#D6EE2C;}"
            "QComboBox{background:#FFFFFF; color:#111111;"
            " border:2px solid #111111; padding:5px 8px;}"
        )

        form = QFormLayout(self)

        self.cb_provider = QComboBox()
        for p in ProviderName:
            self.cb_provider.addItem(p.value.title(), p)
        self.cb_provider.currentIndexChanged.connect(self._on_provider_change)
        form.addRow("Provider", self.cb_provider)

        self.ed_label = QLineEdit()
        self.ed_label.setPlaceholderText("e.g. Personal — gemini #1")
        form.addRow("Label", self.ed_label)

        # API key with show/hide toggle.
        key_row = QWidget()
        kh = QHBoxLayout(key_row)
        kh.setContentsMargins(0, 0, 0, 0)
        kh.setSpacing(6)
        self.ed_key = QLineEdit()
        self.ed_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_key.setPlaceholderText("Paste API key")
        kh.addWidget(self.ed_key, 1)
        self.btn_reveal = QToolButton()
        self.btn_reveal.setText("SHOW")
        self.btn_reveal.setCheckable(True)
        self.btn_reveal.setMinimumHeight(30)
        self.btn_reveal.setStyleSheet(
            "QToolButton{background:#FFFFFF; color:#111111;"
            " border:2px solid #111111; padding:4px 10px; font-weight:800;"
            " letter-spacing:1px;}"
            "QToolButton:checked{background:#D6EE2C;}"
        )
        self.btn_reveal.toggled.connect(self._on_reveal_toggled)
        kh.addWidget(self.btn_reveal)
        form.addRow("API key", key_row)

        self.cb_model = QComboBox()
        form.addRow("Model", self.cb_model)

        self.lbl_hint = QLabel("")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("color:#555555; font-size:11px;")
        form.addRow("", self.lbl_hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        # Initial population — load `existing` if editing, else default
        # to the first provider in the enum.
        if existing is not None:
            for i in range(self.cb_provider.count()):
                if self.cb_provider.itemData(i) == existing.provider:
                    self.cb_provider.setCurrentIndex(i)
                    break
            self.ed_label.setText(existing.label)
            self.ed_key.setText(existing.key)
            self._populate_models(existing.provider, existing.model)
        else:
            self._on_provider_change(0)

    # ---- internal handlers -------------------------------------------

    def _on_provider_change(self, _idx: int) -> None:
        provider = self.cb_provider.currentData()
        # Keep the typed key when switching providers — usually the
        # user pastes the key *after* picking the provider, but if
        # they already pasted we don't want to wipe it.
        prev_model = (
            self._existing.model
            if self._existing is not None
            and self._existing.provider == provider
            else default_model_for(provider)
        )
        self._populate_models(provider, prev_model)

    def _populate_models(self, provider: ProviderName, current: str) -> None:
        self.cb_model.blockSignals(True)
        self.cb_model.clear()
        seen = set()
        for opt in models_for(provider):
            self.cb_model.addItem(opt.display(), opt.id)
            seen.add(opt.id)
        # If the saved model is no longer in the registry (e.g. the
        # user entered a custom one in a previous version), append
        # it so it remains selectable but flag the user clearly.
        if current and current not in seen:
            self.cb_model.addItem(f"{current} (custom)", current)
        # Default to recommended option when no current value.
        if current:
            for i in range(self.cb_model.count()):
                if self.cb_model.itemData(i) == current:
                    self.cb_model.setCurrentIndex(i)
                    break
        else:
            self.cb_model.setCurrentIndex(0)
        self.cb_model.blockSignals(False)

        if not is_supported(provider, current) and current:
            self.lbl_hint.setText(
                "This key was saved with a model that is no longer in the "
                "supported list. Pick a recommended option above."
            )
        else:
            self.lbl_hint.setText(
                "Pick from the supported model list — arbitrary names are not "
                "allowed because the provider HTTP wrapper would reject them."
            )

    def _on_reveal_toggled(self, on: bool) -> None:
        self.btn_reveal.setText("HIDE" if on else "SHOW")
        self.ed_key.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        )

    # ---- public API --------------------------------------------------

    def to_entry(self) -> KeyEntry:
        provider: ProviderName = self.cb_provider.currentData()
        model_id: str = self.cb_model.currentData()
        label = (self.ed_label.text() or "").strip() or f"{provider.value} key"
        key = (self.ed_key.text() or "").strip()
        return KeyEntry(
            provider=provider,
            label=label,
            key=key,
            model=model_id or default_model_for(provider),
            enabled=(
                self._existing.enabled
                if self._existing is not None else True
            ),
            priority=(
                self._existing.priority
                if self._existing is not None else 0
            ),
            status=(
                self._existing.status
                if self._existing is not None else KeyStatus.UNTESTED
            ),
        )


# ---------------------------------------------------------------------------
# Test-key worker
# ---------------------------------------------------------------------------

def _tiny_jpeg() -> bytes:
    if _tiny_jpeg.cache is None:  # type: ignore[attr-defined]
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", (1, 1), color=(255, 255, 255)).save(
            buf, format="JPEG", quality=70,
        )
        _tiny_jpeg.cache = buf.getvalue()  # type: ignore[attr-defined]
    return _tiny_jpeg.cache  # type: ignore[attr-defined]


_tiny_jpeg.cache = None  # type: ignore[attr-defined]


class _TestKeyWorker(QThread):
    finished_ok = Signal(str)
    finished_err = Signal(str, str)   # status_text, message

    def __init__(self, entry: KeyEntry, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._entry = entry

    def run(self) -> None:  # noqa: D401
        try:
            provider = provider_for(self._entry.provider)
        except KeyError:
            self.finished_err.emit("invalid", "Unknown provider")
            return
        img = ImageInput(data=_tiny_jpeg(), mime="image/jpeg")
        resp = provider.analyze(
            self._entry, img,
            "Reply with the JSON object {\"ok\": true} and nothing else.",
            timeout=20,
        )
        if resp.invalid_key:
            self.finished_err.emit("invalid", "Invalid API key")
        elif resp.rate_limited:
            self.finished_err.emit("rate_limited", "Rate limited / quota")
        elif resp.error:
            self.finished_err.emit("invalid", resp.error[:160])
        elif resp.raw_text:
            self.finished_ok.emit("OK")
        else:
            self.finished_err.emit("invalid", "Empty response")


# ---------------------------------------------------------------------------
# API key card
# ---------------------------------------------------------------------------

class ApiKeyCard(QFrame):
    """Single API-key entry rendered as a vertical card.

    Persistence model — every interactive control on the card calls
    back into ``KeyManager.*_and_save()`` so disk state matches the UI
    after every gesture. The Settings panel is the source of truth for
    indices, so the card emits :pyattr:`request_edit`,
    :pyattr:`request_delete`, :pyattr:`request_test` with no arguments
    and the panel resolves them against ``self._index``.
    """

    request_edit = Signal()
    request_delete = Signal()
    request_test = Signal()

    def __init__(
        self,
        index: int,
        entry: KeyEntry,
        km: KeyManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("api-key-card")
        self.setStyleSheet(
            "QFrame#api-key-card{"
            f" background:{theme.SURFACE};"
            f" border:2px solid {theme.INK};"
            "}"
        )
        self._index = index
        self._km = km
        self._entry = entry
        self._test_worker: Optional[_TestKeyWorker] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)

        # ── Row 1: provider badge · label · status pill ───────────
        head = QHBoxLayout()
        head.setSpacing(8)
        self.lbl_provider = QLabel(entry.provider.value.upper())
        self.lbl_provider.setObjectName("provider-badge")
        bg, fg = _PROVIDER_BADGE[entry.provider]
        self.lbl_provider.setStyleSheet(
            f"background:{bg}; color:{fg}; "
            f"border:2px solid {theme.INK}; padding:4px 10px; "
            "font-weight:900; letter-spacing:1.5px;"
        )
        head.addWidget(self.lbl_provider)

        self.lbl_label = QLabel(entry.label)
        f = self.lbl_label.font()
        f.setBold(True)
        f.setPointSize(max(f.pointSize() + 1, 12))
        self.lbl_label.setFont(f)
        self.lbl_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred,
        )
        head.addWidget(self.lbl_label, 1)

        self.lbl_status = QLabel(_STATUS_TEXT[entry.status])
        self.lbl_status.setMinimumWidth(110)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._restyle_status(entry.status)
        head.addWidget(self.lbl_status)
        outer.addLayout(head)

        # ── Row 2: masked key preview · model dropdown ────────────
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.lbl_key = QLabel(_mask_key(entry.key))
        self.lbl_key.setStyleSheet(
            "font-family:'JetBrains Mono', Consolas, monospace; "
            f"color:{theme.INK}; background:{theme.SURFACE_ALT}; "
            f"border:2px solid {theme.LINE_SOFT}; padding:6px 10px;"
        )
        self.lbl_key.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred,
        )
        row2.addWidget(self.lbl_key, 2)

        model_lbl = QLabel("MODEL")
        model_lbl.setStyleSheet(
            f"color:{theme.INK_SOFT}; letter-spacing:1px; font-weight:800;"
        )
        row2.addWidget(model_lbl)

        self.cb_model = QComboBox()
        self._populate_models()
        self.cb_model.currentIndexChanged.connect(self._on_model_changed)
        self.cb_model.setMinimumWidth(220)
        row2.addWidget(self.cb_model, 1)
        outer.addLayout(row2)

        # ── Row 3: enabled toggle + actions ───────────────────────
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        self.chk_enabled = QCheckBox("ENABLED")
        self.chk_enabled.setChecked(entry.enabled)
        self.chk_enabled.toggled.connect(self._on_enabled_toggled)
        row3.addWidget(self.chk_enabled)
        row3.addStretch(1)

        self.btn_test = QPushButton("TEST API")
        self.btn_test.clicked.connect(self.request_test.emit)
        row3.addWidget(self.btn_test)

        self.btn_edit = QPushButton("EDIT KEY")
        self.btn_edit.clicked.connect(self.request_edit.emit)
        row3.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("DELETE")
        self.btn_delete.setStyleSheet(
            "QPushButton{background:#FFFFFF; color:#111111;"
            " border:2px solid #FF3B30;}"
            "QPushButton:hover{background:#FF3B30; color:#FFFFFF;}"
        )
        self.btn_delete.clicked.connect(self.request_delete.emit)
        row3.addWidget(self.btn_delete)

        outer.addLayout(row3)

    # ---- public API used by the panel -------------------------------

    def index(self) -> int:
        return self._index

    def set_index(self, idx: int) -> None:
        self._index = idx

    def update_from(self, entry: KeyEntry) -> None:
        """Refresh visible state from a (possibly mutated) entry."""
        self._entry = entry
        self.lbl_label.setText(entry.label)
        self.lbl_provider.setText(entry.provider.value.upper())
        bg, fg = _PROVIDER_BADGE[entry.provider]
        self.lbl_provider.setStyleSheet(
            f"background:{bg}; color:{fg}; "
            f"border:2px solid {theme.INK}; padding:4px 10px; "
            "font-weight:900; letter-spacing:1.5px;"
        )
        self.lbl_key.setText(_mask_key(entry.key))
        self.chk_enabled.blockSignals(True)
        self.chk_enabled.setChecked(entry.enabled)
        self.chk_enabled.blockSignals(False)
        self._populate_models()
        self.set_status(entry.status)

    def set_status(self, status: KeyStatus) -> None:
        self._entry.status = status
        self.lbl_status.setText(_STATUS_TEXT[status])
        self._restyle_status(status)

    def set_busy(self, busy: bool, text: str = "") -> None:
        self.btn_test.setEnabled(not busy)
        self.btn_edit.setEnabled(not busy)
        self.btn_delete.setEnabled(not busy)
        if busy and text:
            self.lbl_status.setText(text)
            self.lbl_status.setStyleSheet(
                f"background:{theme.SURFACE_ALT}; color:{theme.INK}; "
                f"border:2px solid {theme.INK}; padding:4px 10px; "
                "font-weight:800; letter-spacing:1.5px;"
            )

    # ---- internal handlers ------------------------------------------

    def _populate_models(self) -> None:
        provider = self._entry.provider
        self.cb_model.blockSignals(True)
        self.cb_model.clear()
        seen = set()
        for opt in models_for(provider):
            self.cb_model.addItem(opt.display(), opt.id)
            seen.add(opt.id)
        current = self._entry.model
        if current and current not in seen:
            self.cb_model.addItem(f"{current} (custom)", current)
        for i in range(self.cb_model.count()):
            if self.cb_model.itemData(i) == current:
                self.cb_model.setCurrentIndex(i)
                break
        self.cb_model.blockSignals(False)

    def _on_model_changed(self, _idx: int) -> None:
        model_id: str = self.cb_model.currentData()
        if not model_id or model_id == self._entry.model:
            return
        self._entry.model = model_id
        self._km.set_model_and_save(self._index, model_id)

    def _on_enabled_toggled(self, on: bool) -> None:
        self._entry.enabled = on
        self._km.set_enabled_and_save(self._index, on)

    def _restyle_status(self, status: KeyStatus) -> None:
        bg, fg = _STATUS_COLORS[status]
        self.lbl_status.setStyleSheet(
            f"background:{bg}; color:{fg}; "
            f"border:2px solid {theme.INK}; padding:4px 10px; "
            "font-weight:800; letter-spacing:1.5px;"
        )

    # ---- prevent accidental edits -----------------------------------
    #
    # The previous table-based editor would commit edits when the user
    # clicked into a cell; the new card is read-only at the surface and
    # only opens the edit dialog when the user explicitly hits the
    # "EDIT KEY" button. We swallow double-clicks so they don't bubble
    # to anything that could be construed as an edit affordance.

    def mouseDoubleClickEvent(self, event):  # type: ignore[override]
        event.ignore()


# ---------------------------------------------------------------------------
# Settings panel (the page itself)
# ---------------------------------------------------------------------------

class SettingsPanel(QWidget):
    """Top-level Settings page added as the third rail mode."""

    keys_changed = Signal()

    def __init__(
        self,
        key_manager: KeyManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._km = key_manager
        self._cards: list[ApiKeyCard] = []
        self._build()
        self._reload_cards()
        # Refresh the cards whenever something else mutates the
        # KeyManager (e.g. a key fails over during a run and the
        # status pill needs to flip).
        self._km.add_listener(self._on_keys_changed_external)

    # ---- build UI ----------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(12)

        # Title block.
        title = QLabel("SETTINGS")
        f = title.font()
        f.setBold(True)
        f.setPointSize(max(f.pointSize() + 6, 18))
        title.setFont(f)
        title.setStyleSheet(
            f"color:{theme.INK}; letter-spacing:3px;"
        )
        outer.addWidget(title)

        sub = QLabel(
            "API keys, providers, and models for the AI Anatomy Inspector."
        )
        sub.setStyleSheet(f"color:{theme.INK_SOFT}; font-size:12px;")
        outer.addWidget(sub)

        # Warning banner — same wording as the legacy dialog so users
        # who saw it before still recognise it.
        warn = QLabel(
            "API keys are stored in plain JSON inside your user data folder. "
            "This is intended for local use only — for production, use a "
            "secure backend."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(
            "color:#3A2200; background:#FFF4D6; "
            f"border:2px solid {theme.INK}; padding:8px 10px; "
            "font-weight:600;"
        )
        outer.addWidget(warn)

        # Section header + add button.
        head = QHBoxLayout()
        head.setSpacing(8)
        sec_title = QLabel("API KEYS")
        sec_title.setStyleSheet(
            f"background:{theme.INK}; color:{theme.SURFACE}; "
            "padding:6px 12px; letter-spacing:2px; font-weight:900;"
        )
        head.addWidget(sec_title)

        self.lbl_count = QLabel(self._count_text())
        self.lbl_count.setStyleSheet(
            f"color:{theme.INK_SOFT}; font-size:11px; padding-left:8px;"
        )
        head.addWidget(self.lbl_count)

        head.addStretch(1)

        self.btn_add = QPushButton("+  ADD API KEY")
        self.btn_add.setObjectName("brutal-primary")
        self.btn_add.setMinimumHeight(36)
        self.btn_add.clicked.connect(self._on_add)
        head.addWidget(self.btn_add)
        outer.addLayout(head)

        # Scroll area with stacked cards + empty state.
        self._stack_host = QFrame()
        self._stack = QStackedLayout(self._stack_host)
        self._stack.setContentsMargins(0, 0, 0, 0)

        # Page 1 — scroll area with the cards inside.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea{{background:{theme.BG}; border:0;}}"
        )
        self._cards_host = QWidget()
        self._cards_host.setStyleSheet(f"background:{theme.BG};")
        self._cards_layout = QVBoxLayout(self._cards_host)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(10)
        self._cards_layout.addStretch(1)
        self._scroll.setWidget(self._cards_host)
        self._stack.addWidget(self._scroll)

        # Page 2 — empty state.
        empty = EmptyState(
            title="NO API KEYS YET",
            body=(
                "Add a Gemini, OpenAI, or Groq API key to unlock the AI "
                "Anatomy Inspector. Click + ADD API KEY above to get started."
            ),
        )
        self._stack.addWidget(empty)

        outer.addWidget(self._stack_host, 1)

    def _count_text(self) -> str:
        return f"{self._km.count()} / {MAX_KEYS} keys"

    # ---- card lifecycle ---------------------------------------------

    def _reload_cards(self) -> None:
        # Wipe old cards.
        for c in self._cards:
            self._cards_layout.removeWidget(c)
            c.setParent(None)
            c.deleteLater()
        self._cards.clear()

        for i, entry in enumerate(self._km.all()):
            card = self._build_card(i, entry)
            # Insert above the trailing stretch.
            self._cards_layout.insertWidget(
                self._cards_layout.count() - 1, card,
            )
            self._cards.append(card)

        self.lbl_count.setText(self._count_text())
        # Toggle empty state.
        self._stack.setCurrentIndex(0 if self._cards else 1)

    def _build_card(self, index: int, entry: KeyEntry) -> ApiKeyCard:
        card = ApiKeyCard(index, entry, self._km, self)
        card.request_edit.connect(lambda c=card: self._on_edit(c))
        card.request_delete.connect(lambda c=card: self._on_delete(c))
        card.request_test.connect(lambda c=card: self._on_test(c))
        return card

    def _on_keys_changed_external(self) -> None:
        # The KeyManager fires ``add_listener`` callbacks on whatever
        # thread did the save — in our flows that's always the GUI
        # thread, but we still emit the public ``keys_changed`` signal
        # using direct connections so listeners (e.g. the AI Inspector
        # tab) refresh without polling.
        self.keys_changed.emit()

    # ---- handlers ----------------------------------------------------

    def _on_add(self) -> None:
        if self._km.count() >= MAX_KEYS:
            QMessageBox.warning(
                self, "Limit reached",
                f"Already at {MAX_KEYS} keys. Delete one before adding another.",
            )
            return
        dlg = ApiKeyDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        entry = dlg.to_entry()
        if not entry.key:
            QMessageBox.warning(
                self, "Empty key",
                "API key was empty — nothing was added.",
            )
            return
        self._km.add_and_save(entry)
        self._reload_cards()
        self.keys_changed.emit()

    def _on_edit(self, card: ApiKeyCard) -> None:
        idx = card.index()
        existing = self._km.all()
        if not (0 <= idx < len(existing)):
            return
        dlg = ApiKeyDialog(existing[idx], parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_entry = dlg.to_entry()
        if not new_entry.key:
            QMessageBox.warning(
                self, "Empty key",
                "API key was empty — edit was discarded.",
            )
            return
        self._km.update_and_save(idx, new_entry)
        self._reload_cards()
        self.keys_changed.emit()

    def _on_delete(self, card: ApiKeyCard) -> None:
        idx = card.index()
        existing = self._km.all()
        if not (0 <= idx < len(existing)):
            return
        target = existing[idx]
        confirm = QMessageBox.question(
            self, "Delete API key",
            f"Delete API key '{target.label}' ({target.provider.value})?\n"
            f"This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._km.remove_and_save(idx)
        self._reload_cards()
        self.keys_changed.emit()

    def _on_test(self, card: ApiKeyCard) -> None:
        idx = card.index()
        existing = self._km.all()
        if not (0 <= idx < len(existing)):
            return
        entry = existing[idx]
        if not entry.key:
            QMessageBox.warning(self, "Empty key", "Add the API key first.")
            return

        card.set_busy(True, "testing…")
        worker = _TestKeyWorker(entry, parent=card)
        card._test_worker = worker  # noqa: SLF001 — keep reference alive

        def _finished_ok(_msg: str) -> None:
            card.set_busy(False)
            self._km.set_status_and_save(idx, KeyStatus.ACTIVE)
            card.set_status(KeyStatus.ACTIVE)
            self.keys_changed.emit()

        def _finished_err(status_text: str, msg: str) -> None:
            card.set_busy(False)
            mapped = (
                KeyStatus.RATE_LIMITED
                if status_text == "rate_limited"
                else KeyStatus.FAILED
            )
            self._km.set_status_and_save(idx, mapped, msg)
            card.set_status(mapped)
            QMessageBox.warning(self, "Test failed", msg)
            self.keys_changed.emit()

        worker.finished_ok.connect(_finished_ok)
        worker.finished_err.connect(_finished_err)
        worker.start()


__all__ = ["SettingsPanel", "ApiKeyCard", "ApiKeyDialog", "settings_icon"]
