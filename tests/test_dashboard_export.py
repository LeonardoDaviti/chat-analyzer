"""Tests for the dashboard exporter (Python side only; no browser)."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.dashboard_export import (
    build_daily_aggregates,
    choose_participants,
    build_chat_payload,
    build_lifetime,
    slugify,
    dump_data_js,
    dump_manifest_js,
)
from src.timeutil import DEFAULT_TIMEZONE

TZ = ZoneInfo(DEFAULT_TIMEZONE)


def _ts(y, mo, d, h, mi=0):
    """Epoch ms for a wall-clock time in the pipeline's default timezone."""
    return int(datetime(y, mo, d, h, mi, tzinfo=TZ).timestamp() * 1000)


def _msg(sender, ts, content='', **extra):
    m = {'sender_name': sender, 'timestamp_ms': ts, 'content': content,
         'language': 'english'}
    m.update(extra)
    return m


@pytest.fixture
def synthetic():
    """10 messages, 2 users, known dates/hours/reactions/questions."""
    A, B = 'Alice', 'Bob'
    msgs = [
        _msg(A, _ts(2026, 6, 1, 12, 0), 'hi',
             reactions=[{'reaction': 'x', 'actor': B}]),           # 1
        _msg(B, _ts(2026, 6, 1, 12, 1), "hey what's up?"),          # 2 question
        _msg(A, _ts(2026, 6, 1, 12, 5), 'not much \U0001F600'),     # 3 emoji=1
        _msg(B, _ts(2026, 6, 1, 12, 6), '', photos=[{'uri': 'p'}]), # 4 media, not real
        _msg(A, _ts(2026, 6, 1, 23, 30), 'late'),                   # 5 night
        _msg(B, _ts(2026, 6, 1, 23, 40), 'why so late?'),           # 6 question, night
        _msg(A, _ts(2026, 6, 2, 1, 0), 'cant sleep \U0001F600\U0001F600'),  # 7 night, emoji=2
        _msg(B, _ts(2026, 6, 2, 9, 0), 'morning',
             reactions=[{'reaction': 'y', 'actor': A}]),           # 8
        _msg(A, _ts(2026, 6, 2, 9, 2), 'gm ❤'),           # 9 emoji=1 (heart)
        _msg(B, _ts(2026, 6, 2, 9, 5), 'coffee?'),                  # 10 question
    ]
    return {'participants': [{'name': A}, {'name': B}], 'messages': msgs}


def _totals(daily, user):
    tot = {}
    for day in daily.values():
        cell = day.get(user)
        if not cell:
            continue
        for k, v in cell.items():
            if k == 'hours':
                continue
            tot[k] = tot.get(k, 0) + v
    return tot


def test_participants_by_volume(synthetic):
    parts = choose_participants(synthetic['messages'],
                                ['Alice', 'Bob'])
    assert parts == ['Alice', 'Bob']  # Alice has 5 real msgs, Bob 4


def test_daily_aggregate_counts(synthetic):
    daily = build_daily_aggregates(synthetic['messages'], ['Alice', 'Bob'])
    a = _totals(daily, 'Alice')
    b = _totals(daily, 'Bob')

    # message counts (real only)
    assert a['msgs'] == 5
    assert b['msgs'] == 4
    # questions
    assert a['questions'] == 0
    assert b['questions'] == 3
    # emoji (EMOJI_PATTERN uses a `+` run quantifier, so an adjacent pair is one
    # match — same convention as metrics_v4): msg3=1, msg7 (pair)=1, msg9=1 => 3
    assert a['emoji'] == 3
    assert b['emoji'] == 0
    # night messages (unified window 00:00–05:59): only 01:00 qualifies now;
    # 23:30 / 23:40 are no longer "night" (MONITORING_AUDIT §4/§5).
    assert a['night_msgs'] == 1  # 01:00
    assert b['night_msgs'] == 0  # 23:40 is no longer night
    # media (all messages)
    assert a['media'] == 0
    assert b['media'] == 1
    # reactions given/received
    assert b['reactions_given'] == 1 and a['reactions_received'] == 1
    assert a['reactions_given'] == 1 and b['reactions_received'] == 1
    # initiations (3 sessions: Alice, Alice, Bob)
    assert a['initiations'] == 2
    assert b['initiations'] == 1
    # in-session replies (sender switches): 3 for each
    assert a['resp_lat_n'] == 3
    assert b['resp_lat_n'] == 3
    # words
    assert a['words'] == 10
    assert b['words'] == 8


