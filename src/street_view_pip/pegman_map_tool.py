# -*- coding: utf-8 -*-
"""
Interactive One-Shot Pegman Map Tool for QGIS Map Canvas.

Supports single-drop arming ("drop once, then immediately restore normal QGIS pan"):
  1. Single Click -> Drops Pegman once at clicked location (auto-aligns heading
     with nearest loaded road layer if enabled) and disarms back to Pan/Select.
  2. Click + Drag -> Aims Pegman's viewing cone directly toward the dragged
     azimuth and drops once into Street View facing that direction.
"""

from typing import Optional

from qgis.PyQt import QtCore, QtGui
from qgis.core import QgsPointXY
from qgis.gui import QgsMapCanvas, QgsMapTool

from .canvas_items import CanvasPoseOverlay
from .geo_utils import (
    bearing_between_wgs84,
    canvas_to_epsg5253,
    canvas_to_wgs84,
    snap_to_nearest_road_azimuth,
    snap_to_nearest_road_detail,
)
from .qt_compat import (
    ANTIALIASING,
    BRUSH_SOLID,
    LEFT_BUTTON,
    PEN_SOLID,
    RIGHT_BUTTON,
    TRANSPARENT_BG,
)


def create_pegman_cursor() -> QtGui.QCursor:
    """Programmatically paint a high-DPI yellow Pegman cursor with drop shadow."""
    size = 36
    pm = QtGui.QPixmap(size, size)
    pm.fill(TRANSPARENT_BG)
    painter = QtGui.QPainter(pm)
    painter.setRenderHint(ANTIALIASING, True)

    # Subtle ground drop-ring at hotspot (bottom-center: 18, 31)
    painter.setPen(QtGui.QPen(QtGui.QColor("#38bdf8"), 2.0, PEN_SOLID))
    painter.setBrush(QtGui.QBrush(QtGui.QColor(56, 189, 248, 90), BRUSH_SOLID))
    painter.drawEllipse(QtCore.QPointF(18.0, 31.0), 6.0, 3.0)

    # Yellow Pegman figure
    painter.setPen(QtGui.QPen(QtGui.QColor("#713f12"), 1.6, PEN_SOLID))
    painter.setBrush(QtGui.QBrush(QtGui.QColor("#facc15"), BRUSH_SOLID))
    painter.drawEllipse(QtCore.QPointF(18.0, 8.0), 4.8, 4.8)

    body = QtGui.QPainterPath()
    body.moveTo(11.0, 15.5)
    body.quadTo(18.0, 12.5, 25.0, 15.5)
    body.lineTo(24.0, 23.0)
    body.lineTo(21.0, 23.0)
    body.lineTo(21.0, 30.0)
    body.lineTo(15.0, 30.0)
    body.lineTo(15.0, 23.0)
    body.lineTo(12.0, 23.0)
    body.closeSubpath()
    painter.drawPath(body)
    painter.end()
    return QtGui.QCursor(pm, 18, 31)


class PegmanMapTool(QgsMapTool):
    """QgsMapTool allowing single-shot click drop or click-drag directional aiming."""

    pegmanDropped = QtCore.pyqtSignal(float, float, float)  # lat, lon, heading
    cursorMoved = QtCore.pyqtSignal(float, float, float, float)  # x5253, y5253, lat, lon
    deactivatedTool = QtCore.pyqtSignal()

    def __init__(
        self,
        canvas: QgsMapCanvas,
        overlay: CanvasPoseOverlay,
        snap_road_fn=None,
        one_shot: bool = True,
    ):
        super().__init__(canvas)
        self._canvas = canvas
        self._overlay = overlay
        self._snap_road_fn = snap_road_fn
        self._one_shot = bool(one_shot)
        self._cursor = create_pegman_cursor()
        self.setCursor(self._cursor)

        self._dragging = False
        self._origin_pt: Optional[QgsPointXY] = None
        self._origin_lat: float = 0.0
        self._origin_lon: float = 0.0
        self._drag_heading: Optional[float] = None

    def set_one_shot(self, one_shot: bool) -> None:
        self._one_shot = bool(one_shot)

    def is_one_shot(self) -> bool:
        return self._one_shot

    def activate(self) -> None:
        super().activate()
        self._canvas.setCursor(self._cursor)

    def deactivate(self) -> None:
        self._dragging = False
        self._origin_pt = None
        self._drag_heading = None
        self._overlay.clear_drag_aim()
        self._overlay.hide_drop_reticle()
        super().deactivate()
        self.deactivatedTool.emit()

    def canvasMoveEvent(self, event) -> None:
        map_pt = self.toMapCoordinates(event.pos())
        canvas_crs = self._canvas.mapSettings().destinationCrs()
        lat, lon = canvas_to_wgs84(map_pt, canvas_crs)
        x5253, y5253 = canvas_to_epsg5253(map_pt, canvas_crs)
        self.cursorMoved.emit(x5253, y5253, lat, lon)

        if self._dragging and self._origin_pt is not None:
            px_origin = self.toCanvasCoordinates(self._origin_pt)
            dx = event.pos().x() - px_origin.x()
            dy = event.pos().y() - px_origin.y()
            if (dx * dx + dy * dy) >= 64:  # >= 8 px drag defines explicit heading
                hdg = bearing_between_wgs84(self._origin_lat, self._origin_lon, lat, lon)
                self._drag_heading = hdg
                self._overlay.update_drag_aim(
                    self._origin_lat,
                    self._origin_lon,
                    self._origin_pt,
                    map_pt,
                    hdg,
                )
        else:
            self._overlay.show_drop_reticle(map_pt)

    def canvasPressEvent(self, event) -> None:
        if event.button() == RIGHT_BUTTON:
            self._canvas.unsetMapTool(self)
            return
        if event.button() != LEFT_BUTTON:
            return
        map_pt = self.toMapCoordinates(event.pos())
        canvas_crs = self._canvas.mapSettings().destinationCrs()
        lat, lon = canvas_to_wgs84(map_pt, canvas_crs)
        self._dragging = True
        self._origin_pt = QgsPointXY(map_pt)
        self._origin_lat = lat
        self._origin_lon = lon
        self._drag_heading = None
        self._overlay.hide_drop_reticle()

    def canvasReleaseEvent(self, event) -> None:
        if event.button() != LEFT_BUTTON or not self._dragging:
            return
        self._dragging = False
        self._overlay.clear_drag_aim()
        self._overlay.hide_drop_reticle()

        heading = self._drag_heading
        lat, lon = self._origin_lat, self._origin_lon
        if heading is None:
            should_snap = bool(self._snap_road_fn()) if callable(self._snap_road_fn) else True
            if should_snap:
                snapped = snap_to_nearest_road_detail(lat, lon, max_distance_m=18.0)
                if snapped is not None:
                    lat, lon, heading = snapped
                else:
                    heading = snap_to_nearest_road_azimuth(lat, lon, max_distance_m=35.0)
        if heading is None:
            heading = 0.0

        self._origin_pt = None
        self._drag_heading = None

        self.pegmanDropped.emit(lat, lon, float(heading))
        if self._one_shot and self._canvas.mapTool() is self:
            self._canvas.unsetMapTool(self)
