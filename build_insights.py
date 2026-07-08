#!/usr/bin/env python3
"""Build the Insights ("Findings") layer for the dashboard.

Reads the SAME aggregate payloads the dashboard reads — the per-chat daily
tables (``Dashboard/data/<chat>.js``) listed in ``manifest.js`` and the
``connected_<variant>`` owner profiles — runs the Tier 1 rule engine
(``src.insights_engine``) over them, and writes:

* ``Dashboard/data/insights.js`` — ``window.INSIGHTS = {...};`` (``</script>``
  neutralised) for the dashboard to lazy-load.
* ``Dashboard/data/insights.json`` — a pretty, human-readable twin.

The engine is structurally message-content-blind: it only ever sees the
aggregate numbers already in ``Dashboard/data``. Contact NAMES appear in
findings; message text never does.

Runs fine when the connected files are absent (chat findings only) and when no
chats are present (connected findings only). Usage::

    python build_insights.py [--dash-dir Dashboard]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.insights_engine import run_chat, run_connected  # noqa: E402

_SCRIPT_RE = re.compile(r'</script', re.IGNORECASE)

# window.DASHBOARD_DATA["slug"] = { ... };  (the assignment we care about)
_CHAT_RE = re.compile(
    r'window\.DASHBOARD_DATA\s*\[[^\]]*\]\s*=\s*(\{.*\})\s*;?\s*$', re.S)
_MANIFEST_RE = re.compile(
    r'window\.DASHBOARD_MANIFEST\s*=\s*(\[.*\])\s*;?\s*$', re.S)
_CONN_RE = re.compile(
    r'window\.CONNECTED_V\s*\[[^\]]*\]\s*=\s*(\{.*\})\s*;?\s*$', re.S)

CONNECTED_VARIANTS = ('instagram', 'telegram', 'all')


# --------------------------------------------------------------------------- #
# Loading (strip the ``window.__X =`` wrapper, or read JSON twins)
# --------------------------------------------------------------------------- #

def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return None


def load_manifest(dash_dir: Path) -> List[Dict[str, Any]]:
    txt = _read(dash_dir / 'data' / 'manifest.js')
    if not txt:
        return []
    m = _MANIFEST_RE.search(txt)
    if not m:
        return []
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return []


def load_chat_payload(dash_dir: Path, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    rel = entry.get('file') or f"data/{entry.get('id')}.js"
    txt = _read(dash_dir / rel)
    if not txt:
        return None
    m = _CHAT_RE.search(txt)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def load_connected(dash_dir: Path, variant: str) -> Optional[Dict[str, Any]]:
    """Prefer the JSON twin; fall back to parsing the ``.js`` payload."""
    j = _read(dash_dir / 'data' / f'connected_{variant}.json')
    if j:
        try:
            return json.loads(j)
        except json.JSONDecodeError:
            pass
    js = _read(dash_dir / 'data' / f'connected_{variant}.js')
    if js:
        m = _CONN_RE.search(js)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    return None


# --------------------------------------------------------------------------- #
# Owner resolution (owner may use different display names per platform)
# --------------------------------------------------------------------------- #

def resolve_owner_by_platform(manifest: List[Dict[str, Any]],
                              payloads: Dict[str, Dict[str, Any]],
                              connected: Dict[str, Optional[Dict[str, Any]]]
                              ) -> Dict[str, str]:
    """Map ``platform -> owner display name``.

    Primary source: the connected profiles carry the resolved ``owner`` per
    variant. Fallback: the participant appearing in the most dyadic chats of
    that platform.
    """
    owners: Dict[str, str] = {}
    ig, tg = connected.get('instagram'), connected.get('telegram')
    if ig and ig.get('owner'):
        owners['instagram'] = ig['owner']
    if tg and tg.get('owner'):
        owners['telegram'] = tg['owner']

    # Fallback per platform via participant frequency.
    by_platform: Dict[str, Counter] = {}
    for entry in manifest:
        p = payloads.get(entry.get('id'))
        if not p or p.get('is_group'):
            continue
        plat = p.get('platform', entry.get('platform', 'instagram'))
        c = by_platform.setdefault(plat, Counter())
        for name in set(p.get('participants', [])[:2]):
            c[name] += 1
    for plat, counter in by_platform.items():
        if plat not in owners and counter:
            owners[plat] = counter.most_common(1)[0][0]
    return owners


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #

def _escape_script(text: str) -> str:
    return _SCRIPT_RE.sub(r'<\\/script', text)


def dump_insights_js(insights: Dict[str, Any]) -> str:
    body = json.dumps(insights, ensure_ascii=False, separators=(',', ':'))
    return f'window.INSIGHTS = {_escape_script(body)};\n'


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #

def build(dash_dir: Path) -> Dict[str, Any]:
    manifest = load_manifest(dash_dir)

    payloads: Dict[str, Dict[str, Any]] = {}
    for entry in manifest:
        cid = entry.get('id')
        if not cid:
            continue
        p = load_chat_payload(dash_dir, entry)
        if p is not None:
            payloads[cid] = p

    connected = {v: load_connected(dash_dir, v) for v in CONNECTED_VARIANTS}
    owners = resolve_owner_by_platform(manifest, payloads, connected)

    insights: Dict[str, Any] = {}
    for cid, p in payloads.items():
        if p.get('is_group'):
            continue
        plat = p.get('platform', 'instagram')
        owner = owners.get(plat) or owners.get('instagram') or 'You'
        findings = run_chat(cid, p, owner)
        if findings:
            insights[cid] = findings

    conn_out: Dict[str, List[Dict[str, Any]]] = {}
    ig, tg = connected.get('instagram'), connected.get('telegram')
    for v in CONNECTED_VARIANTS:
        cp = connected.get(v)
        if not cp:
            continue
        if v == 'all':
            conn_out[v] = run_connected(cp, ig=ig, tg=tg)
        else:
            conn_out[v] = run_connected(cp)
    if conn_out:
        insights['connected'] = conn_out

    return insights


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='Build the Findings/insights layer.')
    ap.add_argument('--dash-dir', default='Dashboard',
                    help='dashboard directory holding data/ (default: Dashboard)')
    args = ap.parse_args(argv)

    dash_dir = Path(args.dash_dir)
    data_dir = dash_dir / 'data'
    if not data_dir.is_dir():
        print(f'insights: no {data_dir} — nothing to do')
        return 0

    insights = build(dash_dir)

    js_path = data_dir / 'insights.js'
    json_path = data_dir / 'insights.json'
    js_path.write_text(dump_insights_js(insights), encoding='utf-8')
    json_path.write_text(json.dumps(insights, ensure_ascii=False, indent=2),
                         encoding='utf-8')

    n_chats = sum(1 for k in insights if k != 'connected')
    n_findings = sum(len(v) for k, v in insights.items() if k != 'connected')
    n_conn = sum(len(v) for v in insights.get('connected', {}).values())
    print(f'insights: {n_findings} chat findings across {n_chats} chats, '
          f'{n_conn} connected findings -> {js_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
