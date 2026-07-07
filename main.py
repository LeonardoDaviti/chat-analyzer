#!/usr/bin/env python3
"""
Instagram Chat Analyzer - Full Pipeline
========================================

Automates the complete analysis pipeline:
  1. Auto-discover chats in Chats/ directory
  2. Combine multi-file JSONs (message_1.json, message_2.json, ...)
  3. Normalize: decode Georgian text, detect language, add timestamps
  4. Chunk into sessions (2h gap threshold, stacking merge for tiny sessions)
  5. Analyze: compute all 24 metrics + V3.0 advanced metrics
  6. Generate visualizations (regular + V3 dashboard)
  7. Save organized output to Outputs/{Chat}/{Timestamp}/

Usage:
    python main.py                        # Process all chats
    python main.py --chat mariammerabishvili  # Process specific chat
    python main.py --chat mariammerabishvili,gbb  # Multiple chats
"""

import json
import os
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.data_loader import load_chat_from_dir, get_chat_name_from_dir, load_chats_from_dirs
from src.normalizer import decode_georgian_text
from src.session_chunker import chunk_messages, get_session_statistics
from src.session_markdown import export_sessions_to_markdown
from src.analyzer import ChatAnalyzer
from src.visualizer import ChatVisualizer
from src.visualizer_v3 import AdvancedMetricsVisualizerV3
from src.visualizer_v4 import MetricsVisualizerV4
from src.output_manager import create_output_dir, save_json

# Relative path, inside any export, to the folder that holds the per-chat dirs.
_INBOX_SUFFIX = ("your_instagram_activity", "messages", "inbox")


def _find_inboxes(base_dir: Path) -> list[tuple[str, Path]]:
    """Locate every Instagram-export inbox under ``Chats/``.

    Supports two layouts:
      * ``Chats/<export-folder>/your_instagram_activity/messages/inbox``
        (one or more export folders side by side), and
      * ``Chats/your_instagram_activity/messages/inbox`` (the user extracted
        the zip directly into ``Chats/``).

    Returns a list of ``(export_label, inbox_path)`` tuples.
    """
    chats_root = base_dir / "Chats"
    found: list[tuple[str, Path]] = []

    # Layout B: zip extracted straight into Chats/.
    direct = chats_root.joinpath(*_INBOX_SUFFIX)
    if direct.exists():
        found.append(("Chats", direct))

    # Layout A: one or more export folders under Chats/.
    if chats_root.exists():
        for sub in sorted(chats_root.iterdir()):
            if not sub.is_dir():
                continue
            inbox = sub.joinpath(*_INBOX_SUFFIX)
            if inbox.exists():
                found.append((sub.name, inbox))

    return found


def discover_all_chats(base_dir: str) -> list[tuple[str, str]]:
    """Auto-discover all chat directories across every export under ``Chats/``.

    Returns a list of ``(export_label, chat_dir)`` tuples so callers can report
    which export each chat came from. Multiple exports are concatenated.
    """
    inboxes = _find_inboxes(Path(base_dir))
    if not inboxes:
        raise FileNotFoundError(
            f"No Instagram export inbox found under {Path(base_dir) / 'Chats'}. "
            f"Expected .../your_instagram_activity/messages/inbox — "
            f"import a download first with:  python main.py --import-zip <zip>"
        )

    chats: list[tuple[str, str]] = []
    for export_label, inbox in inboxes:
        for chat_dir in sorted(inbox.iterdir()):
            if not chat_dir.is_dir():
                continue
            # any() — a glob generator is always truthy (BUG_REPORT A5)
            has_msgs = (
                any(chat_dir.glob("message_*.json")) or
                (chat_dir / "combined_message.json").exists() or
                (chat_dir / "normalized.json").exists()
            )
            if has_msgs:
                chats.append((export_label, str(chat_dir)))

    return chats


def _chat_participants(chat_dir: str) -> list[str]:
    """Decoded participant display names for a chat (cheap, no full pipeline)."""
    p = Path(chat_dir)
    candidates = [p / "combined_message.json", p / "normalized.json"]
    candidates += sorted(p.glob("message_*.json"))
    for f in candidates:
        if not f.exists():
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        names = []
        for entry in data.get("participants", []) or []:
            raw = entry.get("name", "") if isinstance(entry, dict) else str(entry)
            name = decode_georgian_text(raw)
            if name:
                names.append(name)
        if names:
            return names
    return []


