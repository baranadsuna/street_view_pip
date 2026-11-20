# Street View Navigator (PiP) — Academic Methodology & Geodetic Architecture

**Plugin Slug:** `street_view_pip` | **Version:** `1.4.0` | **Mandatory CRS:** `EPSG:5253` (TUREF / TM30) | **Target Runtimes:** QGIS 3.22+ (Qt5) & QGIS 4.x (Qt6)

---

## 1. Geodetic Coordinate & Azimuth Mathematics

Street View camera panoramas operate in spherical geographic coordinates $(\phi, \lambda)$ referenced to WGS84 (`EPSG:4326`), whereas urban planning layers in Turkey operate in the metric **TUREF / TM30** (`EPSG:5253`) Transverse Mercator projection (central meridian $\lambda_0 = 30^\circ\text{E}$).

### 1.1. Bidirectional Projection & Meridian Convergence Preservation
Implemented in `geo_utils.py :: canvas_to_wgs84`, `wgs84_to_canvas`, and `wgs84_to_epsg5253`:

$$
(\phi, \lambda)_{\text{EPSG:4326}} \underset{\mathcal{T}^{-1}}{\overset{\mathcal{T}}{\rightleftharpoons}} (E, N)_{\text{EPSG:5253}}
$$

Because Transverse Mercator grid North diverges from true geographic North by the meridian convergence angle $\gamma \approx (\lambda - \lambda_0)\sin\phi$, computing the Field-of-View (FOV) cone vertices directly in `EPSG:5253` using unrotated grid azimuths introduces angular drift (approx. $-1.40^\circ$ in Tire, İzmir at $\lambda \approx 27.73^\circ\text{E}$). To eliminate convergence distortion, `geo_utils.py :: build_fov_cone_polygon` computes each arc vertex geodesically on the sphere of mean radius $R = 6\,371\,008.8\,\text{m}$ via `destination_point_wgs84`:

$$
\phi_2 = \arcsin\!\Big(\sin\phi_1 \cos\delta + \cos\phi_1 \sin\delta \cos\theta\Big), \quad \delta = \frac{d}{R}
$$

$$
\lambda_2 = \lambda_1 + \operatorname{atan2}\!\Big(\sin\theta \sin\delta \cos\phi_1,\; \cos\delta - \sin\phi_1 \sin\phi_2\Big)
$$

where $\theta \in [\alpha - \frac{\text{FOV}}{2},\; \alpha + \frac{\text{FOV}}{2}]$ sweeps across the camera's horizontal field of view and each $(\phi_2, \lambda_2)$ endpoint is transformed dynamically into the active canvas CRS.

### 1.2. Forward Road-Tangent Alignment (`snap_to_nearest_road_azimuth`)
When a user single-clicks a street without drag-aiming, `geo_utils.py :: snap_to_nearest_road_azimuth` transforms nearby `LineString` road features into metric `EPSG:5253`, identifies the closest segment within $d_{\max} = 35\,\text{m}$, and computes the true initial geodesic forward azimuth:

$$
\alpha = \operatorname{atan2}\!\Big(\sin(\Delta\lambda)\cos\phi_2,\; \cos\phi_1\sin\phi_2 - \sin\phi_1\cos\phi_2\cos(\Delta\lambda)\Big) \pmod{360^\circ}
$$

---

## 2. Picture-in-Picture (PiP) Embedded Chromium Architecture

On Microsoft Windows (both QGIS 3 Qt5 and QGIS 4 Qt6), `webview_host.py :: WebView2HostWidget` binds directly to the Microsoft Edge WebView2 Evergreen Runtime via COM (`WebView2Loader.dll` through `ctypes`), inheriting physical client pixel dimensions via Win32 `GetClientRect`. On Linux/macOS or QtWebEngine builds, it seamlessly delegates to `QWebEngineView`, and in headless `offscreen` test sessions it transitions safely to a non-blocking fallback card.

Two-way camera synchronization parses live URL camera states (`@lat,lon,...,fov y,heading h,tilt t` and `!1s<pano_id>`) and updates `PegmanCanvasMarker` + `CanvasPoseOverlay` in real time.

---

## 3. Verified Academic References

1. **Karney, C. F. F. (2012/2013).** *Algorithms for geodesics.* Journal of Geodesy, 87(1), 43–55. DOI: [`10.1007/s00190-012-0578-z`](https://doi.org/10.1007/s00190-012-0578-z)
2. **Anguelov, D., Dulong, C., Filip, D., Frueh, C., Lafon, S., Lyon, R., Ogale, A., Vincent, L., & Weaver, J. (2010).** *Google Street View: Capturing the World at Street Level.* Computer, 43(6), 32–38. DOI: [`10.1109/MC.2010.170`](https://doi.org/10.1109/MC.2010.170)
3. **Biljecki, F., & Ito, K. (2021).** *Street view imagery in urban analytics and GIS: A review.* Landscape and Urban Planning, 215, 104217. DOI: [`10.1016/j.landurbplan.2021.104217`](https://doi.org/10.1016/j.landurbplan.2021.104217)
