"""Response time calculations for chat analysis."""

from typing import List, Dict


def calculate_response_times(messages: List[Dict], my_name: str) -> Dict[str, any]:
    """Calculate response times between messages.
    
    Response time = time between receiving a message and sending a reply.
    
    Args:
        messages: List of message dictionaries
        my_name: Your name in the chat
        
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
            time_diff = (
                curr_msg['timestamp_ms'] - prev_msg['timestamp_ms']
            ) / 1000 / 60  # Convert to minutes
            
            if curr_sender == my_name:
                my_response_times.append(time_diff)
            else:
                partner_response_times.append(time_diff)
    
    return {
        'my_avg_response_minutes': round(_avg(my_response_times), 2),
        'partner_avg_response_minutes': round(_avg(partner_response_times), 2),
        'my_response_stats': _stats(my_response_times),
        'partner_response_stats': _stats(partner_response_times),
        'who_delays_more': _compare_response_times(my_response_times, partner_response_times)
    }


def _avg(values: List[float]) -> float:
    """Calculate average of a list of values."""
    return sum(values) / len(values) if values else 0


def _stats(values: List[float]) -> Dict[str, float]:
    """Calculate statistics for a list of values."""
    if not values:
        return {'min': 0, 'max': 0, 'median': 0, 'p25': 0, 'p75': 0}
    
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    return {
        'min': round(sorted_vals[0], 2),
        'max': round(sorted_vals[-1], 2),
        'median': round(sorted_vals[n//2], 2),
        'p25': round(sorted_vals[n//4], 2),
        'p75': round(sorted_vals[3*n//4], 2)
    }


def _compare_response_times(my_times: List[float], partner_times: List[float]) -> str:
    """Compare response times to determine who delays more."""
    my_avg = _avg(my_times)
    partner_avg = _avg(partner_times)
    
    if my_avg > partner_avg:
        return "you"
    elif partner_avg > my_avg:
        return "partner"
    return "equal"
