# -*- coding: utf-8 -*-
"""
Bottom-Right Resizable Picture-in-Picture (PiP) Overlay for QGIS Map Canvas.

Implements the floating corner Street View window shown on the bottom-right
of the QGIS map canvas with:
  - Smooth bottom-right anchored resizing via top-left corner grip + edges
  - S / M / L / Max quick size presets
  - Collapse-to-Pegman-Pill mode in the bottom-right corner
  - Real Qt QDrag yellow Pegman handle to drag & drop directly onto QgsMapCanvas
  - Embedded WebView2 / QtWebEngine Street View viewport + live EPSG:5253 readout
"""

from typing import Dict, Optional, Tuple

from qgis.PyQt import QtCore, QtGui, QtWidgets

from .geo_utils import StreetViewState, wgs84_to_epsg5253
from .i18n import tr_text
from .qt_compat import (
    ANTIALIASING,
    BRUSH_SOLID,
    CURSOR_ARROW,
    CURSOR_OPEN_HAND,
    CURSOR_POINTING_HAND,
    CURSOR_SIZE_ALL,
    CURSOR_SIZE_FDIAG,
    CURSOR_SIZE_HOR,
    CURSOR_SIZE_VER,
    DROP_COPY,
    EVENT_RESIZE,
    LEFT_BUTTON,
    PEN_SOLID,
    TRANSPARENT_BG,
    event_global_pos,
    event_pos,
    exec_drag,
    log_debug,
)
from .webview_host import StreetViewBrowserWidget

PEGMAN_MIME_TYPE = "application/x-qgis-streetview-pegman"

SIZE_PRESETS: Dict[str, Tuple[int, int]] = {
    "S": (390, 260),
    "M": (480, 320),
    "L": (680, 450),
}


def render_pegman_pixmap(size: int = 28) -> QtGui.QPixmap:
    """Paint a 3D-shaded eyeless cowboy Pegman icon pixmap with red bandana."""
    pm = QtGui.QPixmap(size, size)
    pm.fill(TRANSPARENT_BG)
    p = QtGui.QPainter(pm)
    p.setRenderHint(ANTIALIASING, True)
    scale = size / 32.0
    p.scale(scale, scale)

    body_grad = QtGui.QLinearGradient(8.0, 12.0, 24.0, 29.0)
    body_grad.setColorAt(0.0, QtGui.QColor("#fef08a"))
    body_grad.setColorAt(0.5, QtGui.QColor("#facc15"))
    body_grad.setColorAt(1.0, QtGui.QColor("#b45309"))

    head_grad = QtGui.QRadialGradient(14.5, 8.2, 6.5)
    head_grad.setColorAt(0.0, QtGui.QColor("#fef9c3"))
    head_grad.setColorAt(0.55, QtGui.QColor("#facc15"))
    head_grad.setColorAt(1.0, QtGui.QColor("#b45309"))

    hat_grad = QtGui.QLinearGradient(9.0, 1.0, 23.0, 8.0)
    hat_grad.setColorAt(0.0, QtGui.QColor("#d97706"))
    hat_grad.setColorAt(0.55, QtGui.QColor("#78350f"))
    hat_grad.setColorAt(1.0, QtGui.QColor("#451a03"))

    p.setPen(QtGui.QPen(QtGui.QColor("#291507"), 1.6, PEN_SOLID))
    p.setBrush(QtGui.QBrush(body_grad))

    # Legs + Torso
    body = QtGui.QPainterPath()
    body.moveTo(9.0, 16.0)
    body.quadTo(16.0, 13.0, 23.0, 16.0)
    body.lineTo(22.0, 22.8)
    body.lineTo(19.0, 22.8)
    body.lineTo(19.0, 30.0)
    body.lineTo(13.0, 30.0)
    body.lineTo(13.0, 22.8)
    body.lineTo(10.0, 22.8)
    body.closeSubpath()
    p.drawPath(body)

    # Red bandana
    p.setBrush(QtGui.QBrush(QtGui.QColor("#dc2626"), BRUSH_SOLID))
    scarf = QtGui.QPainterPath()
    scarf.moveTo(11.8, 15.0)
    scarf.lineTo(20.2, 15.0)
    scarf.lineTo(16.0, 19.4)
    scarf.closeSubpath()
    p.drawPath(scarf)

    # Eyeless 3D head
    p.setBrush(QtGui.QBrush(head_grad))
    p.drawEllipse(QtCore.QPointF(16.0, 10.0), 4.6, 4.6)

    # 3D Cowboy Hat
    p.setBrush(QtGui.QBrush(hat_grad))
    hat = QtGui.QPainterPath()
    hat.moveTo(7.5, 7.6)
    hat.quadTo(16.0, 9.8, 24.5, 7.6)
    hat.quadTo(21.5, 5.4, 19.5, 5.7)
    hat.lineTo(18.5, 1.8)
    hat.quadTo(16.0, 3.0, 13.5, 1.8)
    hat.lineTo(12.5, 5.7)
    hat.quadTo(10.5, 5.4, 7.5, 7.6)
    hat.closeSubpath()
    p.drawPath(hat)

    p.setPen(QtGui.QPen(QtGui.QColor("#dc2626"), 1.3, PEN_SOLID))
    p.drawLine(QtCore.QPointF(12.6, 5.7), QtCore.QPointF(19.4, 5.7))
    p.end()
    return pm


