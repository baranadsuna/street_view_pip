# -*- coding: utf-8 -*-
"""
Headless GUI & Lifecycle Smoke Tests for Street View Navigator (PiP).

Verifies:
  1. Bottom-right PiP anchoring & dynamic canvas resize tracking
  2. Top-left corner drag resize pinning bottom-right corner
  3. S / M / L / Max size presets & collapsed Pegman pill
  4. Smooth pose interpolation, shortest-angle wrap & 60s idle wave animation
  5. One-shot PegmanMapTool + single toolbar icon ON/OFF toggle cleanup
  6. Settings dialog English default UI
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsProject
from qgis.gui import QgsMapCanvas

SRC_PARENT = Path(__file__).resolve().parent.parent.parent
if str(SRC_PARENT) not in sys.path:
    sys.path.insert(0, str(SRC_PARENT))

from street_view_pip.canvas_items import CanvasPoseOverlay
from street_view_pip.geo_utils import MANDATORY_CRS_AUTHID
from street_view_pip.pegman_map_tool import PegmanMapTool
from street_view_pip.pip_overlay_widget import SIZE_PRESETS, StreetViewPipOverlay
from street_view_pip.plugin import StreetViewPipPlugin
from street_view_pip.qt_compat import LEFT_BUTTON, NO_BUTTON
from street_view_pip.settings_dialog import PluginConfig, StreetViewSettingsDialog
from street_view_pip import webview_host


class _DummyMessageBar:
    def pushInfo(self, *_args, **_kwargs):
        pass


class _DummyIface:
    def __init__(self, canvas: QgsMapCanvas):
        self._canvas = canvas
        self._main_win = QtWidgets.QMainWindow()
        self._msg_bar = _DummyMessageBar()
        self.toolbar_actions = []
        self.web_menu_actions = []

    def mapCanvas(self):
        return self._canvas

    def mainWindow(self):
        return self._main_win

    def messageBar(self):
        return self._msg_bar

    def addToolBarIcon(self, action):
        self.toolbar_actions.append(action)

    def removeToolBarIcon(self, action):
        if action in self.toolbar_actions:
            self.toolbar_actions.remove(action)

    def addPluginToWebMenu(self, menu_name, action):
        self.web_menu_actions.append((menu_name, action))

    def removePluginWebMenu(self, menu_name, action):
        pair = (menu_name, action)
        if pair in self.web_menu_actions:
            self.web_menu_actions.remove(pair)


def run_gui_smoke() -> None:
    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        crs = QgsCoordinateReferenceSystem(MANDATORY_CRS_AUTHID)
        QgsProject.instance().setCrs(crs)

        canvas = QgsMapCanvas()
        canvas.setDestinationCrs(crs)
        canvas.resize(1000, 700)
        canvas.show()
        QgsApplication.processEvents()

        # 1. Bottom-right PiP anchoring & canvas resize
        pip = StreetViewPipOverlay(canvas=canvas, lang="en", default_preset="M")
        pip.show()
        QgsApplication.processEvents()
        assert pip.browser.backend_name() == "fallback"

        g0 = pip.geometry()
        assert abs((g0.x() + g0.width()) - (1000 - 14)) <= 2
        assert abs((g0.y() + g0.height()) - (700 - 14)) <= 2

        canvas.resize(1240, 820)
        QgsApplication.processEvents()
        g1 = pip.geometry()
        assert abs((g1.x() + g1.width()) - (1240 - 14)) <= 2
        assert abs((g1.y() + g1.height()) - (820 - 14)) <= 2

        # 2. Top-left resize pins bottom-right
        right_before = g1.x() + g1.width()
        bottom_before = g1.y() + g1.height()
        pip._resize_from_top_left(-80, -60)
        QgsApplication.processEvents()
        g2 = pip.geometry()
        assert g2.width() == g1.width() + 80 and g2.height() == g1.height() + 60
        assert (g2.x() + g2.width()) == right_before and (g2.y() + g2.height()) == bottom_before

        # 3. Presets & collapse/expand
        pip.apply_size_preset("S")
        assert pip.width() == SIZE_PRESETS["S"][0]
        pip.apply_size_preset("L")
        assert pip.width() == SIZE_PRESETS["L"][0]
        pip.toggle_maximize()
        assert pip.width() > SIZE_PRESETS["L"][0]
        pip.toggle_maximize()
        assert pip.width() == SIZE_PRESETS["L"][0]

        pip.set_collapsed(True)
        QgsApplication.processEvents()
        assert pip.is_collapsed() and pip.height() == pip.PILL_HEIGHT
        pip.set_collapsed(False)
        QgsApplication.processEvents()
        assert not pip.is_collapsed()

        # 3b. WebView2 native Client-Hints & loadingChanged signal check
        assert not hasattr(webview_host, "CHROME_DESKTOP_UA"), "Stale UA override breaks fresh profiles!"
        assert hasattr(webview_host, "_IID_CONTROLLER2") and hasattr(webview_host, "_Wv2Color")
        loading_events = []
        pip.browser.loadingChanged.connect(loading_events.append)
        pip._current_pose = None
        pip.browser.loadingChanged.emit(True)
        assert loading_events == [True] and "Loading" in pip.lbl_status.text()
        pip.browser.loadingChanged.emit(False)

        url = pip.load_street_view(38.0886007, 27.7346069, heading=265.0)
        assert "viewpoint=38.0886007,27.7346069" in url
        assert "5253:" in pip.lbl_status.text()

        pip.cleanup()
        pip.close()

        # 4. Smooth interpolation + walk vs run + 30s idle wave + lifted grab-by-arm
        overlay = CanvasPoseOverlay(canvas)
        overlay.update_pegman_pose(38.0885, 27.7345, heading=350.0, fov=85.0, smooth=False)
        # Short move (~11m <= 28m) -> WALKING mode
        overlay.update_pegman_pose(38.0886, 27.7345, heading=15.0, fov=80.0, smooth=True)
        assert overlay._running is False, "Short street move should walk, not run"
        assert overlay.step_animation(0.03) is True
        assert overlay._cur_heading >= 350.0 or overlay._cur_heading <= 15.0
        assert abs(overlay._turn_vel) > 0.0
        assert overlay._walk_amount > 0.0

        # Long jump (~120m > 28m) -> RUNNING mode
        overlay.update_pegman_pose(38.0897, 27.7345, heading=15.0, fov=80.0, smooth=True)
        assert overlay._running is True, "Long map jump (>28m) should trigger run animation"

        for _ in range(85):
            overlay.step_animation(0.05)
        assert abs(overlay._cur_heading - 15.0) < 0.5
        assert overlay._running is False
        assert overlay.trigger_idle_wave_check(elapsed_sec=20.0) is False
        assert overlay.trigger_idle_wave_check(elapsed_sec=31.0) is True, "Idle wave must trigger after 30s"
        # Moving again cancels wave immediately
        overlay.update_pegman_pose(38.0898, 27.7346, heading=40.0, smooth=True)
        assert overlay._wave_active is False

        # Verify lifted grab-by-arm state & hit testing
        pt_canvas = overlay._render_current_state()
        vp_pt = canvas.getCoordinateTransform().transform(pt_canvas)
        assert overlay.hit_test_pegman(QtCore.QPointF(vp_pt.x(), vp_pt.y() - 15.0)) is True
        assert overlay.hit_test_pegman(QtCore.QPointF(vp_pt.x() + 120.0, vp_pt.y())) is False
        overlay.set_lifted_drag(pt_canvas, dangle_tilt=10.0)
        assert overlay._lifted is True and overlay._pegman._lifted is True
        overlay.cleanup()

        # 5. Single Toolbar Icon + One-Shot Drop + Direct Canvas Grab + Clean Close Lifecycle
        iface = _DummyIface(canvas)
        plugin = StreetViewPipPlugin(iface)
        plugin.initGui()
        assert len(iface.toolbar_actions) == 1, "Toolbar must expose ONLY 1 Yellow Pegman icon"
        act = iface.toolbar_actions[0]
        assert act.isCheckable() and not act.isChecked()

        # Click 1 -> opens session & arms 1-shot PegmanMapTool
        act.trigger()
        assert plugin.is_session_active() and act.isChecked()
        assert isinstance(canvas.mapTool(), PegmanMapTool)
        assert canvas.mapTool().is_one_shot()

        # Simulate 1 click drop on map tool -> auto-unsets tool & opens PiP
        from qgis.gui import QgsMapMouseEvent
        et_press = QtCore.QEvent.Type.MouseButtonPress if hasattr(QtCore.QEvent, "Type") else QtCore.QEvent.MouseButtonPress
        et_move = QtCore.QEvent.Type.MouseMove if hasattr(QtCore.QEvent, "Type") else QtCore.QEvent.MouseMove
        et_rel = QtCore.QEvent.Type.MouseButtonRelease if hasattr(QtCore.QEvent, "Type") else QtCore.QEvent.MouseButtonRelease
        no_mod = QtCore.Qt.KeyboardModifier.NoModifier if hasattr(QtCore.Qt, "KeyboardModifier") else QtCore.Qt.NoModifier

        press_ev = QgsMapMouseEvent(canvas, et_press, QtCore.QPoint(500, 350), LEFT_BUTTON, LEFT_BUTTON, no_mod)
        rel_ev = QgsMapMouseEvent(canvas, et_rel, QtCore.QPoint(500, 350), LEFT_BUTTON, NO_BUTTON, no_mod)
        canvas.mapTool().canvasPressEvent(press_ev)
        canvas.mapTool().canvasReleaseEvent(rel_ev)
        QgsApplication.processEvents()

        assert not isinstance(canvas.mapTool(), PegmanMapTool), "Pegman tool must auto-disarm after 1 drop!"
        assert plugin._pip is not None and plugin._pip.isVisible() and not plugin._pip.is_collapsed()
        assert plugin._overlay._has_pose is True

        # Simulate grabbing Pegman directly on canvas by collar/arm and dropping elsewhere
        peg_px = canvas.getCoordinateTransform().transform(plugin._overlay._render_current_state())
        grab_pt = QtCore.QPoint(int(round(peg_px.x())), int(round(peg_px.y() - 14)))
        assert plugin._drop_filter.eventFilter(
            canvas.viewport(),
            QtCore.QEvent(et_press) if False else QtGui.QMouseEvent(et_press, QtCore.QPointF(grab_pt), LEFT_BUTTON, LEFT_BUTTON, no_mod),
        ) is True
        assert plugin._drop_filter.is_grabbing() is True and plugin._overlay._lifted is True
        move_pt = QtCore.QPoint(grab_pt.x() + 90, grab_pt.y() - 40)
        assert plugin._drop_filter.eventFilter(
            canvas.viewport(),
            QtGui.QMouseEvent(et_move, QtCore.QPointF(move_pt), NO_BUTTON, LEFT_BUTTON, no_mod),
        ) is True
        assert plugin._drop_filter.eventFilter(
            canvas.viewport(),
            QtGui.QMouseEvent(et_rel, QtCore.QPointF(move_pt), LEFT_BUTTON, NO_BUTTON, no_mod),
        ) is True
        assert plugin._drop_filter.is_grabbing() is False and plugin._overlay._lifted is False

        # Anti-Place-Hijack Guard check
        plugin._pip.browser._last_sv_url = "https://www.google.com/maps/@38.0886007,27.7346069,118a,85y,265h,90t/data=!3m7!1e1!3m5!1sS5EiolKvhOt6RDFUsU9IqA!2e0"
        plugin._pip.browser._handle_url_update("https://www.google.com/maps/place/Sekerbank/@38.088,27.734,17z")
        assert "S5EiolKvhOt6RDFUsU9IqA" in plugin._pip.browser._last_sv_url

        # Confetti button -> Johnny Bravo Monkey Dance check
        assert hasattr(plugin._pip, "btn_dance")
        plugin._pip.btn_dance.click()
        assert plugin._overlay._dance_active is True
        assert plugin._overlay.step_animation(0.25) is True
        plugin._pip.btn_dance.click()  # Toggle dance off cleanly
        assert plugin._overlay._dance_active is False

        # Click 2 -> closes everything cleanly!
        act.trigger()
        QgsApplication.processEvents()
        assert not plugin.is_session_active() and not act.isChecked()
        assert not plugin._pip.isVisible()
        assert plugin._overlay._has_pose is False

        plugin.unload()
        iface._main_win.close()

        # 6. Settings Dialog English default UI
        dlg = StreetViewSettingsDialog(PluginConfig(language="en"))
        assert "Settings" in dlg.windowTitle()
        dlg.close()

        canvas.close()
        print("PASS: test_pip_gui_smoke (all 6 GUI, animation & 1-button lifecycle suites passed)")
    finally:
        qgs.exitQgis()


if __name__ == "__main__":
    run_gui_smoke()
