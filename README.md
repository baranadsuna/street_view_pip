# Street View Navigator (PiP)

Interactive Pegman drag-and-drop Street View browser inside a **resizable bottom-right Picture-in-Picture (PiP) overlay** on the QGIS Map Canvas, built for urban planners and GIS analysts working with satellite basemaps and `EPSG:5253` (TUREF / TM30) datasets.

## Features
- **Pegman Drag-and-Drop & Click-to-Drop:** Click the Pegman toolbar icon OR drag the yellow Pegman handle directly out of the PiP corner onto the QGIS Map Canvas (`QgsMapCanvas`).
- **Blue Street View Coverage Overlay:** Automatically lights up streets with Street View coverage over your `Google Satellite` / vector layers while picking or dragging Pegman.
- **Resizable Bottom-Right Picture-in-Picture (PiP):** Anchored neatly in the bottom-right corner of the map canvas; resize smoothly by dragging the top-left corner (`↖`) or edges, pick `S / M / L / Max` size presets, or collapse to a compact bottom-right Pegman pill (`_`).
- **Real Interactive 360° Street View Walking:** Powered by embedded Microsoft Edge WebView2 on Windows (and `QtWebEngineWidgets` on Qt6/Linux/macOS) — pan 360°, zoom, and walk along streets right inside QGIS.
- **Clean Panorama Mode:** Automatically hides Google Maps search bars, info cards, and redundant minimap overlays inside the compact PiP frame (1-click toggleable).
- **Live Two-Way Sync & `EPSG:5253` Field Observation Logger:** Moving or turning inside Street View updates the Pegman pin and geodesic FOV viewing cone live on the QGIS canvas; save field observation points with heading, pano ID, and coordinates directly into `StreetView_Observations_EPSG5253`.
- **QGIS 3 & QGIS 4 (Qt5 & Qt6) Compatible:** Uses strictly `qgis.PyQt` imports, Qt6 scoped enum shims, and `supportsQt6=True`.
