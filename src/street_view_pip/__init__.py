# -*- coding: utf-8 -*-
"""
Street View Navigator (PiP) — QGIS Plugin Entry Point.

Provides interactive Pegman drag-and-drop Street View browsing inside a
resizable bottom-right Picture-in-Picture (PiP) overlay on the QGIS canvas,
with live EPSG:5253 geodetic synchronization.
"""


def classFactory(iface):
    """Instantiate the Street View Navigator (PiP) plugin."""
    from .plugin import StreetViewPipPlugin
    return StreetViewPipPlugin(iface)
