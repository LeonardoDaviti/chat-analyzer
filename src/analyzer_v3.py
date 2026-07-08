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

from src.timeutil import to_datetime, DEFAULT_TIMEZONE
from src.config import SESSION_GAP_HOURS
from src.normalizer import is_system_message

# Single session-gap constant shared with the pipeline chunker (BUG_REPORT B3).
SESSION_GAP_MS = int(SESSION_GAP_HOURS * 60 * 60 * 1000)


def _get_timestamp(msg: Dict, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    """Convert Instagram timestamp_ms to a timezone-aware datetime."""
    return to_datetime(msg['timestamp_ms'], timezone)


def _get_text(msg: Dict) -> str:
    """Extract real text content from an Instagram message.

    Returns '' for system notifications and media-only messages.
    """
    content = msg.get('content', '')
    if not content:
        return ''
    if is_system_message(msg):
        return ''
    return content


def _split_sessions(sorted_msgs: List[Dict], gap_ms: int = SESSION_GAP_MS) -> List[List[Dict]]:
    """Split chronologically-sorted messages into sessions on gaps > gap_ms.

    Guarantees the final session is emitted (fixes the "last session never
    processed" flush bug shared by several metrics — BUG_REPORT C1/C8).
    """
    sessions: List[List[Dict]] = []
    current: List[Dict] = []
    for msg in sorted_msgs:
        if current:
            gap = msg['timestamp_ms'] - current[-1]['timestamp_ms']
            if gap > gap_ms:
                sessions.append(current)
                current = []
        current.append(msg)
    if current:
        sessions.append(current)
    return sessions


def expressive_lengthening_index(messages: List[Dict], users: List[str]) -> Dict[str, float]:
    """
    Frequency of elongated words (e.g., 'heyyy', 'კაააიი')
    Regex: r'(.)\1{2,}' to find 3+ repeating characters
    
    Returns: Dictionary mapping each user to their elongation ratio
    """
    # Only count 3+ repeats of an ALPHABETIC character ("heyyy", "კაააი").
    # This avoids matching URLs ("www"), ellipses ("..."), numerals ("2000")
    # and repeated emoji (BUG_REPORT C12).
    elongated_pattern = re.compile(r'([^\W\d_])\1{2,}', re.UNICODE)
    url_pattern = re.compile(r'https?://\S+|www\.\S+')

    user_stats = {user: {"elongated": 0, "total_words": 0} for user in users}

    for msg in messages:
        user = msg.get('sender_name', 'Unknown')
        if user not in user_stats:
            continue

        text = _get_text(msg)
        if not text:
            continue

        # Strip URLs before tokenising
        text = url_pattern.sub(' ', text)

        words = text.split()
        user_stats[user]["total_words"] += len(words)

        for word in words:
            # Skip pure numerals
            if word.isdigit():
                continue
            if elongated_pattern.search(word):
                user_stats[user]["elongated"] += 1

    result = {}
    for user, stats in user_stats.items():
        if stats["total_words"] > 0:
            result[user] = round(stats["elongated"] / stats["total_words"], 4)
        else:
            result[user] = 0.0
    
    return result


# Broadened emoji matcher: pictographs, dingbats, hearts (U+2764), supplemental
# symbols (U+1F900–U+1F9FF), skin-tone modifiers, variation selectors.
EMOJI_PATTERN = re.compile(
    '['
    '\U0001F300-\U0001FAFF'   # symbols & pictographs + supplemental + extended
    '\U00002600-\U000027BF'   # misc symbols & dingbats
    '\U0001F1E0-\U0001F1FF'   # regional indicators
    '\U00002764'              # heavy black heart
    '\U0001F3FB-\U0001F3FF'   # skin-tone modifiers
    '\U0000FE0F'              # variation selector-16
    ']+',
    re.UNICODE,
)

_ELONGATED_PATTERN = re.compile(r'([^\W\d_])\1{2,}', re.UNICODE)


def _daily_calendar(dates):
    """Return the continuous list of YYYY-MM-DD strings from min..max inclusive."""
    if not dates:
        return []
    lo = min(dates)
    hi = max(dates)
    out = []
    d = lo
    while d <= hi:
        out.append(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)
    return out


def emotional_cooling_alert(messages: List[Dict], users: List[str],
                            timezone: str = DEFAULT_TIMEZONE,
                            window_days: int = 14) -> Dict[str, Dict]:
    """
    Sudden drop in per-message expressiveness (emojis + elongation) over a
    disjoint pair of ``window_days`` windows, computed per user.

    Fixes (BUG_REPORT C3):
      - continuous daily calendar (silent days = 0), not just active days;
      - DISJOINT windows (previous N days vs current N days) so a genuine drop
        is actually reachable;
      - normalised by message volume (expressiveness *per message*);
      - per-user so we can see who cooled;
      - broadened emoji regex.
    """
    # date(user) -> {"expr": int, "msgs": int}
    per_user_daily = {u: defaultdict(lambda: {"expr": 0, "msgs": 0}) for u in users}
    all_dates = []

    for msg in messages:
        user = msg.get('sender_name', 'Unknown')
        if user not in per_user_daily:
            continue
        text = _get_text(msg)
        if not text:
            continue
        dt = _get_timestamp(msg, timezone)
        all_dates.append(dt.date())
        date_str = dt.strftime('%Y-%m-%d')

        expr = len(EMOJI_PATTERN.findall(text))
        for word in text.split():
            if _ELONGATED_PATTERN.search(word):
                expr += 1

        cell = per_user_daily[user][date_str]
        cell["expr"] += expr
        cell["msgs"] += 1

    calendar = _daily_calendar(all_dates)

    # Need two disjoint windows of window_days each.
    if len(calendar) < 2 * window_days:
        return {"message": "Insufficient data for cooling analysis",
                "alerts": {}, "total_cold_shifts": 0}

    alerts = {}

    def window_score(daily, days):
        expr = sum(daily[d]["expr"] for d in days if d in daily)
        msgs = sum(daily[d]["msgs"] for d in days if d in daily)
        return (expr / msgs) if msgs > 0 else 0.0

    for user in users:
        daily = per_user_daily[user]
        for i in range(2 * window_days, len(calendar) + 1):
            prev_window = calendar[i - 2 * window_days:i - window_days]
            curr_window = calendar[i - window_days:i]

            prev_score = window_score(daily, prev_window)
            curr_score = window_score(daily, curr_window)

            if prev_score > 0:
                drop = (prev_score - curr_score) / prev_score
                if drop > 0.4:
                    key = f"{user} {curr_window[-1]}"
                    alerts[key] = {
                        "user": user,
                        "date": curr_window[-1],
                        "drop_percentage": round(drop * 100, 2),
                        "previous_avg": round(prev_score, 4),
                        "current_avg": round(curr_score, 4),
                        "status": "COLD_SHIFT_DETECTED",
                    }

    return {"alerts": alerts, "total_cold_shifts": len(alerts)}


def final_word_dominance(messages: List[Dict], users: List[str],
                         sessions: List[Dict] = None) -> Dict[str, float]:
    """
    Who consistently sends the last message in a session.

    Fixes (BUG_REPORT C2/B3):
      - the first session's ender is no longer lost when that session is a
        single message (percentages now sum to 1);
      - uses the SHARED session gap (not a private 4h constant);
      - can consume the chunker's precomputed ``sessions`` (whose
        ``participants.ended_by`` field already exists) for exact reconciliation
        with sessions.json.
    """
    user_session_ends = {user: 0 for user in users}
    total_sessions = 0

    if sessions is not None:
        # Preferred path: reuse the chunker's sessions directly.
        for s in sessions:
            ended_by = s.get('participants', {}).get('ended_by')
            total_sessions += 1
            if ended_by in user_session_ends:
                user_session_ends[ended_by] += 1
    else:
        if not messages:
            return {user: 0.0 for user in users}
        sorted_msgs = sorted(messages, key=lambda x: x.get('timestamp_ms', 0))
        for session_msgs in _split_sessions(sorted_msgs):
            total_sessions += 1
            ender = session_msgs[-1].get('sender_name', 'Unknown')
            if ender in user_session_ends:
                user_session_ends[ender] += 1

    result = {}
    for user, count in user_session_ends.items():
        result[user] = round(count / total_sessions, 4) if total_sessions > 0 else 0.0

    return result


def thought_fragmentation_index(messages: List[Dict], users: List[str]) -> Dict[str, float]:
    """
    Tendency to break single thoughts into rapid-fire bursts (3+ messages from
    the SAME sender within 15s).

    Fixes (BUG_REPORT C1):
      - denominator counts SESSIONS the user participated in, not messages
        (the old missing ``break`` made it a message count);
      - the final session is processed (no missing flush);
      - a burst requires the same sender for all 3 messages (a fast ping-pong
        no longer counts);
      - credit goes to the burst's sender, not the session's first sender.
    Result is a ratio in [0, 1] by construction.
    """
    if not messages:
        return {user: 0.0 for user in users}

    sorted_msgs = sorted(messages, key=lambda x: x.get('timestamp_ms', 0))
    FRAGMENTATION_WINDOW_MS = 15 * 1000  # 15 seconds

    user_fragmentation = {user: {"fragmented_sessions": 0, "total_sessions": 0} for user in users}

    for session in _split_sessions(sorted_msgs):
        # Denominator: one per user who sent >=1 message in this session.
        for u in {m.get('sender_name', 'Unknown') for m in session}:
            if u in user_fragmentation:
                user_fragmentation[u]["total_sessions"] += 1

        # Numerator: users who produced a same-sender burst (once per session).
        fragmented_users = set()
        for i in range(len(session) - 2):
            a, b, c = session[i], session[i + 1], session[i + 2]
            sender = a.get('sender_name', 'Unknown')
            if b.get('sender_name') != sender or c.get('sender_name') != sender:
                continue
            if (c['timestamp_ms'] - a['timestamp_ms']) <= FRAGMENTATION_WINDOW_MS:
                fragmented_users.add(sender)

        for u in fragmented_users:
            if u in user_fragmentation:
                user_fragmentation[u]["fragmented_sessions"] += 1

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
    # Unified return shape in ALL cases: {month: {user: {...}}} (BUG_REPORT C7).
    if not messages:
        return {}

    # Group messages by month and user
    monthly_bigrams = defaultdict(lambda: defaultdict(list))

    for msg in messages:
        user = msg.get('sender_name', 'Unknown')
        text = _get_text(msg)
        if not text:
            continue

        text = text.lower()
        date_str = _get_timestamp(msg).strftime('%Y-%m')  # YYYY-MM

        words = text.split()
        bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
        monthly_bigrams[date_str][user].extend(bigrams)

    result = defaultdict(dict)

    for month, users_data in monthly_bigrams.items():
        for user, bigrams in users_data.items():
            if not bigrams:
                result[month][user] = {"raw_entropy": 0.0, "normalized_entropy": 0.0,
                                       "type_token_ratio": 0.0}
                continue

            bigram_counts = Counter(bigrams)
            total = sum(bigram_counts.values())

            # Shannon Entropy: -Σ p(x)log₂p(x)
            entropy = 0.0
            for count in bigram_counts.values():
                p = count / total
                entropy -= p * math.log2(p)

            # Normalising by log2(unique) flattens to ~1.0 because chat bigrams
            # are almost all unique. Report the RAW entropy plus a
            # length-controlled baseline (type-token ratio), which actually
            # varies with repetition/"rut".
            max_entropy = math.log2(len(bigram_counts)) if len(bigram_counts) > 1 else 1
            normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
            ttr = len(bigram_counts) / total  # 1.0 = all unique, low = repetitive

            result[month][user] = {
                "raw_entropy": round(entropy, 4),
                "normalized_entropy": round(normalized_entropy, 4),
                "type_token_ratio": round(ttr, 4),
            }

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

    from src.word_frequency import GEORGIAN_STOPWORDS, ENGLISH_STOPWORDS
    stopwords = GEORGIAN_STOPWORDS | ENGLISH_STOPWORDS

    # Distinctiveness / recency thresholds (BUG_REPORT C11).
    MIN_DRIVER_USES_BEFORE = 2       # driver must have used it repeatedly first
    MIN_ADOPTER_USES = 3             # adopter must actually adopt it, not use once
    MIN_GAP_MS = 60 * 1000           # require a real time gap between first uses

    # Sort messages by timestamp
    sorted_msgs = sorted(messages, key=lambda x: x.get('timestamp_ms', 0))

    user_word_first_use = defaultdict(dict)             # user -> {word: first_ts}
    user_word_count = defaultdict(lambda: defaultdict(int))  # user -> {word: count}
    # Count of driver uses strictly before a given timestamp is derived on demand
    user_word_uses = defaultdict(lambda: defaultdict(list))  # user -> {word: [ts,...]}

    for msg in sorted_msgs:
        user = msg.get('sender_name', 'Unknown')
        text = _get_text(msg)
        if not text:
            continue

        text = text.lower()
        timestamp = msg['timestamp_ms']

        for word in text.split():
            # Clean word (remove punctuation, keep Georgian)
            word = re.sub(r'[^\w\u10A0-\u10FF]', '', word)
            if len(word) < 3:            # Ignore short words
                continue
            if word in stopwords:        # Stopwords are not "slang"
                continue

            if word not in user_word_first_use[user]:
                user_word_first_use[user][word] = timestamp
            user_word_count[user][word] += 1
            user_word_uses[user][word].append(timestamp)

    # Find vocabulary adoption
    contagion = defaultdict(lambda: defaultdict(int))

    for driver, words in user_word_first_use.items():
        for word, first_ts in words.items():
            for adopter, word_counts in user_word_count.items():
                if driver == adopter:
                    continue
                if word_counts.get(word, 0) < MIN_ADOPTER_USES:
                    continue
                if word not in user_word_first_use[adopter]:
                    continue

                adopter_ts = user_word_first_use[adopter][word]
                # Adopter must start using it meaningfully after the driver
                if adopter_ts - first_ts < MIN_GAP_MS:
                    continue
                # Driver must have used it repeatedly BEFORE the adopter's first use
                driver_uses_before = sum(1 for t in user_word_uses[driver][word] if t < adopter_ts)
                if driver_uses_before < MIN_DRIVER_USES_BEFORE:
                    continue

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

    # Word-boundary matchers so "party" doesn't fire on "პარტია" mid-word and
    # "დედა" doesn't match inside unrelated words (BUG_REPORT C4).
    topic_patterns = {
        topic: [re.compile(r'(?<!\w)' + re.escape(kw) + r'(?!\w)', re.UNICODE) for kw in kws]
        for topic, kws in topic_keywords.items()
    }

    # Response times use log-transform to tame the heavy overnight-gap tail, and
    # are capped at the session boundary so a topic isn't blamed for a sleep gap.
    topic_log_delays = defaultdict(list)
    all_log_delays = []

    sorted_msgs = sorted(messages, key=lambda x: x.get('timestamp_ms', 0))

    for i in range(1, len(sorted_msgs)):
        prev_msg = sorted_msgs[i - 1]
        curr_msg = sorted_msgs[i]

        if prev_msg.get('sender_name', '') == curr_msg.get('sender_name', ''):
            continue

        prev_text = _get_text(prev_msg).lower()
        if not prev_text:
            continue

        gap_ms = curr_msg['timestamp_ms'] - prev_msg['timestamp_ms']
        if gap_ms > SESSION_GAP_MS:      # cross-session (sleep) — not a response
            continue

        response_time = gap_ms / 1000 / 60  # minutes
        log_delay = math.log1p(max(response_time, 0.0))
        all_log_delays.append(log_delay)

        # Allow multi-topic tagging (no break).
        for topic, patterns in topic_patterns.items():
            if any(p.search(prev_text) for p in patterns):
                topic_log_delays[topic].append(log_delay)

    if len(all_log_delays) < 5:
        return {}

    baseline_mean = sum(all_log_delays) / len(all_log_delays)
    baseline_std = (sum((x - baseline_mean) ** 2 for x in all_log_delays) / len(all_log_delays)) ** 0.5
    if baseline_std <= 0:
        return {}

    # Flag a topic when its MEAN log-delay is significantly above baseline using
    # the standard error of the mean (σ/√n) with a 2σ threshold — reachable for
    # real data, unlike the old "3σ of individual response times".
    flagged_topics = {}
    for topic, log_delays in topic_log_delays.items():
        n = len(log_delays)
        if n < 3:
            continue
        topic_mean = sum(log_delays) / n
        sem = baseline_std / (n ** 0.5)
        z = (topic_mean - baseline_mean) / sem
        if z > 2:
            flagged_topics[topic] = {
                "z_score": round(z, 2),
                "topic_median_minutes": round(math.expm1(sorted(log_delays)[n // 2]), 2),
                "baseline_median_minutes": round(math.expm1(sorted(all_log_delays)[len(all_log_delays) // 2]), 2),
                "sample_size": n,
            }

    return flagged_topics


def conversational_gini_coefficient(messages: List[Dict], users: List[str]) -> Dict[str, float]:
    """
    Economic inequality of effort per calendar month.

    Returns ``{month: gini}`` (a Gini coefficient per YYYY-MM). For exactly two
    participants this reduces to ``|a-b| / (a+b)`` — the effort-share gap.
    Division is now guarded so a month with zero effort (only system/like
    messages) can no longer raise ZeroDivisionError (BUG_REPORT C9).
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
        total = float(sum(sorted_values))

        # Guard BEFORE dividing (fixes ZeroDivisionError on all-zero effort).
        if total <= 0:
            return 0.0

        gini = (2 * sum((i + 1) * v for i, v in enumerate(sorted_values)) - (n + 1) * total) / (n * total)
        return gini
    
    result = {}
    for period, efforts in user_effort_by_period.items():
        values = list(efforts.values())
        gini = calculate_gini(values)
        result[period] = round(gini, 4)
    
    return result


def _message_effort(msg: Dict) -> int:
    """Effort score for a message: character count + media bonuses."""
    text = _get_text(msg)
    effort = len(text) if text else 0
    if msg.get('photos'):
        effort += 100 * len(msg['photos'])
    if msg.get('videos'):
        effort += 200 * len(msg['videos'])
    if msg.get('audio_files'):
        effort += 200 * len(msg['audio_files'])
    return effort


def conversational_inertia(messages: List[Dict], users: List[str]) -> Dict[str, Dict]:
    """
    Force required to restart a dead chat (>72h gap), per initiating user.

    Rewritten (BUG_REPORT C10): the dead first implementation (with its O(n²)
    ``list.index`` call and unreachable guard) is gone. A restart is the effort
    an initiator spends after a >72h silence, up until the OTHER person replies:
      - answered restart: the partner replied → effort logged as ``answered``;
      - failed restart: another >72h silence (or end of chat) arrives with no
        reply → effort logged as ``failed`` (messages into the void).
    Returns per-user ``{avg_restart_effort, failed_restarts, answered_restarts}``.
    """
    per_user = {u: {"answered": [], "failed": []} for u in users}
    if not messages:
        return {u: {"avg_restart_effort": 0.0, "failed_restarts": 0, "answered_restarts": 0}
                for u in users}

    sorted_msgs = sorted(messages, key=lambda x: x.get('timestamp_ms', 0))
    DEAD_CHAT_GAP_MS = 72 * 60 * 60 * 1000  # 72 hours

    in_recovery = False
    initiator = None
    effort = 0

    def _record(kind):
        if initiator in per_user:
            per_user[initiator][kind].append(effort)

    last_ts = None
    for msg in sorted_msgs:
        eff = _message_effort(msg)
        sender = msg.get('sender_name', 'Unknown')

        if last_ts is not None:
            gap_ms = msg['timestamp_ms'] - last_ts

            if gap_ms > DEAD_CHAT_GAP_MS:
                # A new dead-gap. If we were still waiting on a previous
                # restart, that restart failed (never answered).
                if in_recovery:
                    _record("failed")
                # Start a fresh restart attempt.
                in_recovery = True
                initiator = sender
                effort = eff
            elif in_recovery:
                if sender != initiator:
                    # Partner replied → the restart was answered.
                    _record("answered")
                    in_recovery = False
                    initiator = None
                    effort = 0
                else:
                    # Initiator keeps pushing into the void.
                    effort += eff

        last_ts = msg['timestamp_ms']

    # A restart pending at the end of the chat never got answered.
    if in_recovery:
        _record("failed")

    result = {}
    for user, data in per_user.items():
        efforts = data["answered"] + data["failed"]
        result[user] = {
            "avg_restart_effort": round(sum(efforts) / len(efforts), 2) if efforts else 0.0,
            "failed_restarts": len(data["failed"]),
            "answered_restarts": len(data["answered"]),
        }
    return result


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
    
    all_stopwords = stop_words['english'] | stop_words['georgian']

    user_stats = {user: {"signal": 0, "noise": 0, "affect": 0} for user in users}

    for msg in messages:
        user = msg.get('sender_name', 'Unknown')
        if user not in user_stats:
            continue

        text = _get_text(msg)
        if not text:
            continue

        # Emoji is its own AFFECT channel \u2014 not noise (BUG_REPORT C8).
        user_stats[user]["affect"] += len(EMOJI_PATTERN.findall(text))

        # Normalise each token once (lower + strip punctuation) and classify it
        # exactly once: stopword -> noise, >=4 chars -> signal, else neutral.
        for raw in text.split():
            token = re.sub(r'[^\w\u10A0-\u10FF]', '', raw).lower()
            if not token:
                continue
            if token in all_stopwords:
                user_stats[user]["noise"] += 1
            elif len(token) >= 4:
                user_stats[user]["signal"] += 1
            # else: neutral, counted in neither channel

        # Media counts as signal
        if msg.get('photos') or msg.get('videos') or msg.get('audio_files'):
            user_stats[user]["signal"] += 1

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

    WINDOW_DAYS = 7
    MIN_WINDOW_VOLUME = 5  # require enough messages in the window to be meaningful

    # Group messages by day
    daily = defaultdict(lambda: {user: 0 for user in users})
    dates = []
    for msg in messages:
        dt = _get_timestamp(msg)
        dates.append(dt.date())
        date_str = dt.strftime('%Y-%m-%d')
        user = msg.get('sender_name', 'Unknown')
        if user in daily[date_str]:
            daily[date_str][user] += 1

    # Continuous zero-filled calendar: a day where the retreater sent 0 IS the
    # signal, so silent days must be present (BUG_REPORT C6).
    calendar = _daily_calendar(dates)
    a_series = [daily[d].get(users[0], 0) if d in daily else 0 for d in calendar]
    b_series = [daily[d].get(users[1], 0) if d in daily else 0 for d in calendar]

    if len(calendar) < WINDOW_DAYS:
        return {}

    def _pearson(xs, ys):
        n = len(xs)
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((xs[k] - mx) * (ys[k] - my) for k in range(n))
        dx = sum((xs[k] - mx) ** 2 for k in range(n)) ** 0.5
        dy = sum((ys[k] - my) ** 2 for k in range(n)) ** 0.5
        if dx == 0 or dy == 0:
            return None
        return num / (dx * dy)

    # Rolling correlation series (useful for the dashboard) + threshold crossings.
    series = []
    crossings = {}
    for i in range(WINDOW_DAYS, len(calendar) + 1):
        wa = a_series[i - WINDOW_DAYS:i]
        wb = b_series[i - WINDOW_DAYS:i]
        if sum(wa) + sum(wb) < MIN_WINDOW_VOLUME:
            continue
        corr = _pearson(wa, wb)
        if corr is None:
            continue
        date = calendar[i - 1]
        series.append({"date": date, "correlation": round(corr, 4)})
        if corr < -0.6:
            crossings[date] = {
                "correlation": round(corr, 4),
                "status": "CHASER_RETREATER_DETECTED",
            }

    if not series:
        return {}

    return {"series": series, "crossings": crossings}


def tit_for_tat_retaliation_score(messages: List[Dict], users: List[str]) -> Dict[str, float]:
    """
    Intentional mirroring of delayed responses (Game Theory - Pettiness)
    
    Instagram adaptation: Uses timestamp_ms for delay calculation
    """
    result = {user: 0.0 for user in users}
    if not messages:
        return result

    sorted_msgs = sorted(messages, key=lambda x: x.get('timestamp_ms', 0))

    # Per user: pairs (other's previous delay, this user's delay), log-scaled.
    # A high positive Pearson r means the user mirrors the partner's delays —
    # true tit-for-tat — as opposed to the old self-autocorrelation which
    # measured a user's own consistency (BUG_REPORT C5).
    user_pairs = defaultdict(lambda: ([], []))

    for session in _split_sessions(sorted_msgs):
        # Build the alternating sequence of responses within the session.
        responses = []  # (responder, log_delay)
        for i in range(1, len(session)):
            prev_u = session[i - 1].get('sender_name', '')
            curr_u = session[i].get('sender_name', '')
            if prev_u == curr_u:
                continue
            delay = (session[i]['timestamp_ms'] - session[i - 1]['timestamp_ms']) / 1000 / 60
            responses.append((curr_u, math.log1p(max(delay, 0.0))))

        # Pair each response with the immediately preceding (partner) response.
        for k in range(1, len(responses)):
            prev_responder, prev_delay = responses[k - 1]
            responder, delay = responses[k]
            if responder == prev_responder:
                continue
            if responder in user_pairs:
                xs, ys = user_pairs[responder]
                xs.append(prev_delay)  # partner's delay
                ys.append(delay)       # my delay

    for user in users:
        xs, ys = user_pairs[user]
        n = len(xs)
        if n < 3:
            continue
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
        dx = sum((xs[i] - mx) ** 2 for i in range(n)) ** 0.5
        dy = sum((ys[i] - my) ** 2 for i in range(n)) ** 0.5
        if dx > 0 and dy > 0:
            result[user] = round(num / (dx * dy), 4)  # signed Pearson r

    return result


def temporal_syncopation_variance(messages: List[Dict], users: List[str]) -> Dict[str, float]:
    """
    Unpredictability of conversational rhythm (Music Theory)
    
    Instagram adaptation: Uses timestamp_ms for tempo calculation
    """
    if not messages:
        return {user: 0.0 for user in users}

    sorted_msgs = sorted(messages, key=lambda x: x.get('timestamp_ms', 0))
    user_deviation_variances = defaultdict(list)

    # Iterate ALL sessions, including the final one (the old code only processed
    # a session when a gap flushed it, so the last session — or an entire
    # gap-free chat — was silently skipped). See BUG_REPORT C1/C8.
    for current_session in _split_sessions(sorted_msgs):
        if len(current_session) < 3:
            continue

        tempos = []
        for i in range(1, len(current_session)):
            t1 = current_session[i - 1]['timestamp_ms']
            t2 = current_session[i]['timestamp_ms']
            tempos.append((t2 - t1) / 1000)  # seconds

        if not tempos:
            continue
        baseline = sum(tempos) / len(tempos)

        user_tempos = defaultdict(list)
        for i in range(1, len(current_session)):
            user = current_session[i].get('sender_name', 'Unknown')
            t1 = current_session[i - 1]['timestamp_ms']
            t2 = current_session[i]['timestamp_ms']
            deviation = (t2 - t1) / 1000 - baseline
            user_tempos[user].append(deviation)

        for user, deviations in user_tempos.items():
            if len(deviations) > 1:
                variance = sum(d ** 2 for d in deviations) / len(deviations)
                user_deviation_variances[user].append(variance)

    result = {}
    for user in users:
        variances = user_deviation_variances.get(user, [])
        result[user] = round(sum(variances) / len(variances), 4) if variances else 0.0
    # Include any senders not in `users` too (backward compatible)
    for user, variances in user_deviation_variances.items():
        if user not in result:
            result[user] = round(sum(variances) / len(variances), 4) if variances else 0.0

    return result
