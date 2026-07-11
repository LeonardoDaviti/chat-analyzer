"""DATA-CAPTURE regressions for the normalizer (DATA_AUDIT §4).

Proves the approved Instagram-side raw fields round-trip from a raw message dict
into the normalized message schema. All data here is synthetic — invented names,
no real content.
"""

from src.normalizer import normalize_message, normalize_chat, is_system_message


def test_ig_call_duration_landed_as_seconds():
    """P2: Instagram raw `call_duration` (int seconds) -> `call_duration_s`."""
    m = normalize_message({
        "sender_name": "Nadia", "timestamp_ms": 1700000000000,
        "content": "", "call_duration": 109,
    })
    assert m["call_duration_s"] == 109
    assert m["type"] == "call"


def test_ig_missed_call_zero_duration_still_captured():
    """A 0-second (missed) call is present -> capture the 0, don't drop it."""
    m = normalize_message({
        "sender_name": "Nadia", "timestamp_ms": 1700000000000,
        "content": "", "call_duration": 0,
    })
    assert m["call_duration_s"] == 0


def test_non_call_message_has_no_call_duration_s():
    """No call_duration -> no call_duration_s key (no null spam)."""
    m = normalize_message({
        "sender_name": "Nadia", "timestamp_ms": 1700000000000,
        "content": "hey",
    })
    assert "call_duration_s" not in m


def test_ig_share_owner_captured():
    """P9: share.original_content_owner -> share_owner (str)."""
    m = normalize_message({
        "sender_name": "Nadia", "timestamp_ms": 1700000000000,
        "content": "",
        "share": {"link": "http://x.example/reel",
                  "share_text": "look",
                  "original_content_owner": "some_creator"},
    })
    assert m["share_owner"] == "some_creator"
    assert m["type"] == "share"


def test_ig_share_without_owner_sets_nothing():
    m = normalize_message({
        "sender_name": "Nadia", "timestamp_ms": 1700000000000,
        "content": "",
        "share": {"link": "http://x.example/reel"},
    })
    assert "share_owner" not in m


def test_is_unsent_guard_removed_is_noop():
    """The dead `is_unsent` guard was removed (field never exists in exports)."""
    # A message carrying a stray is_unsent=True must NOT be classified system
    # solely on that basis; only the anchored content regexes decide.
    assert is_system_message({"is_unsent": True, "content": "just a normal line"}) is False
    # genuine system content still detected
    assert is_system_message({"content": "liked a message"}) is True


def test_ig_capture_through_full_chat_normalize():
    """End-to-end: fields survive normalize_chat, not just normalize_message."""
    chat = {
        "participants": [{"name": "Nadia"}, {"name": "Owner"}],
        "messages": [
            {"sender_name": "Nadia", "timestamp_ms": 1700000000000,
             "content": "", "call_duration": 42},
            {"sender_name": "Owner", "timestamp_ms": 1700000100000,
             "content": "",
             "share": {"original_content_owner": "creator_x"}},
        ],
    }
    out = normalize_chat(chat)["messages"]
    assert out[0]["call_duration_s"] == 42
    assert out[1]["share_owner"] == "creator_x"
