#!/usr/bin/env python3
"""CLI entry point for Connected Analysis — owner-centric cross-chat profile.

Builds up to three variants of the owner profile:

* ``instagram`` — every Instagram chat, merged, owner = Instagram handle.
* ``telegram``  — every Telegram chat, merged, owner = Telegram handle.
* ``all``       — Instagram + Telegram merged into ONE cross-platform owner
  stream. The two owner handles are treated as the same human; contacts are NOT
  merged across platforms (a person you talk to on both appears twice, once per
  platform). See ``docs/CONNECTED_ANALYSIS.md``.

Each variant is written to ``Dashboard/data/connected_<variant>.js`` (lazy
``window.CONNECTED_V["<variant>"] = {...}`` script injection) plus a pretty
``connected_<variant>.json``.

Usage:
    python build_connected.py [--platform instagram|telegram|all|everything]
                              [--chats-dir Chats] [--exclude a,b,c]
                              [--dash-dir Dashboard] [--min-msgs 30]
                              [--min-replies 50]

``--platform`` selects which variant(s) to build (default / ``everything``:
build all three). ``--exclude`` takes comma-separated substrings matched against
the chat folder name (default ``á,ð,â`` — the mojibake leftovers).

Privacy: prints counts / dates / top contact names only — never message text.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.connected_export import (
    Chat,
    discover_instagram_chats,
    discover_telegram_chats,
    load_chat,
    load_telegram_chat,
    dedup_chats,
    build_connected_data,
    write_variant_outputs,
    load_identities,
)
from src.timeutil import DEFAULT_TIMEZONE


def _detect_owner(chats: List[Chat]) -> Optional[str]:
    """Owner = most common participant across a platform's chats.

    Prefers ``main.detect_owner_from_participants`` (kept read-only) but falls
    back to a local re-implementation because ``main`` is being refactored.
    """
    participant_lists = [c.participants for c in chats]
    try:
        from main import detect_owner_from_participants
        owner = detect_owner_from_participants(participant_lists)
        if owner:
            return owner
    except Exception:
        pass
    counter: Counter = Counter()
    for parts in participant_lists:
        for name in set(parts):
            counter[name] += 1
    return counter.most_common(1)[0][0] if counter else None


def _detect_telegram_owner(chats: List[Chat]) -> Optional[str]:
    """Owner across Telegram chats: most-common participant, with a title-based
    tie-break.

    Telegram Desktop names a 1:1 export after the CONTACT, so with a single chat
    both participants tie on frequency; the owner is then the participant that is
    never itself a chat title (the contact).
    """
    counter: Counter = Counter()
    titles = set()
    for c in chats:
        titles.add(c.name)
        for name in set(c.participants):
            counter[name] += 1
    if not counter:
        return None
    ranked = counter.most_common()
    top = ranked[0][1]
    tied = [n for n, ct in ranked if ct == top]
    if len(tied) == 1:
        return tied[0]
    non_title = [n for n in tied if n not in titles]
    return non_title[0] if len(non_title) == 1 else tied[0]


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Build Connected Analysis (owner cross-chat profile).')
    p.add_argument('--platform', default='everything',
                   choices=['instagram', 'telegram', 'all', 'everything'],
                   help='which variant(s) to build (default: everything = all three)')
    p.add_argument('--chats-dir', default='Chats', help='root Chats directory (default: Chats)')
    p.add_argument('--exclude', default='á,ð,â',
                   help='comma-separated substrings; drop matching chat folders')
    p.add_argument('--dash-dir', default='Dashboard', help='dashboard output dir (default: Dashboard)')
    p.add_argument('--min-msgs', type=int, default=30, help='min owner msgs to un-gate a contact')
    p.add_argument('--min-replies', type=int, default=50, help='min replies to rank latency')
    p.add_argument('--timezone', default=DEFAULT_TIMEZONE)
    return p.parse_args(argv)


def _load_hidden(dash_dir: str) -> set:
    """Chat ids the user hid in the dashboard (Dashboard/data/hidden.json).

    Single source of truth shared with build_insights.py: hidden chats are
    excluded from the Connected owner profile on the next re-analyze.
    """
    path = Path(dash_dir) / 'data' / 'hidden.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return set()
    return {x for x in data if isinstance(x, str)} if isinstance(data, list) else set()


def _load_platform(kind: str, chat_dirs: List[Path], excludes: List[str],
                   timezone: str, hidden: Optional[set] = None) -> Tuple[List[Chat], int]:
    """Filter, load and dedup a platform's chat dirs. Returns (chats, excluded).

    Chats whose slug id is in ``hidden`` are dropped (and counted as excluded).
    """
    hidden = hidden or set()
    kept_dirs, excluded = [], 0
    for d in chat_dirs:
        if any(e in d.name.lower() for e in excludes):
            excluded += 1
        else:
            kept_dirs.append(d)

    loader = load_chat if kind == 'instagram' else load_telegram_chat
    taken: set = set()
    chats: List[Chat] = []
    for d in kept_dirs:
        c = loader(d, taken, timezone)
        if c is not None and c.recs:
            if c.chat_id in hidden:
                excluded += 1
                continue
            chats.append(c)
    chats, dropped = dedup_chats(chats)
    excluded += dropped
    return chats, excluded


def _build_and_write(variant: str, chats: List[Chat], owner, owner_names,
                     platforms: List[str], excluded: int, args,
                     identities: Optional[List[Dict]] = None) -> Optional[Dict]:
    if not chats:
        print(f'  [skip] variant {variant!r}: no chats for {"+".join(platforms)}.')
        return None
    if not owner:
        print(f'  [skip] variant {variant!r}: could not detect owner.')
        return None
    payload = build_connected_data(
        chats, owner, timezone=args.timezone,
        min_msgs=args.min_msgs, min_replies=args.min_replies,
        excluded_count=excluded, variant=variant, platforms=platforms,
        owner_names=owner_names, identities=identities,
    )
    js_path, json_path = write_variant_outputs(payload, args.dash_dir, variant)
    _report(variant, payload, js_path, json_path)
    return payload


def _report(variant: str, payload: Dict, js_path: Path, json_path: Path) -> None:
    t = payload['totals']
    att = payload['attention']
    fn = payload['funnel']
    print(f"\n=== Connected variant {variant!r} "
          f"({'+'.join(payload['platforms'])}) — sanity report (counts only) ===")
    print(f"  owner:            {payload['owner']}")
    print(f"  range:            {payload['range']['first_day']} .. {payload['range']['last_day']}")
    print(f"  chats included:   {t['chats_included']}  (dyads {t['dyads']}, groups {t['groups']})")
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
    print(f"  wrote {js_path}  +  {json_path.name}")


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    excludes = [s.strip().lower() for s in args.exclude.split(',') if s.strip()]
    hidden = _load_hidden(args.dash_dir)
    if hidden:
        print(f'Hidden chats excluded (from {args.dash_dir}/data/hidden.json): {len(hidden)}')

    # Manual cross-platform identity merges (M3.2) — 'all' variant only. A bad
    # file is reported and skipped rather than crashing the whole build.
    identities: List[Dict] = []
    try:
        identities = load_identities(args.dash_dir)
    except ValueError as exc:
        print(f'WARNING: ignoring {args.dash_dir}/data/identities.json — {exc}',
              file=sys.stderr)
    if identities:
        print(f'Identity merges (from {args.dash_dir}/data/identities.json): '
              f'{len(identities)} (applied to the "all" variant only)')

    want_ig = args.platform in ('instagram', 'all', 'everything')
    want_tg = args.platform in ('telegram', 'all', 'everything')

    ig_chats: List[Chat] = []
    tg_chats: List[Chat] = []
    ig_excluded = tg_excluded = 0
    ig_owner = tg_owner = None

    # --- Instagram ---
    if want_ig:
        ig_dirs = discover_instagram_chats(args.chats_dir)
        ig_chats, ig_excluded = _load_platform('instagram', ig_dirs, excludes, args.timezone, hidden)
        ig_owner = _detect_owner(ig_chats) if ig_chats else None
        print(f'Instagram: {len(ig_dirs)} discovered, {len(ig_chats)} loaded, '
              f'owner {ig_owner!r}.')

    # --- Telegram ---
    if want_tg:
        tg_dirs = discover_telegram_chats(args.chats_dir)
        tg_chats, tg_excluded = _load_platform('telegram', tg_dirs, excludes, args.timezone, hidden)
        tg_owner = _detect_telegram_owner(tg_chats) if tg_chats else None
        print(f'Telegram:  {len(tg_dirs)} discovered, {len(tg_chats)} loaded, '
              f'owner {tg_owner!r}.')

    build_all = args.platform in ('all', 'everything')
    built = 0

    if args.platform in ('instagram', 'everything'):
        if _build_and_write('instagram', ig_chats, ig_owner, {ig_owner} if ig_owner else None,
                            ['instagram'], ig_excluded, args):
            built += 1

    if args.platform in ('telegram', 'everything'):
        if _build_and_write('telegram', tg_chats, tg_owner, {tg_owner} if tg_owner else None,
                            ['telegram'], tg_excluded, args):
            built += 1

    if build_all:
        merged = ig_chats + tg_chats
        # The owner is one human: normalize the label to the Instagram handle
        # when present, and treat BOTH handles as owner while reducing.
        owner_names = {n for n in (ig_owner, tg_owner) if n}
        owner_label = ig_owner or tg_owner
        platforms = [p for p, present in (('instagram', bool(ig_chats)),
                                          ('telegram', bool(tg_chats))) if present]
        if _build_and_write('all', merged, owner_label, owner_names or None,
                            platforms or ['instagram'],
                            ig_excluded + tg_excluded, args,
                            identities=identities):
            built += 1

    if built == 0:
        print('No variants built — no chats found.', file=sys.stderr)
        return 1
    print(f'\nBuilt {built} variant(s).')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
