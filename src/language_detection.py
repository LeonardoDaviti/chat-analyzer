"""Language detection for Georgian/English/Mixed text."""

import re
from collections import defaultdict
from typing import Dict, List


# Georgian Unicode range: U+10A0 to U+10FF
GEORGIAN_PATTERN = re.compile(r'[\u10A0-\u10FF]+')


def detect_language(text: str) -> str:
    """Detect if text is Georgian, English, or Mixed.
    
    Instagram exports encode Georgian text in a special way where the character
    'á' (U+00E1) appears repeatedly. We use this as an indicator.
    
    Args:
        text: The text to analyze
        
    Returns:
        'georgian', 'english', 'mixed', 'empty', or 'unknown'
    """
    if not text:
        return "unknown"
    
    text = text.strip()
    if not text:
        return "empty"
    
    total_chars = len(text)
    
    # Check for proper Georgian Unicode characters first
    georgian_chars = len(GEORGIAN_PATTERN.findall(text))
    
    # Check for the 'á' character which is a strong indicator of Georgian text
    # in this Instagram export format
    a_with_accent_count = text.count('á')
    
    # Calculate ratios
    georgian_unicode_ratio = georgian_chars / total_chars if total_chars > 0 else 0
    a_accent_ratio = a_with_accent_count / total_chars if total_chars > 0 else 0
    
    # If we have many 'á' characters, it's likely Georgian
    if a_accent_ratio > 0.1:  # More than 10% of chars are 'á'
        return "georgian"
    elif georgian_unicode_ratio > 0.7:
        return "georgian"
    elif georgian_unicode_ratio < 0.3 and a_accent_ratio < 0.05:
        return "english"
    else:
        return "mixed"


def get_language_distribution(messages: List[Dict]) -> Dict[str, float]:
    """Get language distribution across all messages.
    
    Args:
        messages: List of message dictionaries
        
    Returns:
        Dictionary with language percentages
    """
    lang_counts = defaultdict(int)
    
    for msg in messages:
        content = msg.get('content', '')
        # Skip non-text messages
        if content in ['Liked a message', '']:
            continue
        
        lang = detect_language(content)
        lang_counts[lang] += 1
    
    total = sum(lang_counts.values())
    if total == 0:
        return {}
    
    return {
        lang: round(count / total * 100, 2) 
        for lang, count in lang_counts.items()
    }
