"""
Session Chunker for Instagram Chat Analysis

Defines a "session" as a continuous stretch of active conversation between participants.
A session ends when there's a gap > SESSION_GAP_HOURS between messages.

This handles edge cases like:
- Late-night conversations spanning midnight (May 19 23:30 → May 20 04:00)
- Sporadic messaging over long periods
- Multi-day conversations that naturally pause and resume

Usage:
    from src.session_chunker import chunk_messages
    
    sessions = chunk_messages(normalized_messages, my_name, partner_name)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple


# Session gap threshold in hours
# A gap > 2 hours between messages = new session
SESSION_GAP_HOURS = 2.0
SESSION_GAP_MS = SESSION_GAP_HOURS * 60 * 60 * 1000  # milliseconds

# Minimum messages for a valid session
MIN_SESSION_MESSAGES = 3

# Minimum duration (seconds) for a valid session
MIN_SESSION_DURATION_S = 30

# Merge threshold: minutes within which tiny sessions get merged to nearby larger sessions
MERGE_THRESHOLD_MINUTES = 60


def is_real_message(msg: Dict[str, Any]) -> bool:
    """Check if a message is a real conversation message (not system/notification).
    
    Args:
        msg: Message dictionary
        
    Returns:
        True if this is a real message that contributes to conversation
    """
    content = msg.get('content', '')
    language = msg.get('language', '')
    
    # Skip system messages
    if language == 'system':
        return False
    
    # Skip empty or non-text messages
    if not content or content in ('', 'Liked a message', 'reacted'):
        return False
    
    # Media-only messages (photos/videos without text)
    if language == 'media':
        return False
    
    return True


def _get_timestamp_ms(msg: Dict[str, Any]) -> int:
    """Get timestamp in milliseconds from a message.
    
    Args:
        msg: Message dictionary
        
    Returns:
        Timestamp in milliseconds
    """
    return msg.get('timestamp_ms', 0)


def _format_time(timestamp_ms: int) -> str:
    """Format timestamp to HH:MM.
    
    Args:
        timestamp_ms: Timestamp in milliseconds
        
    Returns:
        Formatted time string like "15:30"
    """
    dt = datetime.fromtimestamp(timestamp_ms / 1000)
    return dt.strftime('%H:%M')


def _format_date(timestamp_ms: int) -> str:
    """Format timestamp to YYYY-MM-DD.
    
    Args:
        timestamp_ms: Timestamp in milliseconds
        
    Returns:
        Formatted date string like "2025-05-25"
    """
    dt = datetime.fromtimestamp(timestamp_ms / 1000)
    return dt.strftime('%Y-%m-%d')


def chunk_messages(
    messages: List[Dict[str, Any]],
    my_name: str,
    partner_name: str,
    session_gap_hours: float = SESSION_GAP_HOURS
) -> List[Dict[str, Any]]:
    """Chunk messages into conversation sessions.
    
    A session is defined as a continuous stretch of conversation where
    the gap between consecutive real messages is <= session_gap_hours.
    
    After chunking, filters out noisy sessions (<3 messages or <30 seconds).
    
    Args:
        messages: List of normalized message dictionaries (must be sorted by timestamp)
        my_name: Your name in the chat
        partner_name: Partner's name in the chat
        session_gap_hours: Maximum gap between messages to stay in same session
        
    Returns:
        List of filtered, valid session dictionaries with metadata
    """
    global SESSION_GAP_HOURS, SESSION_GAP_MS
    SESSION_GAP_HOURS = session_gap_hours
    SESSION_GAP_MS = session_gap_hours * 60 * 60 * 1000
    
    if not messages:
        return []
    
    # Filter to real messages only (for session boundary detection)
    real_messages = [m for m in messages if is_real_message(m)]
    
    if not real_messages:
        return []
    
    # Ensure messages are sorted by timestamp
    real_messages.sort(key=lambda m: _get_timestamp_ms(m))
    
    # Chunk into sessions
    sessions = []
    current_session_msgs = [real_messages[0]]
    
    for i in range(1, len(real_messages)):
        prev_msg = real_messages[i - 1]
        curr_msg = real_messages[i]
        
        gap_ms = _get_timestamp_ms(curr_msg) - _get_timestamp_ms(prev_msg)
        
        if gap_ms > SESSION_GAP_MS:
            # End current session, start new one
            sessions.append(_build_session(current_session_msgs, my_name, partner_name, len(sessions)))
            current_session_msgs = [curr_msg]
        else:
            current_session_msgs.append(curr_msg)
    
    # Don't forget the last session
    if current_session_msgs:
        sessions.append(_build_session(current_session_msgs, my_name, partner_name, len(sessions)))
    
    # Now, enrich each session with ALL messages (including system/media) 
    # that fall within the session's time range
    _enrich_sessions_with_all_messages(sessions, messages)
    
    # Merge tiny sessions into adjacent larger sessions, then filter
    valid_sessions = filter_sessions(sessions, merge_tiny=True)
    
    return valid_sessions


def _build_session(
    real_msgs: List[Dict[str, Any]],
    my_name: str,
    partner_name: str,
    session_index: int = 0
) -> Dict[str, Any]:
    """Build a session dictionary from a list of real messages.
    
    Args:
        real_msgs: List of real (non-system) messages in this session
        my_name: Your name
        partner_name: Partner's name
        session_index: Index for session ID generation
        
    Returns:
        Session dictionary with metadata
    """
    if not real_msgs:
        return {}
    
    first_ts = _get_timestamp_ms(real_msgs[0])
    last_ts = _get_timestamp_ms(real_msgs[-1])
    
    # Count messages by sender
    msg_counts = {}
    for m in real_msgs:
        sender = m.get('sender_name', 'Unknown')
        msg_counts[sender] = msg_counts.get(sender, 0) + 1
    
    # Determine who initiated and who ended
    first_sender = real_msgs[0].get('sender_name', 'Unknown')
    last_sender = real_msgs[-1].get('sender_name', 'Unknown')
    
    # Calculate average response time
    response_times = []
    for i in range(1, len(real_msgs)):
        prev = real_msgs[i - 1]
        curr = real_msgs[i]
        
        # Only count if different senders (actual response)
        if prev.get('sender_name') != curr.get('sender_name'):
            diff = (_get_timestamp_ms(curr) - _get_timestamp_ms(prev)) / 1000 / 60  # minutes
            response_times.append(diff)
    
    avg_response_time = sum(response_times) / len(response_times) if response_times else 0
    
    # Language distribution
    lang_counts = {}
    for m in real_msgs:
        lang = m.get('language', 'unknown')
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
    
    # Total duration in minutes
    duration_minutes = (last_ts - first_ts) / 1000 / 60
    
    # Both participants active?
    both_active = len(msg_counts) >= 2 and all(count >= 1 for count in msg_counts.values())
    
    session = {
        'session_id': f'session_{session_index:03d}',
        'start_timestamp_ms': first_ts,
        'end_timestamp_ms': last_ts,
        'date': _format_date(first_ts),
        'time_range': f"{_format_time(first_ts)} - {_format_time(last_ts)}",
        'duration_minutes': round(duration_minutes, 1),
        'messages': {
            'total': len(real_msgs),
            'by_sender': msg_counts
        },
        'participants': {
            'initiated_by': first_sender,
            'ended_by': last_sender,
            'both_active': both_active
        },
        'communication': {
            'avg_response_time_minutes': round(avg_response_time, 2),
            'languages': lang_counts
        },
        'real_msgs': real_msgs,  # Keep reference for merging
        'merged_from': []  # Track if this session absorbed a tiny session
    }
    
    return session


def _enrich_sessions_with_all_messages(
    sessions: List[Dict[str, Any]],
    all_messages: List[Dict[str, Any]]
):
    """Add ALL messages (including system/media) to their respective sessions.
    
    Messages that fall within a session's time range are added to that session's
    'all_messages' field, even if they were excluded from the session's real_msgs
    count (system messages, media-only, etc.).
    
    Args:
        sessions: List of session dictionaries
        all_messages: All messages from the chat (including system/media)
    """
    if not sessions or not all_messages:
        return
    
    for session in sessions:
        session_start = session['start_timestamp_ms']
        session_end = session['end_timestamp_ms']
        
        # Find all messages within this session's time range
        session_all_msgs = []
        for msg in all_messages:
            msg_ts = _get_timestamp_ms(msg)
            if session_start <= msg_ts <= session_end:
                session_all_msgs.append(msg)
        
        session['all_messages'] = session_all_msgs
        session['total_all_messages'] = len(session_all_msgs)


def _merge_tiny_sessions(sessions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge tiny sessions into the next large session using stacking logic.
    
    Logic (stacking):
    1. Sessions are sorted by time
    2. Each large session (≥3 msgs) absorbs ALL preceding tiny sessions
       until the previous large session
    3. Tiny sessions before the first large session stay as-is
    4. Large sessions never merge into each other
    
    Example:
        Tiny(1msg) → Tiny(2msgs) → Large(5msgs) → Tiny(1msg) → Tiny(1msg) → Large(10msgs)
        Result:
        Tiny(1msg) → Combined(9msgs, absorbed 3 tiny) → Combined(12msgs, absorbed 2 tiny)
    
    Args:
        sessions: List of session dictionaries (must be sorted by time)
        
    Returns:
        New list of sessions with stacked tiny sessions absorbed into large ones
    """
    if not sessions or len(sessions) < 3:
        return list(sessions)
    
    result = []
    buffer_tiny = []  # Accumulate tiny sessions waiting for a large session
    
    for session in sessions:
        msg_count = session.get('messages', {}).get('total', 0)
        
        if msg_count >= MIN_SESSION_MESSAGES:
            # This is a large session - absorb all buffered tiny sessions
            if buffer_tiny:
                # Merge buffered tiny sessions into this large session
                all_real_msgs = session.get('real_msgs', [])
                merged_from_ids = list(session.get('merged_from', []))
                
                for tiny in buffer_tiny:
                    all_real_msgs.extend(tiny.get('real_msgs', []))
                    merged_from_ids.append(tiny.get('session_id', 'unknown'))
                
                # Update the large session with merged data
                _update_session_with_merged_msgs(session, all_real_msgs, merged_from_ids)
                result.append(session)
            else:
                result.append(session)
            
            # Reset buffer - this large session absorbs the next batch
            buffer_tiny = []
        
        else:
            # Tiny session - buffer it for the next large session
            buffer_tiny.append(session)
    
    # Any remaining tiny sessions at the end (no large session after them)
    # Keep them as-is
    for tiny in buffer_tiny:
        result.append(tiny)
    
    return result


