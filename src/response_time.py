"""Response time calculations for chat analysis."""

import statistics
from typing import List, Dict

from src.config import SESSION_GAP_MS


def calculate_response_times(messages: List[Dict], my_name: str,
                             session_gap_ms: int = SESSION_GAP_MS) -> Dict[str, any]:
    """Calculate in-session response times between messages.

    Response time = time between receiving a message and sending a reply, but
    only counted when the two messages fall within the same session (gap
    <= ``session_gap_ms``). Overnight/multi-day gaps are excluded so the
    headline number is a real reply latency, not sleep (BUG_REPORT C13).
    The comparison and headline lead with the MEDIAN (robust to the tail).

    Args:
        messages: List of message dictionaries
        my_name: Your name in the chat
        session_gap_ms: Gap above which a reply is treated as re-opening the
            conversation rather than an in-session response.

    Returns:
        Dictionary with response time statistics
    """
    # Sort messages by timestamp
    sorted_msgs = sorted(messages, key=lambda x: x['timestamp_ms'])

    my_response_times = []
    partner_response_times = []

    for i in range(1, len(sorted_msgs)):
        prev_msg = sorted_msgs[i-1]
        curr_msg = sorted_msgs[i]

        prev_sender = prev_msg.get('sender_name', 'Unknown')
        curr_sender = curr_msg.get('sender_name', 'Unknown')

        # Only count if it's a reply (different sender)
        if prev_sender != curr_sender:
            gap_ms = curr_msg['timestamp_ms'] - prev_msg['timestamp_ms']
            if gap_ms > session_gap_ms:
                # Re-opening the conversation, not an in-session response.
                continue
            time_diff = gap_ms / 1000 / 60  # minutes

            if curr_sender == my_name:
                my_response_times.append(time_diff)
            else:
                partner_response_times.append(time_diff)

    return {
        'my_avg_response_minutes': round(_avg(my_response_times), 2),
        'partner_avg_response_minutes': round(_avg(partner_response_times), 2),
        'my_median_response_minutes': round(_median(my_response_times), 2),
        'partner_median_response_minutes': round(_median(partner_response_times), 2),
        'my_response_stats': _stats(my_response_times),
        'partner_response_stats': _stats(partner_response_times),
        'who_delays_more': _compare_response_times(my_response_times, partner_response_times)
    }


def _avg(values: List[float]) -> float:
    """Calculate average of a list of values."""
    return sum(values) / len(values) if values else 0


def _median(values: List[float]) -> float:
    """Calculate median of a list of values."""
    return statistics.median(values) if values else 0


def _stats(values: List[float]) -> Dict[str, float]:
    """Calculate statistics for a list of values using proper quantiles."""
    if not values:
        return {'min': 0, 'max': 0, 'median': 0, 'p25': 0, 'p75': 0}

    if len(values) >= 2:
        q = statistics.quantiles(values, n=4, method='inclusive')  # [p25, p50, p75]
        p25, p50, p75 = q[0], q[1], q[2]
    else:
        p25 = p50 = p75 = values[0]

    return {
        'min': round(min(values), 2),
        'max': round(max(values), 2),
        'median': round(p50, 2),
        'p25': round(p25, 2),
        'p75': round(p75, 2)
    }


def _compare_response_times(my_times: List[float], partner_times: List[float]) -> str:
    """Compare response times (by median) to determine who delays more."""
    my_med = _median(my_times)
    partner_med = _median(partner_times)

    if my_med > partner_med:
        return "you"
    elif partner_med > my_med:
        return "partner"
    return "equal"
