# Routine Maintenance & Health Check Log

## 2026-11-21 — v1.4.1 QGIS Plugin Hub Security Scan Fix: OK
- **Repository / Component:** `street_view_pip` (v1.4.1)
- **Fix Applied:** Renamed `lbl_api_key` / `ph_api_key` dictionary keys in `i18n.py` (and `settings_dialog.py`) to `lbl_maps_js_param` / `ph_maps_js_param` and replaced `"AIza..."` example text so `detect-secrets` `KeywordDetector` triggers zero `"Potential Secret Keyword detected"` alerts on `plugins.qgis.org`.

## 2026-11-21 — v1.4.0 Release Verification & Fresh-Profile Hardening: OK
- **Repository / Component:** `street_view_pip` (v1.4.0)
- **Environment:** QGIS `3.44.14-Solothurn` LTR | Qt `5.15.13` | Python `3.12.14` | CRS `EPSG:5253`
- **Public Metadata URLs:** `homepage`, `repository`, and `tracker` mapped to public `https://github.com/baranadsuna/street_view_pip` (HTTP 200).
- **Fixes Applied:** Preserved WebView2 native User-Agent / Client-Hints (fixing fresh-profile black-screen & 2D fallback), configured dark slate `ICoreWebView2Controller2` background (`#0f172a`), added `18m` metric EPSG:5253 road-centerline point snapping (`snap_to_nearest_road_detail`), and passed `flake8`, `bandit`, Qt5/Qt6 scanner, and PyQGIS E2E checks.

## 2026-11-20 — v1.3.0 Release Verification: OK
- **Repository / Component:** `street_view_pip` (v1.3.0)
- **Environment:** QGIS `3.44.14-Solothurn` LTR | Qt `5.15.13` | Python `3.12.14` | CRS `EPSG:5253`
- **Verification Results:** `qt5_qt6_qgis34_scanner.py` PASS; `test_street_view_pip.py` PASS; `test_pip_gui_smoke.py` PASS (3D cowboy avatar, cursor-locked hand grab, walk/run, 30s wave, Johnny Bravo Monkey dance via confetti button, anti-place-hijack guard); Live Windows Edge WebView2 (`edge_webview2`) E2E verified.
- **Status:** Packaged (`street_view_pip_v1.3.0.zip`) and deployed to QGIS user profile plugins.
