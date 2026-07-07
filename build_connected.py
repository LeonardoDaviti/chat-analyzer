#!/usr/bin/env python3
"""CLI entry point for Connected Analysis — owner-centric cross-chat profile.

Discovers every Instagram chat under ``Chats/Instagram`` (v1 is Instagram-only),
computes the owner-centric metrics defined in ``docs/CONNECTED_ANALYSIS.md``, and
writes ``Dashboard/data/connected.js`` (lazy ``window.CONNECTED = {...}`` script
injection, same convention as the other data files) plus a human-inspectable
``Dashboard/data/connected.json``.

Usage:
    python build_connected.py [--chats-dir Chats] [--exclude a,b,c]
                              [--dash-dir Dashboard] [--min-msgs 30]
                              [--min-replies 50]

``--exclude`` takes comma-separated substrings matched against the chat folder
name (default ``á,ð,â`` — the mojibake leftovers, same as the other CLIs).

Privacy: prints counts / dates / top contact names only — never message text.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from src.connected_export import (
    discover_instagram_chats,
    load_chat,
    dedup_chats,
    build_connected_data,
    write_outputs,
)
from src.timeutil import DEFAULT_TIMEZONE


def _detect_owner(chats) -> Optional[str]:
    """Owner = most common participant across chats (reuse main's logic)."""
    participant_lists = [c.participants for c in chats]
    try:
        from main import detect_owner_from_participants
        return detect_owner_from_participants(participant_lists)
    except Exception:
        # Local fallback mirroring detect_owner_from_participants.
        from collections import Counter
        counter: Counter = Counter()
        for parts in participant_lists:
            for name in set(parts):
                counter[name] += 1
        return counter.most_common(1)[0][0] if counter else None


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Build Connected Analysis (owner cross-chat profile).')
    p.add_argument('--chats-dir', default='Chats', help='root Chats directory (default: Chats)')
    p.add_argument('--exclude', default='á,ð,â',
                   help='comma-separated substrings; drop matching chat folders')
    p.add_argument('--dash-dir', default='Dashboard', help='dashboard output dir (default: Dashboard)')
    p.add_argument('--min-msgs', type=int, default=30, help='min owner msgs to un-gate a contact')
    p.add_argument('--min-replies', type=int, default=50, help='min replies to rank latency')
    p.add_argument('--timezone', default=DEFAULT_TIMEZONE)
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    excludes = [s.strip().lower() for s in args.exclude.split(',') if s.strip()]

    chat_dirs = discover_instagram_chats(args.chats_dir)
    if not chat_dirs:
        print(f'No Instagram chats found under {args.chats_dir}/Instagram', file=sys.stderr)
        return 1

    kept_dirs, excluded = [], 0
    for d in chat_dirs:
        if any(e in d.name.lower() for e in excludes):
            excluded += 1
        else:
            kept_dirs.append(d)

    print(f'Discovered {len(chat_dirs)} Instagram chat(s); '
          f'{len(kept_dirs)} kept, {excluded} excluded.')

    taken: set = set()
    chats = []
    for d in kept_dirs:
        c = load_chat(d, taken, args.timezone)
        if c is not None and c.recs:
            chats.append(c)
    chats, dropped = dedup_chats(chats)
    excluded += dropped
    print(f'Loaded {len(chats)} chat(s) with messages '
          f'({dropped} duplicate thread_path copies dropped).')

    owner = _detect_owner(chats)
    if not owner:
        print('Could not detect owner.', file=sys.stderr)
        return 1
    print(f'Owner detected: {owner}')

    payload = build_connected_data(
        chats, owner, timezone=args.timezone,
        min_msgs=args.min_msgs, min_replies=args.min_replies,
        excluded_count=excluded,
    )

    js_path, json_path = write_outputs(payload, args.dash_dir)

    # ---- counts-only sanity report ---- #
    t = payload['totals']
    att = payload['attention']
    fn = payload['funnel']
    print('\n=== Connected Analysis sanity report (counts only) ===')
    print(f"  range:            {payload['range']['first_day']} .. {payload['range']['last_day']}")
    print(f"  chats included:   {t['chats_included']}  (dyads {t['dyads']}, groups {t['groups']})")
    print(f"  chats excluded:   {t['chats_excluded']}")
    print(f"  contacts:         {t['contacts']}")
    print(f"  messages sent:    {t['messages_sent']}   received: {t['messages_received']}")
    print(f"  reciprocity:      {payload['reciprocity']['ratio']}")
    print(f"  bursts:           {att['bursts']['count']}  "
          f"(median {att['bursts']['duration_min']['median']} min, "
          f"p90 {att['bursts']['duration_min']['p90']}, max {att['bursts']['duration_min']['max']})")
    print(f"  parallel rate:    {att['parallel_texting_rate']}  "
          f"switch/hr: {att['chat_switch']['switches_per_active_hour']}")
    print(f"  session types:    {payload['sessions_typed']['totals']}")
    print(f"  funnel:           met {fn['stages']['met']} -> talked_again "
          f"{fn['stages']['talked_again']} -> recurring {fn['stages']['recurring']}")
    print(f"  groups lane:      {payload['groups']['count']} groups, "
          f"{payload['groups']['messages_owner']} owner msgs")
    top5 = payload['leaderboards']['by_sent_share'][:5]
    print('  top-5 by sent share:')
    for row in top5:
        print(f"    {row['name']!r}: {row['sent']} ({row['share']:.1%})")
    print(f"\n  wrote {js_path}")
    print(f"  wrote {json_path}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
