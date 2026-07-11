"""M4.1 — responsive dashboard + PWA surface.

Covers the launcher-served PWA endpoints (manifest / service worker / icons),
the ``--host`` opt-in binding, and that the served dashboard page carries the
guarded service-worker registration. Everything is stdlib-only and uses a live
server on an ephemeral port — no real chat data, no network.
"""

import importlib
import json
import os
import struct
import threading
import urllib.request

import pytest

from src.dashboard_template import render_index_html


def _fresh_launcher(home):
    os.environ["CHAT_ANALYZER_HOME"] = str(home)
    import launcher
    importlib.reload(launcher)
    return launcher


@pytest.fixture
def launcher_mod(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("CHAT_ANALYZER_HOME", str(home))
    mod = _fresh_launcher(home)
    yield mod, home
    os.environ.pop("CHAT_ANALYZER_HOME", None)


@pytest.fixture
def live_server(launcher_mod):
    from http.server import ThreadingHTTPServer
    mod, home = launcher_mod
    httpd = ThreadingHTTPServer((mod.HOST, 0), mod.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://{mod.HOST}:{httpd.server_address[1]}"
    yield mod, home, base
    httpd.shutdown()
    httpd.server_close()


def _seed_dashboard(mod):
    """Write a minimal servable dashboard (real template + non-empty manifest)."""
    dash = mod.dash_dir()
    (dash / "data").mkdir(parents=True, exist_ok=True)
    (dash / "index.html").write_text(render_index_html(), encoding="utf-8")
    (dash / "data" / "manifest.js").write_text(
        "window.DASHBOARD_MANIFEST=[];", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #
def test_manifest_route_shape(live_server):
    mod, home, base = live_server
    resp = urllib.request.urlopen(base + "/manifest.webmanifest", timeout=5)
    assert resp.status == 200
    assert resp.headers.get("Content-Type", "").startswith("application/manifest+json")
    man = json.loads(resp.read())
    assert man["name"] == "Chat Analyzer"
    assert man["display"] == "standalone"
    assert man["start_url"] == "/"
    # theme/background match the dark UI.
    assert man["theme_color"] == "#181B1F"
    assert man["background_color"] == "#181B1F"
    srcs = {i["src"] for i in man["icons"]}
    assert srcs == {"/app-icon-192.png", "/app-icon-512.png"}
    for i in man["icons"]:
        assert i["type"] == "image/png"


# --------------------------------------------------------------------------- #
# Service worker
# --------------------------------------------------------------------------- #
def test_sw_route_and_versioned_cache(live_server):
    mod, home, base = live_server
    resp = urllib.request.urlopen(base + "/sw.js", timeout=5)
    assert resp.status == 200
    assert "javascript" in resp.headers.get("Content-Type", "")
    body = resp.read().decode("utf-8")
    # Cache name is derived from APP_VERSION so a new release busts the cache.
    assert mod.APP_VERSION in body
    assert mod.SW_CACHE_NAME in body
    assert mod.SW_CACHE_NAME == f"chat-analyzer-v{mod.APP_VERSION}"
    # Lifecycle + strategy markers.
    assert "skipWaiting" in body
    assert "clients.claim" in body
    assert "/data/" in body  # network-first branch present


# --------------------------------------------------------------------------- #
# Icons
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path,size", [("/app-icon-192.png", 192),
                                       ("/app-icon-512.png", 512)])
def test_icon_routes_return_png(live_server, path, size):
    mod, home, base = live_server
    resp = urllib.request.urlopen(base + path, timeout=5)
    assert resp.status == 200
    assert resp.headers.get("Content-Type") == "image/png"
    data = resp.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes
    w, h = struct.unpack(">II", data[16:24])  # IHDR width/height
    assert (w, h) == (size, size)


# --------------------------------------------------------------------------- #
# --host opt-in binding
# --------------------------------------------------------------------------- #
def test_host_flag_parsed(launcher_mod):
    mod, home = launcher_mod
    args = mod._parse_args(["--host", "0.0.0.0"])
    assert args.host == "0.0.0.0"
    # default keeps loopback.
    assert mod._parse_args([]).host == "127.0.0.1"


def test_host_flag_binds_all_interfaces(launcher_mod):
    mod, home = launcher_mod
    httpd = mod._bind_server(host="0.0.0.0", port=0)
    try:
        assert httpd.server_address[0] == "0.0.0.0"
    finally:
        httpd.server_close()


# --------------------------------------------------------------------------- #
# Served page carries the guarded SW registration
# --------------------------------------------------------------------------- #
def test_served_page_has_guarded_sw_registration(live_server):
    mod, home, base = live_server
    _seed_dashboard(mod)
    html = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
    # Registration is present...
    assert "navigator.serviceWorker.register('/sw.js')" in html
    # ...but guarded to http(s) so file:// gets nothing.
    assert "location.protocol" in html
    assert "http:" in html and "https:" in html
    # Manifest link + theme-color are in the page head.
    assert '/manifest.webmanifest' in html
    assert 'name="theme-color"' in html
