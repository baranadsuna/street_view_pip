# -*- coding: utf-8 -*-
"""
Geodetic & Coordinate Transformation Utilities for Street View Navigator (PiP).

Strictly adheres to the workspace CRS standard:
  - WGS84 Geographic (EPSG:4326) is converted dynamically to/from any active
    QGIS map canvas CRS and the mandatory Turkish National Reference Frame
    projection EPSG:5253 (TUREF / TM30) using QgsCoordinateTransform.
  - Viewing-cone (FOV) sectors and azimuth bearings are computed via spherical /
    geodesic offsets in WGS84 and projected to the canvas CRS so meridian
    convergence in Transverse Mercator (EPSG:5253) is accurately preserved.
"""

from dataclasses import dataclass
import math
import re
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
)

from .qt_compat import GEOM_LINE, log_debug

MANDATORY_CRS_AUTHID = "EPSG:5253"
WGS84_AUTHID = "EPSG:4326"
EARTH_RADIUS_M = 6371008.8


@dataclass
class StreetViewState:
    """Represents a synchronized Street View camera pose."""

    lat: float
    lon: float
    heading: float = 0.0
    pitch: float = 0.0
    fov: float = 85.0
    pano_id: str = ""
    url: str = ""


def _transform_point(
    point: QgsPointXY,
    src_crs: QgsCoordinateReferenceSystem,
    dst_crs: QgsCoordinateReferenceSystem,
    project: Optional[QgsProject] = None,
) -> QgsPointXY:
    if not src_crs.isValid() or not dst_crs.isValid() or src_crs == dst_crs:
        return QgsPointXY(point)
    ctx = (project or QgsProject.instance()).transformContext()
    xf = QgsCoordinateTransform(src_crs, dst_crs, ctx)
    return xf.transform(point)


def canvas_to_wgs84(
    point: QgsPointXY,
    canvas_crs: QgsCoordinateReferenceSystem,
    project: Optional[QgsProject] = None,
) -> Tuple[float, float]:
    """Transform a canvas map coordinate into WGS84 (lat, lon) degrees."""
    wgs84 = QgsCoordinateReferenceSystem(WGS84_AUTHID)
    pt = _transform_point(point, canvas_crs, wgs84, project)
    return (float(pt.y()), float(pt.x()))


def wgs84_to_canvas(
    lat: float,
    lon: float,
    canvas_crs: QgsCoordinateReferenceSystem,
    project: Optional[QgsProject] = None,
) -> QgsPointXY:
    """Transform WGS84 (lat, lon) into the active canvas CRS."""
    wgs84 = QgsCoordinateReferenceSystem(WGS84_AUTHID)
    return _transform_point(QgsPointXY(lon, lat), wgs84, canvas_crs, project)


def wgs84_to_epsg5253(
    lat: float,
    lon: float,
    project: Optional[QgsProject] = None,
) -> Tuple[float, float]:
    """Transform WGS84 (lat, lon) into mandatory EPSG:5253 (Easting, Northing)."""
    wgs84 = QgsCoordinateReferenceSystem(WGS84_AUTHID)
    tm30 = QgsCoordinateReferenceSystem(MANDATORY_CRS_AUTHID)
    pt = _transform_point(QgsPointXY(lon, lat), wgs84, tm30, project)
    return (float(pt.x()), float(pt.y()))


def canvas_to_epsg5253(
    point: QgsPointXY,
    canvas_crs: QgsCoordinateReferenceSystem,
    project: Optional[QgsProject] = None,
) -> Tuple[float, float]:
    """Transform any canvas point into mandatory EPSG:5253 (Easting, Northing)."""
    tm30 = QgsCoordinateReferenceSystem(MANDATORY_CRS_AUTHID)
    pt = _transform_point(point, canvas_crs, tm30, project)
    return (float(pt.x()), float(pt.y()))