def _chat_thread_path(chat_dir: str) -> str:
    """The ``thread_path`` for a chat (identifies duplicate renamed folders).

    Reads whichever metadata file is available (combined/normalized/message_*);
    ``thread_path`` is present in all of them (report §2).
    """
    p = Path(chat_dir)
    candidates = [p / "combined_message.json", p / "normalized.json"]
    candidates += sorted(p.glob("message_*.json"))
    for f in candidates:
        if not f.exists():
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        tp = data.get("thread_path")
        if tp:
            return str(tp)
    return ""


def _message_bytes(chat_dir: str) -> int:
    """Total bytes of the raw ``message_*.json`` files in a chat directory.

    Used to pick the richest copy among duplicate folders (report §1: keep the
    variant whose message files total the most bytes).
    """
    total = 0
    for f in Path(chat_dir).glob("message_*.json"):
        try:
            total += f.stat().st_size
        except OSError:
            continue
    return total


def dedup_by_thread_path(
    discovered: list[tuple[str, str]]
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Drop duplicate chat folders that share a ``thread_path``.

    Folders can be renamed copies of the same conversation (e.g. 'SemperFi' vs
    'sempeghpghaii_…'; report §1). Among duplicates the folder whose
    ``message_*.json`` files total the most bytes is kept.

    Returns ``(kept, skipped)`` where ``skipped`` is a list of
    ``(kept_dir, skipped_dir)`` pairs for reporting.
    """
    by_tp: dict[str, list[tuple[str, str]]] = {}
    kept: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []

    for label, chat_dir in discovered:
        tp = _chat_thread_path(chat_dir)
        if not tp:
            # No thread_path to key on — never dedup blindly, always keep.
            kept.append((label, chat_dir))
            continue
        by_tp.setdefault(tp, []).append((label, chat_dir))

    for tp, group in by_tp.items():
        if len(group) == 1:
            kept.append(group[0])
            continue
        winner = max(group, key=lambda ld: _message_bytes(ld[1]))
        kept.append(winner)
        for ld in group:
            if ld is not winner:
                skipped.append((winner[1], ld[1]))

    return kept, skipped


def detect_owner_from_participants(participant_lists: list[list[str]]) -> Optional[str]:
    """Most common participant across chats = the export owner.

    The account owner is the only person present in (nearly) every chat, so the
    name appearing in the most participant lists wins. Pure function over
    already-extracted metadata (kept separate for testability).
    """
    counter: Counter = Counter()
    for parts in participant_lists:
        for name in set(parts):  # count each chat at most once per person
            counter[name] += 1
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def detect_owner(chat_dirs: list[str]) -> Optional[str]:
    """Auto-detect the account owner across discovered chat directories."""
    return detect_owner_from_participants(
        [_chat_participants(d) for d in chat_dirs]
    )


def import_zip(zip_path: str, base_dir: Path) -> str:
    """Extract an Instagram export zip into ``Chats/<zipname>/`` (zip-slip safe).

    Validates that ``your_instagram_activity/messages/inbox`` exists inside the
    extracted data and prints how many chats were found. Returns the target dir.
    """
    zp = Path(zip_path).expanduser()
    if not zp.exists():
        raise FileNotFoundError(f"Zip file not found: {zp}")
    if not zipfile.is_zipfile(zp):
        raise ValueError(f"Not a valid zip file: {zp}")

    target = (base_dir / "Chats" / zp.stem)
    target.mkdir(parents=True, exist_ok=True)
    target_root = target.resolve()

    with zipfile.ZipFile(zp) as zf:
        for member in zf.namelist():
            # Reject any member that would escape the target directory
            # (zip-slip / path traversal).
            dest = (target / member).resolve()
            if dest != target_root and target_root not in dest.parents:
                raise ValueError(f"Unsafe path in zip (zip-slip blocked): {member}")
        zf.extractall(target)

    print(f"📦 Extracted '{zp.name}' → {target}")

    # The inbox may be at the archive root or under a single wrapping folder.
    inbox = target.joinpath(*_INBOX_SUFFIX)
    if not inbox.exists():
        matches = sorted(target.glob(os.path.join("**", *_INBOX_SUFFIX)))
        inbox = matches[0] if matches else None

    if inbox is None or not inbox.exists():
        raise FileNotFoundError(
            "Extracted archive does not contain "
            "your_instagram_activity/messages/inbox — is this an Instagram "
            "'messages' export in JSON format?"
        )

    chat_count = sum(
        1 for d in inbox.iterdir()
        if d.is_dir() and (any(d.glob("message_*.json")) or
                           (d / "combined_message.json").exists())
    )
    print(f"✅ Import OK — found {chat_count} chat(s) in {inbox}")
    print("   Next: run  python main.py")
    return str(target)


def run_chat_pipeline(
    chat_dir: str,
    my_name: str,
    output_base: str,
    session_gap_hours: float = 2.0,
    min_session_messages: int = 3,
    min_session_duration_s: int = 30,
    skip_visualizations: bool = False
) -> dict:
    """Run the full analysis pipeline for a single chat.
    
    Args:
        chat_dir: Path to the chat directory
        my_name: Your name in the chat
        output_base: Base output directory
        session_gap_hours: Gap threshold for session splitting
        min_session_messages: Minimum messages for a valid session
        min_session_duration_s: Minimum duration (seconds) for a valid session
        
    Returns:
        Dictionary with all results and metadata
    """
    start_time = time.time()
    
    # Step 1: Load chat (auto-discover + combine + normalize)
    print(f"\n{'='*60}")
    print(f"📁 Loading chat: {chat_dir.split('/')[-1]}")
    print(f"{'='*60}")
    
    data = load_chat_from_dir(chat_dir)
    chat_name = get_chat_name_from_dir(chat_dir)

    print(f"   Chat name: {chat_name}")
    print(f"   Total messages: {len(data.get('messages', []))}")
    
    # Step 2: Create output directory
    output_paths = create_output_dir(output_base, chat_name)
    print(f"\n📂 Output: {output_paths['base']}")
    
    # Step 3: Chunk into sessions
    print("\n🔪 Chunking into sessions...")
    sessions = chunk_messages(
        data['messages'],
        my_name,
        chat_name,
        session_gap_hours=session_gap_hours,
        min_session_messages=min_session_messages,
        min_session_duration_s=min_session_duration_s,
    )
    session_stats = get_session_statistics(sessions)
    # session_stats is {} when a chat has no valid sessions (e.g. only a few
    # scattered messages) — guard all lookups
    print(f"   Sessions: {session_stats.get('total_sessions', 0)}")
    if session_stats.get('date_range'):
        print(f"   Date range: {session_stats['date_range']['first']} → {session_stats['date_range']['last']}")
    if session_stats.get('average_session_duration_minutes'):
        print(f"   Avg duration: {session_stats['average_session_duration_minutes']} min")
    
    # Step 4: Analyze
    print("\n📊 Analyzing...")
    analyzer = ChatAnalyzer(data, my_name, sessions=sessions)
    analysis = analyzer.analyze()
    
    # Print key metrics (derive names from the data, no hardcoding)
    msg_counts = analysis.get('message_counts', {})
    total = sum(msg_counts.values())

    if analysis.get('group_metrics'):
        # Group summary: member count + top-3 share.
        member_count = analysis.get('member_count', len(analysis.get('participants', [])))
        stats = analysis['group_metrics'].get('member_stats', {})
        top3 = sorted(stats.items(), key=lambda kv: -kv[1].get('msgs', 0))[:3]
        print(f"   Group · {member_count} members | Total: {total}")
        top_str = ' | '.join(f"{u}: {s.get('share', 0.0) * 100:.0f}%" for u, s in top3)
        print(f"   Top senders: {top_str}")
        lang = analysis.get('language_distribution', {})
        print(f"   Language: EN={lang.get('english', 0):.1f}% | MIXED={lang.get('mixed', 0):.1f}% | GEORGIAN={lang.get('georgian', 0):.1f}%")
    else:
        partner_name = next((p for p in analysis.get('participants', []) if p != my_name), None)
        partner_count = msg_counts.get(partner_name, 0) if partner_name else 'N/A'
        print(f"   Total: {total} | {my_name}: {msg_counts.get(my_name, 0)} | "
              f"{partner_name or 'Other'}: {partner_count}")

        lang = analysis.get('language_distribution', {})
        print(f"   Language: EN={lang.get('english', 0):.1f}% | MIXED={lang.get('mixed', 0):.1f}% | GEORGIAN={lang.get('georgian', 0):.1f}%")

        rt = analysis.get('response_times', {})
        print(f"   Response time: {my_name}={rt.get('my_avg_response_minutes', 0):.1f}min | Other={rt.get('partner_avg_response_minutes', 0):.1f}min")
    
    # Step 5: Generate visualizations (optional — dashboard reads JSON directly)
    if not skip_visualizations:
        print("\n📈 Generating visualizations...")
        viz_dir = str(output_paths['visualizations'])
        visualizer = ChatVisualizer(viz_dir)
        visualizer_v3 = AdvancedMetricsVisualizerV3(viz_dir)
        visualizer_v4 = MetricsVisualizerV4(viz_dir)

        visualizer.generate_all_plots(analysis, chat_name)
        visualizer_v3.generate_all(analysis, chat_name)
        visualizer_v4.generate_all(analysis, chat_name)
        print(f"   ✓ Generated 22+ charts in {viz_dir}")
    else:
        print("\n📈 Skipping PNG charts (--no-visualizations). Dashboard reads JSON data directly.")
    
    # Step 6: Save outputs
    print("\n💾 Saving outputs...")
    save_json(sessions, output_paths['sessions'])
    save_json(analysis, output_paths['analysis'])
    save_json(session_stats, output_paths['session_stats'])
    save_json(data, output_paths['normalized'])
    
    # Save session-level analysis (simple per-session stats)
    session_analyses = []
    for session in sessions:
        msgs = session.get('real_msgs', [])
        if not msgs:
            continue
        
        by_sender = {}
        for m in msgs:
            sender = m.get('sender_name', 'Unknown')
            by_sender[sender] = by_sender.get(sender, 0) + 1
        
        # Compute response times for this session
        response_times = []
        for i in range(1, len(msgs)):
            prev = msgs[i - 1]
            curr = msgs[i]
            if prev.get('sender_name') != curr.get('sender_name'):
                diff = (curr.get('timestamp_ms', 0) - prev.get('timestamp_ms', 0)) / 1000 / 60
                response_times.append(diff)
        
        # Language distribution for this session
        lang_counts = {}
        for m in msgs:
            lang = m.get('language', 'unknown')
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
        total_lang = sum(lang_counts.values())
        lang_dist = {k: round(v / total_lang * 100, 1) for k, v in lang_counts.items()}
        
        # Word frequency (top 20)
        word_freq = {}
        for m in msgs:
            text = m.get('content', '').lower()
            if text and text not in ('system', 'liked a message', 'reacted...'):
                words = text.split()
                for w in words:
                    word_freq[w] = word_freq.get(w, 0) + 1
        top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:20]
        
        session_analyses.append({
            'session_id': session.get('session_id', ''),
            'date': session.get('date', ''),
            'time_range': session.get('time_range', ''),
            'duration_minutes': session.get('duration_minutes', 0),
            'total_messages': len(msgs),
            'by_sender': by_sender,
            'avg_response_time_minutes': round(sum(response_times) / len(response_times), 2) if response_times else 0,
            'language_distribution': lang_dist,
            'top_words': dict(top_words)
        })
    
    save_json(session_analyses, output_paths['session_analyses'])
    
    # Step 7: Export sessions as markdown files
    print("\n📝 Exporting session markdown files...")
    export_sessions_to_markdown(
        sessions_path=str(output_paths['sessions']),
        output_dir=str(output_paths['sessions_md']),
        chat_name=chat_name,
        min_session_messages=200,
        my_name=my_name
    )
    
    # Step 8: Save metadata
    elapsed = time.time() - start_time
    metadata = {
        'chat_name': chat_name,
        'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'processing_time_seconds': round(elapsed, 1),
        'total_messages': len(data.get('messages', [])),
        'valid_sessions': session_stats.get('total_sessions', 0),
        'my_name': my_name
    }
    save_json(metadata, output_paths['metadata'])
    
    # Count markdown files
    md_file_count = 0
    md_dir = output_paths.get('sessions_md')
    if md_dir and md_dir.exists():
        md_file_count = len(list(md_dir.iterdir()))
    
    print(f"\n{'='*60}")
    print(f"✅ Complete! ({elapsed:.1f}s)")
    print(f"   Output: {output_paths['base']}")
    print(f"   Files: sessions.json, analysis.json, session_stats.json, ")
    print(f"          session_analyses.json, normalized.json, metadata.json,")
    print(f"          visualizations/ (22+ charts), sessions_md/ ({md_file_count} .md files)")
    print(f"{'='*60}")
    
    return {
        'chat_name': chat_name,
        'output_dir': str(output_paths['base']),
        'processing_time': elapsed,
        'messages': len(data.get('messages', [])),
        'sessions': session_stats.get('total_sessions', 0),
        'analysis': analysis,
        'session_stats': session_stats
    }


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Instagram Chat Analyzer')
    parser.add_argument(
        '--chat', type=str, default=None,
        help='Specific chat(s) to process (comma-separated). If not specified, processes all chats.'
    )
    parser.add_argument(
        '--exclude', type=str, default=None,
        help='Chat(s) to skip (comma-separated). A chat is skipped if any value '
             'appears as a substring of its directory name (mirrors --chat).'
    )
    parser.add_argument(
        '--my-name', type=str, default=None,
        help='Your name in the chats. If omitted, it is auto-detected as the '
             'participant present in (nearly) every chat.'
    )
    parser.add_argument(
        '--output-dir', type=str, default='Outputs',
        help='Base output directory (default: Outputs)'
    )
    parser.add_argument(
        '--import-zip', type=str, default=None, metavar='PATH',
        help='Extract an Instagram export zip into Chats/<zipname>/ and exit. '
             'Run this once before analysing.'
    )
    parser.add_argument(
        '--no-visualizations', action='store_true',
        help='Skip PNG chart generation (faster; dashboard reads JSON data directly)'
    )

    args = parser.parse_args()

    base_dir = Path(__file__).parent

    # Import mode: extract a download, then stop.
    if args.import_zip:
        try:
            import_zip(args.import_zip, base_dir)
        except Exception as e:
            print(f"\n❌ Import failed: {e}")
            sys.exit(1)
        return

    print("=" * 60)
    print("Instagram Chat Analyzer - Full Pipeline")
    print("=" * 60)

    # Discover chats: list of (export_label, chat_dir)
    discovered = discover_all_chats(str(base_dir))

    if not discovered:
        print("No chats found in Chats/ directory!")
        sys.exit(1)

    # Drop duplicate folders that share a thread_path (renamed copies).
    discovered, dupes = dedup_by_thread_path(discovered)
    for kept_dir, skipped_dir in dupes:
        print(f"   skipped duplicate of {kept_dir.split('/')[-1]}: "
              f"{skipped_dir.split('/')[-1]}")

    exports = sorted({label for label, _ in discovered})
    print(f"\n🔍 Found {len(discovered)} chat(s) across {len(exports)} export(s):")
    for label, d in discovered:
        parts = _chat_participants(d)
        tag = f"  [group · {len(parts)} members]" if len(parts) >= 3 else ""
        print(f"   - [{label}] {d.split('/')[-1]}{tag}")

    # Filter by --chat if specified
    if args.chat:
        targets = [c.strip() for c in args.chat.split(',')]
        filtered = [(l, d) for (l, d) in discovered if any(t in d for t in targets)]
        if not filtered:
            print(f"\n❌ No chats matching: {args.chat}")
            sys.exit(1)
        selected = filtered
        print(f"\n📋 Processing {len(selected)} chat(s): {[d.split('/')[-1] for _, d in selected]}")
    else:
        selected = list(discovered)

    # Exclude by --exclude if specified (substring match on directory name,
    # mirroring the --chat inclusion logic)
    if args.exclude:
        excludes = [c.strip() for c in args.exclude.split(',') if c.strip()]
        before = len(selected)
        selected = [(l, d) for (l, d) in selected if not any(x in d for x in excludes)]
        skipped = before - len(selected)
        if skipped:
            print(f"\n🚫 Excluded {skipped} chat(s) matching: {args.exclude}")
        if not selected:
            print(f"\n❌ All chats were excluded by: {args.exclude}")
            sys.exit(1)

    # Resolve account owner name: explicit override or auto-detect over ALL
    # discovered chats (so filtering to one chat still detects correctly).
    my_name = args.my_name
    if my_name:
        print(f"\n👤 Account owner: {my_name} (from --my-name)")
    else:
        my_name = detect_owner([d for _, d in discovered])
        if not my_name:
            print("\n❌ Could not auto-detect account owner. Pass --my-name.")
            sys.exit(1)
        print(f"\n👤 Detected account owner: {my_name} (use --my-name to override)")

    # Run pipeline for each chat
    results = []
    for _label, chat_dir in selected:
        try:
            result = run_chat_pipeline(
                chat_dir=chat_dir,
                my_name=my_name,
                output_base=args.output_dir,
                skip_visualizations=args.no_visualizations
            )
            results.append(result)
        except Exception as e:
            print(f"\n❌ Error processing {chat_dir.split('/')[-1]}: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"Processed: {len(results)} chat(s)")
    total_messages = sum(r['messages'] for r in results)
    total_sessions = sum(r['sessions'] for r in results)
    total_time = sum(r['processing_time'] for r in results)
    print(f"Total messages: {total_messages:,}")
    print(f"Total sessions: {total_sessions:,}")
    print(f"Total time: {total_time:.1f}s")
    print(f"\n📍 Output location: {(base_dir / args.output_dir).absolute()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
