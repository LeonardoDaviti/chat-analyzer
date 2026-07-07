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
# Psycholinguistic lexicons (EN + Georgian + common romanized Georgian).
# Single-token entries only; tokens are lowercased and punctuation-stripped
# before lookup. These are deliberately small, high-precision lists — the
# metrics they feed (we-ness, positivity balance, courtesy) are rate-based,
# so precision matters more than recall.
# --------------------------------------------------------------------------- #

LEX_WE = {'we', 'us', 'our', 'ours', 'ourselves',
          'ჩვენ', 'ჩვენი', 'ჩვენს', 'ჩვენც', 'ჩვენთვის', 'ჩვენთან', 'ერთად',
          'chven', 'chveni', 'ertad'}
LEX_I = {'i', 'me', 'my', 'mine', 'myself', 'im', "i'm",
         'მე', 'ჩემი', 'ჩემს', 'ჩემთვის', 'ჩემთან', 'მეც', 'me', 'chemi'}
LEX_YOU = {'you', 'your', 'yours', 'yourself', 'u', 'ur',
           'შენ', 'შენი', 'შენს', 'შენც', 'შენთვის', 'შენთან', 'shen', 'sheni'}
LEX_POS = {'love', 'loved', 'great', 'awesome', 'amazing', 'happy', 'glad',
           'beautiful', 'cute', 'sweet', 'perfect', 'wonderful', 'nice',
           'best', 'excited', 'fun', 'funny', 'cool', 'lovely', 'adorable',
           'enjoy', 'proud', 'yay', 'wow',
           'მიყვარხარ', 'კარგი', 'კარგია', 'მაგარი', 'მაგარია', 'სუპერ',
           'საყვარელი', 'ლამაზი', 'ლამაზო', 'ბედნიერი', 'სიყვარული',
           'მომწონს', 'მიხარია', 'მშვენიერი', 'ჯიგარი', 'საოცარია',
           'გემრიელი', 'სასწაულია',
           'magaria', 'kargia', 'mikvarxar', 'miyvarxar', 'lamazi'}
LEX_NEG = {'hate', 'sad', 'angry', 'mad', 'annoyed', 'annoying', 'awful',
           'terrible', 'horrible', 'worst', 'cry', 'crying', 'upset',
           'scared', 'afraid', 'anxious', 'stress', 'stressed', 'hurt',
           'pain', 'lonely', 'sick', 'depressed', 'ugh',
           'ცუდი', 'ცუდია', 'ცუდად', 'საშინელი', 'საშინელება', 'მეზიზღება',
           'მძულს', 'ბრაზი', 'გავბრაზდი', 'ვნერვიულობ', 'ნერვები', 'სევდა',
           'მოწყენილი', 'ვტირი', 'ტირილი', 'პრობლემა', 'ჩხუბი', 'დაღლილი',
           'მეშინია', 'შემეშინდა', 'ცუდადაა',
           'cudi', 'cudad', 'problema'}
LEX_GRATITUDE = {'thanks', 'thank', 'thx', 'ty', 'thankyou',
                 'მადლობა', 'მადლობთ', 'მადლობები', 'მერსი',
                 'madloba', 'mersi'}
LEX_APOLOGY = {'sorry', 'apologies', 'apologize', 'sry',
               'ბოდიში', 'ბოდიშით', 'უკაცრავად', 'მაპატიე', 'მაპატიო',
               'bodishi', 'mapatie', 'ukacravad'}

