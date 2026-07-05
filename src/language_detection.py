"""Language distribution aggregation.

Single source of truth for language: the per-message ``language`` field written
by ``src.normalizer.detect_language`` (proper Georgian Unicode). The old
heuristic detector (which keyed off the undecoded 'á' character) has been
removed — it disagreed with the normalizer and operated on already-decoded text
where 'á' no longer exists. See BUG_REPORT A3.
"""

from collections import defaultdict
from typing import Dict, List

from src.normalizer import detect_language, decode_georgian_text, is_system_message


def get_language_distribution(messages: List[Dict]) -> Dict[str, float]:
    """Get language distribution across all messages.

    Prefers the per-message ``language`` field written by the normalizer. For
    raw (un-normalized) messages it falls back to decoding + the normalizer's
    detector, so there is exactly one detection code path.

    Args:
        messages: List of message dictionaries

    Returns:
        Dictionary with language percentages (english / georgian / mixed)
    """
    lang_counts = defaultdict(int)

    for msg in messages:
        lang = msg.get('language')

        if lang is None:
            content = msg.get('content', '')
            if not content or is_system_message(msg):
                continue
            lang = detect_language(decode_georgian_text(content))

        # Skip non-linguistic buckets
        if lang in ('system', 'media', 'unknown', 'empty', None):
            continue

        lang_counts[lang] += 1

    total = sum(lang_counts.values())
    if total == 0:
        return {}

    return {
        lang: round(count / total * 100, 2)
        for lang, count in lang_counts.items()
    }
