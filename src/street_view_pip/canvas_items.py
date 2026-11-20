# -*- coding: utf-8 -*-
"""
3D-Shaded Cowboy Pegman Canvas Overlays (Grab-by-Hand, Walk/Run, 30s Wave & Johnny Bravo Monkey Dance).

Features:
  - Sculpted 3D-shaded golden Pegman with brown cowboy hat, red bandana, cast ground
    shadow, and NO face/eyes.
  - Direct on-canvas grab: Pegman's raised hand teleports straight to the cursor tip
    ("held by the hand") while the ground reticle tracks directly beneath his boots.
  - Distance-aware gait: walking stride for nearby steps (<= 28m) and forward-leaning
    sprint animation with speed trails for far jumps (> 28m).
  - Idle wave animation after 30 seconds stationary.
  - Confetti "Do the Monkey!" Johnny Bravo dance mode with burst confetti ribbons!
"""

import math
import time
from typing import Optional

from qgis.PyQt import QtCore, QtGui
from qgis.core import QgsGeometry, QgsPointXY
from qgis.gui import QgsMapCanvas, QgsMapCanvasItem, QgsRubberBand

from .geo_utils import build_fov_cone_polygon, geodesic_distance_m, wgs84_to_canvas
from .qt_compat import (
    ANTIALIASING,
    BRUSH_SOLID,
    GEOM_LINE,
    GEOM_POLYGON,
    NO_PEN,
    PEN_DASH,
    PEN_SOLID,
    log_debug,
)

IDLE_WAVE_DELAY_SEC = 30.0
IDLE_WAVE_DURATION_SEC = 4.5
IDLE_WAVE_REPEAT_SEC = 12.0
RUN_DISTANCE_THRESHOLD_M = 28.0
DANCE_DURATION_SEC = 7.0
LIFTED_BOOT_DROP_OFFSET_PX = 34


def _make_3d_gold_head_brush(cx: float, cy: float, r: float) -> QtGui.QBrush:
    grad = QtGui.QRadialGradient(cx - r * 0.32, cy - r * 0.35, r * 1.45)
    grad.setColorAt(0.0, QtGui.QColor("#fef9c3"))
    grad.setColorAt(0.45, QtGui.QColor("#facc15"))
    grad.setColorAt(1.0, QtGui.QColor("#b45309"))
    return QtGui.QBrush(grad)


def _make_3d_gold_body_brush(x0: float, x1: float) -> QtGui.QBrush:
    grad = QtGui.QLinearGradient(x0, -18.0, x1, -2.0)
    grad.setColorAt(0.0, QtGui.QColor("#fef08a"))
    grad.setColorAt(0.45, QtGui.QColor("#facc15"))
    grad.setColorAt(1.0, QtGui.QColor("#b45309"))
    return QtGui.QBrush(grad)


def _make_3d_hat_brush(w: float) -> QtGui.QBrush:
    grad = QtGui.QLinearGradient(-w, -8.0, w, 4.0)
    grad.setColorAt(0.0, QtGui.QColor("#d97706"))
    grad.setColorAt(0.45, QtGui.QColor("#78350f"))
    grad.setColorAt(1.0, QtGui.QColor("#451a03"))
    return QtGui.QBrush(grad)


def _make_3d_bandana_brush(w: float) -> QtGui.QBrush:
    grad = QtGui.QLinearGradient(-w, -18.0, w, -10.0)
    grad.setColorAt(0.0, QtGui.QColor("#f87171"))
    grad.setColorAt(0.5, QtGui.QColor("#dc2626"))
    grad.setColorAt(1.0, QtGui.QColor("#7f1d1d"))
    return QtGui.QBrush(grad)


def _draw_cowboy_hat(painter: QtGui.QPainter, scale_x: float = 1.0) -> None:
    """Draw a 3D-shaded pinched-crown cowboy hat with red hatband (centered on head)."""
    painter.save()
    outline = QtGui.QPen(QtGui.QColor("#291507"), 1.35, PEN_SOLID)
    painter.setPen(outline)
    painter.setBrush(_make_3d_hat_brush(9.5 * scale_x))

    # Swept 3D cowboy brim + pinched crown
    hat = QtGui.QPainterPath()
    bw = 9.6 * max(0.82, scale_x)
    cw = 4.9 * max(0.78, scale_x)
    hat.moveTo(-bw, -3.2)
    hat.quadTo(0.0, -0.4, bw, -3.2)
    hat.quadTo(bw * 0.85, -5.8, cw, -5.2)
    hat.lineTo(cw * 0.72, -10.2)
    hat.quadTo(0.0, -8.6, -cw * 0.72, -10.2)
    hat.lineTo(-cw, -5.2)
    hat.quadTo(-bw * 0.85, -5.8, -bw, -3.2)
    hat.closeSubpath()
    painter.drawPath(hat)

    # Red hatband accent
    band_pen = QtGui.QPen(QtGui.QColor("#dc2626"), 1.6, PEN_SOLID)
    painter.setPen(band_pen)
    painter.drawLine(QtCore.QPointF(-cw * 0.92, -5.2), QtCore.QPointF(cw * 0.92, -5.2))
    painter.restore()


