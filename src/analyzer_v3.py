"""
Instagram V3.0 Metrics - Advanced Psychological and Behavioral Analysis

Adapted from Telegram Analysis V3.0 for Instagram data format.
Key adaptations:
- Use 'content' instead of 'text'
- Use 'sender_name' instead of 'from'
- Use 'timestamp_ms' (milliseconds) instead of ISO date strings
- Handle Instagram-specific message types and media
"""

import re
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any
import numpy as np


def _get_timestamp(msg: Dict) -> datetime:
    """Convert Instagram timestamp_ms to datetime."""
    return datetime.fromtimestamp(msg['timestamp_ms'] / 1000)


def _get_text(msg: Dict) -> str:
    """Extract text content from Instagram message."""
    content = msg.get('content', '')
    if not content:
        return ''
    # Skip non-text messages
    if content in ['Liked a message', 'sent an attachment.', '']:
        return ''
    return content


def expressive_lengthening_index(messages: List[Dict], users: List[str]) -> Dict[str, float]:
    """
    Frequency of elongated words (e.g., 'heyyy', 'კაააიი')
    Regex: r'(.)\1{2,}' to find 3+ repeating characters
    
    Returns: Dictionary mapping each user to their elongation ratio
    """
    elongated_pattern = re.compile(r'(.)\1{2,}')
    
    user_stats = {user: {"elongated": 0, "total_words": 0} for user in users}
    
    for msg in messages:
        user = msg.get('sender_name', 'Unknown')
        if user not in user_stats:
            continue
            
        text = _get_text(msg)
        if not text:
            continue
        
        words = text.split()
        user_stats[user]["total_words"] += len(words)
        
        for word in words:
            if elongated_pattern.search(word):
                user_stats[user]["elongated"] += 1
    
    result = {}
    for user, stats in user_stats.items():
        if stats["total_words"] > 0:
            result[user] = round(stats["elongated"] / stats["total_words"], 4)
        else:
            result[user] = 0.0
    
    return result


def emotional_cooling_alert(messages: List[Dict], users: List[str]) -> Dict[str, Dict]:
    """
    Sudden drop in expressive lengthening and emojis (>40% over 14 days)
    
    Instagram adaptation: Uses emoji and expressive lengthening only
    (no edit history available)
    """
    elongated_pattern = re.compile(r'(.)\1{2,}')
    emoji_pattern = re.compile(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]+', re.UNICODE)
    
    # Group messages by date
    daily_stats = defaultdict(lambda: {"elongated": 0, "emojis": 0, "words": 0})
    
    for msg in messages:
        timestamp = _get_timestamp(msg)
        date_str = timestamp.strftime('%Y-%m-%d')
        text = _get_text(msg)
        if not text:
            continue
        
        words = text.split()
        daily_stats[date_str]["words"] += len(words)
        daily_stats[date_str]["emojis"] += len(emoji_pattern.findall(text))
        
        for word in words:
            if elongated_pattern.search(word):
                daily_stats[date_str]["elongated"] += 1
    
    # Calculate 14-day rolling average and detect drops
    sorted_dates = sorted(daily_stats.keys())
    alerts = {}
    
    if len(sorted_dates) < 14:
        return {"message": "Insufficient data for 14-day rolling analysis", "total_cold_shifts": 0}
    
    for i in range(13, len(sorted_dates)):
        # Previous 14 days
        prev_window = sorted_dates[i-14:i]
        # Current 14 days
        curr_window = sorted_dates[i-13:i+1]
        
        prev_score = sum(daily_stats[d]["elongated"] + daily_stats[d]["emojis"] for d in prev_window) / 14
        curr_score = sum(daily_stats[d]["elongated"] + daily_stats[d]["emojis"] for d in curr_window) / 14
        
        if prev_score > 0:
            drop = (prev_score - curr_score) / prev_score
            if drop > 0.4:  # 40% drop
                alerts[sorted_dates[i]] = {
                    "drop_percentage": round(drop * 100, 2),
                    "previous_avg": round(prev_score, 2),
                    "current_avg": round(curr_score, 2),
                    "status": "COLD_SHIFT_DETECTED"
                }
    
    return {"alerts": alerts, "total_cold_shifts": len(alerts)}


