#!/usr/bin/env python3
"""Zero-dependency launcher for the chat-analysis pipeline.

Double-clickable entry point: starts a localhost web server, opens the browser,
shows a "drop your export" setup page, runs the whole pipeline with live
progress, then the same tab becomes the dashboard.

Pure standard library only (http.server, threading, webbrowser, json, zipfile,
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
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8347
HOST = "127.0.0.1"


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

    ``CHAT_ANALYZER_HOME`` overrides everything (used by tests / to keep data
    outside the app dir). Otherwise: next to the executable when frozen; the
    repo root from source.
    """
    env = os.environ.get("CHAT_ANALYZER_HOME")
    if env:
        return Path(env).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BUNDLE_ROOT = bundle_root()
WORK_ROOT = work_root()
DASH_DIR = WORK_ROOT / "Dashboard"
MANIFEST = DASH_DIR / "data" / "manifest.js"


def _ensure_runtime_layout() -> None:
    """Make the working dir usable: on-path imports, cwd, vendored ECharts.

    In a frozen build the code modules live inside the bundle (already on
    ``sys.path``), but ``assets/echarts.min.js`` is read by the dashboard
    exporter via a *cwd-relative* path, so we mirror it into WORK_ROOT/assets.
    """
    if str(BUNDLE_ROOT) not in sys.path:
        sys.path.insert(0, str(BUNDLE_ROOT))
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
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
# Pipeline worker
# --------------------------------------------------------------------------- #
def _ingest(source_path: Path) -> None:
    """Bring a user-supplied export into ``Chats/``.

    A ``.zip`` is routed through ``main.import_zip`` (platform-detected,
    zip-slip safe). A directory is copied under ``Chats/`` so the recursive
    discovery in ``main`` picks up its inbox / result.json.
    """
    import main  # lazy — keeps `import launcher` matplotlib/numpy free

    if source_path.is_file() and source_path.suffix.lower() == ".zip":
        main.import_zip(str(source_path), WORK_ROOT)
        return
    if source_path.is_dir():
        dest = WORK_ROOT / "Chats" / f"imported_{source_path.name}"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source_path, dest)
        return
    raise ValueError(f"Not a zip or a folder: {source_path}")


def run_pipeline(source_path: Path, cleanup: bool = False) -> None:
    """Full pipeline in a worker thread: import → analyze → dashboard → connected."""
    global _running
    try:
        _set_progress(stage="importing", detail=source_path.name,
                      i=0, n=0, done=False, error=None)
        _ingest(source_path)

        import main
        _set_progress(stage="analyzing", detail="")

        def _cb(i: int, n: int, chat_name: str) -> None:
            # chat NAME only — never message contents
            _set_progress(stage="analyzing", detail=chat_name, i=i, n=n)

        main.run_all(
            base_dir=WORK_ROOT,
            output_dir=str(WORK_ROOT / "Outputs"),
            skip_visualizations=True,
            progress_cb=_cb,
        )

        _set_progress(stage="dashboard", detail="building dashboard")
        from src.dashboard_export import run_export
        run_export(
            output_dir=str(WORK_ROOT / "Outputs"),
            dash_dir=str(DASH_DIR),
        )

        _set_progress(stage="connected", detail="building connected profile")
        try:
            import build_connected
            build_connected.main([
                "--chats-dir", str(WORK_ROOT / "Chats"),
                "--dash-dir", str(DASH_DIR),
            ])
        except SystemExit:
            pass
        except Exception as exc:  # connected is Instagram-only / best-effort
            print(f"connected profile skipped: {exc}")

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


def _start_run(source_path: Path, cleanup: bool) -> bool:
    """Begin a run if none is active. Returns False if one is already running."""
    global _running
    with _state_lock:
        if _running:
            return False
        _running = True
    t = threading.Thread(target=run_pipeline, args=(source_path, cleanup), daemon=True)
    t.start()
    return True


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
</style></head>
<body><div class="card">
<h1>Chat Analyzer</h1>
<div class="muted">Everything runs on your computer. Nothing is uploaded anywhere.</div>

<div id="drop">Drop your Instagram or Telegram export <b>.zip</b> here<br>
<span class="muted">or click to choose a file</span>
<input id="file" type="file" accept=".zip" hidden></div>

<div class="sep">Or paste a path to a zip / folder on this computer</div>
<input id="path" type="text" placeholder="/home/you/Downloads/instagram-export.zip">
<button id="pathbtn">Analyze this path</button>

<div id="bar"><div></div></div>
<div id="status"></div>
</div>
<script>
const drop=document.getElementById('drop'),file=document.getElementById('file'),
  bar=document.getElementById('bar'),barFill=bar.firstElementChild,
  status=document.getElementById('status'),pathBtn=document.getElementById('pathbtn'),
  pathInput=document.getElementById('path');