class PegmanCanvasMarker(QgsMapCanvasItem):
    """3D-shaded cowboy Pegman supporting grab-by-hand, walk/run, 30s wave & Monkey dance."""

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self._canvas = canvas
        self._map_point: Optional[QgsPointXY] = None
        self._heading: float = 0.0
        self._turn_velocity: float = 0.0
        self._walk_phase: float = 0.0
        self._walk_amount: float = 0.0
        self._running: bool = False
        self._lifted: bool = False
        self._dangle_tilt: float = 0.0
        self._waving: bool = False
        self._wave_phase: float = 0.0
        self._dancing: bool = False
        self._dance_phase: float = 0.0
        self._visible_marker: bool = False
        self.setZValue(120)

    def set_pose(
        self,
        map_point: QgsPointXY,
        heading: float = 0.0,
        turn_velocity: float = 0.0,
        walk_phase: float = 0.0,
        walk_amount: float = 0.0,
        running: bool = False,
        lifted: bool = False,
        dangle_tilt: float = 0.0,
        waving: bool = False,
        wave_phase: float = 0.0,
        dancing: bool = False,
        dance_phase: float = 0.0,
    ) -> None:
        self._map_point = QgsPointXY(map_point)
        self._heading = float(heading) % 360.0
        self._turn_velocity = max(-1.0, min(1.0, float(turn_velocity)))
        self._walk_phase = float(walk_phase)
        self._walk_amount = max(0.0, min(1.0, float(walk_amount)))
        self._running = bool(running)
        self._lifted = bool(lifted)
        self._dangle_tilt = max(-22.0, min(22.0, float(dangle_tilt)))
        self._waving = bool(waving)
        self._wave_phase = float(wave_phase)
        self._dancing = bool(dancing)
        self._dance_phase = float(dance_phase)
        self._visible_marker = True
        self.setPos(self.toCanvasCoordinates(self._map_point))
        self.show()
        self.update()

    def is_visible_marker(self) -> bool:
        return self._visible_marker

    def hit_test_canvas_point(self, viewport_pt: QtCore.QPointF) -> bool:
        """Return True if viewport_pt is directly over Pegman's body, hat, or arms."""
        if not self._visible_marker or self._map_point is None:
            return False
        anchor = self.toCanvasCoordinates(self._map_point)
        dx = viewport_pt.x() - anchor.x()
        dy = viewport_pt.y() - anchor.y()
        return (-20.0 <= dx <= 20.0) and (-46.0 <= dy <= 10.0)

    def clear(self) -> None:
        self._visible_marker = False
        self._map_point = None
        self._waving = False
        self._lifted = False
        self._running = False
        self._dancing = False
        self.hide()

    def updatePosition(self) -> None:
        if self._visible_marker and self._map_point is not None:
            self.setPos(self.toCanvasCoordinates(self._map_point))

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(-44.0, -56.0, 88.0, 96.0)

    def paint(self, painter: QtGui.QPainter, option=None, widget=None) -> None:
        if not self._visible_marker:
            return
        painter.save()
        painter.setRenderHint(ANTIALIASING, True)

        outline = QtGui.QPen(QtGui.QColor("#291507"), 1.55, PEN_SOLID)
        body_brush = _make_3d_gold_body_brush(-8.0, 8.0)

        # --- Special Pose 1: Held by Hand (Cursor Tip Locked Directly to Raised Hand!) ---
        if self._lifted:
            # Shift downward by +34px so his raised hand tip sits right at (0, 0) = cursor!
            painter.translate(-4.0, float(LIFTED_BOOT_DROP_OFFSET_PX) - 2.0)
            painter.rotate(14.0 + self._dangle_tilt)

            # Dangling 3D legs
            painter.setPen(outline)
            painter.setBrush(body_brush)
            painter.save()
            painter.translate(-2.4, -9.0)
            painter.rotate(12.0 + self._dangle_tilt * 0.45)
            painter.drawRoundedRect(QtCore.QRectF(-1.7, 0.0, 3.4, 9.2), 1.5, 1.5)
            painter.restore()
            painter.save()
            painter.translate(2.5, -9.0)
            painter.rotate(-9.0 + self._dangle_tilt * 0.45)
            painter.drawRoundedRect(QtCore.QRectF(-1.7, 0.0, 3.4, 9.2), 1.5, 1.5)
            painter.restore()

            # 3D Torso
            torso = QtGui.QPainterPath()
            torso.moveTo(-6.8, -17.0)
            torso.quadTo(0.0, -19.8, 6.8, -17.0)
            torso.lineTo(5.8, -8.2)
            torso.lineTo(-5.8, -8.2)
            torso.closeSubpath()
            painter.drawPath(torso)

            # Red Bandana
            painter.setBrush(_make_3d_bandana_brush(5.2))
            scarf = QtGui.QPainterPath()
            scarf.moveTo(-5.0, -17.4)
            scarf.lineTo(5.0, -17.4)
            scarf.lineTo(0.0, -11.4)
            scarf.closeSubpath()
            painter.drawPath(scarf)

            # Loose left arm
            painter.setBrush(body_brush)
            painter.save()
            painter.translate(-6.4, -16.2)
            painter.rotate(14.0)
            painter.drawRoundedRect(QtCore.QRectF(-1.5, 0.0, 3.0, 8.4), 1.4, 1.4)
            painter.restore()

            # Raised right arm reaching straight to cursor (0, 0)
            painter.save()
            painter.translate(5.0, -16.4)
            painter.rotate(-172.0)
            painter.drawRoundedRect(QtCore.QRectF(-1.5, 0.0, 3.1, 13.5), 1.4, 1.4)
            painter.restore()

            # Eyeless 3D Head + Cowboy Hat
            painter.save()
            painter.translate(-0.5, -24.2)
            painter.setBrush(_make_3d_gold_head_brush(0.0, 0.0, 5.4))
            painter.drawEllipse(QtCore.QPointF(0.0, 0.0), 5.4, 5.4)
            _draw_cowboy_hat(painter, scale_x=1.0)
            painter.restore()

            painter.restore()
            return

        # --- Ground Anchor & 3D Directional Cast Shadow (Image 2 style!) ---
        painter.setPen(QtGui.QPen(QtGui.QColor("#0f172a"), 1.8, PEN_SOLID))
        painter.setBrush(QtGui.QBrush(QtGui.QColor(56, 189, 248, 210), BRUSH_SOLID))
        painter.drawEllipse(QtCore.QPointF(0.0, 0.0), 6.2, 6.2)

        # 3D cast ground shadow polygon pointing opposite the light
        painter.setPen(NO_PEN)
        painter.setBrush(QtGui.QBrush(QtGui.QColor(15, 23, 42, 135), BRUSH_SOLID))
        shadow_poly = QtGui.QPolygonF([
            QtCore.QPointF(-4.0, 0.5),
            QtCore.QPointF(4.0, 0.5),
            QtCore.QPointF(-11.0, 7.2),
        ])
        painter.drawPolygon(shadow_poly)

        # --- Special Pose 2: Johnny Bravo "Do the Monkey!" Dance + Confetti! ---
        if self._dancing:
            t = self._dance_phase
            # Confetti burst floating around Pegman
            confetti_colors = ("#ec4899", "#38bdf8", "#facc15", "#22c55e", "#f97316")
            for idx in range(10):
                ang = idx * 0.63 + t * 0.25
                rad_c = 14.0 + ((idx * 7 + t * 14.0) % 20.0)
                cx = math.cos(ang) * rad_c
                cy = -18.0 - abs(math.sin(ang + t * 0.4)) * rad_c * 0.85
                painter.save()
                painter.translate(cx, cy)
                painter.rotate(idx * 42.0 + t * 90.0)
                painter.setBrush(QtGui.QBrush(QtGui.QColor(confetti_colors[idx % len(confetti_colors)]), BRUSH_SOLID))
                if idx % 2 == 0:
                    painter.drawRoundedRect(QtCore.QRectF(-2.6, -1.1, 5.2, 2.2), 0.7, 0.7)
                else:
                    painter.drawEllipse(QtCore.QPointF(0.0, 0.0), 1.8, 1.8)
                painter.restore()

            # Johnny Bravo alternating groove: Monkey Pump <-> Muscle/Hair Flex!
            beat_cycle = (t * 1.4) % 4.0
            is_flex = beat_cycle >= 2.8
            hop = abs(math.sin(t * 7.5)) * 3.8
            sway_x = math.sin(t * 3.75) * 3.5
            hip_tilt = math.sin(t * 3.75) * 16.0

            painter.translate(sway_x, -hop)
            painter.rotate(hip_tilt)

            # Wide-stance dancing legs
            painter.setPen(outline)
            painter.setBrush(body_brush)
            knee_l = math.sin(t * 7.5) * 24.0
            knee_r = -math.sin(t * 7.5) * 24.0
            painter.save()
            painter.translate(-3.4, -8.5)
            painter.rotate(knee_l)
            painter.drawRoundedRect(QtCore.QRectF(-1.7, 0.0, 3.4, 8.4), 1.4, 1.4)
            painter.restore()
            painter.save()
            painter.translate(3.4, -8.5)
            painter.rotate(knee_r)
            painter.drawRoundedRect(QtCore.QRectF(-1.7, 0.0, 3.4, 8.4), 1.4, 1.4)
            painter.restore()

            # Chest-out 3D torso
            torso = QtGui.QPainterPath()
            torso.moveTo(-8.2, -17.0)
            torso.quadTo(0.0, -20.2, 8.2, -17.0)
            torso.lineTo(6.2, -8.0)
            torso.lineTo(-6.2, -8.0)
            torso.closeSubpath()
            painter.drawPath(torso)

            # Red bandana
            painter.setBrush(_make_3d_bandana_brush(5.6))
            scarf = QtGui.QPainterPath()
            scarf.moveTo(-5.4, -17.4)
            scarf.lineTo(5.4, -17.4)
            scarf.lineTo(0.0, -11.2)
            scarf.closeSubpath()
            painter.drawPath(scarf)

            # Monkey pumping arms OR Johnny Bravo flex pose!
            painter.setBrush(body_brush)
            if is_flex:
                # Left arm muscle flex up, right hand on hip!
                painter.save()
                painter.translate(-7.5, -16.0)
                painter.rotate(-135.0)
                painter.drawRoundedRect(QtCore.QRectF(-1.5, 0.0, 3.0, 9.2), 1.4, 1.4)
                painter.restore()
                painter.save()
                painter.translate(7.5, -15.5)
                painter.rotate(35.0)
                painter.drawRoundedRect(QtCore.QRectF(-1.5, 0.0, 3.0, 8.0), 1.4, 1.4)
                painter.restore()
            else:
                # Classic asynchronous Monkey arm pump!
                pump_l = -110.0 + math.sin(t * 10.5) * 48.0
                pump_r = -110.0 - math.sin(t * 10.5) * 48.0
                painter.save()
                painter.translate(-7.4, -15.8)
                painter.rotate(pump_l)
                painter.drawRoundedRect(QtCore.QRectF(-1.5, 0.0, 3.0, 8.8), 1.4, 1.4)
                painter.restore()
                painter.save()
                painter.translate(7.4, -15.8)
                painter.rotate(pump_r)
                painter.drawRoundedRect(QtCore.QRectF(-1.5, 0.0, 3.0, 8.8), 1.4, 1.4)
                painter.restore()

            # Head snap + Cowboy hat bounce
            painter.save()
            painter.translate(math.sin(t * 7.5) * 1.6, -24.6)
            painter.rotate(-hip_tilt * 0.45)
            painter.setBrush(_make_3d_gold_head_brush(0.0, 0.0, 5.4))
            painter.drawEllipse(QtCore.QPointF(0.0, 0.0), 5.4, 5.4)
            _draw_cowboy_hat(painter, scale_x=1.0)
            painter.restore()

            painter.restore()
            return

        # --- Normal Grounded Poses: 3D Look / Walk / Run / 30s Idle Wave ---
        if self._waving:
            dir_x, dir_y = 0.0, 1.0
            torso_scale_x = 1.0
            body_tilt = math.sin(self._wave_phase * 0.5) * 3.0
            head_shift_x = 0.0
            head_tilt = math.sin(self._wave_phase * 0.5) * 4.0
        else:
            rad = math.radians(self._heading)
            dir_x = math.sin(rad)
            dir_y = -math.cos(rad)
            torso_scale_x = 0.66 + 0.34 * abs(dir_y)
            sprint_lean = (dir_x * 13.0) if (self._running and self._walk_amount > 0.2) else 0.0
            body_tilt = self._turn_velocity * 4.5 + sprint_lean
            head_shift_x = dir_x * 2.5 + self._turn_velocity * 1.8
            head_tilt = self._turn_velocity * 9.0

        bounce_amp = 3.2 if self._running else 1.7
        bob_y = -abs(math.sin(self._walk_phase)) * bounce_amp * self._walk_amount

        if self._running and self._walk_amount > 0.25 and not self._waving:
            painter.save()
            trail_pen = QtGui.QPen(QtGui.QColor(56, 189, 248, 200), 1.9, PEN_SOLID)
            painter.setPen(trail_pen)
            tx = -dir_x * 11.0
            ty = -dir_y * 5.0 - 10.0
            painter.drawLine(QtCore.QPointF(tx, ty - 4.0), QtCore.QPointF(tx - dir_x * 7.5, ty - 4.0))
            painter.drawLine(QtCore.QPointF(tx, ty + 1.0), QtCore.QPointF(tx - dir_x * 9.5, ty + 1.0))
            painter.restore()

        painter.translate(0.0, bob_y)
        painter.rotate(body_tilt)

        # --- 3D Legs ---
        painter.setPen(outline)
        painter.setBrush(body_brush)
        leg_swing_deg = (math.sin(self._walk_phase) * (36.0 if self._running else 18.0)) * self._walk_amount
        leg_w = max(2.6, 3.2 * torso_scale_x)

        painter.save()
        painter.translate(-2.4 * torso_scale_x, -8.5)
        painter.rotate(leg_swing_deg)
        painter.drawRoundedRect(QtCore.QRectF(-leg_w * 0.5, 0.0, leg_w, 8.0), 1.4, 1.4)
        painter.restore()

        painter.save()
        painter.translate(2.4 * torso_scale_x, -8.5)
        painter.rotate(-leg_swing_deg)
        painter.drawRoundedRect(QtCore.QRectF(-leg_w * 0.5, 0.0, leg_w, 8.0), 1.4, 1.4)
        painter.restore()

        # --- 3D Torso ---
        hw = 7.4 * torso_scale_x
        torso = QtGui.QPainterPath()
        torso.moveTo(-hw, -16.5)
        torso.quadTo(0.0, -19.5, hw, -16.5)
        torso.lineTo(hw * 0.86, -7.8)
        torso.lineTo(-hw * 0.86, -7.8)
        torso.closeSubpath()
        painter.drawPath(torso)

        # Red 3D Bandana (shifts with look direction)
        if dir_y > -0.45 or self._waving:
            painter.setBrush(_make_3d_bandana_brush(5.0))
            sx = 0.0 if self._waving else dir_x * 2.1
            sw = 4.6 * torso_scale_x
            scarf = QtGui.QPainterPath()
            scarf.moveTo(sx - sw, -17.2)
            scarf.lineTo(sx + sw, -17.2)
            scarf.lineTo(sx, -11.5)
            scarf.closeSubpath()
            painter.drawPath(scarf)

        # --- 3D Arms ---
        painter.setBrush(body_brush)
        if self._waving:
            painter.drawRoundedRect(QtCore.QRectF(-hw - 2.6, -16.2, 2.9, 7.6), 1.4, 1.4)
            painter.save()
            painter.translate(hw - 0.8, -15.5)
            wave_deg = -132.0 + math.sin(self._wave_phase) * 26.0
            painter.rotate(wave_deg)
            painter.drawRoundedRect(QtCore.QRectF(-1.4, -0.5, 3.0, 9.2), 1.4, 1.4)
            painter.restore()
        else:
            arm_amp = 42.0 if self._running else 18.0
            arm_swing = math.sin(self._walk_phase) * arm_amp * self._walk_amount
            if torso_scale_x > 0.78:
                painter.save()
                painter.translate(-hw + 0.3, -15.5)
                painter.rotate(arm_swing)
                painter.drawRoundedRect(QtCore.QRectF(-2.2, 0.0, 2.7, 7.3), 1.3, 1.3)
                painter.restore()

                painter.save()
                painter.translate(hw - 0.3, -15.5)
                painter.rotate(-arm_swing)
                painter.drawRoundedRect(QtCore.QRectF(-0.5, 0.0, 2.7, 7.3), 1.3, 1.3)
                painter.restore()
            else:
                painter.save()
                painter.translate(dir_x * 1.4, -15.2)
                painter.rotate(-arm_swing - dir_x * (18.0 if self._running else 8.0))
                painter.drawRoundedRect(QtCore.QRectF(-1.4, 0.0, 2.9, 7.6), 1.4, 1.4)
                painter.restore()

        # --- Eyeless 3D Head + 3D Cowboy Hat ---
        painter.save()
        painter.translate(head_shift_x * 0.45, -24.2)
        painter.rotate(head_tilt)
        painter.setPen(outline)
        painter.setBrush(_make_3d_gold_head_brush(0.0, 0.0, 5.4))
        painter.drawEllipse(QtCore.QPointF(0.0, 0.0), 5.4, 5.4)
        _draw_cowboy_hat(painter, scale_x=torso_scale_x)
        painter.restore()

        painter.restore()

        # White ground dot on anchor
        painter.save()
        painter.setRenderHint(ANTIALIASING, True)
        painter.setPen(NO_PEN)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#ffffff"), BRUSH_SOLID))
        painter.drawEllipse(QtCore.QPointF(0.0, 0.0), 2.2, 2.2)
        painter.restore()


