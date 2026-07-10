"""Tests for the zero-dependency launcher.

Covers the pure, side-effect-free surface (routing table via a live server on an
ephemeral port, path-traversal rejection, HTML injection, progress-state
transitions, platform-detection passthrough, port fallback) using only
synthetic zips — no real chat data, no matplotlib.
"""

import importlib
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _fresh_launcher(home: Path):
    """Import launcher with WORK_ROOT pinned to a temp home (module-level paths)."""
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


def _make_instagram_zip(path: Path) -> None:
    inbox = "your_instagram_activity/messages/inbox"
    with zipfile.ZipFile(path, "w") as zf:
        for folder, parts in (("alice_1", ["Owner", "Alice"]),
                              ("bob_2", ["Owner", "Bob"])):
            payload = {
                "participants": [{"name": p} for p in parts],
                "messages": [
                    {"sender_name": parts[i % 2], "timestamp_ms": 1600000000000 + i * 600000,
                     "content": f"m{i}"} for i in range(30)
                ],
                "title": folder,
                "thread_path": f"inbox/{folder}",
            }
            zf.writestr(f"{inbox}/{folder}/message_1.json", json.dumps(payload))


# --------------------------------------------------------------------------- #
# Import purity
# --------------------------------------------------------------------------- #
def test_import_launcher_is_stdlib_only(launcher_mod):
    bad = [m for m in sys.modules if m.split(".")[0] in ("matplotlib", "numpy")]
    assert bad == [], f"launcher must not pull in {bad}"


