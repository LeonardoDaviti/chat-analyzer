"""
Normalizer for Instagram Chat Data

Processes combined chat data and produces a normalized version:
  - Decodes Georgian text (latin-1 → UTF-8) using the same logic as decode_messages.py
  - Adds formatted_timestamp (HH:MM DD-MM-YYYY) alongside original timestamp_ms
  - Detects language per message using proper Georgian Unicode (U+10A0–U+10FF)
  - Replaces content with decoded text for all downstream analysis

This is required for V3.0 metrics that depend on actual word matching
(defensiveness, SNR, topic avoidance, vocabulary contagion, etc.).

Usage:
    from src.normalizer import normalize_chat
    
    combined = load_chat_from_dir(chat_dir)  # or combine_messages()
    normalized = normalize_chat(combined)
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple

from src.timeutil import to_datetime, DEFAULT_TIMEZONE


# Georgian Unicode range: U+10A0 to U+10FF
GEORGIAN_PATTERN = re.compile(r'[\u10A0-\u10FF]+')


def _count_georgian_chars(text: str) -> int:
    """Count individual Georgian characters (not contiguous runs).

    ``GEORGIAN_PATTERN.findall`` returns runs because of the ``+`` quantifier,
    which undercounts long Georgian words. Count characters directly instead
    (BUG_REPORT A2).
    """
    return sum(1 for ch in text if '\u10A0' <= ch <= '\u10FF')


def decode_georgian_text(text: str) -> str:
    """Decode Georgian text from latin-1 encoded UTF-8 bytes.
    
    Instagram exports store Georgian UTF-8 bytes as latin-1 encoded strings
    (e.g., the character ბ is stored as 'á\x83\x9b' in the JSON).
    
    This reverses that encoding: re-encode as latin-1 to get the original
    UTF-8 bytes, then decode those bytes as UTF-8.
    
    Ported from decode_messages.py which works perfectly for LLMs.
    
    Args:
        text: The raw text from the JSON (may be encoded Georgian)
        
    Returns:
        Decoded text with proper Georgian characters, or original if not Georgian
    """
    if not text:
        return text

    try:
        # Encode as latin-1 (reverses the wrong encoding), then decode as UTF-8.
        # Any successful decode is accepted — this repairs not just Georgian but
        # also Cyrillic titles and EMOJI (which the old Georgian-only check left
        # mangled, silently blinding all emoji/affect metrics). Pure-ASCII text
        # round-trips unchanged; legitimate latin-1 text (e.g. "café") fails the
        # UTF-8 decode and is returned as-is.
        return text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    # Return original if decoding fails
    return text


def detect_language(text: str) -> str:
    """Detect language using proper Georgian Unicode range (U+10A0–U+10FF).
    
    Args:
        text: The decoded text to analyze
        
    Returns:
        'georgian', 'english', or 'mixed'
    """
    if not text or not text.strip():
        return "english"
    
    text = text.strip()
    total_chars = len(text)

    if total_chars == 0:
        return "english"

    # Count Georgian Unicode characters (individual chars, not runs)
    georgian_chars = _count_georgian_chars(text)
    georgian_ratio = georgian_chars / total_chars
    
    # Check for Latin/English characters
    latin_pattern = re.compile(r'[a-zA-Z]')
    latin_chars = len(latin_pattern.findall(text))
    latin_ratio = latin_chars / total_chars
    
    if georgian_ratio >= 0.3:
        if latin_ratio > 0.2:
            return "mixed"
        return "georgian"
    elif latin_ratio >= 0.3:
        return "english"
    else:
        if georgian_chars > 0:
            return "mixed"
        return "english"


def format_timestamp(timestamp_ms: int, timezone: str = DEFAULT_TIMEZONE) -> str:
    """Convert Unix timestamp (milliseconds) to formatted datetime string.

    Format: HH:MM DD-MM-YYYY

    Args:
        timestamp_ms: Unix timestamp in milliseconds
        timezone: IANA timezone used to render the wall-clock time

    Returns:
        Formatted string like "15:07 26-04-2026"
    """
    return to_datetime(timestamp_ms, timezone).strftime('%H:%M %d-%m-%Y')


# Anchored regexes for Instagram system/notification messages. Anchoring avoids
# the "mid-sentence substring" false positives of the old list (e.g. dropping
# "I added you on Steam" or "she reacted badly"). See BUG_REPORT A1.
_SYSTEM_PATTERNS = [
    re.compile(r'^liked a message$'),
    re.compile(r'^reacted .{1,6} to your message$'),
    re.compile(r'^.+ sent an attachment\.$'),
    re.compile(r'^sent an attachment\.$'),
    re.compile(r'^.* changed the chat icon\.?$'),
    re.compile(r'^.* named the group .*$'),
    re.compile(r'^.* started a group conversation.*$'),
    re.compile(r'^.+ added .+ to the group\.?$'),
    re.compile(r'^.+ removed .+ from the group\.?$'),
]


def is_system_message(msg: Any) -> bool:
    """Check if a message is an Instagram system/notification message.

    Accepts either a message dict (preferred — structural fields are checked
    first) or a raw content string (backward compatible).

    Args:
        msg: Message dictionary or content string

    Returns:
        True if this is a system message that should be skipped
    """
    if isinstance(msg, dict):
        # Structural signal first: an unsent/removed message is not real content.
        if msg.get('is_unsent'):
            return True
        content = msg.get('content', '') or ''
    else:
        content = msg or ''

    content_norm = content.lower().strip()
    if not content_norm:
        # Empty content is not classified as a system message here; media/empty
        # handling happens in normalize_message.
        return False

    return any(pat.match(content_norm) for pat in _SYSTEM_PATTERNS)


def is_real_message(msg: Dict[str, Any]) -> bool:
    """Single shared predicate: is this a real conversational text message?

    Unifies the two divergent predicates that previously existed
    (``normalizer.is_system_message`` and ``session_chunker.is_real_message``).
    A real message has text content and is neither a system notification nor a
    media-only event. See BUG_REPORT C15.
    """
    lang = msg.get('language')
    if lang in ('system', 'media'):
        return False

    content = msg.get('content', '') or ''
    if not content.strip():
        return False

    return not is_system_message(msg)


def derive_message_type(msg: Dict[str, Any]) -> str:
    """Derive a coarse message ``type`` from Instagram structural fields.

    The normalizer never wrote a ``type`` field, so the markdown exporter
    silently dropped all media exchanges (BUG_REPORT C16). This makes media
    visible to downstream consumers.
    """
    if msg.get('call_duration') is not None:
        return 'call'
    if msg.get('photos'):
        return 'photo'
    if msg.get('videos'):
        return 'video'
    if msg.get('audio_files'):
        return 'voice'
    if msg.get('share'):
        return 'share'
    if msg.get('sticker'):
        return 'sticker'
    return 'text'


def normalize_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a single message.
    
    Args:
        msg: Original message dictionary
        
    Returns:
        Normalized message with decoded content and additional fields,
        or the original message unchanged if it's a system message.
    """
    normalized = dict(msg)  # Copy all original fields
    
    # Preserve original timestamp_ms for calculations
    if 'timestamp_ms' not in normalized:
        if 'timestamp' in normalized:
            normalized['timestamp_ms'] = normalized['timestamp']
        elif 'date' in normalized:
            try:
                dt = datetime.fromisoformat(normalized['date'].replace('Z', '+00:00'))
                normalized['timestamp_ms'] = int(dt.timestamp() * 1000)
            except (ValueError, TypeError):
                normalized['timestamp_ms'] = 0
    
    # Add formatted timestamp (HH:MM DD-MM-YYYY)
    normalized['formatted_timestamp'] = format_timestamp(normalized.get('timestamp_ms', 0))

    # Decode mojibake sender names (Georgian/Cyrillic names otherwise become
    # 'á...' keys throughout the analysis)
    if normalized.get('sender_name'):
        normalized['sender_name'] = decode_georgian_text(normalized['sender_name'])

    # Derive a coarse message type from structural fields (photo/video/call/...)
    normalized['type'] = derive_message_type(normalized)

    # Decode content and detect language (skip system messages)
    if 'content' in normalized and normalized['content']:
        # Skip Instagram system/notification messages (structural + anchored regex)
        if is_system_message(normalized):
            normalized['language'] = 'system'
            return normalized

        original_content = normalized['content']
        decoded_content = decode_georgian_text(original_content)

        # Replace content with decoded version for downstream analysis
        normalized['content'] = decoded_content
        normalized['language'] = detect_language(decoded_content)

        # Keep original for reference
        if decoded_content != original_content:
            normalized['original_content'] = original_content
    else:
        # Non-text messages (photos, videos, etc.)
        normalized['language'] = 'media'

    return normalized


