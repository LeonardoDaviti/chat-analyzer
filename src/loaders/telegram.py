"""Telegram Desktop export loader.

Turns a Telegram ``result.json`` (Settings → Advanced → Export Telegram Data →
JSON) into the same normalized chat dict the Instagram pipeline consumes, so a
Telegram chat flows through the identical normalizer → sessions → metrics →
dashboard path.

Verified against real exports:

  Top level  ``{name, type, id, messages}``.
    ``type`` ∈ {personal_chat, private_group, private_supergroup, …}; anything
    that is not ``personal_chat`` / ``saved_messages`` is treated as a group.

  Messages   ``type`` ∈ {"message", "service"}.
    ``date_unixtime`` is a STRING of epoch *seconds* → ms for ``timestamp_ms``.
    ``text`` is a string OR a list mixing strings and ``{type, text, …}`` entity
    dicts → flattened by concatenating the string parts and each entity's text.
    ``reactions`` are aggregated per emoji ``{type, count, emoji, recent:[{from,
    from_id, date}]}`` → expanded to Instagram's ``[{reaction, actor}]`` shape.
    Phone calls appear only as ``service`` messages with ``action == 'phone_call'``
    carrying ``duration_seconds`` / ``discard_reason``.

Telegram exports are clean UTF-8, so running them through the Instagram
normalizer (whose latin-1 repair is a no-op on clean text) is safe and gives
uniform ``formatted_timestamp`` / ``language`` / ``type`` fields.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from src.normalizer import normalize_chat_from_data


# Telegram chat ``type`` values that represent a 1:1 (non-group) conversation.
_PERSONAL_TYPES = {"personal_chat", "saved_messages", "bot_chat"}

# Which ``media_type`` maps onto which Instagram attachment channel.
_VIDEO_MEDIA = {"video_file", "video_message", "animation"}
_VOICE_MEDIA = {"voice_message", "audio_file"}


# --------------------------------------------------------------------------- #
# Small field helpers
# --------------------------------------------------------------------------- #

def _flatten_text(text: Any) -> str:
    """Flatten Telegram ``text`` (string OR list of strings/entity dicts)."""
    if isinstance(text, str):
        return text
    if isinstance(text, list):
        parts: List[str] = []
        for part in text:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text", "") or ""))
        return "".join(parts)
    return ""


def _entity_counts(text_entities: Any) -> Dict[str, int]:
    """Count non-plain entity types (link, hashtag, mention, …) on a message."""
    counts: Dict[str, int] = {}
    for e in text_entities or []:
        if not isinstance(e, dict):
            continue
        t = e.get("type")
        if not t or t == "plain":
            continue
        counts[t] = counts.get(t, 0) + 1
    return counts


def _as_int(value: Any) -> int | None:
    """Best-effort int coercion; ``None`` when the value is missing/unparseable."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _map_reactions(reactions: Any) -> List[Dict[str, Any]]:
    """Expand Telegram's aggregated reactions to ``[{reaction, actor, date?}]``.

    Each aggregated entry is ``{type, count, emoji, recent:[{from, from_id,
    date}]}``. We emit one Instagram-shaped reaction per named recent actor; if a
    reaction has a count but no named actors, we still emit ``count`` entries
    with a blank actor so reactions-*received* is counted on the message owner.

    The reactor's ``date`` (ISO local string, 100% coverage per DATA_AUDIT §2 P3)
    is carried as ``date`` in epoch ms — converted the same way message
    timestamps are — so reaction latency becomes computable downstream. The emoji
    is carried verbatim (no lowering/stripping) so its identity survives for P5.
    """
    out: List[Dict[str, Any]] = []
    for r in reactions or []:
        if not isinstance(r, dict):
            continue
        emoji = r.get("emoji") or r.get("document_id") or r.get("type") or ""
        recent = r.get("recent") or []
        if recent:
            for rec in recent:
                rec = rec or {}
                entry: Dict[str, Any] = {"reaction": emoji,
                                         "actor": rec.get("from", "") or ""}
                # P3: preserve the reaction timestamp as epoch ms.
                if rec.get("date") is not None:
                    ts = _ts_ms({"date": rec.get("date")})
                    if ts:
                        entry["date"] = ts
                out.append(entry)
        else:
            try:
                n = int(r.get("count", 0) or 0)
            except (TypeError, ValueError):
                n = 0
            for _ in range(max(0, n)):
                out.append({"reaction": emoji, "actor": ""})
    return out