def final_word_dominance(messages: List[Dict], users: List[str]) -> Dict[str, float]:
    """
    Who consistently sends the last message in a session (gap > 4h)
    
    Instagram adaptation: Uses timestamp_ms for gap calculation
    """
    if not messages:
        return {user: 0.0 for user in users}
    
    # Sort messages by timestamp
    sorted_msgs = sorted(messages, key=lambda x: x.get('timestamp_ms', 0))
    
    # Identify sessions (gap > 4 hours = 14400000 ms)
    SESSION_GAP_MS = 4 * 60 * 60 * 1000
    
    user_session_ends = {user: 0 for user in users}
    total_sessions = 0
    current_session_end_user = None
    
    for i in range(1, len(sorted_msgs)):
        prev_msg = sorted_msgs[i-1]
        curr_msg = sorted_msgs[i]
        
        gap_ms = curr_msg['timestamp_ms'] - prev_msg['timestamp_ms']
        
        if gap_ms > SESSION_GAP_MS:
            # New session started, count previous session end
            total_sessions += 1
            if current_session_end_user in user_session_ends:
                user_session_ends[current_session_end_user] += 1
            current_session_end_user = None
        
        current_session_end_user = curr_msg.get('sender_name', 'Unknown')
    
    # Count final session
    if current_session_end_user:
        total_sessions += 1
        if current_session_end_user in user_session_ends:
            user_session_ends[current_session_end_user] += 1
    
    # Calculate percentages
    result = {}
    for user, count in user_session_ends.items():
        if total_sessions > 0:
            result[user] = round(count / total_sessions, 4)
        else:
            result[user] = 0.0
    
    return result


def thought_fragmentation_index(messages: List[Dict], users: List[str]) -> Dict[str, float]:
    """
    Tendency to break single thoughts into multiple rapid-fire messages (3+ in 15s)
    
    Instagram adaptation: Uses timestamp_ms for timing
    """
    if not messages:
        return {user: 0.0 for user in users}
    
    # Sort messages by timestamp
    sorted_msgs = sorted(messages, key=lambda x: x.get('timestamp_ms', 0))
    
    # Identify sessions and fragmentation
    SESSION_GAP_MS = 4 * 60 * 60 * 1000
    FRAGMENTATION_WINDOW_MS = 15 * 1000  # 15 seconds
    
    user_fragmentation = {user: {"fragmented_sessions": 0, "total_sessions": 0} for user in users}
    
    current_session = []
    
    for msg in sorted_msgs:
        if current_session:
            gap_ms = msg['timestamp_ms'] - current_session[-1]['timestamp_ms']
            
            if gap_ms > SESSION_GAP_MS:
                # Process current session
                if len(current_session) >= 3:
                    # Check for fragmentation (3+ messages within 15s)
                    for i in range(len(current_session) - 2):
                        t1 = current_session[i]['timestamp_ms']
                        t3 = current_session[i+2]['timestamp_ms']
                        if (t3 - t1) <= FRAGMENTATION_WINDOW_MS:
                            # Found fragmentation
                            for m in current_session:
                                u = m.get('sender_name', 'Unknown')
                                if u in user_fragmentation:
                                    user_fragmentation[u]["fragmented_sessions"] += 1
                                    break
                
                # Count total sessions per user
                for m in current_session:
                    u = m.get('sender_name', 'Unknown')
                    if u in user_fragmentation:
                        user_fragmentation[u]["total_sessions"] += 1
                
                current_session = []
        
        current_session.append(msg)
    
    # Calculate ratios
    result = {}
    for user, stats in user_fragmentation.items():
        if stats["total_sessions"] > 0:
            result[user] = round(stats["fragmented_sessions"] / stats["total_sessions"], 4)
        else:
            result[user] = 0.0
    
    return result


