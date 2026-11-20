# -*- coding: utf-8 -*-
"""
Unit & Geodetic Engine Tests for Street View Navigator (PiP).
Verifies EPSG:5253 transformations, FOV cone geometry, Google URL parsing,
road-azimuth snapping, and EPSG:5253 field observation logging.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsSymbolLayer,
    QgsVectorLayer,
)

SRC_PARENT = Path(__file__).resolve().parent.parent.parent
if str(SRC_PARENT) not in sys.path:
    sys.path.insert(0, str(SRC_PARENT))

from street_view_pip.geo_utils import (
    MANDATORY_CRS_AUTHID,
    StreetViewState,
    bearing_between_wgs84,
    build_fov_cone_polygon,
    build_street_view_url,
    canvas_to_wgs84,
    geodesic_distance_m,
    parse_google_maps_url,
    snap_to_nearest_road_azimuth,
    snap_to_nearest_road_detail,
    wgs84_to_canvas,
    wgs84_to_epsg5253,
)
from street_view_pip.observation_logger import log_street_view_observation


def run_tests() -> None:
    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        proj = QgsProject.instance()
        proj.clear()
        crs_5253 = QgsCoordinateReferenceSystem(MANDATORY_CRS_AUTHID)
        assert crs_5253.isValid(), "EPSG:5253 must be valid in QGIS PROJ"
        proj.setCrs(crs_5253)

        # 1. Round-trip WGS84 <-> EPSG:5253 around Tire, Izmir (Akyol Cd.)
        lat, lon = 38.0886007, 27.7346069
        x5253, y5253 = wgs84_to_epsg5253(lat, lon, proj)
        assert 550000.0 < x5253 < 580000.0, f"Unexpected EPSG:5253 Easting: {x5253}"
        assert 4200000.0 < y5253 < 4230000.0, f"Unexpected EPSG:5253 Northing: {y5253}"

        back_pt = wgs84_to_canvas(lat, lon, crs_5253, proj)
        assert abs(back_pt.x() - x5253) < 0.01
        assert abs(back_pt.y() - y5253) < 0.01

        lat_rt, lon_rt = canvas_to_wgs84(back_pt, crs_5253, proj)
        assert abs(lat_rt - lat) < 1e-6 and abs(lon_rt - lon) < 1e-6

        # 2. Geodesic bearing, distance & FOV cone polygon in EPSG:5253
        brg_east = bearing_between_wgs84(38.0, 27.7, 38.0, 27.8)
        assert 89.0 < brg_east < 91.0, f"Expected East ~90 deg, got {brg_east}"
        d_short = geodesic_distance_m(38.0886, 27.7346, 38.0887, 27.7346)
        assert 8.0 < d_short < 15.0, f"Unexpected short geodesic distance: {d_short}"
        d_far = geodesic_distance_m(38.0886, 27.7346, 38.0896, 27.7346)
        assert 95.0 < d_far < 125.0, f"Unexpected far geodesic distance: {d_far}"
        cone = build_fov_cone_polygon(lat, lon, heading_deg=265.0, fov_deg=85.0, radius_m=50.0, canvas_crs=crs_5253, project=proj)
        assert not cone.isEmpty() and cone.area() > 1200.0, f"Unexpected cone area: {cone.area()}"

        # 3. Parse Google Maps URLs (dynamic Street View URL + API=1 URL)
        sample_url = (
            "https://www.google.com/maps/@38.0886007,27.7346069,118a,85y,265.5h,92t/"
            "data=!3m7!1e1!3m5!1sS5EiolKvhOt6RDFUsU9IqA!2e0"
        )
        parsed = parse_google_maps_url(sample_url)
        assert parsed is not None
        assert abs(parsed.lat - 38.0886007) < 1e-6
        assert abs(parsed.lon - 27.7346069) < 1e-6
        assert abs(parsed.fov - 85.0) < 0.01
        assert abs(parsed.heading - 265.5) < 0.01
        assert abs(parsed.pitch - 2.0) < 0.01
        assert parsed.pano_id == "S5EiolKvhOt6RDFUsU9IqA"

        api_url = build_street_view_url(lat, lon, heading=135.0, pitch=5.0, fov=75.0)
        parsed_api = parse_google_maps_url(api_url)
        assert parsed_api is not None
        assert abs(parsed_api.heading - 135.0) < 0.1
        assert abs(parsed_api.fov - 75.0) < 0.1

        # 4. Road azimuth snapping in EPSG:5253
        road_lyr = QgsVectorLayer("LineString?crs=EPSG:5253", "test_roads_5253", "memory")
        f_road = QgsFeature()
        f_road.setGeometry(
            QgsGeometry.fromPolylineXY([
                QgsPointXY(x5253 - 40.0, y5253),
                QgsPointXY(x5253 + 40.0, y5253),
            ])
        )
        road_lyr.dataProvider().addFeatures([f_road])
        road_lyr.updateExtents()
        proj.addMapLayer(road_lyr)

        snapped_az = snap_to_nearest_road_azimuth(lat, lon, project=proj, max_distance_m=25.0)
        assert snapped_az is not None and 85.0 <= snapped_az <= 95.0, f"Unexpected snapped azimuth: {snapped_az}"

        off_lat, off_lon = canvas_to_wgs84(QgsPointXY(x5253, y5253 + 10.0), crs_5253, proj)
        detail = snap_to_nearest_road_detail(off_lat, off_lon, project=proj, max_distance_m=18.0)
        assert detail is not None, "Expected point 10m from road centerline to snap within 18m"
        s_lat, s_lon, s_az = detail
        sx_5253, sy_5253 = wgs84_to_epsg5253(s_lat, s_lon, proj)
        assert abs(sy_5253 - y5253) < 0.05 and 85.0 <= s_az <= 95.0

        # 5. EPSG:5253 Observation Logger
        obs_lyr = log_street_view_observation(
            StreetViewState(lat=lat, lon=lon, heading=265.0, pitch=0.0, fov=85.0, pano_id="S5EiolKvhOt6RDFUsU9IqA", url=sample_url),
            note="Akyol Cd. test point",
            lang="en",
        )
        assert obs_lyr is not None and obs_lyr.crs().authid() == MANDATORY_CRS_AUTHID
        assert obs_lyr.featureCount() == 1
        feat = next(obs_lyr.getFeatures())
        assert abs(feat["heading_deg"] - 265.0) < 0.01
        assert feat["pano_id"] == "S5EiolKvhOt6RDFUsU9IqA"
        sl0 = obs_lyr.renderer().symbol().symbolLayer(0)
        assert sl0.dataDefinedProperties().hasProperty(QgsSymbolLayer.Property.PropertyAngle)

        proj.clear()
        print("PASS: test_street_view_pip (5/5 test groups passed)")
    finally:
        qgs.exitQgis()


if __name__ == "__main__":
    run_tests()
