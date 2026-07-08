"""Connected Analysis — owner-centric cross-chat computation module.

Merges chats into one timeline and profiles the OWNER (their texting behaviour,
attention, and social portfolio). Builds three variants — ``instagram``,
``telegram`` and a merged ``all`` (dual-owner, cross-platform attention). See
``docs/CONNECTED_ANALYSIS.md`` for the full metric definitions and output schema.

Everything here is NEW code; all pipeline infrastructure is reused read-only
(``main``, ``src.timeutil``, ``src.normalizer``, ``src.analyzer_v3``,
``src.metrics_v4``, ``src.config``, ``src.dashboard_export``). No concurrency
locked file is modified — only imported.

Privacy: raw message text is reduced to per-message numeric features at load
time and discarded. Only aggregates / counts / dates are emitted.
"""

from __future__ import annotations

import json
import re
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from src.timeutil import to_datetime, DEFAULT_TIMEZONE
from src.normalizer import (
    is_real_message,
    decode_georgian_text,
    normalize_chat,
)
from src.analyzer_v3 import EMOJI_PATTERN, _split_sessions
from src.metrics_v4 import _is_question
from src.config import SESSION_GAP_MS
# Read-only reuse of the psycholinguistic lexicons + helpers.
from src.dashboard_export import (
    LEX_WE, LEX_I, LEX_YOU, LEX_POS, LEX_NEG,
    _tokens, _media_count, slugify,
)

_SCRIPT_RE = re.compile(r'</script', re.IGNORECASE)

# Window / burst constants.
PARALLEL_WINDOW_MS = 10 * 60 * 1000     # 10-minute attention window
SWITCH_ADJACENT_MS = 10 * 60 * 1000     # "consecutive" owner msgs within 10 min
BURST_GAP_MS = 15 * 60 * 1000           # engagement burst: gaps < 15 min
NIGHT_HOURS = frozenset(range(0, 6))    # 00:00–05:59 for "night ownership"

# Session-type thresholds (documented in the design doc).
PING_MAX_MSGS = 6
PING_MAX_DUR = 5.0
LONG_DUR = 20.0
DEEP_WPT = 8.0
DEEP_Q = 2
DEEP_I_RATE = 0.04
HANGOUT_MEDIA_RATIO = 0.3
HANGOUT_MAX_WPT = 6.0

SESSION_TYPES = ('ping', 'exchange', 'hangout', 'deep_talk')


# --------------------------------------------------------------------------- #
# Discovery + loading  (Instagram-only)
# --------------------------------------------------------------------------- #

_INBOX_SUFFIX = Path('your_instagram_activity') / 'messages' / 'inbox'


def discover_instagram_chats(chats_dir: str) -> List[Path]:
    """Return chat directories under every Instagram inbox in ``chats_dir``.

    v1 is Instagram-only: prefer ``Chats/Instagram`` but fall back to the whole
    ``Chats`` tree — the ``your_instagram_activity/messages/inbox`` suffix means
    only Instagram exports ever match, so Telegram is excluded by construction.
    """
    root = Path(chats_dir)
    search_roots = [root / 'Instagram', root]
    inboxes: List[Path] = []
    seen: set = set()
    for base in search_roots:
        if not base.exists():
            continue
        for inbox in base.glob('**/' + str(_INBOX_SUFFIX)):
            rp = inbox.resolve()
            if inbox.is_dir() and rp not in seen:
                seen.add(rp)
                inboxes.append(inbox)

    chats: List[Path] = []
    seen_chats: set = set()
    for inbox in inboxes:
        for chat_dir in sorted(inbox.iterdir()):
            if not chat_dir.is_dir():
                continue
            rp = chat_dir.resolve()
            if rp in seen_chats:
                continue
            has_msgs = (
                (chat_dir / 'normalized.json').exists() or
                (chat_dir / 'combined_message.json').exists() or
                any(chat_dir.glob('message_*.json'))
            )
            if has_msgs:
                seen_chats.add(rp)
                chats.append(chat_dir)
    return chats