def conversational_entropy(messages: List[Dict], users: List[str]) -> Dict[str, Dict]:
    """
    Shannon Entropy on bigram distribution per month (The 'Rut' indicator)
    
    Instagram adaptation: Uses timestamp_ms for month extraction
    """
    if not messages:
        return {user: 0.0 for user in users}
    
    # Group messages by month and user
    monthly_bigrams = defaultdict(lambda: defaultdict(list))
    
    for msg in messages:
        user = msg.get('sender_name', 'Unknown')
        text = _get_text(msg)
        if not text:
            continue
        
        text = text.lower()
        timestamp = _get_timestamp(msg)
        date_str = timestamp.strftime('%Y-%m')  # YYYY-MM
        
        words = text.split()
        bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]
        monthly_bigrams[date_str][user].extend(bigrams)
    
    # Calculate entropy per month per user
    result = defaultdict(dict)
    
    for month, users_data in monthly_bigrams.items():
        for user, bigrams in users_data.items():
            if not bigrams:
                result[month][user] = 0.0
                continue
            
            # Calculate bigram frequencies
            bigram_counts = Counter(bigrams)
            total = sum(bigram_counts.values())
            
            # Shannon Entropy: -Σ p(x)log₂p(x)
            entropy = 0
            for count in bigram_counts.values():
                p = count / total
                if p > 0:
                    entropy -= p * math.log2(p)
            
            # Normalize by max possible entropy (log2 of unique bigrams)
            max_entropy = math.log2(len(bigram_counts)) if len(bigram_counts) > 1 else 1
            normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0
            
            result[month][user] = round(normalized_entropy, 4)
    
    return dict(result)


def defensiveness_index(messages: List[Dict], users: List[str]) -> Dict[str, float]:
    """
    Usage of justification and shielding words (just, but, technically, უბრალოდ, მარა)
    
    Instagram adaptation: Uses 'content' field
    """
    # Defensiveness words in English and Georgian
    defensive_pattern = re.compile(
        r'\b(just|but|technically|however|actually|literally|უბრალოდ|პროსტა|მარა|მაგრამ|რეალურად)\b',
        re.IGNORECASE
    )
    
    user_stats = {user: {"defensive_words": 0, "total_words": 0} for user in users}
    
    for msg in messages:
        user = msg.get('sender_name', 'Unknown')
        if user not in user_stats:
            continue
        
        text = _get_text(msg)
        if not text:
            continue
        
        words = text.split()
        user_stats[user]["total_words"] += len(words)
        
        matches = defensive_pattern.findall(text.lower())
        user_stats[user]["defensive_words"] += len(matches)
    
    # Calculate per 1000 words
    result = {}
    for user, stats in user_stats.items():
        if stats["total_words"] > 0:
            result[user] = round((stats["defensive_words"] / stats["total_words"]) * 1000, 2)
        else:
            result[user] = 0.0
    
    return result


def vocabulary_contagion_rate(messages: List[Dict], users: List[str]) -> Dict[str, Dict]:
    """
    Who adopts whose slang (Cultural Driver vs Adopter)
    
    Instagram adaptation: Uses timestamp_ms for chronological ordering
    """
    if not messages:
        return {user: {} for user in users}
    
    # Sort messages by timestamp
    sorted_msgs = sorted(messages, key=lambda x: x.get('timestamp_ms', 0))
    
    # Track first usage of unique words per user
    user_word_first_use = defaultdict(dict)  # user -> {word: first_timestamp}
    user_word_count = defaultdict(lambda: defaultdict(int))  # user -> {word: count}
    
    for msg in sorted_msgs:
        user = msg.get('sender_name', 'Unknown')
        text = _get_text(msg)
        if not text:
            continue
        
        text = text.lower()
        timestamp = msg['timestamp_ms']
        
        words = text.split()
        for word in words:
            # Clean word (remove punctuation)
            word = re.sub(r'[^\w\u10A0-\u10FF]', '', word)
            if len(word) < 3:  # Ignore short words
                continue
            
            # Track first usage
            if word not in user_word_first_use[user]:
                user_word_first_use[user][word] = timestamp
            
            # Count usage
            user_word_count[user][word] += 1
    
    # Find vocabulary adoption
    contagion = defaultdict(lambda: defaultdict(int))
    
    for driver, words in user_word_first_use.items():
        for word, first_ts in words.items():
            for adopter, word_counts in user_word_count.items():
                if driver == adopter:
                    continue
                
                if word in word_counts and word_counts[word] >= 3:
                    # Check if adopter used it after driver
                    if word in user_word_first_use[adopter]:
                        adopter_ts = user_word_first_use[adopter][word]
                        if adopter_ts >= first_ts:
                            contagion[driver][adopter] += 1
    
    # Convert to regular dict
    result = {}
    for driver, adopters in contagion.items():
        result[driver] = dict(adopters)
    
    # Ensure all users are in result
    for user in users:
        if user not in result:
            result[user] = {}
    
    return result


