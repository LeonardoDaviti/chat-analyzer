"""Tests for Connected Analysis (src/connected_export.py).

All fixtures are synthetic — no real message content ever appears here.
Covers every metric family: merged-timeline attention (bursts / parallel /
chat-switch / fragmentation), session portfolio typing, contact leaderboards,
portfolio dynamics (Gini / churn), the new-contact funnel, and the groups lane.
"""

import pytest

from src.connected_export import (
    reduce_message, Chat, build_connected_data,
    classify_session, _gini, _split_sessions,
    dump_connected_js,
)

TZ = "Asia/Tbilisi"
OWNER = "Owner"
BASE = 1_700_000_000_000  # arbitrary epoch-ms anchor
MIN = 60 * 1000
HOUR = 60 * MIN


def msg(ts, sender, content="hi there friend", media=False, question=False):
    """Build a synthetic *normalized* message dict."""
    m = {"timestamp_ms": ts, "sender_name": sender}
    if media:
        m["photos"] = [{"uri": "x"}]
        m["content"] = ""
        m["language"] = "media"
        m["type"] = "photo"
    else:
        c = content + ("?" if question else "")
        m["content"] = c
        m["language"] = "english"
        m["type"] = "text"
    return m


def make_chat(chat_id, participants, raw_msgs, taken=None):
    taken = taken if taken is not None else set()
    recs = [reduce_message(m, TZ) for m in raw_msgs]
    recs.sort(key=lambda r: r["timestamp_ms"])
    c = Chat.__new__(Chat)
    c.chat_id = chat_id
    c.name = chat_id
    c.participants = participants
    c.is_group = len(participants) >= 3
    c.recs = recs
    return c


# --------------------------------------------------------------------------- #
# A. Merged timeline & attention
# --------------------------------------------------------------------------- #

def test_bursts_split_on_15min_gap():
    # Burst 1: 3 owner msgs across two chats, gaps < 15 min.
    a = make_chat("a", [OWNER, "A"], [
        msg(BASE, OWNER), msg(BASE + 5 * MIN, OWNER),
    ])
    b = make_chat("b", [OWNER, "B"], [
        msg(BASE + 10 * MIN, OWNER),
        # Burst 2 after a 30-min gap:
        msg(BASE + 40 * MIN, OWNER), msg(BASE + 45 * MIN, OWNER),
    ])
    p = build_connected_data([a, b], OWNER, TZ, min_msgs=0, min_replies=0)
    assert p["attention"]["bursts"]["count"] == 2
    # First burst spans 10 min (BASE .. BASE+10min).
    assert p["attention"]["bursts"]["duration_min"]["max"] == pytest.approx(10.0, abs=0.1)


def test_parallel_texting_rate():
    # Two chats in the SAME 10-min window -> that window is "juggling".
    a = make_chat("a", [OWNER, "A"], [msg(BASE, OWNER)])
    b = make_chat("b", [OWNER, "B"], [msg(BASE + 2 * MIN, OWNER)])
    p = build_connected_data([a, b], OWNER, TZ, min_msgs=0, min_replies=0)
    # Exactly one active window, and it contains 2 chats.
    assert p["attention"]["active_windows"] == 1
    assert p["attention"]["parallel_texting_rate"] == 1.0
    assert p["attention"]["fragmentation_index"] == 1.0
    assert p["attention"]["focus_index"] == 0.0


def test_chat_switch_rate():
    # Consecutive owner msgs within 10 min but in different chats -> a switch.
    a = make_chat("a", [OWNER, "A"], [msg(BASE, OWNER)])
    b = make_chat("b", [OWNER, "B"], [msg(BASE + 3 * MIN, OWNER)])
    p = build_connected_data([a, b], OWNER, TZ, min_msgs=0, min_replies=0)
    assert p["attention"]["chat_switch"]["switch_fraction"] == 1.0


# --------------------------------------------------------------------------- #
# B. Session portfolio
# --------------------------------------------------------------------------- #

