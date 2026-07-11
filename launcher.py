#!/usr/bin/env python3
"""Zero-dependency launcher for the chat-analysis pipeline.

Double-clickable entry point: starts a localhost web server, opens the browser,
shows a "drop your export" setup page, runs the whole pipeline with live
progress, then the same tab becomes the dashboard.

Pure standard library only (http.server, threading, json, zipfile,
...). matplotlib/numpy are never imported — the launcher always runs the
analysis with ``skip_visualizations=True`` (the dashboard reads JSON directly).

Path resolution (source vs PyInstaller onefile)
------------------------------------------------
* BUNDLE_ROOT — read-only code/assets. When frozen this is ``sys._MEIPASS``
  (the temp dir PyInstaller unpacks into); from source it is this file's dir.
  ``main``/``src``/``build_*`` are importable from here; ``assets/echarts.min.js``
  lives here.
* WORK_ROOT — the writable working directory that holds ``Chats/``, ``Outputs/``
  and ``Dashboard/``. When frozen this is the directory *next to the executable*
  (so a user's data sits beside the app, not inside the throwaway _MEIPASS);
  from source it is the repo root. The process chdir's here at startup so the
  build scripts' cwd-relative defaults (``Outputs``, ``Dashboard``,
  ``assets/echarts.min.js``) all resolve correctly.

Privacy: only chat NAMES, counts and dates are ever logged or exposed — never
message contents.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import tempfile
import threading

from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8347
HOST = "127.0.0.1"

# Single source of truth for the app version (also referenced by the spec/CI tag).
APP_VERSION = "1.1.0"

# The ONLY network endpoint the entire product ever touches — a metadata-only,
# fail-silent GitHub release check (M1.5). No content, no telemetry.
RELEASES_API = (
    "https://api.github.com/repos/LeonardoDaviti/chat-analyzer/releases/latest"
)
RELEASES_PAGE = "https://github.com/LeonardoDaviti/chat-analyzer/releases"


# --------------------------------------------------------------------------- #
# App-root resolution (works from source and from a PyInstaller onefile build)
# --------------------------------------------------------------------------- #
def bundle_root() -> Path:
    """Read-only code + bundled assets root (``sys._MEIPASS`` when frozen)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def work_root() -> Path:
    """Writable data root — holds Chats/, Outputs/, Dashboard/.

    Resolution order:

    1. ``CHAT_ANALYZER_HOME`` env var overrides everything (tests / advanced
       users who want data outside the app dir).
    2. Source-tree runs (not frozen) use the repo root — unchanged.
    3. Frozen builds:
       a. Legacy compatibility: if ``<exe dir>/Chats`` already exists, keep
          using ``<exe dir>`` so v1 users' data isn't stranded.
       b. Otherwise a stable, user-visible folder: ``~/Documents/ChatAnalyzer``
          when ``~/Documents`` exists, else ``~/ChatAnalyzer``. This avoids
          dumping Chats/Outputs/Dashboard into wherever the exe was launched
          from (e.g. Downloads).
    """
    env = os.environ.get("CHAT_ANALYZER_HOME")
    if env:
        return Path(env).expanduser().resolve()
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent

    exe_dir = Path(sys.executable).resolve().parent
    if (exe_dir / "Chats").exists():
        return exe_dir
    documents = Path.home() / "Documents"
    base = documents if documents.exists() else Path.home()
    return (base / "ChatAnalyzer").resolve()


BUNDLE_ROOT = bundle_root()
WORK_ROOT = work_root()

# --------------------------------------------------------------------------- #
# Multi-user profiles (M3.3)
# --------------------------------------------------------------------------- #
# Each profile is a self-contained data root: WORK_ROOT/profiles/<name>/ holding
# its own Chats/, Outputs/ and Dashboard/. The active profile is recorded in
# WORK_ROOT/profiles/active.json. CHAT_ANALYZER_HOME still relocates WORK_ROOT;
# profiles live *under* it. All serving/import/reanalyze/start-fresh operate on
# the ACTIVE profile's dirs — the accessors below are the single source of truth
# (constants would go stale the moment a user switches profiles at runtime).
DEFAULT_PROFILE = "default"
_PROFILE_DIRS = ("Chats", "Outputs", "Dashboard")


def profiles_dir() -> Path:
    return WORK_ROOT / "profiles"


def active_file() -> Path:
    return profiles_dir() / "active.json"


def sanitize_profile_name(name: str) -> str:
    """Reduce a user-supplied profile name to the allowed ``[A-Za-z0-9._ -]`` set.

    Mirrors ``_sanitize_upload_name``: keeps only alphanumerics plus ``._ -``,
    strips surrounding whitespace and caps the length at 40 chars. Returns ``""``
    for an unusable name (caller rejects it) — never invents a fallback the way
    upload naming does, because an empty profile name must be an error.
    """
    cleaned = "".join(c for c in (name or "") if c.isalnum() or c in "._ -")
    return cleaned.strip()[:40].strip()


def _read_active_profile() -> str:
    """Return the persisted active-profile name (``default`` when unset/invalid)."""
    try:
        data = json.loads(active_file().read_text(encoding="utf-8"))
        name = sanitize_profile_name(str(data.get("active", "")))
        if name:
            return name
    except (OSError, ValueError):
        pass
    return DEFAULT_PROFILE


def _write_active_profile(name: str) -> None:
    profiles_dir().mkdir(parents=True, exist_ok=True)
    active_file().write_text(
        json.dumps({"active": name}), encoding="utf-8")


def active_profile() -> str:
    return _read_active_profile()


def active_root() -> Path:
    """The writable data root of the ACTIVE profile (holds Chats/Outputs/Dashboard)."""
    return profiles_dir() / active_profile()


def list_profiles() -> list[str]:
    """Existing profile names (dirs under profiles/), excluding start-fresh backups.

    Backups are stored as ``profiles/<name>.backup-<ts>`` (see ``start_fresh``);
    those are not selectable profiles, so they're filtered out here.
    """
    pdir = profiles_dir()
    names = []
    if pdir.is_dir():
        for p in pdir.iterdir():
            if p.is_dir() and ".backup-" not in p.name:
                names.append(p.name)
    if DEFAULT_PROFILE not in names:
        names.append(DEFAULT_PROFILE)
    return sorted(names)


