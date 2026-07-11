"""Tests for the M1 launcher features: folder upload (1.2), re-analyze (1.3),
update-awareness (1.5) and start-fresh (1.6).

Synthetic data only — no real chats, no matplotlib. The pure surfaces are unit
tested; the routes are driven over a live server on an ephemeral port exactly as
a browser would hit them.
"""

import importlib
import io
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


def _fresh_launcher(home: Path):
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


def _post(url, data=None, ctype=None):
    headers = {}
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data or b"", headers=headers,
                                 method="POST")
    return urllib.request.urlopen(req, timeout=10)


def _seed_two_instagram_chats(home: Path) -> None:
    inbox = (home / "Chats" / "Instagram" / "exp" /
             "your_instagram_activity" / "messages" / "inbox")
    for folder, parts in (("alice_1", ["Owner", "Alice"]),
                          ("bob_2", ["Owner", "Bob"])):
        d = inbox / folder
        d.mkdir(parents=True, exist_ok=True)
        payload = {
            "participants": [{"name": p} for p in parts],
            "messages": [
                {"sender_name": parts[i % 2],
                 "timestamp_ms": 1600000000000 + i * 600000,
                 "content": f"m{i}"} for i in range(40)
            ],
            "title": folder,
            "thread_path": f"inbox/{folder}",
        }
        (d / "message_1.json").write_text(json.dumps(payload))


# --------------------------------------------------------------------------- #
# 1.5 — version comparison + fail-silent update check
# --------------------------------------------------------------------------- #
def test_version_tuple_parsing(launcher_mod):
    mod, _ = launcher_mod
    assert mod._version_tuple("v1.2.3") == (1, 2, 3)
    assert mod._version_tuple("1.1.0") == (1, 1, 0)
    assert mod._version_tuple("2.0") == (2, 0)
    assert mod._version_tuple("") == ()
    assert mod._version_tuple(None) == ()


def test_compare_versions(launcher_mod):
    mod, _ = launcher_mod
    assert mod._compare_versions("1.1.0", "1.2.0") is True
    assert mod._compare_versions("1.1.0", "v1.1.1") is True
    assert mod._compare_versions("1.1.0", "1.1.0") is False
    assert mod._compare_versions("1.1.0", "1.0.9") is False
    assert mod._compare_versions("1.1.0", "garbage") is False  # unparseable → no update


class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_check_for_update_newer_sets_flag(launcher_mod, monkeypatch):
    mod, _ = launcher_mod
    body = json.dumps({"tag_name": "v9.9.9"}).encode()
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: _FakeResp(body))
    mod.check_for_update(url="http://example/x", timeout=1)
    info = mod._snapshot_version()
    assert info["update_available"] is True
    assert info["latest"] == "9.9.9"
    assert info["current"] == mod.APP_VERSION


def test_check_for_update_same_version_no_flag(launcher_mod, monkeypatch):
    mod, _ = launcher_mod
    body = json.dumps({"tag_name": mod.APP_VERSION}).encode()
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: _FakeResp(body))
    mod.check_for_update(url="http://example/x", timeout=1)
    assert mod._snapshot_version()["update_available"] is False


def test_check_for_update_fails_silently(launcher_mod, monkeypatch):
    mod, _ = launcher_mod

    def boom(*a, **k):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    # Must not raise, and must not flip the flag.
    mod.check_for_update(url="http://example/x", timeout=1)
    assert mod._snapshot_version()["update_available"] is False


def test_version_route(live_server):
    mod, home, base = live_server
    info = json.loads(urllib.request.urlopen(base + "/version", timeout=5).read())
    assert set(info) == {"current", "latest", "update_available"}
    assert info["current"] == mod.APP_VERSION


def test_hidden_route_roundtrip(live_server):
    """/hidden persists a chat-id list and reads it back (M1.4)."""
    mod, home, base = live_server
    # Empty by default.
    got = json.loads(urllib.request.urlopen(base + "/hidden", timeout=5).read())
    assert got == []
    # POST a list, then GET it back and check the on-disk twin.
    resp = _post(base + "/hidden", json.dumps(["Alice", "Bob"]).encode(),
                 "application/json")
    assert json.loads(resp.read())["saved"] is True
    got = json.loads(urllib.request.urlopen(base + "/hidden", timeout=5).read())
    assert got == ["Alice", "Bob"]
    on_disk = json.loads((home / "Dashboard" / "data" / "hidden.json").read_text())
    assert on_disk == ["Alice", "Bob"]