def test_hours_array(synthetic):
    daily = build_daily_aggregates(synthetic['messages'], ['Alice', 'Bob'])
    # Alice sent a message at 01:00 on 2026-06-02
    cell = daily['2026-06-02']['Alice']
    assert len(cell['hours']) == 24
    assert cell['hours'][1] == 1        # 01:00 message
    assert cell['hours'][9] == 1        # 09:02 message


def test_payload_shape(synthetic):
    analysis = {'message_counts': {'Alice': 5, 'Bob': 4},
                'final_word_dominance': {'Alice': 0.6, 'Bob': 0.4},
                'change_points': {'change_points': [
                    {'date': '2026-06-01', 'signals': [{'metric': 'volume'}]}]}}
    payload = build_chat_payload('Alice & Bob', synthetic, analysis)
    assert payload['name'] == 'Alice & Bob'
    assert payload['participants'] == ['Alice', 'Bob']
    assert '2026-06-01' in payload['daily']
    assert payload['change_points'][0]['date'] == '2026-06-01'
    assert payload['lifetime']['final_word_dominance']['Alice'] == 0.6


def test_lifetime_missing_keys_safe():
    lt = build_lifetime({})  # older analysis.json without V4 blocks
    assert lt['initiation'] == {}
    assert lt['circadian']['overlap_coefficient'] is None
    assert lt['half_life']['median_half_life_minutes'] is None


def test_slug_uniqueness():
    # Same ASCII name repeated: first keeps the clean base, further collisions get
    # a STABLE name-hash suffix (not an order-dependent counter).
    taken = set()
    s1 = slugify('Ann', taken)
    s2 = slugify('Ann', taken)
    s3 = slugify('Ann', taken)
    assert s1 == 'Ann'
    assert s2.startswith('Ann-')
    assert s3.startswith('Ann-')
    assert len({s1, s2, s3}) == 3


def test_slug_deterministic_order_independent():
    """The same name yields the same id regardless of processing order — this is
    what lets the per-chat and connected exporters agree on a chat's id
    (MONITORING_AUDIT §3.4). Non-ASCII (e.g. Georgian) titles are the key case:
    they no longer collapse to order-numbered ``chat``/``chat_2``/``chat_8``."""
    geo1 = 'გამოწერილი'  # some Georgian title
    geo2 = 'სელი'                                        # a different Georgian title
    # Exporter 1 processes geo1 then geo2; exporter 2 processes them reversed.
    t1 = set(); id1_a = slugify(geo1, t1); id1_b = slugify(geo2, t1)
    t2 = set(); id2_b = slugify(geo2, t2); id2_a = slugify(geo1, t2)
    assert id1_a == id2_a          # geo1 gets the same id in both orders
    assert id1_b == id2_b          # geo2 too
    assert id1_a != id1_b          # and the two titles never collide
    assert id1_a.startswith('chat-') and id1_b.startswith('chat-')


def test_slug_sanitizes_unsafe_chars():
    taken = set()
    slug = slugify('Ani \U0001F9DA‍♀️ / weird:name', taken)
    assert '/' not in slug and ':' not in slug and ' ' not in slug
    # only filesystem/JS-safe characters remain
    assert all(c.isalnum() or c in '._-' for c in slug)


def test_slug_empty_name():
    taken = set()
    assert slugify('\U0001F9DA', taken)  # non-ASCII-only -> falls back to 'chat'


def test_data_js_escapes_script():
    payload = {'name': 'x</script><script>alert(1)</script>', 'daily': {}}
    js = dump_data_js('demo', payload)
    assert '</script>' not in js
    assert '<\\/script' in js
    assert js.startswith('window.DASHBOARD_DATA')


def test_data_js_roundtrips():
    payload = {'name': 'Alice', 'participants': ['Alice', 'Bob'], 'daily': {}}
    js = dump_data_js('slugA', payload)
    # extract the JSON object (after the `["slugA"] = ` assignment) and re-parse
    start = js.index('] = ') + 4
    obj = json.loads(js[start:].rstrip().rstrip(';'))
    assert obj['name'] == 'Alice'


