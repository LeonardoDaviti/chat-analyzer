"""
Tests for the V4 relationship-dynamics metrics (M1-M5, M7, M10, M11, M14).

Each test builds a small synthetic message list with hand-computed expected
values, plus a contract-shape check for every metric on empty input.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta, timezone as _tz

from src.metrics_v4 import (
    initiation_metrics,
    question_metrics,
    bid_response_metrics,
    affect_economy_metrics,
    circadian_metrics,
    repair_metrics,
    double_texting_metrics,
    half_life_metrics,
    change_point_metrics,
)

USERS = ["Alice", "Bob"]
BASE = datetime(2025, 1, 6, 12, 0, 0)  # a Monday, local naive


def make_msg(sender, offset_minutes, content="", reactions=None,
             photos=0, videos=0, share=False):
    m = {
        "sender_name": sender,
        "timestamp_ms": int((BASE + timedelta(minutes=offset_minutes)).timestamp() * 1000),
        "content": content,
        "language": "english" if content else "media",
    }
    if reactions is not None:
        m["reactions"] = reactions
    if photos:
        m["photos"] = [{"uri": "p.jpg"}] * photos
    if videos:
        m["videos"] = [{"uri": "v.mp4"}] * videos
    if share:
        m["share"] = {"link": "http://x"}
    return m


# ============================================================
# M1 - initiation
# ============================================================

class TestInitiation:
    def test_share_and_latency(self):
        # Session 1: Alice opens. Gap 3h. Session 2: Bob opens.
        msgs = [
            make_msg("Alice", 0, "hi"),
            make_msg("Bob", 5, "hey"),
            make_msg("Alice", 10, "bye"),
            # 3h gap (> 2h session gap) -> new session
            make_msg("Bob", 10 + 180, "back?"),
            make_msg("Alice", 10 + 185, "yes"),
        ]
        r = initiation_metrics(msgs, USERS)
        assert r["n"] == 2
        assert r["per_user"]["Alice"]["initiation_count"] == 1
        assert r["per_user"]["Bob"]["initiation_count"] == 1
        assert r["per_user"]["Alice"]["initiation_share"] == 0.5
        # Bob reopened after a 3h silence (session1 ended at +10, session2 +190).
        assert r["per_user"]["Bob"]["median_reopen_latency_hours"] == 3.0
        # Alice never reopened (opened the very first session only).
        assert r["per_user"]["Alice"]["median_reopen_latency_hours"] == 0.0


# ============================================================
# M2 - questions
# ============================================================

class TestQuestions:
    def test_answered_vs_ignored(self):
        # One session. Alice asks Q1 (answered by Bob), then at the end asks
        # Q2 with nobody replying -> ignored.
        msgs = [
            make_msg("Alice", 0, "why is that?"),   # Q1
            make_msg("Bob", 2, "because reasons"),  # answers Q1
            make_msg("Alice", 5, "how come?"),      # Q2 - no later different sender
        ]
        r = question_metrics(msgs, USERS)
        assert r["n"] == 2
        d = r["per_user"]["Alice"]
        assert d["questions_asked"] == 2
        assert d["answered_rate"] == 0.5
        assert d["ignored_count"] == 1


# ============================================================
# M3 - bids
# ============================================================

class TestBids:
    def test_toward_vs_away(self):
        # Alice makes two bids (exclamations). First engaged, second ignored.
        msgs = [
            make_msg("Alice", 0, "look at this!"),   # bid 1
            make_msg("Bob", 2, "nice"),           # turns toward bid 1
            make_msg("Alice", 5, "amazing!"),        # bid 2 - no reply follows
        ]
        r = bid_response_metrics(msgs, USERS)
        assert r["n"] == 2
        assert r["per_user"]["Alice"]["bids_made"] == 2
        assert r["per_user"]["Alice"]["partner_turned_toward_rate"] == 0.5
        # Bob turned toward the one bid opportunity she had.
        assert r["per_user"]["Bob"]["toward_rate_given"] == 0.5


# ============================================================
# M4 - affect economy (mojibake actor)
# ============================================================

class TestAffect:
    def test_reactions_with_mojibake_actor(self):
        georgian = "მარიამ"
        mojibake_actor = georgian.encode("utf-8").decode("latin-1")
        users = ["Alice", georgian]
        msgs = [
            make_msg("Alice", 0, "gaixare",
                     reactions=[{"reaction": "❤", "actor": mojibake_actor}]),
            make_msg(georgian, 2, "gilocav"),
        ]
        r = affect_economy_metrics(msgs, users)
        assert r["per_user"][georgian]["reactions_given"] == 1
        assert r["per_user"]["Alice"]["reactions_received"] == 1
        assert r["n"] >= 1


# ============================================================
# M5 - circadian
# ============================================================

class TestCircadian:
    def test_night_share_and_overlap(self):
        # Identical timestamps for both users -> identical hour distributions
        # -> overlap coefficient = 1.0. One night message (Tbilisi 01:00) and one
        # day message (Tbilisi 13:00) each -> night_share = 0.5.
        night_utc = datetime(2025, 1, 1, 21, 0, tzinfo=_tz.utc)   # Tbilisi 01:00
        day_utc = datetime(2025, 1, 1, 9, 0, tzinfo=_tz.utc)      # Tbilisi 13:00
        n_ms = int(night_utc.timestamp() * 1000)
        d_ms = int(day_utc.timestamp() * 1000)
        msgs = []
        for u in USERS:
            for ts in (n_ms, d_ms):
                msgs.append({"sender_name": u, "timestamp_ms": ts,
                             "content": "hi", "language": "english"})
        r = circadian_metrics(msgs, USERS)
        assert r["overlap_coefficient"] == 1.0
        assert r["per_user"]["Alice"]["night_share"] == 0.5
        assert r["per_user"]["Bob"]["night_share"] == 0.5
        assert r["n"] == 4
        assert len(r["matrices"]["Alice"]) == 7
        assert len(r["matrices"]["Alice"][0]) == 24


# ============================================================
# M7 - repair
# ============================================================

class TestRepair:
    def test_rupture_and_repair_attribution(self):
        # Session 1 ended by Alice. 50h silence (>48h) -> rupture. Session 2
        # opened by Bob -> she is the repairer.
        msgs = [
            make_msg("Alice", 0, "hey"),
            make_msg("Bob", 5, "hi"),
            make_msg("Alice", 10, "ok bye"),        # Alice ends session 1
            # 50h gap
            make_msg("Bob", 10 + 50 * 60, "you there?"),  # Bob repairs
            make_msg("Alice", 10 + 50 * 60 + 5, "yes"),
        ]
        r = repair_metrics(msgs, USERS)
        assert r["n"] == 1
        assert r["per_user"]["Alice"]["ruptures_caused"] == 1
        assert r["per_user"]["Bob"]["repairs_made"] == 1
        assert r["per_user"]["Bob"]["repair_share"] == 1.0
        assert abs(r["per_user"]["Bob"]["median_repair_latency_hours"] - 50.0) < 0.5


# ============================================================
# M10 - double texting
# ============================================================

class TestDoubleTexting:
    def test_double_text_and_streak(self):
        # Alice sends 3 consecutive messages 15 min apart (partner silent),
        # then Bob replies. Run length 3 -> streak '3'; two >=10min gaps -> 2
        # double texts.
        msgs = [
            make_msg("Alice", 0, "you up?"),
            make_msg("Alice", 15, "hello?"),
            make_msg("Alice", 30, "guess not"),
            make_msg("Bob", 40, "sorry here"),
        ]
        r = double_texting_metrics(msgs, USERS)
        d = r["per_user"]["Alice"]
        assert d["double_texts"] == 2
        assert d["max_unanswered_streak"] == 3
        assert d["streak_histogram"].get("3") == 1
        assert r["n"] == 2


# ============================================================
# M11 - half-life
# ============================================================

class TestHalfLife:
    def test_momentum_kill_attribution(self):
        # 6 messages: fast first half, slow second half. second-half median (10)
        # > 3x first-half median (1) -> momentum lost. Last holder = Alice.
        offsets = [0, 1, 2, 12, 22, 32]  # intervals: 1,1,10,10,10
        senders = ["Alice", "Bob", "Alice", "Bob", "Bob", "Alice"]
        msgs = [make_msg(s, o, "msg") for s, o in zip(senders, offsets)]
        r = half_life_metrics(msgs, USERS)
        assert r["n"] == 1
        assert r["per_user"]["Alice"]["sessions_last_held"] == 1
        assert r["per_user"]["Alice"]["momentum_kill_share"] == 1.0
        assert r["per_user"]["Bob"]["momentum_kill_share"] == 0.0


# ============================================================
# M14 - change points
# ============================================================

class TestChangePoints:
    def test_detects_step_change(self):
        # 30 weekly buckets: weeks 0-14 low volume, weeks 15-29 high volume.
        msgs = []
        for week in range(30):
            count = 3 if week < 15 else 30
            week_base = week * 7 * 24 * 60  # minutes offset, 1 week apart
            for k in range(count):
                sender = "Alice" if k % 2 == 0 else "Bob"
                msgs.append(make_msg(sender, week_base + k, "hello there"))
        r = change_point_metrics(msgs, USERS)
        assert r["n"] == 30
        vol_signals = [
            s for cp in r["change_points"] for s in cp["signals"]
            if s["metric"] == "volume"
        ]
        assert vol_signals, "expected a volume change-point"
        assert any(s["direction"] == "up" for s in vol_signals)
        assert "volume" in r["weekly_series"]


# ============================================================
# Contract shape on empty input
# ============================================================

class TestContractShape:
    def test_empty_standard_metrics(self):
        fns = [
            initiation_metrics, question_metrics, bid_response_metrics,
            affect_economy_metrics, circadian_metrics, repair_metrics,
            double_texting_metrics, half_life_metrics,
        ]
        for fn in fns:
            r = fn([], USERS)
            assert r["n"] == 0, fn.__name__
            assert r["series"] == {}, fn.__name__
            assert set(r["per_user"].keys()) == set(USERS), fn.__name__

    def test_empty_change_points(self):
        r = change_point_metrics([], USERS)
        assert r["n"] == 0
        assert r["change_points"] == []
        assert r["weekly_series"] == {}