def _update_session_with_merged_msgs(
    session: Dict[str, Any],
    all_real_msgs: List[Dict[str, Any]],
    merged_from_ids: List[str]
) -> None:
    """Update a session's data with messages from merged tiny sessions.
    
    Args:
        session: The large session to update
        all_real_msgs: All real messages (large + merged tiny)
        merged_from_ids: List of tiny session IDs that were merged in
    """
    if not all_real_msgs:
        return
    
    # Sort messages by timestamp
    all_real_msgs.sort(key=lambda m: m['timestamp_ms'])
    
    # Update real_msgs reference
    session['real_msgs'] = all_real_msgs
    session['messages']['total'] = len(all_real_msgs)
    
    # Recalculate message counts by sender
    msg_counts = {}
    for m in all_real_msgs:
        sender = m.get('sender_name', 'Unknown')
        msg_counts[sender] = msg_counts.get(sender, 0) + 1
    session['messages']['by_sender'] = msg_counts
    
    # Update time range
    all_timestamps = [m['timestamp_ms'] for m in all_real_msgs]
    first_ts = min(all_timestamps)
    last_ts = max(all_timestamps)
    session['start_timestamp_ms'] = first_ts
    session['end_timestamp_ms'] = last_ts
    session['date'] = _format_date(first_ts)
    session['time_range'] = f"{_format_time(first_ts)} - {_format_time(last_ts)}"
    session['duration_minutes'] = round((last_ts - first_ts) / 1000 / 60, 1)
    
    # Recalculate response times
    response_times = []
    for i in range(1, len(all_real_msgs)):
        prev = all_real_msgs[i - 1]
        curr = all_real_msgs[i]
        if prev.get('sender_name') != curr.get('sender_name'):
            diff = (curr['timestamp_ms'] - prev['timestamp_ms']) / 1000 / 60
            response_times.append(diff)
    avg_rt = sum(response_times) / len(response_times) if response_times else 0
    session['communication']['avg_response_time_minutes'] = round(avg_rt, 2)
    
    # Update participants
    session['participants']['initiated_by'] = all_real_msgs[0].get('sender_name', 'Unknown')
    session['participants']['ended_by'] = all_real_msgs[-1].get('sender_name', 'Unknown')
    
    # Recalculate languages
    lang_counts = {}
    for m in all_real_msgs:
        lang = m.get('language', 'unknown')
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
    session['communication']['languages'] = lang_counts
    
    # Mark as merged
    session['merged_from'] = merged_from_ids


