"""
V4 Metrics - Relationship-dynamics instrument (statistical layer).

These metrics operationalise the "psychological gap analysis" from
``docs/METRICS_EXPANSION.md``. They deliberately share ALL of the existing
pipeline infrastructure rather than re-deriving it:

  - ``src.timeutil.to_datetime`` for every timestamp -> wall-clock conversion
    (never ``datetime.fromtimestamp``), so buckets are timezone-aware.
  - ``src.config.SESSION_GAP_MS`` / ``analyzer_v3._split_sessions`` for the ONE
    shared session definition (final-flush safe).
  - ``src.session_chunker`` output when available (``valid`` sessions only), with
    its precomputed ``participants.initiated_by/ended_by``.
  - ``src.normalizer`` predicates (``is_real_message``) and ``decode_georgian_text``
    for mojibake reaction actors/emoji.
  - ``analyzer_v3.EMOJI_PATTERN`` for the affect channel.

## The metric contract (F0)

Every V4 metric (except M14, which is a composite timeline) is a function

    metric(messages, users, sessions=None, timezone=DEFAULT_TIMEZONE) -> {
        'per_user': {user: {...}},          # lifetime aggregates per user
        'series':   {bucket: {user: {...}}},# monthly buckets keyed 'YYYY-MM'
        'n':        int,                     # sample size the metric is based on
        ...                                  # optional metric-specific top-level keys
    }

- ``per_user`` always contains an entry for every user in ``users``.
- ``series`` monthly buckets are timezone-aware ('YYYY-MM' from ``to_datetime``).
- ``n`` lets the UI grey out low-confidence values.
- When ``sessions`` (chunker output) is supplied it is preferred; only sessions
  flagged ``valid: True`` are consumed. Otherwise sessions are derived with
  ``_split_sessions`` over the real messages.
- Empty / tiny chats return the contract shape with ``n = 0`` and empty series.

M14 (``change_point_metrics``) has a different, documented output shape.
"""

import re
from collections import Counter, defaultdict
from datetime import datetime
from statistics import median
from typing import Dict, List, Any, Optional

from src.timeutil import to_datetime, DEFAULT_TIMEZONE
from src.config import SESSION_GAP_MS
from src.normalizer import is_real_message, is_system_message, decode_georgian_text
from src.analyzer_v3 import _split_sessions, EMOJI_PATTERN

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

RESPONSE_WINDOW_MS = 30 * 60 * 1000        # 30 min: question / bid response window
DOUBLE_TEXT_GAP_MS = 10 * 60 * 1000        # 10 min: double-text threshold
RUPTURE_SILENCE_MS = 48 * 60 * 60 * 1000   # 48 h: abnormal silence after a session
# Unified night window across every surface (per-chat daily table, group
# metrics, and — matching connected_export.NIGHT_HOURS — the connected view):
# 00:00–05:59. See docs/MONITORING_AUDIT §4/§5. Previously {23,0,1,2}.
NIGHT_HOURS = frozenset(range(0, 6))       # 00:00-05:59 "night"
STREAK_CAP = 10                            # streak histogram cap ("10+")
HALF_LIFE_MIN_GAP_MS = 5 * 60 * 1000       # floor for the "conversation died" gap

_WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

# Interrogative word lists (word-boundary matched). English multiword phrases
# ("do you", ...) are matched as phrases; Georgian particles as words.
_EN_QUESTION_WORDS = [
    'what', 'why', 'how', 'when', 'where', 'who', 'whom', 'whose', 'which',
    'do you', 'did you', 'are you', 'were you', 'will you', 'would you',
    'can you', 'could you', 'have you', 'is it', "isn't", "aren't", "don't you",
]
_GE_QUESTION_WORDS = [
    'რატომ', 'როგორ', 'სად', 'ვინ', 'რა', 'როდის', 'რომელი', 'ხომ',
    'რას', 'რაში', 'საიდან', 'რამდენი', 'ნეტავ',
]

# ASCII words use \b; Georgian has no \b support for its script in `re`, so use
# explicit non-Georgian-letter boundaries.
_EN_QUESTION_RE = re.compile(
    r'\b(?:' + '|'.join(re.escape(w) for w in _EN_QUESTION_WORDS) + r')\b',
    re.IGNORECASE,
)
_GE_QUESTION_RE = re.compile(
    r'(?<![Ⴀ-ჿ])(?:' + '|'.join(re.escape(w) for w in _GE_QUESTION_WORDS)
    + r')(?![Ⴀ-ჿ])'
)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #

def _sorted_real(messages: List[Dict]) -> List[Dict]:
    """Chronologically-sorted real (text) messages."""
    real = [m for m in messages if is_real_message(m)]
    real.sort(key=lambda m: m.get('timestamp_ms', 0))
    return real