def dash_dir() -> Path:
    return active_root() / "Dashboard"


def manifest_path() -> Path:
    return dash_dir() / "data" / "manifest.js"


def _migrate_legacy_layout() -> bool:
    """One-time transparent migration of a pre-profiles WORK_ROOT.

    Condition (ALL must hold): ``profiles/`` does not yet exist AND at least one
    legacy top-level ``Chats``/``Outputs``/``Dashboard`` dir is present. When it
    fires, those dirs are *moved* (never copied) into ``profiles/default/`` and
    ``default`` is recorded as active. Idempotent: once ``profiles/`` exists this
    is a no-op. Only the three named dirs are touched, so ``ChatAnalyzer.backup-*``
    (and anything else) is left untouched. Returns True iff a move happened.
    """
    if profiles_dir().exists():
        return False
    legacy = [n for n in _PROFILE_DIRS if (WORK_ROOT / n).is_dir()]
    if not legacy:
        return False
    default_dir = profiles_dir() / DEFAULT_PROFILE
    default_dir.mkdir(parents=True, exist_ok=True)
    for name in legacy:
        shutil.move(str(WORK_ROOT / name), str(default_dir / name))
    _write_active_profile(DEFAULT_PROFILE)
    print(f"Migrated existing data into profiles/{DEFAULT_PROFILE}/ "
          f"({', '.join(legacy)}).")
    return True


def ensure_profiles() -> None:
    """Make the profiles layout usable: migrate legacy data, seed active + dirs.

    Safe to call repeatedly; the migration step is guarded to run at most once.
    NOT called at import time — only from real startup (``_ensure_runtime_layout``)
    and tests — so merely importing the module never moves a source tree's data.
    """
    _migrate_legacy_layout()
    profiles_dir().mkdir(parents=True, exist_ok=True)
    if not active_file().exists():
        _write_active_profile(DEFAULT_PROFILE)
    active_root().mkdir(parents=True, exist_ok=True)


def _ensure_runtime_layout() -> None:
    """Make the working dir usable: on-path imports, cwd, vendored ECharts.

    In a frozen build the code modules live inside the bundle (already on
    ``sys.path``), but ``assets/echarts.min.js`` is read by the dashboard
    exporter via a *cwd-relative* path, so we mirror it into WORK_ROOT/assets.
    """
    if str(BUNDLE_ROOT) not in sys.path:
        sys.path.insert(0, str(BUNDLE_ROOT))
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    ensure_profiles()  # migrate legacy layout + seed the active profile (M3.3)
    os.chdir(WORK_ROOT)
    asset = WORK_ROOT / "assets" / "echarts.min.js"
    if not asset.exists():
        src = BUNDLE_ROOT / "assets" / "echarts.min.js"
        if src.exists():
            asset.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, asset)


# --------------------------------------------------------------------------- #
# Global progress state (single run at a time)
# --------------------------------------------------------------------------- #
_state_lock = threading.Lock()
PROGRESS = {
    "stage": "idle",   # idle | importing | analyzing | dashboard | connected | done
    "detail": "",       # human label (chat NAME only, never contents)
    "i": 0,             # chats completed
    "n": 0,             # chats total
    "done": False,
    "error": None,
}
_running = False  # True while a pipeline worker is active


def _set_progress(**kw) -> None:
    with _state_lock:
        PROGRESS.update(kw)


def _snapshot_progress() -> dict:
    with _state_lock:
        return dict(PROGRESS)


# --------------------------------------------------------------------------- #
# Update-awareness (M1.5) — the ONLY network call in the whole product.
# Metadata only (a version tag), 3s timeout, ANY failure = silently no banner.
# --------------------------------------------------------------------------- #
_version_lock = threading.Lock()
_VERSION_INFO = {"current": APP_VERSION, "latest": None, "update_available": False}


def _version_tuple(tag) -> tuple:
    """Parse a ``v1.2.3``-style tag into a comparable int tuple (best effort)."""
    parts = []
    for chunk in str(tag or "").strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _compare_versions(current: str, latest: str) -> bool:
    """True iff ``latest`` is a strictly newer version than ``current``."""
    lt = _version_tuple(latest)
    if not lt:
        return False
    return lt > _version_tuple(current)


def check_for_update(url: str = RELEASES_API, timeout: float = 3.0) -> None:
    """Query GitHub's latest release once and record whether we're behind.

    Stdlib urllib only. ANY failure (offline, rate-limit, bad JSON, missing tag)
    leaves ``_VERSION_INFO`` untouched so no banner is ever shown — the check is
    strictly best-effort and never raises.
    """
    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"ChatAnalyzer/{APP_VERSION}",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        latest = data.get("tag_name") or data.get("name")
        if not latest:
            return
        available = _compare_versions(APP_VERSION, latest)
        with _version_lock:
            _VERSION_INFO.update(
                current=APP_VERSION,
                latest=str(latest).strip().lstrip("vV"),
                update_available=available,
            )
    except Exception:
        return  # offline / rate-limited / unparseable → silent, no banner


def _snapshot_version() -> dict:
    with _version_lock:
        return dict(_VERSION_INFO)


def _start_update_check() -> None:
    """Kick the version check off in a daemon thread so startup never blocks."""
    threading.Thread(target=check_for_update, daemon=True).start()


# --------------------------------------------------------------------------- #
# Pipeline worker
# --------------------------------------------------------------------------- #
def _sanitize_upload_name(name: str) -> str:
    """Reduce a browser-supplied filename to a safe basename.

    Keeps only ``[A-Za-z0-9._ -]`` (strips path separators and anything else),
    takes the basename so no directory components survive, and falls back to
    ``upload.zip`` when nothing usable remains. Used to name the imported chat
    folder after the uploaded file instead of a ``mkstemp`` temp name.
    """
    base = os.path.basename((name or "").replace("\\", "/"))
    cleaned = "".join(c for c in base if c.isalnum() or c in "._ -").strip()
    return cleaned or "upload.zip"