def test_pipeline_runs_without_matplotlib(tmp_path):
    """Poison matplotlib/numpy imports, then run the full analysis in a subprocess.

    Proves --no-visualizations / skip_visualizations=True never touches
    matplotlib, so the frozen binary (which excludes it) works.
    """
    home = tmp_path / "home"
    home.mkdir()
    zp = home / "instagram-export.zip"
    _make_instagram_zip(zp)

    script = f"""
import sys
# Make any attempt to import matplotlib/numpy fail loudly.
for _name in ("matplotlib", "numpy"):
    sys.modules[_name] = None
sys.path.insert(0, {str(REPO_ROOT)!r})
from pathlib import Path
import main
main.import_zip({str(zp)!r}, Path({str(home)!r}))
res = main.run_all(base_dir={str(home)!r},
                   output_dir=str(Path({str(home)!r}) / "Outputs"),
                   generate_visualizations=False)
assert res, "no chats analysed"
print("ANALYSED", len(res))
"""
    proc = subprocess.run([sys.executable, "-c", script],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "ANALYSED 2" in proc.stdout


# --------------------------------------------------------------------------- #
# Path traversal / static resolution
# --------------------------------------------------------------------------- #
def test_safe_static_rejects_traversal(launcher_mod):
    mod, home = launcher_mod
    (mod.DASH_DIR / "data").mkdir(parents=True)
    (mod.DASH_DIR / "data" / "x.js").write_text("ok")
    assert mod.safe_static("/data/x.js") is not None
    assert mod.safe_static("/../launcher.py") is None
    assert mod.safe_static("/../../etc/passwd") is None
    assert mod.safe_static("/data/../../secret") is None
    assert mod.safe_static("/does-not-exist.js") is None


# --------------------------------------------------------------------------- #
# HTML injection
# --------------------------------------------------------------------------- #
def test_inject_add_chats_before_body(launcher_mod):
    mod, _ = launcher_mod
    out = mod.inject_add_chats(b"<html><body><h1>hi</h1></body></html>")
    assert b"Add chats" in out
    assert b'href="/setup"' in out
    # snippet sits immediately before the closing body tag
    assert out.index(b"Add chats") < out.rindex(b"</body>")


def test_inject_add_chats_no_body_tag(launcher_mod):
    mod, _ = launcher_mod
    out = mod.inject_add_chats(b"<html>no body</html>")
    assert b"Add chats" in out


# --------------------------------------------------------------------------- #
# Manifest gating
# --------------------------------------------------------------------------- #
def test_manifest_ready(launcher_mod):
    mod, home = launcher_mod
    assert mod.manifest_ready() is False
    mod.MANIFEST.parent.mkdir(parents=True)
    mod.MANIFEST.write_text("")           # empty -> not ready
    assert mod.manifest_ready() is False
    mod.MANIFEST.write_text("window.DASHBOARD_MANIFEST=[]")
    assert mod.manifest_ready() is True


# --------------------------------------------------------------------------- #
# Boundary parsing + streaming multipart
# --------------------------------------------------------------------------- #
def test_boundary_parse(launcher_mod):
    mod, _ = launcher_mod
    assert mod._boundary("multipart/form-data; boundary=abc123") == b"abc123"
    assert mod._boundary('multipart/form-data; boundary="q u o t e d"') == b"q u o t e d"
    with pytest.raises(ValueError):
        mod._boundary("multipart/form-data")


def test_stream_multipart_file(launcher_mod, tmp_path):
    mod, _ = launcher_mod
    boundary = b"BOUND"
    file_bytes = b"\x00\x01binary\r\ncontent\xff" * 100
    body = (
        b"--BOUND\r\n"
        b'Content-Disposition: form-data; name="file"; filename="my export.zip"\r\n'
        b"Content-Type: application/zip\r\n\r\n"
        + file_bytes +
        b"\r\n--BOUND--\r\n"
    )
    rfile = io.BytesIO(body)
    out = tmp_path / "out.bin"
    with open(out, "wb") as fh:
        name = mod.stream_multipart_file(rfile, len(body), boundary, fh)
    assert name == "my export.zip"
    assert out.read_bytes() == file_bytes


# --------------------------------------------------------------------------- #
# Port fallback
# --------------------------------------------------------------------------- #
def test_port_fallback_when_taken(launcher_mod):
    mod, _ = launcher_mod
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind((mod.HOST, 0))
    taken_port = blocker.getsockname()[1]
    blocker.listen(1)
    orig = mod.PORT
    try:
        mod.PORT = taken_port           # force the preferred port to be occupied
        httpd = mod._bind_server()
        try:
            assert httpd.server_address[1] != taken_port  # fell back to ephemeral
            assert httpd.server_address[1] != 0
        finally:
            httpd.server_close()
    finally:
        mod.PORT = orig
        blocker.close()


# --------------------------------------------------------------------------- #
# Platform detection passthrough (via main.import_zip through _ingest)
# --------------------------------------------------------------------------- #
def test_ingest_routes_instagram_zip(launcher_mod, tmp_path):
    mod, home = launcher_mod
    zp = tmp_path / "instagram-export.zip"
    _make_instagram_zip(zp)
    mod._ingest(zp)
    # import_zip files Instagram exports under Chats/Instagram/<stem>/
    assert (home / "Chats" / "Instagram" / "instagram-export").exists()


def test_ingest_copies_folder(launcher_mod, tmp_path):
    mod, home = launcher_mod
    src = tmp_path / "some_telegram_export"
    src.mkdir()
    (src / "result.json").write_text('{"messages":[]}')
    mod._ingest(src)
    dest = home / "Chats" / "imported_some_telegram_export"
    assert (dest / "result.json").exists()


# --------------------------------------------------------------------------- #
# Upload filename -> import folder name (Fix 3)
# --------------------------------------------------------------------------- #
def test_sanitize_upload_name(launcher_mod):
    mod, _ = launcher_mod
    assert mod._sanitize_upload_name("my export.zip") == "my export.zip"
    # path components are stripped (basename only)
    assert mod._sanitize_upload_name("../../etc/passwd") == "passwd"
    assert mod._sanitize_upload_name("C:\\Users\\me\\export.zip") == "export.zip"
    # disallowed chars removed
    assert mod._sanitize_upload_name("weird*name?.zip") == "weirdname.zip"
    # empty / all-stripped -> fallback
    assert mod._sanitize_upload_name("") == "upload.zip"
    assert mod._sanitize_upload_name("///") == "upload.zip"


def test_ingest_names_folder_after_upload(launcher_mod, tmp_path):
    """A browser upload (temp path) is filed under the ORIGINAL name, not tmp*."""
    mod, home = launcher_mod
    tmp = tmp_path / "tmp2ip9o4qu.zip"          # a mkstemp-style temp name
    _make_instagram_zip(tmp)
    mod._ingest(tmp, display_name="My Export.zip")
    dest = home / "Chats" / "Instagram"
    assert (dest / "My Export").exists()
    assert not any(p.name.startswith("tmp") for p in dest.iterdir())


# --------------------------------------------------------------------------- #
# work_root() resolution order (Fix 2)
# --------------------------------------------------------------------------- #
def test_work_root_env_override(launcher_mod, tmp_path, monkeypatch):
    mod, _ = launcher_mod
    override = tmp_path / "custom_home"
    monkeypatch.setenv("CHAT_ANALYZER_HOME", str(override))
    assert mod.work_root() == override.resolve()


def test_work_root_source_tree_uses_repo_root(launcher_mod, monkeypatch):
    mod, _ = launcher_mod
    monkeypatch.delenv("CHAT_ANALYZER_HOME", raising=False)
    monkeypatch.setattr(mod.sys, "frozen", False, raising=False)
    assert mod.work_root() == Path(mod.__file__).resolve().parent


def test_work_root_frozen_legacy_dir(launcher_mod, tmp_path, monkeypatch):
    """Frozen: existing <exe dir>/Chats keeps data next to the exe (v1 compat)."""
    mod, _ = launcher_mod
    monkeypatch.delenv("CHAT_ANALYZER_HOME", raising=False)
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    (exe_dir / "Chats").mkdir()                  # legacy data already present
    fake_home = tmp_path / "userhome"
    (fake_home / "Documents").mkdir(parents=True)
    monkeypatch.setattr(mod.sys, "frozen", True, raising=False)
    monkeypatch.setattr(mod.sys, "executable", str(exe_dir / "ChatAnalyzer"))
    monkeypatch.setattr(mod.Path, "home", staticmethod(lambda: fake_home))
    assert mod.work_root() == exe_dir.resolve()


def test_work_root_frozen_documents(launcher_mod, tmp_path, monkeypatch):
    """Frozen, no legacy dir: ~/Documents/ChatAnalyzer when Documents exists."""
    mod, _ = launcher_mod
    monkeypatch.delenv("CHAT_ANALYZER_HOME", raising=False)
    exe_dir = tmp_path / "downloads"
    exe_dir.mkdir()                              # no Chats/ here
    fake_home = tmp_path / "userhome"
    (fake_home / "Documents").mkdir(parents=True)
    monkeypatch.setattr(mod.sys, "frozen", True, raising=False)
    monkeypatch.setattr(mod.sys, "executable", str(exe_dir / "ChatAnalyzer"))
    monkeypatch.setattr(mod.Path, "home", staticmethod(lambda: fake_home))
    assert mod.work_root() == (fake_home / "Documents" / "ChatAnalyzer").resolve()


def test_work_root_frozen_no_documents(launcher_mod, tmp_path, monkeypatch):
    """Frozen, no legacy dir, no ~/Documents: ~/ChatAnalyzer."""
    mod, _ = launcher_mod
    monkeypatch.delenv("CHAT_ANALYZER_HOME", raising=False)
    exe_dir = tmp_path / "downloads"
    exe_dir.mkdir()
    fake_home = tmp_path / "userhome"
    fake_home.mkdir()                            # no Documents subfolder
    monkeypatch.setattr(mod.sys, "frozen", True, raising=False)
    monkeypatch.setattr(mod.sys, "executable", str(exe_dir / "ChatAnalyzer"))
    monkeypatch.setattr(mod.Path, "home", staticmethod(lambda: fake_home))
    assert mod.work_root() == (fake_home / "ChatAnalyzer").resolve()


# --------------------------------------------------------------------------- #
# Progress-state transitions + double-submission guard
# --------------------------------------------------------------------------- #
def test_progress_state_transitions_and_double_submit(launcher_mod, tmp_path):
    mod, home = launcher_mod
    gate = threading.Event()

    def fake_pipeline(source_path, cleanup=False, display_name=None):
        mod._set_progress(stage="analyzing", i=0, n=1)
        gate.wait(2)
        mod._set_progress(stage="done", done=True)
        with mod._state_lock:
            mod._running = False

    mod.run_pipeline = fake_pipeline
    started = mod._start_run(tmp_path / "x.zip", cleanup=False)
    assert started is True
    # a second run is rejected while the first is active
    assert mod._start_run(tmp_path / "y.zip", cleanup=False) is False
    snap = mod._snapshot_progress()
    assert snap["stage"] == "analyzing"
    gate.set()
    for _ in range(50):
        if mod._snapshot_progress()["done"]:
            break
        time.sleep(0.02)
    assert mod._snapshot_progress()["done"] is True
    # once finished, a new run is accepted again
    assert mod._start_run(tmp_path / "z.zip", cleanup=False) is True
    gate.set()


# --------------------------------------------------------------------------- #
# Live routing table on an ephemeral port
# --------------------------------------------------------------------------- #
@pytest.fixture
def live_server(launcher_mod):
    from http.server import ThreadingHTTPServer
    mod, home = launcher_mod
    httpd = ThreadingHTTPServer((mod.HOST, 0), mod.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://{mod.HOST}:{httpd.server_address[1]}"
    yield mod, home, base
    httpd.shutdown()
    httpd.server_close()


def _get(url, **kw):
    req = urllib.request.Request(url, **kw)
    return urllib.request.urlopen(req, timeout=5)


def test_routes_setup_and_progress(live_server):
    mod, home, base = live_server
    # / redirects to /setup while no manifest exists
    resp = urllib.request.urlopen(base + "/", timeout=5)
    assert b"Chat Analyzer" in resp.read()  # redirect followed to /setup
    # /setup direct
    assert urllib.request.urlopen(base + "/setup", timeout=5).status == 200
    # /progress is JSON
    prog = json.loads(urllib.request.urlopen(base + "/progress", timeout=5).read())
    assert set(prog) >= {"stage", "detail", "i", "n", "done", "error"}


def test_route_serves_dashboard_with_injection(live_server):
    mod, home, base = live_server
    (mod.DASH_DIR / "data").mkdir(parents=True)
    mod.MANIFEST.write_text("window.DASHBOARD_MANIFEST=[]")
    (mod.DASH_DIR / "index.html").write_text("<html><body>DASH</body></html>")
    body = urllib.request.urlopen(base + "/", timeout=5).read()
    assert b"DASH" in body
    assert b"Add chats" in body  # injected at serve time


def test_route_static_traversal_404(live_server):
    mod, home, base = live_server
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(base + "/data/../../nope", timeout=5)
    assert ei.value.code == 404
