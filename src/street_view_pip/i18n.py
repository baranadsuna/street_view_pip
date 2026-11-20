# -*- coding: utf-8 -*-
"""
Lightweight Bilingual Dictionary (100% English Default, Optional Turkish).
"""

STRINGS = {
    "en": {
        "plugin_name": "Street View Navigator (PiP)",
        "toolbar_pegman": "Drop Pegman on Map (Street View)",
        "toolbar_toggle_pip": "Toggle Street View PiP Window",
        "toolbar_coverage": "Toggle Street View Blue Coverage",
        "toolbar_settings": "Street View Settings",
        "pip_title": "Street View",
        "pill_label": "Street View | Drag Pegman",
        "pegman_tooltip": (
            "Click to activate Pegman Map Tool, OR drag & drop Pegman directly onto the map!"
        ),
        "resize_grip_tooltip": "Drag top-left corner to resize the PiP window",
        "coverage_tooltip": "Toggle Street View Blue Coverage Lines on Map",
        "clean_mode_tooltip": "Clean Panorama Mode (hide Google search & minimap clutter)",
        "follow_tooltip": "Auto-Pan QGIS canvas to follow Pegman while walking",
        "log_obs_tooltip": "Log current Street View point into EPSG:5253 Observations layer",
        "open_browser_tooltip": "Open current Street View in external browser",
        "copy_coords_tooltip": "Copy EPSG:5253 & WGS84 coordinates to clipboard",
        "settings_tooltip": "Configure Street View provider, API key, and defaults",
        "popout_tooltip": "Expand / Restore PiP size",
        "collapse_tooltip": "Collapse to bottom-right Pegman pill",
        "close_tooltip": "Hide Street View PiP window",
        "snap_corner_tooltip": "Snap PiP window back to bottom-right corner",
        "dance_tooltip": "Do the Monkey! (Johnny Bravo Dance + Confetti)",
        "status_ready": "Click a blue street once to drop Pegman",
        "status_loading": "Loading 360\u00b0 Street View...",
        "status_hover": "Drop Pegman -> EPSG:5253 ({x:.1f}, {y:.1f}) | {lat:.5f}, {lon:.5f}",
        "status_dragging": "Release mouse on a street to open Street View...",
        "status_no_sv": "No Street View here — drag Pegman onto a blue street line",
        "status_live": "5253: {x:.0f}, {y:.0f} | {hdg:.0f}\u00b0",
        "preset_s": "S",
        "preset_m": "M",
        "preset_l": "L",
        "preset_max": "Max",
        "obs_saved": (
            "Logged Street View observation at EPSG:5253 ({x:.1f}, {y:.1f}) heading {hdg:.0f} deg."
        ),
        "coords_copied": (
            "Copied coordinates to clipboard: EPSG:5253 ({x:.1f}, {y:.1f}) / "
            "WGS84 ({lat:.6f}, {lon:.6f})."
        ),
        "coverage_layer_name": "Street View Coverage (SVV Overlay)",
        "obs_layer_name": "StreetView_Observations_EPSG5253",
        "fallback_title": "Embedded WebView Unavailable in Current Session",
        "fallback_desc": (
            "Microsoft Edge WebView2 (Windows) or QtWebEngine is not active in this runtime "
            "(for example headless offscreen testing or restricted environment). "
            "You can still drop Pegman, sync EPSG:5253 coordinates, and launch Street View externally."
        ),
        "fallback_btn": "Open Street View in Default Browser",
        "settings_title": "Street View Navigator (PiP) — Settings",
        "grp_provider": "Street View Imagery Provider",
        "lbl_provider": "Active Provider:",
        "prov_google_direct": "Google Street View (Direct WebView2 — No API Key Required)",
        "prov_google_js": "Google Maps JS API (Custom API Key — Native Fullscreen Bridge)",
        "prov_panoramax": "Panoramax (Open-Source Street Imagery — No Key Required)",
        "lbl_maps_js_param": "Google Maps JS Key (Optional):",
        "ph_maps_js_param": "Paste custom browser key only if using Google Maps JS API mode",
        "grp_behavior": "Map Interaction && EPSG:5253 Synchronization",
        "chk_auto_coverage": "Auto-show blue Street View coverage lines when Pegman is active",
        "chk_snap_road": "Auto-align Pegman heading with nearest QGIS road layer",
        "chk_follow_pegman": "Auto-pan QGIS canvas to keep Pegman visible while walking",
        "chk_clean_mode": "Clean Panorama Mode (hide Google search box, card, and minimap in PiP)",
        "lbl_default_size": "Default PiP Window Preset:",
        "lbl_language": "Plugin Interface Language:",
        "btn_save": "Save Settings",
        "btn_cancel": "Cancel",
    },
    "tr": {
        "plugin_name": "Street View Gezgini (PiP)",
        "toolbar_pegman": "Pegman'i Haritaya Birak (Street View)",
        "toolbar_toggle_pip": "Street View PiP Penceresini Ac/Kapat",
        "toolbar_coverage": "Street View Mavi Kapsama Agini Ac/Kapat",
        "toolbar_settings": "Street View Ayarlari",
        "pip_title": "Street View PiP",
        "pill_label": "Street View  |  Pegman'i Surukle",
        "pegman_tooltip": (
            "Pegman aracini acmak icin tiklayin VEYA Pegman'i dogrudan haritaya surukleyip birakin!"
        ),
        "resize_grip_tooltip": "PiP penceresini buyutup kucultmek icin sol ust koseden surukleyin",
        "coverage_tooltip": "Haritada Street View Mavi Kapsama Cizgilerini Ac/Kapat",
        "clean_mode_tooltip": "Temiz Panorama Modu (Google arama ve mini haritayi gizle)",
        "follow_tooltip": "Sokakta yururken QGIS haritasini Pegman ile otomatik kaydir",
        "log_obs_tooltip": "Mevcut Street View noktasini EPSG:5253 Gozlem katmanina kaydet",
        "open_browser_tooltip": "Mevcut Street View gorunumunu dis tarayicida ac",
        "copy_coords_tooltip": "EPSG:5253 ve WGS84 koordinatlarini panoya kopyala",
        "settings_tooltip": "Saglayici, API anahtari ve varsayilan ayarlari duzenle",
        "popout_tooltip": "PiP penceresini buyut / geri al",
        "collapse_tooltip": "Sag alt kosede kucuk kapsule daralt",
        "close_tooltip": "Street View PiP penceresini gizle",
        "snap_corner_tooltip": "PiP penceresini sag alt koseye geri sabitle",
        "dance_tooltip": "Johnny Bravo Maymun Dansi! (Konfeti)",
        "status_ready": "Sokaga 1 kez tiklayip Pegman'i birakin",
        "status_loading": "360\u00b0 Street View yukleniyor...",
        "status_hover": "Pegman -> EPSG:5253 ({x:.1f}, {y:.1f}) | {lat:.5f}, {lon:.5f}",
        "status_dragging": "Street View acmak icin fareyi sokak uzerinde birakin...",
        "status_no_sv": "Burada Street View yok — Pegman'i mavi cizgiye birakin",
        "status_live": "5253: {x:.1f}, {y:.1f} | {lat:.5f}, {lon:.5f} | Yon {hdg:.0f} der",
        "preset_s": "K",
        "preset_m": "O",
        "preset_l": "B",
        "preset_max": "Tam",
        "obs_saved": "Street View gozlemi EPSG:5253 ({x:.1f}, {y:.1f}), {hdg:.0f} der aci ile kaydedildi.",
        "coords_copied": "Koordinatlar kopyalandi: EPSG:5253 ({x:.1f}, {y:.1f}) / WGS84 ({lat:.6f}, {lon:.6f}).",
        "coverage_layer_name": "Street View Kapsama Agi (SVV)",
        "obs_layer_name": "StreetView_Observations_EPSG5253",
        "fallback_title": "Gomulu Tarayici Bu Oturumda Kullanilamiyor",
        "fallback_desc": (
            "Microsoft Edge WebView2 veya QtWebEngine bu calisma ortaminda aktif degil. "
            "Pegman yerlestirmeye ve dis tarayicida Street View acmaya devam edebilirsiniz."
        ),
        "fallback_btn": "Street View'i Dis Tarayicida Ac",
        "settings_title": "Street View Gezgini (PiP) — Ayarlar",
        "grp_provider": "Street View Goruntu Saglayicisi",
        "lbl_provider": "Aktif Saglayici:",
        "prov_google_direct": "Google Street View (Dogrudan WebView2 — API Anahtari Gereksiz)",
        "prov_google_js": "Google Maps JS API (Ozel Anahtar — Tam Ekran JS Koprusu)",
        "prov_panoramax": "Panoramax (Acik Kaynak Sokak Goruntusu — Anahtarsiz)",
        "lbl_maps_js_param": "Google Maps JS Anahtari (Opsiyonel):",
        "ph_maps_js_param": "Yalnizca JS API modu kullanilacaksa ozel tarayici anahtarini girin",
        "grp_behavior": "Harita Etkilesimi ve EPSG:5253 Senkronizasyonu",
        "chk_auto_coverage": "Pegman aktifken mavi Street View kapsama cizgilerini otomatik goster",
        "chk_snap_road": "Pegman bakis yonunu en yakin yol katmanina otomatik hizala",
        "chk_follow_pegman": "Sokakta gezerken QGIS haritasini Pegman ile otomatik takip et",
        "chk_clean_mode": "Temiz Panorama Modu (PiP icindeki arama kutusu ve mini haritayi gizle)",
        "lbl_default_size": "Varsayilan PiP Pencere Boyutu:",
        "lbl_language": "Eklenti Arayuz Dili:",
        "btn_save": "Ayarlari Kaydet",
        "btn_cancel": "Iptal",
    },
}


def tr_text(lang: str, key: str, **kwargs) -> str:
    """Return localized string defaulting strictly to English ('en')."""
    table = STRINGS.get(lang, STRINGS["en"])
    text = table.get(key, STRINGS["en"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