def test_hidden_route_rejects_bad_payload(live_server):
    mod, home, base = live_server
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base + "/hidden", json.dumps({"not": "a list"}).encode(),
              "application/json")
    assert exc.value.code == 400


def test_update_banner_and_injection(launcher_mod):
    mod, _ = launcher_mod
    # No update known → no banner, but the Re-analyze control is always injected.
    out = mod.inject_add_chats(b"<html><body>x</body></html>")
    assert b"Re-analyze" in out
    assert b"Add chats" in out
    assert mod._update_banner_bytes() == b""
    # Flip the flag → banner appears with the releases link.
    with mod._version_lock:
        mod._VERSION_INFO.update(update_available=True, latest="2.0.0")
    banner = mod._update_banner_bytes()
    assert b"Update available" in banner
    assert mod.RELEASES_PAGE.encode() in banner
    assert b"Re-analyze" in mod.inject_add_chats(b"<body></body>")


def test_server_version_uses_app_version(launcher_mod):
    mod, _ = launcher_mod
    assert mod.Handler.server_version == f"ChatAnalyzer/{mod.APP_VERSION}"


# --------------------------------------------------------------------------- #
# 1.2 — folder upload
# --------------------------------------------------------------------------- #
def test_safe_tree_join_rejects_traversal(launcher_mod, tmp_path):
    mod, _ = launcher_mod
    root = tmp_path / "root"
    root.mkdir()
    assert mod._safe_tree_join(root, "a/b.json") == (root / "a" / "b.json").resolve()
    assert mod._safe_tree_join(root, "/etc/passwd") == (root / "etc" / "passwd").resolve()
    assert mod._safe_tree_join(root, "../escape") is None
    assert mod._safe_tree_join(root, "a/../../escape") is None
    assert mod._safe_tree_join(root, "") is None


def _folder_multipart(files: dict, boundary=b"BOUND"):
    """Build a multipart body: {relpath: bytes}."""
    parts = []
    for rel, data in files.items():
        parts.append(b"--" + boundary + b"\r\n")
        parts.append(('Content-Disposition: form-data; name="files"; '
                      f'filename="{rel}"\r\n').encode())
        parts.append(b"Content-Type: application/octet-stream\r\n\r\n")
        parts.append(data)
        parts.append(b"\r\n")
    parts.append(b"--" + boundary + b"--\r\n")
    return b"".join(parts)


def test_stream_multipart_folder_reconstructs_tree(launcher_mod, tmp_path):
    mod, _ = launcher_mod
    body = _folder_multipart({
        "ChatExport/result.json": b'{"messages":[]}',
        "ChatExport/media/photo.bin": b"\x00\x01\x02binary\r\ndata\xff" * 50,
        "ChatExport/nested/deep/x.txt": b"hello",
    })
    dest = tmp_path / "tree"
    dest.mkdir()
    n = mod.stream_multipart_folder(io.BytesIO(body), len(body), b"BOUND", dest)
    assert n == 3
    assert (dest / "ChatExport" / "result.json").read_bytes() == b'{"messages":[]}'
    assert (dest / "ChatExport" / "media" / "photo.bin").read_bytes() == \
        b"\x00\x01\x02binary\r\ndata\xff" * 50
    assert (dest / "ChatExport" / "nested" / "deep" / "x.txt").read_bytes() == b"hello"


def test_upload_folder_route_imports_tree(live_server):
    mod, home, base = live_server
    body = _folder_multipart({
        "ChatExport_Demo/result.json": json.dumps({
            "name": "Demo", "type": "personal_chat", "id": 1,
            "messages": [{"id": 1, "type": "message", "date_unixtime": "1600000000",
                          "from": "Owner", "from_id": "user1", "text": "hi"}],
        }).encode(),
    })
    resp = _post(base + "/upload-folder", data=body,
                 ctype="multipart/form-data; boundary=BOUND")
    assert json.loads(resp.read())["started"] is True
    # Wait for the run to finish, then the reconstructed folder must be in Chats/.
    for _ in range(100):
        if mod._snapshot_progress()["done"] or mod._snapshot_progress()["error"]:
            break
        time.sleep(0.05)
    found = list((home / "Chats").rglob("result.json"))
    assert found, "uploaded telegram folder was not routed into Chats/"