def _session_msg_lists(messages: List[Dict],
                       sessions: Optional[List[Dict]],
                       ) -> List[List[Dict]]:
    """Return sessions as chronologically-sorted lists of real messages.

    Prefers the chunker ``sessions`` (valid only) when provided; otherwise
    derives sessions from ``messages`` with the shared ``_split_sessions``.
    Sessions themselves are returned sorted by start time.
    """
    if sessions is not None:
        out = []
        for s in sessions:
            if not s.get('valid', False):
                continue
            rm = [m for m in s.get('real_msgs', []) if is_real_message(m)]
            rm.sort(key=lambda m: m.get('timestamp_ms', 0))
            if rm:
                out.append(rm)
        out.sort(key=lambda sm: sm[0].get('timestamp_ms', 0))
        return out
    return _split_sessions(_sorted_real(messages))


def _month(ts_ms: int, timezone: str) -> str:
    """Timezone-aware 'YYYY-MM' bucket key."""
    return to_datetime(ts_ms, timezone).strftime('%Y-%m')


def _top2(messages: List[Dict], users: List[str]) -> List[str]:
    """The two most active senders (by real-message count), padded from users."""
    counts = Counter()
    for m in messages:
        if is_real_message(m):
            counts[m.get('sender_name', 'Unknown')] += 1
    ranked = [u for u, _ in counts.most_common() if u in set(users)]
    for u in users:
        if u not in ranked:
            ranked.append(u)
    return ranked[:2] if len(ranked) >= 2 else (ranked + users)[:2]


def _partner_map(users: List[str], top2: List[str]) -> Dict[str, str]:
    """Map every user to their conversational partner (the other top-2 member)."""
    a, b = (top2 + [None, None])[:2]
    pm = {}
    for u in users:
        if u == a:
            pm[u] = b
        elif u == b:
            pm[u] = a
        else:
            pm[u] = a if a is not None else b
    return pm


def _real_count_by_user(messages: List[Dict], users: List[str]) -> Dict[str, int]:
    counts = {u: 0 for u in users}
    for m in messages:
        if is_real_message(m):
            s = m.get('sender_name', 'Unknown')
            if s in counts:
                counts[s] += 1
    return counts


def _is_question(msg: Dict) -> bool:
    """Question detection: '?' or an interrogative word (EN or Georgian)."""
    text = msg.get('content', '') or ''
    if not text:
        return False
    if '?' in text:
        return True
    return bool(_EN_QUESTION_RE.search(text) or _GE_QUESTION_RE.search(text))


def _is_bid(msg: Dict) -> bool:
    """A "bid" invites response: question, a share/photo/video, or ends with '!'."""
    if _is_question(msg):
        return True
    if msg.get('photos') or msg.get('videos') or msg.get('share'):
        return True
    text = (msg.get('content', '') or '').strip()
    return text.endswith('!')


def _median(values: List[float]) -> float:
    return round(float(median(values)), 4) if values else 0.0


def _empty(users: List[str], per_user_template: Dict[str, Any],
           **extra) -> Dict[str, Any]:
    """Contract-shaped empty result."""
    out = {
        'per_user': {u: dict(per_user_template) for u in users},
        'series': {},
        'n': 0,
    }
    out.update(extra)
    return out


# --------------------------------------------------------------------------- #
# M1 - Initiation ratio & reopen latency
# --------------------------------------------------------------------------- #

def initiation_metrics(messages: List[Dict], users: List[str],
                       sessions: Optional[List[Dict]] = None,
                       timezone: str = DEFAULT_TIMEZONE) -> Dict[str, Any]:
    """Who opens each session and how long after the previous session ended."""
    template = {'initiation_count': 0, 'initiation_share': 0.0,
                'median_reopen_latency_hours': 0.0}
    sess = _session_msg_lists(messages, sessions)
    if not sess:
        return _empty(users, template)

    per_user = {u: dict(template) for u in users}
    latencies = defaultdict(list)
    series = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'share': 0.0}))

    prev_end = None
    for s in sess:
        initiator = s[0].get('sender_name', 'Unknown')
        start = s[0].get('timestamp_ms', 0)
        end = s[-1].get('timestamp_ms', 0)
        bucket = _month(start, timezone)
        if initiator in per_user:
            per_user[initiator]['initiation_count'] += 1
            series[bucket][initiator]['count'] += 1
            if prev_end is not None:
                latencies[initiator].append((start - prev_end) / 3_600_000)
        prev_end = end

    n = len(sess)
    for u in users:
        per_user[u]['initiation_share'] = round(per_user[u]['initiation_count'] / n, 4)
        per_user[u]['median_reopen_latency_hours'] = _median(latencies[u])

    # Fill monthly shares.
    series_out = {}
    for bucket, ud in series.items():
        total = sum(v['count'] for v in ud.values())
        series_out[bucket] = {
            u: {'count': v['count'],
                'share': round(v['count'] / total, 4) if total else 0.0}
            for u, v in ud.items()
        }

    return {'per_user': per_user, 'series': series_out, 'n': n}


