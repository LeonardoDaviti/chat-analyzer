"""Group-chat (3+ participants) analysis block.

A 1v1 relationship instrument (the V3/V4 pair metrics) is meaningless for a
group, so instead of squeezing a group into a fake top-2 pair we compute a
dedicated ``group_metrics`` block: per-member activity, a who-reacts-to-whom
matrix, a who-responds-to-whom matrix, and the lurker set.

All shared pipeline infrastructure is reused rather than re-derived:
  - ``src.metrics_v4._session_msg_lists`` for the ONE shared session definition
    (prefers chunker sessions, else ``_split_sessions``).
  - ``src.metrics_v4._is_question`` / ``NIGHT_HOURS`` for the question / night
    channels.
  - ``src.analyzer_v3.EMOJI_PATTERN`` for the emoji channel.
  - ``src.normalizer.is_real_message`` / ``decode_georgian_text`` (mojibake
    reaction actors).
  - ``src.timeutil.to_datetime`` for timezone-aware bucketing.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from src.timeutil import to_datetime, DEFAULT_TIMEZONE
from src.normalizer import is_real_message, decode_georgian_text
from src.analyzer_v3 import EMOJI_PATTERN
from src.metrics_v4 import _session_msg_lists, _is_question, NIGHT_HOURS


def order_members_by_volume(messages: List[Dict[str, Any]],
                            participants: List[str]) -> List[str]:
    """Return every participant, most-active first, inactive members appended.

    Ordering is by real-message volume (the lifetime rank the dashboard relies
    on for a stable per-member colour assignment).
    """
    counts: Counter = Counter()
    for m in messages:
        if is_real_message(m):
            counts[m.get('sender_name', 'Unknown')] += 1
    ranked = [u for u, _ in counts.most_common() if u in set(participants)]
    for u in participants:
        if u not in ranked:
            ranked.append(u)
    return ranked


def compute_group_metrics(messages: List[Dict[str, Any]],
                          participants: List[str],
                          sessions: Optional[List[Dict[str, Any]]] = None,
                          timezone: str = DEFAULT_TIMEZONE) -> Dict[str, Any]:
    """Compute the group analysis block for a 3+ participant chat.

    Args:
        messages: normalized messages.
        participants: ALL member display names (order irrelevant here).
        sessions: optional chunker sessions (valid-only consumed).
        timezone: IANA timezone for the night-hours channel.

    Returns a dict with ``member_stats``, ``reaction_matrix``, ``reply_matrix``,
    ``lurkers``, ``is_group`` and ``member_count``.
    """
    member_set = set(participants)

    # --- per-member real-message channels --------------------------------- #
    msgs = {u: 0 for u in participants}
    words = {u: 0 for u in participants}
    emoji = {u: 0 for u in participants}
    night = {u: 0 for u in participants}
    questions = {u: 0 for u in participants}

    for m in messages:
        sender = m.get('sender_name', 'Unknown')
        if sender not in member_set or not is_real_message(m):
            continue
        content = m.get('content', '') or ''
        msgs[sender] += 1
        words[sender] += len(content.split())
        emoji[sender] += len(EMOJI_PATTERN.findall(content))
        if _is_question(m):
            questions[sender] += 1
        if to_datetime(m.get('timestamp_ms', 0), timezone).hour in NIGHT_HOURS:
            night[sender] += 1

    # --- reactions given / received + reaction matrix --------------------- #
    reactions_given = {u: 0 for u in participants}
    reactions_received = {u: 0 for u in participants}
    reaction_matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for m in messages:
        receiver = m.get('sender_name', 'Unknown')
        for r in (m.get('reactions') or []):
            actor = decode_georgian_text(r.get('actor', '') or '')
            if actor in member_set:
                reactions_given[actor] += 1
                if receiver in member_set:
                    reaction_matrix[actor][receiver] += 1
            if receiver in member_set:
                reactions_received[receiver] += 1

    # --- session-derived channels: initiations, endings, reply matrix ----- #
    initiations = {u: 0 for u in participants}
    endings = {u: 0 for u in participants}
    reply_matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for session in _session_msg_lists(messages, sessions):
        if not session:
            continue
        opener = session[0].get('sender_name', 'Unknown')
        if opener in member_set:
            initiations[opener] += 1
        closer = session[-1].get('sender_name', 'Unknown')
        if closer in member_set:
            endings[closer] += 1
        prev_sender = None
        for m in session:
            sender = m.get('sender_name', 'Unknown')
            if prev_sender is not None and sender != prev_sender:
                if sender in member_set and prev_sender in member_set:
                    reply_matrix[sender][prev_sender] += 1
            prev_sender = sender

    total_msgs = sum(msgs.values())

    member_stats: Dict[str, Dict[str, Any]] = {}
    for u in participants:
        mc = msgs[u]
        member_stats[u] = {
            'msgs': mc,
            'words': words[u],
            'share': round(mc / total_msgs, 4) if total_msgs else 0.0,
            'initiations': initiations[u],
            'endings': endings[u],
            'reactions_given': reactions_given[u],
            'reactions_received': reactions_received[u],
            'emoji_per_100': round(emoji[u] / mc * 100, 2) if mc else 0.0,
            'night_share': round(night[u] / mc, 4) if mc else 0.0,
            'questions_per_100': round(questions[u] / mc * 100, 2) if mc else 0.0,
        }

    lurkers = [u for u in participants if msgs[u] == 0]

    return {
        'is_group': True,
        'member_count': len(participants),
        'member_stats': member_stats,
        'reaction_matrix': {g: dict(rr) for g, rr in reaction_matrix.items()},
        'reply_matrix': {r: dict(pp) for r, pp in reply_matrix.items()},
        'lurkers': lurkers,
    }