def _sender_name(name: Any, sender_id: Any) -> str:
    """Resolve a display sender name, falling back for deleted/anonymous users.

    Telegram messages from deleted accounts have a null ``from`` but keep a
    stable ``from_id`` (e.g. ``"user8054914236"``); using it preserves identity
    without ever producing an empty name (which downstream code index-errors on).
    """
    if name:
        return str(name)
    if sender_id:
        return str(sender_id)
    return "Unknown"


def _ts_ms(msg: Dict[str, Any]) -> int:
    """``date_unixtime`` (string epoch seconds) → int epoch milliseconds."""
    raw = msg.get("date_unixtime")
    if raw is not None:
        try:
            return int(raw) * 1000
        except (TypeError, ValueError):
            pass
    # Fallback: ISO ``date`` (local, no tz) — best effort.
    date = msg.get("date")
    if isinstance(date, str) and date:
        try:
            from datetime import datetime
            return int(datetime.fromisoformat(date).timestamp() * 1000)
        except (TypeError, ValueError):
            pass
    return 0


def _apply_media(out: Dict[str, Any], msg: Dict[str, Any]) -> None:
    """Map Telegram media onto the attachment fields the pipeline reads."""
    media_type = msg.get("media_type")
    file_ref = msg.get("file") or msg.get("thumbnail") or ""

    if msg.get("photo"):
        out["photos"] = [{"uri": str(msg.get("photo"))}]
    if media_type in _VIDEO_MEDIA:
        out["videos"] = [{"uri": str(file_ref)}]
    elif media_type in _VOICE_MEDIA:
        out["audio_files"] = [{"uri": str(file_ref)}]

    # P1: carry voice/round-video/audio playback length (seconds). Stickers and
    # photos have no duration; calls are handled on their own paths.
    if media_type in _VIDEO_MEDIA or media_type in _VOICE_MEDIA:
        dur = _as_int(msg.get("duration_seconds"))
        if dur is not None:
            out["media_duration_s"] = dur

    # Stickers: dedicated media_type or a bare sticker emoji.
    if media_type == "sticker" or msg.get("sticker_emoji"):
        out["sticker"] = {"emoji": msg.get("sticker_emoji", "")}

    # Forwarded content is Telegram's analogue of an Instagram "share".
    fwd = msg.get("forwarded_from")
    if fwd:
        out["share"] = {"link": "", "forwarded": True}
        out["forwarded_from"] = fwd


def _build_message(msg: Dict[str, Any]) -> Dict[str, Any] | None:
    """Convert one Telegram message/service entry to a pipeline message.

    Returns ``None`` for service entries we deliberately drop (everything except
    phone calls, which are carried as call messages so durations survive).
    """
    mtype = msg.get("type")

    if mtype == "service":
        if msg.get("action") != "phone_call":
            return None
        # Phone call: empty content → normalizer marks language='media' so it is
        # excluded from real-message channels, but call_duration is available to
        # the media/call metrics (mirrors Instagram calls).
        out: Dict[str, Any] = {
            "sender_name": _sender_name(msg.get("actor"), msg.get("actor_id")),
            "timestamp_ms": _ts_ms(msg),
            "content": "",
            "call_duration": msg.get("duration_seconds"),
            "msg_id": msg.get("id"),
        }
        # P2: talk-time as int seconds + outcome, on the service-message path.
        dur = _as_int(msg.get("duration_seconds"))
        if dur is not None:
            out["call_duration_s"] = dur
        if msg.get("discard_reason"):
            out["call_discard_reason"] = str(msg.get("discard_reason"))
        return out

    # Regular message.
    content = _flatten_text(msg.get("text", ""))
    out = {
        "sender_name": _sender_name(msg.get("from"), msg.get("from_id")),
        "timestamp_ms": _ts_ms(msg),
        "content": content,
        "msg_id": msg.get("id"),
    }

    reactions = _map_reactions(msg.get("reactions"))
    if reactions:
        out["reactions"] = reactions

    # Phone call reported on a regular message (media_type variant), if present.
    if msg.get("media_type") == "phone_call":
        out["call_duration"] = msg.get("duration_seconds")
        # P2: same call fields must survive on this path too.
        dur = _as_int(msg.get("duration_seconds"))
        if dur is not None:
            out["call_duration_s"] = dur
        if msg.get("discard_reason"):
            out["call_discard_reason"] = str(msg.get("discard_reason"))

    _apply_media(out, msg)

    # ---- Telegram-only extras (Instagram messages simply won't have them) --- #
    if msg.get("reply_to_message_id") is not None:
        out["reply_to_id"] = msg.get("reply_to_message_id")
    if msg.get("edited_unixtime") is not None:
        try:
            out["edited_ms"] = int(msg["edited_unixtime"]) * 1000
        except (TypeError, ValueError):
            pass
    elif msg.get("edited"):
        out["edited_ms"] = _ts_ms({"date": msg.get("edited")})
    entities = _entity_counts(msg.get("text_entities"))
    if entities:
        out["entities"] = entities

    return out


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def is_telegram_export(data: Dict[str, Any]) -> bool:
    """Heuristic: does a parsed JSON object look like a Telegram export?"""
    return (
        isinstance(data, dict)
        and "messages" in data
        and "type" in data
        and isinstance(data.get("messages"), list)
    )


