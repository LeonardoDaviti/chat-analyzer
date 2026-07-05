"""Interactive HTML dashboard exporter.

Scans ``Outputs/*`` for the latest analysed run of every chat and emits a
self-contained, offline (``file://``) Grafana-style dashboard into
``Outputs/Dashboard/``.

The heavy lifting on the client is driven by a compact **daily aggregate table**
computed here from ``normalized.json`` (one row per user per calendar day). The
browser derives every weekly/monthly rollup and windowed metric from those rows,
so arbitrary-range recomputation is instant without shipping Python to the client
(see ``docs/HTML_DASHBOARD_DESIGN.md`` §2).

All shared pipeline infrastructure is reused rather than re-derived:
  - ``src.timeutil.to_datetime`` for every timestamp -> wall-clock conversion.
  - ``src.normalizer.is_real_message`` / ``decode_georgian_text``.
  - ``src.analyzer_v3.EMOJI_PATTERN`` + ``_split_sessions``.
  - ``src.metrics_v4._is_question`` / ``NIGHT_HOURS``.
  - ``src.config.SESSION_GAP_MS``.
  - ``src.output_manager.truncate_component``.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.timeutil import to_datetime, DEFAULT_TIMEZONE
from src.normalizer import is_real_message, decode_georgian_text
from src.analyzer_v3 import EMOJI_PATTERN, _split_sessions
from src.metrics_v4 import _is_question, NIGHT_HOURS
from src.config import SESSION_GAP_MS
from src.output_manager import truncate_component

# Timestamped run folders look like ``2026-07-05_09-50``.
_RUN_RE = re.compile(r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}$')
_SCRIPT_RE = re.compile(r'</script', re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Daily aggregate table
# --------------------------------------------------------------------------- #

def _blank_day() -> Dict[str, Any]:
    return {
        'msgs': 0, 'words': 0, 'chars': 0, 'emoji': 0, 'questions': 0,
        'night_msgs': 0, 'reactions_given': 0, 'reactions_received': 0,
        'media': 0, 'hours': [0] * 24,
        'resp_lat_sum_min': 0.0, 'resp_lat_n': 0, 'initiations': 0,
    }


def _media_count(msg: Dict[str, Any]) -> int:
    """photos + videos + audio_files (+1 for a share) attachments on a message."""
    n = 0
    for field in ('photos', 'videos', 'audio_files'):
        val = msg.get(field)
        if isinstance(val, list):
            n += len(val)
        elif val:
            n += 1
    if msg.get('share'):
        n += 1
    return n


def choose_participants(messages: List[Dict[str, Any]],
                        fallback: Optional[List[str]] = None) -> List[str]:
    """The two most active senders (by real-message volume), most active first."""
    counts = Counter()
    for m in messages:
        if is_real_message(m):
            counts[m.get('sender_name', 'Unknown')] += 1
    ranked = [u for u, _ in counts.most_common()]
    for u in (fallback or []):
        if u not in ranked:
            ranked.append(u)
    while len(ranked) < 2:
        ranked.append(f'User {len(ranked) + 1}')
    return ranked[:2]


def build_daily_aggregates(messages: List[Dict[str, Any]],
                           participants: List[str],
                           timezone: str = DEFAULT_TIMEZONE,
                           ) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Compute the per-day, per-user aggregate table.

    Only the two ``participants`` are tracked. Real-message channels use
    ``is_real_message``; reactions and media are counted over ALL messages.

    Returns ``{ 'YYYY-MM-DD': { user: {aggregate fields...} } }`` with only the
    users that were active on that day present.
    """
    user_set = set(participants)
    daily: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)

    def cell(date: str, user: str) -> Dict[str, Any]:
        day = daily[date]
        if user not in day:
            day[user] = _blank_day()
        return day[user]

    # --- Real-message channels (per message) ------------------------------- #
    for m in messages:
        sender = m.get('sender_name', 'Unknown')
        if sender not in user_set or not is_real_message(m):
            continue
        dt = to_datetime(m.get('timestamp_ms', 0), timezone)
        c = cell(dt.strftime('%Y-%m-%d'), sender)
        content = m.get('content', '') or ''
        c['msgs'] += 1
        c['words'] += len(content.split())
        c['chars'] += len(content)
        c['emoji'] += len(EMOJI_PATTERN.findall(content))
        if _is_question(m):
            c['questions'] += 1
        if dt.hour in NIGHT_HOURS:
            c['night_msgs'] += 1
        c['hours'][dt.hour] += 1

    # --- Reactions + media (ALL messages) ---------------------------------- #
    for m in messages:
        ts = m.get('timestamp_ms', 0)
        date = to_datetime(ts, timezone).strftime('%Y-%m-%d')
        receiver = m.get('sender_name', 'Unknown')
        for r in (m.get('reactions') or []):
            actor = decode_georgian_text(r.get('actor', '') or '')
            if actor in user_set:
                cell(date, actor)['reactions_given'] += 1
            if receiver in user_set:
                cell(date, receiver)['reactions_received'] += 1
        media = _media_count(m)
        if media and receiver in user_set:
            cell(date, receiver)['media'] += media

    # --- Session-derived channels (initiations + reply latency) ------------ #
    real = [m for m in messages
            if is_real_message(m) and m.get('sender_name') in user_set]
    real.sort(key=lambda m: m.get('timestamp_ms', 0))
    for session in _split_sessions(real):
        opener = session[0]
        o_sender = opener.get('sender_name', 'Unknown')
        if o_sender in user_set:
            o_date = to_datetime(opener.get('timestamp_ms', 0), timezone).strftime('%Y-%m-%d')
            cell(o_date, o_sender)['initiations'] += 1
        for k in range(1, len(session)):
            cur, prev = session[k], session[k - 1]
            if cur.get('sender_name') == prev.get('sender_name'):
                continue  # same speaker: not a reply
            gap_ms = cur.get('timestamp_ms', 0) - prev.get('timestamp_ms', 0)
            if gap_ms < 0 or gap_ms > SESSION_GAP_MS:
                continue
            replier = cur.get('sender_name', 'Unknown')
            if replier in user_set:
                r_date = to_datetime(cur.get('timestamp_ms', 0), timezone).strftime('%Y-%m-%d')
                c = cell(r_date, replier)
                c['resp_lat_sum_min'] += gap_ms / 60000.0
                c['resp_lat_n'] += 1

    # Round latency sums and freeze ordinary dicts.
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for date in sorted(daily):
        out[date] = {}
        for user, c in daily[date].items():
            c['resp_lat_sum_min'] = round(c['resp_lat_sum_min'], 2)
            out[date][user] = c
    return out


