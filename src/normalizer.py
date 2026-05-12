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


# Georgian Unicode range: U+10A0 to U+10FF
GEORGIAN_PATTERN = re.compile(r'[\u10A0-\u10FF]+')


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
        # Encode as latin-1 (reverses the wrong encoding), then decode as UTF-8
        decoded = text.encode('latin-1').decode('utf-8')
        
        # Verify the result contains valid Georgian characters
        if GEORGIAN_PATTERN.search(decoded):
            return decoded
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    
    # Return original if decoding fails or doesn't produce Georgian text
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
    
    # Count Georgian Unicode characters
    georgian_chars = len(GEORGIAN_PATTERN.findall(text))
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


def format_timestamp(timestamp_ms: int) -> str:
    """Convert Unix timestamp (milliseconds) to formatted datetime string.
    
    Format: HH:MM DD-MM-YYYY
    
    Args:
        timestamp_ms: Unix timestamp in milliseconds
        
    Returns:
        Formatted string like "15:07 26-04-2026"
    """
    dt = datetime.fromtimestamp(timestamp_ms / 1000)
    return dt.strftime('%H:%M %d-%m-%Y')


def is_system_message(content: str) -> bool:
    """Check if a message is an Instagram system/notification message.
    
    These should be skipped during normalization and analysis.
    
    Args:
        content: The message content string
        
    Returns:
        True if this is a system message that should be skipped
    """
    if not content:
        return True
    
    skip_patterns = [
        'Liked a message',           # Instagram like reaction
        'reacted',                   # Reaction to message
        'sent an attachment.',       # Media share notification
        'changed the chat icon',     # Chat setting change
        'started a group conversation',
        'added',                     # Member added notification
    ]
    
    content_lower = content.lower().strip()
    return any(pattern in content_lower for pattern in skip_patterns)


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
    
    # Decode content and detect language (skip system messages)
    if 'content' in normalized and normalized['content']:
        content = normalized['content']
        
        # Skip Instagram system/notification messages
        if is_system_message(content):
            normalized['language'] = 'system'
            return normalized
        
        original_content = content
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