def render_confetti_pixmap(size: int = 22) -> QtGui.QPixmap:
    """Paint a crisp 3D party confetti popper icon matching Image 4."""
    pm = QtGui.QPixmap(size, size)
    pm.fill(TRANSPARENT_BG)
    p = QtGui.QPainter(pm)
    p.setRenderHint(ANTIALIASING, True)
    scale = size / 24.0
    p.scale(scale, scale)

    # Party cone (gold/orange with blue stripes)
    cone_grad = QtGui.QLinearGradient(3.0, 11.0, 13.0, 21.0)
    cone_grad.setColorAt(0.0, QtGui.QColor("#facc15"))
    cone_grad.setColorAt(1.0, QtGui.QColor("#ea580c"))
    p.setPen(QtGui.QPen(QtGui.QColor("#7c2d12"), 1.1, PEN_SOLID))
    p.setBrush(QtGui.QBrush(cone_grad))
    cone = QtGui.QPainterPath()
    cone.moveTo(4.0, 20.0)
    cone.lineTo(8.0, 9.5)
    cone.lineTo(14.5, 16.0)
    cone.closeSubpath()
    p.drawPath(cone)

    p.setPen(QtGui.QPen(QtGui.QColor("#2563eb"), 1.6, PEN_SOLID))
    p.drawLine(QtCore.QPointF(6.8, 13.5), QtCore.QPointF(10.5, 17.2))
    p.drawLine(QtCore.QPointF(5.5, 16.8), QtCore.QPointF(7.8, 19.0))

    # Pink & cyan confetti ribbons + dots
    p.setPen(QtGui.QPen(QtGui.QColor("#ec4899"), 2.0, PEN_SOLID))
    p.drawArc(QtCore.QRectF(8.5, 3.0, 5.0, 8.0), -20 * 16, 130 * 16)
    p.drawArc(QtCore.QRectF(13.5, 7.5, 7.0, 5.0), 40 * 16, 120 * 16)

    p.setPen(QtGui.QPen(QtGui.QColor("#38bdf8"), 2.0, PEN_SOLID))
    p.drawArc(QtCore.QRectF(12.0, 2.5, 5.5, 7.0), 10 * 16, 150 * 16)
    p.drawArc(QtCore.QRectF(12.5, 11.5, 7.5, 5.5), 10 * 16, 140 * 16)

    for cx, cy, col in ((9.5, 4.2, "#facc15"), (18.5, 5.2, "#ec4899"), (19.5, 16.5, "#facc15"), (13.8, 9.8, "#38bdf8")):
        p.setPen(QtGui.QPen(QtGui.QColor(col), 1.0, PEN_SOLID))
        p.setBrush(QtGui.QBrush(QtGui.QColor(col), BRUSH_SOLID))
        p.drawEllipse(QtCore.QPointF(cx, cy), 1.15, 1.15)
    p.end()
    return pm