def test_manifest_js_content():
    manifest = [{'id': 'a', 'name': 'A</script>', 'file': 'data/a.js',
                 'messages': 100, 'first_date': '2026-01-01', 'last_date': '2026-02-01'}]
    js = dump_manifest_js(manifest)
    assert js.startswith('window.DASHBOARD_MANIFEST = ')
    assert '</script>' not in js
    start = js.index('= ') + 2
    parsed = json.loads(js[start:].rstrip().rstrip(';\n').rstrip(';'))
    assert parsed[0]['messages'] == 100
    assert parsed[0]['name'] == 'A</script>'  # decoded back from escaped form


# --------------------------------------------------------------------------- #
# MONITORING_AUDIT fixes: median latency, unified night window, calls label
# --------------------------------------------------------------------------- #

def test_reply_latency_p50_is_true_median_not_mean():
    """The daily cell ships resp_lat_p50_min = the TRUE per-day reply-latency
    median. On data whose mean and median differ wildly it must equal the median
    (and the honest lifetime median from response_time.py), NOT the pooled mean
    the chart used to draw under its "Median" title (MONITORING_AUDIT §3.1)."""
    A, B = 'Alice', 'Bob'
    base = _ts(2026, 6, 1, 8, 0)
    MIN = 60 * 1000
    # Alternating A/B; every A->B gap is a Bob reply. Nine 1-min replies + one
    # 110-min reply (still inside the 2h session gap) => median 1, mean ~11.9.
    mins = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 128]
    senders = [A, B] * 10
    msgs = [_msg(senders[i], base + mins[i] * MIN, 'm') for i in range(len(mins))]

    daily = build_daily_aggregates(msgs, [A, B])
    assert len(daily) == 1                       # all on one calendar day
    bob = next(iter(daily.values()))[B]
    assert bob['resp_lat_n'] == 10
    mean = bob['resp_lat_sum_min'] / bob['resp_lat_n']
    assert mean > 10                             # pooled mean ~11.9 min
    assert bob['resp_lat_p50_min'] == pytest.approx(1.0)   # true median = 1 min
    assert mean > 10 * bob['resp_lat_p50_min']   # mean and median differ wildly

    # The shipped p50 agrees with the honest lifetime median (response_time.py),
    # so the chart (per-bucket median) and the lifetime block match at full range.
    from src.response_time import calculate_response_times
    rt = calculate_response_times(msgs, B)
    assert bob['resp_lat_p50_min'] == pytest.approx(rt['my_median_response_minutes'])


def test_night_window_is_midnight_to_six():
    """Night = 00:00–05:59 everywhere now (MONITORING_AUDIT §4/§5). 03:00 counts;
    23:00 does not."""
    A, B = 'Alice', 'Bob'
    msgs = [
        _msg(A, _ts(2026, 6, 1, 3, 0), 'deep night'),    # 03:00 -> night
        _msg(A, _ts(2026, 6, 1, 5, 30), 'still night'),  # 05:30 -> night
        _msg(A, _ts(2026, 6, 1, 23, 0), 'evening'),      # 23:00 -> NOT night
        _msg(A, _ts(2026, 6, 1, 12, 0), 'noon'),         # noon -> NOT night
    ]
    tot = _totals(build_daily_aggregates(msgs, [A, B]), A)
    assert tot['night_msgs'] == 2                         # 03:00 + 05:30 only


def test_media_stats_answered_calls_label():
    """media_stats renames the answered-only count to ``answered_calls`` so no
    consumer mistakes it for the total call count (MONITORING_AUDIT §3.3)."""
    from src.media_analyzer import get_media_stats
    msgs = [
        {'sender_name': 'A', 'call_duration': 120},   # answered
        {'sender_name': 'A', 'call_duration': 0},     # missed -> NOT counted
        {'sender_name': 'A'},                          # not a call
    ]
    stats = get_media_stats(msgs)
    assert 'calls' not in stats['totals']              # misleading name is gone
    assert stats['totals']['answered_calls'] == 1      # answered-only, truthfully
    assert stats['by_sender']['A']['answered_calls'] == 1
