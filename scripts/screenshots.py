#!/usr/bin/env python3
"""Capture README screenshots from a SYNTHETIC corpus with a headless browser.

End to end, with no real data ever touched:

    1. generate a synthetic corpus (scripts/make_synthetic_corpus.py)
    2. run the full pipeline over it in a temp CHAT_ANALYZER_HOME
    3. build dashboard + connected + insights there
    4. drive a headless Chromium-family browser to capture:
         - the chat view with charts
         - the Findings section
         - the Connected ("You") view
         - the chat picker with the platform filter visible
         - the launcher's /setup drop page (served live)
    5. write PNGs into docs/img/

If no headless browser is found the script still generates the corpus + builds
the dashboard and prints manual capture instructions (see scripts/screenshots.md).

Usage:
    venv/bin/python scripts/screenshots.py            # auto temp home
    venv/bin/python scripts/screenshots.py --home /tmp/ca-shots --keep
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IMG_DIR = REPO / "docs" / "img"

# Candidate headless browsers, in preference order.
_BROWSERS = [
    "chromium", "chromium-browser", "google-chrome-stable", "google-chrome",
    "brave", "brave-browser",
]


def find_browser() -> str | None:
    for name in _BROWSERS:
        path = shutil.which(name)
        if path:
            return path
    # Firefox has a different flag set; supported as a last resort.
    if shutil.which("firefox"):
        return shutil.which("firefox")
    return None


def _py() -> str:
    return sys.executable


# Known parse-time bugs in the generated dashboard's inline <script> that break
# ALL rendering in a real browser (unescaped apostrophes inside single-quoted JS
# string literals). We patch ONLY the throwaway temp-dir copy so screenshots can
# render; the repo's dashboard template is never touched (owned elsewhere). If
# the upstream template is fixed, these replacements simply become no-ops.
_TEMPLATE_BUG_FIXES = [
    ("— that's a finding too.", "— that\\'s a finding too."),
]


def _workaround_template_bugs(dash: Path) -> None:
    idx = dash / "index.html"
    src = idx.read_text(encoding="utf-8")
    changed = False
    for bad, good in _TEMPLATE_BUG_FIXES:
        if bad in src and good not in src:
            src = src.replace(bad, good)
            changed = True
    if changed:
        idx.write_text(src, encoding="utf-8")
        print("  (applied temp-only workaround for upstream dashboard "
              "template SyntaxError so charts render)")


def build_everything(home: Path) -> None:
    """Corpus -> pipeline -> dashboard/connected/insights in ``home``."""
    env = dict(os.environ, CHAT_ANALYZER_HOME=str(home))
    subprocess.run([_py(), str(REPO / "scripts" / "make_synthetic_corpus.py"),
                    "--out", str(home)], check=True, env=env)
    subprocess.run([_py(), "-c",
                    "import main; from pathlib import Path; "
                    f"main.run_all(base_dir=Path({str(home)!r}), "
                    f"output_dir=str(Path({str(home)!r})/'Outputs'), "
                    "generate_visualizations=False)"],
                   check=True, cwd=str(REPO), env=env)
    for script, args in (
        ("build_dashboard.py", ["--output-dir", str(home / "Outputs"),
                                "--dash-dir", str(home / "Dashboard")]),
        ("build_connected.py", ["--chats-dir", str(home / "Chats"),
                                "--dash-dir", str(home / "Dashboard")]),
        ("build_insights.py", ["--dash-dir", str(home / "Dashboard")]),
    ):
        subprocess.run([_py(), str(REPO / script), *args],
                       check=True, cwd=str(REPO), env=env)
    _workaround_template_bugs(home / "Dashboard")


# On-load JS injected into a throwaway copy of index.html per shot. Each returns
# the DOM action to run; a generous setTimeout lets ECharts finish drawing.
_INJECTIONS = {
    "chat": "selectChat('Alex_Rivera');",
    # Headless --screenshot captures from the top of the layout, so scrolling is
    # useless; instead hoist the Findings section to the top of the page.
    "findings": ("selectChat('Alex_Rivera');"
                 "setTimeout(function(){var b=document.getElementById('findingsBox');"
                 "if(b){var s=b.closest('.section')||b.parentNode;"
                 "var app=document.getElementById('app')||document.body;"
                 "app.insertBefore(s,app.firstChild);window.scrollTo(0,0);}},2000);"),
    "connected": "selectConnected();",
    "platform_filter": ("selectChat('Alex_Rivera');"
                        "setTimeout(function(){openDD();},1200);"),
}


def _shot_html(dash_dir: Path, key: str, action: str) -> Path:
    src = (dash_dir / "index.html").read_text(encoding="utf-8")
    inject = (f"<script>window.addEventListener('load',function(){{"
              f"setTimeout(function(){{{action}}},400);}});</script>")
    out = dash_dir / f"_shot_{key}.html"
    marker = "</body>"
    idx = src.rfind(marker)
    src = src[:idx] + inject + src[idx:] if idx != -1 else src + inject
    out.write_text(src, encoding="utf-8")
    return out


def capture(browser: str, url: str, out: Path, width: int, height: int,
            budget_ms: int = 9000) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    if "firefox" in browser:
        cmd = [browser, "--headless", "--window-size", f"{width},{height}",
               f"--screenshot={out}", url]
    else:
        cmd = [browser, "--headless", "--disable-gpu", "--no-sandbox",
               "--hide-scrollbars", f"--window-size={width},{height}",
               f"--virtual-time-budget={budget_ms}", f"--screenshot={out}", url]
    subprocess.run(cmd, capture_output=True, timeout=90)
    return out.exists() and out.stat().st_size > 0


def _serve_launcher(home: Path):
    """Start the launcher HTTP server bound to an ephemeral port; return (mod, base)."""
    os.environ["CHAT_ANALYZER_HOME"] = str(home)
    sys.path.insert(0, str(REPO))
    import importlib
    import launcher
    importlib.reload(launcher)
    from http.server import ThreadingHTTPServer
    httpd = ThreadingHTTPServer((launcher.HOST, 0), launcher.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://{launcher.HOST}:{httpd.server_address[1]}"
    return httpd, base


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Capture README screenshots.")
    ap.add_argument("--home", default=None,
                    help="temp CHAT_ANALYZER_HOME (default: a fresh mkdtemp)")
    ap.add_argument("--keep", action="store_true",
                    help="keep the temp home instead of deleting it")
    args = ap.parse_args(argv)

    home = Path(args.home).resolve() if args.home else \
        Path(tempfile.mkdtemp(prefix="ca-shots-"))
    home.mkdir(parents=True, exist_ok=True)

    print(f"Building synthetic corpus + dashboard under {home} ...")
    build_everything(home)
    dash = home / "Dashboard"

    browser = find_browser()
    if not browser:
        print("\nNO headless browser found (looked for: "
              + ", ".join(_BROWSERS) + ", firefox).")
        print("The corpus + dashboard are built at:")
        print(f"  {dash}/index.html")
        print("Follow scripts/screenshots.md to capture the images manually.")
        return 2

    print(f"Using browser: {browser}")
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    made = []

    # 1-4: dashboard shots from injected throwaway copies.
    shot_sizes = {
        "chat": (1440, 2600),
        "findings": (1440, 1500),
        "connected": (1440, 2400),
        "platform_filter": (1440, 1200),
    }
    try:
        for key, action in _INJECTIONS.items():
            page = _shot_html(dash, key, action)
            w, h = shot_sizes[key]
            out = IMG_DIR / f"{key}.png"
            ok = capture(browser, f"file://{page}", out, w, h)
            print(f"  {'OK ' if ok else 'MISS'} {out.name}")
            if ok:
                made.append(out.name)
            page.unlink(missing_ok=True)
    finally:
        for p in dash.glob("_shot_*.html"):
            p.unlink(missing_ok=True)

    # 5: live /setup drop page.
    httpd, base = _serve_launcher(home)
    try:
        out = IMG_DIR / "setup.png"
        ok = capture(browser, base + "/setup", out, 1440, 1100)
        print(f"  {'OK ' if ok else 'MISS'} {out.name}")
        if ok:
            made.append(out.name)
    finally:
        httpd.shutdown()

    print(f"\nCaptured {len(made)} screenshots into {IMG_DIR}")
    if not args.keep:
        shutil.rmtree(home, ignore_errors=True)
    else:
        print(f"Kept temp home: {home}")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
