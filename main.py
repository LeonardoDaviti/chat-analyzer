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
import sys
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.data_loader import load_chat_from_dir, get_chat_name_from_dir, load_chats_from_dirs
from src.session_chunker import chunk_messages, get_session_statistics
from src.analyzer import ChatAnalyzer
from src.visualizer import ChatVisualizer
from src.visualizer_v3 import AdvancedMetricsVisualizerV3
from src.output_manager import create_output_dir, save_json


def discover_all_chats(base_dir: str) -> list[str]:
    """Auto-discover all chat directories under the inbox."""
    inbox = Path(base_dir) / "Chats" / "instagram-leonardodaviti-2026-04-26-oLmiaSkf" / \
            "your_instagram_activity" / "messages" / "inbox"
    
    if not inbox.exists():
        raise FileNotFoundError(f"Inbox directory not found: {inbox}")
    
    chat_dirs = []
    for chat_dir in sorted(inbox.iterdir()):
        if not chat_dir.is_dir():
            continue
        has_msgs = (
            chat_dir.glob("message_*.json") or
            (chat_dir / "combined_message.json").exists()
        )
        if has_msgs:
            chat_dirs.append(str(chat_dir))
    
    return chat_dirs


def run_chat_pipeline(
    chat_dir: str,
    my_name: str,
    output_base: str,
    session_gap_hours: float = 2.0,
    min_session_messages: int = 3,
    min_session_duration_s: int = 30
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
    
    # Update my_name if it was changed by get_chat_name_from_dir
    if my_name == "drxnem":
        my_name = "David"  # drxnem is David's handle
    
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
        chat_name
    )
    session_stats = get_session_statistics(sessions)
    print(f"   Sessions: {session_stats['total_sessions']}")
    print(f"   Date range: {session_stats['date_range']['first']} → {session_stats['date_range']['last']}")
    if session_stats.get('average_session_duration_minutes'):
        print(f"   Avg duration: {session_stats['average_session_duration_minutes']} min")
    
    # Step 4: Analyze
    print("\n📊 Analyzing...")
    analyzer = ChatAnalyzer(data, my_name)
    analysis = analyzer.analyze()
    
    # Print key metrics
    msg_counts = analysis.get('message_counts', {})
    total = sum(msg_counts.values())
    print(f"   Total: {total} | David: {msg_counts.get('David', 0)} | Other: {msg_counts.get('Mariam Merabishvili', 0) if 'Mariam Merabishvili' in msg_counts else 'N/A'}")
    
    lang = analysis.get('language_distribution', {})
    print(f"   Language: EN={lang.get('english', 0):.1f}% | MIXED={lang.get('mixed', 0):.1f}% | GEORGIAN={lang.get('georgian', 0):.1f}%")
    
    rt = analysis.get('response_times', {})
    print(f"   Response time: David={rt.get('my_avg_response_minutes', 0):.1f}min | Other={rt.get('partner_avg_response_minutes', 0):.1f}min")
    
    # Step 5: Generate visualizations
    print("\n📈 Generating visualizations...")
    viz_dir = str(output_paths['visualizations'])
    visualizer = ChatVisualizer(viz_dir)
    visualizer_v3 = AdvancedMetricsVisualizerV3(viz_dir)
    
    visualizer.generate_all_plots(analysis, chat_name)
    visualizer_v3.generate_all(analysis, chat_name)
    print(f"   ✓ Generated 22+ charts in {viz_dir}")
    
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
    
    # Step 7: Save metadata
    elapsed = time.time() - start_time
    metadata = {
        'chat_name': chat_name,
        'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'processing_time_seconds': round(elapsed, 1),
        'total_messages': len(data.get('messages', [])),
        'valid_sessions': session_stats['total_sessions'],
        'my_name': my_name
    }
    save_json(metadata, output_paths['metadata'])
    
    print(f"\n{'='*60}")
    print(f"✅ Complete! ({elapsed:.1f}s)")
    print(f"   Output: {output_paths['base']}")
    print(f"   Files: sessions.json, analysis.json, session_stats.json, ")
    print(f"          session_analyses.json, normalized.json, metadata.json,")
    print(f"          visualizations/ (22+ charts)")
    print(f"{'='*60}")
    
    return {
        'chat_name': chat_name,
        'output_dir': str(output_paths['base']),
        'processing_time': elapsed,
        'messages': len(data.get('messages', [])),
        'sessions': session_stats['total_sessions'],
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
        '--my-name', type=str, default='David',
        help='Your name in the chats (default: David)'
    )
    parser.add_argument(
        '--output-dir', type=str, default='Outputs',
        help='Base output directory (default: Outputs)'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Instagram Chat Analyzer - Full Pipeline")
    print("=" * 60)
    
    # Discover chats
    base_dir = Path(__file__).parent
    all_chat_dirs = discover_all_chats(str(base_dir))
    
    if not all_chat_dirs:
        print("No chats found in Chats/ directory!")
        sys.exit(1)
    
    print(f"\n🔍 Found {len(all_chat_dirs)} chat(s):")
    for d in all_chat_dirs:
        print(f"   - {d.split('/')[-1]}")
    
    # Filter by --chat if specified
    if args.chat:
        targets = [c.strip() for c in args.chat.split(',')]
        filtered = [d for d in all_chat_dirs if any(t in d for t in targets)]
        if not filtered:
            print(f"\n❌ No chats matching: {args.chat}")
            sys.exit(1)
        chat_dirs = filtered
        print(f"\n📋 Processing {len(chat_dirs)} chat(s): {[d.split('/')[-1] for d in chat_dirs]}")
    else:
        chat_dirs = all_chat_dirs
    
    # Run pipeline for each chat
    results = []
    for chat_dir in chat_dirs:
        try:
            result = run_chat_pipeline(
                chat_dir=chat_dir,
                my_name=args.my_name,
                output_base=args.output_dir
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