# --------------------------------------------------------------------------- #
# M2 - Question asymmetry (curiosity index)
# --------------------------------------------------------------------------- #

def question_metrics(messages: List[Dict], users: List[str],
                     sessions: Optional[List[Dict]] = None,
                     timezone: str = DEFAULT_TIMEZONE) -> Dict[str, Any]:
    """Interrogative rate per user + whether the partner answered within session."""
    template = {'questions_asked': 0, 'questions_per_100_msgs': 0.0,
                'answered_rate': 0.0, 'ignored_count': 0}
    sess = _session_msg_lists(messages, sessions)
    real_counts = _real_count_by_user([m for s in sess for m in s], users)

    per_user = {u: dict(template) for u in users}
    answered = defaultdict(int)
    series = defaultdict(lambda: defaultdict(
        lambda: {'questions': 0, 'ignored': 0, 'msgs': 0}))

    total_questions = 0
    for s in sess:
        for i, msg in enumerate(s):
            sender = msg.get('sender_name', 'Unknown')
            bucket = _month(msg.get('timestamp_ms', 0), timezone)
            if sender in per_user:
                series[bucket][sender]['msgs'] += 1
            if not _is_question(msg):
                continue
            total_questions += 1
            if sender in per_user:
                per_user[sender]['questions_asked'] += 1
                series[bucket][sender]['questions'] += 1
            # Answered if a DIFFERENT sender replies within the window, in session.
            q_ts = msg.get('timestamp_ms', 0)
            got_answer = False
            for later in s[i + 1:]:
                if later.get('timestamp_ms', 0) - q_ts > RESPONSE_WINDOW_MS:
                    break
                if later.get('sender_name') != sender:
                    got_answer = True
                    break
            if got_answer:
                answered[sender] += 1
            elif sender in per_user:
                per_user[sender]['ignored_count'] += 1
                series[bucket][sender]['ignored'] += 1

    for u in users:
        asked = per_user[u]['questions_asked']
        msgs = real_counts.get(u, 0)
        per_user[u]['questions_per_100_msgs'] = (
            round(asked / msgs * 100, 2) if msgs else 0.0)
        per_user[u]['answered_rate'] = (
            round(answered[u] / asked, 4) if asked else 0.0)

    series_out = {}
    for bucket, ud in series.items():
        series_out[bucket] = {}
        for u, v in ud.items():
            series_out[bucket][u] = {
                'questions': v['questions'],
                'question_rate': round(v['questions'] / v['msgs'] * 100, 2) if v['msgs'] else 0.0,
                'ignored_rate': round(v['ignored'] / v['questions'], 4) if v['questions'] else 0.0,
            }

    return {'per_user': per_user, 'series': series_out, 'n': total_questions}


# --------------------------------------------------------------------------- #
# M3 - Bid-and-response ledger (turning toward / away)
# --------------------------------------------------------------------------- #

def bid_response_metrics(messages: List[Dict], users: List[str],
                         sessions: Optional[List[Dict]] = None,
                         timezone: str = DEFAULT_TIMEZONE) -> Dict[str, Any]:
    """Gottman bids: does the partner turn toward (engage) or away (ignore)?"""
    template = {'bids_made': 0, 'partner_turned_toward_rate': 0.0,
                'toward_rate_given': 0.0}
    sess = _session_msg_lists(messages, sessions)
    top2 = _top2([m for s in sess for m in s], users)
    partner_of = _partner_map(users, top2)

    per_user = {u: dict(template) for u in users}
    toward_hits = defaultdict(int)      # X's bids that got engagement
    given_hits = defaultdict(int)       # bids by partner(U) that U turned toward
    given_opps = defaultdict(int)       # bids by partner(U) (opportunities for U)
    series = defaultdict(lambda: defaultdict(
        lambda: {'bids': 0, 'toward': 0}))

    total_bids = 0
    for s in sess:
        for i, msg in enumerate(s):
            if not _is_bid(msg):
                continue
            sender = msg.get('sender_name', 'Unknown')
            total_bids += 1
            bucket = _month(msg.get('timestamp_ms', 0), timezone)
            if sender in per_user:
                per_user[sender]['bids_made'] += 1
                series[bucket][sender]['bids'] += 1

            bid_ts = msg.get('timestamp_ms', 0)
            responder = None
            for later in s[i + 1:]:
                if later.get('timestamp_ms', 0) - bid_ts > RESPONSE_WINDOW_MS:
                    break
                if later.get('sender_name') != sender:
                    responder = later.get('sender_name')
                    break

            if sender in per_user:
                expected = partner_of.get(sender)
                if expected is not None:
                    given_opps[expected] += 1
                if responder is not None:
                    toward_hits[sender] += 1
                    series[bucket][sender]['toward'] += 1
                    if responder == expected:
                        given_hits[expected] += 1

    for u in users:
        bids = per_user[u]['bids_made']
        per_user[u]['partner_turned_toward_rate'] = (
            round(toward_hits[u] / bids, 4) if bids else 0.0)
        per_user[u]['toward_rate_given'] = (
            round(given_hits[u] / given_opps[u], 4) if given_opps[u] else 0.0)

    series_out = {}
    for bucket, ud in series.items():
        series_out[bucket] = {
            u: {'bids': v['bids'],
                'partner_turned_toward_rate': round(v['toward'] / v['bids'], 4) if v['bids'] else 0.0}
            for u, v in ud.items()
        }

    return {'per_user': per_user, 'series': series_out, 'n': total_bids}


