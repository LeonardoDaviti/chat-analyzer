"""Tests for Connected Analysis (src/connected_export.py).

All fixtures are synthetic — no real message content ever appears here.
Covers every metric family: merged-timeline attention (bursts / parallel /
chat-switch / fragmentation), session portfolio typing, contact leaderboards,
portfolio dynamics (Gini / churn), the new-contact funnel, and the groups lane.
"""

import json
from pathlib import Path

import pytest

from src.connected_export import (
    reduce_message, Chat, build_connected_data,
    classify_session, _gini, _split_sessions,
    dump_connected_js, write_variant_outputs,
    discover_telegram_chats, load_telegram_chat,
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


def make_chat(chat_id, participants, raw_msgs, taken=None, platform="instagram",
              is_group=None):
    taken = taken if taken is not None else set()
    recs = [reduce_message(m, TZ) for m in raw_msgs]
    recs.sort(key=lambda r: r["timestamp_ms"])
    c = Chat.__new__(Chat)
    c.chat_id = chat_id
    c.name = chat_id
    c.participants = participants
    c.is_group = (len(participants) >= 3) if is_group is None else bool(is_group)
    c.recs = recs
    c.thread_path = ""
    c.platform = platform
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


def test_dump_js_neutralises_script_and_registers_variant():
    c = make_chat("a", [OWNER, "A"], [msg(BASE, OWNER), msg(BASE + MIN, "A")])
    p = build_connected_data([c], OWNER, TZ, min_msgs=0, min_replies=0,
                             variant="instagram")
    js = dump_connected_js(p, "instagram")
    assert "window.CONNECTED_V = window.CONNECTED_V || {}" in js
    assert 'window.CONNECTED_V["instagram"] =' in js
    assert js.rstrip().endswith(";")
    assert "</script" not in js.lower()


# --------------------------------------------------------------------------- #
# Telegram + multi-variant (per-platform / merged 'all')
# --------------------------------------------------------------------------- #

def _tg_msg(ts_ms, sender, text="hi there friend"):
    return {"type": "message", "date_unixtime": str(ts_ms // 1000),
            "from": sender, "from_id": "user_" + sender, "text": text}


def _write_tg_export(base_dir, folder, name, chat_type, msgs, chat_id="42"):
    d = Path(base_dir) / "Telegram" / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / "result.json").write_text(json.dumps(
        {"name": name, "type": chat_type, "id": chat_id, "messages": msgs}),
        encoding="utf-8")
    return d


def _write_ig_chat(base_dir, folder, title, participants, msgs, thread_path):
    inbox = (Path(base_dir) / "Instagram" / "exp" /
             "your_instagram_activity" / "messages" / "inbox" / folder)
    inbox.mkdir(parents=True, exist_ok=True)
    norm = {"title": title, "thread_path": thread_path,
            "participants": [{"name": p} for p in participants], "messages": msgs}
    (inbox / "normalized.json").write_text(json.dumps(norm), encoding="utf-8")
    return inbox


def test_discover_and_load_telegram_chat(tmp_path):
    _write_tg_export(tmp_path, "DAV", "Davo",
                     "personal_chat",
                     [_tg_msg(BASE + i * MIN, "Davidus" if i % 2 == 0 else "Davo")
                      for i in range(6)])
    dirs = discover_telegram_chats(str(tmp_path))
    assert len(dirs) == 1
    c = load_telegram_chat(dirs[0], set(), TZ)
    assert c is not None
    assert c.platform == "telegram"
    assert c.is_group is False
    assert set(c.participants) == {"Davidus", "Davo"}
    assert len(c.recs) == 6


def test_telegram_group_flag_routes_to_groups_lane(tmp_path):
    # A 2-person Telegram *group* must still be treated as a group.
    _write_tg_export(tmp_path, "GRP", "Squad", "private_group",
                     [_tg_msg(BASE, "Davidus"), _tg_msg(BASE + MIN, "Zed")])
    c = load_telegram_chat(discover_telegram_chats(str(tmp_path))[0], set(), TZ)
    assert c.is_group is True
    p = build_connected_data([c], "Davidus", TZ, min_msgs=0, min_replies=0,
                             variant="telegram", platforms=["telegram"])
    assert p["groups"]["count"] == 1
    assert p["contacts"] == []


def test_contact_platform_tagging_and_merged_dual_owner():
    # Instagram owner "David"; Telegram owner "Davidus" — same human in 'all'.
    ig = make_chat("ig", ["David", "Alice"], [
        msg(BASE, "David"), msg(BASE + 2 * MIN, "David"), msg(BASE + 4 * MIN, "Alice"),
    ], platform="instagram")
    tg = make_chat("tg", ["Davidus", "Bob"], [
        msg(BASE + 1 * MIN, "Davidus"), msg(BASE + 3 * MIN, "Davidus"),
        msg(BASE + 5 * MIN, "Davidus"), msg(BASE + 6 * MIN, "Bob"),
    ], platform="telegram")

    p = build_connected_data([ig, tg], "David", TZ, min_msgs=0, min_replies=0,
                             variant="all", platforms=["instagram", "telegram"],
                             owner_names={"David", "Davidus"})
    assert p["variant"] == "all"
    assert p["platforms"] == ["instagram", "telegram"]
    assert p["owner"] == "David"                      # normalized to IG label
    # Both owner handles counted as owner (2 + 3 = 5 sent).
    assert p["reciprocity"]["sent_total"] == 5
    plats = {c["name"]: c["platform"] for c in p["contacts"]}
    assert plats == {"Alice": "instagram", "Bob": "telegram"}
    # Cross-platform stream: owner messages interleave IG/TG within one burst.
    assert p["attention"]["bursts"]["count"] == 1
    # A switch between an IG chat and a TG chat is counted.
    assert p["attention"]["chat_switch"]["switch_fraction"] > 0
    # Leaderboard rows carry platform for badge rendering.
    assert all("platform" in r for r in p["leaderboards"]["by_sent_share"])


def test_per_platform_variant_isolation():
    ig = make_chat("ig", ["David", "Alice"],
                   [msg(BASE, "David"), msg(BASE + MIN, "Alice")], platform="instagram")
    p = build_connected_data([ig], "David", TZ, min_msgs=0, min_replies=0,
                             variant="instagram", platforms=["instagram"])
    assert p["variant"] == "instagram"
    assert all(c["platform"] == "instagram" for c in p["contacts"])


def test_write_variant_outputs(tmp_path):
    c = make_chat("a", [OWNER, "A"], [msg(BASE, OWNER), msg(BASE + MIN, "A")])
    p = build_connected_data([c], OWNER, TZ, min_msgs=0, min_replies=0,
                             variant="telegram", platforms=["telegram"])
    js_path, json_path = write_variant_outputs(p, str(tmp_path), "telegram")
    assert js_path.name == "connected_telegram.js"
    assert json_path.name == "connected_telegram.json"
    js = js_path.read_text(encoding="utf-8")
    assert 'window.CONNECTED_V["telegram"]' in js
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["variant"] == "telegram"


def test_cli_builds_three_variants(tmp_path):
    import build_connected
    chats = tmp_path / "Chats"
    dash = tmp_path / "Dashboard"
    _write_ig_chat(chats, "alice", "Alice", ["David", "Alice"],
                   [{"timestamp_ms": BASE + i * MIN,
                     "sender_name": "David" if i % 2 == 0 else "Alice",
                     "content": "hello there", "language": "english", "type": "text"}
                    for i in range(6)],
                   thread_path="inbox/alice_1")
    _write_tg_export(chats, "DAV", "Davo", "personal_chat",
                     [_tg_msg(BASE + i * MIN, "Davidus" if i % 2 == 0 else "Davo")
                      for i in range(6)])
    rc = build_connected.main([
        "--chats-dir", str(chats), "--dash-dir", str(dash),
        "--min-msgs", "0", "--min-replies", "0"])
    assert rc == 0
    data = dash / "data"
    for v in ("instagram", "telegram", "all"):
        assert (data / f"connected_{v}.js").exists()
        assert (data / f"connected_{v}.json").exists()
    allp = json.loads((data / "connected_all.json").read_text(encoding="utf-8"))
    assert set(allp["platforms"]) == {"instagram", "telegram"}


def test_cli_no_telegram_skips_gracefully(tmp_path):
    import build_connected
    chats = tmp_path / "Chats"
    dash = tmp_path / "Dashboard"
    _write_ig_chat(chats, "alice", "Alice", ["David", "Alice"],
                   [{"timestamp_ms": BASE + i * MIN,
                     "sender_name": "David" if i % 2 == 0 else "Alice",
                     "content": "hello there", "language": "english", "type": "text"}
                    for i in range(6)],
                   thread_path="inbox/alice_1")
    # No Telegram/ dir at all — telegram + all(merged from IG only) still fine.
    rc = build_connected.main([
        "--chats-dir", str(chats), "--dash-dir", str(dash),
        "--min-msgs", "0", "--min-replies", "0"])
    assert rc == 0
    data = dash / "data"
    assert (data / "connected_instagram.js").exists()
    # Telegram variant skipped (no chats) → no file written.
    assert not (data / "connected_telegram.js").exists()
    # 'all' still built from Instagram alone.
    allp = json.loads((data / "connected_all.json").read_text(encoding="utf-8"))
    assert allp["platforms"] == ["instagram"]


# --------------------------------------------------------------------------- #
# contact_monthly — the per-contact per-month windowed data layer
# --------------------------------------------------------------------------- #

MONTH_MS = 31 * 24 * HOUR  # comfortably crosses a month boundary


def _cm_row(p, month, chat_id):
    return p["contact_monthly"].get(month, {}).get(chat_id)


def test_contact_monthly_counter_correctness_and_bucketing():
    # Two months of activity in one chat. Owner sends in both months; contact
    # replies. Verify sent/recv land in the right month bucket and totals match.
    m1 = BASE
    # advance to a clearly different calendar month
    from src.timeutil import to_datetime
    m2 = BASE + MONTH_MS
    while to_datetime(m2, TZ).strftime("%Y-%m") == to_datetime(m1, TZ).strftime("%Y-%m"):
        m2 += 7 * 24 * HOUR
    mon1 = to_datetime(m1, TZ).strftime("%Y-%m")
    mon2 = to_datetime(m2, TZ).strftime("%Y-%m")

    raw = [
        msg(m1, OWNER), msg(m1 + MIN, OWNER), msg(m1 + 2 * MIN, "A"),   # mon1: 2 sent, 1 recv
        msg(m2, OWNER), msg(m2 + MIN, "A"), msg(m2 + 2 * MIN, "A"),     # mon2: 1 sent, 2 recv
    ]
    c = make_chat("a", [OWNER, "A"], raw)
    p = build_connected_data([c], OWNER, TZ, min_msgs=0, min_replies=0)

    r1, r2 = _cm_row(p, mon1, "a"), _cm_row(p, mon2, "a")
    assert r1 and r2
    assert r1["sent"] == 2 and r1["recv"] == 1
    assert r2["sent"] == 1 and r2["recv"] == 2
    # zero counters are omitted entirely
    assert all(v != 0 for v in r1.values())
    # totals reconcile with the all-time contact record
    ct = next(x for x in p["contacts"] if x["name"] == "A")
    tot_sent = sum(p["contact_monthly"][mo]["a"].get("sent", 0)
                   for mo in p["contact_monthly"] if "a" in p["contact_monthly"][mo])
    assert tot_sent == ct["sent"]


def test_contact_monthly_night_and_words_and_style():
    from src.timeutil import to_datetime
    ts = BASE
    while to_datetime(ts, TZ).hour != 2:      # a 02:00 local (night) anchor
        ts += HOUR
    mon = to_datetime(ts, TZ).strftime("%Y-%m")
    # owner sends two 3-word georgian-tagged msgs at night; contact replies once.
    raw = [
        {"timestamp_ms": ts, "sender_name": OWNER, "content": "one two three",
         "language": "georgian", "type": "text"},
        {"timestamp_ms": ts + MIN, "sender_name": OWNER, "content": "aa bb cc",
         "language": "georgian", "type": "text"},
        {"timestamp_ms": ts + 2 * MIN, "sender_name": "A", "content": "hi",
         "language": "english", "type": "text"},
    ]
    c = make_chat("a", [OWNER, "A"], raw)
    p = build_connected_data([c], OWNER, TZ, min_msgs=0, min_replies=0)
    r = _cm_row(p, mon, "a")
    assert r["night_sent"] == 2
    assert r["words_sent"] == 6           # 3 + 3 owner words
    assert r["lang_geo"] == 2 and r["lang_total"] == 2
    assert r["turns_sent"] == 1           # one maximal owner run
    assert r["sessions"] == 1 and r["initiations"] == 1


def test_contact_monthly_reply_latency_bucket():
    from src.timeutil import to_datetime
    raw = [msg(BASE, "A"), msg(BASE + 2 * MIN, OWNER),        # owner reply, 2 min
           msg(BASE + 4 * MIN, "A"), msg(BASE + 7 * MIN, OWNER)]  # owner reply, 3 min
    mon = to_datetime(BASE, TZ).strftime("%Y-%m")
    c = make_chat("a", [OWNER, "A"], raw)
    p = build_connected_data([c], OWNER, TZ, min_msgs=0, min_replies=0)
    r = _cm_row(p, mon, "a")
    assert r["reply_lat_n"] == 2
    assert r["reply_lat_sum_min"] == pytest.approx(5.0, abs=0.01)


def test_contact_monthly_reaction_latency_both_directions():
    from src.timeutil import to_datetime
    mon = to_datetime(BASE, TZ).strftime("%Y-%m")
    # Telegram-style dated reactions. Owner reacts to A's msg after 60s; A reacts
    # to owner's msg after 120s.
    a_msg = {"timestamp_ms": BASE, "sender_name": "A", "content": "hi there",
             "language": "english", "type": "text",
             "reactions": [{"actor": OWNER, "date": BASE + 60 * 1000}]}
    o_msg = {"timestamp_ms": BASE + 5 * MIN, "sender_name": OWNER, "content": "yo there",
             "language": "english", "type": "text",
             "reactions": [{"actor": "A", "date": BASE + 5 * MIN + 120 * 1000}]}
    c = make_chat("a", [OWNER, "A"], [a_msg, o_msg])
    p = build_connected_data([c], OWNER, TZ, min_msgs=0, min_replies=0)
    r = _cm_row(p, mon, "a")
    assert r["react_you_n"] == 1 and r["react_you_sum_s"] == pytest.approx(60.0, abs=0.1)
    assert r["react_them_n"] == 1 and r["react_them_sum_s"] == pytest.approx(120.0, abs=0.1)


def test_contact_monthly_merge_folds_rows():
    # Same human on IG + TG; identity merge folds their monthly rows into one.
    from src.timeutil import to_datetime
    mon = to_datetime(BASE, TZ).strftime("%Y-%m")
    ig = make_chat("ig", ["David", "Alice"],
                   [msg(BASE, "David"), msg(BASE + MIN, "Alice")], platform="instagram")
    tg = make_chat("tg", ["Davidus", "Alice"],
                   [msg(BASE + 2 * MIN, "Davidus"), msg(BASE + 3 * MIN, "Alice")],
                   platform="telegram")
    identities = [{"name": "Alice", "members": ["instagram:ig", "telegram:tg"]}]
    p = build_connected_data([ig, tg], "David", TZ, min_msgs=0, min_replies=0,
                             variant="all", platforms=["instagram", "telegram"],
                             owner_names={"David", "Davidus"}, identities=identities)
    # a single merged entity id holds the combined monthly row (2 sent total)
    month = p["contact_monthly"][mon]
    assert "ig" not in month and "tg" not in month
    merged_ids = [cid for cid in month if cid.startswith("merged_")]
    assert len(merged_ids) == 1
    assert month[merged_ids[0]]["sent"] == 2


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
