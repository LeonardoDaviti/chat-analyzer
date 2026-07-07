"""Platform loaders.

Each loader turns a platform-specific export into the *normalized-input shape*
the Instagram analysis pipeline consumes (``{title, participants, thread_path,
messages}`` where every message has ``sender_name``, ``timestamp_ms``,
``content`` and the optional media/reaction channels).

  - ``telegram``  — Telegram Desktop JSON exports (``result.json``).

The Instagram path is intentionally left in ``src.data_loader`` /
``src.data_combiner`` untouched; a thin re-export is provided for symmetry.
"""

from src.loaders.telegram import (  # noqa: F401
    load_telegram_chat,
    parse_telegram_result,
    telegram_participants,
    telegram_thread_path,
    telegram_title,
    is_telegram_export,
)
