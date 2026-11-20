# Third-Party Notices

This plugin (`street_view_pip`) is written entirely from scratch in clean-room Python without copying external plugin codebases.

- **QGIS Python API & PyQt (`qgis.PyQt`):** Licensed under GNU GPL v2/v3.
- **Microsoft Edge WebView2 Evergreen Runtime & `WebView2Loader.dll`:** Accessed dynamically at runtime via standard Windows COM ABI (`CreateCoreWebView2EnvironmentWithOptions` per Microsoft WebView2 SDK specification, MIT/BSD-style redistributable interface); no proprietary WebView2 binaries are bundled inside this source repository.
- **Google Maps URLs & Street View:** Accessed via official Google Maps URLs scheme (`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=...`) or user-supplied Google Maps JavaScript API key; Google Maps copyright & capture attribution overlays remain intact.
- **Panoramax:** Optional open-source street-level imagery integration (`https://api.panoramax.xyz/`).
