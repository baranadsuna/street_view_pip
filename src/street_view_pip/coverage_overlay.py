# -*- coding: utf-8 -*-
"""
Street View Blue Coverage Overlay Manager.

Adds and toggles an XYZ raster overlay showing streets with Street View
coverage (blue lines on top of satellite imagery, matching Google Maps Pegman
drag mode) cleanly without polluting the user's QGIS project on unload.
"""

from typing import Optional
from urllib.parse import quote

from qgis.core import QgsProject, QgsRasterLayer

from .i18n import tr_text
from .qt_compat import log_debug

GOOGLE_SVV_TILE_TEMPLATE = (
    "https://mts2.google.com/mapslt?lyrs=svv&x={x}&y={y}&z={z}&w=256&h=256&hl=en&style=40,18"
)


class CoverageOverlayManager:
    """Manages an ephemeral XYZ raster overlay for Street View street coverage."""

    def __init__(self, lang: str = "en"):
        self._lang = lang
        self._layer_id: Optional[str] = None
        self._pinned_by_user: bool = False

    def set_language(self, lang: str) -> None:
        self._lang = lang
        lyr = self.get_layer()
        if lyr is not None:
            lyr.setName(tr_text(self._lang, "coverage_layer_name"))

    def is_visible(self) -> bool:
        lyr = self.get_layer()
        if lyr is None:
            return False
        node = QgsProject.instance().layerTreeRoot().findLayer(lyr.id())
        return bool(node and node.isVisible())

    def is_pinned(self) -> bool:
        return self._pinned_by_user

    def get_layer(self) -> Optional[QgsRasterLayer]:
        if not self._layer_id:
            return None
        lyr = QgsProject.instance().mapLayer(self._layer_id)
        if isinstance(lyr, QgsRasterLayer) and lyr.isValid():
            return lyr
        self._layer_id = None
        return None

    def ensure_layer(self) -> Optional[QgsRasterLayer]:
        """Create or retrieve the Street View coverage XYZ overlay at top of layer tree."""
        existing = self.get_layer()
        if existing is not None:
            return existing

        encoded_url = quote(GOOGLE_SVV_TILE_TEMPLATE, safe=":")
        uri = f"type=xyz&url={encoded_url}&zmax=19&zmin=0"
        name = tr_text(self._lang, "coverage_layer_name")
        lyr = QgsRasterLayer(uri, name, "wms")
        if not lyr.isValid():
            return None

        lyr.setOpacity(0.90)
        proj = QgsProject.instance()
        # Add at index 0 (above Google Satellite and basemaps) without auto-insert at bottom
        proj.addMapLayer(lyr, False)
        proj.layerTreeRoot().insertLayer(0, lyr)
        self._layer_id = lyr.id()
        return lyr

    def set_visible(self, visible: bool, user_pinned: Optional[bool] = None) -> bool:
        """Show or hide the coverage layer; returns actual visibility."""
        if user_pinned is not None:
            self._pinned_by_user = user_pinned
        if visible:
            lyr = self.ensure_layer()
            if lyr is None:
                return False
            node = QgsProject.instance().layerTreeRoot().findLayer(lyr.id())
            if node:
                node.setItemVisibilityChecked(True)
            return True
        else:
            lyr = self.get_layer()
            if lyr is not None:
                node = QgsProject.instance().layerTreeRoot().findLayer(lyr.id())
                if node:
                    node.setItemVisibilityChecked(False)
            return False

    def toggle_user_pinned(self) -> bool:
        """Toggle user-pinned visibility for the coverage overlay."""
        target = not self.is_visible()
        return self.set_visible(target, user_pinned=target)

    def set_transient_active(self, active: bool) -> None:
        """Temporarily show coverage during Pegman hover/drag unless user pinned it."""
        if active:
            self.set_visible(True)
        elif not self._pinned_by_user:
            self.set_visible(False)

    def cleanup(self) -> None:
        """Remove ephemeral coverage layer cleanly on plugin unload."""
        lyr = self.get_layer()
        if lyr is not None:
            try:
                QgsProject.instance().removeMapLayer(lyr.id())
            except Exception as exc:
                log_debug(f"Coverage overlay cleanup skipped: {exc}")
        self._layer_id = None
        self._pinned_by_user = False
