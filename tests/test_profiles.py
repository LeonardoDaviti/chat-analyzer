"""Tests for multi-user profiles (M3.3).

Covers the transparent legacy migration, idempotency, profile-name sanitization,
the /profile switch/create routes (including 409-while-running), active-profile
persistence, start-fresh scoping and the hidden.json route landing under the
ACTIVE profile's Dashboard/data.

Synthetic data only — no real chats, no matplotlib. Routes are driven over a
live server on an ephemeral port, exactly as a browser would hit them, under a
temp CHAT_ANALYZER_HOME.
"""

import importlib
import json
import os
import threading
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


def _post_json(url, obj):
    req = urllib.request.Request(
        url, data=json.dumps(obj).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=10)


def _get_json(url):
    return json.loads(urllib.request.urlopen(url, timeout=5).read())


def _seed_legacy(home: Path) -> None:
    """A pre-profiles WORK_ROOT: top-level Chats/Outputs/Dashboard, no profiles/."""
    for name in ("Chats", "Outputs", "Dashboard"):
        d = home / name
        d.mkdir(parents=True)
        (d / "marker.txt").write_text(name)


# --------------------------------------------------------------------------- #
# Sanitization
# --------------------------------------------------------------------------- #
def test_sanitize_profile_name(launcher_mod):
    mod, _ = launcher_mod
    assert mod.sanitize_profile_name("Alice") == "Alice"
    assert mod.sanitize_profile_name("  my profile ") == "my profile"
    assert mod.sanitize_profile_name("weird*/name?") == "weirdname"
    assert mod.sanitize_profile_name("a" * 60) == "a" * 40      # capped at 40
    assert mod.sanitize_profile_name("") == ""                   # empty -> invalid
    assert mod.sanitize_profile_name("///") == ""
    assert mod.sanitize_profile_name(None) == ""
    # path separators cannot survive (no traversal into other profiles)
    assert "/" not in mod.sanitize_profile_name("../../etc")
    assert "\\" not in mod.sanitize_profile_name("a\\b")


# --------------------------------------------------------------------------- #
# Migration (legacy -> profiles/default)
# --------------------------------------------------------------------------- #
def test_migration_moves_legacy_into_default(launcher_mod):
    mod, home = launcher_mod
    _seed_legacy(home)
    assert not mod.profiles_dir().exists()

    moved = mod._migrate_legacy_layout()
    assert moved is True

    default = mod.profiles_dir() / "default"
    for name in ("Chats", "Outputs", "Dashboard"):
        assert (default / name / "marker.txt").read_text() == name
        assert not (home / name).exists()             # moved, not copied
    assert mod.active_profile() == "default"


def test_migration_is_idempotent(launcher_mod):
    mod, home = launcher_mod
    _seed_legacy(home)
    assert mod._migrate_legacy_layout() is True
    # Second run: profiles/ now exists -> no-op, no error, nothing new moved.
    assert mod._migrate_legacy_layout() is False
    default = mod.profiles_dir() / "default"
    assert (default / "Chats" / "marker.txt").read_text() == "Chats"


def test_migration_skipped_when_profiles_exists(launcher_mod):
    mod, home = launcher_mod
    _seed_legacy(home)
    # A pre-existing profiles/ dir means migration must NOT fire even with legacy
    # dirs present (idempotency guard).
    mod.profiles_dir().mkdir()
    assert mod._migrate_legacy_layout() is False
    assert (home / "Chats" / "marker.txt").read_text() == "Chats"  # left in place


def test_migration_ignores_backup_folders(launcher_mod):
    mod, home = launcher_mod
    _seed_legacy(home)
    backup = home / "ChatAnalyzer.backup-20250101-000000"
    backup.mkdir()
    (backup / "old.txt").write_text("keep")
    mod._migrate_legacy_layout()
    # The old M1.6 backup is never touched by migration.
    assert (backup / "old.txt").read_text() == "keep"
    assert not (mod.profiles_dir() / "default" / "ChatAnalyzer.backup-20250101-000000").exists()


def test_no_migration_when_no_legacy(launcher_mod):
    mod, home = launcher_mod
    assert mod._migrate_legacy_layout() is False
    mod.ensure_profiles()
    # Fresh home: default profile seeded, active recorded.
    assert mod.active_profile() == "default"
    assert mod.active_file().exists()


# --------------------------------------------------------------------------- #
# Active-profile persistence
# --------------------------------------------------------------------------- #
def test_active_profile_persists(launcher_mod):
    mod, home = launcher_mod
    mod.ensure_profiles()
    (mod.profiles_dir() / "beta").mkdir()
    mod._write_active_profile("beta")
    assert mod.active_profile() == "beta"
    on_disk = json.loads(mod.active_file().read_text())
    assert on_disk == {"active": "beta"}
    # Invalid / missing active.json falls back to default.
    mod.active_file().write_text("{not json")
    assert mod.active_profile() == "default"


def test_list_profiles_excludes_backups(launcher_mod):
    mod, home = launcher_mod
    mod.ensure_profiles()
    (mod.profiles_dir() / "beta").mkdir()
    (mod.profiles_dir() / "default.backup-20250101-000000").mkdir()
    names = mod.list_profiles()
    assert "default" in names and "beta" in names
    assert all(".backup-" not in n for n in names)