def normalize_chat(chat_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize all messages in a chat.
    
    Args:
        chat_data: Combined chat data dictionary
        
    Returns:
        Normalized chat data with all messages processed
    """
    messages = chat_data.get('messages', [])
    normalized_messages = [normalize_message(msg) for msg in messages]

    normalized = dict(chat_data)
    normalized['messages'] = normalized_messages

    # Decode mojibake in chat title and participant names so output folders,
    # analysis keys, and chart labels show real Georgian/Cyrillic/emoji text
    if normalized.get('title'):
        normalized['title'] = decode_georgian_text(normalized['title'])
    if normalized.get('participants'):
        normalized['participants'] = [
            {**p, 'name': decode_georgian_text(p.get('name', ''))}
            for p in normalized['participants']
        ]
    
    # Add normalization metadata
    langs = {}
    for m in normalized_messages:
        lang = m.get('language', 'unknown')
        langs[lang] = langs.get(lang, 0) + 1
    
    normalized['normalization_info'] = {
        'total_messages': len(normalized_messages),
        'language_distribution': langs,
        'date_range': {
            'first': format_timestamp(normalized_messages[0]['timestamp_ms']) if normalized_messages else 'N/A',
            'last': format_timestamp(normalized_messages[-1]['timestamp_ms']) if normalized_messages else 'N/A'
        }
    }
    
    return normalized


def normalize_and_save(chat_data: Dict[str, Any], chat_dir: str) -> Path:
    """Normalize chat data and save to normalized.json.
    
    Args:
        chat_data: Combined chat data
        chat_dir: Path to the chat directory
        
    Returns:
        Path to the saved normalized.json file
    """
    normalized = normalize_chat(chat_data)
    
    output_path = Path(chat_dir) / "normalized.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    
    return output_path


def normalize_chat_from_data(chat_data: Dict[str, Any], chat_dir: str = None) -> Dict[str, Any]:
    """Normalize chat data and optionally save to file.
    
    Args:
        chat_data: Combined chat data
        chat_dir: If provided, save to normalized.json in this directory
        
    Returns:
        Normalized chat data dictionary
    """
    normalized = normalize_chat(chat_data)
    
    if chat_dir:
        output_path = Path(chat_dir) / "normalized.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
    
    return normalized


def load_normalized(chat_dir: str) -> Dict[str, Any]:
    """Load pre-normalized data if it exists.
    
    Args:
        chat_dir: Path to the chat directory
        
    Returns:
        Normalized chat data dictionary
    """
    normalized_file = Path(chat_dir) / "normalized.json"
    if normalized_file.exists():
        with open(normalized_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None