class PegmanDragHandle(QtWidgets.QToolButton):
    """Yellow Pegman button supporting BOTH click-to-arm and drag-to-drop onto canvas."""

    dragStarted = QtCore.pyqtSignal()
    dragEnded = QtCore.pyqtSignal(bool)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._press_pos: Optional[QtCore.QPoint] = None
        self._did_drag = False
        self.setCheckable(True)
        self.setCursor(CURSOR_OPEN_HAND)
        self.setIcon(QtGui.QIcon(render_pegman_pixmap(24)))
        self.setIconSize(QtCore.QSize(20, 20))
        self.setFixedSize(28, 24)
        self.setStyleSheet(
            "QToolButton { background: #fef08a; border: 1px solid #eab308; border-radius: 5px; padding: 1px; }"
            "QToolButton:hover { background: #fde047; border-color: #facc15; }"
            "QToolButton:checked { background: #facc15; border: 2px solid #38bdf8; }"
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == LEFT_BUTTON:
            self._press_pos = event_pos(event)
            self._did_drag = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (event.buttons() & LEFT_BUTTON) and self._press_pos is not None:
            delta = event_pos(event) - self._press_pos
            if delta.manhattanLength() >= 6:
                self._did_drag = True
                self.dragStarted.emit()
                mime = QtCore.QMimeData()
                mime.setData(PEGMAN_MIME_TYPE, b"pegman")
                drag = QtGui.QDrag(self)
                drag.setMimeData(mime)
                pm = render_pegman_pixmap(42)
                drag.setPixmap(pm)
                drag.setHotSpot(QtCore.QPoint(int(pm.width() * 0.65), int(pm.height() * 0.22)))
                res = exec_drag(drag, DROP_COPY)
                self._press_pos = None
                self.setDown(False)
                self.dragEnded.emit(res == DROP_COPY)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._did_drag:
            self._did_drag = False
            self._press_pos = None
            self.setDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ResizeGripCorner(QtWidgets.QWidget):
    """Top-left corner grip that anchors the bottom-right corner while resizing."""

    resizedByDelta = QtCore.pyqtSignal(int, int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(20, 24)
        self.setCursor(CURSOR_SIZE_FDIAG)
        self._dragging = False
        self._last_global: Optional[QtCore.QPoint] = None

    def paintEvent(self, event) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(ANTIALIASING, True)
        pen = QtGui.QPen(QtGui.QColor("#38bdf8"), 1.6, PEN_SOLID)
        p.setPen(pen)
        # Draw subtle top-left diagonal resize chevron
        p.drawLine(4, 10, 4, 4)
        p.drawLine(4, 4, 10, 4)
        p.drawLine(4, 4, 12, 12)
        p.drawLine(4, 14, 14, 4)
        p.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == LEFT_BUTTON:
            self._dragging = True
            self._last_global = event_global_pos(event)
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and self._last_global is not None:
            cur = event_global_pos(event)
            dx = cur.x() - self._last_global.x()
            dy = cur.y() - self._last_global.y()
            self._last_global = cur
            self.resizedByDelta.emit(dx, dy)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        self._last_global = None
        event.accept()


class StreetViewPipOverlay(QtWidgets.QFrame):
    """
    Resizable Picture-in-Picture Street View overlay anchored to the bottom-right
    corner of QgsMapCanvas (or standalone parent widget in headless tests).
    """

    pegmanToolRequested = QtCore.pyqtSignal()
    pegmanDragStarted = QtCore.pyqtSignal()
    pegmanDragFinished = QtCore.pyqtSignal(bool)
    coverageToggled = QtCore.pyqtSignal(bool)
    cleanModeToggled = QtCore.pyqtSignal(bool)
    followToggled = QtCore.pyqtSignal(bool)
    saveObservationRequested = QtCore.pyqtSignal()
    settingsRequested = QtCore.pyqtSignal()
    openBrowserRequested = QtCore.pyqtSignal()
    copyCoordsRequested = QtCore.pyqtSignal()
    sessionCloseRequested = QtCore.pyqtSignal()
    danceRequested = QtCore.pyqtSignal()
    viewpointChanged = QtCore.pyqtSignal(object)

    MIN_WIDTH = 330
    MIN_HEIGHT = 210
    PILL_WIDTH = 220
    PILL_HEIGHT = 38
    BORDER_HIT = 6

    def __init__(
        self,
        canvas: Optional[QtWidgets.QWidget] = None,
        lang: str = "en",
        default_preset: str = "M",
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        host_parent = parent if parent is not None else canvas
        super().__init__(host_parent)
        self._canvas = canvas
        self._lang = lang
        self._collapsed = False
        self._maximized = False
        self._anchored_bottom_right = True
        self._right_margin = 14
        self._bottom_margin = 14

        init_w, init_h = SIZE_PRESETS.get(default_preset, SIZE_PRESETS["M"])
        self._expanded_size = QtCore.QSize(init_w, init_h)
        self._pre_max_size = QtCore.QSize(init_w, init_h)
        self._current_pose: Optional[StreetViewState] = None

        self._edge_resize_mode: Optional[str] = None
        self._move_dragging = False
        self._drag_origin_global: Optional[QtCore.QPoint] = None
        self._drag_start_geom: Optional[QtCore.QRect] = None

        self.setObjectName("StreetViewPipOverlay")
        self.setMouseTracking(True)
        self._apply_frame_style()
        self._build_ui()
        self._apply_language()

        if self._canvas is not None:
            self._canvas.installEventFilter(self)

        self.resize(self._expanded_size)
        self.reposition_in_canvas()

    def _apply_frame_style(self) -> None:
        self.setStyleSheet(
            "#StreetViewPipOverlay {"
            "  background-color: #0f172a;"
            "  border: 2px solid #38bdf8;"
            "  border-radius: 9px;"
            "}"
            "QToolButton {"
            "  background: #1e293b; color: #e2e8f0; border: 1px solid #334155;"
            "  border-radius: 4px; padding: 2px 5px; font-size: 11px; font-weight: 600;"
            "}"
            "QToolButton:hover { border-color: #38bdf8; background: #263349; color: #ffffff; }"
            "QToolButton:checked { background: #0284c7; border-color: #38bdf8; color: #ffffff; }"
        )

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(4, 3, 4, 4)
        root.setSpacing(3)

        # --- 1. Expanded Header Bar ---
        self._header_widget = QtWidgets.QWidget(self)
        self._header_widget.setFixedHeight(28)
        self._header_widget.setMouseTracking(True)
        self._header_widget.installEventFilter(self)
        hbar = QtWidgets.QHBoxLayout(self._header_widget)
        hbar.setContentsMargins(0, 0, 0, 0)
        hbar.setSpacing(3)

        self.grip_tl = ResizeGripCorner(self._header_widget)
        self.grip_tl.resizedByDelta.connect(self._resize_from_top_left)
        hbar.addWidget(self.grip_tl)

        self.btn_pegman = PegmanDragHandle(self._header_widget)
        self.btn_pegman.clicked.connect(lambda _chk: self.pegmanToolRequested.emit())
        self.btn_pegman.dragStarted.connect(self.pegmanDragStarted.emit)
        self.btn_pegman.dragEnded.connect(self.pegmanDragFinished.emit)
        hbar.addWidget(self.btn_pegman)

        self.lbl_title = QtWidgets.QLabel(self._header_widget)
        self.lbl_title.setStyleSheet("color: #f8fafc; font-weight: 700; font-size: 11px; padding: 0 4px;")
        self.lbl_title.setCursor(CURSOR_SIZE_ALL)
        hbar.addWidget(self.lbl_title, 1)

        # Party confetti button -> Johnny Bravo "Do the Monkey!" dance!
        self.btn_dance = QtWidgets.QToolButton(self._header_widget)
        self.btn_dance.setIcon(QtGui.QIcon(render_confetti_pixmap(20)))
        self.btn_dance.setIconSize(QtCore.QSize(18, 18))
        self.btn_dance.setFixedSize(26, 22)
        self.btn_dance.setCursor(CURSOR_POINTING_HAND)
        self.btn_dance.clicked.connect(lambda: self.danceRequested.emit())
        hbar.addWidget(self.btn_dance)

        # Size preset pills: S, M, L, Max
        self.btn_s = QtWidgets.QToolButton(self._header_widget)
        self.btn_s.clicked.connect(lambda: self.apply_size_preset("S"))
        self.btn_m = QtWidgets.QToolButton(self._header_widget)
        self.btn_m.clicked.connect(lambda: self.apply_size_preset("M"))
        self.btn_l = QtWidgets.QToolButton(self._header_widget)
        self.btn_l.clicked.connect(lambda: self.apply_size_preset("L"))
        self.btn_max = QtWidgets.QToolButton(self._header_widget)
        self.btn_max.clicked.connect(self.toggle_maximize)

        for b in (self.btn_s, self.btn_m, self.btn_l):
            b.setCursor(CURSOR_POINTING_HAND)
            b.setFixedSize(23, 22)
            hbar.addWidget(b)
        self.btn_max.setCursor(CURSOR_POINTING_HAND)
        self.btn_max.setFixedSize(38, 22)
        self.btn_max.setStyleSheet("padding: 1px 2px;")
        hbar.addWidget(self.btn_max)

        self.btn_snap_corner = QtWidgets.QToolButton(self._header_widget)
        self.btn_snap_corner.setText("BR")
        self.btn_snap_corner.setFixedSize(26, 22)
        self.btn_snap_corner.setCursor(CURSOR_POINTING_HAND)
        self.btn_snap_corner.clicked.connect(self.snap_to_bottom_right)
        self.btn_snap_corner.hide()
        hbar.addWidget(self.btn_snap_corner)

        self.btn_collapse = QtWidgets.QToolButton(self._header_widget)
        self.btn_collapse.setText("_")
        self.btn_collapse.setFixedSize(23, 22)
        self.btn_collapse.setCursor(CURSOR_POINTING_HAND)
        self.btn_collapse.clicked.connect(lambda: self.set_collapsed(True))
        hbar.addWidget(self.btn_collapse)

        self.btn_close = QtWidgets.QToolButton(self._header_widget)
        self.btn_close.setText("X")
        self.btn_close.setFixedSize(23, 22)
        self.btn_close.setCursor(CURSOR_POINTING_HAND)
        self.btn_close.clicked.connect(lambda: self.sessionCloseRequested.emit())
        hbar.addWidget(self.btn_close)

        root.addWidget(self._header_widget)

        # --- 2. Embedded Browser Viewport ---
        self.browser = StreetViewBrowserWidget(lang=self._lang, parent=self)
        self.browser.viewpointChanged.connect(self._on_browser_viewpoint_changed)
        self.browser.loadingChanged.connect(self._on_browser_loading_changed)
        self.browser.streetViewUnavailable.connect(lambda: self.set_status_message("status_no_sv"))
        self.browser.openExternalRequested.connect(lambda _u: self.openBrowserRequested.emit())
        root.addWidget(self.browser, 1)

        # --- 3. Compact Coordinate & Action Footer ---
        self._footer_widget = QtWidgets.QWidget(self)
        self._footer_widget.setFixedHeight(23)
        fbar = QtWidgets.QHBoxLayout(self._footer_widget)
        fbar.setContentsMargins(3, 0, 1, 0)
        fbar.setSpacing(3)

        self.lbl_status = QtWidgets.QLabel(self._footer_widget)
        self.lbl_status.setStyleSheet("color: #94a3b8; font-family: Consolas, monospace; font-size: 10px;")
        self.lbl_status.setMinimumWidth(90)
        fbar.addWidget(self.lbl_status, 1)

        self.btn_coverage = QtWidgets.QToolButton(self._footer_widget)
        self.btn_coverage.setCheckable(True)
        self.btn_coverage.setText("Cov")
        self.btn_coverage.clicked.connect(lambda chk: self.coverageToggled.emit(chk))

        self.btn_clean = QtWidgets.QToolButton(self._footer_widget)
        self.btn_clean.setCheckable(True)
        self.btn_clean.setChecked(True)
        self.btn_clean.setText("Cln")
        self.btn_clean.clicked.connect(self._on_clean_clicked)

        self.btn_follow = QtWidgets.QToolButton(self._footer_widget)
        self.btn_follow.setCheckable(True)
        self.btn_follow.setChecked(True)
        self.btn_follow.setText("Syn")
        self.btn_follow.clicked.connect(lambda chk: self.followToggled.emit(chk))

        self.btn_log_obs = QtWidgets.QToolButton(self._footer_widget)
        self.btn_log_obs.setText("+Pt")
        self.btn_log_obs.clicked.connect(lambda: self.saveObservationRequested.emit())

        self.btn_settings = QtWidgets.QToolButton(self._footer_widget)
        self.btn_settings.setText("Cfg")
        self.btn_settings.clicked.connect(lambda: self.settingsRequested.emit())

        self.btn_copy = QtWidgets.QToolButton(self._footer_widget)
        self.btn_copy.setText("Cpy")
        self.btn_copy.clicked.connect(lambda: self.copyCoordsRequested.emit())

        self.btn_open_ext = QtWidgets.QToolButton(self._footer_widget)
        self.btn_open_ext.setText("Web")
        self.btn_open_ext.clicked.connect(lambda: self.openBrowserRequested.emit())

        for b in (
            self.btn_coverage,
            self.btn_clean,
            self.btn_follow,
            self.btn_log_obs,
            self.btn_settings,
            self.btn_copy,
            self.btn_open_ext,
        ):
            b.setFixedHeight(19)
            b.setMinimumWidth(28)
            b.setCursor(CURSOR_POINTING_HAND)
            fbar.addWidget(b)

        root.addWidget(self._footer_widget)

        # --- 4. Collapsed Bottom-Right Pegman Pill ---
        self._pill_widget = QtWidgets.QWidget(self)
        self._pill_widget.setFixedHeight(30)
        pbar = QtWidgets.QHBoxLayout(self._pill_widget)
        pbar.setContentsMargins(4, 2, 4, 2)
        pbar.setSpacing(6)

        self.btn_pill_pegman = PegmanDragHandle(self._pill_widget)
        self.btn_pill_pegman.clicked.connect(lambda _chk: self.pegmanToolRequested.emit())
        self.btn_pill_pegman.dragStarted.connect(self.pegmanDragStarted.emit)
        self.btn_pill_pegman.dragEnded.connect(self.pegmanDragFinished.emit)
        pbar.addWidget(self.btn_pill_pegman)

        self.lbl_pill = QtWidgets.QLabel(self._pill_widget)
        self.lbl_pill.setStyleSheet("color: #f8fafc; font-weight: 700; font-size: 11px;")
        pbar.addWidget(self.lbl_pill, 1)

        self.btn_expand_pill = QtWidgets.QToolButton(self._pill_widget)
        self.btn_expand_pill.setText("^")
        self.btn_expand_pill.setFixedSize(24, 22)
        self.btn_expand_pill.setCursor(CURSOR_POINTING_HAND)
        self.btn_expand_pill.clicked.connect(lambda: self.set_collapsed(False))
        pbar.addWidget(self.btn_expand_pill)

        self._pill_widget.hide()
        root.addWidget(self._pill_widget)

    def _apply_language(self) -> None:
        self.lbl_title.setText(tr_text(self._lang, "pip_title"))
        self.lbl_pill.setText(tr_text(self._lang, "pill_label"))
        self.btn_pegman.setToolTip(tr_text(self._lang, "pegman_tooltip"))
        self.btn_pill_pegman.setToolTip(tr_text(self._lang, "pegman_tooltip"))
        self.grip_tl.setToolTip(tr_text(self._lang, "resize_grip_tooltip"))
        self.btn_s.setText(tr_text(self._lang, "preset_s"))
        self.btn_m.setText(tr_text(self._lang, "preset_m"))
        self.btn_l.setText(tr_text(self._lang, "preset_l"))
        self.btn_max.setText(tr_text(self._lang, "preset_max"))
        self.btn_max.setToolTip(tr_text(self._lang, "popout_tooltip"))
        self.btn_coverage.setToolTip(tr_text(self._lang, "coverage_tooltip"))
        self.btn_clean.setToolTip(tr_text(self._lang, "clean_mode_tooltip"))
        self.btn_follow.setToolTip(tr_text(self._lang, "follow_tooltip"))
        self.btn_log_obs.setToolTip(tr_text(self._lang, "log_obs_tooltip"))
        self.btn_snap_corner.setToolTip(tr_text(self._lang, "snap_corner_tooltip"))
        self.btn_dance.setToolTip(tr_text(self._lang, "dance_tooltip"))
        self.btn_settings.setToolTip(tr_text(self._lang, "settings_tooltip"))
        self.btn_collapse.setToolTip(tr_text(self._lang, "collapse_tooltip"))
        self.btn_close.setToolTip(tr_text(self._lang, "close_tooltip"))
        self.btn_copy.setToolTip(tr_text(self._lang, "copy_coords_tooltip"))
        self.btn_open_ext.setToolTip(tr_text(self._lang, "open_browser_tooltip"))
        if self._current_pose is None:
            self.lbl_status.setText(tr_text(self._lang, "status_ready"))
        self.browser.set_language(self._lang)

    def set_language(self, lang: str) -> None:
        self._lang = lang
        self._apply_language()

    def set_pegman_armed(self, armed: bool) -> None:
        self.btn_pegman.setChecked(armed)
        self.btn_pill_pegman.setChecked(armed)

    def set_coverage_checked(self, checked: bool) -> None:
        self.btn_coverage.setChecked(checked)

    def set_clean_checked(self, checked: bool) -> None:
        self.btn_clean.setChecked(checked)
        self.browser.set_clean_mode(checked)

    def set_follow_checked(self, checked: bool) -> None:
        self.btn_follow.setChecked(checked)

    def _on_clean_clicked(self, checked: bool) -> None:
        self.browser.set_clean_mode(checked)
        self.cleanModeToggled.emit(checked)

    def set_status_hover(self, x5253: float, y5253: float, lat: float, lon: float) -> None:
        self.lbl_status.setText(
            tr_text(self._lang, "status_hover", x=x5253, y=y5253, lat=lat, lon=lon)
        )

    def set_status_message(self, key: str) -> None:
        self.lbl_status.setText(tr_text(self._lang, key))

    def load_street_view(
        self,
        lat: float,
        lon: float,
        heading: float = 0.0,
        pitch: float = 0.0,
        fov: float = 85.0,
        provider: str = "google_direct",
        api_key: str = "",
    ) -> str:
        if self._collapsed:
            self.set_collapsed(False)
        if not self.isVisible():
            self.show()
        self.raise_()
        url = self.browser.load_location(
            lat=lat,
            lon=lon,
            heading=heading,
            pitch=pitch,
            fov=fov,
            provider=provider,
            api_key=api_key,
        )
        pose = StreetViewState(lat=lat, lon=lon, heading=heading, pitch=pitch, fov=fov, url=url)
        self._update_pose_readout(pose)
        return url

    def _on_browser_loading_changed(self, loading: bool) -> None:
        if loading and self._current_pose is None:
            self.set_status_message("status_loading")
        elif not loading and self._current_pose is not None:
            self._update_pose_readout(self._current_pose)

    def _on_browser_viewpoint_changed(self, pose: StreetViewState) -> None:
        self._update_pose_readout(pose)
        self.viewpointChanged.emit(pose)

    def _update_pose_readout(self, pose: StreetViewState) -> None:
        self._current_pose = pose
        x5253, y5253 = wgs84_to_epsg5253(pose.lat, pose.lon)
        self.lbl_status.setText(
            tr_text(
                self._lang,
                "status_live",
                x=x5253,
                y=y5253,
                lat=pose.lat,
                lon=pose.lon,
                hdg=pose.heading,
            )
        )

    def current_pose(self) -> Optional[StreetViewState]:
        return self._current_pose

    def reset_session(self) -> None:
        self._current_pose = None
        self.browser.reset_view()
        self.lbl_status.setText(tr_text(self._lang, "status_ready"))
        self.hide()

    # --- Sizing, Collapsing & Bottom-Right Anchoring ---

    def _max_canvas_bounds(self) -> Tuple[int, int]:
        if self._canvas is None:
            return (1200, 800)
        return (
            max(self.MIN_WIDTH, self._canvas.width() - 20),
            max(self.MIN_HEIGHT, self._canvas.height() - 20),
        )

    def apply_size_preset(self, preset: str) -> None:
        if self._collapsed:
            self.set_collapsed(False)
        self._maximized = False
        w, h = SIZE_PRESETS.get(preset, SIZE_PRESETS["M"])
        max_w, max_h = self._max_canvas_bounds()
        w = min(w, max_w)
        h = min(h, max_h)
        self._expanded_size = QtCore.QSize(w, h)
        self.resize(self._expanded_size)
        self.reposition_in_canvas()

    def toggle_maximize(self) -> None:
        if self._collapsed:
            self.set_collapsed(False)
        if not self._maximized:
            self._pre_max_size = QtCore.QSize(self.size())
            max_w, max_h = self._max_canvas_bounds()
            target_w = max(self.MIN_WIDTH, int(max_w * 0.88))
            target_h = max(self.MIN_HEIGHT, int(max_h * 0.86))
            self._maximized = True
            self._anchored_bottom_right = True
            self.btn_snap_corner.hide()
            self._expanded_size = QtCore.QSize(target_w, target_h)
            self.resize(self._expanded_size)
        else:
            self._maximized = False
            self._expanded_size = QtCore.QSize(self._pre_max_size)
            self.resize(self._expanded_size)
        self.reposition_in_canvas()

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = bool(collapsed)
        if self._collapsed:
            if self.height() > self.PILL_HEIGHT + 20:
                self._expanded_size = QtCore.QSize(self.size())
            self._header_widget.hide()
            self.browser.hide()
            self._footer_widget.hide()
            self._pill_widget.show()
            self.setFixedSize(self.PILL_WIDTH, self.PILL_HEIGHT)
        else:
            self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
            self.setMaximumSize(16777215, 16777215)
            self._pill_widget.hide()
            self._header_widget.show()
            self.browser.show()
            self._footer_widget.show()
            self.resize(self._expanded_size)
        self.reposition_in_canvas()

    def is_collapsed(self) -> bool:
        return self._collapsed

    def snap_to_bottom_right(self) -> None:
        self._anchored_bottom_right = True
        self.btn_snap_corner.hide()
        self.reposition_in_canvas()

    def reposition_in_canvas(self) -> None:
        if self._canvas is None:
            return
        cw = self._canvas.width()
        ch = self._canvas.height()
        if cw <= 0 or ch <= 0:
            return

        if self._anchored_bottom_right:
            x = max(8, cw - self.width() - self._right_margin)
            y = max(8, ch - self.height() - self._bottom_margin)
            self.move(x, y)
        else:
            x = max(8, min(self.x(), max(8, cw - self.width() - 8)))
            y = max(8, min(self.y(), max(8, ch - self.height() - 8)))
            self.move(x, y)

    def _resize_from_top_left(self, dx: int, dy: int) -> None:
        if self._collapsed:
            return
        self._maximized = False
        max_w, max_h = self._max_canvas_bounds()
        geom = self.geometry()
        right = geom.x() + geom.width()
        bottom = geom.y() + geom.height()

        new_w = max(self.MIN_WIDTH, min(max_w, geom.width() - dx))
        new_h = max(self.MIN_HEIGHT, min(max_h, geom.height() - dy))
        new_x = max(8, right - new_w)
        new_y = max(8, bottom - new_h)
        new_w = right - new_x
        new_h = bottom - new_y

        self._expanded_size = QtCore.QSize(new_w, new_h)
        self.setGeometry(new_x, new_y, new_w, new_h)

    def _hit_test_edge(self, pos: QtCore.QPoint) -> Optional[str]:
        if self._collapsed:
            return None
        b = self.BORDER_HIT
        left = pos.x() <= b
        top = pos.y() <= b
        right = pos.x() >= self.width() - b
        bottom = pos.y() >= self.height() - b
        if left and top:
            return "tl"
        if left:
            return "l"
        if top:
            return "t"
        if right and bottom:
            return "br"
        if right:
            return "r"
        if bottom:
            return "b"
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() == LEFT_BUTTON:
            edge = self._hit_test_edge(event_pos(event))
            if edge is not None:
                self._edge_resize_mode = edge
                self._drag_origin_global = event_global_pos(event)
                self._drag_start_geom = QtCore.QRect(self.geometry())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._edge_resize_mode and self._drag_origin_global and self._drag_start_geom:
            delta = event_global_pos(event) - self._drag_origin_global
            g = self._drag_start_geom
            max_w, max_h = self._max_canvas_bounds()
            x, y, w, h = g.x(), g.y(), g.width(), g.height()
            mode = self._edge_resize_mode

            if "l" in mode:
                right = g.x() + g.width()
                w = max(self.MIN_WIDTH, min(max_w, g.width() - delta.x()))
                x = max(8, right - w)
                w = right - x
            if "t" in mode:
                bottom = g.y() + g.height()
                h = max(self.MIN_HEIGHT, min(max_h, g.height() - delta.y()))
                y = max(8, bottom - h)
                h = bottom - y
            if "r" in mode:
                w = max(self.MIN_WIDTH, min(max_w, g.width() + delta.x()))
            if "b" in mode:
                h = max(self.MIN_HEIGHT, min(max_h, g.height() + delta.y()))

            self._maximized = False
            self._expanded_size = QtCore.QSize(w, h)
            self.setGeometry(x, y, w, h)
            event.accept()
            return

        edge = self._hit_test_edge(event_pos(event))
        if edge in ("tl", "br"):
            self.setCursor(CURSOR_SIZE_FDIAG)
        elif edge in ("l", "r"):
            self.setCursor(CURSOR_SIZE_HOR)
        elif edge in ("t", "b"):
            self.setCursor(CURSOR_SIZE_VER)
        else:
            self.setCursor(CURSOR_ARROW)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._edge_resize_mode = None
        self._drag_origin_global = None
        self._drag_start_geom = None
        super().mouseReleaseEvent(event)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._canvas and event.type() == EVENT_RESIZE:
            self.reposition_in_canvas()
        elif obj is self._header_widget:
            et = event.type()
            et_press = getattr(QtCore.QEvent, "Type", QtCore.QEvent).MouseButtonPress
            et_move = getattr(QtCore.QEvent, "Type", QtCore.QEvent).MouseMove
            et_rel = getattr(QtCore.QEvent, "Type", QtCore.QEvent).MouseButtonRelease
            if et == et_press and event.button() == LEFT_BUTTON:
                child = self._header_widget.childAt(event_pos(event))
                if child is None or child is self.lbl_title:
                    self._move_dragging = True
                    self._drag_origin_global = event_global_pos(event)
                    self._drag_start_geom = QtCore.QRect(self.geometry())
                    return True
            elif et == et_move and self._move_dragging and self._drag_origin_global and self._drag_start_geom:
                delta = event_global_pos(event) - self._drag_origin_global
                new_x = self._drag_start_geom.x() + delta.x()
                new_y = self._drag_start_geom.y() + delta.y()
                if self._canvas is not None:
                    new_x = max(8, min(new_x, max(8, self._canvas.width() - self.width() - 8)))
                    new_y = max(8, min(new_y, max(8, self._canvas.height() - self.height() - 8)))
                self._anchored_bottom_right = False
                self.btn_snap_corner.show()
                self.move(new_x, new_y)
                return True
            elif et == et_rel and self._move_dragging:
                self._move_dragging = False
                self._drag_origin_global = None
                self._drag_start_geom = None
                return True
        return super().eventFilter(obj, event)

    def cleanup(self) -> None:
        if self._canvas is not None:
            try:
                self._canvas.removeEventFilter(self)
            except Exception as exc:
                log_debug(f"PiP canvas event filter removal warning: {exc}")
        self.browser.cleanup()