# --------------------------------------------------------------------------- #
# M4 - Reaction & emoji affect economy
# --------------------------------------------------------------------------- #

def affect_economy_metrics(messages: List[Dict], users: List[str],
                           sessions: Optional[List[Dict]] = None,
                           timezone: str = DEFAULT_TIMEZONE) -> Dict[str, Any]:
    """Reactions given/received and emoji usage as an affect channel."""
    template = {'reactions_given': 0, 'reactions_received': 0,
                'reaction_reciprocity': 0.0, 'emoji_per_100_msgs': 0.0}
    user_set = set(users)

    per_user = {u: dict(template) for u in users}
    emoji_count = defaultdict(int)
    msg_count = defaultdict(int)
    series = defaultdict(lambda: defaultdict(
        lambda: {'reactions_given': 0, 'emoji': 0, 'msgs': 0}))

    total_reactions = 0
    emoji_bearing = 0

    for msg in messages:
        receiver = msg.get('sender_name', 'Unknown')
        ts = msg.get('timestamp_ms', 0)
        bucket = _month(ts, timezone)

        # Reactions: actor -> gives, message sender -> receives (decode mojibake).
        for r in (msg.get('reactions') or []):
            actor = decode_georgian_text(r.get('actor', '') or '')
            total_reactions += 1
            if actor in user_set:
                per_user[actor]['reactions_given'] += 1
                series[bucket][actor]['reactions_given'] += 1
            if receiver in user_set:
                per_user[receiver]['reactions_received'] += 1

        # Emoji channel on real text messages only.
        if is_real_message(msg):
            if receiver in user_set:
                msg_count[receiver] += 1
                series[bucket][receiver]['msgs'] += 1
            emojis = len(EMOJI_PATTERN.findall(msg.get('content', '') or ''))
            if emojis:
                emoji_bearing += 1
                if receiver in user_set:
                    emoji_count[receiver] += emojis
                    series[bucket][receiver]['emoji'] += emojis

    for u in users:
        given = per_user[u]['reactions_given']
        received = per_user[u]['reactions_received']
        per_user[u]['reaction_reciprocity'] = (
            round(given / received, 4) if received else 0.0)
        per_user[u]['emoji_per_100_msgs'] = (
            round(emoji_count[u] / msg_count[u] * 100, 2) if msg_count[u] else 0.0)

    series_out = {}
    for bucket, ud in series.items():
        series_out[bucket] = {
            u: {'reactions_given': v['reactions_given'],
                'emoji_per_100_msgs': round(v['emoji'] / v['msgs'] * 100, 2) if v['msgs'] else 0.0}
            for u, v in ud.items()
        }

    return {'per_user': per_user, 'series': series_out,
            'n': total_reactions + emoji_bearing}


# --------------------------------------------------------------------------- #
# M5 - Circadian overlap & sacred hours
# --------------------------------------------------------------------------- #

