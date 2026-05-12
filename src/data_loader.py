"""Data loading and parsing for Instagram chat JSON files.

Supports multiple loading strategies:
  1. Direct loading from a single JSON file
  2. Auto-discovery of chat directories (message_*.json or combined_message.json)
  3. Loading from a specific directory with optional normalization

Pipeline: discover → combine → normalize → load

Usage:
    # Quick load (uses existing normalized.json if available)
    chat = load_chat_from_dir(chat_dir)
    
    # Auto-discover all chats in inbox
    chats = load_all_chats(inbox_path)
    
    # Force re-normalization
    chat = load_chat_from_dir(chat_dir, force_normalize=True)
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional

from src.data_combiner import combine_messages, discover_message_files
from src.normalizer import (
    normalize_and_save,
    normalize_chat_from_data,
    load_normalized,
)


def load_chat(chat_path: str) -> Dict[str, Any]:
    """Load and parse a single chat JSON file.
    
    Args:
        chat_path: Path to the message_*.json or combined_message.json file
        
    Returns:
        Parsed JSON data as dictionary
    """
    with open(chat_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_all_chats(inbox_path: str) -> Dict[str, Dict[str, Any]]:
    """Load all chats from inbox directory.
    
    Uses normalized.json if available, falls back to combined_message.json,
    then to message_*.json files.
    
    Args:
        inbox_path: Path to the inbox directory containing chat folders
        
    Returns:
        Dictionary mapping chat names to their data
    """
    chats = {}
    inbox = Path(inbox_path)
    
    if not inbox.exists():
        raise FileNotFoundError(f"Inbox directory not found: {inbox_path}")
    
    for chat_dir in sorted(inbox.iterdir()):
        if not chat_dir.is_dir():
            continue
        
        # Priority: normalized.json > combined_message.json > message_*.json
        normalized = chat_dir / 'normalized.json'
        combined = chat_dir / 'combined_message.json'
        msg_files = sorted(chat_dir.glob('message_*.json'),
                          key=lambda p: int(''.join(filter(str.isdigit, p.stem))))
        
        if normalized.exists():
            chat_name = chat_dir.name
            with open(normalized, 'r', encoding='utf-8') as f:
                chats[chat_name] = json.load(f)
            continue
        
        if combined.exists():
            chat_name = chat_dir.name
            chats[chat_name] = load_chat(str(combined))
            continue
        
        if msg_files:
            chat_name = chat_dir.name
            chats[chat_name] = load_chat(str(msg_files[0]))
    
    return chats


def load_specific_chats(chat_paths: List[str]) -> Dict[str, Dict[str, Any]]:
    """Load specific chat files by path.
    
    Args:
        chat_paths: List of paths to message_*.json or combined_message.json files
        
    Returns:
        Dictionary mapping chat names to their data
    """
    chats = {}
    
    for chat_path in chat_paths:
        path = Path(chat_path)
        if path.exists():
            chat_name = path.parent.name
            chats[chat_name] = load_chat(str(path))
        else:
            print(f"Warning: Chat file not found: {chat_path}")
    
    return chats


def load_chat_from_dir(
    chat_dir: str,
    force_normalize: bool = False
) -> Dict[str, Any]:
    """Load a chat from its directory with full pipeline.
    
    Follows this priority:
      1. If normalized.json exists → load it directly (fastest, decoded Georgian)
      2. If combined_message.json exists → normalize it
      3. If message_*.json files exist → combine + normalize them
    
    Args:
        chat_dir: Path to the chat directory
        force_normalize: Re-normalize even if normalized.json exists
        
    Returns:
        Normalized chat data with decoded Georgian text and all annotations
    """
    chat_path = Path(chat_dir)
    
    # Fast path: use existing normalized file (unless force_normalize)
    if not force_normalize:
        existing = load_normalized(chat_dir)
        if existing is not None:
            print(f"  Loaded normalized data ({len(existing.get('messages', []))} msgs)")
            return existing
    
    # Check for combined file
    combined_file = chat_path / "combined_message.json"
    if combined_file.exists():
        with open(combined_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"  Loaded combined data ({len(data.get('messages', []))} msgs)")
    else:
        # Combine message files
        msg_files = discover_message_files(chat_dir)
        if not msg_files:
            raise FileNotFoundError(f"No message files found in {chat_dir}")
        
        print(f"  Combining {len(msg_files)} message file(s)...")
        data = combine_messages(chat_dir)
    
    # Normalize
    print(f"  Normalizing (decoding Georgian text, detecting language)...")
    normalized = normalize_chat_from_data(data)
    print(f"  Normalization complete. Saved to: normalized.json")
    
    return normalized


def load_chats_from_dirs(
    base_dir: str,
    chat_ids: Optional[List[str]] = None,
    force_normalize: bool = False
) -> Dict[str, Dict[str, Any]]:
    """Load multiple chats from directories under base_dir.
    
    Args:
        base_dir: Base directory containing chat folders
        chat_ids: Optional list of chat IDs to include (filters by directory name)
        force_normalize: Re-normalize all chats
        
    Returns:
        Dictionary mapping chat names to their normalized data
    """
    inbox = Path(base_dir) / "your_instagram_activity" / "messages" / "inbox"
    
    if not inbox.exists():
        raise FileNotFoundError(f"Inbox directory not found: {inbox}")
    
    chats = {}
    for chat_dir in sorted(inbox.iterdir()):
        if not chat_dir.is_dir():
            continue
        
        # Filter by chat_ids if specified
        if chat_ids and not any(chat_dir.name.endswith(cid) for cid in chat_ids):
            continue
        
        # Check if it has message files
        has_msgs = chat_dir.glob("message_*.json") or (chat_dir / "combined_message.json").exists()
        if not has_msgs:
            continue
        
        chat_name = chat_dir.name
        try:
            chats[chat_name] = load_chat_from_dir(str(chat_dir), force_normalize=force_normalize)
            msg_count = len(chats[chat_name].get('messages', []))
            print(f"  ✓ {chat_name}: {msg_count} messages")
        except Exception as e:
            print(f"  ✗ {chat_name}: Error - {e}")
    
    return chats


def get_chat_name_from_dir(chat_dir: str) -> str:
    """Extract the display name for a chat from its directory.
    
    Args:
        chat_dir: Path to the chat directory
        
    Returns:
        Display name (title from chat data, or directory name as fallback)
    """
    from src.data_loader import load_chat_from_dir
    try:
        data = load_chat_from_dir(chat_dir)
        title = data.get('title', '')
        if title:
            return title
    except Exception:
        pass
    return Path(chat_dir).name
