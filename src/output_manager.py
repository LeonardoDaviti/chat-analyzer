"""
Output Manager for Instagram Chat Analysis

Creates organized output directory structure:
  Outputs/
  └── {Chat Name}/
      └── {YYYY-MM-DD_HH-MM-SS}/
          ├── sessions.json           # All session data
          ├── analysis.json           # Full analysis results
          ├── session_stats.json      # Session summary statistics
          ├── visualizations/         # Chart images
          └── normalized.json         # Normalized chat data (optional)

Usage:
    from src.output_manager import create_output_dir, get_output_paths
    
    base_dir = "Outputs"
    output_paths = create_output_dir(base_dir, chat_name)
    # Returns dict with paths to all output directories/files
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any


def create_output_dir(base_dir: str, chat_name: str) -> Dict[str, Path]:
    """Create output directory structure for a chat.
    
    Args:
        base_dir: Base output directory (e.g., "Outputs")
        chat_name: Display name of the chat
        
    Returns:
        Dictionary with paths to all output directories and files
    """
    # Sanitize chat name for filesystem
    safe_name = _sanitize_filename(chat_name)
    
    # Create timestamped output folder
    now = datetime.now()
    timestamp = now.strftime('%Y-%m-%d_%H-%M')
    
    output_base = Path(base_dir) / safe_name / timestamp
    output_base.mkdir(parents=True, exist_ok=True)
    
    # Create subdirectories
    viz_dir = output_base / "visualizations"
    viz_dir.mkdir(exist_ok=True)
    
    # Create sessions markdown directory
    sessions_md_dir = output_base / "sessions_md"
    sessions_md_dir.mkdir(exist_ok=True)
    
    return {
        'base': output_base,
        'visualizations': viz_dir,
        'sessions': output_base / 'sessions.json',
        'analysis': output_base / 'analysis.json',
        'session_stats': output_base / 'session_stats.json',
        'session_analyses': output_base / 'session_analyses.json',
        'normalized': output_base / 'normalized.json',
        'metadata': output_base / 'metadata.json',
        'sessions_md': sessions_md_dir,
    }


def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename.
    
    Args:
        name: Original string
        
    Returns:
        Sanitized string safe for filenames
    """
    # Replace problematic characters
    safe = name.replace('/', '_').replace('\\', '_')
    safe = safe.replace(':', '_').replace('*', '_')
    safe = safe.replace('?', '_').replace('"', '_')
    safe = safe.replace('<', '_').replace('>', '_')
    safe = safe.replace('|', '_')
    # Remove extra whitespace
    safe = ' '.join(safe.split())
    return safe


def save_json(data: Any, path: Path) -> None:
    """Save data to a JSON file.
    
    Args:
        data: Data to serialize
        path: Output file path
    """
    import json
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