def circadian_metrics(messages: List[Dict], users: List[str],
                      sessions: Optional[List[Dict]] = None,
                      timezone: str = DEFAULT_TIMEZONE) -> Dict[str, Any]:
    """7x24 activity matrices, hour-of-day overlap coefficient, night-share."""
    template = {'night_share': 0.0, 'peak_hour': None, 'peak_weekday': None}
    real = _sorted_real(messages)
    if not real:
        return _empty(users, template, overlap_coefficient=0.0,
                      matrices={u: [[0] * 24 for _ in range(7)] for u in users})

    matrices = {u: [[0] * 24 for _ in range(7)] for u in users}
    night = defaultdict(int)
    total = defaultdict(int)
    series = defaultdict(lambda: defaultdict(lambda: {'night': 0, 'msgs': 0}))

    n = 0
    for msg in real:
        sender = msg.get('sender_name', 'Unknown')
        if sender not in matrices:
            continue
        n += 1
        dt = to_datetime(msg.get('timestamp_ms', 0), timezone)
        wd, hr = dt.weekday(), dt.hour
        matrices[sender][wd][hr] += 1
        total[sender] += 1
        bucket = dt.strftime('%Y-%m')
        series[bucket][sender]['msgs'] += 1
        if hr in NIGHT_HOURS:
            night[sender] += 1
            series[bucket][sender]['night'] += 1

    per_user = {}
    for u in users:
        tot = total[u]
        hour_hist = [sum(matrices[u][wd][hr] for wd in range(7)) for hr in range(24)]
        wday_hist = [sum(matrices[u][wd]) for wd in range(7)]
        per_user[u] = {
            'night_share': round(night[u] / tot, 4) if tot else 0.0,
            'peak_hour': max(range(24), key=lambda h: hour_hist[h]) if tot else None,
            'peak_weekday': _WEEKDAYS[max(range(7), key=lambda w: wday_hist[w])] if tot else None,
        }

    # Overlap coefficient between the top-2 users' normalized hour-of-day dists.
    top2 = _top2(real, users)
    overlap = 0.0
    if len(top2) >= 2 and all(total[u] for u in top2[:2]):
        a, b = top2[0], top2[1]
        ha = [sum(matrices[a][wd][hr] for wd in range(7)) / total[a] for hr in range(24)]
        hb = [sum(matrices[b][wd][hr] for wd in range(7)) / total[b] for hr in range(24)]
        overlap = round(sum(min(ha[h], hb[h]) for h in range(24)), 4)

    series_out = {}
    for bucket, ud in series.items():
        series_out[bucket] = {
            u: {'night_share': round(v['night'] / v['msgs'], 4) if v['msgs'] else 0.0}
            for u, v in ud.items()
        }

    return {'per_user': per_user, 'series': series_out, 'n': n,
            'overlap_coefficient': overlap, 'matrices': matrices}


# --------------------------------------------------------------------------- #
# M7 - Repair latency (rupture -> repair cycle)
# --------------------------------------------------------------------------- #

def repair_metrics(messages: List[Dict], users: List[str],
                   sessions: Optional[List[Dict]] = None,
                   timezone: str = DEFAULT_TIMEZONE) -> Dict[str, Any]:
    """Ruptures (session end + >48h silence) and who reaches out to repair."""
    template = {'ruptures_caused': 0, 'repairs_made': 0, 'repair_share': 0.0,
                'median_repair_latency_hours': 0.0}
    sess = _session_msg_lists(messages, sessions)
    if len(sess) < 2:
        return _empty(users, template)

    per_user = {u: dict(template) for u in users}
    repair_latencies = defaultdict(list)
    series = defaultdict(lambda: defaultdict(
        lambda: {'ruptures': 0, 'repairs': 0}))

    ruptures = 0
    for i in range(len(sess) - 1):
        cur, nxt = sess[i], sess[i + 1]
        end_ts = cur[-1].get('timestamp_ms', 0)
        start_ts = nxt[0].get('timestamp_ms', 0)
        gap = start_ts - end_ts
        if gap <= RUPTURE_SILENCE_MS:
            continue

        ruptures += 1
        ruptured_by = cur[-1].get('sender_name', 'Unknown')
        repairer = nxt[0].get('sender_name', 'Unknown')
        latency_h = gap / 3_600_000

        if ruptured_by in per_user:
            per_user[ruptured_by]['ruptures_caused'] += 1
            series[_month(end_ts, timezone)][ruptured_by]['ruptures'] += 1
        if repairer in per_user:
            per_user[repairer]['repairs_made'] += 1
            repair_latencies[repairer].append(latency_h)
            series[_month(start_ts, timezone)][repairer]['repairs'] += 1

    for u in users:
        per_user[u]['repair_share'] = (
            round(per_user[u]['repairs_made'] / ruptures, 4) if ruptures else 0.0)
        per_user[u]['median_repair_latency_hours'] = _median(repair_latencies[u])

    series_out = {b: {u: dict(v) for u, v in ud.items()}
                  for b, ud in series.items()}

    return {'per_user': per_user, 'series': series_out, 'n': ruptures}


# --------------------------------------------------------------------------- #
# M10 - Double-texting & re-engagement persistence
# --------------------------------------------------------------------------- #

def _streak_key(length: int) -> str:
    return f'{STREAK_CAP}+' if length >= STREAK_CAP else str(length)


