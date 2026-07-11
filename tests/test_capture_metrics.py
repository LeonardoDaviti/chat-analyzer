"""M3.1 capture-layer surfacing tests — synthetic fixtures only.

Covers the export blocks (calls, voice notes, stickers, reaction latency,
signature emoji, edit latency), the connected reaction-latency leaderboards,
and the six new insight rules (trigger + gate). No real content or names.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dashboard_export import (  # noqa: E402
    build_call_stats, build_telegram_signals, build_daily_aggregates,
)
from src.connected_export import (  # noqa: E402
    reduce_message, Chat, build_connected_data,
)
from src.insights_engine import run_chat, _SUM_FIELDS  # noqa: E402

TZ = 'Asia/Tbilisi'
BASE = 1_700_000_000_000
SEC = 1000
MIN = 60 * SEC
A, B = 'A', 'B'


def cmsg(ts, sender, dur=None, reason=None):
    m = {'sender_name': sender, 'timestamp_ms': ts, 'content': '',
         'language': 'media', 'type': 'call'}
    if dur is not None:
        m['call_duration_s'] = dur
    if reason is not None:
        m['call_discard_reason'] = reason
    return m


# --------------------------------------------------------------------------- #
# Calls (platform-neutral block + daily counters)
# --------------------------------------------------------------------------- #

def test_call_stats_totals_and_outcomes():
    msgs = [
        cmsg(BASE, A, dur=120, reason='hangup'),
        cmsg(BASE + MIN, A, dur=0, reason='missed'),
        cmsg(BASE + 2 * MIN, B, dur=300, reason='hangup'),
        cmsg(BASE + 3 * MIN, B, dur=0, reason='busy'),
    ]
    cs = build_call_stats(msgs, [A, B])
    assert cs['total_calls'] == 4
    assert cs['answered'] == 2
    assert cs['missed'] == 2
    assert cs['total_talk_s'] == 420
    assert cs['median_talk_s'] == 210  # median of [120, 300]
    assert cs['outcomes'] == {'hangup': 2, 'missed': 1, 'busy': 1}
    assert cs['attribution'] == 'initiator'
    assert cs['per_user'][A]['calls'] == 2
    assert cs['per_user'][A]['answered'] == 1
    assert cs['per_user'][B]['median_s'] == 300


def test_call_stats_none_when_no_calls():
    msgs = [{'sender_name': A, 'timestamp_ms': BASE, 'content': 'hi',
             'language': 'english', 'type': 'text'}]
    assert build_call_stats(msgs, [A, B]) is None


def test_daily_table_carries_calls():
    msgs = [
        cmsg(BASE, A, dur=120, reason='hangup'),
        cmsg(BASE + MIN, A, dur=0, reason='missed'),
    ]
    daily = build_daily_aggregates(msgs, [A, B], TZ)
    tot = {'calls': 0, 'call_answered': 0, 'call_missed': 0, 'call_seconds': 0}
    for day in daily.values():
        for cell in day.values():
            for k in tot:
                tot[k] += cell.get(k, 0)
    assert tot == {'calls': 2, 'call_answered': 1, 'call_missed': 1,
                   'call_seconds': 120}


# --------------------------------------------------------------------------- #
# Telegram extras: voice / stickers / reaction latency / signature / edits
# --------------------------------------------------------------------------- #

def test_voice_notes_and_stickers_overlap():
    msgs = []
    for i in range(5):
        msgs.append({'sender_name': A, 'timestamp_ms': BASE + i, 'content': '',
                     'language': 'media', 'type': 'voice', 'media_duration_s': 10})
    for i in range(3):
        msgs.append({'sender_name': B, 'timestamp_ms': BASE + 100 + i, 'content': '',
                     'language': 'media', 'type': 'voice', 'media_duration_s': 40})
    # stickers: A uses {x,y,z}; B uses {y,z} → overlap = 2/min(3,2) = 1.0
    for e in ('x', 'y', 'z'):
        msgs.append({'sender_name': A, 'timestamp_ms': BASE + 200, 'content': '',
                     'language': 'media', 'type': 'sticker', 'sticker': {'emoji': e}})
    for e in ('y', 'z'):
        msgs.append({'sender_name': B, 'timestamp_ms': BASE + 300, 'content': '',
                     'language': 'media', 'type': 'sticker', 'sticker': {'emoji': e}})
    tg = build_telegram_signals(msgs, [A, B])
    assert tg['voice_notes'][A] == {'n': 5, 'median_s': 10, 'total_s': 50}
    assert tg['voice_notes'][B]['median_s'] == 40
    assert tg['stickers']['total'] == 5
    assert tg['stickers']['overlap'] == 1.0
    assert set(tg['stickers']['shared']) == {'y', 'z'}


def test_reaction_latency_and_signature_emoji():
    # A reacts to B's messages: 10s, 20s, 30s → median 20s, all ❤
    msgs = []
    for i, lat in enumerate((10, 20, 30)):
        ts = BASE + i * MIN
        msgs.append({'sender_name': B, 'timestamp_ms': ts, 'content': 'x',
                     'language': 'english', 'type': 'text',
                     'reactions': [{'reaction': '❤', 'actor': A,
                                    'date': ts + lat * SEC}]})
    # a stale reaction beyond the 7-day cap is dropped
    msgs.append({'sender_name': B, 'timestamp_ms': BASE, 'content': 'y',
                 'language': 'english', 'type': 'text',
                 'reactions': [{'reaction': '❤', 'actor': A,
                                'date': BASE + 8 * 24 * 60 * MIN}]})
    tg = build_telegram_signals(msgs, [A, B])
    rl = tg['reaction_latency'][A]
    assert rl['n'] == 3
    assert rl['median_s'] == 20
    sig = tg['signature_emoji'][A]
    assert sig['top'][0][0] == '❤'
    assert sig['concentration'] == 1.0


def test_edit_latency_buckets():
    msgs = [
        {'sender_name': A, 'timestamp_ms': BASE, 'content': 'a',
         'language': 'english', 'type': 'text', 'edited_ms': BASE + 30 * SEC},
        {'sender_name': A, 'timestamp_ms': BASE + MIN, 'content': 'b',
         'language': 'english', 'type': 'text',
         'edited_ms': BASE + MIN + 2 * 60 * 60 * SEC},  # >1h
    ]
    tg = build_telegram_signals(msgs, [A, B])
    el = tg['edit_latency'][A]
    assert el['n'] == 2
    assert el['buckets'].get('<1m') == 1
    assert el['buckets'].get('>1h') == 1


# --------------------------------------------------------------------------- #
# Connected reaction-latency leaderboards
# --------------------------------------------------------------------------- #

def test_reduce_message_carries_dated_reactions():
    r = reduce_message({'sender_name': B, 'timestamp_ms': BASE, 'content': 'x',
                        'language': 'english',
                        'reactions': [{'reaction': '❤', 'actor': A, 'date': BASE + 5000},
                                      {'reaction': '👍', 'actor': A}]}, TZ)
    assert r['rx'] == [[A, BASE + 5000]]  # undated reaction excluded


def _mkchat(cid, parts, raw, platform='telegram'):
    c = Chat.__new__(Chat)
    c.chat_id = cid
    c.name = cid
    c.participants = parts
    c.is_group = False
    c.recs = sorted((reduce_message(m, TZ) for m in raw),
                    key=lambda r: r['timestamp_ms'])
    c.thread_path = ''
    c.platform = platform
    return c


def test_connected_reaction_latency_leaderboards():
    owner = 'Owner'
    raw = []
    # Owner reacts to contact's messages fast (5s); contact reacts to owner slow.
    for i in range(40):
        ts = BASE + i * MIN
        raw.append({'sender_name': 'Contact', 'timestamp_ms': ts, 'content': 'hi there',
                    'language': 'english',
                    'reactions': [{'reaction': '❤', 'actor': owner, 'date': ts + 5 * SEC}]})
        ts2 = ts + 30 * SEC
        raw.append({'sender_name': owner, 'timestamp_ms': ts2, 'content': 'hello friend',
                    'language': 'english',
                    'reactions': [{'reaction': '👍', 'actor': 'Contact',
                                   'date': ts2 + 20 * MIN}]})
    chat = _mkchat('c', [owner, 'Contact'], raw)
    p = build_connected_data([chat], owner, TZ, min_msgs=0, min_replies=0)
    lb = p['leaderboards']
    you = lb['react_latency_you']
    them = lb['react_latency_them']
    assert you and you[0]['react_n'] == 40
    assert you[0]['react_median_min'] < 1        # ~5s
    assert them and them[0]['react_median_min'] > 10  # ~20min


def test_connected_reaction_latency_gated_below_30():
    owner = 'Owner'
    raw = []
    for i in range(10):  # below the 30-reaction gate
        ts = BASE + i * MIN
        raw.append({'sender_name': 'Contact', 'timestamp_ms': ts, 'content': 'hi there',
                    'language': 'english',
                    'reactions': [{'reaction': '❤', 'actor': owner, 'date': ts + 5 * SEC}]})
    chat = _mkchat('c', [owner, 'Contact'], raw)
    p = build_connected_data([chat], owner, TZ, min_msgs=0, min_replies=0)
    assert p['leaderboards']['react_latency_you'] == []


# --------------------------------------------------------------------------- #
# Insight rules (trigger + gate)
# --------------------------------------------------------------------------- #

OWNER = 'B'
PARTNER = 'A'


def _cell(**kw):
    c = {f: 0 for f in _SUM_FIELDS}
    c['hours'] = [0] * 24
    c.update(kw)
    return c


def _daily(n_months=12, msgs_each=50):
    daily = {}
    y, m = 2024, 1
    for _ in range(n_months):
        d = f'{y:04d}-{m:02d}-15'
        daily[d] = {PARTNER: _cell(msgs=msgs_each, words=msgs_each * 5,
                                   initiations=5, turns=msgs_each),
                    OWNER: _cell(msgs=msgs_each, words=msgs_each * 5,
                                 initiations=5, turns=msgs_each)}
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return daily


def _payload(telegram=None, calls=None):
    p = {'name': 't', 'platform': 'telegram', 'is_group': False,
         'participants': [PARTNER, OWNER], 'daily': _daily(),
         'lifetime': {}, 'extras': {}, 'telegram': telegram, 'change_points': []}
    if calls is not None:
        p['calls'] = calls
    return p


def _ids(p):
    return {f['id'] for f in run_chat('t', p, OWNER)}


def test_rule_call_habit_fires_and_gates():
    calls = {'per_user': {}, 'total_calls': 40, 'answered': 25, 'missed': 15,
             'total_talk_s': 7200, 'median_talk_s': 240, 'outcomes': {}}
    assert 'call-habit' in _ids(_payload(calls=calls))
    # gate: too little talk time
    calls_low = dict(calls, total_talk_s=600)
    assert 'call-habit' not in _ids(_payload(calls=calls_low))


def test_rule_voice_note_asymmetry_fires_and_gates():
    tg = {'voice_notes': {PARTNER: {'n': 60, 'median_s': 40, 'total_s': 2400},
                          OWNER: {'n': 10, 'median_s': 8, 'total_s': 80}}}
    assert 'voice-note-asymmetry' in _ids(_payload(telegram=tg))
    tg_sym = {'voice_notes': {PARTNER: {'n': 40, 'median_s': 20, 'total_s': 800},
                              OWNER: {'n': 35, 'median_s': 20, 'total_s': 700}}}
    assert 'voice-note-asymmetry' not in _ids(_payload(telegram=tg_sym))


def test_rule_fast_reactor_fires_and_gates():
    tg = {'reaction_latency': {PARTNER: {'n': 100, 'median_s': 15, 'buckets': {}},
                               OWNER: {'n': 100, 'median_s': 120, 'buckets': {}}}}
    assert 'fast-reactor' in _ids(_payload(telegram=tg))
    tg_close = {'reaction_latency': {PARTNER: {'n': 100, 'median_s': 90, 'buckets': {}},
                                     OWNER: {'n': 100, 'median_s': 120, 'buckets': {}}}}
    assert 'fast-reactor' not in _ids(_payload(telegram=tg_close))


def test_rule_signature_emoji_fires_and_gates():
    tg = {'signature_emoji': {PARTNER: {'n': 200, 'top': [['⚡', 180], ['❤', 20]],
                                        'concentration': 0.9},
                              OWNER: {'n': 200, 'top': [['❤', 60]], 'concentration': 0.3}}}
    assert 'signature-emoji' in _ids(_payload(telegram=tg))
    tg_low = {'signature_emoji': {PARTNER: {'n': 50, 'top': [['⚡', 45]],
                                            'concentration': 0.9}}}
    assert 'signature-emoji' not in _ids(_payload(telegram=tg_low))


def test_rule_edit_reconsideration_fires_and_gates():
    tg = {'edit_latency': {PARTNER: {'n': 400, 'median_s': 100,
                                     'buckets': {'<1m': 200, '>1h': 80}},
                           OWNER: {'n': 400, 'median_s': 20,
                                   'buckets': {'<1m': 380, '>1h': 5}}}}
    assert 'edit-reconsideration' in _ids(_payload(telegram=tg))
    tg_low = {'edit_latency': {PARTNER: {'n': 400, 'median_s': 20,
                                         'buckets': {'<1m': 390, '>1h': 8}}}}
    assert 'edit-reconsideration' not in _ids(_payload(telegram=tg_low))


def test_rule_sticker_vocabulary_high_and_gate():
    tg_high = {'stickers': {'total': 300, 'overlap': 0.7, 'shared': ['x', 'y']}}
    assert 'sticker-vocabulary' in _ids(_payload(telegram=tg_high))
    tg_low = {'stickers': {'total': 300, 'overlap': 0.08, 'shared': []}}
    assert 'sticker-vocabulary' in _ids(_payload(telegram=tg_low))
    tg_mid = {'stickers': {'total': 300, 'overlap': 0.4, 'shared': []}}
    assert 'sticker-vocabulary' not in _ids(_payload(telegram=tg_mid))
    tg_thin = {'stickers': {'total': 50, 'overlap': 0.7, 'shared': ['x']}}
    assert 'sticker-vocabulary' not in _ids(_payload(telegram=tg_thin))


def test_new_rules_absent_without_telegram_or_calls():
    ids = _ids(_payload())
    for rid in ('call-habit', 'voice-note-asymmetry', 'fast-reactor',
                'signature-emoji', 'edit-reconsideration', 'sticker-vocabulary'):
        assert rid not in ids
