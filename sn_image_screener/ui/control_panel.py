"""Left control panel: Source / Preset / Quality Rules / Output / Advanced.

The panel is wrapped in a QScrollArea so it scrolls independently when
content is taller than the window.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from . import theme
from .widgets import CollapsibleGroup, label
from ..core.presets import PRESETS, Rules, with_overrides


def _spinbox(value: int, lo: int = 0, hi: int = 99999) -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(int(value))
    s.setButtonSymbols(QSpinBox.PlusMinus)
    return s


def _dspinbox(value: float, lo: float = 0.0, hi: float = 99999.0, step: float = 1.0, decimals: int = 1) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setDecimals(decimals)
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setValue(float(value))
    s.setButtonSymbols(QDoubleSpinBox.PlusMinus)
    return s


class ControlPanel(QFrame):
    """Left side panel — scrollable settings on top, sticky START SCAN at the bottom."""

    add_folder_clicked = Signal()
    add_files_clicked  = Signal()
    clear_sources_clicked = Signal()
    start_clicked      = Signal()
    output_changed     = Signal(str)
    rules_changed      = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumWidth(310)
        self.setMaximumWidth(440)
        self.setObjectName("control-panel-root")

        # Outer layout: scroll area (top) + sticky START SCAN block (bottom)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("control-scroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(self.scroll, 1)

        host = QWidget()
        host.setObjectName("root")
        self.scroll.setWidget(host)

        layout = QVBoxLayout(host)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # --- Source -------------------------------------------------------
        self.grp_source = CollapsibleGroup("Source", expanded=True)
        layout.addWidget(self.grp_source)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_add_folder = QPushButton("+ FOLDER")
        self.btn_add_folder.setObjectName("brutal-primary")
        self.btn_add_folder.clicked.connect(self.add_folder_clicked.emit)
        btn_row.addWidget(self.btn_add_folder)

        self.btn_add_files = QPushButton("+ FILES")
        self.btn_add_files.setObjectName("brutal-secondary")
        self.btn_add_files.clicked.connect(self.add_files_clicked.emit)
        btn_row.addWidget(self.btn_add_files)
        self.grp_source.add_layout(btn_row)

        self.lst_sources = QListWidget()
        self.lst_sources.setStyleSheet(
            f"background:{theme.SURFACE};"
            f"border:2px solid {theme.INK};"
            f"font-family:'JetBrains Mono', Consolas, monospace; font-size:11px;"
        )
        self.lst_sources.setMinimumHeight(90)
        self.grp_source.add(self.lst_sources)

        self.lbl_source_count = label("— no sources added —", soft=True, size=10)
        self.grp_source.add(self.lbl_source_count)

        clr_row = QHBoxLayout()
        self.btn_clear_sources = QPushButton("CLEAR SOURCES")
        self.btn_clear_sources.setObjectName("brutal-ghost")
        self.btn_clear_sources.clicked.connect(self.clear_sources_clicked.emit)
        clr_row.addWidget(self.btn_clear_sources)
        clr_row.addStretch(1)
        self.grp_source.add_layout(clr_row)

        # --- Preset -------------------------------------------------------
        self.grp_preset = CollapsibleGroup("Preset", expanded=True)
        layout.addWidget(self.grp_preset)

        self.cmb_preset = QComboBox()
        for name in PRESETS:
            self.cmb_preset.addItem(name)
        self.cmb_preset.setCurrentText("Normal")
        self.cmb_preset.currentTextChanged.connect(self._on_preset_changed)
        self.grp_preset.add(self.cmb_preset)

        self.lbl_preset_help = label(
            "Stock Strict — submission grade   ·   Normal — general culling   ·   Loose — minimum bar",
            soft=True, size=10,
        )
        self.lbl_preset_help.setWordWrap(True)
        self.grp_preset.add(self.lbl_preset_help)

        # --- Quality rules (read-only summary, editable via Advanced) -----
        self.grp_rules = CollapsibleGroup("Quality Rules", expanded=True)
        layout.addWidget(self.grp_rules)

        rules_form = QFormLayout()
        rules_form.setSpacing(6)
        rules_form.setLabelAlignment(Qt.AlignLeft)
        rules_form.setFormAlignment(Qt.AlignTop)

        self.chk_blur     = QCheckBox("Blur");     self.chk_blur.setChecked(True)
        self.chk_noise    = QCheckBox("Noise");    self.chk_noise.setChecked(True)
        self.chk_exposure = QCheckBox("Exposure"); self.chk_exposure.setChecked(True)
        self.chk_artifact = QCheckBox("JPEG Artifact"); self.chk_artifact.setChecked(True)
        self.chk_filesize = QCheckBox("File size gate"); self.chk_filesize.setChecked(True)
        self.chk_dimension = QCheckBox("Resolution gate"); self.chk_dimension.setChecked(True)

        for cb in (self.chk_blur, self.chk_noise, self.chk_exposure,
                   self.chk_artifact, self.chk_filesize, self.chk_dimension):
            cb.toggled.connect(self.rules_changed.emit)

        toggles = QVBoxLayout()
        toggles.setSpacing(6)
        for cb in (self.chk_blur, self.chk_noise, self.chk_exposure,
                   self.chk_artifact, self.chk_filesize, self.chk_dimension):
            toggles.addWidget(cb)
        self.grp_rules.add_layout(toggles)

        # --- Output -------------------------------------------------------
        self.grp_output = CollapsibleGroup("Output", expanded=True)
        layout.addWidget(self.grp_output)

        out_row = QHBoxLayout()
        self.ed_output = QLineEdit()
        self.ed_output.setPlaceholderText("Choose export folder…")
        self.ed_output.textChanged.connect(self.output_changed.emit)
        out_row.addWidget(self.ed_output, 1)

        self.btn_choose_output = QPushButton("…")
        self.btn_choose_output.clicked.connect(self._choose_output)
        out_row.addWidget(self.btn_choose_output)
        self.grp_output.add_layout(out_row)

        self.chk_copy_pass = QCheckBox("Copy PASS files on export"); self.chk_copy_pass.setChecked(True)
        self.chk_copy_review = QCheckBox("Copy REVIEW files on export")
        self.chk_export_csv = QCheckBox("Write CSV report"); self.chk_export_csv.setChecked(True)
        self.chk_export_json = QCheckBox("Write JSON report")
        for cb in (self.chk_copy_pass, self.chk_copy_review,
                   self.chk_export_csv, self.chk_export_json):
            self.grp_output.add(cb)

        # --- Advanced (collapsed) ----------------------------------------
        self.grp_advanced = CollapsibleGroup("Advanced", expanded=False)
        layout.addWidget(self.grp_advanced)

        self.sp_min_kb = _dspinbox(30, 0, 99999, 5, decimals=1)
        self.sp_min_w  = _spinbox(1024, 1, 99999)
        self.sp_min_h  = _spinbox(1024, 1, 99999)
        self.sp_blur_reject = _dspinbox(60, 0, 99999, 5, decimals=1)
        self.sp_blur_review = _dspinbox(120, 0, 99999, 5, decimals=1)
        self.sp_noise_reject = _dspinbox(28, 0, 999, 1, decimals=1)
        self.sp_noise_review = _dspinbox(18, 0, 999, 1, decimals=1)
        self.sp_artifact_reject = _dspinbox(14, 0, 999, 1, decimals=1)
        self.sp_artifact_review = _dspinbox(9,  0, 999, 1, decimals=1)
        self.sp_exp_min = _dspinbox(35,  0, 255, 5, decimals=1)
        self.sp_exp_max = _dspinbox(225, 0, 255, 5, decimals=1)

        adv_form = QFormLayout()
        adv_form.setSpacing(6)
        adv_form.setLabelAlignment(Qt.AlignLeft)
        adv_form.addRow("Min file size (KB)", self.sp_min_kb)
        adv_form.addRow("Min width (px)",     self.sp_min_w)
        adv_form.addRow("Min height (px)",    self.sp_min_h)
        adv_form.addRow("Blur reject below",  self.sp_blur_reject)
        adv_form.addRow("Blur review below",  self.sp_blur_review)
        adv_form.addRow("Noise reject above", self.sp_noise_reject)
        adv_form.addRow("Noise review above", self.sp_noise_review)
        adv_form.addRow("JPG artifact reject", self.sp_artifact_reject)
        adv_form.addRow("JPG artifact review", self.sp_artifact_review)
        adv_form.addRow("Exposure min (mean)", self.sp_exp_min)
        adv_form.addRow("Exposure max (mean)", self.sp_exp_max)
        for spin in (self.sp_min_kb, self.sp_min_w, self.sp_min_h,
                     self.sp_blur_reject, self.sp_blur_review,
                     self.sp_noise_reject, self.sp_noise_review,
                     self.sp_artifact_reject, self.sp_artifact_review,
                     self.sp_exp_min, self.sp_exp_max):
            spin.valueChanged.connect(self.rules_changed.emit)
        self.grp_advanced.add_layout(adv_form)

        layout.addStretch(1)

        # --- Sticky bottom block (OUTSIDE the scroll area) --------------
        sticky = QFrame()
        sticky.setObjectName("control-sticky")
        sticky_lay = QVBoxLayout(sticky)
        sticky_lay.setContentsMargins(14, 10, 14, 14)
        sticky_lay.setSpacing(6)

        self.btn_start = QPushButton("▶  START SCAN")
        self.btn_start.setObjectName("brutal-primary")
        self.btn_start.setMinimumHeight(54)
        f = self.btn_start.font()
        f.setPointSize(14)
        f.setBold(True)
        f.setLetterSpacing(f.SpacingType.AbsoluteSpacing, 1.2)
        self.btn_start.setFont(f)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self.start_clicked.emit)
        sticky_lay.addWidget(self.btn_start)

        sticky_hint = QLabel("↑  scroll for advanced settings")
        sticky_hint.setObjectName("scroll-hint")
        sticky_hint.setAlignment(Qt.AlignCenter)
        sticky_lay.addWidget(sticky_hint)

        outer.addWidget(sticky, 0)

        # Apply default preset to spinboxes.
        self._on_preset_changed("Normal")
        self.update_source_summary([], [])

    # ----------------------------------------------------------------- API

    def update_source_summary(self, folders: List[Path], files: List[Path]) -> None:
        self.lst_sources.clear()
        for d in folders:
            self.lst_sources.addItem(f"📁  {d}")
        for f in files:
            self.lst_sources.addItem(f"🖼  {f.name}")

        n = len(folders) + len(files)
        if n == 0:
            self.lbl_source_count.setText("— no sources added —")
            self.btn_start.setEnabled(False)
            self.btn_start.setText("▶  ADD A FOLDER FIRST")
        else:
            self.lbl_source_count.setText(
                f"{len(folders)} folder(s)  ·  {len(files)} loose file(s)"
            )
            self.btn_start.setEnabled(True)
            self.btn_start.setText("▶  START SCAN")

    def current_rules(self) -> Rules:
        base = PRESETS.get(self.cmb_preset.currentText(), PRESETS["Normal"])
        rules = with_overrides(
            base,
            min_file_kb     = float(self.sp_min_kb.value()),
            min_width       = int(self.sp_min_w.value()),
            min_height      = int(self.sp_min_h.value()),
            blur_reject     = float(self.sp_blur_reject.value()),
            blur_review     = float(self.sp_blur_review.value()),
            noise_reject    = float(self.sp_noise_reject.value()),
            noise_review    = float(self.sp_noise_review.value()),
            artifact_reject = float(self.sp_artifact_reject.value()),
            artifact_review = float(self.sp_artifact_review.value()),
            exposure_mean_min = float(self.sp_exp_min.value()),
            exposure_mean_max = float(self.sp_exp_max.value()),
        )

        # Honour the per-check toggles by relaxing thresholds when off.
        if not self.chk_blur.isChecked():
            rules = replace(rules, blur_reject=0.0, blur_review=0.0)
        if not self.chk_noise.isChecked():
            rules = replace(rules, noise_reject=1e9, noise_review=1e9)
        if not self.chk_exposure.isChecked():
            rules = replace(rules,
                exposure_mean_min=0.0, exposure_mean_max=255.0,
                exposure_review_low=0.0, exposure_review_high=255.0,
                clip_low_reject=1.0, clip_high_reject=1.0,
                clip_low_review=1.0, clip_high_review=1.0,
                dynamic_range_review=0.0,
            )
        if not self.chk_artifact.isChecked():
            rules = replace(rules, artifact_reject=1e9, artifact_review=1e9)
        if not self.chk_filesize.isChecked():
            rules = replace(rules, min_file_kb=0.0)
        if not self.chk_dimension.isChecked():
            rules = replace(rules, min_width=1, min_height=1)
        return rules

    def output_dir(self) -> Optional[Path]:
        text = self.ed_output.text().strip()
        return Path(text) if text else None

    # ------------------------------------------------------------ private

    def _on_preset_changed(self, name: str) -> None:
        rules = PRESETS.get(name, PRESETS["Normal"])
        # Block signals so we don't fire 11 changes
        widgets = [
            self.sp_min_kb, self.sp_min_w, self.sp_min_h,
            self.sp_blur_reject, self.sp_blur_review,
            self.sp_noise_reject, self.sp_noise_review,
            self.sp_artifact_reject, self.sp_artifact_review,
            self.sp_exp_min, self.sp_exp_max,
        ]
        for w in widgets:
            w.blockSignals(True)
        self.sp_min_kb.setValue(rules.min_file_kb)
        self.sp_min_w.setValue(rules.min_width)
        self.sp_min_h.setValue(rules.min_height)
        self.sp_blur_reject.setValue(rules.blur_reject)
        self.sp_blur_review.setValue(rules.blur_review)
        self.sp_noise_reject.setValue(rules.noise_reject)
        self.sp_noise_review.setValue(rules.noise_review)
        self.sp_artifact_reject.setValue(rules.artifact_reject)
        self.sp_artifact_review.setValue(rules.artifact_review)
        self.sp_exp_min.setValue(rules.exposure_mean_min)
        self.sp_exp_max.setValue(rules.exposure_mean_max)
        for w in widgets:
            w.blockSignals(False)
        self.rules_changed.emit()

    def _choose_output(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose export folder")
        if d:
            self.ed_output.setText(d)