def _ingest(source_path: Path, display_name: str | None = None) -> None:
    """Bring a user-supplied export into ``Chats/``.

    A ``.zip`` is routed through ``main.import_zip`` (platform-detected,
    zip-slip safe). ``display_name`` — when set (browser uploads) — names the
    extracted folder after the original file instead of the temp path's stem.
    A directory is copied under ``Chats/`` so the recursive discovery in
    ``main`` picks up its inbox / result.json.
    """
    import main  # lazy — keeps `import launcher` matplotlib/numpy free

    if source_path.is_file() and source_path.suffix.lower() == ".zip":
        main.import_zip(str(source_path), active_root(), dest_name=display_name)
        return
    if source_path.is_dir():
        dest = active_root() / "Chats" / f"imported_{source_path.name}"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source_path, dest)
        return
    raise ValueError(f"Not a zip or a folder: {source_path}")


def run_pipeline(source_path: Path | None, cleanup: bool = False,
                 display_name: str | None = None, import_step: bool = True) -> None:
    """Full pipeline in a worker thread: [import →] analyze → dashboard → connected.

    ``display_name`` is the sanitized original upload filename (or None for
    path/folder imports); it names the extracted chat folder. When
    ``import_step`` is False (the Re-analyze action) the ingest step is skipped
    entirely and the run goes straight to analysis over the existing ``Chats/``.
    """
    global _running
    # Snapshot the active profile's dirs for the whole run. Profile switching is
    # blocked while a run is active (409), so these can't shift mid-pipeline.
    root = active_root()
    dash = root / "Dashboard"
    try:
        if import_step:
            _set_progress(stage="importing",
                          detail=display_name or (source_path.name if source_path else ""),
                          i=0, n=0, done=False, error=None)
            _ingest(source_path, display_name=display_name)
        else:
            _set_progress(stage="analyzing", detail="", i=0, n=0,
                          done=False, error=None)

        import main
        _set_progress(stage="analyzing", detail="")

        def _cb(i: int, n: int, chat_name: str) -> None:
            # chat NAME only — never message contents
            _set_progress(stage="analyzing", detail=chat_name, i=i, n=n)

        main.run_all(
            base_dir=root,
            output_dir=str(root / "Outputs"),
            # Visualizations and session markdown are skipped by default —
            # the dashboard reads JSON directly. Use --visuals / --sessions
            # to opt-in when running from the CLI.
            progress_cb=_cb,
        )

        _set_progress(stage="dashboard", detail="building dashboard")
        from src.dashboard_export import run_export
        run_export(
            output_dir=str(root / "Outputs"),
            dash_dir=str(dash),
        )

        _set_progress(stage="connected", detail="building connected profile")
        try:
            import build_connected
            build_connected.main([
                "--chats-dir", str(root / "Chats"),
                "--dash-dir", str(dash),
            ])
        except SystemExit:
            pass
        except Exception as exc:  # connected is Instagram-only / best-effort
            print(f"connected profile skipped: {exc}")

        _set_progress(stage="insights", detail="finding what stands out")
        try:
            import build_insights
            build_insights.main(["--dash-dir", str(dash)])
        except SystemExit:
            pass
        except Exception as exc:  # findings are best-effort, never fatal
            print(f"insights skipped: {exc}")

        _set_progress(stage="done", detail="", done=True)
    except Exception as exc:  # surface to the setup page
        import traceback
        traceback.print_exc()
        _set_progress(stage="error", detail="", error=str(exc), done=False)
    finally:
        if cleanup:
            try:
                source_path.unlink()
            except OSError:
                pass
        with _state_lock:
            _running = False


def _start_run(source_path: Path, cleanup: bool,
               display_name: str | None = None) -> bool:
    """Begin a run if none is active. Returns False if one is already running."""
    global _running
    with _state_lock:
        if _running:
            return False
        _running = True
    t = threading.Thread(target=run_pipeline,
                         args=(source_path, cleanup, display_name), daemon=True)
    t.start()
    return True


def _start_reanalyze() -> bool:
    """Re-run analysis over the existing ``Chats/`` with no import step (M1.3)."""
    global _running
    with _state_lock:
        if _running:
            return False
        _running = True
    t = threading.Thread(
        target=run_pipeline,
        kwargs={"source_path": None, "import_step": False},
        daemon=True,
    )
    t.start()
    return True


# --------------------------------------------------------------------------- #
# Start fresh (M1.6) — archive current data, never delete
# --------------------------------------------------------------------------- #
def start_fresh() -> tuple[Path, list[str]]:
    """Archive the ACTIVE profile's ``Chats``/``Outputs``/``Dashboard`` (M3.3).

    Creates ``profiles/<active>.backup-YYYYMMDD-HHMMSS`` and *moves* (never
    deletes) whichever of the three data dirs exist into it, returning
    ``(backup_dir, moved_names)``. Only the active profile is touched — other
    profiles and their data are left alone. The setup page then reloads to its
    empty state because the active profile's manifest is gone.
    """
    active = active_profile()
    root = active_root()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = profiles_dir() / f"{active}.backup-{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for name in _PROFILE_DIRS:
        src = root / name
        if src.exists():
            shutil.move(str(src), str(backup / name))
            moved.append(name)
    return backup, moved


# --------------------------------------------------------------------------- #
# Multipart streaming (exports can be 1GB+ — never buffer the whole body)
# --------------------------------------------------------------------------- #
def _boundary(content_type: str) -> bytes:
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("boundary="):
            b = part[len("boundary="):].strip().strip('"')
            return b.encode("latin-1")
    raise ValueError("multipart body without boundary")


def stream_multipart_file(rfile, length: int, boundary: bytes, dest) -> str:
    """Stream the first file part of a multipart body to ``dest`` (a file object).

    Returns the original filename. Reads in bounded chunks and scans for the
    closing boundary so a multi-hundred-MB upload never lands in memory.
    """
    delim = b"--" + boundary
    end_marker = b"\r\n" + delim
    remaining = length
    buf = b""

    # 1. Read up to the end of the first part's header block.
    while b"\r\n\r\n" not in buf:
        chunk = rfile.read(min(4096, remaining))
        if not chunk:
            break
        remaining -= len(chunk)
        buf += chunk
    header_block, _, body = buf.partition(b"\r\n\r\n")

    filename = "upload.zip"
    for line in header_block.split(b"\r\n"):
        low = line.lower()
        if low.startswith(b"content-disposition") and b"filename=" in low:
            try:
                filename = line.split(b"filename=", 1)[1].split(b";")[0]
                filename = filename.strip().strip(b'"').decode("utf-8", "replace")
            except Exception:
                pass

    # 2. Stream the body until the closing boundary.
    data = body
    tail = len(end_marker)
    while True:
        idx = data.find(end_marker)
        if idx != -1:
            dest.write(data[:idx])
            return filename or "upload.zip"
        if len(data) > tail:
            dest.write(data[:-tail])
            data = data[-tail:]
        if remaining <= 0:
            dest.write(data)
            return filename or "upload.zip"
        chunk = rfile.read(min(1 << 16, remaining))
        if not chunk:
            dest.write(data)
            return filename or "upload.zip"
        remaining -= len(chunk)
        data += chunk