# --------------------------------------------------------------------------- #
# Lifetime subset from analysis.json
# --------------------------------------------------------------------------- #

def _per_user(analysis: Dict[str, Any], key: str) -> Dict[str, Any]:
    block = analysis.get(key) or {}
    return block.get('per_user', {}) if isinstance(block, dict) else {}


def build_lifetime(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Small, range-independent 'All-time' subset of ``analysis.json``."""
    rt = analysis.get('response_times', {}) or {}
    circ = analysis.get('circadian', {}) or {}
    hl = analysis.get('half_life', {}) or {}
    return {
        'message_counts': analysis.get('message_counts', {}) or {},
        'response_times': {
            'my_median_response_minutes': rt.get('my_median_response_minutes'),
            'partner_median_response_minutes': rt.get('partner_median_response_minutes'),
            'who_delays_more': rt.get('who_delays_more'),
        },
        'final_word_dominance': analysis.get('final_word_dominance', {}) or {},
        'initiation': _per_user(analysis, 'initiation'),
        'question_asymmetry': _per_user(analysis, 'question_asymmetry'),
        'bid_response': _per_user(analysis, 'bid_response'),
        'affect_economy': _per_user(analysis, 'affect_economy'),
        'circadian': {
            'per_user': circ.get('per_user', {}) if isinstance(circ, dict) else {},
            'overlap_coefficient': circ.get('overlap_coefficient') if isinstance(circ, dict) else None,
        },
        'repair': _per_user(analysis, 'repair'),
        'double_texting': _per_user(analysis, 'double_texting'),
        'half_life': {
            'per_user': hl.get('per_user', {}) if isinstance(hl, dict) else {},
            'median_half_life_minutes': hl.get('median_half_life_minutes') if isinstance(hl, dict) else None,
        },
    }


def _change_points(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    cp = analysis.get('change_points') or {}
    if isinstance(cp, dict):
        return cp.get('change_points', []) or []
    return []


# --------------------------------------------------------------------------- #
# Payload assembly
# --------------------------------------------------------------------------- #

def build_chat_payload(name: str,
                       normalized: Dict[str, Any],
                       analysis: Dict[str, Any],
                       timezone: str = DEFAULT_TIMEZONE) -> Dict[str, Any]:
    """Assemble the full per-chat data payload embedded into ``data/{slug}.js``."""
    messages = normalized.get('messages', normalized) if isinstance(normalized, dict) else normalized
    if not isinstance(messages, list):
        messages = []

    fallback = []
    for p in (normalized.get('participants', []) if isinstance(normalized, dict) else []):
        nm = decode_georgian_text(p.get('name', '') if isinstance(p, dict) else str(p))
        if nm:
            fallback.append(nm)
    participants = choose_participants(messages, fallback)
    daily = build_daily_aggregates(messages, participants, timezone)

    return {
        'name': name,
        'participants': participants,
        'daily': daily,
        'change_points': _change_points(analysis),
        'lifetime': build_lifetime(analysis),
    }


# --------------------------------------------------------------------------- #
# Slugs + JS writers
# --------------------------------------------------------------------------- #

def slugify(name: str, taken: set) -> str:
    """Filesystem- and JS-key-safe unique slug, byte-truncated for OS limits."""
    base = re.sub(r'[^A-Za-z0-9._-]+', '_', name).strip('_.')
    base = truncate_component(base or 'chat', max_bytes=48)
    base = base or 'chat'
    slug = base
    i = 2
    while slug in taken or not slug:
        slug = f'{base}_{i}'
        i += 1
    taken.add(slug)
    return slug


def _escape_script(text: str) -> str:
    """Neutralise any ``</script>`` sequence inside embedded JSON."""
    return _SCRIPT_RE.sub(r'<\\/script', text)


def dump_data_js(slug: str, payload: Dict[str, Any]) -> str:
    """``window.DASHBOARD_DATA["slug"] = {...};`` with </script> neutralised."""
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    key = json.dumps(slug, ensure_ascii=False)
    return ('window.DASHBOARD_DATA = window.DASHBOARD_DATA || {};\n'
            f'window.DASHBOARD_DATA[{_escape_script(key)}] = '
            f'{_escape_script(body)};\n')


def dump_manifest_js(manifest: List[Dict[str, Any]]) -> str:
    body = json.dumps(manifest, ensure_ascii=False, separators=(',', ':'))
    return f'window.DASHBOARD_MANIFEST = {_escape_script(body)};\n'


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #

def _latest_run(chat_dir: Path) -> Optional[Path]:
    """Latest timestamped run under ``chat_dir`` with analysis + normalized."""
    runs = []
    for child in chat_dir.iterdir():
        if child.is_dir() and _RUN_RE.match(child.name):
            if (child / 'analysis.json').exists() and (child / 'normalized.json').exists():
                runs.append(child)
    if not runs:
        return None
    return sorted(runs, key=lambda p: p.name)[-1]


def _matches(folder: str, include: List[str], exclude: List[str]) -> bool:
    low = folder.lower()
    if include and not any(s.lower() in low for s in include if s):
        return False
    if exclude and any(s.lower() in low for s in exclude if s):
        return False
    return True


def discover_chats(output_dir: Path, include: List[str],
                   exclude: List[str]) -> List[Tuple[str, Path]]:
    """Return ``(folder_name, latest_run_dir)`` for every eligible chat."""
    found = []
    if not output_dir.exists():
        return found
    for chat_dir in sorted(output_dir.iterdir(), key=lambda p: p.name.lower()):
        if not chat_dir.is_dir() or chat_dir.name == 'Dashboard':
            continue
        if not _matches(chat_dir.name, include, exclude):
            continue
        run = _latest_run(chat_dir)
        if run is not None:
            found.append((chat_dir.name, run))
    return found


def _display_name(folder: str, normalized: Dict[str, Any],
                  analysis: Dict[str, Any]) -> str:
    info = analysis.get('chat_info', {}) if isinstance(analysis, dict) else {}
    for cand in (info.get('chat_name'),
                 normalized.get('title') if isinstance(normalized, dict) else None,
                 folder):
        if cand:
            return decode_georgian_text(cand)
    return folder


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def run_export(output_dir: str = 'Outputs',
               include: Optional[List[str]] = None,
               exclude: Optional[List[str]] = None,
               timezone: str = DEFAULT_TIMEZONE) -> Dict[str, Any]:
    """Build the whole dashboard. Returns a summary dict (also printed by main)."""
    from src.dashboard_template import render_index_html

    out_root = Path(output_dir)
    chats = discover_chats(out_root, include or [], exclude or [])

    dash_dir = out_root / 'Dashboard'
    data_dir = dash_dir / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)

    taken: set = set()
    manifest: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, Any]] = []

    for folder, run in chats:
        try:
            normalized = json.loads((run / 'normalized.json').read_text(encoding='utf-8'))
            analysis = json.loads((run / 'analysis.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue

        name = _display_name(folder, normalized, analysis)
        payload = build_chat_payload(name, normalized, analysis, timezone)
        slug = slugify(name, taken)

        js = dump_data_js(slug, payload)
        data_file = data_dir / f'{slug}.js'
        data_file.write_text(js, encoding='utf-8')

        dates = sorted(payload['daily'].keys())
        messages = sum((payload['lifetime']['message_counts'] or {}).values())
        if not messages:
            messages = sum(u['msgs'] for d in payload['daily'].values() for u in d.values())

        manifest.append({
            'id': slug,
            'name': name,
            'file': f'data/{slug}.js',
            'messages': messages,
            'first_date': dates[0] if dates else None,
            'last_date': dates[-1] if dates else None,
        })
        summary_rows.append({
            'chat': name,
            'slug': slug,
            'days': len(dates),
            'bytes': data_file.stat().st_size,
        })

    manifest.sort(key=lambda e: e['messages'], reverse=True)
    (data_dir / 'manifest.js').write_text(dump_manifest_js(manifest), encoding='utf-8')

    # Vendored ECharts (copied, never downloaded).
    echarts_src = Path('assets/echarts.min.js')
    if echarts_src.exists():
        (dash_dir / 'echarts.min.js').write_bytes(echarts_src.read_bytes())

    (dash_dir / 'index.html').write_text(render_index_html(), encoding='utf-8')

    summary_rows.sort(key=lambda r: r['bytes'], reverse=True)
    return {
        'dashboard_dir': str(dash_dir),
        'chats': summary_rows,
        'manifest': manifest,
    }


def _print_summary(summary: Dict[str, Any]) -> None:
    rows = summary['chats']
    print(f"\nDashboard written to: {summary['dashboard_dir']}")
    print(f"Chats exported: {len(rows)}\n")
    if not rows:
        print("  (no eligible chats found)")
        return
    name_w = min(40, max((len(r['chat']) for r in rows), default=4))
    print(f"  {'CHAT'.ljust(name_w)}  {'DAYS':>5}  {'SIZE':>10}")
    print(f"  {'-' * name_w}  {'-' * 5}  {'-' * 10}")
    total = 0
    for r in rows:
        total += r['bytes']
        chat = r['chat'] if len(r['chat']) <= name_w else r['chat'][:name_w - 1] + '…'
        print(f"  {chat.ljust(name_w)}  {r['days']:>5}  {_fmt_bytes(r['bytes']):>10}")
    print(f"  {'-' * name_w}  {'-' * 5}  {'-' * 10}")
    print(f"  {'TOTAL'.ljust(name_w)}  {'':>5}  {_fmt_bytes(total):>10}")


def _fmt_bytes(n: int) -> str:
    size = float(n)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024
    return f'{n} B'


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Build the interactive HTML dashboard.')
    p.add_argument('--chat', default='', help='comma-separated substrings; keep only matching chat folders')
    p.add_argument('--exclude', default='', help='comma-separated substrings; drop matching chat folders')
    p.add_argument('--output-dir', default='Outputs', help='root Outputs directory (default: Outputs)')
    return p.parse_args(argv)


def _split_csv(value: str) -> List[str]:
    return [s.strip() for s in value.split(',') if s.strip()]


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    summary = run_export(
        output_dir=args.output_dir,
        include=_split_csv(args.chat),
        exclude=_split_csv(args.exclude),
    )
    _print_summary(summary)
    return 0