class DropTargetReticle(QgsMapCanvasItem):
    """Animated-style circular drop target shown when dragging Pegman over canvas."""

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self._canvas = canvas
        self._active = False
        self._map_point: Optional[QgsPointXY] = None
        self.setZValue(115)
        self.hide()

    def set_target(self, map_point: QgsPointXY) -> None:
        self._map_point = QgsPointXY(map_point)
        self._active = True
        self.setPos(self.toCanvasCoordinates(self._map_point))
        self.show()
        self.update()

    def clear(self) -> None:
        self._active = False
        self._map_point = None
        self.hide()

    def updatePosition(self) -> None:
        if self._active and self._map_point is not None:
            self.setPos(self.toCanvasCoordinates(self._map_point))

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(-28.0, -28.0, 56.0, 56.0)

    def paint(self, painter: QtGui.QPainter, option=None, widget=None) -> None:
        if not self._active:
            return
        painter.save()
        painter.setRenderHint(ANTIALIASING, True)
        painter.setPen(QtGui.QPen(QtGui.QColor("#38bdf8"), 2.2, PEN_DASH))
        painter.setBrush(QtGui.QBrush(QtGui.QColor(56, 189, 248, 55), BRUSH_SOLID))
        painter.drawEllipse(QtCore.QPointF(0.0, 0.0), 20.0, 20.0)
        painter.setPen(QtGui.QPen(QtGui.QColor("#facc15"), 2.0, PEN_SOLID))
        painter.setBrush(QtGui.QBrush(QtGui.QColor(250, 204, 21, 160), BRUSH_SOLID))
        painter.drawEllipse(QtCore.QPointF(0.0, 0.0), 5.0, 5.0)
        painter.restore()


