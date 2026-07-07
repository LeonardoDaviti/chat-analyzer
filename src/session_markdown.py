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
        sessions_path='Outputs/<chat-name>/sessions.json',
        output_dir='Outputs/<chat-name>/sessions_md'
    )
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional

from src.timeutil import to_datetime

# Break a same-sender group when the in-group gap exceeds this many minutes, so
# messages days apart don't collapse into "one breath" (BUG_REPORT C16).
GROUP_BREAK_GAP_MINUTES = 10


def _media_placeholder(msg: Dict[str, Any], msg_type: str) -> Optional[str]:
    """Render a placeholder for a media/system message so it isn't invisible."""
    if msg_type == 'call':
        dur = msg.get('call_duration')
        if isinstance(dur, (int, float)) and dur > 0:
            minutes = int(dur) // 60
            if minutes >= 1:
                return f'[CALL {minutes}min]'
            return f'[CALL {int(dur)}s]'
        return '[CALL]'
    if msg_type == 'photo':
        return '[PHOTO]'
    if msg_type == 'video':
        return '[VIDEO]'
    if msg_type == 'voice':
        return '[VOICE]'
    if msg_type == 'share':
        return '[SHARE]'
    if msg_type == 'sticker':
        return '[STICKER]'
    return None


def group_consecutive_msgs(all_msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group consecutive messages from the same sender.

    Media/system messages are rendered as placeholders (``[PHOTO]``,
    ``[CALL 12min]``, ...) rather than dropped, so the LLM transcript reflects
    the whole exchange. Groups are broken when the calendar day changes OR the
    time gap between two messages exceeds ``GROUP_BREAK_GAP_MINUTES`` — the first
    timestamp of a group is then representative (BUG_REPORT C16).

    Args:
        all_msgs: List of message dicts sorted by timestamp

    Returns:
        List of grouped message dicts with 'parts', 'time', and 'date' keys
    """
    if not all_msgs:
        return []

    groups = []
    current = None
    prev_ts = None

    for msg in all_msgs:
        sender = msg.get('sender_name', 'Unknown')
        sender_name = msg.get('sender_name_normalized', sender)
        content = msg.get('content', '')
        timestamp_ms = msg.get('timestamp_ms', 0)
        lang = msg.get('language', 'unknown')
        msg_type = msg.get('type', 'text')

        dt = to_datetime(timestamp_ms) if timestamp_ms else None
        time_str = dt.strftime('%H:%M') if dt else ''
        date_str = dt.strftime('%Y-%m-%d') if dt else ''

        # Determine rendered content
        if lang == 'system':
            content = None  # system notifications stay out of the transcript
        elif msg_type != 'text':
            content = _media_placeholder(msg, msg_type) or (content if content.strip() else None)
        elif not content.strip():
            content = None

        if content is None:
            prev_ts = timestamp_ms  # advance time cursor even for skipped msgs
            continue

        # Break the group on sender change, date change, or a large time gap.
        gap_min = ((timestamp_ms - prev_ts) / 1000 / 60) if prev_ts else 0
        same_group = (
            current is not None
            and current['sender_name'] == sender_name
            and current['date'] == date_str
            and gap_min <= GROUP_BREAK_GAP_MINUTES
        )

        if same_group:
            current['parts'].append(content)
        else:
            current = {
                'key': (sender_name,),
                'sender_name': sender_name,
                'parts': [content],
                'time': time_str,
                'date': date_str,
            }
            groups.append(current)

        prev_ts = timestamp_ms

    return groups


def build_session_markdown(
    session_group: List[Dict[str, Any]],
    chat_name: str,
    my_name: str = "You"
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
        # Prefer the full message list (incl. media/system) so photos, calls,
        # etc. are rendered as placeholders instead of vanishing (C16).
        all_msgs.extend(session.get('all_messages', session.get('real_msgs', [])))

    all_msgs.sort(key=lambda m: m.get('timestamp_ms', 0))

    if not all_msgs:
        return ""

    # Calculate aggregate stats
    first_ts = all_msgs[0].get('timestamp_ms', 0)
    last_ts = all_msgs[-1].get('timestamp_ms', 0)

    start_dt = to_datetime(first_ts)
    end_dt = to_datetime(last_ts)
    
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
    my_name: str = "You"
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

    # Micro-interaction sessions are retained in the data (valid=False) but are
    # excluded from the LLM transcript export.
    sessions = [s for s in sessions if s.get('valid', True)]

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

    sessions_path = "Outputs/<chat-name>/sessions.json"
    output_base = "Outputs/<chat-name>/sessions_md"
    chat_name = "Chat Partner"
    
    if len(sys.argv) > 1:
        sessions_path = sys.argv[1]
    if len(sys.argv) > 2:
        output_base = sys.argv[2]
    if len(sys.argv) > 3:
        chat_name = sys.argv[3]
    
    export_sessions_to_markdown(sessions_path, output_base, chat_name)
