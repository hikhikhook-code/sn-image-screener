"""Settings → AI Keys management dialog.

Supports up to 20 API keys across Gemini / OpenAI / Groq. Each row has:

    provider · label · key · model · enabled · priority · status · test · delete

Reorder by priority via Up/Down buttons. The dialog persists changes
back to the :class:`KeyManager` JSON file on Save.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...services.ai import KeyManager, MAX_KEYS
from ...services.ai.providers import provider_for
from ...services.ai.types import (
    ImageInput, KeyEntry, KeyStatus, ProviderName,
)


def _tiny_jpeg() -> bytes:
    """A 1×1 white JPEG used by the "Test key" button.

    Built with PIL at first call (cached) so we never carry a hand-typed
    hex blob in the source. Small enough that every provider returns
    quickly even on the cheapest model. The model may complain about
    resolution, but a 200/401/429 response still tells us whether the
    key works.
    """
    if _tiny_jpeg.cache is None:  # type: ignore[attr-defined]
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", (1, 1), color=(255, 255, 255)).save(
            buf, format="JPEG", quality=70,
        )
        _tiny_jpeg.cache = buf.getvalue()  # type: ignore[attr-defined]
    return _tiny_jpeg.cache  # type: ignore[attr-defined,return-value]


_tiny_jpeg.cache = None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Background test-key worker
# ---------------------------------------------------------------------------

class _TestKeyWorker(QThread):
    finished_ok = Signal(int, str)        # row, message
    finished_err = Signal(int, str)       # row, message

    def __init__(self, row: int, key: KeyEntry) -> None:
        super().__init__()
        self.row = row
        self.key = key

    def run(self) -> None:  # noqa: D401
        provider = provider_for(self.key.provider)
        img = ImageInput(data=_tiny_jpeg(), mime="image/jpeg")
        resp = provider.analyze(
            self.key, img,
            "Reply with the JSON object {\"ok\": true} and nothing else.",
            timeout=20,
        )
        if resp.invalid_key:
            self.finished_err.emit(self.row, "Invalid key")
        elif resp.rate_limited:
            self.finished_err.emit(self.row, "Rate limited / quota")
        elif resp.error:
            self.finished_err.emit(self.row, resp.error[:120])
        elif resp.raw_text:
            self.finished_ok.emit(self.row, "OK")
        else:
            self.finished_err.emit(self.row, "Empty response")


# ---------------------------------------------------------------------------
# Add-key sub-dialog
# ---------------------------------------------------------------------------

class AddKeyDialog(QDialog):
    DEFAULT_MODELS = {
        ProviderName.GEMINI: "gemini-1.5-flash",
        ProviderName.OPENAI: "gpt-4o-mini",
        ProviderName.GROQ: "llama-3.2-11b-vision-preview",
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add API Key")
        self.setMinimumWidth(440)

        form = QFormLayout(self)

        self.cb_provider = QComboBox()
        for p in ProviderName:
            self.cb_provider.addItem(p.value.title(), p)
        self.cb_provider.currentIndexChanged.connect(self._on_provider_change)
        form.addRow("Provider", self.cb_provider)

        self.ed_label = QLineEdit()
        self.ed_label.setPlaceholderText("e.g. Personal — gemini #1")
        form.addRow("Label", self.ed_label)

        self.ed_key = QLineEdit()
        self.ed_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_key.setPlaceholderText("Paste API key")
        form.addRow("API key", self.ed_key)

        self.ed_model = QLineEdit()
        form.addRow("Model name", self.ed_model)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self._on_provider_change(0)

    def _on_provider_change(self, _idx: int) -> None:
        provider = self.cb_provider.currentData()
        self.ed_model.setText(self.DEFAULT_MODELS[provider])
        self.ed_model.setPlaceholderText(self.DEFAULT_MODELS[provider])

    def entry(self) -> KeyEntry:
        provider: ProviderName = self.cb_provider.currentData()
        return KeyEntry(
            provider=provider,
            label=self.ed_label.text().strip() or f"{provider.value} key",
            key=self.ed_key.text().strip(),
            model=self.ed_model.text().strip()
                  or self.DEFAULT_MODELS[provider],
            enabled=True,
            priority=0,
            status=KeyStatus.UNTESTED,
        )


# ---------------------------------------------------------------------------
# Main settings dialog
# ---------------------------------------------------------------------------

class KeySettingsDialog(QDialog):
    """Manage API keys for the AI Anatomy Inspector."""

    COL_PROVIDER, COL_LABEL, COL_KEY, COL_MODEL, COL_ENABLED, \
        COL_STATUS, COL_TEST, COL_DEL, NCOLS = range(9)

    def __init__(self, key_manager: KeyManager,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Anatomy — API Keys")
        self.resize(880, 480)
        self.km = key_manager
        self._workers: list[_TestKeyWorker] = []

        root = QVBoxLayout(self)

        # Header / warning -------------------------------------------------
        header = QLabel(
            "<b>API Keys</b><br>"
            f"Up to {MAX_KEYS} keys across Gemini, OpenAI, and Groq. "
            "Keys are tried in priority order; failed or rate-limited keys "
            "automatically fall over to the next enabled key."
        )
        header.setWordWrap(True)
        root.addWidget(header)

        warn = QLabel(
            "API keys saved in browser storage are for local testing only. "
            "For production, use a secure backend."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(
            "color:#3A2200; background:#FFF4D6; "
            "border:2px solid #111111; padding:6px;"
        )
        root.addWidget(warn)

        # Toolbar ----------------------------------------------------------
        bar = QHBoxLayout()
        self.btn_add = QPushButton("+ ADD KEY")
        self.btn_add.clicked.connect(self._on_add)
        bar.addWidget(self.btn_add)

        self.btn_up = QPushButton("MOVE UP")
        self.btn_up.clicked.connect(self._on_up)
        bar.addWidget(self.btn_up)

        self.btn_down = QPushButton("MOVE DOWN")
        self.btn_down.clicked.connect(self._on_down)
        bar.addWidget(self.btn_down)
        bar.addStretch(1)

        self.lbl_count = QLabel()
        bar.addWidget(self.lbl_count)
        root.addLayout(bar)

        # Table ------------------------------------------------------------
        self.table = QTableWidget(0, self.NCOLS)
        self.table.setHorizontalHeaderLabels([
            "Provider", "Label", "API Key", "Model",
            "Enabled", "Status", "Test", "",
        ])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(self.COL_LABEL, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(self.COL_KEY, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(self.COL_MODEL, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked |
            QTableWidget.EditTrigger.SelectedClicked
        )
        self.table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self.table, 1)

        # Footer -----------------------------------------------------------
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._reload()

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _reload(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for entry in self.km.all():
            self._append_row(entry)
        self.table.blockSignals(False)
        self.lbl_count.setText(f"{self.km.count()} / {MAX_KEYS} keys")

    def _append_row(self, entry: KeyEntry) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Provider — read-only
        prov = QTableWidgetItem(entry.provider.value.title())
        prov.setFlags(prov.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, self.COL_PROVIDER, prov)

        self.table.setItem(row, self.COL_LABEL, QTableWidgetItem(entry.label))
        # Mask the key in the visible cell.
        key_cell = QTableWidgetItem(_mask(entry.key))
        key_cell.setData(Qt.ItemDataRole.UserRole, entry.key)
        self.table.setItem(row, self.COL_KEY, key_cell)
        self.table.setItem(row, self.COL_MODEL, QTableWidgetItem(entry.model))

        # Enabled toggle
        chk = QCheckBox()
        chk.setChecked(entry.enabled)
        chk.stateChanged.connect(lambda _: self._set_dirty())
        wrap = _centered(chk)
        self.table.setCellWidget(row, self.COL_ENABLED, wrap)

        # Status
        status_item = QTableWidgetItem(entry.status.value)
        _style_status(status_item, entry.status)
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, self.COL_STATUS, status_item)

        # Test button
        btn_test = QPushButton("Test")
        btn_test.clicked.connect(lambda _=False, r=row: self._on_test(r))
        self.table.setCellWidget(row, self.COL_TEST, btn_test)

        # Delete button
        btn_del = QPushButton("✕")
        btn_del.setToolTip("Remove this key")
        btn_del.clicked.connect(lambda _=False, r=row: self._on_delete(r))
        self.table.setCellWidget(row, self.COL_DEL, btn_del)

    def _set_dirty(self) -> None:
        # No explicit dirty flag — _on_save reconstructs from rows directly.
        pass

    def _row_to_entry(self, row: int) -> KeyEntry:
        provider_text = self.table.item(row, self.COL_PROVIDER).text().lower()
        provider = ProviderName(provider_text)
        label = (self.table.item(row, self.COL_LABEL).text() or "").strip()
        key_item = self.table.item(row, self.COL_KEY)
        # If the cell still shows the masked value, recover the original
        # from UserRole data; if the user edited it the visible text
        # IS the new value.
        if key_item.text() == _mask(key_item.data(Qt.ItemDataRole.UserRole) or ""):
            key = key_item.data(Qt.ItemDataRole.UserRole) or ""
        else:
            key = key_item.text().strip()
        model = self.table.item(row, self.COL_MODEL).text().strip()
        chk = self.table.cellWidget(row, self.COL_ENABLED).findChild(QCheckBox)
        enabled = chk.isChecked() if chk else True
        status_text = self.table.item(row, self.COL_STATUS).text()
        try:
            status = KeyStatus(status_text)
        except ValueError:
            status = KeyStatus.UNTESTED
        return KeyEntry(
            provider=provider, label=label, key=key, model=model,
            enabled=enabled, priority=row, status=status,
        )

    def _on_save(self) -> None:
        new_keys: list[KeyEntry] = []
        for row in range(self.table.rowCount()):
            entry = self._row_to_entry(row)
            if not entry.key:
                QMessageBox.warning(
                    self, "Empty key",
                    f"Row {row + 1}: API key is empty. Fill it in or delete the row.",
                )
                return
            new_keys.append(entry)

        # Replace KeyManager state in one shot.
        # We rebuild instead of mutating so priority renumbering is clean.
        self.km._keys = []  # noqa: SLF001 — internal rebuild on save
        for k in new_keys:
            self.km._keys.append(k)
        self.km._sort_in_place()  # noqa: SLF001
        self.km.save()
        self.accept()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_item_changed(self, _item: QTableWidgetItem) -> None:
        # No-op for now; saving rebuilds from rows.
        pass

    def _on_add(self) -> None:
        if self.table.rowCount() >= MAX_KEYS:
            QMessageBox.warning(
                self, "Limit reached",
                f"Already at {MAX_KEYS} keys. Delete one before adding another.",
            )
            return
        dlg = AddKeyDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        entry = dlg.entry()
        if not entry.key:
            return
        self._append_row(entry)
        self.lbl_count.setText(f"{self.table.rowCount()} / {MAX_KEYS} keys")

    def _on_delete(self, row: int) -> None:
        self.table.removeRow(row)
        self.lbl_count.setText(f"{self.table.rowCount()} / {MAX_KEYS} keys")

    def _on_up(self) -> None:
        row = self.table.currentRow()
        if row > 0:
            self._swap_rows(row, row - 1)
            self.table.setCurrentCell(row - 1, 0)

    def _on_down(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < self.table.rowCount() - 1:
            self._swap_rows(row, row + 1)
            self.table.setCurrentCell(row + 1, 0)

    def _swap_rows(self, a: int, b: int) -> None:
        ea = self._row_to_entry(a)
        eb = self._row_to_entry(b)
        self.table.removeRow(max(a, b))
        self.table.removeRow(min(a, b))
        # Re-insert in swapped order.
        if a < b:
            self._append_row(eb)
            self._append_row(ea)
        else:
            self._append_row(ea)
            self._append_row(eb)

    def _on_test(self, row: int) -> None:
        entry = self._row_to_entry(row)
        if not entry.key:
            QMessageBox.warning(self, "Empty key", "Enter the API key first.")
            return
        self.table.item(row, self.COL_STATUS).setText("testing…")
        worker = _TestKeyWorker(row, entry)
        worker.finished_ok.connect(self._on_test_ok)
        worker.finished_err.connect(self._on_test_err)
        worker.finished.connect(lambda: self._workers.remove(worker)
                                if worker in self._workers else None)
        self._workers.append(worker)
        worker.start()

    def _on_test_ok(self, row: int, _msg: str) -> None:
        item = self.table.item(row, self.COL_STATUS)
        item.setText("active")
        _style_status(item, KeyStatus.ACTIVE)

    def _on_test_err(self, row: int, msg: str) -> None:
        item = self.table.item(row, self.COL_STATUS)
        if "Invalid" in msg:
            status = KeyStatus.FAILED
            text = "failed"
        elif "Rate limited" in msg or "quota" in msg.lower():
            status = KeyStatus.RATE_LIMITED
            text = "rate_limited"
        else:
            status = KeyStatus.FAILED
            text = "failed"
        item.setText(text)
        item.setToolTip(msg)
        _style_status(item, status)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}{'•' * (len(key) - 8)}{key[-4:]}"


def _centered(widget: QWidget) -> QWidget:
    holder = QWidget()
    lay = QHBoxLayout(holder)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addStretch(1)
    lay.addWidget(widget)
    lay.addStretch(1)
    return holder


def _style_status(item: QTableWidgetItem, status: KeyStatus) -> None:
    palette = {
        KeyStatus.UNTESTED:    ("#EEEEEE", "#111111"),
        KeyStatus.ACTIVE:      ("#6FE34D", "#0B2D00"),
        KeyStatus.FAILED:      ("#FF3B30", "#FFFFFF"),
        KeyStatus.RATE_LIMITED: ("#FFB627", "#3A2200"),
        KeyStatus.EXHAUSTED:   ("#111111", "#FFC700"),
    }
    bg, fg = palette[status]
    item.setBackground(QColor(bg))
    item.setForeground(QColor(fg))
