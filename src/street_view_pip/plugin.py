# -*- coding: utf-8 -*-
"""
Main QGIS Plugin Controller for Street View Navigator (PiP).

Implements a clean single-button toolbar UX:
  - One Yellow Pegman toolbar button (toggles the Street View session ON/OFF).
  - Click 1 (ON): Arms one-shot Pegman drop + blue coverage lines. Dropping
    Pegman once on a street opens the bottom-right PiP Street View and
    automatically returns the QGIS cursor to normal Pan/Select.
  - Walking/panning in Street View smoothly animates Pegman & the FOV cone
    (including head/torso turns, walking stride, and 60s idle waving).
  - Click 2 (OFF) or clicking [X] on the PiP window closes everything cleanly:
    removes Pegman, FOV cone, coverage lines, and the bottom-right PiP window.
"""

from pathlib import Path
from typing import Optional

from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.core import QgsPointXY, QgsRectangle

from .canvas_items import CanvasPoseOverlay, LIFTED_BOOT_DROP_OFFSET_PX
from .coverage_overlay import CoverageOverlayManager
from .geo_utils import (
    StreetViewState,
    build_street_view_url,
    canvas_to_epsg5253,
    canvas_to_wgs84,
    snap_to_nearest_road_azimuth,
    snap_to_nearest_road_detail,
    wgs84_to_epsg5253,
)
from .i18n import tr_text
from .observation_logger import log_street_view_observation
from .pegman_map_tool import PegmanMapTool
from .pip_overlay_widget import PEGMAN_MIME_TYPE, StreetViewPipOverlay, render_pegman_pixmap
from .qt_compat import (
    CURSOR_CLOSED_HAND,
    CURSOR_OPEN_HAND,
    DROP_COPY,
    EVENT_DRAG_ENTER,
    EVENT_DRAG_LEAVE,
    EVENT_DRAG_MOVE,
    EVENT_DROP,
    EVENT_MOUSE_MOVE,
    EVENT_MOUSE_PRESS,
    EVENT_MOUSE_RELEASE,
    LEFT_BUTTON,
    event_pos,
    exec_dialog,
    log_debug,
)
from .settings_dialog import PluginConfig, StreetViewSettingsDialog


class CanvasPegmanDropFilter(QtCore.QObject):
    """Handles BOTH QDrag Pegman drops from PiP AND direct on-canvas Pegman grab-and-drop."""

    pegmanHover = QtCore.pyqtSignal(object)  # QgsPointXY
    pegmanLeft = QtCore.pyqtSignal()
    pegmanDropped = QtCore.pyqtSignal(object)  # QgsPointXY
    canvasGrabStarted = QtCore.pyqtSignal(object, object)  # hand_map_pt, drop_map_pt
    canvasGrabMoved = QtCore.pyqtSignal(object, object, float)  # hand_map_pt, drop_map_pt, dangle_tilt
    canvasGrabDropped = QtCore.pyqtSignal(object)  # drop_map_pt

    def __init__(
        self,
        canvas,
        overlay: CanvasPoseOverlay,
        map_tool: PegmanMapTool,
        parent: Optional[QtCore.QObject] = None,
    ):
        super().__init__(parent)
        self._canvas = canvas
        self._overlay = overlay
        self._map_tool = map_tool
        self._grabbing = False
        self._hovering_pegman = False
        self._last_x: Optional[int] = None

    def is_grabbing(self) -> bool:
        return self._grabbing

    def _to_map_point(self, px: QtCore.QPoint) -> QgsPointXY:
        return self._canvas.getCoordinateTransform().toMapCoordinates(px)

    def eventFilter(self, obj, event) -> bool:
        et = event.type()

        # 1. External QDrag from PiP Pegman button onto canvas
        if et in (EVENT_DRAG_ENTER, EVENT_DRAG_MOVE):
            mime = event.mimeData()
            if mime is not None and mime.hasFormat(PEGMAN_MIME_TYPE):
                event.setDropAction(DROP_COPY)
                event.accept()
                self.pegmanHover.emit(self._to_map_point(event_pos(event)))
                return True
        elif et == EVENT_DRAG_LEAVE:
            self.pegmanLeft.emit()
        elif et == EVENT_DROP:
            mime = event.mimeData()
            if mime is not None and mime.hasFormat(PEGMAN_MIME_TYPE):
                event.setDropAction(DROP_COPY)
                event.accept()
                self.pegmanDropped.emit(self._to_map_point(event_pos(event)))
                return True

        # 2. Direct on-canvas Pegman pick-up by raised hand (teleports hand right to cursor!)
        if self._canvas.mapTool() is not self._map_tool:
            if et == EVENT_MOUSE_PRESS and event.button() == LEFT_BUTTON:
                px = event_pos(event)
                if self._overlay.hit_test_pegman(QtCore.QPointF(px)):
                    self._grabbing = True
                    self._last_x = px.x()
                    self._canvas.viewport().setCursor(CURSOR_CLOSED_HAND)
                    drop_px = QtCore.QPoint(px.x(), px.y() + LIFTED_BOOT_DROP_OFFSET_PX)
                    self.canvasGrabStarted.emit(self._to_map_point(px), self._to_map_point(drop_px))
                    return True
            elif et == EVENT_MOUSE_MOVE:
                px = event_pos(event)
                if self._grabbing:
                    dx = 0 if self._last_x is None else (px.x() - self._last_x)
                    self._last_x = px.x()
                    tilt = max(-18.0, min(18.0, -dx * 1.4))
                    drop_px = QtCore.QPoint(px.x(), px.y() + LIFTED_BOOT_DROP_OFFSET_PX)
                    self.canvasGrabMoved.emit(self._to_map_point(px), self._to_map_point(drop_px), tilt)
                    return True
                else:
                    over = self._overlay.hit_test_pegman(QtCore.QPointF(px))
                    if over and not self._hovering_pegman:
                        self._hovering_pegman = True
                        self._canvas.viewport().setCursor(CURSOR_OPEN_HAND)
                    elif not over and self._hovering_pegman:
                        self._hovering_pegman = False
                        self._canvas.viewport().unsetCursor()
            elif et == EVENT_MOUSE_RELEASE and event.button() == LEFT_BUTTON and self._grabbing:
                self._grabbing = False
                self._last_x = None
                self._hovering_pegman = False
                self._canvas.viewport().unsetCursor()
                px = event_pos(event)
                drop_px = QtCore.QPoint(px.x(), px.y() + LIFTED_BOOT_DROP_OFFSET_PX)
                self.canvasGrabDropped.emit(self._to_map_point(drop_px))
                return True

        return super().eventFilter(obj, event)


