"""Tests for the Telegram loader, platform detection and Telegram-only metrics.

All data here is synthetic — no real message content is ever used.
"""

import json
from pathlib import Path

import pytest

import main
from src.loaders.telegram import (
    parse_telegram_result,
    load_telegram_chat,
    _flatten_text,
    _map_reactions,
    _entity_counts,
)
from src.normalizer import is_real_message
from src.dashboard_export import (
    build_chat_payload,
    build_daily_aggregates,
    has_telegram_fields,
    build_telegram_signals,
)


# --------------------------------------------------------------------------- #
# Synthetic Telegram result.json
# --------------------------------------------------------------------------- #

OWNER = "Owner"
OTHER = "Friend"


def _result():
    """A small but structurally complete Telegram personal_chat export."""
    return {
        "name": OTHER,          # top-level name is the OTHER person
        "type": "personal_chat",
        "id": 424242,
        "messages": [
            # 1: plain string text, edited, with a reaction from OTHER
            {
                "id": 1, "type": "message",
                "date_unixtime": "1700000000",
                "from": OWNER, "from_id": "user1",
                "text": "hello there",
                "text_entities": [{"type": "plain", "text": "hello there"}],
                "edited": "2023-11-14T22:14:00", "edited_unixtime": "1700000100",
                "reactions": [{"type": "emoji", "count": 1, "emoji": "\U0001F44D",
                               "recent": [{"from": OTHER, "from_id": "user2",
                                           "date": "2023-11-14T22:14:10"}]}],
            },
            # 2: entity-list text mixing a plain string and a link entity; a reply
            {
                "id": 2, "type": "message",
                "date_unixtime": "1700000200",
                "from": OTHER, "from_id": "user2",
                "text": ["see ", {"type": "link", "text": "http://x.example"},
                         " #cool @owner"],
                "text_entities": [
                    {"type": "plain", "text": "see "},
                    {"type": "link", "text": "http://x.example"},
                    {"type": "hashtag", "text": "#cool"},
                    {"type": "mention", "text": "@owner"},
                ],
                "reply_to_message_id": 1,
            },
            # 3: reply to message 2 (chain depth 2), from OWNER
            {
                "id": 3, "type": "message",
                "date_unixtime": "1700000300",
                "from": OWNER, "from_id": "user1",
                "text": "nice", "text_entities": [{"type": "plain", "text": "nice"}],
                "reply_to_message_id": 2,
            },
            # 4: a photo message (media, not a real text message)
            {
                "id": 4, "type": "message",
                "date_unixtime": "1700000400",
                "from": OTHER, "from_id": "user2",
                "text": "", "text_entities": [],
                "photo": "photos/photo_1.jpg", "photo_file_size": 1234,
                "width": 100, "height": 100,
            },
            # 5: a voice message
            {
                "id": 5, "type": "message",
                "date_unixtime": "1700000500",
                "from": OWNER, "from_id": "user1",
                "text": "", "text_entities": [],
                "file": "voice.ogg", "media_type": "voice_message",
                "duration_seconds": 3, "mime_type": "audio/ogg",
            },
            # 6: a service phone call (kept, carries duration)
            {
                "id": 6, "type": "service",
                "date_unixtime": "1700000600",
                "actor": OWNER, "actor_id": "user1",
                "action": "phone_call", "discard_reason": "hangup",
                "duration_seconds": 42,
                "text": "", "text_entities": [],
            },
            # 7: a service pin (dropped)
            {
                "id": 7, "type": "service",
                "date_unixtime": "1700000700",
                "actor": OTHER, "actor_id": "user2",
                "action": "pin_message", "message_id": 2,
                "text": "", "text_entities": [],
            },
        ],
    }


def _group_result():
    r = _result()
    r["type"] = "private_supergroup"
    return r


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #

def test_flatten_text_string_and_list():
    assert _flatten_text("plain") == "plain"
    assert _flatten_text(["a ", {"type": "link", "text": "b"}, " c"]) == "a b c"
    assert _flatten_text(None) == ""