def test_session_typing_ping_and_deep():
    # ping: 3 quick messages.
    ping = [msg(BASE + i * 30 * 1000, OWNER if i % 2 == 0 else "A") for i in range(3)]

    # deep_talk: 12 alternating msgs over 30 min, 10 words each, 2 questions.
    deep = []
    for i in range(12):
        sender = OWNER if i % 2 == 0 else "A"
        deep.append(msg(BASE + 10 * HOUR + i * 150 * 1000, sender,
                        content=" ".join(["word"] * 10),
                        question=(i in (2, 4))))

    c = make_chat("a", [OWNER, "A"], ping + deep)
    real = [r for r in c.recs if r["real"]]
    sessions = _split_sessions(real)
    types = [classify_session(s, OWNER, [])[0] for s in sessions]
    assert "ping" in types
    assert "deep_talk" in types


def test_deep_talk_flows_to_totals():
    deep = []
    for i in range(12):
        sender = OWNER if i % 2 == 0 else "A"
        deep.append(msg(BASE + i * 150 * 1000, sender,
                        content=" ".join(["word"] * 10),
                        question=(i in (2, 4))))
    c = make_chat("a", [OWNER, "A"], deep)
    p = build_connected_data([c], OWNER, TZ, min_msgs=0, min_replies=0)
    assert p["sessions_typed"]["totals"]["deep_talk"] >= 1


# --------------------------------------------------------------------------- #
# C. Contact leaderboards
# --------------------------------------------------------------------------- #

def test_contact_totals_and_initiation():
    raw = [
        msg(BASE, OWNER),                 # owner opens (initiation)
        msg(BASE + MIN, "A"),
        msg(BASE + 2 * MIN, OWNER),
        msg(BASE + 3 * MIN, "A"),
        msg(BASE + 4 * MIN, OWNER, media=True),
    ]
    c = make_chat("a", [OWNER, "A"], raw)
    p = build_connected_data([c], OWNER, TZ, min_msgs=0, min_replies=0)
    ct = next(x for x in p["contacts"] if x["name"] == "A")
    assert ct["sent"] == 3          # 2 text + 1 media owner msgs
    assert ct["received"] == 2
    assert ct["media_sent"] == 1
    assert ct["initiations"] == 1
    assert ct["initiation_share"] == 1.0


def test_reply_latency_gating():
    # Only a couple of replies -> latency stays gated at min_replies=50.
    raw = [msg(BASE, "A"), msg(BASE + 2 * MIN, OWNER),
           msg(BASE + 4 * MIN, "A"), msg(BASE + 5 * MIN, OWNER)]
    c = make_chat("a", [OWNER, "A"], raw)
    p = build_connected_data([c], OWNER, TZ, min_msgs=0, min_replies=50)
    ct = p["contacts"][0]
    assert ct["reply_n"] == 2
    assert ct["latency_gated"] is False
    # attention_hierarchy only includes ungated contacts.
    assert all(r["reply_n"] >= 50 for r in p["leaderboards"]["attention_hierarchy"])


def test_night_ownership_share():
    # 00:00-06:00 messages. BASE is some hour; shift to a known 02:00 local.
    from src.timeutil import to_datetime
    # find a ts whose local hour is 2
    ts = BASE
    while to_datetime(ts, TZ).hour != 2:
        ts += HOUR
    a = make_chat("a", [OWNER, "A"], [msg(ts, OWNER), msg(ts + MIN, OWNER)])
    b = make_chat("b", [OWNER, "B"], [msg(ts + 2 * MIN, OWNER)])
    p = build_connected_data([a, b], OWNER, TZ, min_msgs=0, min_replies=0)
    shares = {r["name"]: r["night_share"] for r in p["leaderboards"]["night"]}
    assert shares["A"] == pytest.approx(2 / 3, abs=0.01)
    assert shares["B"] == pytest.approx(1 / 3, abs=0.01)


# --------------------------------------------------------------------------- #
# D. Portfolio dynamics
# --------------------------------------------------------------------------- #

def test_gini_concentration():
    assert _gini([10, 10, 10]) == 0.0            # perfectly even
    assert _gini([0, 0, 100]) > 0.5              # concentrated
    assert _gini([]) == 0.0


