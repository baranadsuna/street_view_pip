# -*- coding: utf-8 -*-
"""
Qt5 / Qt6 and QGIS 3 / QGIS 4 Compatibility Helpers.

All Qt imports go strictly through ``qgis.PyQt`` without direct PyQt5/PyQt6
references so the plugin runs identically on QGIS 3.22+ (Qt5) and QGIS 4.x (Qt6).
"""

from qgis.PyQt import QtCore, QtGui
from qgis.core import Qgis, QgsMessageLog, QgsWkbTypes


def _resolve_enum(owner, scoped_name: str, member_name: str):
    """Resolve a Qt6 scoped enum member with automatic Qt5 unscoped fallback."""
    scoped_cls = getattr(owner, scoped_name, None)
    if scoped_cls is not None and hasattr(scoped_cls, member_name):
        return getattr(scoped_cls, member_name)
    return getattr(owner, member_name)


# --- Alignment Flags ---
ALIGN_LEFT = _resolve_enum(QtCore.Qt, "AlignmentFlag", "AlignLeft")
ALIGN_RIGHT = _resolve_enum(QtCore.Qt, "AlignmentFlag", "AlignRight")
ALIGN_CENTER = _resolve_enum(QtCore.Qt, "AlignmentFlag", "AlignCenter")
ALIGN_VCENTER = _resolve_enum(QtCore.Qt, "AlignmentFlag", "AlignVCenter")

# --- Mouse Buttons ---
LEFT_BUTTON = _resolve_enum(QtCore.Qt, "MouseButton", "LeftButton")
RIGHT_BUTTON = _resolve_enum(QtCore.Qt, "MouseButton", "RightButton")
NO_BUTTON = _resolve_enum(QtCore.Qt, "MouseButton", "NoButton")

# --- Cursor Shapes ---
CURSOR_ARROW = _resolve_enum(QtCore.Qt, "CursorShape", "ArrowCursor")
CURSOR_CROSS = _resolve_enum(QtCore.Qt, "CursorShape", "CrossCursor")
CURSOR_POINTING_HAND = _resolve_enum(QtCore.Qt, "CursorShape", "PointingHandCursor")
CURSOR_OPEN_HAND = _resolve_enum(QtCore.Qt, "CursorShape", "OpenHandCursor")
CURSOR_CLOSED_HAND = _resolve_enum(QtCore.Qt, "CursorShape", "ClosedHandCursor")
CURSOR_SIZE_FDIAG = _resolve_enum(QtCore.Qt, "CursorShape", "SizeFDiagCursor")
CURSOR_SIZE_BDIAG = _resolve_enum(QtCore.Qt, "CursorShape", "SizeBDiagCursor")
CURSOR_SIZE_HOR = _resolve_enum(QtCore.Qt, "CursorShape", "SizeHorCursor")
CURSOR_SIZE_VER = _resolve_enum(QtCore.Qt, "CursorShape", "SizeVerCursor")
CURSOR_SIZE_ALL = _resolve_enum(QtCore.Qt, "CursorShape", "SizeAllCursor")

# --- Drop Actions ---
DROP_COPY = _resolve_enum(QtCore.Qt, "DropAction", "CopyAction")
DROP_MOVE = _resolve_enum(QtCore.Qt, "DropAction", "MoveAction")

# --- Event Types ---
EVENT_RESIZE = _resolve_enum(QtCore.QEvent, "Type", "Resize")
EVENT_SHOW = _resolve_enum(QtCore.QEvent, "Type", "Show")
EVENT_HIDE = _resolve_enum(QtCore.QEvent, "Type", "Hide")
EVENT_DRAG_ENTER = _resolve_enum(QtCore.QEvent, "Type", "DragEnter")
EVENT_DRAG_MOVE = _resolve_enum(QtCore.QEvent, "Type", "DragMove")
EVENT_DRAG_LEAVE = _resolve_enum(QtCore.QEvent, "Type", "DragLeave")
EVENT_DROP = _resolve_enum(QtCore.QEvent, "Type", "Drop")
EVENT_MOUSE_PRESS = _resolve_enum(QtCore.QEvent, "Type", "MouseButtonPress")
EVENT_MOUSE_MOVE = _resolve_enum(QtCore.QEvent, "Type", "MouseMove")
EVENT_MOUSE_RELEASE = _resolve_enum(QtCore.QEvent, "Type", "MouseButtonRelease")