def test_entity_counts_skips_plain():
    counts = _entity_counts([
        {"type": "plain", "text": "x"},
        {"type": "link", "text": "y"},
        {"type": "link", "text": "z"},
        {"type": "hashtag", "text": "#h"},
    ])
    assert counts == {"link": 2, "hashtag": 1}


def test_map_reactions_expands_recent():
    reacts = _map_reactions([{"type": "emoji", "count": 1, "emoji": "\U0001F44D",
                              "recent": [{"from": "Ann"}]}])
    assert reacts == [{"reaction": "\U0001F44D", "actor": "Ann"}]


# --------------------------------------------------------------------------- #
# parse_telegram_result — loader contract
# --------------------------------------------------------------------------- #

def test_parse_contract_and_seconds_to_ms():
    combined = parse_telegram_result(_result())
    assert combined["platform"] == "telegram"
    assert combined["is_group"] is False
    assert combined["title"] == OTHER
    assert combined["thread_path"] == "telegram/424242"
    assert {p["name"] for p in combined["participants"]} == {OWNER, OTHER}

    msgs = combined["messages"]
    # service pin dropped; phone-call service kept -> 6 messages
    assert len(msgs) == 6
    # seconds string -> ms int
    assert msgs[0]["timestamp_ms"] == 1700000000 * 1000
    # sorted ascending
    assert [m["timestamp_ms"] for m in msgs] == sorted(m["timestamp_ms"] for m in msgs)


def test_parse_message_field_mapping():
    msgs = {m["msg_id"]: m for m in parse_telegram_result(_result())["messages"]}
    # entity-list flattened
    assert "http://x.example" in msgs[2]["content"]
    assert msgs[2]["reply_to_id"] == 1
    assert msgs[2]["entities"] == {"link": 1, "hashtag": 1, "mention": 1}
    # edit converted to ms
    assert msgs[1]["edited_ms"] == 1700000100 * 1000
    # reaction mapped to Instagram shape
    assert msgs[1]["reactions"] == [{"reaction": "\U0001F44D", "actor": OTHER}]
    # media mapping
    assert msgs[4]["photos"] and msgs[5]["audio_files"]
    # phone call service -> call message with duration
    assert msgs[6]["call_duration"] == 42
    assert msgs[6]["content"] == ""


def test_group_type_detection():
    assert parse_telegram_result(_group_result())["is_group"] is True


# --------------------------------------------------------------------------- #
# load_telegram_chat — normalized output
# --------------------------------------------------------------------------- #

def _write_result(tmp_path, data):
    chat_dir = tmp_path / "ChatExport"
    chat_dir.mkdir()
    (chat_dir / "result.json").write_text(json.dumps(data), encoding="utf-8")
    return chat_dir


def test_load_telegram_chat_normalized(tmp_path):
    chat_dir = _write_result(tmp_path, _result())
    data = load_telegram_chat(str(chat_dir))
    assert data["platform"] == "telegram"
    # normalizer added formatted_timestamp / language / type
    m0 = data["messages"][0]
    assert "formatted_timestamp" in m0 and "language" in m0
    # text message is a "real" message; call/photo/voice are not
    reals = [m for m in data["messages"] if is_real_message(m)]
    assert all(m["content"] for m in reals)
    # the phone-call message survived (media/system) but is excluded from real
    calls = [m for m in data["messages"] if m.get("call_duration")]
    assert calls and not is_real_message(calls[0])


# --------------------------------------------------------------------------- #
# Platform detection + discovery (main.py)
# --------------------------------------------------------------------------- #

def test_detect_platform(tmp_path):
    tg = _write_result(tmp_path, _result())
    assert main.detect_platform(str(tg)) == "telegram"
    ig = tmp_path / "ig_chat"
    ig.mkdir()
    (ig / "message_1.json").write_text("{}", encoding="utf-8")
    assert main.detect_platform(str(ig)) == "instagram"