def selective_topic_avoidance(messages: List[Dict], users: List[str]) -> Dict[str, Dict]:
    """
    Identifies topics that cause severe response delays (>3σ above baseline)
    
    Instagram adaptation: Uses keyword-based clustering (no embeddings)
    """
    if not messages:
        return {}
    
    # Simple topic clustering based on keywords
    topic_keywords = {
        "family": ["family", "mom", "dad", "parents", "მამა", "მამაშენი", "დედა"],
        "work": ["work", "job", "office", "სამუშაო", "ოფისი"],
        "social": ["party", "friends", "night", "პარტია", "გამგზავრება"],
        "conflict": ["argue", "fight", "problem", "issue", "პრობლემა", "ჩხუბი"],
        "personal": ["feel", "think", "emotion", "გრძნობა", "ფიქრი"],
    }
    
    # Calculate response times per topic
    topic_response_times = defaultdict(list)
    all_response_times = []
    
    sorted_msgs = sorted(messages, key=lambda x: x.get('timestamp_ms', 0))
    
    for i in range(1, len(sorted_msgs)):
        prev_msg = sorted_msgs[i-1]
        curr_msg = sorted_msgs[i]
        
        prev_user = prev_msg.get('sender_name', '')
        curr_user = curr_msg.get('sender_name', '')
        
        # Only count if different users (actual response)
        if prev_user == curr_user:
            continue
        
        prev_text = _get_text(prev_msg).lower()
        if not prev_text:
            continue
        
        # Calculate response time in minutes
        response_time = (curr_msg['timestamp_ms'] - prev_msg['timestamp_ms']) / 1000 / 60
        
        all_response_times.append(response_time)
        
        # Identify topic
        for topic, keywords in topic_keywords.items():
            if any(kw in prev_text for kw in keywords):
                topic_response_times[topic].append(response_time)
                break
    
    # Calculate baseline and flag anomalies
    if not all_response_times:
        return {}
    
    baseline_mean = sum(all_response_times) / len(all_response_times)
    baseline_std = (sum((x - baseline_mean) ** 2 for x in all_response_times) / len(all_response_times)) ** 0.5
    
    # Find topics with response time > 3σ above baseline
    flagged_topics = {}
    for topic, times in topic_response_times.items():
        if times:
            topic_mean = sum(times) / len(times)
            if baseline_std > 0:
                deviation = (topic_mean - baseline_mean) / baseline_std
                if deviation > 3:
                    flagged_topics[topic] = {
                        "delay_multiplier": round(deviation, 2),
                        "topic_mean_minutes": round(topic_mean, 2),
                        "baseline_mean_minutes": round(baseline_mean, 2),
                        "sample_size": len(times)
                    }
    
    return flagged_topics