class CanvasPoseOverlay(QtCore.QObject):
    """Coordinates smooth 33 FPS walk/run Pegman, hand-grab teleport, 30s wave & dance."""

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self._canvas = canvas
        self._fov_band = QgsRubberBand(canvas, GEOM_POLYGON)
        self._fov_band.setFillColor(QtGui.QColor(56, 189, 248, 82))
        self._fov_band.setStrokeColor(QtGui.QColor(14, 165, 233, 210))
        self._fov_band.setWidth(2)
        self._fov_band.setZValue(110)

        self._aim_line = QgsRubberBand(canvas, GEOM_LINE)
        self._aim_line.setColor(QtGui.QColor(250, 204, 21, 235))
        self._aim_line.setWidth(3)
        self._aim_line.setLineStyle(PEN_DASH)
        self._aim_line.setZValue(112)

        self._pegman = PegmanCanvasMarker(canvas)
        self._reticle = DropTargetReticle(canvas)

        self._has_pose = False
        self._cur_lat = 0.0
        self._cur_lon = 0.0
        self._cur_heading = 0.0
        self._cur_fov = 85.0
        self._tgt_lat = 0.0
        self._tgt_lon = 0.0
        self._tgt_heading = 0.0
        self._tgt_fov = 85.0
        self._turn_vel = 0.0
        self._walk_phase = 0.0
        self._walk_amount = 0.0
        self._running = False
        self._lifted = False
        self._dangle_tilt = 0.0
        self._wave_active = False
        self._wave_phase = 0.0
        self._dance_active = False
        self._dance_elapsed = 0.0
        self._last_activity_ts = time.monotonic()

        self._anim_timer = QtCore.QTimer(self)
        self._anim_timer.setInterval(30)
        self._anim_timer.timeout.connect(self._on_anim_tick)

        self._idle_timer = QtCore.QTimer(self)
        self._idle_timer.setInterval(1000)
        self._idle_timer.timeout.connect(self._on_idle_check)

    def _compute_cone_radius_m(self) -> float:
        extent = self._canvas.extent()
        canvas_crs = self._canvas.mapSettings().destinationCrs()
        if canvas_crs.isGeographic():
            approx_m = extent.width() * 90000.0
        else:
            approx_m = extent.width()
        return max(22.0, min(220.0, approx_m * 0.095))

    def _shortest_angle_delta(self, current: float, target: float) -> float:
        return ((target - current + 180.0) % 360.0) - 180.0

    def hit_test_pegman(self, viewport_pt: QtCore.QPointF) -> bool:
        return self._pegman.hit_test_canvas_point(viewport_pt)

    def set_lifted_drag(
        self,
        hand_map_pt: QgsPointXY,
        drop_map_pt: Optional[QgsPointXY] = None,
        dangle_tilt: float = 0.0,
    ) -> None:
        """Teleport Pegman's raised hand straight to cursor while targeting drop_map_pt below boots."""
        self._anim_timer.stop()
        self._last_activity_ts = time.monotonic()
        self._wave_active = False
        self._dance_active = False
        self._lifted = True
        self._dangle_tilt = dangle_tilt
        self._fov_band.hide()
        self._reticle.set_target(drop_map_pt if drop_map_pt is not None else hand_map_pt)
        self._pegman.set_pose(
            hand_map_pt,
            heading=self._cur_heading,
            lifted=True,
            dangle_tilt=dangle_tilt,
        )

    def trigger_monkey_dance(self, toggle: bool = True) -> bool:
        """Start or stop the Johnny Bravo Monkey dance + confetti around Pegman."""
        if not self._has_pose or self._lifted:
            return False
        if toggle and self._dance_active:
            self._dance_active = False
            self._render_current_state()
            return False
        self._last_activity_ts = time.monotonic()
        self._wave_active = False
        self._dance_active = True
        self._dance_elapsed = 0.0
        if not self._anim_timer.isActive():
            self._anim_timer.start()
        self._render_current_state()
        return True

    def _render_current_state(self) -> QgsPointXY:
        canvas_crs = self._canvas.mapSettings().destinationCrs()
        canvas_pt = wgs84_to_canvas(self._cur_lat, self._cur_lon, canvas_crs)
        if not self._lifted:
            radius_m = self._compute_cone_radius_m()
            cone_geom = build_fov_cone_polygon(
                lat=self._cur_lat,
                lon=self._cur_lon,
                heading_deg=self._cur_heading,
                fov_deg=self._cur_fov,
                radius_m=radius_m,
                canvas_crs=canvas_crs,
            )
            self._fov_band.setToGeometry(cone_geom, canvas_crs)
            self._fov_band.show()
        self._pegman.set_pose(
            canvas_pt,
            heading=self._cur_heading,
            turn_velocity=self._turn_vel,
            walk_phase=self._walk_phase,
            walk_amount=self._walk_amount,
            running=self._running,
            lifted=self._lifted,
            dangle_tilt=self._dangle_tilt,
            waving=self._wave_active,
            wave_phase=self._wave_phase,
            dancing=self._dance_active,
            dance_phase=self._dance_elapsed * 2.4,
        )
        return canvas_pt

    def update_pegman_pose(
        self,
        lat: float,
        lon: float,
        heading: float = 0.0,
        fov: float = 85.0,
        smooth: bool = True,
    ) -> QgsPointXY:
        """Set or smoothly animate Pegman (walking for near moves, running for far jumps)."""
        self._last_activity_ts = time.monotonic()
        self._wave_active = False
        self._dance_active = False
        self._lifted = False
        self._reticle.clear()

        heading_norm = float(heading) % 360.0
        self._tgt_lat = float(lat)
        self._tgt_lon = float(lon)
        self._tgt_heading = heading_norm
        self._tgt_fov = float(fov)

        if not self._has_pose or not smooth:
            self._has_pose = True
            self._cur_lat = self._tgt_lat
            self._cur_lon = self._tgt_lon
            self._cur_heading = self._tgt_heading
            self._cur_fov = self._tgt_fov
            self._turn_vel = 0.0
            self._walk_amount = 0.0
            self._running = False
            if not self._idle_timer.isActive():
                self._idle_timer.start()
            return self._render_current_state()

        jump_m = geodesic_distance_m(self._cur_lat, self._cur_lon, self._tgt_lat, self._tgt_lon)
        if jump_m > RUN_DISTANCE_THRESHOLD_M:
            self._running = True
        elif jump_m > 1.5:
            self._running = False

        if not self._anim_timer.isActive():
            self._anim_timer.start()
        if not self._idle_timer.isActive():
            self._idle_timer.start()
        return wgs84_to_canvas(
            self._cur_lat, self._cur_lon, self._canvas.mapSettings().destinationCrs()
        )

    def step_animation(self, dt_sec: float = 0.03) -> bool:
        """Advance one smooth interpolation, dance, or idle wave frame."""
        if not self._has_pose or self._lifted:
            return False

        d_lat = self._tgt_lat - self._cur_lat
        d_lon = self._tgt_lon - self._cur_lon
        d_hdg = self._shortest_angle_delta(self._cur_heading, self._tgt_heading)
        d_fov = self._tgt_fov - self._cur_fov

        pos_dist_deg = math.hypot(d_lat, d_lon)
        moving = pos_dist_deg > 1e-6 or abs(d_hdg) > 0.25 or abs(d_fov) > 0.15

        if moving:
            rem_m = geodesic_distance_m(self._cur_lat, self._cur_lon, self._tgt_lat, self._tgt_lon)
            if rem_m > RUN_DISTANCE_THRESHOLD_M:
                self._running = True
            ease = min(1.0, max(0.16, dt_sec * (6.2 if self._running else 8.5)))
            self._cur_lat += d_lat * ease
            self._cur_lon += d_lon * ease
            self._cur_heading = (self._cur_heading + d_hdg * ease) % 360.0
            self._cur_fov += d_fov * ease

            self._turn_vel = max(-1.0, min(1.0, d_hdg / 35.0))
            if pos_dist_deg > 2e-6:
                self._walk_amount = min(1.0, max(0.35, pos_dist_deg * 18000.0))
                self._walk_phase += dt_sec * (24.0 if self._running else 12.5)
            else:
                self._walk_amount *= 0.7
            self._render_current_state()
            return True

        self._cur_lat = self._tgt_lat
        self._cur_lon = self._tgt_lon
        self._cur_heading = self._tgt_heading
        self._cur_fov = self._tgt_fov
        self._turn_vel = 0.0
        self._walk_amount = 0.0
        self._running = False

        if self._dance_active:
            self._dance_elapsed += dt_sec
            if self._dance_elapsed >= DANCE_DURATION_SEC:
                self._dance_active = False
                self._last_activity_ts = time.monotonic()
                self._render_current_state()
                return False
            self._render_current_state()
            return True

        if self._wave_active:
            self._wave_phase += dt_sec * 8.5
            self._render_current_state()
            return True

        self._render_current_state()
        return False

    def _on_anim_tick(self) -> None:
        if not self.step_animation(0.03):
            self._anim_timer.stop()

    def trigger_idle_wave_check(self, elapsed_sec: Optional[float] = None) -> bool:
        """Evaluate whether Pegman has stood idle >= 30s and should wave."""
        if not self._has_pose or self._lifted or self._dance_active:
            return False
        idle = (
            float(elapsed_sec)
            if elapsed_sec is not None
            else (time.monotonic() - self._last_activity_ts)
        )
        if idle < IDLE_WAVE_DELAY_SEC:
            if self._wave_active:
                self._wave_active = False
                self._render_current_state()
            return False

        cycle = (idle - IDLE_WAVE_DELAY_SEC) % IDLE_WAVE_REPEAT_SEC
        should_wave = cycle <= IDLE_WAVE_DURATION_SEC
        if should_wave != self._wave_active:
            self._wave_active = should_wave
            if should_wave and not self._anim_timer.isActive():
                self._anim_timer.start()
            elif not should_wave:
                self._render_current_state()
        return self._wave_active

    def _on_idle_check(self) -> None:
        self.trigger_idle_wave_check()

    def update_drag_aim(
        self,
        origin_lat: float,
        origin_lon: float,
        origin_pt: QgsPointXY,
        aim_pt: QgsPointXY,
        heading: float,
    ) -> None:
        canvas_crs = self._canvas.mapSettings().destinationCrs()
        line_geom = QgsGeometry.fromPolylineXY([origin_pt, aim_pt])
        self._aim_line.setToGeometry(line_geom, canvas_crs)
        self._aim_line.show()
        self.update_pegman_pose(origin_lat, origin_lon, heading=heading, fov=80.0, smooth=False)

    def clear_drag_aim(self) -> None:
        self._aim_line.reset(GEOM_LINE)

    def show_drop_reticle(self, map_pt: QgsPointXY) -> None:
        self._reticle.set_target(map_pt)

    def hide_drop_reticle(self) -> None:
        self._reticle.clear()

    def clear_all(self) -> None:
        self._anim_timer.stop()
        self._idle_timer.stop()
        self._has_pose = False
        self._wave_active = False
        self._dance_active = False
        self._lifted = False
        self._running = False
        self._fov_band.reset(GEOM_POLYGON)
        self._aim_line.reset(GEOM_LINE)
        self._pegman.clear()
        self._reticle.clear()

    def cleanup(self) -> None:
        self.clear_all()
        scene = self._canvas.scene()
        for item in (self._fov_band, self._aim_line, self._pegman, self._reticle):
            try:
                if scene is not None and item.scene() == scene:
                    scene.removeItem(item)
            except Exception as exc:
                log_debug(f"Canvas item cleanup skipped: {exc}")
