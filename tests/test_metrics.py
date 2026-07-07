"""
Tests for all 24 metrics (10 core + 14 V3.0).

Each test creates controlled message data and verifies:
  1. The metric produces output (not empty/errors)
  2. The output has the expected structure
  3. Key values make sense for the given input
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta
from src.analyzer import ChatAnalyzer
from src.language_detection import get_language_distribution
from src.word_frequency import get_word_frequency
from src.response_time import calculate_response_times
from src.media_analyzer import get_media_stats
from src.analyzer_v3 import (
    expressive_lengthening_index,
    emotional_cooling_alert,
    final_word_dominance,
    thought_fragmentation_index,
    conversational_entropy,
    defensiveness_index,
    vocabulary_contagion_rate,
    selective_topic_avoidance,
    conversational_gini_coefficient,
    conversational_inertia,
    signal_to_noise_ratio,
    chaser_retreater_oscillation,
    tit_for_tat_retaliation_score,
    temporal_syncopation_variance,
)


def make_msg(sender, offset_minutes, content="", photos=0, videos=0):
    """Helper to create a test message."""
    base = datetime(2025, 1, 1, 12, 0, 0)
    return {
        "sender_name": sender,
        "timestamp_ms": int((base + timedelta(minutes=offset_minutes)).timestamp() * 1000),
        "content": content,
        "photos": [{"uri": f"photo_{photos}.jpg"}] * photos if photos else [],
        "videos": [{"uri": f"video_{videos}.mp4"}] * videos if videos else [],
    }


# ============================================================
# Core Metrics Tests (10)
# ============================================================

class TestMessageCounts:
    """Test: Alice sends 3, Bob sends 7."""

    def test_basic_counts(self):
        data = {
            "participants": [{"name": "Alice"}, {"name": "Bob"}],
            "title": "Test",
            "messages": [
                make_msg("Alice", 0, "hello"),
                make_msg("Bob", 1, "hi"),
                make_msg("Alice", 2, "hey"),
                make_msg("Bob", 3, "hello again"),
                make_msg("Bob", 4, "yes"),
                make_msg("Alice", 5, "ok"),
                make_msg("Bob", 6, "sure"),
                make_msg("Bob", 7, "bye"),
                make_msg("Bob", 8, "see you"),
                make_msg("Bob", 9, "later"),
            ],
        }
        analyzer = ChatAnalyzer(data, "Alice")
        result = analyzer._get_message_counts()

        assert result["Alice"] == 3, f"Expected Alice=3, got {result['Alice']}"
        assert result["Bob"] == 7, f"Expected Bob=7, got {result['Bob']}"


class TestLanguageDistribution:
    """Test language detection on known content."""

    def test_english_only(self):
        msgs = [
            make_msg("Alice", 0, "hello world"),
            make_msg("Bob", 1, "how are you"),
        ]
        result = get_language_distribution(msgs)
        assert "english" in result
        assert result["english"] == 100.0

    def test_georgian_detected(self):
        # Single detector (normalizer.detect_language) on decoded Georgian text.
        # (The old undecoded 'a-accent' heuristic detector was removed - A3.)
        msgs = [
            make_msg("Alice", 0, "როგორ ხარ"),
            make_msg("Bob", 1, "კარგად ვარ"),
        ]
        result = get_language_distribution(msgs)
        assert "georgian" in result
        assert result["georgian"] == 100.0

    def test_language_field_is_aggregated(self):
        # Aggregates the normalizer's per-message `language` field directly.
        msgs = [
            {"sender_name": "Alice", "content": "hi", "language": "english"},
            {"sender_name": "Alice", "content": "x", "language": "georgian"},
            {"sender_name": "Alice", "content": "y", "language": "system"},
        ]
        result = get_language_distribution(msgs)
        assert result["english"] == 50.0
        assert result["georgian"] == 50.0


class TestWordFrequency:
    """Test word frequency counting."""

    def test_top_words(self):
        # NOTE: "hello"/"world" were poor choices originally — "hello" is a
        # word_frequency stopword and is (correctly) filtered. Use non-stopword
        # content words to exercise the counting mechanics.
        msgs = [
            make_msg("Alice", 0, "apple apple banana"),
            make_msg("Alice", 1, "apple cherry"),
            make_msg("Bob", 2, "banana banana banana"),
        ]
        result = get_word_frequency(msgs, "Alice")
        assert result["apple"] == 3
        assert result["banana"] == 1

    def test_empty_messages(self):
        msgs = [
            make_msg("Alice", 0, ""),
            make_msg("Alice", 1, "Liked a message"),
        ]
        result = get_word_frequency(msgs, "Alice")
        assert result == {}


class TestResponseTimes:
    """Test response time calculations."""

    def test_basic_response_times(self):
        msgs = [
            make_msg("Alice", 0, "hi"),
            make_msg("Bob", 5, "hello"),     # Bob responds in 5 min
            make_msg("Alice", 10, "hey"),       # Alice responds in 5 min
            make_msg("Bob", 12, "hi again"), # Bob responds in 2 min
        ]
        result = calculate_response_times(msgs, "Alice")

        assert result["my_avg_response_minutes"] == 5.0, \
            f"Alice avg should be 5.0, got {result['my_avg_response_minutes']}"
        assert result["partner_avg_response_minutes"] == 3.5, \
            f"Bob avg should be 3.5, got {result['partner_avg_response_minutes']}"

    def test_who_delays_more(self):
        msgs = [
            make_msg("Alice", 0, "hi"),
            make_msg("Bob", 2, "hello"),     # Bob: 2 min
            make_msg("Alice", 30, "hey"),       # Alice: 28 min
            make_msg("Bob", 32, "hi"),       # Bob: 2 min
        ]
        result = calculate_response_times(msgs, "Alice")
        assert result["who_delays_more"] == "you"


class TestMediaStats:
    """Test media statistics."""

    def test_photo_count(self):
        msgs = [
            make_msg("Alice", 0, "", photos=2),
            make_msg("Bob", 1, "", photos=1),
            make_msg("Alice", 2, "no media"),
        ]
        result = get_media_stats(msgs)
        assert result["totals"]["photos"] == 3
        assert result["by_sender"]["Alice"]["photos"] == 2
        assert result["by_sender"]["Bob"]["photos"] == 1


# ============================================================
# V3.0 Metrics Tests (14)
# ============================================================

class TestExpressiveLengthening:
    """Test expressive lengthening index (elongated words like 'heyyy')."""

    def test_elongated_words(self):
        msgs = [
            make_msg("Alice", 0, "heyyy noooo yessss"),
            make_msg("Alice", 1, "ok"),
            make_msg("Bob", 2, "hello world"),
        ]
        result = expressive_lengthening_index(msgs, ["Alice", "Bob"])
        assert result["Alice"] > 0, "Alice should have elongated words"
        assert result["Bob"] == 0.0, "Bob should have no elongated words"

    def test_no_elongated(self):
        msgs = [
            make_msg("Alice", 0, "hello world"),
            make_msg("Bob", 1, "how are you"),
        ]
        result = expressive_lengthening_index(msgs, ["Alice", "Bob"])
        assert result["Alice"] == 0.0
        assert result["Bob"] == 0.0


class TestEmotionalCoolingAlert:
    """Test emotional cooling alerts (>40% drop in expressiveness)."""

    def test_no_alerts_when_stable(self):
        # Messages spread over enough days but with consistent expressiveness
        msgs = []
        for day in range(30):
            msgs.append(make_msg(
                "Alice", day * 60,
                content="heyyy noooo yessss" * 5  # High expressiveness every day
            ))
        result = emotional_cooling_alert(msgs, ["Alice"])
        # Should have few or no alerts since expressiveness is stable
        assert "total_cold_shifts" in result

    def test_alert_structure(self):
        msgs = []
        for day in range(30):
            if day < 15:
                msgs.append(make_msg("Alice", day * 60, "heyyy"))  # High expressiveness
            else:
                msgs.append(make_msg("Alice", day * 60, "ok"))     # Low expressiveness
        result = emotional_cooling_alert(msgs, ["Alice"])
        assert "alerts" in result or "total_cold_shifts" in result


class TestFinalWordDominance:
    """Test who ends sessions (last message in a conversation thread)."""

    def test_dominant_ender(self):
        msgs = [
            make_msg("Alice", 0, "hi"),
            make_msg("Bob", 1, "hello"),
            make_msg("Alice", 2, "how are you"),
            make_msg("Bob", 3, "good"),
            # Gap > 4h (simulated by large time jump)
            make_msg("Alice", 500, "hey"),
            make_msg("Bob", 501, "hi"),
            make_msg("Alice", 502, "last word"),  # Alice ends this session
        ]
        result = final_word_dominance(msgs, ["Alice", "Bob"])
        assert "Alice" in result
        assert "Bob" in result
        total = sum(result.values())
        assert total > 0, "Should have at least one session"


class TestThoughtFragmentation:
    """Test rapid-fire message detection (3+ messages in 15s)."""

    def test_fragmented_sender(self):
        base = datetime(2025, 1, 1, 12, 0, 0)
        msgs = [
            # Alice rapid fires (3 messages within 15 seconds)
            make_msg("Alice", 0, "msg1"),
            make_msg("Alice", 0.1, "msg2"),
            make_msg("Alice", 0.2, "msg3"),
            # Normal conversation
            make_msg("Bob", 10, "slow reply"),
        ]
        result = thought_fragmentation_index(msgs, ["Alice", "Bob"])
        assert "Alice" in result
        assert result["Alice"] >= 0

    def test_no_fragmentation(self):
        msgs = [
            make_msg("Alice", 0, "hello"),
            make_msg("Bob", 30, "hi"),
            make_msg("Alice", 60, "hey"),
        ]
        result = thought_fragmentation_index(msgs, ["Alice", "Bob"])
        assert result["Alice"] == 0.0


class TestConversationalEntropy:
    """Test Shannon entropy on bigram distribution."""

    def test_returns_per_month(self):
        msgs = [
            make_msg("Alice", 0, "hello world how are you"),
            make_msg("Alice", 1, "i am fine thanks"),
            make_msg("Bob", 2, "good to hear"),
        ]
        result = conversational_entropy(msgs, ["Alice", "Bob"])
        assert isinstance(result, dict)
        # Should have at least one month key
        assert len(result) > 0

    def test_english_only(self):
        msgs = [
            make_msg("Alice", 0, "the quick brown fox jumps over the lazy dog"),
            make_msg("Alice", 1, "the cat sat on the mat"),
        ]
        result = conversational_entropy(msgs, ["Alice"])
        assert "Alice" in result[list(result.keys())[0]]


class TestDefensivenessIndex:
    """Test defensiveness word detection."""

    def test_defensive_words(self):
        msgs = [
            make_msg("Alice", 0, "I but just technically actually"),
            make_msg("Alice", 1, "hello"),
            make_msg("Bob", 2, "hi there"),
        ]
        result = defensiveness_index(msgs, ["Alice", "Bob"])
        assert result["Alice"] > result["Bob"], \
            f"Alice should be more defensive: Alice={result['Alice']}, Bob={result['Bob']}"

    def test_no_defensive_words(self):
        msgs = [
            make_msg("Alice", 0, "hello world yes okay"),
            make_msg("Bob", 1, "hi there bye"),
        ]
        result = defensiveness_index(msgs, ["Alice", "Bob"])
        assert result["Alice"] == 0.0 or result["Alice"] < 10


class TestVocabularyContagion:
    """Test vocabulary adoption between users."""

    def test_word_adoption(self):
        msgs = [
            # Alice introduces unique words
            make_msg("Alice", 0, "let me use the word xyz123"),
            make_msg("Alice", 1, "xyz123 is cool"),
            make_msg("Alice", 2, "xyz123 again"),
            make_msg("Alice", 3, "xyz123 once more"),
            # Bob starts using it too
            make_msg("Bob", 4, "yes xyz123 is great"),
            make_msg("Bob", 5, "xyz123 xyz123 love it"),
            make_msg("Bob", 6, "xyz123 forever"),
        ]
        result = vocabulary_contagion_rate(msgs, ["Alice", "Bob"])
        assert "Alice" in result
        assert "Bob" in result


class TestSelectiveTopicAvoidance:
    """Test topic-based response delay detection."""

    def test_empty_when_no_topics(self):
        msgs = [
            make_msg("Alice", 0, "hello"),
            make_msg("Bob", 5, "hi"),
        ]
        result = selective_topic_avoidance(msgs, ["Alice", "Bob"])
        # May return empty dict - that's valid
        assert isinstance(result, dict)

    def test_returns_dict(self):
        msgs = [
            make_msg("Alice", 0, "talking about family stuff"),
            make_msg("Bob", 5, "hi"),
        ]
        result = selective_topic_avoidance(msgs, ["Alice", "Bob"])
        assert isinstance(result, dict)


class TestConversationalGini:
    """Test Gini coefficient for effort inequality."""

    def test_returns_per_month(self):
        msgs = [
            make_msg("Alice", 0, "hello world this is a longer message with more content"),
            make_msg("Bob", 1, "hi"),
            make_msg("Alice", 2, "hey"),
            make_msg("Bob", 3, "yes"),
        ]
        result = conversational_gini_coefficient(msgs, ["Alice", "Bob"])
        assert isinstance(result, dict)
        # Should have at least one period
        assert len(result) > 0


class TestConversationalInertia:
    """Test chat restart effort after dead periods."""

    def test_returns_number(self):
        msgs = [
            make_msg("Alice", 0, "hello"),
            make_msg("Bob", 1, "hi"),
            # Big gap (simulate >72h)
            make_msg("Alice", 10000, "hey"),
            make_msg("Bob", 10001, "hello"),
        ]
        result = conversational_inertia(msgs, ["Alice", "Bob"])
        # C10: now returns a per-user breakdown (not a single blended float).
        assert isinstance(result, dict)
        assert "Alice" in result and "Bob" in result
        assert result["Alice"]["avg_restart_effort"] >= 0
        assert set(result["Alice"].keys()) == {
            "avg_restart_effort", "failed_restarts", "answered_restarts"
        }


class TestSignalToNoiseRatio:
    """Test conversation depth vs filler detection."""

    def test_returns_per_user(self):
        msgs = [
            make_msg("Alice", 0, "hello world this is meaningful content"),
            make_msg("Alice", 1, "ok yeah yes no"),
            make_msg("Bob", 2, "hi there"),
        ]
        result = signal_to_noise_ratio(msgs, ["Alice", "Bob"])
        assert "Alice" in result
        assert "Bob" in result
        assert isinstance(result["Alice"], (int, float))


class TestChaserRetreater:
    """Test anxious-avoidant pursuit dynamics."""

    def test_returns_dict(self):
        msgs = [
            make_msg("Alice", 0, "hello"),
            make_msg("Bob", 1, "hi"),
            make_msg("Alice", 2, "hey"),
            make_msg("Bob", 3, "hello"),
        ]
        result = chaser_retreater_oscillation(msgs, ["Alice", "Bob"])
        assert isinstance(result, dict)


class TestTitForTat:
    """Test delay mirroring detection."""

    def test_returns_per_user(self):
        msgs = [
            make_msg("Alice", 0, "hi"),
            make_msg("Bob", 5, "hello"),
            make_msg("Alice", 10, "hey"),
            make_msg("Bob", 15, "hi"),
            make_msg("Alice", 20, "hello"),
        ]
        result = tit_for_tat_retaliation_score(msgs, ["Alice", "Bob"])
        assert "Alice" in result
        assert "Bob" in result
        assert 0 <= result["Alice"] <= 1
        assert 0 <= result["Bob"] <= 1


class TestTemporalSyncopation:
    """Test rhythm unpredictability."""

    def test_returns_per_user(self):
        msgs = [
            make_msg("Alice", 0, "hello"),
            make_msg("Bob", 1, "hi"),
            make_msg("Alice", 2, "hey"),
            make_msg("Bob", 10, "hello"),  # Larger gap
            make_msg("Alice", 11, "hello"),
        ]
        result = temporal_syncopation_variance(msgs, ["Alice", "Bob"])
        assert "Alice" in result
        assert "Bob" in result
        assert isinstance(result["Alice"], (int, float))


# ============================================================
# Full Pipeline Test
# ============================================================

class TestFullPipeline:
    """Test the complete analysis pipeline on a realistic dataset."""

    def test_full_analysis(self):
        """Run full analyze() and verify all metrics are present."""
        msgs = []
        # Create 30 days of messages
        for day in range(30):
            for hour in range(8, 22):
                sender = "Alice" if (day + hour) % 2 == 0 else "Bob"
                content = "hello world" if sender == "Alice" else "hi there friend"
                msgs.append(make_msg(sender, day * 60 + hour, content))

        data = {
            "participants": [{"name": "Alice"}, {"name": "Bob"}],
            "title": "Full Pipeline Test",
            "messages": msgs,
        }

        analyzer = ChatAnalyzer(data, "Alice")
        result = analyzer.analyze()

        # Check all 24 metrics are present
        expected_keys = [
            "chat_info", "message_counts", "language_distribution",
            "day_of_week", "first_message", "messages_per_week",
            "yearly_stats", "response_times", "media_stats", "word_frequency",
            "expressive_lengthening_index", "emotional_cooling_alert",
            "final_word_dominance", "thought_fragmentation_index",
            "conversational_entropy", "defensiveness_index",
            "vocabulary_contagion_rate", "selective_topic_avoidance",
            "conversational_gini_coefficient", "conversational_inertia",
            "signal_to_noise_ratio", "chaser_retreater_oscillation",
            "tit_for_tat_retaliation_score", "temporal_syncopation_variance",
        ]

        for key in expected_keys:
            assert key in result, f"Missing metric: {key}"

        # Check basic sanity
        assert result["chat_info"]["total_messages"] == len(msgs)
        assert sum(result["message_counts"].values()) == len(msgs)
        assert result["response_times"]["who_delays_more"] in ("you", "partner", "equal")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