def conversational_gini_coefficient(messages: List[Dict], users: List[str]) -> Dict[str, float]:
    """
    Economic inequality of effort (rolling 30-day Gini coefficient)
    
    Instagram adaptation: Uses timestamp_ms and Instagram media types
    """
    if not messages:
        return {user: 0.0 for user in users}
    
    # Group messages by 30-day periods
    user_effort_by_period = defaultdict(lambda: defaultdict(float))
    
    for msg in messages:
        user = msg.get('sender_name', 'Unknown')
        timestamp = _get_timestamp(msg)
        date_str = timestamp.strftime('%Y-%m')  # YYYY-MM
        text = _get_text(msg)
        
        # Effort score = character count + media bonus
        effort = len(text) if text else 0
        
        # Check for media
        if msg.get('photos'):
            effort += 100 * len(msg['photos'])
        if msg.get('videos'):
            effort += 200 * len(msg['videos'])
        if msg.get('audio_files'):
            effort += 200 * len(msg['audio_files'])
        
        user_effort_by_period[date_str][user] += effort
    
    # Calculate Gini for each period
    def calculate_gini(values):
        if not values or len(values) < 2:
            return 0.0
        
        sorted_values = sorted(values)
        n = len(sorted_values)
        cumsum = np.cumsum(sorted_values)
        
        # Gini formula
        gini = (2 * sum((i + 1) * v for i, v in enumerate(sorted_values)) - (n + 1) * cumsum[-1]) / (n * cumsum[-1])
        return gini if cumsum[-1] > 0 else 0.0
    
    result = {}
    for period, efforts in user_effort_by_period.items():
        values = list(efforts.values())
        gini = calculate_gini(values)
        result[period] = round(gini, 4)
    
    return result


def conversational_inertia(messages: List[Dict], users: List[str]) -> float:
    """
    Force required to restart a dead chat (>72h gap)
    
    Instagram adaptation: Uses timestamp_ms for gap detection
    """
    if not messages:
        return 0.0
    
    # Sort messages
    sorted_msgs = sorted(messages, key=lambda x: x.get('timestamp_ms', 0))
    
    # Find sessions after >72h gaps
    DEAD_CHAT_GAP_MS = 72 * 60 * 60 * 1000  # 72 hours in milliseconds
    
    restart_forces = []
    in_dead_chat_recovery = False
    current_restart_effort = 0
    
    for msg in sorted_msgs:
        text = _get_text(msg)
        
        # Media bonus
        effort = len(text) if text else 0
        if msg.get('photos'):
            effort += 100 * len(msg['photos'])
        if msg.get('videos'):
            effort += 200 * len(msg['videos'])
        if msg.get('audio_files'):
            effort += 200 * len(msg['audio_files'])
        
        if restart_forces or in_dead_chat_recovery:
            # Check for gap
            prev_ts = sorted_msgs[sorted_msgs.index(msg) - 1]['timestamp_ms'] if msg != sorted_msgs[0] else msg['timestamp_ms']
            gap_ms = msg['timestamp_ms'] - prev_ts if msg != sorted_msgs[0] else 0
            
            if gap_ms > DEAD_CHAT_GAP_MS and not in_dead_chat_recovery:
                # Dead chat detected, measure restart effort
                in_dead_chat_recovery = True
                current_restart_effort = effort
            elif in_dead_chat_recovery and gap_ms <= DEAD_CHAT_GAP_MS:
                # Still in recovery phase
                current_restart_effort += effort
            elif in_dead_chat_recovery:
                # Recovery phase ended
                restart_forces.append(current_restart_effort)
                in_dead_chat_recovery = False
        elif not restart_forces and msg != sorted_msgs[0]:
            # First message after initial skip
            pass
    
    # Simplified approach
    restart_forces = []
    last_msg_ts = None
    in_recovery = False
    recovery_effort = 0
    
    for msg in sorted_msgs:
        text = _get_text(msg)
        effort = len(text) if text else 0
        if msg.get('photos'):
            effort += 100 * len(msg['photos'])
        if msg.get('videos'):
            effort += 200 * len(msg['videos'])
        if msg.get('audio_files'):
            effort += 200 * len(msg['audio_files'])
        
        if last_msg_ts is not None:
            gap_ms = msg['timestamp_ms'] - last_msg_ts
            
            if gap_ms > DEAD_CHAT_GAP_MS:
                # Dead chat detected
                in_recovery = True
                recovery_effort = effort
            elif in_recovery:
                # Continue counting recovery effort
                recovery_effort += effort
            else:
                # Normal message
                pass
            
            # End recovery if gap is small enough after a dead chat
            if in_recovery and gap_ms < 1 * 60 * 60 * 1000:  # Less than 1 hour
                restart_forces.append(recovery_effort)
                in_recovery = False
                recovery_effort = 0
        
        last_msg_ts = msg['timestamp_ms']
    
    # Average force
    if restart_forces:
        return round(sum(restart_forces) / len(restart_forces), 2)
    return 0.0