def double_texting_metrics(messages: List[Dict], users: List[str],
                           sessions: Optional[List[Dict]] = None,
                           timezone: str = DEFAULT_TIMEZONE) -> Dict[str, Any]:
    """Anxious-pursuit signal: double texts + unanswered-streak distribution."""
    template = {'double_texts': 0, 'double_text_rate': 0.0,
                'max_unanswered_streak': 0, 'streak_histogram': {}}
    sess = _session_msg_lists(messages, sessions)
    real_counts = _real_count_by_user([m for s in sess for m in s], users)

    double_texts = defaultdict(int)
    max_streak = defaultdict(int)
    histogram = defaultdict(lambda: defaultdict(int))
    series = defaultdict(lambda: defaultdict(lambda: {'doubles': 0, 'msgs': 0}))

    # Per-month message counts (denominator for the monthly rate).
    for s in sess:
        for m in s:
            sender = m.get('sender_name', 'Unknown')
            if sender in real_counts:
                series[_month(m.get('timestamp_ms', 0), timezone)][sender]['msgs'] += 1

    total_doubles = 0
    for s in sess:
        i = 0
        while i < len(s):
            sender = s[i].get('sender_name', 'Unknown')
            j = i
            while j + 1 < len(s) and s[j + 1].get('sender_name') == sender:
                j += 1
            run = s[i:j + 1]
            length = len(run)
            if length >= 2:
                histogram[sender][_streak_key(length)] += 1
                max_streak[sender] = max(max_streak[sender], length)
                for k in range(1, length):
                    gap = run[k].get('timestamp_ms', 0) - run[k - 1].get('timestamp_ms', 0)
                    if gap >= DOUBLE_TEXT_GAP_MS:
                        double_texts[sender] += 1
                        total_doubles += 1
                        bucket = _month(run[k].get('timestamp_ms', 0), timezone)
                        if sender in real_counts:
                            series[bucket][sender]['doubles'] += 1
            i = j + 1

    per_user = {}
    for u in users:
        msgs = real_counts.get(u, 0)
        per_user[u] = {
            'double_texts': double_texts[u],
            'double_text_rate': round(double_texts[u] / msgs * 100, 2) if msgs else 0.0,
            'max_unanswered_streak': max_streak[u],
            'streak_histogram': dict(histogram[u]),
        }

    series_out = {}
    for bucket, ud in series.items():
        series_out[bucket] = {
            u: {'double_text_rate': round(v['doubles'] / v['msgs'] * 100, 2) if v['msgs'] else 0.0}
            for u, v in ud.items()
        }

    return {'per_user': per_user, 'series': series_out, 'n': total_doubles}


# --------------------------------------------------------------------------- #
# M11 - Conversation half-life
# --------------------------------------------------------------------------- #

def half_life_metrics(messages: List[Dict], users: List[str],
                      sessions: Optional[List[Dict]] = None,
                      timezone: str = DEFAULT_TIMEZONE) -> Dict[str, Any]:
    """Momentum loss per session: who was the last to hold it, and when it died."""
    template = {'sessions_last_held': 0, 'momentum_kill_share': 0.0}
    sess = _session_msg_lists(messages, sessions)
    user_set = set(users)
    analyzed = [s for s in sess if len(s) >= 6]
    if not analyzed:
        return _empty(users, template, median_half_life_minutes=0.0)

    last_held = defaultdict(int)
    kills = defaultdict(int)
    half_lives = []
    series = defaultdict(lambda: defaultdict(lambda: {'kills': 0, 'sessions': 0}))

    for s in analyzed:
        ts = [m.get('timestamp_ms', 0) for m in s]
        intervals = [(ts[k] - ts[k - 1]) for k in range(1, len(ts))]
        sess_median = median(intervals) if intervals else 0
        # Floor the death-gap: in rapid-fire chats the median interval is a few
        # seconds, so a bare 3x-median threshold trips within seconds and makes
        # the half-life degenerate. A pause under 5 min is not a dead chat.
        threshold = max(3 * sess_median, HALF_LIFE_MIN_GAP_MS)

        half = len(intervals) // 2
        first_med = median(intervals[:half]) if intervals[:half] else 0
        second_med = median(intervals[half:]) if intervals[half:] else 0
        momentum_lost = second_med > 3 * first_med if first_med > 0 else False

        # First gap exceeding 3x the session median => the message before it is
        # the "last holder"; the elapsed time to it is the half-life.
        holder_idx = len(s) - 1
        half_life_ms = ts[-1] - ts[0]
        for k, gap in enumerate(intervals):
            if threshold > 0 and gap > threshold:
                holder_idx = k
                half_life_ms = ts[k] - ts[0]
                break
        holder = s[holder_idx].get('sender_name', 'Unknown')
        half_lives.append(half_life_ms / 60000)

        bucket = _month(ts[0], timezone)
        for u in users:
            series[bucket][u]['sessions'] += 1
        if holder in user_set:
            last_held[holder] += 1
            if momentum_lost:
                kills[holder] += 1
                series[bucket][holder]['kills'] += 1

    n = len(analyzed)
    per_user = {
        u: {'sessions_last_held': last_held[u],
            'momentum_kill_share': round(kills[u] / n, 4) if n else 0.0}
        for u in users
    }

    series_out = {}
    for bucket, ud in series.items():
        series_out[bucket] = {
            u: {'kills': v['kills'], 'sessions': v['sessions'],
                'momentum_kill_share': round(v['kills'] / v['sessions'], 4) if v['sessions'] else 0.0}
            for u, v in ud.items()
        }

    return {'per_user': per_user, 'series': series_out, 'n': n,
            'median_half_life_minutes': _median(half_lives)}


