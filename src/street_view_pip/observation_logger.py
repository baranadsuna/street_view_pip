# -*- coding: utf-8 -*-
"""
EPSG:5253 Field Observation Logger for Street View Navigator (PiP).

Logs inspected Street View coordinates, camera heading, field of view,
panorama ID, and direct link into an EPSG:5253 (TUREF / TM30) point vector
layer with directional arrow symbology so Street View site inspections feed
directly into urban planning synthesis (No Orphan Analysis rule).
"""

from datetime import datetime
from typing import Optional

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsMarkerSymbol,
    QgsPointXY,
    QgsProject,
    QgsProperty,
    QgsSymbolLayer,
    QgsVectorLayer,
)

from .geo_utils import MANDATORY_CRS_AUTHID, StreetViewState, wgs84_to_epsg5253
from .i18n import tr_text
from .qt_compat import FIELD_DOUBLE, FIELD_STRING


def _find_or_create_observation_layer(lang: str = "en") -> QgsVectorLayer:
    layer_name = tr_text(lang, "obs_layer_name")
    proj = QgsProject.instance()
    for lyr in proj.mapLayers().values():
        if isinstance(lyr, QgsVectorLayer) and lyr.name() == layer_name and lyr.isValid():
            return lyr

    lyr = QgsVectorLayer(f"Point?crs={MANDATORY_CRS_AUTHID}", layer_name, "memory")
    dp = lyr.dataProvider()
    dp.addAttributes([
        QgsField("obs_id", FIELD_STRING),
        QgsField("timestamp", FIELD_STRING),
        QgsField("epsg5253_x", FIELD_DOUBLE),
        QgsField("epsg5253_y", FIELD_DOUBLE),
        QgsField("lat_wgs84", FIELD_DOUBLE),
        QgsField("lon_wgs84", FIELD_DOUBLE),
        QgsField("heading_deg", FIELD_DOUBLE),
        QgsField("pitch_deg", FIELD_DOUBLE),
        QgsField("fov_deg", FIELD_DOUBLE),
        QgsField("pano_id", FIELD_STRING),
        QgsField("sv_url", FIELD_STRING),
        QgsField("field_note", FIELD_STRING),
    ])
    lyr.updateFields()

    # Crisp directional arrowhead marker rotated by heading_deg
    symbol = QgsMarkerSymbol.createSimple({
        "name": "arrowhead",
        "color": "#facc15",
        "outline_color": "#0f172a",
        "outline_width": "0.6",
        "size": "5.2",
    })
    if symbol and symbol.symbolLayerCount() > 0:
        sl = symbol.symbolLayer(0)
        # Arrowhead points East (90 deg) by default in QGIS; rotate heading - 90
        prop = QgsProperty.fromExpression('"heading_deg" - 90')
        sl.setDataDefinedProperty(QgsSymbolLayer.Property.PropertyAngle, prop)
    lyr.renderer().setSymbol(symbol)

    proj.addMapLayer(lyr, True)
    return lyr


def log_street_view_observation(
    state: StreetViewState,
    note: str = "",
    lang: str = "en",
) -> Optional[QgsVectorLayer]:
    """Append a Street View camera state as a point feature in EPSG:5253."""
    if state is None:
        return None
    lyr = _find_or_create_observation_layer(lang=lang)
    x5253, y5253 = wgs84_to_epsg5253(state.lat, state.lon)
    feat = QgsFeature(lyr.fields())
    feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x5253, y5253)))

    obs_id = f"SV-{lyr.featureCount() + 1:04d}"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    feat.setAttributes([
        obs_id,
        ts,
        round(x5253, 3),
        round(y5253, 3),
        round(state.lat, 7),
        round(state.lon, 7),
        round(state.heading, 2),
        round(state.pitch, 2),
        round(state.fov, 2),
        state.pano_id or "",
        state.url or "",
        note or "Street View inspection",
    ])
    lyr.dataProvider().addFeatures([feat])
    lyr.updateExtents()
    lyr.triggerRepaint()
    return lyr