def filter_sessions(sessions: List[Dict[str, Any]], merge_tiny: bool = True) -> List[Dict[str, Any]]:
    """Filter out noisy/invalid sessions, with optional tiny session merging.
    
    A valid session must have:
    - At least MIN_SESSION_MESSAGES messages (after merging tiny sessions)
    - At least MIN_SESSION_DURATION_S seconds of duration
    
    If merge_tiny=True: 1-2 message sessions are merged into adjacent larger sessions
    before filtering.
    
    Args:
        sessions: List of session dictionaries
        merge_tiny: Whether to merge tiny sessions first (default: True)
        
    Returns:
        Filtered list of valid sessions
    """
    if merge_tiny and len(sessions) > 2:
        sessions = _merge_tiny_sessions(sessions)
    
    valid = []
    for s in sessions:
        msg_count = s.get('messages', {}).get('total', 0)
        duration = s.get('duration_minutes', 0) * 60  # Convert to seconds
        
        if msg_count >= MIN_SESSION_MESSAGES and duration >= MIN_SESSION_DURATION_S:
            valid.append(s)
    
    return valid


def get_session_statistics(sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate summary statistics across all sessions.
    
    Args:
        sessions: List of session dictionaries
        
    Returns:
        Dictionary with aggregate statistics
    """
    if not sessions:
        return {}
    
    dates = [s['date'] for s in sessions]
    durations = [s['duration_minutes'] for s in sessions if s.get('duration_minutes', 0) > 0]
    response_times = [
        s['communication']['avg_response_time_minutes']
        for s in sessions
        if s.get('communication', {}).get('avg_response_time_minutes', 0) > 0
    ]
    
    # Most active day
    date_counts = {}
    for s in sessions:
        d = s['date']
        date_counts[d] = date_counts.get(d, 0) + s['messages']['total']
    
    most_active_day = max(date_counts.items(), key=lambda x: x[1]) if date_counts else (None, 0)
    
    # Longest session
    longest = max(sessions, key=lambda s: s['duration_minutes']) if sessions else None
    
    return {
        'total_sessions': len(sessions),
        'date_range': {
            'first': dates[0] if dates else None,
            'last': dates[-1] if dates else None,
            'span_days': len(set(dates))
        },
        'average_session_duration_minutes': round(sum(durations) / len(durations), 1) if durations else 0,
        'longest_session': {
            'date': longest['date'] if longest else None,
            'duration_minutes': longest['duration_minutes'] if longest else 0,
            'time_range': longest['time_range'] if longest else None
        } if longest else None,
        'most_active_day': {
            'date': most_active_day[0],
            'messages': most_active_day[1]
        } if most_active_day[0] else None,
        'average_response_time_minutes': round(sum(response_times) / len(response_times), 2) if response_times else 0
    }