# --------------------------------------------------------------------------- #
# M14 - Change-point timeline (composite)
# --------------------------------------------------------------------------- #

def _zscore(series: List[float]) -> List[float]:
    """Robust z-score: median/MAD-scaled, falling back to mean/std.

    Plain mean/std z-scores are masked by the very shifts we want to detect
    (a 6000-message week inflates the std so much that its own z stays small).
    MAD resists that; when MAD is 0 (e.g. zero-filled sparse series) fall back
    to the classic z-score.
    """
    n = len(series)
    if n == 0:
        return []
    med = float(median(series))
    mad = float(median([abs(x - med) for x in series]))
    if mad > 0:
        scale = 1.4826 * mad
        return [(x - med) / scale for x in series]
    mean = sum(series) / n
    var = sum((x - mean) ** 2 for x in series) / n
    std = var ** 0.5
    if std == 0:
        return [0.0] * n
    return [(x - mean) / std for x in series]


def _cusum(z: List[float], drift: float = 0.25,
           threshold: float = 3.0) -> List[Dict[str, Any]]:
    """Two-sided CUSUM change-point detection over a z-scored series."""
    sp = sm = 0.0
    out = []
    for i, x in enumerate(z):
        sp = max(0.0, sp + x - drift)
        sm = min(0.0, sm + x + drift)
        if sp > threshold:
            out.append({'index': i, 'direction': 'up', 'magnitude': round(sp, 4)})
            sp = sm = 0.0
        elif sm < -threshold:
            out.append({'index': i, 'direction': 'down', 'magnitude': round(-sm, 4)})
            sp = sm = 0.0
    return out


