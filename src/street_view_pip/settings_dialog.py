# -*- coding: utf-8 -*-
"""
Settings Dialog for Street View Navigator (PiP).

100% English default with optional Turkish UI toggle, supporting Google Direct
(Zero-Key WebView2), Google Maps JS API (optional user key), and Panoramax.
"""

from dataclasses import dataclass
from typing import Optional

from qgis.PyQt import QtWidgets
from qgis.core import QgsSettings

from .i18n import tr_text
from .qt_compat import CURSOR_POINTING_HAND


@dataclass
class PluginConfig:
    provider: str = "google_direct"
    api_key: str = ""
    auto_coverage: bool = True
    snap_road: bool = True
    follow_pegman: bool = True
    clean_mode: bool = True
    default_preset: str = "M"
    language: str = "en"

    @classmethod
    def load(cls) -> "PluginConfig":
        s = QgsSettings()
        return cls(
            provider=str(s.value("street_view_pip/provider", "google_direct")),
            api_key=str(s.value("street_view_pip/api_key", "")),
            auto_coverage=str(s.value("street_view_pip/auto_coverage", "true")).lower() == "true",
            snap_road=str(s.value("street_view_pip/snap_road", "true")).lower() == "true",
            follow_pegman=str(s.value("street_view_pip/follow_pegman", "true")).lower() == "true",
            clean_mode=str(s.value("street_view_pip/clean_mode", "true")).lower() == "true",
            default_preset=str(s.value("street_view_pip/default_preset", "M")),
            language=str(s.value("street_view_pip/language", "en")),
        )

    def save(self) -> None:
        s = QgsSettings()
        s.setValue("street_view_pip/provider", self.provider)
        s.setValue("street_view_pip/api_key", self.api_key)
        s.setValue("street_view_pip/auto_coverage", "true" if self.auto_coverage else "false")
        s.setValue("street_view_pip/snap_road", "true" if self.snap_road else "false")
        s.setValue("street_view_pip/follow_pegman", "true" if self.follow_pegman else "false")
        s.setValue("street_view_pip/clean_mode", "true" if self.clean_mode else "false")
        s.setValue("street_view_pip/default_preset", self.default_preset)
        s.setValue("street_view_pip/language", self.language)