def test_gini_monthly_series_present():
    a = make_chat("a", [OWNER, "A"], [msg(BASE, OWNER), msg(BASE + MIN, "A")])
    b = make_chat("b", [OWNER, "B"], [msg(BASE, OWNER)])
    p = build_connected_data([a, b], OWNER, TZ, min_msgs=0, min_replies=0)
    assert isinstance(p["monthly"]["gini"], dict)
    assert len(p["monthly"]["gini"]) >= 1


def test_reciprocity_surplus_deficit():
    # Owner over-invests in A (sends a lot), under-invests in B.
    a = make_chat("a", [OWNER, "A"],
                  [msg(BASE + i * MIN, OWNER) for i in range(10)] +
                  [msg(BASE + 100 * MIN, "A")])
    b = make_chat("b", [OWNER, "B"],
                  [msg(BASE, OWNER)] +
                  [msg(BASE + i * MIN, "B") for i in range(1, 11)])
    p = build_connected_data([a, b], OWNER, TZ, min_msgs=0, min_replies=0)
    surplus = p["leaderboards"]["reciprocity_surplus"]
    deficit = p["leaderboards"]["reciprocity_deficit"]
    assert surplus[0]["name"] == "A"
    assert deficit[0]["name"] == "B"


# --------------------------------------------------------------------------- #
# E. New-contact funnel
# --------------------------------------------------------------------------- #

def test_funnel_and_retention():
    # Contact with 3 separated sessions spanning > 90 days -> recurring + retained.
    raw = []
    for s in range(3):
        base = BASE + s * 40 * 24 * HOUR  # 40-day spacing -> 3 sessions, ~80 days span
        for i in range(4):
            sender = OWNER if i % 2 == 0 else "A"
            raw.append(msg(base + i * MIN, sender))
    c = make_chat("a", [OWNER, "A"], raw)
    p = build_connected_data([c], OWNER, TZ, min_msgs=0, min_replies=0)
    fn = p["funnel"]
    assert fn["stages"]["met"] == 1
    assert fn["stages"]["talked_again"] == 1
    assert fn["stages"]["recurring"] == 1
    assert fn["retention"]["survived_3_sessions"] == 1
    assert fn["retention"]["active_30d"] == 1
    # who-texted-first: owner opened the first session.
    month = next(iter(fn["new_per_month"].values()))
    assert month["owner_first"] == 1


# --------------------------------------------------------------------------- #
# Groups lane + serialization
# --------------------------------------------------------------------------- #

def test_groups_excluded_from_contacts():
    group = make_chat("g", [OWNER, "A", "B"], [
        msg(BASE, OWNER), msg(BASE + MIN, "A"), msg(BASE + 2 * MIN, "B"),
    ])
    dyad = make_chat("a", [OWNER, "A"], [msg(BASE, OWNER), msg(BASE + MIN, "A")])
    p = build_connected_data([group, dyad], OWNER, TZ, min_msgs=0, min_replies=0)
    names = {c["name"] for c in p["contacts"]}
    assert names == {"A"}                       # only the dyad contact
    assert p["groups"]["count"] == 1
    assert p["groups"]["messages_owner"] == 1
    assert p["totals"]["groups"] == 1


def test_dump_js_neutralises_script_and_is_assignable():
    c = make_chat("a", [OWNER, "A"], [msg(BASE, OWNER), msg(BASE + MIN, "A")])
    p = build_connected_data([c], OWNER, TZ, min_msgs=0, min_replies=0)
    js = dump_connected_js(p)
    assert js.startswith("window.CONNECTED = ")
    assert js.rstrip().endswith(";")
    assert "</script" not in js.lower()


def test_owner_aggregate_daily_table():
    c = make_chat("a", [OWNER, "A"], [
        msg(BASE, OWNER), msg(BASE + MIN, OWNER), msg(BASE + 2 * MIN, "A"),
    ])
    p = build_connected_data([c], OWNER, TZ, min_msgs=0, min_replies=0)
    assert p["daily"]
    day = next(iter(p["daily"].values()))
    assert day["msgs"] == 2           # owner sent 2
    assert day["received"] == 1       # contact sent 1
    assert len(day["hours"]) == 24
    assert p["range"]["first_day"] is not None