def _safe_tree_join(root: Path, rel: str) -> Path | None:
    """Join a browser-supplied relative path under ``root``, traversal-safe.

    Strips drive letters / leading slashes and rejects any ``..`` component so a
    folder upload can never escape the reconstruction dir (analogous to the
    zip-slip guard in ``main.import_zip``). Returns None for an unusable path.
    """
    rel = (rel or "").replace("\\", "/").lstrip("/")
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    root_res = root.resolve()
    target = (root / Path(*parts)).resolve()
    if target != root_res and root_res not in target.parents:
        return None
    return target


def stream_multipart_folder(rfile, length: int, boundary: bytes,
                            dest_root: Path) -> int:
    """Stream every file part of a multipart body into a tree under ``dest_root``.

    Each part's ``filename`` carries the file's path relative to the dropped
    folder (the client sends ``webkitRelativePath``); the tree is reconstructed
    on disk so the existing directory-import path in ``_ingest`` can pick it up.
    Bodies are streamed in bounded chunks so a multi-hundred-MB folder never
    lands in memory. Returns the number of files written.
    """
    delim = b"--" + boundary
    remaining = length

    def _read(n: int = 1 << 16) -> bytes:
        nonlocal remaining
        if remaining <= 0:
            return b""
        chunk = rfile.read(min(n, remaining))
        remaining -= len(chunk)
        return chunk

    buf = b""
    # Skip the preamble up to and including the first boundary.
    while delim not in buf:
        chunk = _read()
        if not chunk:
            return 0
        buf += chunk
    buf = buf.split(delim, 1)[1]

    written = 0
    needle = b"\r\n" + delim
    while True:
        while len(buf) < 2:
            chunk = _read()
            if not chunk:
                return written
            buf += chunk
        if buf[:2] == b"--":            # closing boundary → done
            return written
        if buf[:2] == b"\r\n":          # CRLF before this part's headers
            buf = buf[2:]

        while b"\r\n\r\n" not in buf:
            chunk = _read()
            if not chunk:
                return written
            buf += chunk
        header_block, _, buf = buf.partition(b"\r\n\r\n")

        filename = ""
        for line in header_block.split(b"\r\n"):
            low = line.lower()
            if low.startswith(b"content-disposition") and b"filename=" in low:
                try:
                    filename = line.split(b"filename=", 1)[1].split(b";")[0]
                    filename = filename.strip().strip(b'"').decode("utf-8", "replace")
                except Exception:
                    filename = ""

        dest = _safe_tree_join(dest_root, filename) if filename else None
        fh = None
        if dest is not None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            fh = open(dest, "wb")
        try:
            while True:
                idx = buf.find(needle)
                if idx != -1:
                    if fh:
                        fh.write(buf[:idx])
                    buf = buf[idx + len(needle):]   # advance past CRLF + boundary
                    break
                keep = len(needle)
                if len(buf) > keep:
                    if fh:
                        fh.write(buf[:-keep])
                    buf = buf[-keep:]
                chunk = _read()
                if not chunk:
                    if fh:
                        fh.write(buf)
                    buf = b""
                    break
                buf += chunk
        finally:
            if fh:
                fh.close()
        if dest is not None:
            written += 1
    return written


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
SETUP_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chat Analyzer — Setup</title>
<style>
:root{--bg:#181B1F;--panel:#22262B;--border:#2c3137;--text:#D8D9DA;
  --muted:#8e9297;--a:#4DB6AC;--bad:#E02F44;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  line-height:1.5;display:flex;min-height:100vh;align-items:center;justify-content:center}
.card{max-width:560px;width:92%;background:var(--panel);border:1px solid var(--border);
  border-radius:12px;padding:28px 30px}
h1{font-size:20px;margin:0 0 4px}.muted{color:var(--muted);font-size:13px}
#drop{margin:22px 0;border:2px dashed var(--border);border-radius:10px;
  padding:38px 20px;text-align:center;cursor:pointer;transition:.15s}
#drop.over{border-color:var(--a);background:rgba(77,182,172,.08)}
#drop b{color:var(--a)}
input[type=text]{width:100%;padding:10px 12px;background:#1a1d21;color:var(--text);
  border:1px solid var(--border);border-radius:8px;font-size:13px}
button{margin-top:10px;padding:9px 16px;background:var(--a);color:#08302c;border:0;
  border-radius:8px;font-weight:600;cursor:pointer}
button:disabled{opacity:.5;cursor:default}
.sep{margin:22px 0 8px;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.5px}
#bar{height:10px;background:#1a1d21;border-radius:6px;overflow:hidden;margin-top:8px;display:none}
#bar>div{height:100%;width:0;background:var(--a);transition:width .3s}
#status{margin-top:10px;font-size:13px;min-height:18px}
.err{color:var(--bad)}
button.ghost{background:transparent;color:var(--muted);border:1px solid var(--border)}
.row{display:flex;gap:10px;flex-wrap:wrap}
.linklike{color:var(--a);cursor:pointer;text-decoration:underline;font-size:13px}
#updateBanner{display:none;margin:0 0 16px;padding:10px 14px;border-radius:8px;
  background:rgba(77,182,172,.12);border:1px solid var(--a);color:var(--text);
  font-size:13px}
#updateBanner a{color:var(--a);font-weight:600}
#updateBanner .x{float:right;cursor:pointer;color:var(--muted);
  margin-left:12px;font-weight:700}
</style></head>
<body><div class="card">
<div id="updateBanner"><span class="x" onclick="this.parentNode.style.display='none'">×</span>
Update available — <a id="updateLink" href="__RELEASES_PAGE__" target="_blank" rel="noopener">download here</a></div>
<h1>Chat Analyzer</h1>
<div class="muted">Everything runs on your computer. Nothing is uploaded anywhere.</div>
<div class="muted" style="margin-top:8px">Your dashboard and imported chats are stored in:<br>
<code style="color:#4DB6AC;word-break:break-all">__WORK_ROOT__</code></div>

