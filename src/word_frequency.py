"""Word frequency analysis for Georgian and English text."""

import re
from collections import Counter
from typing import List, Dict


# Georgian stopwords (common words to exclude)
GEORGIAN_STOPWORDS = {
    'და', 'ის', 'ა', 'ეს', 'რომ', 'რომელი', 'ვინ', 'რას', 'რამდენი',
    'ყველა', 'თითო', 'ერთი', 'მე', 'შენ', 'ჩვენ', 'თქვენ', 'მას',
    'მიმ', 'გა', 'მა', 'მო', 'გ', 'ს', 'ით', 'ზე', 'ში',
    'გან', 'მიერ', 'თვის', 'მდე', 'ვერ', 'არ', 'არა',
    'თუ', 'მხოლოდ', 'მარტო', 'ცოტა', 'ძალიან', 'უფრო',
    'რამდენად', 'რატომ', 'როგორ', 'რა', 'კად', 'კი', 'მეც'
}

ENGLISH_STOPWORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need',
    'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her',
    'us', 'them', 'my', 'your', 'his', 'its', 'our', 'their', 'mine',
    'yours', 'hers', 'ours', 'theirs', 'this', 'that', 'these', 'those',
    'what', 'which', 'who', 'whom', 'whose', 'where', 'when', 'why', 'how',
    'and', 'but', 'or', 'nor', 'for', 'yet', 'so', 'if', 'then', 'than',
    'to', 'of', 'in', 'on', 'at', 'by', 'from', 'with', 'about', 'against',
    'between', 'into', 'through', 'during', 'before', 'after', 'above',
    'below', 'up', 'down', 'out', 'off', 'over', 'under', 'again', 'further',
    'am', 'ok', 'hello', 'hi', 'bye', 'yes', 'no'
}


def extract_words(text: str) -> List[str]:
    """Extract words from text, handling both Georgian and English.
    
    Args:
        text: The text to extract words from
        
    Returns:
        List of lowercase words (filtered)
    """
    # Remove URLs and special characters
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    
    # Split by whitespace and punctuation (keep Georgian characters)
    words = re.findall(r'\w+', text.lower())
    
    # Filter stopwords and very short words
    stopwords = GEORGIAN_STOPWORDS | ENGLISH_STOPWORDS
    return [w for w in words if w not in stopwords and len(w) > 1]


def get_word_frequency(messages: List[Dict], sender_name: str = None) -> Dict[str, int]:
    """Get word frequency for messages, optionally filtered by sender.
    
    Args:
        messages: List of message dictionaries
        sender_name: Optional filter for specific sender
        
    Returns:
        Dictionary of word frequencies (top 50)
    """
    words = []
    
    for msg in messages:
        if sender_name and msg.get('sender_name') != sender_name:
            continue
        
        content = msg.get('content', '')
        if content and content != 'Liked a message':
            words.extend(extract_words(content))
    
    return dict(Counter(words).most_common(50))