# --------------------------------------------------------------------------- #
# /profile routes
# --------------------------------------------------------------------------- #
def test_profile_get_lists_active_and_names(live_server):
    mod, home, base = live_server
    mod.ensure_profiles()
    info = _get_json(base + "/profile")
    assert info["active"] == "default"
    assert "default" in info["profiles"]


def test_profile_create_then_switch(live_server):
    mod, home, base = live_server
    mod.ensure_profiles()
    # Create "beta" -> becomes active, dir exists.
    body = json.loads(_post_json(base + "/profile",
                                 {"action": "create", "name": "beta"}).read())
    assert body["ok"] is True and body["active"] == "beta"
    assert (mod.profiles_dir() / "beta").is_dir()
    assert mod.active_profile() == "beta"
    # Switch back to default.
    body = json.loads(_post_json(base + "/profile",
                                 {"action": "switch", "name": "default"}).read())
    assert body["active"] == "default"
    assert mod.active_profile() == "default"


def test_profile_create_duplicate_rejected(live_server):
    mod, home, base = live_server
    mod.ensure_profiles()
    _post_json(base + "/profile", {"action": "create", "name": "beta"})
    with pytest.raises(urllib.error.HTTPError) as ei:
        _post_json(base + "/profile", {"action": "create", "name": "beta"})
    assert ei.value.code == 400


def test_profile_switch_unknown_rejected(live_server):
    mod, home, base = live_server
    mod.ensure_profiles()
    with pytest.raises(urllib.error.HTTPError) as ei:
        _post_json(base + "/profile", {"action": "switch", "name": "ghost"})
    assert ei.value.code == 400


def test_profile_invalid_name_rejected(live_server):
    mod, home, base = live_server
    mod.ensure_profiles()
    with pytest.raises(urllib.error.HTTPError) as ei:
        _post_json(base + "/profile", {"action": "create", "name": "///"})
    assert ei.value.code == 400


def test_profile_bad_action_rejected(live_server):
    mod, home, base = live_server
    with pytest.raises(urllib.error.HTTPError) as ei:
        _post_json(base + "/profile", {"action": "nuke", "name": "x"})
    assert ei.value.code == 400


def test_profile_switch_refused_while_running(live_server):
    mod, home, base = live_server
    mod.ensure_profiles()
    (mod.profiles_dir() / "beta").mkdir()
    with mod._state_lock:
        mod._running = True
    try:
        with pytest.raises(urllib.error.HTTPError) as ei:
            _post_json(base + "/profile", {"action": "switch", "name": "beta"})
        assert ei.value.code == 409
        # active unchanged
        assert mod.active_profile() == "default"
    finally:
        with mod._state_lock:
            mod._running = False


def test_profile_create_refused_while_running(live_server):
    mod, home, base = live_server
    mod.ensure_profiles()
    with mod._state_lock:
        mod._running = True
    try:
        with pytest.raises(urllib.error.HTTPError) as ei:
            _post_json(base + "/profile", {"action": "create", "name": "beta"})
        assert ei.value.code == 409
        assert not (mod.profiles_dir() / "beta").exists()
    finally:
        with mod._state_lock:
            mod._running = False


# --------------------------------------------------------------------------- #
# Isolation: hidden.json + dashboard routing follow the active profile
# --------------------------------------------------------------------------- #
def test_hidden_route_lands_in_active_profile(live_server):
    mod, home, base = live_server
    mod.ensure_profiles()
    # Create + switch to beta, then persist a hidden list.
    _post_json(base + "/profile", {"action": "create", "name": "beta"})
    req = urllib.request.Request(
        base + "/hidden", data=json.dumps(["X"]).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5)
    beta_hidden = home / "profiles" / "beta" / "Dashboard" / "data" / "hidden.json"
    assert json.loads(beta_hidden.read_text()) == ["X"]
    # default profile has no hidden.json — isolation holds.
    default_hidden = home / "profiles" / "default" / "Dashboard" / "data" / "hidden.json"
    assert not default_hidden.exists()


def test_dashboard_isolation_between_profiles(live_server):
    """A manifest in profile A must not make profile B's dashboard 'ready'."""
    mod, home, base = live_server
    mod.ensure_profiles()
    # Give default a manifest.
    md = mod.manifest_path()
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("window.DASHBOARD_MANIFEST=[]")
    assert mod.manifest_ready() is True
    # Switch to a fresh profile -> not ready (its own empty Dashboard).
    _post_json(base + "/profile", {"action": "create", "name": "beta"})
    assert mod.active_profile() == "beta"
    assert mod.manifest_ready() is False
    # / redirects to /setup for the empty profile.
    resp = urllib.request.urlopen(base + "/", timeout=5)
    assert b"Chat Analyzer" in resp.read()


def test_setup_page_shows_profile_controls(live_server):
    mod, home, base = live_server
    mod.ensure_profiles()
    html = urllib.request.urlopen(base + "/setup", timeout=5).read()
    assert b"profileSelect" in html
    assert b"New profile" in html
    assert b"active:" in html