# --------------------------------------------------------------------------- #
# 1.3 — re-analyze (no import step)
# --------------------------------------------------------------------------- #
def test_reanalyze_route_requires_chats(live_server):
    mod, home, base = live_server
    with pytest.raises(urllib.error.HTTPError) as ei:
        _post(base + "/reanalyze")
    assert ei.value.code == 400


def test_reanalyze_runs_without_import_step(live_server, monkeypatch):
    mod, home, base = live_server
    _seed_two_instagram_chats(home)

    # If the ingest step ran, this would blow up the worker — proving skip.
    def _no_ingest(*a, **k):
        raise AssertionError("re-analyze must not call _ingest")

    monkeypatch.setattr(mod, "_ingest", _no_ingest)

    resp = _post(base + "/reanalyze")
    assert json.loads(resp.read())["started"] is True

    err = None
    for _ in range(200):
        snap = mod._snapshot_progress()
        if snap["done"]:
            break
        if snap["error"]:
            err = snap["error"]
            break
        time.sleep(0.05)
    assert err is None, f"re-analyze errored: {err}"
    assert mod.manifest_ready(), "re-analyze did not rebuild the dashboard manifest"


def test_reanalyze_rejected_while_running(launcher_mod):
    mod, home = launcher_mod
    with mod._state_lock:
        mod._running = True
    try:
        assert mod._start_reanalyze() is False
    finally:
        with mod._state_lock:
            mod._running = False


# --------------------------------------------------------------------------- #
# 1.6 — start fresh
# --------------------------------------------------------------------------- #
def test_start_fresh_archives_and_never_deletes(launcher_mod):
    mod, home = launcher_mod
    for name in ("Chats", "Outputs", "Dashboard"):
        d = home / name
        d.mkdir()
        (d / "marker.txt").write_text(name)

    backup, moved = mod.start_fresh()

    assert set(moved) == {"Chats", "Outputs", "Dashboard"}
    # Originals are gone from the live location...
    for name in ("Chats", "Outputs", "Dashboard"):
        assert not (home / name).exists()
        # ...but preserved (moved, not deleted) inside the backup.
        assert (backup / name / "marker.txt").read_text() == name
    assert backup.parent == home
    assert backup.name.startswith("ChatAnalyzer.backup-")


def test_start_fresh_partial_dirs(launcher_mod):
    mod, home = launcher_mod
    (home / "Chats").mkdir()
    backup, moved = mod.start_fresh()
    assert moved == ["Chats"]
    assert (backup / "Chats").exists()


def test_start_fresh_route(live_server):
    mod, home, base = live_server
    (home / "Chats").mkdir()
    (home / "Chats" / "x").write_text("y")
    resp = _post(base + "/start-fresh")
    body = json.loads(resp.read())
    assert body["ok"] is True and "Chats" in body["moved"]
    assert not (home / "Chats").exists()
    assert Path(body["backup"]).exists()


def test_start_fresh_refused_while_running(live_server):
    mod, home, base = live_server
    with mod._state_lock:
        mod._running = True
    try:
        with pytest.raises(urllib.error.HTTPError) as ei:
            _post(base + "/start-fresh")
        assert ei.value.code == 409
    finally:
        with mod._state_lock:
            mod._running = False


# --------------------------------------------------------------------------- #
# Setup page renders the new controls
# --------------------------------------------------------------------------- #
def test_setup_page_has_new_controls(live_server):
    mod, home, base = live_server
    html = urllib.request.urlopen(base + "/setup", timeout=5).read()
    assert b"webkitdirectory" in html          # folder picker (1.2)
    assert b"Re-analyze everything" in html     # re-analyze (1.3)
    assert b"Start fresh" in html               # start fresh (1.6)
    assert b"updateBanner" in html              # update banner (1.5)
    assert mod.RELEASES_PAGE.encode() in html