def signal_to_noise_ratio(messages: List[Dict], users: List[str]) -> Dict[str, float]:
    """
    Depth of conversation vs idle filler (Signal/Noise)
    
    Instagram adaptation: Uses 'content' field and Instagram media types
    """
    # Stopwords and filler words
    stop_words = {
        'english': {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 
                   'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 
                   'should', 'may', 'might', 'must', 'ok', 'okay', 'yeah', 'yes', 'no'},
        'georgian': {'კი', 'ხო', 'არა', 'მე', 'თქვენ', 'მეგობარი', 'როგორ', 'კაი', 'ოკ'}
    }
    
    emoji_pattern = re.compile(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]+', re.UNICODE)
    
    user_stats = {user: {"signal": 0, "noise": 0} for user in users}
    
    for msg in messages:
        user = msg.get('sender_name', 'Unknown')
        if user not in user_stats:
            continue
        
        text = _get_text(msg)
        if not text:
            continue
        
        text_lower = text.lower()
        words = text.split()
        
        # Count signal (longer words, media)
        for word in words:
            word_clean = re.sub(r'[^\w\u10A0-\u10FF]', '', word)
            if len(word_clean) >= 4:
                user_stats[user]["signal"] += 1
        
        # Count noise (stopwords, short affirmations)
        for word in words:
            if word in stop_words['english'] or word in stop_words['georgian']:
                user_stats[user]["noise"] += 1
        
        # Media counts as signal
        if msg.get('photos') or msg.get('videos') or msg.get('audio_files'):
            user_stats[user]["signal"] += 1
        
        # Emojis count as noise
        user_stats[user]["noise"] += len(emoji_pattern.findall(text))
    
    # Calculate ratio
    result = {}
    for user, stats in user_stats.items():
        if stats["noise"] > 0:
            result[user] = round(stats["signal"] / stats["noise"], 4)
        else:
            result[user] = float(stats["signal"]) if stats["signal"] > 0 else 0.0
    
    return result


def chaser_retreater_oscillation(messages: List[Dict], users: List[str]) -> Dict[str, Dict]:
    """
    Anxious-avoidant pursuit dynamics (rolling 3-day correlation)
    
    Instagram adaptation: Uses timestamp_ms for date extraction
    """
    if not messages or len(users) < 2:
        return {}
    
    # Group messages by day
    daily_counts = defaultdict(lambda: {user: 0 for user in users})
    
    for msg in messages:
        timestamp = _get_timestamp(msg)
        date_str = timestamp.strftime('%Y-%m-%d')
        user = msg.get('sender_name', 'Unknown')
        if user in daily_counts[date_str]:
            daily_counts[date_str][user] += 1
    
    # Calculate rolling 3-day Pearson correlation
    sorted_dates = sorted(daily_counts.keys())
    
    correlations = []
    for i in range(2, len(sorted_dates)):
        window = sorted_dates[i-3:i]
        
        # Get counts for first two users
        user_a_counts = [daily_counts[d].get(users[0], 0) for d in window]
        user_b_counts = [daily_counts[d].get(users[1], 0) for d in window]
        
        if len(user_a_counts) != 3 or len(user_b_counts) != 3:
            continue
        
        # Pearson correlation
        mean_a = sum(user_a_counts) / 3
        mean_b = sum(user_b_counts) / 3
        
        try:
            numerator = sum((user_a_counts[j] - mean_a) * (user_b_counts[j] - mean_b) for j in range(3))
            denom_a = sum((user_a_counts[j] - mean_a) ** 2 for j in range(3)) ** 0.5
            denom_b = sum((user_b_counts[j] - mean_b) ** 2 for j in range(3)) ** 0.5
            
            if denom_a > 0 and denom_b > 0:
                correlation = numerator / (denom_a * denom_b)
                correlations.append((sorted_dates[i], correlation))
        except (ZeroDivisionError, IndexError):
            continue
    
    # Find periods with strong negative correlation (< -0.6)
    result = {}
    for date, corr in correlations:
        if corr < -0.6:
            result[date] = {
                "correlation": round(corr, 4),
                "status": "CHASER_RETREATER_DETECTED"
            }
    
    return result