# Simplified Language-Style-Matching categories (function words; Ireland &
# Pennebaker). Matching on function words — not content — is what makes LSM a
# rapport measure rather than a topic-overlap measure.
LSM_CATEGORIES = {
    'pronouns': LEX_I | LEX_YOU | LEX_WE | {'he', 'she', 'it', 'they', 'them',
        'his', 'her', 'their', 'ის', 'იმან', 'მან', 'ისინი', 'მისი', 'მათი'},
    'conjunctions': {'and', 'but', 'or', 'so', 'because', 'if', 'then',
        'და', 'მაგრამ', 'მარა', 'თუ', 'რომ', 'იმიტომ', 'იმიტორო', 'ანუ', 'თორე'},
    'negations': {'not', 'no', 'never', 'dont', "don't", 'cant', "can't",
        'wont', "won't", 'არ', 'არა', 'ვერ', 'ნუ', 'არც', 'ara', 'ar'},
    'questions': {'what', 'how', 'why', 'when', 'where', 'who',
        'რა', 'როგორ', 'რატომ', 'როდის', 'სად', 'ვინ', 'ra', 'rogor', 'ratom'},
    'affirmations': {'yes', 'yeah', 'yep', 'ok', 'okay', 'sure',
        'კი', 'ხო', 'კაი', 'ოკ', 'ჰო', 'აჰა', 'ki', 'xo', 'kai', 'ho', 'aha'},
}

_TOKEN_CLEAN = re.compile(r'[^\wႠ-ჿ]')


def _tokens(content: str) -> List[str]:
    """Lowercased, punctuation-stripped tokens (empty strings dropped)."""
    out = []
    for raw in content.lower().split():
        t = _TOKEN_CLEAN.sub('', raw)
        if t:
            out.append(t)
    return out


# --------------------------------------------------------------------------- #
# Daily aggregate table
# --------------------------------------------------------------------------- #