<div class="sep">Profile — active: <b id="activeName">__ACTIVE_PROFILE__</b></div>
<div class="row">
<select id="profileSelect" style="flex:1;min-width:160px;padding:9px 10px;background:#1a1d21;color:var(--text);border:1px solid var(--border);border-radius:8px;font-size:13px"></select>
<button id="switchBtn">Switch</button>
</div>
<div class="row" style="margin-top:8px">
<input id="newProfile" type="text" placeholder="new profile name" style="flex:1;min-width:160px">
<button id="createBtn" class="ghost">New profile</button>
</div>

<div id="drop">Drop your Instagram or Telegram export <b>.zip</b> or a <b>folder</b> here<br>
<span class="muted">or click to choose a file, <span id="folderPick" class="linklike">choose a folder</span>, or paste a path below</span>
<input id="file" type="file" accept=".zip" hidden>
<input id="folder" type="file" webkitdirectory directory multiple hidden></div>

<div class="sep">Or paste a path to a zip / folder on this computer</div>
<input id="path" type="text" placeholder="/home/you/Downloads/export.zip or /path/to/chat-folder">
<button id="pathbtn">Analyze this path</button>

<div class="sep">Already imported chats? Manage your data</div>
<div class="row">
<button id="reanalyzeBtn">↻ Re-analyze everything</button>
<button id="freshBtn" class="ghost">Start fresh (archive current data)</button>
</div>

<div id="bar"><div></div></div>
<div id="status"></div>
</div>
<script>
const drop=document.getElementById('drop'),file=document.getElementById('file'),
  folder=document.getElementById('folder'),folderPick=document.getElementById('folderPick'),
  bar=document.getElementById('bar'),barFill=bar.firstElementChild,
  status=document.getElementById('status'),pathBtn=document.getElementById('pathbtn'),
  pathInput=document.getElementById('path'),reBtn=document.getElementById('reanalyzeBtn'),
  freshBtn=document.getElementById('freshBtn');
let polling=false;
function busy(){status.classList.remove('err');bar.style.display='block';}
function fail(m){status.classList.add('err');status.textContent=m;}
drop.onclick=(e)=>{if(e.target!==folderPick)file.click();};
folderPick.onclick=(e)=>{e.stopPropagation();folder.click();};
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('over');}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('over');}));
drop.addEventListener('drop',ev=>{
  const items=ev.dataTransfer.items;
  // Prefer the entry API: if a directory was dropped, walk it client-side.
  if(items&&items.length&&typeof items[0].webkitGetAsEntry==='function'){
    const entries=[];for(let i=0;i<items.length;i++){const en=items[i].webkitGetAsEntry&&items[i].webkitGetAsEntry();if(en)entries.push(en);}
    if(entries.some(en=>en&&en.isDirectory)){uploadEntries(entries);return;}
  }
  if(ev.dataTransfer.files.length)upload(ev.dataTransfer.files[0]);
});
file.onchange=()=>{if(file.files.length)upload(file.files[0]);};
folder.onchange=()=>{if(folder.files.length)uploadFolderFiles(folder.files);};
pathBtn.onclick=()=>{const p=pathInput.value.trim();if(!p)return;busy();status.textContent='Importing...';
  fetch('/import-path',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:p})}).then(r=>r.json()).then(handleStart).catch(e=>fail(''+e));};
reBtn.onclick=()=>{busy();status.textContent='Re-analyzing everything...';
  fetch('/reanalyze',{method:'POST'}).then(r=>r.json()).then(handleStart).catch(e=>fail(''+e));};
freshBtn.onclick=()=>{
  if(!confirm('Archive your current Chats, Outputs and Dashboard into a backup folder and start over? Nothing is deleted.'))return;
  fetch('/start-fresh',{method:'POST'}).then(r=>r.json()).then(j=>{
    if(j.error){fail(j.error);return;}if(j.busy){fail('A run is already in progress.');return;}
    location.href='/setup';
  }).catch(e=>fail(''+e));};
function upload(f){busy();status.textContent='Uploading '+f.name+'...';
  const fd=new FormData();fd.append('file',f,f.name);
  fetch('/upload',{method:'POST',body:fd}).then(r=>r.json()).then(handleStart).catch(e=>fail(''+e));}
// ---- folder upload: gather files with relative paths, POST as one batch ---- //
function uploadFolderFiles(files){
  busy();status.textContent='Uploading folder ('+files.length+' files)...';
  const fd=new FormData();
  for(let i=0;i<files.length;i++){const f=files[i];fd.append('files',f,f.webkitRelativePath||f.name);}
  fetch('/upload-folder',{method:'POST',body:fd}).then(r=>r.json()).then(handleStart).catch(e=>fail(''+e));
}
function readAllEntries(reader){return new Promise((res,rej)=>{const all=[];
  (function next(){reader.readEntries(function(batch){if(!batch.length){res(all);}else{all.push.apply(all,batch);next();}},rej);})();});}
function gather(entry,prefix,out){return new Promise((res,rej)=>{
  if(entry.isFile){entry.file(function(f){out.push({file:f,path:prefix+f.name});res();},rej);}
  else if(entry.isDirectory){const r=entry.createReader();
    readAllEntries(r).then(function(entries){
      let p=Promise.resolve();entries.forEach(function(e){p=p.then(()=>gather(e,prefix+entry.name+'/',out));});
      p.then(res,rej);},rej);}
  else{res();}});}
function uploadEntries(entries){busy();status.textContent='Reading folder...';
  const out=[];let p=Promise.resolve();
  entries.forEach(function(en){p=p.then(()=>gather(en,'',out));});
  p.then(function(){
    if(!out.length){fail('No files found in that folder.');return;}
    status.textContent='Uploading folder ('+out.length+' files)...';
    const fd=new FormData();out.forEach(function(o){fd.append('files',o.file,o.path);});
    return fetch('/upload-folder',{method:'POST',body:fd}).then(r=>r.json()).then(handleStart);
  }).catch(e=>fail(''+e));}