class StreetViewPipPlugin:
    """QGIS Plugin lifecycle & single-button Pegman PiP orchestrator."""

    def __init__(self, iface):
        self.iface = iface
        self._config = PluginConfig.load()
        self._plugin_dir = Path(__file__).resolve().parent
        self._session_active = False

        self._act_pegman: Optional[QtWidgets.QAction] = None
        self._act_settings: Optional[QtWidgets.QAction] = None
        self._menu_actions: list = []

        self._overlay: Optional[CanvasPoseOverlay] = None
        self._coverage: Optional[CoverageOverlayManager] = None
        self._map_tool: Optional[PegmanMapTool] = None
        self._pip: Optional[StreetViewPipOverlay] = None
        self._drop_filter: Optional[CanvasPegmanDropFilter] = None
        self._prev_map_tool = None

    def _load_pegman_icon(self) -> QtGui.QIcon:
        icon_png = self._plugin_dir / "icon.png"
        icon_svg = self._plugin_dir / "icon.svg"
        if icon_png.exists():
            return QtGui.QIcon(str(icon_png))
        if icon_svg.exists():
            return QtGui.QIcon(str(icon_svg))
        return QtGui.QIcon(render_pegman_pixmap(48))

    def initGui(self) -> None:
        canvas = self.iface.mapCanvas()
        lang = self._config.language

        self._overlay = CanvasPoseOverlay(canvas)
        self._coverage = CoverageOverlayManager(lang=lang)
        self._map_tool = PegmanMapTool(
            canvas,
            self._overlay,
            snap_road_fn=lambda: self._config.snap_road,
            one_shot=True,
        )
        self._map_tool.pegmanDropped.connect(self._on_pegman_dropped_latlon)
        self._map_tool.cursorMoved.connect(self._on_cursor_moved)
        self._map_tool.deactivatedTool.connect(self._on_map_tool_deactivated)

        vp = canvas.viewport()
        vp.setAcceptDrops(True)
        self._drop_filter = CanvasPegmanDropFilter(canvas, self._overlay, self._map_tool, vp)
        self._drop_filter.pegmanHover.connect(self._on_drag_hover_map_point)
        self._drop_filter.pegmanLeft.connect(self._on_drag_left_canvas)
        self._drop_filter.pegmanDropped.connect(self._on_drag_dropped_map_point)
        self._drop_filter.canvasGrabStarted.connect(self._on_canvas_grab_started)
        self._drop_filter.canvasGrabMoved.connect(self._on_canvas_grab_moved)
        self._drop_filter.canvasGrabDropped.connect(self._on_canvas_grab_dropped)
        vp.installEventFilter(self._drop_filter)

        # Single yellow Pegman icon on QGIS Toolbar
        peg_icon = self._load_pegman_icon()
        self._act_pegman = QtWidgets.QAction(
            peg_icon, tr_text(lang, "toolbar_pegman"), self.iface.mainWindow()
        )
        self._act_pegman.setCheckable(True)
        self._act_pegman.triggered.connect(self._on_toolbar_pegman_toggled)
        self.iface.addToolBarIcon(self._act_pegman)

        self._act_settings = QtWidgets.QAction(
            tr_text(lang, "toolbar_settings"), self.iface.mainWindow()
        )
        self._act_settings.triggered.connect(self._open_settings)

        menu_name = tr_text(lang, "plugin_name")
        for act in (self._act_pegman, self._act_settings):
            self.iface.addPluginToWebMenu(menu_name, act)
            self._menu_actions.append((menu_name, act))

    def _ensure_pip_widget(self) -> StreetViewPipOverlay:
        if self._pip is None:
            canvas = self.iface.mapCanvas()
            self._pip = StreetViewPipOverlay(
                canvas=canvas,
                lang=self._config.language,
                default_preset=self._config.default_preset,
            )
            self._pip.set_clean_checked(self._config.clean_mode)
            self._pip.set_follow_checked(self._config.follow_pegman)
            self._pip.pegmanToolRequested.connect(self._arm_one_shot_pegman)
            self._pip.pegmanDragStarted.connect(self._on_pip_drag_started)
            self._pip.pegmanDragFinished.connect(self._on_pip_drag_finished)
            self._pip.coverageToggled.connect(self._on_toggle_coverage)
            self._pip.cleanModeToggled.connect(self._on_clean_toggled)
            self._pip.followToggled.connect(self._on_follow_toggled)
            self._pip.saveObservationRequested.connect(self._save_current_observation)
            self._pip.settingsRequested.connect(self._open_settings)
            self._pip.openBrowserRequested.connect(self._open_in_external_browser)
            self._pip.copyCoordsRequested.connect(self._copy_current_coords)
            self._pip.sessionCloseRequested.connect(self.close_session)
            self._pip.danceRequested.connect(self._on_dance_requested)
            self._pip.viewpointChanged.connect(self._on_streetview_pose_updated)
        return self._pip

    # --- Single Toolbar Button Session Toggle ---

    def is_session_active(self) -> bool:
        return self._session_active

    def _on_toolbar_pegman_toggled(self, checked: bool) -> None:
        if checked:
            self.open_session()
        else:
            self.close_session()

    def open_session(self) -> None:
        """Start Street View session: show bottom-right pill and arm one-shot Pegman drop."""
        self._session_active = True
        if self._act_pegman:
            self._act_pegman.setChecked(True)
        pip = self._ensure_pip_widget()
        if pip.current_pose() is None:
            pip.set_collapsed(True)
        pip.show()
        pip.reposition_in_canvas()
        pip.raise_()
        self._arm_one_shot_pegman()

    def close_session(self) -> None:
        """Completely close Street View session: hide PiP, Pegman, FOV cone & coverage."""
        self._session_active = False
        self._disarm_pegman_tool()

        if self._pip is not None:
            self._pip.reset_session()
            self._pip.set_pegman_armed(False)
            self._pip.set_coverage_checked(False)

        if self._overlay is not None:
            self._overlay.clear_all()

        if self._coverage is not None:
            self._coverage.set_visible(False, user_pinned=False)

        if self._act_pegman:
            self._act_pegman.setChecked(False)

    def _arm_one_shot_pegman(self) -> None:
        canvas = self.iface.mapCanvas()
        if canvas.mapTool() is self._map_tool:
            self._disarm_pegman_tool()
            return

        self._prev_map_tool = canvas.mapTool()
        self._map_tool.set_one_shot(True)
        canvas.setMapTool(self._map_tool)

        pip = self._ensure_pip_widget()
        pip.set_pegman_armed(True)
        if self._config.auto_coverage and self._coverage is not None:
            self._coverage.set_transient_active(True)
            pip.set_coverage_checked(self._coverage.is_visible())

    def _disarm_pegman_tool(self) -> None:
        canvas = self.iface.mapCanvas()
        if canvas.mapTool() is self._map_tool:
            if self._prev_map_tool is not None and self._prev_map_tool is not self._map_tool:
                canvas.setMapTool(self._prev_map_tool)
            else:
                canvas.unsetMapTool(self._map_tool)
        self._prev_map_tool = None

    def _on_map_tool_deactivated(self) -> None:
        if self._pip is not None:
            self._pip.set_pegman_armed(False)
        if self._coverage is not None:
            self._coverage.set_transient_active(False)
            if self._pip is not None:
                self._pip.set_coverage_checked(self._coverage.is_visible())

    def _on_pip_drag_started(self) -> None:
        if self._config.auto_coverage and self._coverage is not None:
            self._coverage.set_transient_active(True)
            if self._pip is not None:
                self._pip.set_coverage_checked(self._coverage.is_visible())
                self._pip.set_status_message("status_dragging")

    def _on_pip_drag_finished(self, accepted: bool) -> None:
        if not accepted and self._overlay is not None:
            self._overlay.hide_drop_reticle()
        if self._coverage is not None:
            self._coverage.set_transient_active(False)
            if self._pip is not None:
                self._pip.set_coverage_checked(self._coverage.is_visible())

    def _on_drag_hover_map_point(self, map_pt: QgsPointXY) -> None:
        if self._overlay is not None:
            self._overlay.show_drop_reticle(map_pt)
        if self._pip is not None:
            canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
            lat, lon = canvas_to_wgs84(map_pt, canvas_crs)
            x5253, y5253 = canvas_to_epsg5253(map_pt, canvas_crs)
            self._pip.set_status_hover(x5253, y5253, lat, lon)

    def _on_drag_left_canvas(self) -> None:
        if self._overlay is not None:
            self._overlay.hide_drop_reticle()

    def _on_drag_dropped_map_point(self, map_pt: QgsPointXY) -> None:
        if self._overlay is not None:
            self._overlay.hide_drop_reticle()
        canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        lat, lon = canvas_to_wgs84(map_pt, canvas_crs)
        heading = 0.0
        if self._config.snap_road:
            snapped = snap_to_nearest_road_detail(lat, lon, max_distance_m=18.0)
            if snapped is not None:
                lat, lon, heading = snapped
            else:
                az = snap_to_nearest_road_azimuth(lat, lon, max_distance_m=35.0)
                if az is not None:
                    heading = az
        self._on_pegman_dropped_latlon(lat, lon, heading)

    def _on_canvas_grab_started(self, hand_map_pt: QgsPointXY, drop_map_pt: QgsPointXY) -> None:
        if self._config.auto_coverage and self._coverage is not None:
            self._coverage.set_transient_active(True)
            if self._pip is not None:
                self._pip.set_coverage_checked(self._coverage.is_visible())
                self._pip.set_status_message("status_dragging")
        if self._overlay is not None:
            self._overlay.set_lifted_drag(hand_map_pt, drop_map_pt=drop_map_pt, dangle_tilt=0.0)

    def _on_canvas_grab_moved(self, hand_map_pt: QgsPointXY, drop_map_pt: QgsPointXY, dangle_tilt: float) -> None:
        if self._overlay is not None:
            self._overlay.set_lifted_drag(hand_map_pt, drop_map_pt=drop_map_pt, dangle_tilt=dangle_tilt)
        if self._pip is not None:
            canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
            lat, lon = canvas_to_wgs84(drop_map_pt, canvas_crs)
            x5253, y5253 = canvas_to_epsg5253(drop_map_pt, canvas_crs)
            self._pip.set_status_hover(x5253, y5253, lat, lon)

    def _on_canvas_grab_dropped(self, drop_map_pt: QgsPointXY) -> None:
        if self._coverage is not None:
            self._coverage.set_transient_active(False)
            if self._pip is not None:
                self._pip.set_coverage_checked(self._coverage.is_visible())
        self._on_drag_dropped_map_point(drop_map_pt)

    def _on_dance_requested(self) -> None:
        if self._overlay is not None:
            self._overlay.trigger_monkey_dance()

    def _on_cursor_moved(self, x5253: float, y5253: float, lat: float, lon: float) -> None:
        if self._pip is not None and not self._pip.is_collapsed():
            self._pip.set_status_hover(x5253, y5253, lat, lon)

    # --- Opening & Smooth Synchronizing Street View ---

    def _on_pegman_dropped_latlon(self, lat: float, lon: float, heading: float) -> None:
        self._session_active = True
        if self._act_pegman:
            self._act_pegman.setChecked(True)

        pip = self._ensure_pip_widget()
        if self._overlay is not None:
            self._overlay.update_pegman_pose(lat, lon, heading=heading, fov=85.0, smooth=False)
        pip.load_street_view(
            lat=lat,
            lon=lon,
            heading=heading,
            pitch=0.0,
            fov=85.0,
            provider=self._config.provider,
            api_key=self._config.api_key,
        )

    def _on_streetview_pose_updated(self, pose: StreetViewState) -> None:
        if not self._session_active:
            return
        canvas = self.iface.mapCanvas()
        if self._overlay is not None:
            canvas_pt = self._overlay.update_pegman_pose(
                pose.lat, pose.lon, heading=pose.heading, fov=pose.fov, smooth=True
            )
            if self._config.follow_pegman:
                ext = canvas.extent()
                inner = QgsRectangle(ext)
                inner.scale(0.82)
                if not inner.contains(canvas_pt):
                    canvas.setCenter(canvas_pt)
                    canvas.refresh()

    def _on_toggle_coverage(self, checked: Optional[bool] = None) -> None:
        if self._coverage is None:
            return
        if checked is None:
            vis = self._coverage.toggle_user_pinned()
        else:
            vis = self._coverage.set_visible(bool(checked), user_pinned=bool(checked))
        if self._pip is not None:
            self._pip.set_coverage_checked(vis)

    def _on_clean_toggled(self, checked: bool) -> None:
        self._config.clean_mode = bool(checked)
        self._config.save()

    def _on_follow_toggled(self, checked: bool) -> None:
        self._config.follow_pegman = bool(checked)
        self._config.save()

    def _save_current_observation(self) -> None:
        pip = self._ensure_pip_widget()
        pose = pip.current_pose()
        if pose is None:
            return
        log_street_view_observation(pose, lang=self._config.language)
        x5253, y5253 = wgs84_to_epsg5253(pose.lat, pose.lon)
        msg = tr_text(self._config.language, "obs_saved", x=x5253, y=y5253, hdg=pose.heading)
        self.iface.messageBar().pushInfo(tr_text(self._config.language, "plugin_name"), msg)

    def _copy_current_coords(self) -> None:
        pip = self._ensure_pip_widget()
        pose = pip.current_pose()
        if pose is None:
            return
        x5253, y5253 = wgs84_to_epsg5253(pose.lat, pose.lon)
        payload = (
            f"EPSG:5253: {x5253:.2f}, {y5253:.2f} | "
            f"WGS84: {pose.lat:.6f}, {pose.lon:.6f} | Heading: {pose.heading:.1f}"
        )
        QtWidgets.QApplication.clipboard().setText(payload)
        msg = tr_text(
            self._config.language,
            "coords_copied",
            x=x5253,
            y=y5253,
            lat=pose.lat,
            lon=pose.lon,
        )
        self.iface.messageBar().pushInfo(tr_text(self._config.language, "plugin_name"), msg)

    def _open_in_external_browser(self) -> None:
        pip = self._ensure_pip_widget()
        pose = pip.current_pose()
        if pose is not None:
            url = pose.url or build_street_view_url(
                pose.lat,
                pose.lon,
                pose.heading,
                pose.pitch,
                pose.fov,
                self._config.provider,
                pose.pano_id,
            )
        else:
            url = pip.browser.current_url()
        if url:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    def _open_settings(self) -> None:
        dlg = StreetViewSettingsDialog(self._config, self.iface.mainWindow())
        if exec_dialog(dlg):
            self._config = dlg.config()
            if self._coverage is not None:
                self._coverage.set_language(self._config.language)
            if self._pip is not None:
                self._pip.set_language(self._config.language)
                self._pip.set_clean_checked(self._config.clean_mode)
                self._pip.set_follow_checked(self._config.follow_pegman)
                pose = self._pip.current_pose()
                if pose is not None:
                    self._pip.load_street_view(
                        pose.lat,
                        pose.lon,
                        pose.heading,
                        pose.pitch,
                        pose.fov,
                        provider=self._config.provider,
                        api_key=self._config.api_key,
                    )

    def unload(self) -> None:
        self.close_session()
        canvas = self.iface.mapCanvas()

        if self._drop_filter is not None:
            try:
                canvas.viewport().removeEventFilter(self._drop_filter)
            except Exception as exc:
                log_debug(f"Canvas viewport filter removal warning: {exc}")
            self._drop_filter = None

        if self._pip is not None:
            self._pip.cleanup()
            self._pip.hide()
            self._pip.deleteLater()
            self._pip = None

        if self._overlay is not None:
            self._overlay.cleanup()
            self._overlay = None

        if self._coverage is not None:
            self._coverage.cleanup()
            self._coverage = None

        if self._act_pegman is not None:
            self.iface.removeToolBarIcon(self._act_pegman)

        for menu_name, act in self._menu_actions:
            self.iface.removePluginWebMenu(menu_name, act)
        self._menu_actions.clear()