def _blank_day() -> Dict[str, Any]:
    return {
        'msgs': 0, 'words': 0, 'chars': 0, 'emoji': 0, 'questions': 0,
        'night_msgs': 0, 'reactions_given': 0, 'reactions_received': 0,
        'media': 0, 'photos': 0, 'videos': 0, 'voice': 0, 'shares': 0,
        'hours': [0] * 24,
        'resp_lat_sum_min': 0.0, 'resp_lat_n': 0, 'initiations': 0,
        # "turns": consecutive-message runs started this day. A turn ends when
        # the OTHER person interjects or a session gap passes. msgs/turns =
        # average monologue length; words/turns = words per complete thought.
        'turns': 0,
        # turns that got a partner follow-up within the session (the rest
        # "talked into the void" — they ended the session unanswered)
        'turns_answered': 0,
        # session-ending dynamics
        'endings': 0,        # sessions where this user had the final word
        'self_restarts': 0,  # opened a session although THEIR last message was
                             # the one that ended the previous session (re-knock
                             # without ever getting a reply)
        'reacted_leave': 0,  # reacted to the partner's session-final message
                             # instead of replying ("left on reacted")
        # waiting eagerness: after >=1h of waiting for a reply, how fast this
        # user answers once the partner's reply finally lands
        'wait_reply_sum_min': 0.0, 'wait_reply_n': 0,
        # psycholinguistic lexicon counters (token matches)
        'we_words': 0, 'i_words': 0, 'you_words': 0,
        'pos_words': 0, 'neg_words': 0,
        'gratitude': 0, 'apology': 0,
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
        for t in _tokens(content):
            if t in LEX_WE: c['we_words'] += 1
            elif t in LEX_I: c['i_words'] += 1
            elif t in LEX_YOU: c['you_words'] += 1
            if t in LEX_POS: c['pos_words'] += 1
            elif t in LEX_NEG: c['neg_words'] += 1
            if t in LEX_GRATITUDE: c['gratitude'] += 1
            elif t in LEX_APOLOGY: c['apology'] += 1
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
            c = cell(date, receiver)
            c['media'] += media
            # per-kind breakdown
            for field, key in (('photos', 'photos'), ('videos', 'videos'),
                               ('audio_files', 'voice')):
                val = m.get(field)
                if isinstance(val, list):
                    c[key] += len(val)
                elif val:
                    c[key] += 1
            if m.get('share'):
                c['shares'] += 1

    # --- Session-derived channels (initiations + reply latency) ------------ #
    real = [m for m in messages
            if is_real_message(m) and m.get('sender_name') in user_set]
    real.sort(key=lambda m: m.get('timestamp_ms', 0))
    def _day(msg):
        return to_datetime(msg.get('timestamp_ms', 0), timezone).strftime('%Y-%m-%d')

    sessions = _split_sessions(real)
    for si, session in enumerate(sessions):
        opener = session[0]
        o_sender = opener.get('sender_name', 'Unknown')
        if o_sender in user_set:
            cell(_day(opener), o_sender)['initiations'] += 1

        # Turns: a new run starts at the session opening and on every speaker
        # change; attributed to the day of its first message. Every turn except
        # the session's last one was followed by the partner (= answered).
        run_starts = []  # (sender, first_msg)
        prev_sender = None
        for msg in session:
            sender = msg.get('sender_name', 'Unknown')
            if sender != prev_sender:
                run_starts.append((sender, msg))
                prev_sender = sender
        for ri, (sender, first_msg) in enumerate(run_starts):
            if sender not in user_set:
                continue
            c = cell(_day(first_msg), sender)
            c['turns'] += 1
            if ri < len(run_starts) - 1:
                c['turns_answered'] += 1

        # Endings: the final-word holder of this session.
        last = session[-1]
        l_sender = last.get('sender_name', 'Unknown')
        if l_sender in user_set:
            cell(_day(last), l_sender)['endings'] += 1

        # "Left on reacted": the partner reacted to the session-final message
        # instead of replying with text.
        for r in (last.get('reactions') or []):
            actor = decode_georgian_text(r.get('actor', '') or '')
            if actor in user_set and actor != l_sender:
                cell(_day(last), actor)['reacted_leave'] += 1

        # Self-restart (re-knock): this session's opener also had the final
        # word of the PREVIOUS session — they restarted without ever getting
        # a reply.
        if si > 0:
            prev_last = sessions[si - 1][-1].get('sender_name', 'Unknown')
            if o_sender in user_set and o_sender == prev_last:
                cell(_day(opener), o_sender)['self_restarts'] += 1

        # In-session reply latency.
        for k in range(1, len(session)):
            cur, prev = session[k], session[k - 1]
            if cur.get('sender_name') == prev.get('sender_name'):
                continue  # same speaker: not a reply
            gap_ms = cur.get('timestamp_ms', 0) - prev.get('timestamp_ms', 0)
            if gap_ms < 0 or gap_ms > SESSION_GAP_MS:
                continue
            replier = cur.get('sender_name', 'Unknown')
            if replier in user_set:
                c = cell(_day(cur), replier)
                c['resp_lat_sum_min'] += gap_ms / 60000.0
                c['resp_lat_n'] += 1

    # --- Waiting eagerness (cross-session aware) ---------------------------- #
    # X sent a message, the partner's reply took >= 1h; how fast does X answer
    # that long-awaited reply? (Only follow-ups within a session gap count —
    # if X also vanished, nobody was waiting.)
    WAIT_MS = 60 * 60 * 1000
    for i in range(1, len(real) - 1):
        prev_m, cur_m, nxt_m = real[i - 1], real[i], real[i + 1]
        waiter = prev_m.get('sender_name', 'Unknown')
        if cur_m.get('sender_name') == waiter or nxt_m.get('sender_name') != waiter:
            continue
        wait_gap = cur_m.get('timestamp_ms', 0) - prev_m.get('timestamp_ms', 0)
        if wait_gap < WAIT_MS:
            continue
        follow = nxt_m.get('timestamp_ms', 0) - cur_m.get('timestamp_ms', 0)
        if follow < 0 or follow > SESSION_GAP_MS:
            continue
        if waiter in user_set:
            c = cell(_day(nxt_m), waiter)
            c['wait_reply_sum_min'] += follow / 60000.0
            c['wait_reply_n'] += 1

    # Round latency sums and freeze ordinary dicts.
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for date in sorted(daily):
        out[date] = {}
        for user, c in daily[date].items():
            c['resp_lat_sum_min'] = round(c['resp_lat_sum_min'], 2)
            c['wait_reply_sum_min'] = round(c['wait_reply_sum_min'], 2)
            out[date][user] = c
    return out


# --------------------------------------------------------------------------- #
# All-time extras: turn histogram, media reciprocity, basic NLP
# --------------------------------------------------------------------------- #

# Single-emoji matcher (EMOJI_PATTERN matches runs); modifiers excluded so a
# skin-toned emoji counts as its base glyph.
_EMOJI_ONE = re.compile(
    '[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E0-\U0001F1FF\U00002764]'
)
_EMOJI_SKIP = set('\U0000FE0F\U0001F3FB\U0001F3FC\U0001F3FD\U0001F3FE\U0001F3FF')

MEDIA_RECIP_WINDOW_MS = 30 * 60 * 1000


def build_extras(messages: List[Dict[str, Any]],
                 participants: List[str],
                 timezone: str = DEFAULT_TIMEZONE) -> Dict[str, Any]:
    """All-time per-user extras: turn-length histogram, media reciprocity and
    a basic-NLP block (top emojis / words / distinctive vocabulary)."""
    from src.word_frequency import extract_words

    user_set = set(participants)
    real = [m for m in messages
            if is_real_message(m) and m.get('sender_name') in user_set]
    real.sort(key=lambda m: m.get('timestamp_ms', 0))

    # ---- turn-length histogram (1..9, '10+') ------------------------------- #
    turn_hist: Dict[str, Counter] = {u: Counter() for u in participants}
    for session in _split_sessions(real):
        run_sender, run_len = None, 0
        for msg in session + [None]:
            sender = msg.get('sender_name') if msg else None
            if sender == run_sender:
                run_len += 1
                continue
            if run_sender in user_set and run_len:
                key = '10+' if run_len >= 10 else str(run_len)
                turn_hist[run_sender][key] += 1
            run_sender, run_len = sender, 1

    # ---- media reciprocity -------------------------------------------------- #
    media_all = [m for m in messages if m.get('sender_name') in user_set]
    media_all.sort(key=lambda m: m.get('timestamp_ms', 0))
    recip = {u: {'media_sent': 0, 'media_reciprocated': 0} for u in participants}
    media_idx = [i for i, m in enumerate(media_all) if _media_count(m)]
    for pos, i in enumerate(media_idx):
        m = media_all[i]
        sender = m.get('sender_name')
        recip[sender]['media_sent'] += 1
        ts = m.get('timestamp_ms', 0)
        for j in media_idx[pos + 1:]:
            m2 = media_all[j]
            gap = m2.get('timestamp_ms', 0) - ts
            if gap > MEDIA_RECIP_WINDOW_MS:
                break
            if m2.get('sender_name') != sender:
                recip[sender]['media_reciprocated'] += 1
                break

    # ---- basic NLP ----------------------------------------------------------#
    words: Dict[str, Counter] = {u: Counter() for u in participants}
    emojis: Dict[str, Counter] = {u: Counter() for u in participants}
    word_totals = {u: 0 for u in participants}
    # monthly blocks (client merges the months inside the active range so the
    # Language section follows the global time filter)
    m_words: Dict[str, Dict[str, Counter]] = defaultdict(lambda: {u: Counter() for u in participants})
    m_emojis: Dict[str, Dict[str, Counter]] = defaultdict(lambda: {u: Counter() for u in participants})
    m_uniq_total: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: {u: [0, 0] for u in participants})
    m_lsm_counts: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
        lambda: {u: {cat: 0 for cat in LSM_CATEGORIES} for u in participants})
    m_lsm_tokens: Dict[str, Dict[str, int]] = defaultdict(lambda: {u: 0 for u in participants})

    for m in real:
        u = m.get('sender_name')
        content = m.get('content', '') or ''
        month = to_datetime(m.get('timestamp_ms', 0), timezone).strftime('%Y-%m')
        ws = extract_words(content)
        words[u].update(ws)
        m_words[month][u].update(ws)
        word_totals[u] += len(content.split())
        for ch in _EMOJI_ONE.findall(content):
            if ch not in _EMOJI_SKIP:
                emojis[u][ch] += 1
                m_emojis[month][u][ch] += 1
        toks = _tokens(content)
        m_lsm_tokens[month][u] += len(toks)
        for t in toks:
            for cat, lex in LSM_CATEGORIES.items():
                if t in lex:
                    m_lsm_counts[month][u][cat] += 1

    # per-month vocabulary richness (TTR is only meaningful within a window)
    for month, per_u in m_words.items():
        for u in participants:
            cnt = per_u[u]
            m_uniq_total[month][u] = [len(cnt), sum(cnt.values())]

    # ---- monthly LSM (Language Style Matching, simplified) ----------------- #
    MIN_LSM_TOKENS = 150  # both people need real volume for LSM to mean anything
    lsm_monthly: Dict[str, Optional[float]] = {}
    if len(participants) >= 2:
        pa, pb = participants[0], participants[1]
        for month in sorted(m_lsm_tokens):
            ta, tb = m_lsm_tokens[month][pa], m_lsm_tokens[month][pb]
            if ta < MIN_LSM_TOKENS or tb < MIN_LSM_TOKENS:
                lsm_monthly[month] = None
                continue
            sims = []
            for cat in LSM_CATEGORIES:
                ra = m_lsm_counts[month][pa][cat] / ta
                rb = m_lsm_counts[month][pb][cat] / tb
                sims.append(1 - abs(ra - rb) / (ra + rb + 1e-4))
            lsm_monthly[month] = round(sum(sims) / len(sims), 4)

    # distinctive vocabulary: log-odds with +1 smoothing, min combined count 5
    import math
    nlp = {}
    a = participants[0]
    b = participants[1] if len(participants) > 1 else None
    tot_a = sum(words[a].values()) or 1
    tot_b = (sum(words[b].values()) or 1) if b else 1
    for u, other, tu, to in ((a, b, tot_a, tot_b), (b, a, tot_b, tot_a)):
        if u is None:
            continue
        distinctive = []
        if other is not None:
            for w, cu in words[u].items():
                co = words[other].get(w, 0)
                if cu + co < 5:
                    continue
                score = math.log((cu + 1) / (tu - cu + 1)) - math.log((co + 1) / (to - co + 1))
                if score > 0:
                    distinctive.append((w, round(score, 3), cu))
            distinctive.sort(key=lambda x: -x[1])
        uniq = len(words[u])
        total_w = sum(words[u].values())
        nlp[u] = {
            'top_words': words[u].most_common(25),
            'top_emojis': emojis[u].most_common(15),
            'distinctive': [[w, c] for w, _, c in distinctive[:12]],
            'unique_words': uniq,
            'total_words': word_totals[u],
            'ttr': round(uniq / total_w, 4) if total_w else 0.0,
        }

    nlp_monthly = {}
    for month in sorted(m_words):
        nlp_monthly[month] = {}
        for u in participants:
            nlp_monthly[month][u] = {
                'words': m_words[month][u].most_common(60),
                'emojis': m_emojis[month][u].most_common(20),
                'uniq': m_uniq_total[month][u][0],
                'total': m_uniq_total[month][u][1],
            }

    return {
        'turn_hist': {u: dict(turn_hist[u]) for u in participants},
        'media_recip': recip,
        'nlp': nlp,
        'nlp_monthly': nlp_monthly,
        'lsm_monthly': lsm_monthly,
    }


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
        'extras': build_extras(messages, participants, timezone),
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