// ---- profiles (M3.3): list, switch, create ---- //
const profileSelect=document.getElementById('profileSelect'),
  switchBtn=document.getElementById('switchBtn'),createBtn=document.getElementById('createBtn'),
  newProfile=document.getElementById('newProfile'),activeName=document.getElementById('activeName');
function loadProfiles(){fetch('/profile').then(r=>r.json()).then(j=>{
  activeName.textContent=j.active;profileSelect.innerHTML='';
  (j.profiles||[]).forEach(function(n){const o=document.createElement('option');
    o.value=n;o.textContent=n;if(n===j.active)o.selected=true;profileSelect.appendChild(o);});
}).catch(()=>{});}
function postProfile(action,name){return fetch('/profile',{method:'POST',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({action:action,name:name})}).then(r=>r.json().then(j=>({s:r.status,j:j})));}
switchBtn.onclick=()=>{const n=profileSelect.value;if(!n)return;
  postProfile('switch',n).then(o=>{if(o.s===409){fail('A run is in progress — cannot switch.');return;}
    if(o.j.error){fail(o.j.error);return;}location.href='/';}).catch(e=>fail(''+e));};
createBtn.onclick=()=>{const n=newProfile.value.trim();if(!n){fail('Enter a profile name.');return;}
  postProfile('create',n).then(o=>{if(o.s===409){fail('A run is in progress — cannot create.');return;}
    if(o.j.error){fail(o.j.error);return;}location.href='/';}).catch(e=>fail(''+e));};
loadProfiles();
// ---- update banner (fail-silent; server does the actual check) ---- //
fetch('/version').then(r=>r.json()).then(v=>{if(v&&v.update_available){
  const b=document.getElementById('updateBanner');if(b){b.style.display='block';
    if(v.latest)document.getElementById('updateLink').textContent='download '+v.latest;}}}).catch(()=>{});
function handleStart(j){if(j.error){fail(j.error);return;}if(j.busy){fail('A run is already in progress.');return;}poll();}
function poll(){if(polling)return;polling=true;const iv=setInterval(()=>{
  fetch('/progress').then(r=>r.json()).then(p=>{
    if(p.error){clearInterval(iv);polling=false;fail('Error: '+p.error);return;}
    if(p.done){clearInterval(iv);barFill.style.width='100%';status.textContent='Done! Opening dashboard...';
      setTimeout(()=>location.href='/',600);return;}
    let pct=5;let label=p.stage;
    if(p.stage==='analyzing'&&p.n){pct=10+80*(p.i/p.n);label='Analyzing '+(p.detail||'')+' ('+p.i+'/'+p.n+')';}
    else if(p.stage==='dashboard'){pct=92;label='Building dashboard';}
    else if(p.stage==='connected'){pct=96;label='Building your connected profile';}
    else if(p.stage==='insights'){pct=98;label='Finding what stands out';}
    else if(p.stage==='importing'){pct=6;label='Importing '+(p.detail||'');}
    barFill.style.width=pct+'%';status.textContent=label;
  }).catch(()=>{});},700);}
</script></body></html>"""


# Fixed floating controls injected into the dashboard: "Add chats" (goes to the
# setup page) plus a "Re-analyze" action right next to it (M1.3). The re-analyze
# link POSTs /reanalyze then hands off to /setup to watch progress.
_ADD_CHATS_SNIPPET = (
    b'<div style="position:fixed;right:16px;bottom:16px;z-index:9999;display:flex;'
    b'gap:8px;font:600 13px -apple-system,Segoe UI,Roboto,sans-serif">'
    b'<a href="/setup" style="background:#4DB6AC;color:#08302c;padding:9px 14px;'
    b'border-radius:20px;text-decoration:none;box-shadow:0 2px 8px rgba(0,0,0,.4)">'
    b'\xe2\x9e\x95 Add chats</a>'
    b'<a href="#" onclick="fetch(\'/reanalyze\',{method:\'POST\'})'
    b'.then(function(r){return r.json()}).then(function(j){'
    b'if(j&&j.busy){alert(\'A run is already in progress.\');return}'
    b'location.href=\'/setup\'}).catch(function(){location.href=\'/setup\'});return false;" '
    b'style="background:#22262B;color:#4DB6AC;border:1px solid #4DB6AC;'
    b'padding:9px 14px;border-radius:20px;text-decoration:none;'
    b'box-shadow:0 2px 8px rgba(0,0,0,.4)">\xe2\x86\xbb Re-analyze</a></div>'
)


def _update_banner_bytes() -> bytes:
    """A dismissible 'update available' banner, or b'' when up to date/unknown.

    Rendered from the last fail-silent version check (M1.5); empty whenever no
    newer release is known so an offline/failed check shows nothing.
    """
    info = _snapshot_version()
    if not info.get("update_available"):
        return b""
    latest = info.get("latest") or ""
    label = f"download {latest}" if latest else "download here"
    html = (
        '<div id="ca-update" style="position:fixed;left:16px;bottom:16px;'
        'z-index:9999;background:rgba(77,182,172,.12);border:1px solid #4DB6AC;'
        'color:#D8D9DA;padding:9px 14px;border-radius:8px;'
        'font:13px -apple-system,Segoe UI,Roboto,sans-serif;'
        'box-shadow:0 2px 8px rgba(0,0,0,.4)">'
        '<span style="cursor:pointer;color:#8e9297;margin-right:8px;font-weight:700" '
        'onclick="this.parentNode.remove()">×</span>'
        f'Update available — <a href="{RELEASES_PAGE}" target="_blank" '
        f'rel="noopener" style="color:#4DB6AC;font-weight:600">{label}</a></div>'
    )
    return html.encode("utf-8")


def render_setup_html() -> bytes:
    """The setup/drop page with the writable data location + active profile filled in.

    Users need to know where their dashboard and imported chats live — the
    console window is the only other place it's shown. The active profile's root
    is a local filesystem path (never chat content), safe to display.
    """
    html = (SETUP_HTML
            .replace("__WORK_ROOT__", str(active_root()))
            .replace("__ACTIVE_PROFILE__", active_profile())
            .replace("__RELEASES_PAGE__", RELEASES_PAGE))
    return html.encode("utf-8")


def _profile_switcher_bytes() -> bytes:
    """A compact dashboard-header profile switcher (current name + switch dropdown).

    Rendered per-request so the shown name always matches the active profile. A
    ``<select>`` is populated from ``/profile`` and, on change, POSTs a switch and
    reloads (or alerts on a 409 while a run is active).
    """
    name = active_profile()
    html = (
        '<div id="ca-profile" style="position:fixed;left:16px;top:16px;z-index:9999;'
        'display:flex;gap:6px;align-items:center;background:#22262B;'
        'border:1px solid #4DB6AC;border-radius:20px;padding:6px 12px;'
        'font:600 12px -apple-system,Segoe UI,Roboto,sans-serif;color:#4DB6AC;'
        'box-shadow:0 2px 8px rgba(0,0,0,.4)">Profile: '
        f'<span id="ca-prof-name">{name}</span>'
        '<select id="ca-prof-sel" onchange="(function(s){fetch(\'/profile\','
        '{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},'
        'body:JSON.stringify({action:\'switch\',name:s.value})}).then(function(r){'
        'if(r.status===409){alert(\'A run is in progress — cannot switch.\');return}'
        'location.href=\'/\'});})(this)" '
        'style="background:#1a1d21;color:#D8D9DA;border:1px solid #2c3137;'
        'border-radius:6px;font-size:12px;padding:2px 4px"></select></div>'
        '<script>fetch(\'/profile\').then(function(r){return r.json()}).then(function(j){'
        'var s=document.getElementById(\'ca-prof-sel\');if(!s)return;'
        '(j.profiles||[]).forEach(function(n){var o=document.createElement(\'option\');'
        'o.value=n;o.textContent=n;if(n===j.active)o.selected=true;s.appendChild(o);});'
        '}).catch(function(){});</script>'
    )
    return html.encode("utf-8")


def inject_add_chats(html: bytes) -> bytes:
    """Insert the floating 'Add chats' / 'Re-analyze' controls, a profile switcher
    and an update banner (when one is available) before </body> at serve time.

    Never touches the on-disk dashboard so ``file://`` usage is unchanged.
    """
    snippet = _ADD_CHATS_SNIPPET + _profile_switcher_bytes() + _update_banner_bytes()
    marker = b"</body>"
    idx = html.rfind(marker)
    if idx == -1:
        return html + snippet
    return html[:idx] + snippet + html[idx:]


# --------------------------------------------------------------------------- #
# Static file helpers
# --------------------------------------------------------------------------- #
_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}


def safe_static(url_path: str):
    """Resolve a URL path to a file under the active Dashboard/, or None."""
    rel = url_path.lstrip("/")
    base = dash_dir()
    root = base.resolve()
    target = (base / rel).resolve()
    if target == root or root in target.parents:
        if target.is_file():
            return target
    return None


def manifest_ready() -> bool:
    """Dashboard is servable when the active profile's manifest exists non-empty."""
    try:
        m = manifest_path()
        return m.exists() and m.stat().st_size > 0
    except OSError:
        return False