def parse_telegram_result(data: Dict[str, Any]) -> Dict[str, Any]:
    """Turn a parsed ``result.json`` into a pre-normalization chat dict.

    Output shape matches what the Instagram combiner produces:
    ``{title, participants:[{name}], thread_path, messages, is_group,
    platform:'telegram'}`` with messages sorted by timestamp.
    """
    chat_type = data.get("type", "personal_chat")
    is_group = chat_type not in _PERSONAL_TYPES

    messages: List[Dict[str, Any]] = []
    senders: List[str] = []
    seen_senders = set()
    for raw in data.get("messages", []) or []:
        m = _build_message(raw)
        if m is None:
            continue
        messages.append(m)
        name = m.get("sender_name")
        if name and name not in seen_senders:
            seen_senders.add(name)
            senders.append(name)

    messages.sort(key=lambda m: m.get("timestamp_ms", 0))

    return {
        "title": data.get("name") or f"Telegram {data.get('id', '')}",
        "participants": [{"name": s} for s in senders],
        "thread_path": f"telegram/{data.get('id', '')}",
        "is_group": is_group,
        "chat_type": chat_type,
        "platform": "telegram",
        "messages": messages,
    }


def load_telegram_chat(chat_dir: str) -> Dict[str, Any]:
    """Load + normalize a Telegram chat directory (containing ``result.json``).

    Returns normalized chat data in the exact shape ``load_chat_from_dir``
    returns for Instagram, with ``platform='telegram'`` carried through.
    """
    result_file = Path(chat_dir) / "result.json"
    if not result_file.exists():
        raise FileNotFoundError(f"No result.json in {chat_dir}")

    with open(result_file, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    combined = parse_telegram_result(data)
    normalized = normalize_chat_from_data(combined)
    # normalize_chat_from_data copies unknown top-level keys through, but make
    # the platform/group markers explicit and authoritative.
    normalized["platform"] = "telegram"
    normalized["is_group"] = combined["is_group"]
    normalized["chat_type"] = combined["chat_type"]
    return normalized


def telegram_participants(chat_dir: str) -> List[str]:
    """Cheap participant list (unique senders) for a Telegram chat directory."""
    result_file = Path(chat_dir) / "result.json"
    if not result_file.exists():
        return []
    try:
        with open(result_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    names: List[str] = []
    seen = set()
    for raw in data.get("messages", []) or []:
        if raw.get("type") == "service":
            if raw.get("action") != "phone_call":
                continue
            name = _sender_name(raw.get("actor"), raw.get("actor_id"))
        else:
            name = _sender_name(raw.get("from"), raw.get("from_id"))
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def telegram_thread_path(chat_dir: str) -> str:
    """The synthesized ``thread_path`` for a Telegram chat directory."""
    result_file = Path(chat_dir) / "result.json"
    if not result_file.exists():
        return ""
    try:
        with open(result_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return ""
    return f"telegram/{data.get('id', '')}"


def telegram_title(chat_dir: str) -> str:
    """Display title (top-level ``name``) for a Telegram chat directory."""
    result_file = Path(chat_dir) / "result.json"
    if not result_file.exists():
        return Path(chat_dir).name
    try:
        with open(result_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return Path(chat_dir).name
    return data.get("name") or Path(chat_dir).name
