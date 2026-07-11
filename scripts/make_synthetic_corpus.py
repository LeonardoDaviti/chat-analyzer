#!/usr/bin/env python3
"""Generate a fully SYNTHETIC but realistic-looking chat corpus.

Everything here is invented — the names, the words, the timestamps. There is
NO real message content anywhere in this file, so its output is safe to feed
through the pipeline and screenshot for the README (the project's #1 privacy
rule: synthetic corpora only).

It writes proper export *structures* under a target directory:

    <out>/Chats/Instagram/synthetic-instagram/your_instagram_activity/messages/inbox/<chat>/message_1.json
    <out>/Chats/Telegram/<chat>/result.json

so the normal ``discover_all_chats`` → ``run_all`` → dashboard/connected/
insights path picks them up exactly like a real import. Both platforms are
represented; volumes, date ranges and emoji vary per chat so the dashboard
has something interesting to draw.

Usage:
    python scripts/make_synthetic_corpus.py --out /tmp/chat-analyzer-demo
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

# The invented account owner — present in every chat (so owner auto-detection
# and the Connected profile work), with different display names per platform
# to exercise the per-platform owner logic.
OWNER_IG = "Jordan Blake"
OWNER_TG = "Jordan"

# Invented contacts. (contact_name, platform, approx_msgs, start_days_ago,
#   span_days, owner_share, emoji_rate, question_rate, night_rate)
INSTAGRAM_CONTACTS = [
    ("Alex Rivera", 1400, 300, 300, 0.58, 0.22, 0.14, 0.12),
    ("Mara Chen", 640, 210, 180, 0.38, 0.10, 0.20, 0.30),
    ("Sofia Duarte", 300, 120, 95, 0.50, 0.35, 0.09, 0.06),
]
TELEGRAM_CONTACTS = [
    ("Danil Petrov", 900, 260, 240, 0.47, 0.18, 0.16, 0.20),
    ("Yuki Tanaka", 420, 150, 130, 0.55, 0.28, 0.11, 0.09),
]

# Invented small-talk fragments — deliberately generic, no real messages.
_OPENERS = [
    "hey", "morning", "yo", "hi hi", "you around?", "quick q",
    "guess what", "ok so", "random but", "update:",
]
_LINES = [
    "just got back home", "that meeting ran long again", "coffee was great today",
    "the weather turned finally", "watched that show you mentioned",
    "still stuck on this bug", "lunch was underwhelming honestly",
    "found a new spot downtown", "packing for the trip", "so tired lol",
    "the playlist is unreal", "reading something good rn",
    "cleaned the whole apartment", "gym was brutal", "cooked pasta again",
]
_QUESTIONS = [
    "you free this weekend?", "did you send it yet?", "how'd the thing go?",
    "wanna grab food later?", "what time works for you?", "is that today?",
    "did you see my message?", "coming to the thing?", "which one do you prefer?",
]
_LAUGHS = ["haha", "lol", "hahaha", "lmao", "😂", "😅"]
_EMOJI = ["🙂", "🔥", "✨", "👀", "🎉", "💀", "🥲", "🙌", "☕", "🌧️", "❤️", "😴"]
_CLOSERS = ["ttyl", "talk soon", "gnight", "later!", "ok cool", "sounds good"]


def _sentence(rng: random.Random, emoji_rate: float, question_rate: float) -> str:
    """One invented message line, no real content."""
    roll = rng.random()
    if roll < question_rate:
        text = rng.choice(_QUESTIONS)
    elif roll < question_rate + 0.12:
        text = rng.choice(_LAUGHS)
    elif roll < question_rate + 0.20:
        text = rng.choice(_OPENERS)
    elif roll < question_rate + 0.28:
        text = rng.choice(_CLOSERS)
    else:
        text = rng.choice(_LINES)
    if rng.random() < emoji_rate:
        text = f"{text} {rng.choice(_EMOJI)}"
    return text


def _timestamps(rng: random.Random, n: int, start_days_ago: int,
                span_days: int, night_rate: float) -> list[int]:
    """Generate n sorted epoch-ms timestamps clustered into daily sessions."""
    now = datetime.now()
    start = now - timedelta(days=start_days_ago)
    out: list[int] = []
    produced = 0
    day = 0
    while produced < n and day <= span_days:
        # Not every day has a conversation.
        if rng.random() < 0.55:
            base = start + timedelta(days=day)
            # Night vs daytime session.
            if rng.random() < night_rate:
                hour = rng.choice([0, 1, 2, 23])
            else:
                hour = rng.randint(8, 22)
            t = base.replace(hour=hour, minute=rng.randint(0, 59),
                             second=rng.randint(0, 59))
            burst = min(rng.randint(4, 40), n - produced)
            for _ in range(burst):
                out.append(int(t.timestamp() * 1000))
                t += timedelta(seconds=rng.randint(20, 900))
                produced += 1
        day += 1
    # If we ran out of days before hitting n, top up on the last day.
    while produced < n:
        out.append(out[-1] + rng.randint(20, 900) * 1000 if out else
                   int(start.timestamp() * 1000))
        produced += 1
    out.sort()
    return out


def _sender_sequence(rng: random.Random, n: int, owner: str, contact: str,
                     owner_share: float) -> list[str]:
    """A believable back-and-forth sender sequence with the given owner share."""
    seq: list[str] = []
    for _ in range(n):
        if seq and rng.random() < 0.45:
            seq.append(seq[-1])  # bursts: same sender twice in a row sometimes
        else:
            seq.append(owner if rng.random() < owner_share else contact)
    return seq


def _messages(rng: random.Random, owner: str, contact: str, count: int,
              start_days_ago: int, span_days: int, owner_share: float,
              emoji_rate: float, question_rate: float, night_rate: float):
    ts = _timestamps(rng, count, start_days_ago, span_days, night_rate)
    senders = _sender_sequence(rng, count, owner, contact, owner_share)
    msgs = []
    for i in range(count):
        msgs.append({
            "sender": senders[i],
            "ts": ts[i],
            "text": _sentence(rng, emoji_rate, question_rate),
        })
    return msgs


def _write_instagram(inbox: Path, owner: str, contact: str, msgs: list) -> None:
    slug = contact.lower().replace(" ", "") + f"_{abs(hash(contact)) % 10**9}"
    chat_dir = inbox / slug
    chat_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "participants": [{"name": contact}, {"name": owner}],
        "messages": [
            {"sender_name": m["sender"], "timestamp_ms": m["ts"],
             "content": m["text"]}
            for m in msgs
        ],
        "title": contact,
        "thread_path": f"inbox/{slug}",
    }
    (chat_dir / "message_1.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_telegram(chats_root: Path, owner: str, contact: str, msgs: list,
                    rng: random.Random) -> None:
    chat_dir = chats_root / "Telegram" / f"ChatExport_{contact.replace(' ', '')}"
    chat_dir.mkdir(parents=True, exist_ok=True)
    tg_msgs = []
    for i, m in enumerate(msgs, start=1):
        secs = m["ts"] // 1000
        entry = {
            "id": i,
            "type": "message",
            "date": datetime.fromtimestamp(secs).isoformat(),
            "date_unixtime": str(secs),
            "from": m["sender"],
            "from_id": "user1" if m["sender"] == owner else "user2",
            "text": m["text"],
            "text_entities": [{"type": "plain", "text": m["text"]}],
        }
        # A sprinkle of Telegram-only signals: edits, replies, reactions, stickers.
        if rng.random() < 0.05:
            entry["edited_unixtime"] = str(secs + 60)
        if i > 1 and rng.random() < 0.12:
            entry["reply_to_message_id"] = i - 1
        if rng.random() < 0.08:
            entry["reactions"] = [{
                "type": "emoji", "count": 1, "emoji": rng.choice(_EMOJI),
                "recent": [{"from": owner if m["sender"] != owner else contact,
                            "from_id": "user9", "date": entry["date"]}],
            }]
        if rng.random() < 0.03:
            entry["media_type"] = "sticker"
            entry["sticker_emoji"] = rng.choice(_EMOJI)
        tg_msgs.append(entry)
    result = {
        "name": contact,
        "type": "personal_chat",
        "id": abs(hash(contact)) % 10**9,
        "messages": tg_msgs,
    }
    (chat_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8")


def build_corpus(out: Path, seed: int = 1234) -> Path:
    """Create the full synthetic corpus under ``out`` and return ``out/Chats``."""
    rng = random.Random(seed)
    chats_root = out / "Chats"
    inbox = (chats_root / "Instagram" / "synthetic-instagram" /
             "your_instagram_activity" / "messages" / "inbox")
    inbox.mkdir(parents=True, exist_ok=True)

    for (name, count, start, span, share, emoji, q, night) in INSTAGRAM_CONTACTS:
        msgs = _messages(rng, OWNER_IG, name, count, start, span, share,
                         emoji, q, night)
        _write_instagram(inbox, OWNER_IG, name, msgs)

    for (name, count, start, span, share, emoji, q, night) in TELEGRAM_CONTACTS:
        msgs = _messages(rng, OWNER_TG, name, count, start, span, share,
                         emoji, q, night)
        _write_telegram(chats_root, OWNER_TG, name, msgs, rng)

    return chats_root


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Generate a synthetic chat corpus.")
    ap.add_argument("--out", required=True,
                    help="target directory (Chats/ is created inside it)")
    ap.add_argument("--seed", type=int, default=1234,
                    help="RNG seed for reproducible corpora")
    args = ap.parse_args(argv)
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    chats_root = build_corpus(out, seed=args.seed)
    total = (len(INSTAGRAM_CONTACTS) + len(TELEGRAM_CONTACTS))
    print(f"Synthetic corpus written: {total} chats under {chats_root}")
    print("  Instagram:", ", ".join(c[0] for c in INSTAGRAM_CONTACTS))
    print("  Telegram :", ", ".join(c[0] for c in TELEGRAM_CONTACTS))


if __name__ == "__main__":
    main()
