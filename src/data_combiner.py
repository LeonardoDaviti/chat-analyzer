"""
Data Combiner for Instagram Chat Analysis

Auto-discovers and merges multiple message JSON files per chat directory.
Supports:
  - message_1.json, message_2.json, ... (split files)
  - combined_message.json (already combined)

Output: {chat_name}_combined.json with all messages merged and sorted.
"""

import json
from pathlib import Path
from typing import Dict, Any, List


def discover_message_files(chat_dir: str) -> List[Path]:
    """Discover message JSON files in a chat directory.
    
    Priority:
      1. combined_message.json (if it exists, use it as-is)
      2. message_1.json, message_2.json, ... (merge them)
    
    Args:
        chat_dir: Path to the chat directory
        
    Returns:
        List of message file paths in order
    """
    chat_path = Path(chat_dir)
    
    # Check for combined_message.json first
    combined = chat_path / "combined_message.json"
    if combined.exists():
        return [combined]
    
    # Look for message_*.json files (sorted numerically)
    msg_files = sorted(
        chat_path.glob("message_*.json"),
        key=lambda p: int(''.join(filter(str.isdigit, p.stem)))
    )
    
    if msg_files:
        return msg_files
    
    return []


def load_chat_metadata(chat_dir: str) -> Dict[str, Any]:
    """Load chat metadata (participants, title) from any message file.
    
    Args:
        chat_dir: Path to the chat directory
        
    Returns:
        Chat metadata dictionary
    """
    files = discover_message_files(chat_dir)
    if not files:
        raise FileNotFoundError(f"No message files found in {chat_dir}")
    
    with open(files[0], 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return {
        'participants': data.get('participants', []),
        'title': data.get('title', ''),
        'is_still_participant': data.get('is_still_participant', True),
        'thread_path': data.get('thread_path', ''),
        'magic_words': data.get('magic_words', [])
    }


def combine_messages(chat_dir: str) -> Dict[str, Any]:
    """Combine all message files from a chat directory.
    
    Args:
        chat_dir: Path to the chat directory
        
    Returns:
        Combined chat data dictionary with all messages merged and sorted
    """
    files = discover_message_files(chat_dir)
    if not files:
        raise FileNotFoundError(f"No message files found in {chat_dir}")
    
    # Load metadata from first file
    metadata = load_chat_metadata(chat_dir)
    
    # Load and merge all messages
    all_messages = []
    for msg_file in files:
        with open(msg_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            messages = data.get('messages', [])
            all_messages.extend(messages)
    
    # Sort by timestamp (handle both timestamp_ms and date fields)
    def sort_key(msg):
        if 'timestamp_ms' in msg:
            return msg['timestamp_ms']
        return 0
    
    all_messages.sort(key=sort_key)
    
    # Deduplicate by (timestamp_ms, sender_name, content)
    seen = set()
    unique_messages = []
    for msg in all_messages:
        key = (
            msg.get('timestamp_ms', 0),
            msg.get('sender_name', ''),
            msg.get('content', '')
        )
        if key not in seen:
            seen.add(key)
            unique_messages.append(msg)
    
    combined = {
        'participants': metadata['participants'],
        'title': metadata['title'],
        'is_still_participant': metadata['is_still_participant'],
        'thread_path': metadata['thread_path'],
        'magic_words': metadata['magic_words'],
        'messages': unique_messages
    }
    
    return combined


def save_combined(combined: Dict[str, Any], chat_dir: str) -> Path:
    """Save combined messages to combined_message.json.
    
    Args:
        combined: Combined chat data
        chat_dir: Path to the chat directory
        
    Returns:
        Path to the saved file
    """
    output_path = Path(chat_dir) / "combined_message.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    return output_path


def combine_and_save(chat_dir: str, save: bool = True) -> Dict[str, Any]:
    """Combine messages and optionally save to file.
    
    Args:
        chat_dir: Path to the chat directory
        save: Whether to save combined_message.json (default: True)
        
    Returns:
        Combined chat data dictionary
    """
    combined = combine_messages(chat_dir)
    
    if save:
        save_combined(combined, chat_dir)
    
    return combined


def get_chat_dirs(base_dir: str, chat_ids: List[str] = None) -> List[Path]:
    """Discover all chat directories under base_dir.
    
    Args:
        base_dir: Base directory containing chat folders
        chat_ids: Optional list of specific chat IDs to include
        
    Returns:
        List of chat directory paths
    """
    base = Path(base_dir)
    inbox = base / "your_instagram_activity" / "messages" / "inbox"
    
    if not inbox.exists():
        raise FileNotFoundError(f"Inbox directory not found: {inbox}")
    
    chat_dirs = []
    for chat_dir in sorted(inbox.iterdir()):
        if not chat_dir.is_dir():
            continue
        
        # Check if it has message files
        if chat_dir.glob("message_*.json") or (chat_dir / "combined_message.json").exists():
            if chat_ids is None or any(chat_dir.name.endswith(cid) for cid in chat_ids):
                chat_dirs.append(chat_dir)
    
    return chat_dirs