class StreetViewSettingsDialog(QtWidgets.QDialog):
    """Configuration dialog for Street View provider, API key, and PiP defaults."""

    def __init__(self, config: PluginConfig, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._config = PluginConfig(
            provider=config.provider,
            api_key=config.api_key,
            auto_coverage=config.auto_coverage,
            snap_road=config.snap_road,
            follow_pegman=config.follow_pegman,
            clean_mode=config.clean_mode,
            default_preset=config.default_preset,
            language=config.language,
        )
        self.setMinimumWidth(480)
        self._build_ui()
        self._apply_language()
        self._populate_values()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            "QDialog { background: #0f172a; color: #f8fafc; }"
            "QGroupBox { border: 1px solid #334155; border-radius: 6px; margin-top: 10px; "
            "padding: 12px 10px 10px 10px; font-weight: 700; color: #38bdf8; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }"
            "QLabel, QCheckBox { color: #e2e8f0; font-size: 12px; }"
            "QComboBox, QLineEdit { background: #1e293b; color: #f8fafc; border: 1px solid #475569; "
            "border-radius: 4px; padding: 5px 8px; }"
            "QPushButton { background: #1e293b; color: #f8fafc; border: 1px solid #475569; "
            "border-radius: 5px; padding: 6px 14px; font-weight: 600; }"
            "QPushButton:hover { border-color: #38bdf8; background: #263349; }"
            "QPushButton#btnSave { background: #0284c7; border-color: #38bdf8; color: #ffffff; }"
            "QPushButton#btnSave:hover { background: #0ea5e9; }"
        )

        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(12)

        # Group 1: Imagery Provider
        self.grp_provider = QtWidgets.QGroupBox()
        g1 = QtWidgets.QFormLayout(self.grp_provider)
        g1.setSpacing(8)

        self.lbl_provider = QtWidgets.QLabel()
        self.cmb_provider = QtWidgets.QComboBox()
        self.cmb_provider.addItem("", "google_direct")
        self.cmb_provider.addItem("", "google_js")
        self.cmb_provider.addItem("", "panoramax")
        self.cmb_provider.currentIndexChanged.connect(self._on_provider_changed)
        g1.addRow(self.lbl_provider, self.cmb_provider)

        self.lbl_api_key = QtWidgets.QLabel()
        self.edt_api_key = QtWidgets.QLineEdit()
        self.edt_api_key.setEchoMode(
            QtWidgets.QLineEdit.EchoMode.PasswordEchoOnEdit
            if hasattr(QtWidgets.QLineEdit, "EchoMode")
            else QtWidgets.QLineEdit.PasswordEchoOnEdit
        )
        g1.addRow(self.lbl_api_key, self.edt_api_key)
        root.addWidget(self.grp_provider)

        # Group 2: Map Interaction & PiP Behavior
        self.grp_behavior = QtWidgets.QGroupBox()
        g2 = QtWidgets.QVBoxLayout(self.grp_behavior)
        g2.setSpacing(7)

        self.chk_auto_coverage = QtWidgets.QCheckBox()
        self.chk_snap_road = QtWidgets.QCheckBox()
        self.chk_follow_pegman = QtWidgets.QCheckBox()
        self.chk_clean_mode = QtWidgets.QCheckBox()
        g2.addWidget(self.chk_auto_coverage)
        g2.addWidget(self.chk_snap_road)
        g2.addWidget(self.chk_follow_pegman)
        g2.addWidget(self.chk_clean_mode)

        form2 = QtWidgets.QFormLayout()
        form2.setSpacing(8)
        self.lbl_default_size = QtWidgets.QLabel()
        self.cmb_default_size = QtWidgets.QComboBox()
        self.cmb_default_size.addItem("S (390 x 260 px)", "S")
        self.cmb_default_size.addItem("M (480 x 320 px)", "M")
        self.cmb_default_size.addItem("L (680 x 450 px)", "L")
        form2.addRow(self.lbl_default_size, self.cmb_default_size)

        self.lbl_language = QtWidgets.QLabel()
        self.cmb_language = QtWidgets.QComboBox()
        self.cmb_language.addItem("English (Default)", "en")
        self.cmb_language.addItem("Turkce (Turkish)", "tr")
        self.cmb_language.currentIndexChanged.connect(self._on_lang_changed)
        form2.addRow(self.lbl_language, self.cmb_language)
        g2.addLayout(form2)
        root.addWidget(self.grp_behavior)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_cancel = QtWidgets.QPushButton()
        self.btn_cancel.setCursor(CURSOR_POINTING_HAND)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QtWidgets.QPushButton()
        self.btn_save.setObjectName("btnSave")
        self.btn_save.setCursor(CURSOR_POINTING_HAND)
        self.btn_save.clicked.connect(self._save_and_accept)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_save)
        root.addLayout(btn_row)

    def _apply_language(self) -> None:
        lang = self._config.language
        self.setWindowTitle(tr_text(lang, "settings_title"))
        self.grp_provider.setTitle(tr_text(lang, "grp_provider"))
        self.lbl_provider.setText(tr_text(lang, "lbl_provider"))
        self.cmb_provider.setItemText(0, tr_text(lang, "prov_google_direct"))
        self.cmb_provider.setItemText(1, tr_text(lang, "prov_google_js"))
        self.cmb_provider.setItemText(2, tr_text(lang, "prov_panoramax"))
        self.lbl_api_key.setText(tr_text(lang, "lbl_api_key"))
        self.edt_api_key.setPlaceholderText(tr_text(lang, "ph_api_key"))

        self.grp_behavior.setTitle(tr_text(lang, "grp_behavior"))
        self.chk_auto_coverage.setText(tr_text(lang, "chk_auto_coverage"))
        self.chk_snap_road.setText(tr_text(lang, "chk_snap_road"))
        self.chk_follow_pegman.setText(tr_text(lang, "chk_follow_pegman"))
        self.chk_clean_mode.setText(tr_text(lang, "chk_clean_mode"))
        self.lbl_default_size.setText(tr_text(lang, "lbl_default_size"))
        self.lbl_language.setText(tr_text(lang, "lbl_language"))
        self.btn_save.setText(tr_text(lang, "btn_save"))
        self.btn_cancel.setText(tr_text(lang, "btn_cancel"))

    def _populate_values(self) -> None:
        idx_p = self.cmb_provider.findData(self._config.provider)
        self.cmb_provider.setCurrentIndex(max(0, idx_p))
        self.edt_api_key.setText(self._config.api_key)
        self.chk_auto_coverage.setChecked(self._config.auto_coverage)
        self.chk_snap_road.setChecked(self._config.snap_road)
        self.chk_follow_pegman.setChecked(self._config.follow_pegman)
        self.chk_clean_mode.setChecked(self._config.clean_mode)

        idx_s = self.cmb_default_size.findData(self._config.default_preset)
        self.cmb_default_size.setCurrentIndex(max(0, idx_s))

        idx_l = self.cmb_language.findData(self._config.language)
        self.cmb_language.setCurrentIndex(max(0, idx_l))
        self._on_provider_changed()

    def _on_provider_changed(self) -> None:
        prov = self.cmb_provider.currentData()
        needs_key = prov == "google_js"
        self.edt_api_key.setEnabled(needs_key)
        self.lbl_api_key.setEnabled(needs_key)

    def _on_lang_changed(self) -> None:
        lang = self.cmb_language.currentData() or "en"
        self._config.language = lang
        self._apply_language()

    def _save_and_accept(self) -> None:
        self._config.provider = str(self.cmb_provider.currentData() or "google_direct")
        self._config.api_key = self.edt_api_key.text().strip()
        self._config.auto_coverage = self.chk_auto_coverage.isChecked()
        self._config.snap_road = self.chk_snap_road.isChecked()
        self._config.follow_pegman = self.chk_follow_pegman.isChecked()
        self._config.clean_mode = self.chk_clean_mode.isChecked()
        self._config.default_preset = str(self.cmb_default_size.currentData() or "M")
        self._config.language = str(self.cmb_language.currentData() or "en")
        self._config.save()
        self.accept()

    def config(self) -> PluginConfig:
        return self._config