def test_discovery_mixed_layout(tmp_path):
    # Chats/Telegram/<export>/result.json  +  Chats/Instagram/<export>/inbox/<chat>
    chats = tmp_path / "Chats"
    tg = chats / "Telegram" / "Export1"
    tg.mkdir(parents=True)
    (tg / "result.json").write_text(json.dumps(_result()), encoding="utf-8")

    inbox = chats / "Instagram" / "ig-export"
    inbox = inbox.joinpath(*main._INBOX_SUFFIX) / "alice_1"
    inbox.mkdir(parents=True)
    (inbox / "message_1.json").write_text(
        json.dumps({"participants": [{"name": OWNER}, {"name": "Alice"}],
                    "messages": [], "title": "Alice"}), encoding="utf-8")

    discovered = main.discover_all_chats(str(tmp_path))
    dirs = {Path(d).name for _, d in discovered}
    assert "Export1" in dirs and "alice_1" in dirs
    plats = {main.detect_platform(d) for _, d in discovered}
    assert plats == {"telegram", "instagram"}


def test_telegram_participants_in_owner_pool(tmp_path):
    tg = _write_result(tmp_path, _result())
    parts = main._chat_participants(str(tg))
    assert OWNER in parts and OTHER in parts


def test_import_zip_routes_telegram(tmp_path):
    import zipfile
    zip_path = tmp_path / "ChatExport_2026-04-26.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("result.json", json.dumps(_result()))
    target = main.import_zip(str(zip_path), tmp_path)
    assert Path(target) == tmp_path / "Chats" / "Telegram" / "ChatExport_2026-04-26"
    assert (Path(target) / "result.json").exists()


# --------------------------------------------------------------------------- #
# Telegram-exclusive metrics (dashboard_export)
# --------------------------------------------------------------------------- #

def test_has_telegram_fields():
    combined = parse_telegram_result(_result())
    assert has_telegram_fields(combined["messages"]) is True
    assert has_telegram_fields([{"sender_name": "A", "content": "hi",
                                 "timestamp_ms": 1}]) is False


def test_telegram_signals_compute():
    msgs = load_telegram_chat_messages()
    sig = build_telegram_signals(msgs, [OWNER, OTHER])
    pu = sig["per_user"]
    # Owner sent 2 real text msgs (id1 edited, id3 reply); edit_rate 1/2
    assert pu[OWNER]["msgs"] == 2
    assert pu[OWNER]["edits"] == 1
    assert pu[OWNER]["edit_rate"] == 0.5
    # id3 is a reply -> owner reply_share 1/2
    assert pu[OWNER]["reply_share"] == 0.5
    # Friend msg id2 carries link+hashtag+mention entities
    assert pu[OTHER]["links"] == 1
    assert pu[OTHER]["hashtags"] == 1
    assert pu[OTHER]["mentions"] == 1
    # reply-depth histogram: id2 depth1, id3 depth2
    assert sig["reply_depth"].get("1") == 1
    assert sig["reply_depth"].get("2") == 1


def load_telegram_chat_messages():
    combined = parse_telegram_result(_result())
    # normalize so is_real_message works as in the real pipeline
    from src.normalizer import normalize_chat
    return normalize_chat(combined)["messages"]


def test_daily_edits_counted():
    msgs = load_telegram_chat_messages()
    daily = build_daily_aggregates(msgs, [OWNER, OTHER])
    total_edits = sum(cell.get("edits", 0)
                      for day in daily.values() for cell in day.values())
    assert total_edits == 1


def test_payload_carries_platform_and_telegram(tmp_path):
    combined = parse_telegram_result(_result())
    from src.normalizer import normalize_chat
    normalized = normalize_chat(combined)
    normalized["platform"] = "telegram"
    payload = build_chat_payload("Owner & Friend", normalized, {})
    assert payload["platform"] == "telegram"
    assert "telegram" in payload
    assert payload["telegram"]["per_user"][OWNER]["edit_rate"] == 0.5


def test_instagram_payload_has_no_telegram():
    msgs = [{"sender_name": OWNER, "timestamp_ms": 1700000000000,
             "content": "hi", "language": "english"}]
    normalized = {"participants": [{"name": OWNER}, {"name": OTHER}],
                  "messages": msgs}
    payload = build_chat_payload("IG", normalized, {})
    assert payload["platform"] == "instagram"
    assert "telegram" not in payload