def hidden_path() -> Path:
    """Active profile's Dashboard/data/hidden.json (builders' hidden-chat source)."""
    return dash_dir() / "data" / "hidden.json"


def _read_hidden() -> list:
    """Return the persisted hidden-chat id list (empty when absent/invalid)."""
    try:
        data = json.loads(hidden_path().read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, str)]
    except (OSError, ValueError):
        pass
    return []


def _write_hidden(ids: list) -> None:
    """Persist the hidden-chat id list to the active Dashboard/data/hidden.json."""
    hp = hidden_path()
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text(
        json.dumps(list(ids), ensure_ascii=False, indent=0), encoding="utf-8")


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = f"ChatAnalyzer/{APP_VERSION}"

    def log_message(self, fmt, *args):  # quiet; keep console clean
        pass

    # -- helpers -------------------------------------------------------------
    def _send(self, code, body: bytes, ctype="text/html; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _serve_file(self, path: Path, inject=False):
        data = path.read_bytes()
        ctype = _MIME.get(path.suffix.lower(), "application/octet-stream")
        if inject:
            data = inject_add_chats(data)
        self._send(200, data, ctype)

    # -- routing -------------------------------------------------------------
    def do_GET(self):
        route = self.path.split("?", 1)[0]

        if route == "/progress":
            self._json(200, _snapshot_progress())
            return
        if route == "/version":
            self._json(200, _snapshot_version())
            return
        if route == "/hidden":
            self._json(200, _read_hidden())
            return
        if route == "/profile":
            self._json(200, {"active": active_profile(),
                             "profiles": list_profiles()})
            return
        if route == "/setup":
            self._send(200, render_setup_html())
            return
        if route == "/":
            if manifest_ready():
                self._serve_file(dash_dir() / "index.html", inject=True)
            else:
                self._redirect("/setup")
            return
        if route in ("/index.html",):
            if manifest_ready():
                self._serve_file(dash_dir() / "index.html", inject=True)
                return
            self._redirect("/setup")
            return

        target = safe_static(route)
        if target is None:
            self._send(404, b"Not found")
            return
        self._serve_file(target)

    do_HEAD = do_GET

    def do_POST(self):
        route = self.path.split("?", 1)[0]
        if route == "/upload":
            self._handle_upload()
        elif route == "/upload-folder":
            self._handle_upload_folder()
        elif route == "/import-path":
            self._handle_import_path()
        elif route == "/reanalyze":
            self._handle_reanalyze()
        elif route == "/start-fresh":
            self._handle_start_fresh()
        elif route == "/hidden":
            self._handle_hidden()
        elif route == "/profile":
            self._handle_profile()
        else:
            self._send(404, b"Not found")

    def _handle_profile(self):
        """Switch or create a profile (M3.3).

        Body: ``{"action":"switch"|"create","name":<str>}``. Both actions change
        the active profile, so both are refused with 409 while a run is active.
        ``create`` makes ``profiles/<name>/`` (and its data dirs) then activates
        it; ``switch`` requires the profile to already exist. Names are sanitized
        to ``[A-Za-z0-9._ -]`` (max 40). On success returns ``{"ok":True,...}``;
        the client redirects to ``/`` (the new profile's dashboard, or /setup if
        it has no data yet).
        """
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            action = str(payload.get("action", "")).strip()
            name = sanitize_profile_name(str(payload.get("name", "")))
        except Exception as exc:
            self._json(400, {"error": f"bad request: {exc}"})
            return
        if action not in ("switch", "create"):
            self._json(400, {"error": "action must be 'switch' or 'create'"})
            return
        if not name:
            self._json(400, {"error": "invalid profile name"})
            return
        # Changing the active profile mid-run would repoint the pipeline's output
        # dirs — refuse while a run is active.
        with _state_lock:
            if _running:
                self._json(409, {"busy": True})
                return
        existing = list_profiles()
        if action == "create":
            if name in existing and (profiles_dir() / name).is_dir():
                self._json(400, {"error": f"profile '{name}' already exists"})
                return
            (profiles_dir() / name).mkdir(parents=True, exist_ok=True)
        else:  # switch
            if not (profiles_dir() / name).is_dir():
                self._json(400, {"error": f"no such profile: {name}"})
                return
        try:
            _write_active_profile(name)
        except OSError as exc:
            self._json(500, {"error": f"could not persist active profile: {exc}"})
            return
        self._json(200, {"ok": True, "active": name,
                         "profiles": list_profiles()})

    def _handle_hidden(self):
        """Persist the dashboard's hidden-chat id list to Dashboard/data/hidden.json.

        Body is a JSON array of chat ids. This is the single source of truth the
        builders (build_connected.py / build_insights.py) read to exclude hidden
        chats on the next re-analyze.
        """
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"[]"
            data = json.loads(raw.decode("utf-8") or "[]")
        except Exception as exc:
            self._json(400, {"error": f"bad hidden payload: {exc}"})
            return
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            self._json(400, {"error": "expected a JSON array of chat ids"})
            return
        try:
            _write_hidden(data)
        except OSError as exc:
            self._json(500, {"error": f"could not write hidden.json: {exc}"})
            return
        self._json(200, {"saved": True, "count": len(data)})

    def _handle_upload(self):
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            self._json(400, {"error": "expected multipart/form-data"})
            return
        with _state_lock:
            if _running:
                self._json(409, {"busy": True})
                return
        try:
            boundary = _boundary(ctype)
            length = int(self.headers.get("Content-Length", "0"))
            fd, tmp_path = tempfile.mkstemp(suffix=".zip")
            with os.fdopen(fd, "wb") as fh:
                original_name = stream_multipart_file(self.rfile, length, boundary, fh)
        except Exception as exc:
            self._json(400, {"error": f"upload failed: {exc}"})
            return
        display_name = _sanitize_upload_name(original_name)
        if not _start_run(Path(tmp_path), cleanup=True, display_name=display_name):
            self._json(409, {"busy": True})
            return
        self._json(200, {"started": True})

    def _handle_upload_folder(self):
        """Reconstruct a dropped folder on disk and route it through ``_ingest``.

        The client uploads every file in the folder as one multipart batch, each
        part's filename carrying its path relative to the folder root. We stream
        the batch into a temp tree (never buffering the whole body) and then run
        the existing directory-import path over it.
        """
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            self._json(400, {"error": "expected multipart/form-data"})
            return
        with _state_lock:
            if _running:
                self._json(409, {"busy": True})
                return
        try:
            boundary = _boundary(ctype)
            length = int(self.headers.get("Content-Length", "0"))
            root = Path(tempfile.mkdtemp(prefix="ca-folder-"))
            count = stream_multipart_folder(self.rfile, length, boundary, root)
        except Exception as exc:
            self._json(400, {"error": f"folder upload failed: {exc}"})
            return
        if count == 0:
            self._json(400, {"error": "no files received in folder upload"})
            return
        # If the tree has a single top-level directory (the dropped folder),
        # import that so the chat folder keeps its real name.
        entries = [p for p in root.iterdir()]
        src = entries[0] if len(entries) == 1 and entries[0].is_dir() else root
        if not _start_run(src, cleanup=False):
            self._json(409, {"busy": True})
            return
        self._json(200, {"started": True})

    def _handle_reanalyze(self):
        with _state_lock:
            if _running:
                self._json(409, {"busy": True})
                return
        if not (active_root() / "Chats").exists():
            self._json(400, {"error": "No Chats/ to re-analyze yet — import first."})
            return
        if not _start_reanalyze():
            self._json(409, {"busy": True})
            return
        self._json(200, {"started": True})

    def _handle_start_fresh(self):
        with _state_lock:
            if _running:
                self._json(409, {"busy": True})
                return
        try:
            backup, moved = start_fresh()
        except Exception as exc:
            self._json(500, {"error": f"start fresh failed: {exc}"})
            return
        self._json(200, {"ok": True, "backup": str(backup), "moved": moved})

    def _handle_import_path(self):
        with _state_lock:
            if _running:
                self._json(409, {"busy": True})
                return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            raw = str(payload.get("path", "")).strip()
        except Exception as exc:
            self._json(400, {"error": f"bad request: {exc}"})
            return
        if not raw:
            self._json(400, {"error": "no path given"})
            return
        p = Path(raw).expanduser()
        if not p.exists():
            self._json(400, {"error": f"path not found: {raw}"})
            return
        if not _start_run(p, cleanup=False):
            self._json(409, {"busy": True})
            return
        self._json(200, {"started": True})


# --------------------------------------------------------------------------- #
# Server bootstrap
# --------------------------------------------------------------------------- #
def _bind_server() -> ThreadingHTTPServer:
    """Bind the preferred port, else fall back to an ephemeral one."""
    try:
        return ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        return ThreadingHTTPServer((HOST, 0), Handler)


def main() -> None:
    _ensure_runtime_layout()
    _start_update_check()  # fail-silent GitHub release check in the background
    httpd = _bind_server()
    host, port = httpd.server_address[0], httpd.server_address[1]
    url = f"http://{host}:{port}/"
    print("=" * 60)
    print(f"Your chats, dashboard and results are stored in:")
    print(f"    {WORK_ROOT}")
    print("=" * 60)
    print(f"Chat Analyzer running at {url}")
    print("Paste that address into your browser.")
    print("Press Ctrl+C to stop.")
    # Don't auto-open the browser — on some desktop environments (KDE, etc.)
    # webbrowser.open() can hang or crash when the system URL handler
    # conflicts with the bundled libraries (e.g. OpenSSL version mismatch).
    # Users can open the URL manually; it's a one-time copy-paste.
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
