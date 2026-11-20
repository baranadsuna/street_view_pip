# AGENTS.md — `street_view_pip` (Street View Navigator (PiP))

- **CRS Standard:** `EPSG:5253` (TUREF / TM30) for metric road snapping, FOV geometry projection, and observation point logging.
- **Qt5 / Qt6 Compatibility:** All Qt imports go strictly through `qgis.PyQt`; Win32 Edge WebView2 COM runs via `ctypes` (`WebView2Loader.dll`) with `QtWebEngineWidgets` and offscreen fallback.
- **Default UI Language:** 100% English (`language="en"` default, optional `"tr"` toggle).