def tit_for_tat_retaliation_score(messages: List[Dict], users: List[str]) -> Dict[str, float]:
    """
    Intentional mirroring of delayed responses (Game Theory - Pettiness)
    
    Instagram adaptation: Uses timestamp_ms for delay calculation
    """
    if not messages:
        return {user: 0.0 for user in users}
    
    # Sort messages
    sorted_msgs = sorted(messages, key=lambda x: x.get('timestamp_ms', 0))
    
    # Track response time pairs (A responds to B, then B responds to A)
    user_delays = defaultdict(list)
    
    for i in range(1, len(sorted_msgs)):
        prev_msg = sorted_msgs[i-1]
        curr_msg = sorted_msgs[i]
        
        prev_user = prev_msg.get('sender_name', '')
        curr_user = curr_msg.get('sender_name', '')
        
        if prev_user == curr_user:
            continue
        
        # Calculate delay in minutes
        delay = (curr_msg['timestamp_ms'] - prev_msg['timestamp_ms']) / 1000 / 60
        
        # Track delay for the responder
        user_delays[curr_user].append(delay)
    
    # Calculate R² between consecutive delays (tit-for-tat pattern)
    result = {}
    for user, delays in user_delays.items():
        if len(delays) < 3:
            result[user] = 0.0
            continue
        
        # Calculate autocorrelation (R²)
        n = len(delays)
        mean = sum(delays) / n
        
        # Correlation between delay[i] and delay[i+1]
        numerator = sum((delays[i] - mean) * (delays[i+1] - mean) for i in range(n-1))
        denom = sum((delays[i] - mean) ** 2 for i in range(n))
        
        if denom > 0:
            r = numerator / denom
            r_squared = r ** 2
            result[user] = round(r_squared, 4)
        else:
            result[user] = 0.0
    
    return result


def temporal_syncopation_variance(messages: List[Dict], users: List[str]) -> Dict[str, float]:
    """
    Unpredictability of conversational rhythm (Music Theory)
    
    Instagram adaptation: Uses timestamp_ms for tempo calculation
    """
    if not messages:
        return {user: 0.0 for user in users}
    
    # Sort messages
    sorted_msgs = sorted(messages, key=lambda x: x.get('timestamp_ms', 0))
    
    # Calculate baseline tempo per session
    SESSION_GAP_MS = 4 * 60 * 60 * 1000  # 4 hours
    user_deviation_variances = defaultdict(list)
    
    current_session = []
    
    for msg in sorted_msgs:
        if current_session:
            gap_ms = msg['timestamp_ms'] - current_session[-1]['timestamp_ms']
            
            if gap_ms > SESSION_GAP_MS:
                # Process session
                if len(current_session) >= 3:
                    # Calculate baseline tempo
                    tempos = []
                    for i in range(1, len(current_session)):
                        t1 = current_session[i-1]['timestamp_ms']
                        t2 = current_session[i]['timestamp_ms']
                        tempos.append((t2 - t1) / 1000)  # Convert to seconds
                    
                    if tempos:
                        baseline = sum(tempos) / len(tempos)
                        
                        # Calculate variance per user
                        user_tempos = defaultdict(list)
                        for i in range(1, len(current_session)):
                            user = current_session[i].get('sender_name', 'Unknown')
                            t1 = current_session[i-1]['timestamp_ms']
                            t2 = current_session[i]['timestamp_ms']
                            tempo = (t2 - t1) / 1000
                            deviation = tempo - baseline
                            user_tempos[user].append(deviation)
                        
                        # Calculate variance
                        for user, deviations in user_tempos.items():
                            if len(deviations) > 1:
                                variance = sum(d ** 2 for d in deviations) / len(deviations)
                                user_deviation_variances[user].append(variance)
                
                current_session = []
        
        current_session.append(msg)
    
    # Average variance per user
    result = {}
    for user, variances in user_deviation_variances.items():
        if variances:
            result[user] = round(sum(variances) / len(variances), 4)
        else:
            result[user] = 0.0
    
    return result