def bearing_between_wgs84(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute initial true-north forward azimuth [0, 360) from point 1 to point 2."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_lam = math.radians(lon2 - lon1)
    y = math.sin(d_lam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lam)
    if abs(x) < 1e-12 and abs(y) < 1e-12:
        return 0.0
    brng = math.degrees(math.atan2(y, x))
    return (brng + 360.0) % 360.0


def geodesic_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute Haversine spherical ground distance in meters between two WGS84 points."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi * 0.5) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(d_lam * 0.5) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_M * c


def destination_point_wgs84(
    lat: float,
    lon: float,
    bearing_deg: float,
    distance_m: float,
) -> Tuple[float, float]:
    """Compute geodesic destination (lat, lon) given bearing and distance in meters."""
    delta = distance_m / EARTH_RADIUS_M
    theta = math.radians(bearing_deg)
    phi1 = math.radians(lat)
    lam1 = math.radians(lon)

    sin_phi2 = math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    phi2 = math.asin(max(-1.0, min(1.0, sin_phi2)))
    y = math.sin(theta) * math.sin(delta) * math.cos(phi1)
    x = math.cos(delta) - math.sin(phi1) * math.sin(phi2)
    lam2 = lam1 + math.atan2(y, x)
    return (math.degrees(phi2), ((math.degrees(lam2) + 540.0) % 360.0) - 180.0)


def build_fov_cone_polygon(
    lat: float,
    lon: float,
    heading_deg: float,
    fov_deg: float,
    radius_m: float,
    canvas_crs: QgsCoordinateReferenceSystem,
    project: Optional[QgsProject] = None,
    steps: int = 16,
) -> QgsGeometry:
    """Build a projected FOV sector polygon in canvas_crs from geodesic WGS84 offsets."""
    half_fov = max(10.0, min(140.0, fov_deg)) * 0.5
    origin = wgs84_to_canvas(lat, lon, canvas_crs, project)
    ring = [origin]
    for idx in range(steps + 1):
        frac = idx / float(steps)
        az = (heading_deg - half_fov + frac * (2.0 * half_fov)) % 360.0
        d_lat, d_lon = destination_point_wgs84(lat, lon, az, radius_m)
        ring.append(wgs84_to_canvas(d_lat, d_lon, canvas_crs, project))
    ring.append(origin)
    return QgsGeometry.fromPolygonXY([ring])


def parse_google_maps_url(url: str) -> Optional[StreetViewState]:
    """
    Parse latitude, longitude, FOV, heading, pitch, and pano_id from Google Maps URLs.

    Supports both:
      1) Standard dynamic Street View URLs:
         https://www.google.com/maps/@38.0886007,27.7346069,3a,85y,265h,90t/data=!3m7!1e1!3m5!1s<PANO_ID>!2e0...
      2) Official Google Maps URLs API links:
         https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=38.0885,27.7347&heading=265&pitch=0&fov=85
    """
    if not url or "google." not in url:
        return None

    # 1. Standard /maps/@lat,lon,params path
    at_match = re.search(
        r"/@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?),([^/?#]+)",
        url,
    )
    if at_match:
        lat = float(at_match.group(1))
        lon = float(at_match.group(2))
        params_seg = at_match.group(3)
        # Only treat as Street View when 'a' (panorama/aspect) or 'y'/'h'/'t' streetview tokens exist
        if any(tok in params_seg for tok in ("a,", "y,", "h,", "t")) or "streetview" in url:
            fov_m = re.search(r"(\d+(?:\.\d+)?)y", params_seg)
            hdg_m = re.search(r"(-?\d+(?:\.\d+)?)h", params_seg)
            tilt_m = re.search(r"(-?\d+(?:\.\d+)?)t", params_seg)
            pano_m = re.search(r"!1s([^!/?&#]+)", url)

            fov = float(fov_m.group(1)) if fov_m else 85.0
            heading = (float(hdg_m.group(1)) % 360.0) if hdg_m else 0.0
            tilt = float(tilt_m.group(1)) if tilt_m else 90.0
            pitch = max(-90.0, min(90.0, tilt - 90.0))
            pano_id = pano_m.group(1) if pano_m else ""
            return StreetViewState(
                lat=lat,
                lon=lon,
                heading=heading,
                pitch=pitch,
                fov=fov,
                pano_id=pano_id,
                url=url,
            )

    # 2. Query parameter fallback (?api=1&map_action=pano&viewpoint=lat,lon...)
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "viewpoint" in qs:
        parts = qs["viewpoint"][0].split(",")
        if len(parts) == 2:
            try:
                lat = float(parts[0])
                lon = float(parts[1])
                heading = float(qs.get("heading", ["0"])[0]) % 360.0
                pitch = float(qs.get("pitch", ["0"])[0])
                fov = float(qs.get("fov", ["85"])[0])
                pano_id = qs.get("pano", [""])[0]
                return StreetViewState(
                    lat=lat,
                    lon=lon,
                    heading=heading,
                    pitch=pitch,
                    fov=fov,
                    pano_id=pano_id,
                    url=url,
                )
            except ValueError:
                return None
    return None


def build_street_view_url(
    lat: float,
    lon: float,
    heading: float = 0.0,
    pitch: float = 0.0,
    fov: float = 85.0,
    provider: str = "google_direct",
    pano_id: str = "",
) -> str:
    """Build the target Street View URL for the selected provider."""
    heading_norm = float(heading) % 360.0
    fov_clamped = max(15.0, min(115.0, float(fov)))
    pitch_clamped = max(-85.0, min(85.0, float(pitch)))

    if provider == "panoramax":
        return f"https://api.panoramax.xyz/#focus=pic&map=19/{lat:.6f}/{lon:.6f}"

    url = (
        "https://www.google.com/maps/@?api=1&map_action=pano"
        f"&viewpoint={lat:.7f},{lon:.7f}"
        f"&heading={heading_norm:.1f}&pitch={pitch_clamped:.1f}&fov={fov_clamped:.1f}"
    )
    if pano_id:
        url += f"&pano={pano_id}"
    return url


def snap_to_nearest_road_detail(
    lat: float,
    lon: float,
    project: Optional[QgsProject] = None,
    max_distance_m: float = 35.0,
) -> Optional[Tuple[float, float, float]]:
    """
    Snap (lat, lon) onto the nearest loaded LineString road segment in EPSG:5253.

    Returns (snapped_lat, snapped_lon, road_azimuth_deg) if a road lies within
    max_distance_m, otherwise None.
    """
    proj = project or QgsProject.instance()
    tm30 = QgsCoordinateReferenceSystem(MANDATORY_CRS_AUTHID)
    wgs84 = QgsCoordinateReferenceSystem(WGS84_AUTHID)
    ctx = proj.transformContext()

    pt_wgs = QgsPointXY(lon, lat)
    pt_5253 = _transform_point(pt_wgs, wgs84, tm30, proj)
    pt_geom = QgsGeometry.fromPointXY(pt_5253)

    best_dist = max_distance_m
    best_result: Optional[Tuple[float, float, float]] = None

    for layer in proj.mapLayers().values():
        if not hasattr(layer, "geometryType") or layer.geometryType() != GEOM_LINE:
            continue
        if not layer.isValid():
            continue
        xf_to_5253 = QgsCoordinateTransform(layer.crs(), tm30, ctx)
        xf_to_wgs = QgsCoordinateTransform(tm30, wgs84, ctx)
        xf_5253_to_layer = QgsCoordinateTransform(tm30, layer.crs(), ctx)
        try:
            search_pt = xf_5253_to_layer.transform(pt_5253)
            buf_deg = max_distance_m if not layer.crs().isGeographic() else (max_distance_m / 90000.0)
            from qgis.core import QgsFeatureRequest, QgsRectangle

            rect = QgsRectangle(
                search_pt.x() - buf_deg,
                search_pt.y() - buf_deg,
                search_pt.x() + buf_deg,
                search_pt.y() + buf_deg,
            )
            req = QgsFeatureRequest().setFilterRect(rect)
            for feat in layer.getFeatures(req):
                geom = QgsGeometry(feat.geometry())
                if geom.isNull() or geom.isEmpty():
                    continue
                if layer.crs() != tm30:
                    geom.transform(xf_to_5253)
                dist = geom.distance(pt_geom)
                if dist <= best_dist:
                    _, closest_pt, next_vtx, _ = geom.closestSegmentWithContext(pt_5253)
                    poly = geom.asMultiPolyline()[0] if geom.isMultipart() else geom.asPolyline()
                    if len(poly) >= 2:
                        idx2 = min(max(1, next_vtx), len(poly) - 1)
                        p_a = xf_to_wgs.transform(poly[idx2 - 1])
                        p_b = xf_to_wgs.transform(poly[idx2])
                        p_snap = xf_to_wgs.transform(closest_pt)
                        best_dist = dist
                        az = bearing_between_wgs84(p_a.y(), p_a.x(), p_b.y(), p_b.x())
                        best_result = (float(p_snap.y()), float(p_snap.x()), float(az))
        except Exception as exc:
            log_debug(f"Road snap skipped for layer {layer.name()}: {exc}")

    return best_result


def snap_to_nearest_road_azimuth(
    lat: float,
    lon: float,
    project: Optional[QgsProject] = None,
    max_distance_m: float = 35.0,
) -> Optional[float]:
    """Return true WGS84 azimuth along closest QGIS road segment within max_distance_m."""
    res = snap_to_nearest_road_detail(lat, lon, project=project, max_distance_m=max_distance_m)
    return res[2] if res is not None else None