def change_point_metrics(messages: List[Dict], users: List[str],
                         sessions: Optional[List[Dict]] = None,
                         timezone: str = DEFAULT_TIMEZONE) -> Dict[str, Any]:
    """Joint CUSUM change-point detection over weekly core series.

    Output shape (differs from the standard contract)::

        {
          'change_points': [
            {'week': 'YYYY-Www', 'date': 'YYYY-MM-DD',   # ISO week start (Monday)
             'signals': [{'metric': str, 'direction': 'up'|'down',
                          'magnitude': float}, ...]},
          ],
          'weekly_series': {metric_name: {week: value}},
          'n': weeks_count,
        }
    """
    real = _sorted_real(messages)
    sess = _session_msg_lists(messages, sessions)
    top2 = _top2(real, users)
    user_a = top2[0] if top2 else None

    # Collect the set of ISO weeks that appear, sorted.
    def week_key(ts_ms):
        iso = to_datetime(ts_ms, timezone).isocalendar()
        return (iso[0], iso[1])

    week_set = set(week_key(m.get('timestamp_ms', 0)) for m in real)
    if len(week_set) < 3:
        return {'change_points': [], 'weekly_series': {}, 'n': len(week_set)}

    # Continuous ISO-week calendar from first to last active week: a silent
    # week is a real 0-volume data point (silence IS the signal), not a gap to
    # be compressed away.
    from datetime import timedelta
    first_wk, last_wk = min(week_set), max(week_set)
    cursor = datetime.fromisocalendar(first_wk[0], first_wk[1], 1)
    last_day = datetime.fromisocalendar(last_wk[0], last_wk[1], 1)
    weeks = []
    while cursor <= last_day:
        iso = cursor.isocalendar()
        weeks.append((iso[0], iso[1]))
        cursor += timedelta(weeks=1)
    week_index = {w: i for i, w in enumerate(weeks)}
    week_label = {w: f'{w[0]}-W{w[1]:02d}' for w in weeks}

    # --- Build the five weekly series -------------------------------------- #
    volume = [0] * len(weeks)
    night = [0] * len(weeks)
    affect_num = [0] * len(weeks)   # reactions + emoji
    for m in real:
        wi = week_index[week_key(m.get('timestamp_ms', 0))]
        volume[wi] += 1
        dt = to_datetime(m.get('timestamp_ms', 0), timezone)
        if dt.hour in NIGHT_HOURS:
            night[wi] += 1
        affect_num[wi] += len(EMOJI_PATTERN.findall(m.get('content', '') or ''))
    for m in messages:
        wk = week_key(m.get('timestamp_ms', 0))
        if wk in week_index:
            affect_num[week_index[wk]] += len(m.get('reactions') or [])

    # Ratio metrics are meaningless on near-silent weeks (one 2am message makes
    # night_share = 1.0); below this volume a week contributes a neutral value.
    MIN_RATIO_WEEK_VOLUME = 15

    def _neutral_fill(vals):
        """Replace silent/low-volume-week Nones with the median of active weeks
        so the zero-filled calendar can't fabricate shifts in ratio metrics."""
        active = [v for v in vals if v is not None]
        neutral = float(median(active)) if active else 0.0
        return [neutral if v is None else v for v in vals]

    def _gated(i):
        return volume[i] >= MIN_RATIO_WEEK_VOLUME

    night_share = _neutral_fill(
        [night[i] / volume[i] if _gated(i) else None for i in range(len(weeks))])
    affect_rate = _neutral_fill(
        [affect_num[i] / volume[i] if _gated(i) else None for i in range(len(weeks))])

    # Initiation share of user A + in-session median response latency (minutes).
    init_a = [0] * len(weeks)
    init_total = [0] * len(weeks)
    latencies = defaultdict(list)
    for s in sess:
        wk = week_key(s[0].get('timestamp_ms', 0))
        if wk in week_index:
            wi = week_index[wk]
            init_total[wi] += 1
            if s[0].get('sender_name') == user_a:
                init_a[wi] += 1
        for k in range(1, len(s)):
            if s[k].get('sender_name') != s[k - 1].get('sender_name'):
                gap_min = (s[k].get('timestamp_ms', 0) - s[k - 1].get('timestamp_ms', 0)) / 60000
                wk2 = week_key(s[k].get('timestamp_ms', 0))
                if wk2 in week_index:
                    latencies[week_index[wk2]].append(gap_min)

    initiation_share = _neutral_fill(
        [init_a[i] / init_total[i] if init_total[i] and _gated(i) else None
         for i in range(len(weeks))])
    response_latency = _neutral_fill(
        [float(median(latencies[i])) if latencies[i] and _gated(i) else None
         for i in range(len(weeks))])

    metric_series = {
        'volume': volume,
        'initiation_share': initiation_share,
        'response_latency': response_latency,
        'affect_rate': affect_rate,
        'night_share': night_share,
    }

    # --- CUSUM per metric, collect signals --------------------------------- #
    all_signals = []
    for name, ser in metric_series.items():
        for cp in _cusum(_zscore([float(x) for x in ser])):
            all_signals.append({'index': cp['index'], 'metric': name,
                                'direction': cp['direction'],
                                'magnitude': cp['magnitude']})

    all_signals.sort(key=lambda c: c['index'])

    # --- Merge signals within 2 weeks of each other into one event --------- #
    events = []
    for sig in all_signals:
        if events and sig['index'] - events[-1]['_last'] <= 2:
            events[-1]['signals'].append({'metric': sig['metric'],
                                          'direction': sig['direction'],
                                          'magnitude': sig['magnitude']})
            events[-1]['_last'] = sig['index']
        else:
            events.append({'_index': sig['index'], '_last': sig['index'],
                           'signals': [{'metric': sig['metric'],
                                        'direction': sig['direction'],
                                        'magnitude': sig['magnitude']}]})

    change_points = []
    for ev in events:
        w = weeks[ev['_index']]
        try:
            monday = datetime.fromisocalendar(w[0], w[1], 1).strftime('%Y-%m-%d')
        except ValueError:
            monday = None
        # Dedupe repeated firings of the same (metric, direction) within one
        # merged event, keeping the strongest magnitude.
        best = {}
        for s in ev['signals']:
            key = (s['metric'], s['direction'])
            if key not in best or s['magnitude'] > best[key]['magnitude']:
                best[key] = s
        change_points.append({
            'week': week_label[w],
            'date': monday,
            'signals': sorted(best.values(), key=lambda s: -s['magnitude']),
        })

    weekly_series = {
        name: {week_label[weeks[i]]: round(float(ser[i]), 4) for i in range(len(weeks))}
        for name, ser in metric_series.items()
    }

    return {'change_points': change_points, 'weekly_series': weekly_series,
            'n': len(weeks)}
