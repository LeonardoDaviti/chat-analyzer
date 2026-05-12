"""
Session Markdown Exporter

Converts session data into per-session markdown files optimized for LLM analysis.

Format:
  - First letter of sender name as identifier (D, M, etc.)
  - Consecutive messages from same sender grouped with " | " separator
  - {new_date} markers when calendar day changes within a session
  - Token-based session merging (threshold: 200 tokens)

Usage:
    from src.session_markdown import export_sessions_to_markdown
    
    export_sessions_to_markdown(
        sessions_path='Outputs/Mariam Merabishvili/2026-05-12_19-28/sessions.json',
        output_dir='Outputs/Mariam Merabishvili/2026-05-12_19-28/sessions_md'
    )
"""

import json
from pathlib import Path
from typing import Dict, List, Any


def group_consecutive_msgs(all_msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group consecutive messages from the same sender.
    
    Args:
        all_msgs: List of message dicts sorted by timestamp
        
    Returns:
        List of grouped message dicts with 'parts', 'time', and 'date' keys
    """
    if not all_msgs:
        return []
    
    groups = []
    current = None
    
    for msg in all_msgs:
        sender = msg.get('sender_name', 'Unknown')
        sender_name = msg.get('sender_name_normalized', sender)
        content = msg.get('content', '')
        timestamp_ms = msg.get('timestamp_ms', 0)
        lang = msg.get('language', 'unknown')
        msg_type = msg.get('type', 'text')
        
        from datetime import datetime
        dt = datetime.fromtimestamp(timestamp_ms / 1000) if timestamp_ms else None
        time_str = dt.strftime('%H:%M') if dt else ''
        date_str = dt.strftime('%Y-%m-%d') if dt else ''
        
        # Determine content
        if lang == 'system' or msg_type in ('photo', 'video', 'audio_call', 'link'):
            content = f'[{msg_type.upper()}]' if msg_type != 'text' else content
        elif not content.strip():
            content = None
        
        if content is None:
            continue
        
        key = (sender_name,)
        
        if current and current['key'] == key:
            current['parts'].append(content)
        else:
            current = {
                'key': key,
                'sender_name': sender_name,
                'parts': [content],
                'time': time_str,
                'date': date_str,
            }
            groups.append(current)
    
    return groups


def build_session_markdown(
    session_group: List[Dict[str, Any]],
    chat_name: str,
    my_name: str = "David"
) -> str:
    """Build markdown content for a group of sessions.
    
    Inserts {new_date} markers when the calendar day changes between messages,
    so LLMs don't hallucinate about conversation context across days.
    
    Args:
        session_group: List of sessions to combine
        chat_name: Display name for the chat
        my_name: Your name in the chat
        
    Returns:
        Complete markdown string
    """
    lines = []
    
    all_msgs = []
    for session in session_group:
        all_msgs.extend(session.get('real_msgs', []))
    
    all_msgs.sort(key=lambda m: m.get('timestamp_ms', 0))
    
    if not all_msgs:
        return ""
    
    # Calculate aggregate stats
    first_ts = all_msgs[0].get('timestamp_ms', 0)
    last_ts = all_msgs[-1].get('timestamp_ms', 0)
    
    from datetime import datetime
    start_dt = datetime.fromtimestamp(first_ts / 1000)
    end_dt = datetime.fromtimestamp(last_ts / 1000)
    
    duration_minutes = (last_ts - first_ts) / 1000 / 60
    start_time = start_dt.strftime('%H:%M')
    end_time = end_dt.strftime('%H:%M')
    start_date = start_dt.strftime('%Y-%m-%d')
    end_date = end_dt.strftime('%Y-%m-%d')
    
    # Count by sender
    sender_counts = {}
    for m in all_msgs:
        sender = m.get('sender_name_normalized', m.get('sender_name', 'Unknown'))
        sender_counts[sender] = sender_counts.get(sender, 0) + 1
    
    # Legend
    legend = {}
    for name in sorted(sender_counts.keys()):
        legend[name] = name[0].upper()
    
    # Group consecutive messages
    grouped = group_consecutive_msgs(all_msgs)
    
    # Header
    lines.append("# LEGEND")
    for full_name, abbrev in legend.items():
        lines.append(f"{full_name} - {abbrev}")
    lines.append("#")
    lines.append("")
    
    # Session Summary
    lines.append("## Session Summary")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| **Date Range** | {start_date} → {end_date} |")
    lines.append(f"| **Time Range** | {start_time} - {end_time} |")
    lines.append(f"| **Duration** | {duration_minutes:.1f} minutes |")
    lines.append(f"| **Total Messages** | {len(all_msgs)} |")
    lines.append(f"| **Messages by Sender** | {', '.join(f'{k}: {v}' for k, v in sender_counts.items())} |")
    lines.append("")
    
    # Separator
    lines.append("---")
    lines.append("")
    lines.append("## Messages")
    lines.append("")
    
    # Format messages with {new_date} markers
    last_date = None
    for group in grouped:
        # Insert date marker if day changed
        if group['date'] != last_date and last_date is not None:
            lines.append(f"{{{group['date']}}}")
            lines.append("")
        last_date = group['date']
        
        abbrev = legend.get(group['sender_name'], group['sender_name'][0].upper())
        msg_text = ' | '.join(group['parts'])
        time_str = group['time']
        lines.append(f"{abbrev}|{msg_text}|{time_str}")
    
    lines.append("")
    
    return '\n'.join(lines)


def estimate_tokens(content: str) -> int:
    """Rough token estimate: chars / 4."""
    return len(content) // 4


def group_sessions_for_markdown(
    sessions: List[Dict[str, Any]],
    min_session_messages: int = 200
) -> List[List[Dict[str, Any]]]:
    """Group sessions for markdown output based on message count.
    
    Sessions under min_session_messages are merged with adjacent ones.
    
    Args:
        sessions: List of session dicts (sorted by time)
        min_session_messages: Min message count before a session stands alone
        
    Returns:
        List of session groups
    """
    if not sessions:
        return []
    
    groups = []
    current_group = []
    
    for session in sessions:
        msg_count = session.get('messages', {}).get('total', 0)
        
        if msg_count >= min_session_messages:
            # Large session — finalize previous group and start new one
            if current_group:
                groups.append(current_group)
            groups.append([session])
            current_group = []
        else:
            # Small session — accumulate for merging
            current_group.append(session)
    
    # Any remaining small sessions at the end
    if current_group:
        groups.append(current_group)
    
    return groups


def export_sessions_to_markdown(
    sessions_path: str,
    output_dir: str,
    chat_name: str = "Chat",
    min_session_messages: int = 200,
    my_name: str = "David"
) -> List[Path]:
    """Export sessions to markdown files.
    
    Args:
        sessions_path: Path to sessions.json file
        output_dir: Directory where markdown files will be saved
        chat_name: Display name for the chat
        min_session_messages: Min message count before a session stands alone
        my_name: Your name in the chat
        
    Returns:
        List of created markdown file paths
    """
    with open(sessions_path, 'r', encoding='utf-8') as f:
        sessions = json.load(f)
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    groups = group_sessions_for_markdown(sessions, min_session_messages=min_session_messages)
    
    print(f"\n=== SESSION MARKDOWN EXPORT ===")
    print(f"Total sessions loaded: {len(sessions)}")
    print(f"Output files: {len(groups)}")
    print(f"Min session messages threshold: {min_session_messages}")
    
    created_files = []
    for i, group in enumerate(groups, 1):
        if len(group) == 1:
            date_str = group[0].get('date', f'session_{i:03d}')
        else:
            first_session = group[0]
            last_session = group[-1]
            date_str = f"{first_session.get('date', 'start')}_to_{last_session.get('date', 'end')}"
        
        filename = f"session_{i:03d}_{date_str}.md"
        filepath = output_path / filename
        
        content = build_session_markdown(group, chat_name, my_name)
        
        if not content:
            continue
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        created_files.append(filepath)
        
        total_msgs = sum(s.get('messages', {}).get('total', 0) for s in group)
        total_tokens = estimate_tokens(content)
        if len(group) == 1:
            print(f"  {filename:<55} | {total_msgs:>5} msgs | {total_tokens:>6} tok | {group[0].get('duration_minutes', 0):>7.1f} min")
        else:
            print(f"  {filename:<55} | {total_msgs:>5} msgs | {total_tokens:>6} tok | {group[-1].get('duration_minutes', 0):>7.1f} min (merged {len(group)} sessions)")
    
    print(f"\n✅ Created {len(created_files)} markdown files in: {output_path}")
    
    return created_files


if __name__ == "__main__":
    import sys
    
    sessions_path = "Outputs/Mariam Merabishvili/2026-05-12_19-28/sessions.json"
    output_base = "Outputs/Mariam Merabishvili/2026-05-12_19-28/sessions_md"
    chat_name = "Mariam Merabishvili"
    
    if len(sys.argv) > 1:
        sessions_path = sys.argv[1]
    if len(sys.argv) > 2:
        output_base = sys.argv[2]
    if len(sys.argv) > 3:
        chat_name = sys.argv[3]
    
    export_sessions_to_markdown(sessions_path, output_base, chat_name)