def _load_normalized(chat_dir: Path) -> Optional[Dict[str, Any]]:
    """Load a chat and normalize IN MEMORY (never writes into ``Chats/``)."""
    norm = chat_dir / 'normalized.json'
    if norm.exists():
        try:
            return json.loads(norm.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    combined = chat_dir / 'combined_message.json'
    data: Optional[Dict[str, Any]] = None
    if combined.exists():
        try:
            data = json.loads(combined.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = None
    if data is None:
        try:
            from src.data_combiner import combine_messages
            data = combine_messages(str(chat_dir))
        except Exception:
            return None
    try:
        return normalize_chat(data)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Per-message reduction  (text -> numeric features, then text discarded)
# --------------------------------------------------------------------------- #

def reduce_message(msg: Dict[str, Any], timezone: str) -> Dict[str, Any]:
    """Reduce a normalized message to a compact numeric record.

    Keys ``timestamp_ms`` / ``sender_name`` are kept so ``_split_sessions`` and
    the existing session helpers work unchanged.
    """
    content = msg.get('content', '') or ''
    lang = msg.get('language', '') or ''
    real = is_real_message(msg)
    ts = msg.get('timestamp_ms', 0) or 0
    dt = to_datetime(ts, timezone)
    iso = dt.isocalendar()

    words = content.split() if real else []
    i = we = you = pos = neg = 0
    if real:
        for t in _tokens(content):
            if t in LEX_WE: we += 1
            elif t in LEX_I: i += 1
            elif t in LEX_YOU: you += 1
            if t in LEX_POS: pos += 1
            elif t in LEX_NEG: neg += 1

    return {
        'timestamp_ms': ts,
        'sender_name': msg.get('sender_name', 'Unknown'),
        'real': real,
        'sys': lang == 'system',
        'type': msg.get('type', 'text'),
        'w': len(words),
        'wlen': sum(len(w) for w in words),
        'ch': len(content) if real else 0,
        'em': len(EMOJI_PATTERN.findall(content)) if content else 0,
        'q': bool(_is_question(msg)) if real else False,
        'h': dt.hour,
        'day': dt.strftime('%Y-%m-%d'),
        'mon': dt.strftime('%Y-%m'),
        'week': f'{iso[0]}-W{iso[1]:02d}',
        'i': i, 'we': we, 'you': you, 'pos': pos, 'neg': neg,
        'media': _media_count(msg),
        'photos': _len_field(msg.get('photos')),
        'videos': _len_field(msg.get('videos')),
        'voice': _len_field(msg.get('audio_files')),
        'shares': 1 if msg.get('share') else 0,
        'lang': lang if real else ('media' if lang == 'media' else lang),
    }


def _len_field(val: Any) -> int:
    if isinstance(val, list):
        return len(val)
    return 1 if val else 0


class Chat:
    """A loaded chat reduced to numeric records plus metadata."""

    __slots__ = ('chat_id', 'name', 'participants', 'is_group', 'recs',
                 'thread_path', 'platform')

    def __init__(self, chat_id: str, name: str, participants: List[str],
                 recs: List[Dict[str, Any]], thread_path: str = '',
                 platform: str = 'instagram', is_group: Optional[bool] = None):
        self.chat_id = chat_id
        self.name = name
        self.participants = participants
        # Telegram carries an authoritative is_group flag (a 2-person group is
        # still a group); Instagram infers it from the participant count.
        self.is_group = (len(participants) >= 3) if is_group is None else bool(is_group)
        self.recs = recs
        self.thread_path = thread_path
        self.platform = platform


def load_chat(chat_dir: Path, taken: set, timezone: str) -> Optional[Chat]:
    data = _load_normalized(chat_dir)
    if not data:
        return None
    participants = [
        decode_georgian_text(p.get('name', '') if isinstance(p, dict) else str(p))
        for p in (data.get('participants') or [])
    ]
    participants = [p for p in participants if p]
    name = decode_georgian_text(data.get('title') or chat_dir.name)
    recs = [reduce_message(m, timezone) for m in data.get('messages', [])]
    recs.sort(key=lambda r: r['timestamp_ms'])
    return Chat(slugify(name, taken), name, participants, recs,
                thread_path=str(data.get('thread_path') or ''),
                platform='instagram')


# --------------------------------------------------------------------------- #
# Telegram discovery + loading  (via the shared read-only loader)
# --------------------------------------------------------------------------- #

def discover_telegram_chats(chats_dir: str) -> List[Path]:
    """Return Telegram export directories under ``chats_dir/Telegram``.

    Each export is a directory containing a ``result.json`` (Telegram Desktop
    "Export Chat History → JSON").
    """
    root = Path(chats_dir) / 'Telegram'
    chats: List[Path] = []
    if not root.exists():
        return chats
    for chat_dir in sorted(root.iterdir()):
        if chat_dir.is_dir() and (chat_dir / 'result.json').exists():
            chats.append(chat_dir)
    return chats


def load_telegram_chat(chat_dir: Path, taken: set, timezone: str) -> Optional[Chat]:
    """Load a Telegram export dir and reduce it with the same ``reduce_message``
    path Instagram uses.

    Uses ``src.loaders.telegram.load_telegram_chat`` (read-only) to normalize the
    ``result.json`` into the pipeline's chat shape, then reduces each message to
    the compact numeric record and discards text — identical to Instagram.
    """
    from src.loaders.telegram import load_telegram_chat as _load_tg
    try:
        data = _load_tg(str(chat_dir))
    except Exception:
        return None
    participants = [
        decode_georgian_text(p.get('name', '') if isinstance(p, dict) else str(p))
        for p in (data.get('participants') or [])
    ]
    participants = [p for p in participants if p]
    name = decode_georgian_text(data.get('title') or chat_dir.name)
    recs = [reduce_message(m, timezone) for m in data.get('messages', [])]
    recs.sort(key=lambda r: r['timestamp_ms'])
    # Telegram group-type chats (private_group / supergroup / channel …) carry an
    # authoritative is_group flag; honour it so a 2-person group still lands in
    # the groups lane, exactly like an Instagram group.
    is_group = bool(data.get('is_group')) or len(participants) >= 3
    return Chat(slugify(name, taken), name, participants, recs,
                thread_path=str(data.get('thread_path') or ''),
                platform='telegram', is_group=is_group)


def dedup_chats(chats: List[Chat]) -> Tuple[List[Chat], int]:
    """Drop duplicate chat folders sharing a ``thread_path`` (renamed copies).

    Among duplicates the copy with the MOST messages is kept — robust when the
    Instagram export split a conversation across differently-named folders (e.g.
    ``Ami``/``Ami 2``/``Ami 3``). Returns ``(kept, n_dropped)``. Mirrors
    ``main.dedup_by_thread_path`` but keys on message count, not file bytes,
    since deduped copies may lack raw ``message_*.json`` files.
    """
    by_tp: Dict[str, List[Chat]] = defaultdict(list)
    kept: List[Chat] = []
    dropped = 0
    for c in chats:
        if c.thread_path:
            by_tp[c.thread_path].append(c)
        else:
            kept.append(c)
    for group in by_tp.values():
        if len(group) == 1:
            kept.append(group[0])
        else:
            winner = max(group, key=lambda c: len(c.recs))
            kept.append(winner)
            dropped += len(group) - 1
    return kept, dropped


# --------------------------------------------------------------------------- #
# Small stats helpers
# --------------------------------------------------------------------------- #

def _median(vals: List[float]) -> float:
    return round(float(median(vals)), 3) if vals else 0.0


def _pct(vals: List[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..1)."""
    if not vals:
        return 0.0
    s = sorted(vals)
    idx = min(len(s) - 1, int(round(q * (len(s) - 1))))
    return round(float(s[idx]), 3)


def _gini(values: List[float]) -> float:
    """Gini coefficient of non-negative values (0 = even, 1 = concentrated)."""
    vals = sorted(v for v in values if v >= 0)
    n = len(vals)
    if n <= 1:
        return 0.0
    total = sum(vals)
    if total == 0:
        return 0.0
    cum = sum((i + 1) * v for i, v in enumerate(vals))
    return round((2 * cum) / (n * total) - (n + 1) / n, 4)


def _variance(values: List[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return round(sum((v - mean) ** 2 for v in values) / n, 6)


def _month_index(mon: str) -> int:
    y, m = mon.split('-')
    return int(y) * 12 + int(m)


def _owner_set(owner: Any) -> frozenset:
    """Normalize an owner argument to a set of owner display names.

    Accepts a single name (Instagram/Telegram per-platform owner) or an iterable
    of names (the ``all`` variant, where the owner is one human with a distinct
    handle per platform — e.g. ``{'David', 'Davidus'}``).
    """
    if isinstance(owner, (set, frozenset)):
        return frozenset(owner)
    if isinstance(owner, (list, tuple)):
        return frozenset(owner)
    return frozenset({owner})


# --------------------------------------------------------------------------- #
# Session typing
# --------------------------------------------------------------------------- #

def classify_session(session: List[Dict[str, Any]], owner: str,
                     media_ts: List[int]) -> Tuple[str, Dict[str, Any]]:
    """Classify a dyadic session and return ``(type, features)``.

    ``session`` is the list of REAL records (sorted). ``media_ts`` is the sorted
    list of media-message timestamps in the chat, used to count media that fell
    inside the session window without polluting the real-message turn logic.

    ``owner`` may be a single name or a set of names (the ``all`` variant treats
    both platform handles as the same owner).
    """
    owners = _owner_set(owner)
    n = len(session)
    start = session[0]['timestamp_ms']
    end = session[-1]['timestamp_ms']
    dur = (end - start) / 60000.0

    # turns = maximal same-sender runs
    turns = 0
    prev = None
    for r in session:
        if r['sender_name'] != prev:
            turns += 1
            prev = r['sender_name']

    total_words = sum(r['w'] for r in session)
    wpt = total_words / turns if turns else 0.0
    q = sum(1 for r in session if r['q'])
    owner_words = sum(r['w'] for r in session if r['sender_name'] in owners)
    owner_i = sum(r['i'] for r in session if r['sender_name'] in owners)
    i_rate = owner_i / owner_words if owner_words else 0.0

    media = bisect_right(media_ts, end) - bisect_left(media_ts, start)
    media_ratio = media / n if n else 0.0

    feats = {'n': n, 'dur': round(dur, 2), 'wpt': round(wpt, 2), 'q': q,
             'i_rate': round(i_rate, 4), 'media_ratio': round(media_ratio, 3)}

    if n < PING_MAX_MSGS or dur < PING_MAX_DUR:
        return 'ping', feats
    if dur >= LONG_DUR and wpt >= DEEP_WPT and (q >= DEEP_Q or i_rate >= DEEP_I_RATE):
        return 'deep_talk', feats
    if dur >= LONG_DUR and media_ratio >= HANGOUT_MEDIA_RATIO and wpt < HANGOUT_MAX_WPT:
        return 'hangout', feats
    return 'exchange', feats


# --------------------------------------------------------------------------- #
# Main builder
# --------------------------------------------------------------------------- #

def build_connected_data(chats: List[Chat], owner: Any,
                         timezone: str = DEFAULT_TIMEZONE,
                         min_msgs: int = 30, min_replies: int = 50,
                         excluded_count: int = 0,
                         variant: str = 'all',
                         platforms: Optional[List[str]] = None,
                         owner_names: Optional[Any] = None) -> Dict[str, Any]:
    """Compute the full CONNECTED payload from loaded chats.

    ``variant`` is one of ``instagram`` / ``telegram`` / ``all`` and is echoed in
    the payload alongside ``platforms``. ``owner`` is the display label; for the
    ``all`` variant pass ``owner_names`` (the two platform handles of the same
    human) so BOTH are treated as owner when reducing messages — no cross-platform
    contact-identity merging is done, only the owner is unified.
    """
    owners = _owner_set(owner_names) if owner_names is not None else _owner_set(owner)
    owner_label = owner if isinstance(owner, str) else (sorted(owners)[0] if owners else '')
    if platforms is None:
        platforms = sorted({getattr(c, 'platform', 'instagram') for c in chats}) or ['instagram']

    dyads = [c for c in chats if not c.is_group and any(o in c.participants for o in owners)]
    # A chat where the owner isn't a listed participant but authored messages is
    # still treated as a dyad against the other participant.
    for c in chats:
        if not c.is_group and not any(o in c.participants for o in owners) and c not in dyads:
            dyads.append(c)
    groups = [c for c in chats if c.is_group]

    # ---- global owner-sent stream (all chats: dyad + group) --------------- #
    owner_stream: List[Tuple[int, str]] = []  # (ts, chat_id)
    for c in chats:
        for r in c.recs:
            if r['sender_name'] in owners and not r['sys']:
                owner_stream.append((r['timestamp_ms'], c.chat_id))
    owner_stream.sort(key=lambda x: x[0])

    daily: Dict[str, Dict[str, Any]] = {}

    def day_cell(day: str) -> Dict[str, Any]:
        if day not in daily:
            daily[day] = {
                'msgs': 0, 'received': 0, 'words': 0, 'chars': 0, 'emoji': 0,
                'questions': 0, 'night_msgs': 0, 'media': 0,
                'i_words': 0, 'we_words': 0, 'you_words': 0,
                'pos_words': 0, 'neg_words': 0,
                'hours': [0] * 24, 'active_chats': 0,
                'sessions': 0, 'texting_minutes': 0.0, 'bursts': 0,
                '_chats': set(),
            }
        return daily[day]

    # ---- per-day owner aggregates (sent) + received (dyads) --------------- #
    for c in chats:
        is_dyad = c in dyads
        for r in c.recs:
            if r['sys']:
                continue
            if r['sender_name'] in owners:
                cell = day_cell(r['day'])
                cell['msgs'] += 1
                cell['hours'][r['h']] += 1
                cell['_chats'].add(c.chat_id)
                if r['h'] in NIGHT_HOURS:
                    cell['night_msgs'] += 1
                cell['media'] += r['media']
                cell['emoji'] += r['em']
                if r['real']:
                    cell['words'] += r['w']
                    cell['chars'] += r['ch']
                    cell['questions'] += 1 if r['q'] else 0
                    cell['i_words'] += r['i']
                    cell['we_words'] += r['we']
                    cell['you_words'] += r['you']
                    cell['pos_words'] += r['pos']
                    cell['neg_words'] += r['neg']
            elif is_dyad:
                day_cell(r['day'])['received'] += 1

    # ================= B/C/D/E  per-dyad accumulation ===================== #
    contacts: Dict[str, Dict[str, Any]] = {}
    type_mix_month: Dict[str, Counter] = defaultdict(Counter)
    type_mix_week: Dict[str, Counter] = defaultdict(Counter)
    deep_week: Counter = Counter()
    sent_by_month_contact: Dict[str, Counter] = defaultdict(Counter)
    texting_min_month: Counter = Counter()
    texting_min_week: Counter = Counter()
    total_types: Counter = Counter()

    for c in dyads:
        non_owner = [p for p in c.participants if p not in owners]
        senders = Counter(r['sender_name'] for r in c.recs
                          if r['sender_name'] not in owners and not r['sys'])
        if non_owner:
            contact_name = non_owner[0]
        elif senders:
            contact_name = senders.most_common(1)[0][0]
        else:
            contact_name = c.name

        ct = contacts.get(c.chat_id)
        if ct is None:
            ct = _blank_contact(contact_name, c.chat_id,
                                getattr(c, 'platform', 'instagram'))
            contacts[c.chat_id] = ct

        real_recs = [r for r in c.recs if r['real']]
        media_ts = sorted(r['timestamp_ms'] for r in c.recs
                          if not r['real'] and not r['sys'] and r['media'])

        first_ts = last_ts = None
        for r in c.recs:
            if r['sys']:
                continue
            if first_ts is None:
                first_ts = r['timestamp_ms']
                ct['_first_sender'] = r['sender_name']
            last_ts = r['timestamp_ms']
            is_owner = r['sender_name'] in owners
            if is_owner:
                ct['sent'] += 1
                ct['emoji_sent'] += r['em']
                ct['media_sent'] += r['media']
                ct['_o_msgs'] += 1
                if r['real']:
                    ct['_o_words'] += r['w']
                    ct['_o_wlen'] += r['wlen']
                    ct['_o_q'] += 1 if r['q'] else 0
                    ct['_o_i'] += r['i']
                    ct['_o_pos'] += r['pos']
                    ct['_o_em'] += r['em']
                    ct['_o_lang'][r['lang']] += 1
                if r['h'] in NIGHT_HOURS:
                    ct['night_msgs'] += 1
            else:
                ct['received'] += 1
                ct['_c_msgs'] += 1
                ct['_c_em'] += r['em']
        ct['_first_ts'] = first_ts
        ct['_last_ts'] = last_ts
        ct['_months'] = {r['mon'] for r in c.recs if not r['sys']}

        # ---- sessions (real messages) ---- #
        sessions = _split_sessions(real_recs)
        for session in sessions:
            if not session:
                continue
            opener = session[0]['sender_name']
            ct['sessions'] += 1
            if opener in owners:
                ct['initiations'] += 1

            # session type + time-spent (attributed to start day/week/month)
            stype, _ = classify_session(session, owners, media_ts)
            ct['session_types'][stype] += 1
            total_types[stype] += 1
            start = session[0]['timestamp_ms']
            end = session[-1]['timestamp_ms']
            sd = to_datetime(start, timezone)
            iso = sd.isocalendar()
            wk = f'{iso[0]}-W{iso[1]:02d}'
            mo = sd.strftime('%Y-%m')
            type_mix_month[mo][stype] += 1
            type_mix_week[wk][stype] += 1
            if stype == 'deep_talk':
                deep_week[wk] += 1

            owner_here = any(r['sender_name'] in owners for r in session)
            if owner_here:
                dur = (end - start) / 60000.0
                dcell = day_cell(sd.strftime('%Y-%m-%d'))
                dcell['sessions'] += 1
                dcell['texting_minutes'] += dur
                texting_min_month[mo] += dur
                texting_min_week[wk] += dur

            # reply latency: owner replying to contact, session-scoped
            for k in range(1, len(session)):
                cur, prev = session[k], session[k - 1]
                if cur['sender_name'] == prev['sender_name']:
                    continue
                gap = cur['timestamp_ms'] - prev['timestamp_ms']
                if gap < 0 or gap > SESSION_GAP_MS:
                    continue
                if cur['sender_name'] in owners:
                    ct['_lat'].append(gap / 60000.0)

        for mon in ct['_months']:
            sent_by_month_contact[mon][c.chat_id] += 0  # ensure key
        for r in c.recs:
            if r['sender_name'] in owners and not r['sys']:
                sent_by_month_contact[r['mon']][c.chat_id] += 1

    # attribute texting minutes/sessions per-day for groups too (owner engagement)
    for c in groups:
        real_recs = [r for r in c.recs if r['real']]
        for session in _split_sessions(real_recs):
            if not session:
                continue
            if not any(r['sender_name'] in owners for r in session):
                continue
            start = session[0]['timestamp_ms']
            end = session[-1]['timestamp_ms']
            sd = to_datetime(start, timezone)
            iso = sd.isocalendar()
            wk = f'{iso[0]}-W{iso[1]:02d}'
            mo = sd.strftime('%Y-%m')
            dur = (end - start) / 60000.0
            dcell = day_cell(sd.strftime('%Y-%m-%d'))
            dcell['sessions'] += 1
            dcell['texting_minutes'] += dur
            texting_min_month[mo] += dur
            texting_min_week[wk] += dur

    # ---- finalize contacts ---- #
    total_night = sum(ct['night_msgs'] for ct in contacts.values())
    total_sent = sum(ct['sent'] for ct in contacts.values())
    total_received = sum(ct['received'] for ct in contacts.values())
    contact_list: List[Dict[str, Any]] = []
    emoji_rates: List[float] = []
    wordlen_vals: List[float] = []
    lang_geo_vals: List[float] = []
    for ct in contacts.values():
        o_msgs = ct['_o_msgs'] or 0
        o_words = ct['_o_words'] or 0
        lat = ct['_lat']
        lang_total = sum(ct['_o_lang'].values()) or 1
        lang_mix = {k: round(v / lang_total, 3) for k, v in ct['_o_lang'].items()}
        emoji_rate = round(ct['_o_em'] / o_msgs, 4) if o_msgs else 0.0
        avg_word_len = round(ct['_o_wlen'] / o_words, 3) if o_words else 0.0
        c_emoji_rate = round(ct['_c_em'] / ct['_c_msgs'], 4) if ct['_c_msgs'] else 0.0
        gated = ct['sent'] < min_msgs
        latency_ok = len(lat) >= min_replies
        out = {
            'name': ct['name'], 'chat_id': ct['chat_id'],
            'platform': ct['platform'],
            'sent': ct['sent'], 'received': ct['received'],
            'reciprocity': round(ct['sent'] / ct['received'], 3) if ct['received'] else None,
            'emoji_sent': ct['emoji_sent'], 'media_sent': ct['media_sent'],
            'sessions': ct['sessions'], 'initiations': ct['initiations'],
            'initiation_share': round(ct['initiations'] / ct['sessions'], 3) if ct['sessions'] else 0.0,
            'reply_latency_median_min': _median(lat), 'reply_n': len(lat),
            'latency_gated': latency_ok,
            'words_per_turn': round(o_words / o_msgs, 3) if o_msgs else 0.0,
            'question_rate': round(ct['_o_q'] / o_msgs, 4) if o_msgs else 0.0,
            'i_word_rate': round(ct['_o_i'] / o_words, 4) if o_words else 0.0,
            'pos_rate': round(ct['_o_pos'] / o_words, 4) if o_words else 0.0,
            'night_msgs': ct['night_msgs'],
            'night_share': round(ct['night_msgs'] / total_night, 3) if total_night else 0.0,
            'style': {'emoji_rate': emoji_rate, 'avg_word_len': avg_word_len,
                      'lang_mix': lang_mix},
            'mirror_score': round(1 - min(1.0, abs(emoji_rate - c_emoji_rate)), 3),
            'session_types': dict(ct['session_types']),
            'first_day': to_datetime(ct['_first_ts'], timezone).strftime('%Y-%m-%d') if ct['_first_ts'] else None,
            'last_day': to_datetime(ct['_last_ts'], timezone).strftime('%Y-%m-%d') if ct['_last_ts'] else None,
            'months_active': len(ct['_months']),
            'gated': gated,
        }
        contact_list.append(out)
        if not gated:
            emoji_rates.append(emoji_rate)
            wordlen_vals.append(avg_word_len)
            lang_geo_vals.append(lang_mix.get('georgian', 0.0))

    contact_list.sort(key=lambda x: x['sent'], reverse=True)

    # ---- leaderboards ---- #
    ungated = [c for c in contact_list if not c['gated']]
    by_sent = [{'name': c['name'], 'platform': c['platform'], 'sent': c['sent'],
                'share': round(c['sent'] / total_sent, 4) if total_sent else 0.0}
               for c in contact_list[:25]]
    attention_hierarchy = sorted(
        ({'name': c['name'], 'platform': c['platform'],
          'reply_latency_median_min': c['reply_latency_median_min'],
          'reply_n': c['reply_n']} for c in contact_list if c['latency_gated']),
        key=lambda x: x['reply_latency_median_min'])
    openness = sorted(
        ({'name': c['name'], 'platform': c['platform'],
          'words_per_turn': c['words_per_turn'],
          'question_rate': c['question_rate'], 'i_word_rate': c['i_word_rate'],
          'pos_rate': c['pos_rate']} for c in ungated),
        key=lambda x: x['words_per_turn'], reverse=True)
    initiation = sorted(
        ({'name': c['name'], 'platform': c['platform'],
          'initiation_share': c['initiation_share'],
          'sessions': c['sessions']} for c in ungated),
        key=lambda x: x['initiation_share'], reverse=True)
    night = sorted(
        ({'name': c['name'], 'platform': c['platform'],
          'night_share': c['night_share'],
          'night_msgs': c['night_msgs']} for c in contact_list if c['night_msgs']),
        key=lambda x: x['night_share'], reverse=True)
    recip = [c for c in ungated if c['reciprocity'] is not None]
    recip_surplus = sorted(recip, key=lambda x: x['reciprocity'], reverse=True)[:10]
    recip_deficit = sorted(recip, key=lambda x: x['reciprocity'])[:10]

    def _recip_row(c):
        return {'name': c['name'], 'platform': c['platform'],
                'reciprocity': c['reciprocity'],
                'sent': c['sent'], 'received': c['received']}

    # ================= A  merged timeline / attention ==================== #
    attention = _compute_attention(owner_stream, daily, timezone)

    # ================= D  portfolio dynamics ============================= #
    all_months = sorted({r['mon'] for c in chats for r in c.recs if not r['sys']})
    gini_month = {}
    for mon in all_months:
        gini_month[mon] = _gini(list(sent_by_month_contact.get(mon, {}).values()))

    contact_months = {ct['chat_id']: ct['_months'] for ct in contacts.values()}
    active_month, churn_month, react_month = _portfolio_dynamics(contact_months, all_months)

    # ================= E  new-contact funnel ============================= #
    funnel = _funnel(contacts, owners, timezone)

    # ================= groups lane ======================================= #
    groups_lane = _groups_lane(groups, owners, timezone)

    # ---- monthly / weekly rollups ---- #
    monthly = {
        'gini': gini_month,
        'active_contacts': active_month,
        'churned': churn_month,
        'reactivated': react_month,
        'type_mix': {m: {t: type_mix_month[m].get(t, 0) for t in SESSION_TYPES}
                     for m in sorted(type_mix_month)},
        'new_contacts': funnel['new_per_month'],
        'bursts': attention['_bursts_monthly'],
        'texting_minutes': {m: round(texting_min_month[m], 1) for m in sorted(texting_min_month)},
    }
    weekly = {
        'type_mix': {w: {t: type_mix_week[w].get(t, 0) for t in SESSION_TYPES}
                     for w in sorted(type_mix_week)},
        'deep_talk': {w: deep_week[w] for w in sorted(deep_week)},
        'texting_minutes': {w: round(texting_min_week[w], 1) for w in sorted(texting_min_week)},
    }

    # ---- finalize daily (drop private helper set) ---- #
    daily_out: Dict[str, Any] = {}
    for day in sorted(daily):
        cell = daily[day]
        cell['active_chats'] = len(cell.pop('_chats'))
        cell['texting_minutes'] = round(cell['texting_minutes'], 1)
        daily_out[day] = cell
    days = sorted(daily_out)

    n_weeks = max(1, len(weekly['deep_talk']) or len({r['week'] for c in dyads for r in c.recs}))
    deep_total = total_types['deep_talk']
    n_days_active = sum(1 for d in daily_out.values() if d['sessions'])

    payload = {
        'owner': owner_label,
        'variant': variant,
        'platforms': platforms,
        'generated_at': datetime.now().astimezone().isoformat(timespec='seconds'),
        'timezone': timezone,
        'range': {'first_day': days[0] if days else None,
                  'last_day': days[-1] if days else None},
        'daily': daily_out,
        'monthly': monthly,
        'weekly': weekly,
        'attention': {k: v for k, v in attention.items() if not k.startswith('_')},
        'contacts': contact_list,
        'leaderboards': {
            'by_sent_share': by_sent,
            'attention_hierarchy': attention_hierarchy,
            'openness': openness[:25],
            'initiation': initiation[:25],
            'night': night[:25],
            'reciprocity_surplus': [_recip_row(c) for c in recip_surplus],
            'reciprocity_deficit': [_recip_row(c) for c in recip_deficit],
        },
        'code_switching': {
            'emoji_rate_variance': _variance(emoji_rates),
            'avg_word_len_variance': _variance(wordlen_vals),
            'lang_variance': _variance(lang_geo_vals),
            'per_contact': [
                {'name': c['name'], 'platform': c['platform'],
                 'emoji_rate': c['style']['emoji_rate'],
                 'avg_word_len': c['style']['avg_word_len'],
                 'lang_mix': c['style']['lang_mix'], 'mirror_score': c['mirror_score']}
                for c in ungated
            ],
        },
        'sessions_typed': {
            'totals': {t: total_types[t] for t in SESSION_TYPES},
            'deep_per_week': round(deep_total / n_weeks, 3),
            'deep_per_day': round(deep_total / max(1, len(days)), 4),
        },
        'funnel': {
            'caveat': 'Export contains only accepted, still-existing chats (survivorship bias).',
            'stages': funnel['stages'],
            'retention': funnel['retention'],
            'new_per_month': funnel['new_per_month'],
        },
        'groups': groups_lane,
        'reciprocity': {
            'sent_total': total_sent, 'received_total': total_received,
            'ratio': round(total_sent / total_received, 3) if total_received else None,
        },
        'totals': {
            'chats_included': len(chats), 'chats_excluded': excluded_count,
            'dyads': len(dyads), 'groups': len(groups),
            'contacts': len(contact_list),
            'messages_sent': total_sent, 'messages_received': total_received,
            'bursts': attention['bursts']['count'],
        },
    }
    return payload


def _blank_contact(name: str, chat_id: str,
                   platform: str = 'instagram') -> Dict[str, Any]:
    return {
        'name': name, 'chat_id': chat_id, 'platform': platform,
        'sent': 0, 'received': 0, 'emoji_sent': 0, 'media_sent': 0,
        'sessions': 0, 'initiations': 0, 'night_msgs': 0,
        'session_types': Counter(),
        '_lat': [], '_o_msgs': 0, '_o_words': 0, '_o_wlen': 0, '_o_q': 0,
        '_o_i': 0, '_o_pos': 0, '_o_em': 0, '_o_lang': Counter(),
        '_c_msgs': 0, '_c_em': 0,
        '_first_ts': None, '_last_ts': None, '_first_sender': None, '_months': set(),
    }


def _compute_attention(owner_stream: List[Tuple[int, str]],
                       daily: Dict[str, Any], timezone: str) -> Dict[str, Any]:
    """A. Parallel texting, chat-switch, fragmentation, bursts."""
    # 10-min windows
    windows: Dict[int, set] = defaultdict(set)
    hours_active: set = set()
    for ts, cid in owner_stream:
        windows[ts // PARALLEL_WINDOW_MS].add(cid)
        hours_active.add(ts // (60 * 60 * 1000))
    active_windows = len(windows)
    juggling = sum(1 for chats in windows.values() if len(chats) >= 2)
    parallel_rate = round(juggling / active_windows, 4) if active_windows else 0.0

    # chat-switch over adjacent (<10 min) consecutive owner messages
    adjacent = switches = 0
    for i in range(1, len(owner_stream)):
        (t0, c0), (t1, c1) = owner_stream[i - 1], owner_stream[i]
        if t1 - t0 < SWITCH_ADJACENT_MS:
            adjacent += 1
            if c0 != c1:
                switches += 1
    active_hours = len(hours_active)

    # bursts: maximal runs with gaps < 15 min
    bursts: List[Tuple[int, int, int]] = []  # (start, end, n)
    if owner_stream:
        b_start = owner_stream[0][0]
        b_last = owner_stream[0][0]
        b_n = 1
        for i in range(1, len(owner_stream)):
            t = owner_stream[i][0]
            if t - b_last < BURST_GAP_MS:
                b_last = t
                b_n += 1
            else:
                bursts.append((b_start, b_last, b_n))
                b_start = b_last = t
                b_n = 1
        bursts.append((b_start, b_last, b_n))

    durations = [(e - s) / 60000.0 for s, e, _ in bursts]
    burst_days = {to_datetime(s, timezone).strftime('%Y-%m-%d') for s, _, _ in bursts}
    per_active_day = round(len(bursts) / len(burst_days), 3) if burst_days else 0.0

    # attribute bursts to daily + monthly
    monthly: Dict[str, List[float]] = defaultdict(list)
    for s, e, _ in bursts:
        d = to_datetime(s, timezone)
        if d.strftime('%Y-%m-%d') in daily:
            daily[d.strftime('%Y-%m-%d')]['bursts'] += 1
        monthly[d.strftime('%Y-%m')].append((e - s) / 60000.0)
    bursts_monthly = {m: {'count': len(v), 'median_min': _median(v)}
                      for m, v in sorted(monthly.items())}

    return {
        'parallel_texting_rate': parallel_rate,
        'chat_switch': {
            'switch_fraction': round(switches / adjacent, 4) if adjacent else 0.0,
            'switches_per_active_hour': round(switches / active_hours, 4) if active_hours else 0.0,
        },
        'fragmentation_index': parallel_rate,
        'focus_index': round(1 - parallel_rate, 4),
        'active_windows': active_windows, 'active_hours': active_hours,
        'bursts': {
            'count': len(bursts), 'per_active_day': per_active_day,
            'mean_msgs': round(sum(n for _, _, n in bursts) / len(bursts), 3) if bursts else 0.0,
            'duration_min': {'median': _median(durations),
                             'p90': _pct(durations, 0.9),
                             'max': round(max(durations), 3) if durations else 0.0},
        },
        '_bursts_monthly': bursts_monthly,
    }


def _portfolio_dynamics(contact_months: Dict[str, set], all_months: List[str]):
    """D. active contacts / churn / reactivation per month."""
    active_month: Dict[str, int] = {}
    churn_month: Counter = Counter()
    react_month: Counter = Counter()

    max_idx = _month_index(all_months[-1]) if all_months else 0

    for mon in all_months:
        active_month[mon] = sum(1 for months in contact_months.values() if mon in months)

    for months in contact_months.values():
        idxs = sorted(_month_index(m) for m in months)
        idx_set = set(idxs)
        for m in months:
            mi = _month_index(m)
            # churn: active this month, silent next 2 months. Skip the final two
            # months of the dataset (their silence is unobservable — censored).
            if mi + 2 > max_idx:
                continue
            if (mi + 1) not in idx_set and (mi + 2) not in idx_set:
                churn_month[_index_to_month(mi)] += 1
        # reactivation: active after a gap of >= 2 silent months
        for prev, cur in zip(idxs, idxs[1:]):
            if cur - prev >= 3:
                react_month[_index_to_month(cur)] += 1

    return active_month, dict(churn_month), dict(react_month)


def _index_to_month(idx: int) -> str:
    y, m = divmod(idx, 12)
    if m == 0:
        y -= 1
        m = 12
    return f'{y:04d}-{m:02d}'


def _funnel(contacts: Dict[str, Any], owner: Any, timezone: str) -> Dict[str, Any]:
    """E. new-contact funnel + retention."""
    owners = _owner_set(owner)
    new_per_month: Dict[str, Dict[str, int]] = {}
    stages = {'met': 0, 'talked_again': 0, 'recurring': 0}
    retention = {'survived_3_sessions': 0, 'active_30d': 0, 'active_90d': 0}

    DAY_MS = 86400000
    for ct in contacts.values():
        if ct['_first_ts'] is None:
            continue
        stages['met'] += 1
        if ct['sessions'] >= 2:
            stages['talked_again'] += 1
        if ct['sessions'] >= 3:
            stages['recurring'] += 1
            retention['survived_3_sessions'] += 1
        span = (ct['_last_ts'] - ct['_first_ts']) / DAY_MS if ct['_last_ts'] else 0
        if span >= 30:
            retention['active_30d'] += 1
        if span >= 90:
            retention['active_90d'] += 1

        mon = to_datetime(ct['_first_ts'], timezone).strftime('%Y-%m')
        row = new_per_month.setdefault(mon, {'total': 0, 'owner_first': 0, 'contact_first': 0})
        row['total'] += 1
        # who texted first = sender of the earliest non-system message.
        if ct['_first_sender'] in owners:
            row['owner_first'] += 1
        else:
            row['contact_first'] += 1

    return {'new_per_month': dict(sorted(new_per_month.items())),
            'stages': stages, 'retention': retention}


def _groups_lane(groups: List[Chat], owner: Any, timezone: str) -> Dict[str, Any]:
    """Small separate lane: time/messages in groups (never pollutes contacts).

    Aggregates groups across every platform present; each group row carries its
    ``platform`` so the merged view can badge it.
    """
    owners = _owner_set(owner)
    per_group = []
    total_owner = total_all = 0
    total_min = 0.0
    for c in groups:
        owner_msgs = sum(1 for r in c.recs if r['sender_name'] in owners and not r['sys'])
        all_msgs = sum(1 for r in c.recs if not r['sys'])
        real_recs = [r for r in c.recs if r['real']]
        minutes = 0.0
        for session in _split_sessions(real_recs):
            if session and any(r['sender_name'] in owners for r in session):
                minutes += (session[-1]['timestamp_ms'] - session[0]['timestamp_ms']) / 60000.0
        total_owner += owner_msgs
        total_all += all_msgs
        total_min += minutes
        per_group.append({
            'name': c.name, 'chat_id': c.chat_id,
            'platform': getattr(c, 'platform', 'instagram'),
            'messages_owner': owner_msgs, 'messages_total': all_msgs,
            'members': len(c.participants), 'texting_minutes': round(minutes, 1),
        })
    per_group.sort(key=lambda g: g['messages_owner'], reverse=True)
    return {
        'count': len(groups), 'messages_owner': total_owner,
        'messages_total': total_all, 'texting_minutes': round(total_min, 1),
        'per_group': per_group,
    }


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #

def _escape_script(text: str) -> str:
    return _SCRIPT_RE.sub(r'<\\/script', text)


def dump_connected_js(payload: Dict[str, Any], variant: str) -> str:
    """Serialize a variant payload as a lazy ``window.CONNECTED_V`` assignment.

    Each variant file registers itself into the shared ``window.CONNECTED_V``
    map keyed by variant name, so the dashboard can lazy-load one variant at a
    time without clobbering the others.
    """
    body = _escape_script(json.dumps(payload, ensure_ascii=False,
                                     separators=(',', ':')))
    return ('window.CONNECTED_V = window.CONNECTED_V || {};\n'
            f'window.CONNECTED_V[{json.dumps(variant)}] = {body};\n')


def write_variant_outputs(payload: Dict[str, Any], dash_dir: str,
                          variant: str) -> Tuple[Path, Path]:
    """Write ``connected_<variant>.js`` + ``connected_<variant>.json``."""
    data_dir = Path(dash_dir) / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    js_path = data_dir / f'connected_{variant}.js'
    json_path = data_dir / f'connected_{variant}.json'
    js_path.write_text(dump_connected_js(payload, variant), encoding='utf-8')
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                         encoding='utf-8')
    return js_path, json_path
