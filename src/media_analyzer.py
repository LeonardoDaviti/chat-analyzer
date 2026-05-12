"""Media statistics for photos, videos, audio files, and shares."""

from collections import defaultdict
from typing import Dict, List, Any


def get_media_stats(messages: List[Dict]) -> Dict[str, Any]:
    """Calculate media statistics per sender.
    
    Args:
        messages: List of message dictionaries
        
    Returns:
        Dictionary with media statistics
    """
    media_by_sender = defaultdict(lambda: {
        'photos': 0,
        'videos': 0,
        'audio_files': 0,
        'shares': 0,
        'calls': 0
    })
    
    for msg in messages:
        sender = msg.get('sender_name', 'Unknown')
        
        # Count photos
        photos = msg.get('photos')
        if photos:
            media_by_sender[sender]['photos'] += len(photos)
        
        # Count videos
        videos = msg.get('videos')
        if videos:
            media_by_sender[sender]['videos'] += len(videos)
        
        # Count audio files
        audio = msg.get('audio_files')
        if audio:
            media_by_sender[sender]['audio_files'] += len(audio)
        
        # Count shares
        if msg.get('share'):
            media_by_sender[sender]['shares'] += 1
        
        # Count calls
        if msg.get('call_duration'):
            media_by_sender[sender]['calls'] += 1
    
    # Calculate totals
    totals = {
        'photos': sum(s['photos'] for s in media_by_sender.values()),
        'videos': sum(s['videos'] for s in media_by_sender.values()),
        'audio_files': sum(s['audio_files'] for s in media_by_sender.values()),
        'shares': sum(s['shares'] for s in media_by_sender.values()),
        'calls': sum(s['calls'] for s in media_by_sender.values())
    }
    
    return {
        'by_sender': dict(media_by_sender),
        'totals': totals,
        'who_sends_most_media': _find_top_media_sender(media_by_sender)
    }


def _find_top_media_sender(media_by_sender: Dict) -> str:
    """Find who sends the most media overall."""
    totals = {
        sender: sum(media.values()) 
        for sender, media in media_by_sender.items()
    }
    return max(totals.items(), key=lambda x: x[1])[0] if totals else "none"
