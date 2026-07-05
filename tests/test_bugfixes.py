"""
Regression tests for the BUG_REPORT fixes.

Each test uses a tiny synthetic message list with a known answer and targets a
specific bug cluster (referenced by its BUG_REPORT id).
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.timeutil import to_datetime, DEFAULT_TIMEZONE
from src.normalizer import is_system_message, is_real_message, detect_language, normalize_message
from src.analyzer import ChatAnalyzer
from src.analyzer_v3 import (
    thought_fragmentation_index,
    final_word_dominance,
    emotional_cooling_alert,
    temporal_syncopation_variance,
)
from src.session_chunker import chunk_messages
from src.data_combiner import get_chat_dirs


def _epoch_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def msg(sender, ts_ms, content=""):
    return {"sender_name": sender, "timestamp_ms": ts_ms, "content": content}


# ------------------------------------------------------------------ A1
class TestSystemMessageDetection:
    def test_liked_a_message_is_system(self):
        # Case bug: 'Liked a message' must be detected (old code lowercased the
        # content but kept a capitalised pattern -> always False).
        assert is_system_message({"content": "Liked a message"}) is True
        assert is_system_message("Liked a message") is True

    def test_normalize_flags_like_as_system(self):
        out = normalize_message({"sender_name": "David", "timestamp_ms": 1000,
                                 "content": "Liked a message"})
        assert out["language"] == "system"
        assert is_real_message(out) is False

    def test_real_message_with_substring_not_dropped(self):
        # Inverse bug: bare substrings 'added' / 'reacted' dropped real messages.
        assert is_system_message({"content": "I added you on Steam"}) is False
        assert is_system_message({"content": "she reacted badly to the news"}) is False
        assert is_real_message({"content": "I added you on Steam", "language": "english"}) is True


# ------------------------------------------------------------------ A2
class TestGeorgianCharCounting:
    def test_long_pure_georgian_is_georgian_not_mixed(self):
        # 3 words / 16 chars. Old run-counting gave 3/16 -> "mixed".
        text = "როგორ ხარ კარგად"
        assert detect_language(text) == "georgian"

    def test_short_georgian(self):
        assert detect_language("კი") == "georgian"


# ------------------------------------------------------------------ A4
class TestTimezoneBucketing:
    def test_epoch_zero_is_tbilisi_0400(self):
        # 1970-01-01 00:00 UTC == 04:00 in Asia/Tbilisi (UTC+4).
        dt = to_datetime(0)
        assert dt.hour == 4
        assert dt.tzinfo is not None

    def test_late_night_lands_on_correct_local_day(self):
        # 2025-05-19 23:30 UTC -> 2025-05-20 03:30 Tbilisi (next day).
        ts = _epoch_ms(datetime(2025, 5, 19, 23, 30, tzinfo=timezone.utc))
        dt = to_datetime(ts, DEFAULT_TIMEZONE)
        assert dt.strftime("%Y-%m-%d") == "2025-05-20"


# ------------------------------------------------------------------ A5
class TestGeneratorTruthiness:
    def test_empty_subdir_not_a_chat(self, tmp_path):
        inbox = tmp_path / "your_instagram_activity" / "messages" / "inbox"
        (inbox / "real_chat").mkdir(parents=True)
        (inbox / "real_chat" / "message_1.json").write_text("{}", encoding="utf-8")
        (inbox / "empty_dir").mkdir()  # stray directory, no message files

        dirs = get_chat_dirs(str(tmp_path))
        names = {d.name for d in dirs}
        assert names == {"real_chat"}  # empty_dir must NOT be treated as a chat


# ------------------------------------------------------------------ B1
class TestTinySessionMergeThreshold:
    def _base(self):
        return datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def test_far_tiny_session_not_merged(self):
        base = self._base()
        msgs = [
            # Tiny 2-message exchange in January
            msg("David", _epoch_ms(base), "hi"),
            msg("Mariam", _epoch_ms(base + timedelta(minutes=1)), "hey"),
            # Large session ~40 days later
            *[msg("David" if i % 2 == 0 else "Mariam",
                  _epoch_ms(base + timedelta(days=40, minutes=i)), f"m{i}")
              for i in range(6)],
        ]
        sessions = chunk_messages(msgs, "David", "Mariam")
        large = [s for s in sessions if s["messages"]["total"] >= 3]
        assert len(large) == 1
        # Its duration must NOT be inflated to tens of thousands of minutes.
        assert large[0]["duration_minutes"] < 60
        # The tiny session is retained (not deleted), tagged invalid.
        assert any(s["messages"]["total"] == 2 and s["valid"] is False for s in sessions)

    def test_near_tiny_session_is_merged(self):
        base = self._base()
        msgs = [
            msg("David", _epoch_ms(base), "hi"),
            msg("Mariam", _epoch_ms(base + timedelta(minutes=1)), "hey"),
            # Large session only 30 minutes later (within 60-min threshold)
            *[msg("David" if i % 2 == 0 else "Mariam",
                  _epoch_ms(base + timedelta(minutes=30 + i)), f"m{i}")
              for i in range(4)],
        ]
        sessions = chunk_messages(msgs, "David", "Mariam")
        merged = [s for s in sessions if s["messages"]["total"] == 6]
        assert len(merged) == 1
        assert merged[0]["valid"] is True


# ------------------------------------------------------------------ C1
class TestThoughtFragmentationDenominator:
    def test_denominator_is_sessions_not_messages(self):
        base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        msgs = [
            # David rapid-fires 3 messages within 15s (a burst)
            msg("David", _epoch_ms(base), "one"),
            msg("David", _epoch_ms(base + timedelta(seconds=5)), "two"),
            msg("David", _epoch_ms(base + timedelta(seconds=10)), "three"),
            # Mariam replies within the same session
            msg("Mariam", _epoch_ms(base + timedelta(minutes=5)), "ok"),
        ]
        result = thought_fragmentation_index(msgs, ["David", "Mariam"])
        # One session, David burst -> index 1.0 (not deflated by message count).
        assert result["David"] == 1.0
        assert result["Mariam"] == 0.0

    def test_pingpong_is_not_fragmentation(self):
        base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        msgs = [
            msg("David", _epoch_ms(base), "a"),
            msg("Mariam", _epoch_ms(base + timedelta(seconds=4)), "b"),
            msg("David", _epoch_ms(base + timedelta(seconds=8)), "c"),
        ]
        # 3 fast messages but alternating senders -> NOT a burst.
        result = thought_fragmentation_index(msgs, ["David", "Mariam"])
        assert result["David"] == 0.0


# ------------------------------------------------------------------ C2
class TestFinalWordFirstSession:
    def test_first_session_single_message_ender_counted(self):
        base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        msgs = [
            # Session 1: a single message from David
            msg("David", _epoch_ms(base), "hey"),
            # Session 2 (after a >2h gap), ended by Mariam
            msg("David", _epoch_ms(base + timedelta(hours=5)), "back"),
            msg("Mariam", _epoch_ms(base + timedelta(hours=5, minutes=2)), "hi"),
        ]
        result = final_word_dominance(msgs, ["David", "Mariam"])
        # Two sessions; each ender counted; percentages sum to 1.0.
        assert round(sum(result.values()), 4) == 1.0
        assert result["David"] == 0.5
        assert result["Mariam"] == 0.5

    def test_accepts_precomputed_sessions(self):
        sessions = [
            {"participants": {"ended_by": "David"}},
            {"participants": {"ended_by": "Mariam"}},
            {"participants": {"ended_by": "David"}},
        ]
        result = final_word_dominance([], ["David", "Mariam"], sessions=sessions)
        assert result["David"] == round(2 / 3, 4)
        assert result["Mariam"] == round(1 / 3, 4)


# ------------------------------------------------------------------ C3
class TestDisjointCoolingWindows:
    def test_detects_cooling_over_disjoint_windows(self):
        base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        msgs = []
        for d in range(28):
            content = "wooow 😍😍" if d < 14 else "ok"
            msgs.append(msg("David", _epoch_ms(base + timedelta(days=d)), content))
        result = emotional_cooling_alert(msgs, ["David"])
        assert result["total_cold_shifts"] >= 1
        assert any(v["user"] == "David" for v in result["alerts"].values())

    def test_stable_expressiveness_no_alert(self):
        base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        msgs = [msg("David", _epoch_ms(base + timedelta(days=d)), "wooow 😍")
                for d in range(28)]
        result = emotional_cooling_alert(msgs, ["David"])
        assert result["total_cold_shifts"] == 0


# ------------------------------------------------------------------ C1/C8
class TestSyncopationLastSessionFlush:
    def test_single_gapless_session_is_processed(self):
        base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        msgs = [
            msg("David", _epoch_ms(base), "a"),
            msg("Mariam", _epoch_ms(base + timedelta(seconds=30)), "b"),
            msg("David", _epoch_ms(base + timedelta(minutes=10)), "c"),
            msg("Mariam", _epoch_ms(base + timedelta(minutes=11)), "d"),
        ]
        # No 4h/2h gap anywhere -> the whole chat is one session that must
        # still be flushed and processed (old code skipped the last session).
        result = temporal_syncopation_variance(msgs, ["David", "Mariam"])
        assert result != {}
        assert "David" in result and "Mariam" in result


# ------------------------------------------------------------------ C14
class TestISOWeekYearBoundary:
    def test_dec_29_31_land_in_next_iso_year(self):
        # 2024-12-30 belongs to ISO week 1 of ISO year 2025.
        d1 = _epoch_ms(datetime(2024, 12, 30, 12, 0, tzinfo=timezone.utc))
        d2 = _epoch_ms(datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc))
        data = {
            "participants": [{"name": "David"}, {"name": "Mariam"}],
            "title": "T",
            "messages": [
                msg("David", d1, "one"),
                msg("Mariam", d2, "two"),
            ],
        }
        analyzer = ChatAnalyzer(data, "David")
        weeks = analyzer._get_messages_per_week()
        # No phantom 2024 bucket; both messages in ISO-year 2025, week 1.
        assert "2024" not in weeks
        assert "2025" in weeks
        assert weeks["2025"]["weekly_counts"][0] == 2  # week 1 -> index 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
