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

from typing import Dict, List, Any, Tuple

from src.timeutil import to_datetime
from src.config import (
    SESSION_GAP_HOURS,
    MIN_SESSION_MESSAGES,
    MIN_SESSION_DURATION_S,
    MERGE_THRESHOLD_MINUTES,
)
# The single shared predicate (BUG_REPORT C15).
from src.normalizer import is_real_message

# Derived constant (shared gap; see BUG_REPORT B3).
SESSION_GAP_MS = int(SESSION_GAP_HOURS * 60 * 60 * 1000)


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
    return to_datetime(timestamp_ms).strftime('%H:%M')


def _format_date(timestamp_ms: int) -> str:
    """Format timestamp to YYYY-MM-DD.
    
    Args:
        timestamp_ms: Timestamp in milliseconds
        
    Returns:
        Formatted date string like "2025-05-25"
    """
    return to_datetime(timestamp_ms).strftime('%Y-%m-%d')


def chunk_messages(
    messages: List[Dict[str, Any]],
    my_name: str,
    partner_name: str,
    session_gap_hours: float = SESSION_GAP_HOURS,
    min_session_messages: int = MIN_SESSION_MESSAGES,
    min_session_duration_s: int = MIN_SESSION_DURATION_S,
    merge_threshold_minutes: float = MERGE_THRESHOLD_MINUTES,
) -> List[Dict[str, Any]]:
    """Chunk messages into conversation sessions.

    A session is a continuous stretch of conversation where the gap between
    consecutive real messages is <= ``session_gap_hours``. Parameters are
    threaded through explicitly (no module-global mutation — this function is
    now re-entrant; see BUG_REPORT A6).

    Args:
        messages: Normalized message dictionaries (sorted by timestamp)
        my_name: Your name in the chat
        partner_name: Partner's name in the chat
        session_gap_hours: Maximum gap between messages to stay in same session
        min_session_messages: Minimum messages for a valid session
        min_session_duration_s: Minimum duration (seconds) for a valid session
        merge_threshold_minutes: Only merge a tiny session into an adjacent one
            if the gap between them is within this many minutes

    Returns:
        List of session dictionaries. Each carries a ``valid`` flag; invalid
        (micro-interaction) sessions are retained rather than deleted (B2).
    """
    if not messages:
        return []

    gap_ms = int(session_gap_hours * 60 * 60 * 1000)

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

        if _get_timestamp_ms(curr_msg) - _get_timestamp_ms(prev_msg) > gap_ms:
            sessions.append(_build_session(current_session_msgs, my_name, partner_name, len(sessions)))
            current_session_msgs = [curr_msg]
        else:
            current_session_msgs.append(curr_msg)

    # Don't forget the last session
    if current_session_msgs:
        sessions.append(_build_session(current_session_msgs, my_name, partner_name, len(sessions)))

    # Enrich each session with ALL messages (including system/media) in range
    _enrich_sessions_with_all_messages(sessions, messages)

    # Merge nearby tiny sessions, tag validity, keep all data
    sessions = filter_sessions(
        sessions,
        merge_tiny=True,
        min_session_messages=min_session_messages,
        min_session_duration_s=min_session_duration_s,
        merge_threshold_minutes=merge_threshold_minutes,
    )

    return sessions


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


def _merge_tiny_sessions(
    sessions: List[Dict[str, Any]],
    min_session_messages: int = MIN_SESSION_MESSAGES,
    merge_threshold_minutes: float = MERGE_THRESHOLD_MINUTES,
) -> List[Dict[str, Any]]:
    """Merge tiny sessions into the next large session — but only if NEARBY.

    A tiny (<min_session_messages) session is only absorbed into the following
    large session when the gap between them is within ``merge_threshold_minutes``.
    A tiny exchange months away from the large session is NOT merged (which used
    to corrupt the large session's duration/date/response-time); it is retained
    as a standalone micro-interaction instead of being deleted (BUG_REPORT
    B1/B2).

    Args:
        sessions: List of session dictionaries (sorted by time)
        min_session_messages: Threshold below which a session is "tiny"
        merge_threshold_minutes: Max gap (minutes) to allow a merge

    Returns:
        New list of sessions; no data is dropped.
    """
    if not sessions:
        return list(sessions)

    threshold_ms = merge_threshold_minutes * 60 * 1000
    result = []
    buffer_tiny = []  # Tiny sessions awaiting a nearby large session

    for session in sessions:
        msg_count = session.get('messages', {}).get('total', 0)

        if msg_count >= min_session_messages:
            large_start = session.get('start_timestamp_ms', 0)
            mergeable, kept = [], []
            for tiny in buffer_tiny:
                gap = large_start - tiny.get('end_timestamp_ms', 0)
                if 0 <= gap <= threshold_ms:
                    mergeable.append(tiny)
                else:
                    kept.append(tiny)

            # Non-mergeable tinies stay in place (chronologically before large)
            result.extend(kept)

            if mergeable:
                all_real_msgs = list(session.get('real_msgs', []))
                merged_from_ids = list(session.get('merged_from', []))
                for tiny in mergeable:
                    all_real_msgs.extend(tiny.get('real_msgs', []))
                    merged_from_ids.append(tiny.get('session_id', 'unknown'))
                _update_session_with_merged_msgs(session, all_real_msgs, merged_from_ids)

            result.append(session)
            buffer_tiny = []
        else:
            buffer_tiny.append(session)

    # Trailing tiny sessions (no large session after them) are kept, not deleted.
    result.extend(buffer_tiny)

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


def filter_sessions(
    sessions: List[Dict[str, Any]],
    merge_tiny: bool = True,
    min_session_messages: int = MIN_SESSION_MESSAGES,
    min_session_duration_s: int = MIN_SESSION_DURATION_S,
    merge_threshold_minutes: float = MERGE_THRESHOLD_MINUTES,
) -> List[Dict[str, Any]]:
    """Tag sessions with validity instead of silently deleting data.

    A session is ``valid`` when it has at least ``min_session_messages`` messages
    and lasts at least ``min_session_duration_s`` seconds (after nearby tiny
    sessions are merged). Invalid (micro-interaction) sessions are RETAINED with
    ``valid: False`` so no messages vanish without a trace (BUG_REPORT B2).

    Returns:
        The full list of sessions, each carrying a ``valid`` boolean flag.
    """
    if merge_tiny and len(sessions) > 1:
        sessions = _merge_tiny_sessions(
            sessions,
            min_session_messages=min_session_messages,
            merge_threshold_minutes=merge_threshold_minutes,
        )

    valid_count = 0
    dropped_msgs = 0
    for s in sessions:
        msg_count = s.get('messages', {}).get('total', 0)
        duration = s.get('duration_minutes', 0) * 60  # seconds
        is_valid = msg_count >= min_session_messages and duration >= min_session_duration_s
        s['valid'] = is_valid
        if is_valid:
            valid_count += 1
        else:
            dropped_msgs += msg_count

    if dropped_msgs:
        print(f"   [sessions] {len(sessions) - valid_count} micro-interaction "
              f"session(s) kept (valid=False), covering {dropped_msgs} message(s)")

    return sessions


def get_session_statistics(sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate summary statistics across all sessions.
    
    Args:
        sessions: List of session dictionaries
        
    Returns:
        Dictionary with aggregate statistics
    """
    # Only valid sessions contribute to aggregate stats; micro-interactions are
    # retained in the data but excluded here (BUG_REPORT B2).
    sessions = [s for s in sessions if s.get('valid', True)]

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