# --- Pen / Brush / Painter ---
PEN_SOLID = _resolve_enum(QtCore.Qt, "PenStyle", "SolidLine")
PEN_DASH = _resolve_enum(QtCore.Qt, "PenStyle", "DashLine")
NO_PEN = _resolve_enum(QtCore.Qt, "PenStyle", "NoPen")
BRUSH_SOLID = _resolve_enum(QtCore.Qt, "BrushStyle", "SolidPattern")
ANTIALIASING = _resolve_enum(QtGui.QPainter, "RenderHint", "Antialiasing")
SMOOTH_PIXMAP = _resolve_enum(QtGui.QPainter, "RenderHint", "SmoothPixmapTransform")
KEEP_ASPECT = _resolve_enum(QtCore.Qt, "AspectRatioMode", "KeepAspectRatio")
TRANSPARENT_BG = _resolve_enum(QtCore.Qt, "GlobalColor", "transparent")

# --- Widget Attributes & Window Flags ---
WA_TRANSPARENT_FOR_MOUSE = _resolve_enum(
    QtCore.Qt, "WidgetAttribute", "WA_TransparentForMouseEvents"
)
WA_DELETE_ON_CLOSE = _resolve_enum(
    QtCore.Qt, "WidgetAttribute", "WA_DeleteOnClose"
)

# --- Geometry Types ---
GEOM_POINT = _resolve_enum(QgsWkbTypes, "GeometryType", "PointGeometry")
GEOM_LINE = _resolve_enum(QgsWkbTypes, "GeometryType", "LineGeometry")
GEOM_POLYGON = _resolve_enum(QgsWkbTypes, "GeometryType", "PolygonGeometry")

# --- QgsField Data Types (Qt5 QVariant & Qt6 QMetaType compatible) ---
try:
    _QMetaType = QtCore.QMetaType
    FIELD_DOUBLE = _QMetaType.Type.Double
    FIELD_INT = _QMetaType.Type.Int
    FIELD_STRING = _QMetaType.Type.QString
except (AttributeError, ImportError):
    FIELD_DOUBLE = getattr(QtCore.QVariant, "Double", 6)
    FIELD_INT = getattr(QtCore.QVariant, "Int", 2)
    FIELD_STRING = getattr(QtCore.QVariant, "String", 10)


def event_pos(event) -> QtCore.QPoint:
    """Return local QPoint from a mouse or drop event on both Qt5 and Qt6."""
    if hasattr(event, "position"):
        return event.position().toPoint()
    return event.pos()


def event_global_pos(event) -> QtCore.QPoint:
    """Return global QPoint from a mouse event on both Qt5 and Qt6."""
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


def exec_dialog(dlg) -> int:
    """Execute a QDialog compatibly on Qt5 and Qt6."""
    fn = getattr(dlg, "exec", None) or getattr(dlg, "exec_")
    return fn()


def exec_drag(drag: QtGui.QDrag, actions):
    """Execute a QDrag compatibly on Qt5 and Qt6."""
    fn = getattr(drag, "exec", None) or getattr(drag, "exec_")
    return fn(actions)


def log_debug(message: str) -> None:
    """Emit non-fatal diagnostic message to QGIS Message Log."""
    try:
        lvl = _resolve_enum(Qgis, "MessageLevel", "Info")
        QgsMessageLog.logMessage(message, "StreetViewPip", lvl)
    except (AttributeError, RuntimeError):
        return