let polling=false;
function busy(){status.classList.remove('err');bar.style.display='block';}
function fail(m){status.classList.add('err');status.textContent=m;}
drop.onclick=()=>file.click();
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('over');}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('over');}));
drop.addEventListener('drop',ev=>{if(ev.dataTransfer.files.length)upload(ev.dataTransfer.files[0]);});
file.onchange=()=>{if(file.files.length)upload(file.files[0]);};
pathBtn.onclick=()=>{const p=pathInput.value.trim();if(!p)return;busy();status.textContent='Importing...';
  fetch('/import-path',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:p})}).then(r=>r.json()).then(handleStart).catch(e=>fail(''+e));};
function upload(f){busy();status.textContent='Uploading '+f.name+'...';
  const fd=new FormData();fd.append('file',f,f.name);
  fetch('/upload',{method:'POST',body:fd}).then(r=>r.json()).then(handleStart).catch(e=>fail(''+e));}
function handleStart(j){if(j.error){fail(j.error);return;}if(j.busy){fail('A run is already in progress.');return;}poll();}
function poll(){if(polling)return;polling=true;const iv=setInterval(()=>{
  fetch('/progress').then(r=>r.json()).then(p=>{
    if(p.error){clearInterval(iv);polling=false;fail('Error: '+p.error);return;}
    if(p.done){clearInterval(iv);barFill.style.width='100%';status.textContent='Done! Opening dashboard...';
      setTimeout(()=>location.href='/',600);return;}
    let pct=5;let label=p.stage;
    if(p.stage==='analyzing'&&p.n){pct=10+80*(p.i/p.n);label='Analyzing '+(p.detail||'')+' ('+p.i+'/'+p.n+')';}
    else if(p.stage==='dashboard'){pct=92;label='Building dashboard';}
    else if(p.stage==='connected'){pct=97;label='Building your connected profile';}
    else if(p.stage==='importing'){pct=6;label='Importing '+(p.detail||'');}
    barFill.style.width=pct+'%';status.textContent=label;
  }).catch(()=>{});},700);}
</script></body></html>"""


_ADD_CHATS_SNIPPET = (
    b'<a href="/setup" style="position:fixed;right:16px;bottom:16px;z-index:9999;'
    b'background:#4DB6AC;color:#08302c;padding:9px 14px;border-radius:20px;'
    b'font:600 13px -apple-system,Segoe UI,Roboto,sans-serif;text-decoration:none;'
    b'box-shadow:0 2px 8px rgba(0,0,0,.4)">\xe2\x9e\x95 Add chats</a>'
)


def inject_add_chats(html: bytes) -> bytes:
    """Insert the fixed 'Add chats' link before </body> at serve time.

    Never touches the on-disk dashboard so ``file://`` usage is unchanged.
    """
    marker = b"</body>"
    idx = html.rfind(marker)
    if idx == -1:
        return html + _ADD_CHATS_SNIPPET
    return html[:idx] + _ADD_CHATS_SNIPPET + html[idx:]


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
    """Resolve a URL path to a file under Dashboard/, or None (traversal-safe)."""
    rel = url_path.lstrip("/")
    root = DASH_DIR.resolve()
    target = (DASH_DIR / rel).resolve()
    if target == root or root in target.parents:
        if target.is_file():
            return target
    return None


def manifest_ready() -> bool:
    """Dashboard is servable when the manifest exists and is non-empty."""
    try:
        return MANIFEST.exists() and MANIFEST.stat().st_size > 0
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "ChatAnalyzer/1.0"

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
        if route == "/setup":
            self._send(200, SETUP_HTML.encode("utf-8"))
            return
        if route == "/":
            if manifest_ready():
                self._serve_file(DASH_DIR / "index.html", inject=True)
            else:
                self._redirect("/setup")
            return
        if route in ("/index.html",):
            if manifest_ready():
                self._serve_file(DASH_DIR / "index.html", inject=True)
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
        elif route == "/import-path":
            self._handle_import_path()
        else:
            self._send(404, b"Not found")

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
                stream_multipart_file(self.rfile, length, boundary, fh)
        except Exception as exc:
            self._json(400, {"error": f"upload failed: {exc}"})
            return
        if not _start_run(Path(tmp_path), cleanup=True):
            self._json(409, {"busy": True})
            return
        self._json(200, {"started": True})

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
    httpd = _bind_server()
    host, port = httpd.server_address[0], httpd.server_address[1]
    url = f"http://{host}:{port}/"
    print(f"Chat Analyzer running at {url}")
    print("Open that address in your browser if it didn't open automatically.")
    print("Press Ctrl+C to stop.")
    threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
