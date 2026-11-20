# -*- coding: utf-8 -*-
"""
Embedded Street View Web Browser Host (Edge WebView2 + QtWebEngine + Fallback).

Provides a hardware-accelerated Chromium viewport embedded directly inside a Qt
widget without external pip dependencies:
  1. On Windows (QGIS 3 Qt5 & QGIS 4 Qt6): uses Microsoft Edge WebView2 via
     WebView2Loader.dll COM (ctypes) attached to the widget's native HWND.
  2. On QGIS 4 / Linux / macOS with QtWebEngineWidgets: uses QWebEngineView.
  3. In headless offscreen CI or restricted environments: renders a clean,
     non-crashing fallback status card with external browser launch.
"""

import ctypes
from ctypes import wintypes
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Callable, List, Optional

from qgis.PyQt import QtCore, QtWidgets

from .geo_utils import StreetViewState, build_street_view_url, parse_google_maps_url
from .i18n import tr_text
from .qt_compat import ALIGN_CENTER, CURSOR_POINTING_HAND, log_debug

# --- JavaScript Snippets for Google Maps Direct & JS API Modes ---


class _Guid(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _Wv2Color(ctypes.Structure):
    _fields_ = [
        ("A", ctypes.c_ubyte),
        ("R", ctypes.c_ubyte),
        ("G", ctypes.c_ubyte),
        ("B", ctypes.c_ubyte),
    ]


# Keep WebView2's native User-Agent untouched so Sec-CH-UA headers and WebGL
# remain consistent on brand-new user profiles; only set dark background (#0f172a).
_IID_CONTROLLER2 = _Guid(
    0xc979903e,
    0xd4ca,
    0x4228,
    (ctypes.c_ubyte * 8)(0x92, 0xeb, 0x47, 0xee, 0x3f, 0xa9, 0x6e, 0xab),
)

EARLY_CLEAN_DOCUMENT_JS = r"""
(() => {
  if (typeof window.__qgisCleanMode === 'undefined') {
    window.__qgisCleanMode = true;
  }
  const applyQgisSvCleanup = () => {
    const hideEl = (el, tag) => {
      if (!el || el.id === 'scene' || el.id === 'content-container' || el.querySelector('canvas')) return;
      el.dataset[tag] = '1';
      el.style.setProperty('display', 'none', 'important');
    };

    // 1. Suppress Google Chrome promo modal, Sign-in button, Apps launcher, Tooltips & Place Panels
    for (const dlg of document.querySelectorAll('[role="dialog"], [role="alertdialog"], div')) {
      if (dlg.querySelector('canvas')) continue;
      const r = dlg.getBoundingClientRect();
      if (r.width > 120 && r.width < 460 && r.height > 70 && r.height < 380) {
        const t = dlg.innerText || '';
        if (
          t.includes("Chrome'u") || t.includes("Chrome'a") ||
          t.includes('Switch to Chrome') || t.includes('Get Google Chrome')
        ) {
          hideEl(dlg, 'qgisPromoHidden');
        }
      }
    }

    // Kill "Yan paneli daralt" / "Collapse side panel" tooltips and opened Place/Review drawers
    for (const tt of document.querySelectorAll('[role="tooltip"], .tooltip, div[aria-live]')) {
      const t = (tt.innerText || '').toLowerCase();
      if (t.includes('yan panel') || t.includes('side panel') || t.includes('daralt') || t.includes('collapse')) {
        hideEl(tt, 'qgisPromoHidden');
      }
    }

    if (!document.querySelector('canvas')) return;

    const hideOutermostNonCanvas = (el, tag) => {
      if (!el || el.querySelector('canvas')) return;
      let cur = el;
      for (let i = 0; i < 7 && cur.parentElement; i++) {
        const p = cur.parentElement;
        if (
          p === document.body ||
          p === document.documentElement ||
          p.id === 'content-container' ||
          p.id === 'scene' ||
          p.querySelector('canvas')
        ) {
          break;
        }
        const r = p.getBoundingClientRect();
        if (r.width >= window.innerWidth * 0.96 && r.height >= window.innerHeight * 0.96) {
          break;
        }
        cur = p;
      }
      hideEl(cur, tag);
    };

    // Auto-collapse Google Place Side Panel cleanly so Street View canvas stays 100% full-width
    const panelBtns = document.querySelectorAll(
      'button[aria-label*="Yan panel" i], button[aria-label*="Collapse side panel" i]'
    );
    for (const btn of panelBtns) {
      const br = btn.getBoundingClientRect();
      if (br.width > 0 && br.height > 0 && !btn.dataset.qgisClicked) {
        btn.dataset.qgisClicked = '1';
        btn.click();
      }
      hideEl(btn, 'qgisPromoHidden');
    }
    for (const pane of document.querySelectorAll('#QA0Szd, [role="main"], .k7jAl, .XltNde, .bJzME, .m6QErb')) {
      if (pane.querySelector('canvas')) continue;
      const r = pane.getBoundingClientRect();
      if (r.width > 30 && r.height > 30) {
        hideOutermostNonCanvas(pane, 'qgisPromoHidden');
      }
    }
    const sc = document.getElementById('scene');
    if (sc && document.querySelector('canvas')) {
      const sr = sc.getBoundingClientRect();
      if (sr.left > 10 || sr.width < window.innerWidth - 20) {
        sc.style.setProperty('left', '0px', 'important');
        sc.style.setProperty('width', '100%', 'important');
        window.dispatchEvent(new Event('resize'));
      }
    }

    for (const el of document.querySelectorAll('a, button, [role="button"]')) {
      if (el.querySelector('canvas')) continue;
      const r = el.getBoundingClientRect();
      if (r.top < 110 && r.height > 14 && r.height < 84) {
        const lbl = (el.getAttribute('aria-label') || el.innerText || '').toLowerCase();
        if (
          lbl.includes('oturum') || lbl.includes('sign in') ||
          lbl.includes('google uygulamalar') || lbl.includes('google apps')
        ) {
          hideEl(el, 'qgisPromoHidden');
        }
      }
    }

    // 2. Clean Panorama Mode chrome hiding (toggleable via window.__qgisCleanMode)
    if (!window.__qgisCleanMode) {
      for (const el of document.querySelectorAll('[data-qgis-sv-hidden="1"]')) {
        el.style.removeProperty('display');
        delete el.dataset.qgisSvHidden;
      }
      return;
    }

    for (const inp of document.querySelectorAll('input, [role="search"]')) {
      let cur = inp;
      for (let i = 0; i < 6 && cur && cur.parentElement; i++) {
        const r = cur.getBoundingClientRect();
        if (r.top < 110 && r.height > 25 && r.height < 115 && !cur.querySelector('canvas')) {
          const pr = cur.parentElement.getBoundingClientRect();
          if (pr.top < 110 && pr.height < 115 && !cur.parentElement.querySelector('canvas')) {
            cur = cur.parentElement;
          } else {
            hideEl(cur, 'qgisSvHidden');
            break;
          }
        } else {
          cur = cur.parentElement;
        }
      }
    }

    const minimaps = document.querySelectorAll(
      '#minimap, .widget-minimap, [aria-label*="Harita" i], [aria-label*="Map" i]'
    );
    for (const mm of minimaps) {
      const r = mm.getBoundingClientRect();
      const hasScene = Boolean(mm.querySelector('canvas.widget-scene-canvas'));
      if (r.width > 70 && r.width < 380 && r.height > 55 && r.height < 280 && !hasScene) {
        hideEl(mm, 'qgisSvHidden');
      }
    }

    for (const el of document.querySelectorAll('div')) {
      if (el.querySelector('canvas')) continue;
      const r = el.getBoundingClientRect();
      if (r.width >= 150 && r.width <= window.innerWidth && r.height >= 45 && r.height <= 320) {
        const txt = el.innerText || '';
        if (
          (txt.includes('Street View') || txt.includes('Daha fazla tarih') ||
           txt.includes('See more dates') || txt.includes('Yorum yaz') || txt.includes('yorum')) &&
          r.height < window.innerHeight * 0.85
        ) {
          hideEl(el, 'qgisSvHidden');
        }
      }
    }

    for (const logo of document.querySelectorAll('img[src*="MapsLogo" i], img[src*="mapslogo" i], .J6jgHf')) {
      hideEl(logo, 'qgisSvHidden');
    }

    for (const el of document.querySelectorAll('button, [role="button"], a, .goog-container')) {
      if (el.querySelector('canvas')) continue;
      const r = el.getBoundingClientRect();
      if (r.top < 110 && r.height >= 20 && r.height <= 68 && r.width <= 160) {
        const rawLbl = el.getAttribute('aria-label') || el.getAttribute('data-tooltip') || el.innerText || '';
        const label = rawLbl.toLowerCase();
        if (
          label.includes('kapat') || label.includes('close') ||
          label.includes('payla') || label.includes('share') ||
          label.includes('keyboard') || label.includes('input tools') ||
          (r.left > window.innerWidth - 200 && r.width <= 76)
        ) {
          hideEl(el, 'qgisSvHidden');
        }
      }
    }
  };

  window.__applyQgisSvCleanup = applyQgisSvCleanup;
  const start = () => {
    applyQgisSvCleanup();
    if (!window.__qgisSvObserver) {
      window.__qgisSvObserver = new MutationObserver(() => applyQgisSvCleanup());
      window.__qgisSvObserver.observe(document.documentElement || document.body, { childList: true, subtree: true });
      setInterval(applyQgisSvCleanup, 500);
    }
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
"""

CLEAN_PANORAMA_JS_TEMPLATE = r"""
(() => {
  window.__qgisCleanMode = __ENABLE_CLEAN__;
  if (typeof window.__applyQgisSvCleanup === 'function') {
    window.__applyQgisSvCleanup();
  }
  return document.querySelectorAll('[data-qgis-sv-hidden="1"]').length;
})();
"""

POLL_POSE_JS = r"""
(() => {
  if (window.__qgisJsPanoPose) {
    return JSON.stringify(window.__qgisJsPanoPose);
  }
  return window.location.href;
})();
"""


def build_google_js_api_html(
    api_key: str,
    lat: float,
    lon: float,
    heading: float,
    pitch: float,
    fov: float,
) -> str:
    """Build clean HTML5 Google Maps JS API StreetViewPanorama page (optional key mode)."""
    zoom = max(0.0, min(4.0, math_log2_approx_zoom(fov)))
    safe_key = json.dumps(api_key.strip())[1:-1]
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body, #pano {{ margin: 0; padding: 0; width: 100%; height: 100%; background: #0b1120; overflow: hidden; }}
  </style>
</head>
<body>
  <div id="pano"></div>
  <script>
    window.__qgisJsPanoPose = {{lat: {lat}, lon: {lon}, heading: {heading}, pitch: {pitch}, fov: {fov}, pano: ""}};
    function initPano() {{
      const pos = {{ lat: {lat}, lng: {lon} }};
      const sv = new google.maps.StreetViewService();
      const pano = new google.maps.StreetViewPanorama(document.getElementById("pano"), {{
        position: pos,
        pov: {{ heading: {heading}, pitch: {pitch} }},
        zoom: {zoom:.2f},
        addressControl: false,
        fullscreenControl: false,
        linksControl: true,
        panControl: true,
        enableCloseButton: false,
      }});
      const syncPose = () => {{
        const p = pano.getPosition();
        const pov = pano.getPov();
        const z = pano.getZoom() || 1;
        const estFov = Math.max(15, Math.min(115, 180 / Math.pow(2, z)));
        if (p) {{
          window.__qgisJsPanoPose = {{
            lat: p.lat(),
            lon: p.lng(),
            heading: ((pov.heading % 360) + 360) % 360,
            pitch: pov.pitch || 0,
            fov: estFov,
            pano: pano.getPano() || ""
          }};
        }}
      }};
      pano.addListener("position_changed", syncPose);
      pano.addListener("pov_changed", syncPose);
      pano.addListener("pano_changed", syncPose);
      sv.getPanorama({{ location: pos, radius: 75 }}, (data, status) => {{
        if (status === "OK" && data && data.location) {{
          pano.setPano(data.location.pano);
        }}
      }});
    }}
  </script>
  <script async defer src="https://maps.googleapis.com/maps/api/js?key={safe_key}&callback=initPano"></script>
</body>
</html>"""


def math_log2_approx_zoom(fov: float) -> float:
    import math
    return math.log2(180.0 / max(20.0, min(120.0, float(fov))))


# --- Windows Edge WebView2 COM Helpers ---

def find_webview2_loader_dll() -> Optional[str]:
    """Locate WebView2Loader.dll on Windows without shipping external binaries."""
    if os.name != "nt":
        return None
    candidates: List[Path] = []
    try:
        import wx  # Bundled in standard OSGeo4W / QGIS Windows installers
        candidates.append(Path(wx.__file__).resolve().parent / "WebView2Loader.dll")
    except (ImportError, OSError, AttributeError) as exc:
        log_debug(f"wx WebView2Loader lookup skipped: {exc}")
    plugin_dir = Path(__file__).resolve().parent
    candidates.append(plugin_dir / "WebView2Loader.dll")
    exe_dir = Path(sys.executable).resolve().parent
    candidates.append(exe_dir / "WebView2Loader.dll")
    candidates.append(Path(sys.prefix) / "Lib" / "site-packages" / "wx" / "WebView2Loader.dll")
    qgis_prefix = os.environ.get("QGIS_PREFIX_PATH")
    if qgis_prefix:
        qp = Path(qgis_prefix)
        candidates.append(qp / "bin" / "WebView2Loader.dll")
        candidates.append(qp.parent / "apps" / "Python312" / "Lib" / "site-packages" / "wx" / "WebView2Loader.dll")
    for cand in candidates:
        if cand.exists() and cand.is_file():
            return str(cand)
    return None


class _Win32Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


def _make_com_handler(invoke_fn: Callable, argtypes: list):
    """Create a reference-counted COM callback implementing IUnknown + Invoke."""
    qi_t = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
    addref_t = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
    release_t = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
    invoke_t = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)

    class VTable(ctypes.Structure):
        _fields_ = [
            ("QueryInterface", qi_t),
            ("AddRef", addref_t),
            ("Release", release_t),
            ("Invoke", invoke_t),
        ]

    class ComObj(ctypes.Structure):
        _fields_ = [("lpVtbl", ctypes.POINTER(VTable))]

    refcount = [1]

    def _qi(this, riid, ppv):
        if ppv:
            ppv[0] = this
            refcount[0] += 1
        return 0

    def _addref(this):
        refcount[0] += 1
        return refcount[0]

    def _release(this):
        refcount[0] -= 1
        return max(0, refcount[0])

    def _invoke(this, *args):
        try:
            return int(invoke_fn(*args) or 0)
        except Exception as exc:
            log_debug(f"WebView2 COM callback failed: {exc}")
            return 0

    vt = VTable(qi_t(_qi), addref_t(_addref), release_t(_release), invoke_t(_invoke))
    obj = ComObj(ctypes.pointer(vt))
    obj._keepalive = (vt,)
    return obj


def _call_vtable(ptr: int, index: int, restype, argtypes: list, *args):
    vtbl_ptr = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return proto(vtbl_ptr[0][index])(ptr, *args)


class WebView2HostWidget(QtWidgets.QWidget):
    """Hosts Microsoft Edge WebView2 inside a Qt QWidget via native HWND."""

    urlChanged = QtCore.pyqtSignal(str)
    navigationFinished = QtCore.pyqtSignal(str)
    scriptResult = QtCore.pyqtSignal(str)
    backendFailed = QtCore.pyqtSignal(str)

    def __init__(self, dll_path: str, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._dll_path = dll_path
        self._env_ptr: Optional[int] = None
        self._ctrl_ptr: Optional[int] = None
        self._wv_ptr: Optional[int] = None
        self._handlers: list = []
        self._initialized = False
        self._closing = False
        self._pending_nav: Optional[tuple] = None  # ("url" | "html", payload)
        self._hwnd: int = 0

        wa_native = (
            QtCore.Qt.WidgetAttribute.WA_NativeWindow
            if hasattr(QtCore.Qt, "WidgetAttribute")
            else QtCore.Qt.WA_NativeWindow
        )
        self.setAttribute(wa_native, True)
        QtCore.QTimer.singleShot(20, self._init_webview2)

    def _init_webview2(self) -> None:
        if self._closing or self._initialized:
            return
        try:
            ctypes.oledll.ole32.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
            self._loader = ctypes.WinDLL(self._dll_path)
            self._hwnd = int(self.winId())
            user_data = os.path.join(tempfile.gettempdir(), "qgis_street_view_pip_wv2")
            os.makedirs(user_data, exist_ok=True)

            def on_env(err_code, env_ptr):
                if self._closing or err_code != 0 or not env_ptr:
                    self.backendFailed.emit(f"WebView2 environment error: {err_code}")
                    return 0
                self._env_ptr = env_ptr
                _call_vtable(env_ptr, 1, ctypes.c_ulong, [])  # AddRef
                h_ctrl = _make_com_handler(on_ctrl, [ctypes.c_long, ctypes.c_void_p])
                self._handlers.append(h_ctrl)
                _call_vtable(
                    env_ptr,
                    3,  # CreateCoreWebView2Controller
                    ctypes.c_long,
                    [wintypes.HWND, ctypes.c_void_p],
                    self._hwnd,
                    ctypes.byref(h_ctrl),
                )
                return 0

            def on_ctrl(err_code, ctrl_ptr):
                if self._closing or err_code != 0 or not ctrl_ptr:
                    self.backendFailed.emit(f"WebView2 controller error: {err_code}")
                    return 0
                self._ctrl_ptr = ctrl_ptr
                _call_vtable(ctrl_ptr, 1, ctypes.c_ulong, [])  # AddRef
                self._apply_controller_background(ctrl_ptr)
                _call_vtable(ctrl_ptr, 4, ctypes.c_long, [wintypes.BOOL], bool(self.isVisible()))

                wv_ptr = ctypes.c_void_p()
                _call_vtable(ctrl_ptr, 25, ctypes.c_long, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(wv_ptr))
                self._wv_ptr = wv_ptr.value
                if self._wv_ptr:
                    _call_vtable(self._wv_ptr, 1, ctypes.c_ulong, [])
                    self._register_early_script()
                    self._wire_events()
                    self._initialized = True
                    self._sync_bounds()
                    if self._pending_nav:
                        kind, payload = self._pending_nav
                        self._pending_nav = None
                        if kind == "url":
                            self.navigate(payload)
                        else:
                            self.set_html(payload)
                return 0

            h_env = _make_com_handler(on_env, [ctypes.c_long, ctypes.c_void_p])
            self._handlers.append(h_env)
            create_fn = self._loader.CreateCoreWebView2EnvironmentWithOptions
            create_fn.restype = ctypes.c_long
            create_fn.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_void_p]
            hr = create_fn(None, user_data, None, ctypes.byref(h_env))
            if hr != 0:
                self.backendFailed.emit(f"CreateCoreWebView2EnvironmentWithOptions failed (hr={hr})")
        except Exception as exc:
            self.backendFailed.emit(str(exc))

    def _apply_controller_background(self, ctrl_ptr: int) -> None:
        """Set WebView2 initial background to dark slate (#0f172a) to prevent flash."""
        try:
            c2_ptr = ctypes.c_void_p()
            hr_qi = _call_vtable(
                ctrl_ptr,
                0,
                ctypes.c_long,
                [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
                ctypes.byref(_IID_CONTROLLER2),
                ctypes.byref(c2_ptr),
            )
            if hr_qi == 0 and c2_ptr.value:
                bg = _Wv2Color(255, 15, 23, 42)
                _call_vtable(c2_ptr.value, 27, ctypes.c_long, [_Wv2Color], bg)
                _call_vtable(c2_ptr.value, 2, ctypes.c_ulong, [])
        except (OSError, ValueError, ctypes.ArgumentError) as exc:
            log_debug(f"WebView2 background color configuration skipped: {exc}")

    def _register_early_script(self) -> None:
        """Register early DOM cleaner script without mutating the native User-Agent."""
        if not self._wv_ptr or self._closing:
            return
        try:
            h_early = _make_com_handler(lambda _err, _sid: 0, [ctypes.c_long, ctypes.c_wchar_p])
            self._handlers.append(h_early)
            _call_vtable(
                self._wv_ptr,
                27,  # AddScriptToExecuteOnDocumentCreated
                ctypes.c_long,
                [ctypes.c_wchar_p, ctypes.c_void_p],
                EARLY_CLEAN_DOCUMENT_JS,
                ctypes.byref(h_early),
            )
        except (OSError, ValueError, RuntimeError) as exc:
            log_debug(f"WebView2 early script registration skipped: {exc}")

    def _wire_events(self) -> None:
        if not self._wv_ptr:
            return
        tok = ctypes.c_int64()

        def emit_current_uri():
            if not self._wv_ptr or self._closing:
                return ""
            uri_ptr = ctypes.c_wchar_p()
            hr = _call_vtable(self._wv_ptr, 4, ctypes.c_long, [ctypes.POINTER(ctypes.c_wchar_p)], ctypes.byref(uri_ptr))
            uri = uri_ptr.value or "" if hr == 0 else ""
            if uri_ptr.value:
                ctypes.oledll.ole32.CoTaskMemFree(ctypes.cast(uri_ptr, ctypes.c_void_p))
            return uri

        def on_src_changed(sender, args):
            uri = emit_current_uri()
            if uri:
                self.urlChanged.emit(uri)
            return 0

        def on_hist_changed(sender, args):
            uri = emit_current_uri()
            if uri:
                self.urlChanged.emit(uri)
            return 0

        def on_nav_completed(sender, args):
            uri = emit_current_uri()
            if uri:
                self.navigationFinished.emit(uri)
            return 0

        def on_new_window(sender, args):
            # Suppress stray popups inside the compact PiP container
            if args:
                _call_vtable(args, 6, ctypes.c_long, [wintypes.BOOL], True)  # put_Handled(True)
            return 0

        h_src = _make_com_handler(on_src_changed, [ctypes.c_void_p, ctypes.c_void_p])
        h_hist = _make_com_handler(on_hist_changed, [ctypes.c_void_p, ctypes.c_void_p])
        h_nav = _make_com_handler(on_nav_completed, [ctypes.c_void_p, ctypes.c_void_p])
        h_win = _make_com_handler(on_new_window, [ctypes.c_void_p, ctypes.c_void_p])
        self._handlers.extend([h_src, h_hist, h_nav, h_win])

        _call_vtable(
            self._wv_ptr, 11, ctypes.c_long, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64)],
            ctypes.byref(h_src), ctypes.byref(tok),
        )
        _call_vtable(
            self._wv_ptr, 13, ctypes.c_long, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64)],
            ctypes.byref(h_hist), ctypes.byref(tok),
        )
        _call_vtable(
            self._wv_ptr, 15, ctypes.c_long, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64)],
            ctypes.byref(h_nav), ctypes.byref(tok),
        )
        _call_vtable(
            self._wv_ptr, 44, ctypes.c_long, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64)],
            ctypes.byref(h_win), ctypes.byref(tok),
        )

    def _sync_bounds(self) -> None:
        if not self._ctrl_ptr or self._closing:
            return
        rect = _Win32Rect(0, 0, max(1, self.width()), max(1, self.height()))
        if self._hwnd:
            ok = ctypes.windll.user32.GetClientRect(self._hwnd, ctypes.byref(rect))
            if not ok or rect.right <= 0 or rect.bottom <= 0:
                dpr = self.devicePixelRatioF()
                rect = _Win32Rect(0, 0, max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
        _call_vtable(self._ctrl_ptr, 6, ctypes.c_long, [_Win32Rect], rect)
        _call_vtable(self._ctrl_ptr, 23, ctypes.c_long, [])  # NotifyParentWindowPositionChanged

    def navigate(self, url: str) -> None:
        if self._closing:
            return
        if not self._wv_ptr:
            self._pending_nav = ("url", url)
            return
        _call_vtable(self._wv_ptr, 5, ctypes.c_long, [ctypes.c_wchar_p], url)

    def set_html(self, html: str) -> None:
        if self._closing:
            return
        if not self._wv_ptr:
            self._pending_nav = ("html", html)
            return
        _call_vtable(self._wv_ptr, 6, ctypes.c_long, [ctypes.c_wchar_p], html)

    def run_script(self, js_code: str, callback: Optional[Callable[[str], None]] = None) -> None:
        if self._closing or not self._wv_ptr:
            return

        def on_done(err_code, result_json):
            if err_code == 0 and result_json is not None and callback is not None:
                try:
                    val = json.loads(result_json)
                    if not isinstance(val, str):
                        val = json.dumps(val)
                except (ValueError, TypeError):
                    val = str(result_json)
                callback(val)
            return 0

        h_exec = _make_com_handler(on_done, [ctypes.c_long, ctypes.c_wchar_p])
        # Keep bounded ring of transient script handlers to avoid unbounded growth
        if len(self._handlers) > 64:
            self._handlers = self._handlers[:16] + self._handlers[-24:]
        self._handlers.append(h_exec)
        _call_vtable(
            self._wv_ptr,
            29,  # ExecuteScript
            ctypes.c_long,
            [ctypes.c_wchar_p, ctypes.c_void_p],
            js_code,
            ctypes.byref(h_exec),
        )

    def set_webview_visible(self, visible: bool) -> None:
        if self._ctrl_ptr and not self._closing:
            _call_vtable(self._ctrl_ptr, 4, ctypes.c_long, [wintypes.BOOL], bool(visible))
            if visible:
                self._sync_bounds()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_bounds()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self._ctrl_ptr and not self._closing:
            _call_vtable(self._ctrl_ptr, 23, ctypes.c_long, [])

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.set_webview_visible(True)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.set_webview_visible(False)

    def cleanup(self) -> None:
        self._closing = True
        if self._ctrl_ptr:
            try:
                _call_vtable(self._ctrl_ptr, 24, ctypes.c_long, [])  # Close
                _call_vtable(self._ctrl_ptr, 2, ctypes.c_ulong, [])  # Release
            except Exception as exc:
                log_debug(f"WebView2 controller cleanup warning: {exc}")
            self._ctrl_ptr = None
        if self._wv_ptr:
            try:
                _call_vtable(self._wv_ptr, 2, ctypes.c_ulong, [])
            except Exception as exc:
                log_debug(f"WebView2 core cleanup warning: {exc}")
            self._wv_ptr = None
        if self._env_ptr:
            try:
                _call_vtable(self._env_ptr, 2, ctypes.c_ulong, [])
            except Exception as exc:
                log_debug(f"WebView2 environment cleanup warning: {exc}")
            self._env_ptr = None
        self._handlers.clear()


class StreetViewBrowserWidget(QtWidgets.QWidget):
    """Unified embedded Street View browser supporting WebView2, QtWebEngine, and Fallback."""

    viewpointChanged = QtCore.pyqtSignal(object)  # StreetViewState
    streetViewUnavailable = QtCore.pyqtSignal()
    openExternalRequested = QtCore.pyqtSignal(str)
    loadingChanged = QtCore.pyqtSignal(bool)

    def __init__(self, lang: str = "en", parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._lang = lang
        self._clean_mode = True
        self._provider = "google_direct"
        self._api_key = ""
        self._current_url = ""
        self._last_sv_url = ""
        self._last_pose: Optional[StreetViewState] = None
        self._backend_name = "fallback"
        self._wv2: Optional[WebView2HostWidget] = None
        self._qt_web = None

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(400)
        self._poll_timer.timeout.connect(self._poll_live_pose)

        self._clean_debounce = QtCore.QTimer(self)
        self._clean_debounce.setSingleShot(True)
        self._clean_debounce.setInterval(350)
        self._clean_debounce.timeout.connect(self._apply_clean_mode)

        self._load_timeout = QtCore.QTimer(self)
        self._load_timeout.setSingleShot(True)
        self._load_timeout.setInterval(4500)
        self._load_timeout.timeout.connect(lambda: self.loadingChanged.emit(False))

        self._init_backend()

    def backend_name(self) -> str:
        return self._backend_name

    def set_language(self, lang: str) -> None:
        self._lang = lang
        if hasattr(self, "_lbl_fb_title"):
            self._lbl_fb_title.setText(tr_text(self._lang, "fallback_title"))
            self._lbl_fb_desc.setText(tr_text(self._lang, "fallback_desc"))
            self._btn_fb_open.setText(tr_text(self._lang, "fallback_btn"))

    def set_clean_mode(self, enabled: bool) -> None:
        self._clean_mode = bool(enabled)
        self._apply_clean_mode()

    def _init_backend(self) -> None:
        is_offscreen = os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"

        # 1. Preferred on Windows: Native Edge WebView2 (works identically on Qt5 & Qt6)
        dll_path = None if is_offscreen else find_webview2_loader_dll()
        if dll_path:
            try:
                self._wv2 = WebView2HostWidget(dll_path, self)
                self._wv2.urlChanged.connect(self._handle_url_update)
                self._wv2.navigationFinished.connect(self._on_nav_finished)
                self._wv2.backendFailed.connect(self._switch_to_fallback)
                self._layout.addWidget(self._wv2)
                self._backend_name = "edge_webview2"
                return
            except Exception as exc:
                log_debug(f"WebView2 initialization fallback triggered: {exc}")
                self._wv2 = None

        # 2. Cross-platform / QGIS 4 QtWebEngineWidgets fallback
        if not is_offscreen:
            try:
                we_mod = importlib.import_module("qgis.PyQt.QtWebEngineWidgets")
                qwe_cls = getattr(we_mod, "QWebEngineView")
                self._qt_web = qwe_cls(self)
                self._qt_web.loadStarted.connect(lambda: self.loadingChanged.emit(True))
                self._qt_web.urlChanged.connect(lambda qurl: self._handle_url_update(qurl.toString()))
                self._qt_web.loadFinished.connect(lambda _ok: self._on_nav_finished(self._qt_web.url().toString()))
                self._layout.addWidget(self._qt_web)
                self._backend_name = "qt_webengine"
                return
            except Exception as exc:
                log_debug(f"QtWebEngineWidgets unavailable: {exc}")
                self._qt_web = None

        # 3. Clean Fallback Card (Headless CI / no Chromium runtime)
        self._build_fallback_card()

    def _build_fallback_card(self) -> None:
        self._backend_name = "fallback"
        card = QtWidgets.QFrame(self)
        card.setStyleSheet(
            "QFrame { background: #0f172a; color: #e2e8f0; border: none; }"
            "QLabel { color: #cbd5e1; }"
            "QPushButton { background: #0284c7; color: #ffffff; border-radius: 5px; "
            "padding: 7px 14px; font-weight: 600; border: none; }"
            "QPushButton:hover { background: #0ea5e9; }"
        )
        vbox = QtWidgets.QVBoxLayout(card)
        vbox.setContentsMargins(16, 16, 16, 16)
        vbox.setSpacing(8)
        vbox.addStretch(1)

        self._lbl_fb_title = QtWidgets.QLabel(tr_text(self._lang, "fallback_title"))
        self._lbl_fb_title.setAlignment(ALIGN_CENTER)
        self._lbl_fb_title.setWordWrap(True)
        self._lbl_fb_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #38bdf8;")
        vbox.addWidget(self._lbl_fb_title)

        self._lbl_fb_desc = QtWidgets.QLabel(tr_text(self._lang, "fallback_desc"))
        self._lbl_fb_desc.setAlignment(ALIGN_CENTER)
        self._lbl_fb_desc.setWordWrap(True)
        self._lbl_fb_desc.setStyleSheet("font-size: 11px; color: #94a3b8;")
        vbox.addWidget(self._lbl_fb_desc)

        self._lbl_fb_coords = QtWidgets.QLabel("")
        self._lbl_fb_coords.setAlignment(ALIGN_CENTER)
        self._lbl_fb_coords.setStyleSheet("font-family: Consolas, monospace; font-size: 11px; color: #facc15;")
        vbox.addWidget(self._lbl_fb_coords)

        self._btn_fb_open = QtWidgets.QPushButton(tr_text(self._lang, "fallback_btn"))
        self._btn_fb_open.setCursor(CURSOR_POINTING_HAND)
        self._btn_fb_open.clicked.connect(lambda: self.openExternalRequested.emit(self._current_url))
        vbox.addWidget(self._btn_fb_open, 0, ALIGN_CENTER)
        vbox.addStretch(1)

        self._fallback_card = card
        self._layout.addWidget(card)

    def _switch_to_fallback(self, _reason: str) -> None:
        self._load_timeout.stop()
        self.loadingChanged.emit(False)
        if self._wv2 is not None:
            self._wv2.cleanup()
            self._layout.removeWidget(self._wv2)
            self._wv2.deleteLater()
            self._wv2 = None
        if not hasattr(self, "_fallback_card"):
            self._build_fallback_card()

    def load_location(
        self,
        lat: float,
        lon: float,
        heading: float = 0.0,
        pitch: float = 0.0,
        fov: float = 85.0,
        provider: str = "google_direct",
        api_key: str = "",
        pano_id: str = "",
    ) -> str:
        """Navigate embedded viewer to the requested Street View pose."""
        self._provider = provider
        self._api_key = api_key
        url = build_street_view_url(
            lat=lat,
            lon=lon,
            heading=heading,
            pitch=pitch,
            fov=fov,
            provider=provider,
            pano_id=pano_id,
        )
        self._current_url = url
        self._last_pose = StreetViewState(
            lat=lat,
            lon=lon,
            heading=heading,
            pitch=pitch,
            fov=fov,
            pano_id=pano_id,
            url=url,
        )

        if hasattr(self, "_lbl_fb_coords"):
            self._lbl_fb_coords.setText(f"{lat:.6f}, {lon:.6f} | Hdg {heading:.0f} deg")

        if provider == "google_js" and api_key.strip():
            html = build_google_js_api_html(api_key, lat, lon, heading, pitch, fov)
            if self._wv2 is not None:
                self.loadingChanged.emit(True)
                self._load_timeout.start()
                self._wv2.set_html(html)
            elif self._qt_web is not None:
                self.loadingChanged.emit(True)
                self._load_timeout.start()
                self._qt_web.setHtml(html, QtCore.QUrl("https://localhost/"))
        else:
            if self._wv2 is not None:
                self.loadingChanged.emit(True)
                self._load_timeout.start()
                self._wv2.navigate(url)
            elif self._qt_web is not None:
                self.loadingChanged.emit(True)
                self._load_timeout.start()
                self._qt_web.setUrl(QtCore.QUrl(url))

        if (self._wv2 is not None or self._qt_web is not None) and self.isVisible():
            self._poll_timer.start()
        return url

    def current_url(self) -> str:
        return self._current_url

    def _on_nav_finished(self, url: str) -> None:
        self._load_timeout.stop()
        self.loadingChanged.emit(False)
        self._handle_url_update(url)
        if self._provider == "google_direct":
            self._apply_clean_mode()
            for delay_ms in (500, 1400, 2600, 4200):
                QtCore.QTimer.singleShot(delay_ms, self._apply_clean_mode)
            QtCore.QTimer.singleShot(3200, self._check_street_view_landed)

    def _check_street_view_landed(self) -> None:
        if self._provider != "google_direct" or not self.isVisible():
            return
        check_js = "window.location.href"

        def on_url(url_str: str):
            if url_str and "google." in url_str and "/@" in url_str:
                if parse_google_maps_url(url_str) is None and "map_action=pano" not in url_str:
                    self.streetViewUnavailable.emit()

        if self._wv2 is not None:
            self._wv2.run_script(check_js, on_url)
        elif self._qt_web is not None:
            self._qt_web.page().runJavaScript(check_js, on_url)

    def _apply_clean_mode(self) -> None:
        if self._provider != "google_direct":
            return
        js = CLEAN_PANORAMA_JS_TEMPLATE.replace(
            "__ENABLE_CLEAN__", "true" if self._clean_mode else "false"
        )
        if self._wv2 is not None:
            self._wv2.run_script(js)
        elif self._qt_web is not None:
            self._qt_web.page().runJavaScript(js)

    def _poll_live_pose(self) -> None:
        if not self.isVisible():
            return
        if self._wv2 is not None:
            self._wv2.run_script(POLL_POSE_JS, self._handle_poll_result)
        elif self._qt_web is not None:
            self._qt_web.page().runJavaScript(POLL_POSE_JS, self._handle_poll_result)

    def _handle_poll_result(self, payload: str) -> None:
        if not payload:
            return
        if payload.startswith("{"):
            try:
                data = json.loads(payload)
                pose = StreetViewState(
                    lat=float(data["lat"]),
                    lon=float(data["lon"]),
                    heading=float(data.get("heading", 0.0)),
                    pitch=float(data.get("pitch", 0.0)),
                    fov=float(data.get("fov", 85.0)),
                    pano_id=str(data.get("pano", "")),
                    url=build_street_view_url(
                        float(data["lat"]),
                        float(data["lon"]),
                        float(data.get("heading", 0.0)),
                        float(data.get("pitch", 0.0)),
                        float(data.get("fov", 85.0)),
                        pano_id=str(data.get("pano", "")),
                    ),
                )
                self._emit_if_changed(pose)
            except (ValueError, KeyError, TypeError) as exc:
                log_debug(f"Ignored invalid Street View JS pose payload: {exc}")
                return
        else:
            self._handle_url_update(payload)

    def _handle_url_update(self, url: str) -> None:
        if not url or not url.startswith("http"):
            return
        self._current_url = url
        # Anti-Place-Hijack Guard: if user accidentally clicked a POI shop marker
        # inside Street View and Google navigated to /maps/place/..., revert to Street View!
        if self._provider == "google_direct" and "/maps/place/" in url and self._last_sv_url:
            if self._wv2 is not None:
                self._wv2.navigate(self._last_sv_url)
            elif self._qt_web is not None:
                self._qt_web.setUrl(QtCore.QUrl(self._last_sv_url))
            return
        pose = parse_google_maps_url(url)
        if pose is not None:
            if ",3a," in url or "a," in url or "panoid=" in url:
                self._last_sv_url = url
            self._emit_if_changed(pose)

    def _emit_if_changed(self, pose: StreetViewState) -> None:
        if self._last_pose is not None:
            d_lat = abs(pose.lat - self._last_pose.lat)
            d_lon = abs(pose.lon - self._last_pose.lon)
            d_hdg = abs((pose.heading - self._last_pose.heading + 180.0) % 360.0 - 180.0)
            d_fov = abs(pose.fov - self._last_pose.fov)
            if (
                d_lat < 1e-6
                and d_lon < 1e-6
                and d_hdg < 0.8
                and d_fov < 1.0
                and pose.pano_id == self._last_pose.pano_id
            ):
                return
        self._last_pose = pose
        self.viewpointChanged.emit(pose)

    def setVisible(self, visible: bool) -> None:
        super().setVisible(visible)
        if self._wv2 is not None:
            self._wv2.set_webview_visible(visible)
        if visible and self._current_url and (self._wv2 is not None or self._qt_web is not None):
            self._poll_timer.start()
        else:
            self._poll_timer.stop()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._clean_mode and self._provider == "google_direct" and self._current_url:
            self._clean_debounce.start()

    def reset_view(self) -> None:
        self._poll_timer.stop()
        self._clean_debounce.stop()
        self._load_timeout.stop()
        self.loadingChanged.emit(False)
        self._current_url = ""
        self._last_sv_url = ""
        self._last_pose = None
        if self._wv2 is not None:
            self._wv2.set_html("<html><body style='background:#0f172a;margin:0;'></body></html>")
        elif self._qt_web is not None:
            self._qt_web.setHtml("<html><body style='background:#0f172a;margin:0;'></body></html>")

    def cleanup(self) -> None:
        self._poll_timer.stop()
        self._clean_debounce.stop()
        self._load_timeout.stop()
        if self._wv2 is not None:
            self._wv2.cleanup()
