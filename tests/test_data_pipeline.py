"""Tests for data pipeline: combiner and loader."""

import json
import tempfile
from pathlib import Path

from src.data_combiner import (
    discover_message_files,
    combine_messages,
    load_chat_metadata,
)
from src.data_loader import load_chat, load_chat_from_dir


class TestDiscoverMessageFiles:
    """Test file discovery logic."""

    def test_combined_message_json_priority(self, tmp_path):
        """combined_message.json takes priority over message_*.json."""
        # Create files
        (tmp_path / "combined_message.json").write_text("{}", encoding="utf-8")
        (tmp_path / "message_1.json").write_text("{}", encoding="utf-8")
        (tmp_path / "message_2.json").write_text("{}", encoding="utf-8")

        files = discover_message_files(str(tmp_path))
        assert len(files) == 1
        assert files[0].name == "combined_message.json"

    def test_multiple_message_files_sorted(self, tmp_path):
        """Multiple message files are discovered and sorted numerically."""
        (tmp_path / "message_3.json").write_text("{}", encoding="utf-8")
        (tmp_path / "message_1.json").write_text("{}", encoding="utf-8")
        (tmp_path / "message_2.json").write_text("{}", encoding="utf-8")

        files = discover_message_files(str(tmp_path))
        assert len(files) == 3
        assert [f.name for f in files] == ["message_1.json", "message_2.json", "message_3.json"]

    def test_single_message_file(self, tmp_path):
        """Single message file is found."""
        (tmp_path / "message_1.json").write_text("{}", encoding="utf-8")

        files = discover_message_files(str(tmp_path))
        assert len(files) == 1
        assert files[0].name == "message_1.json"

    def test_no_files_raises(self, tmp_path):
        """No message files returns empty list."""
        files = discover_message_files(str(tmp_path))
        assert len(files) == 0


class TestCombineMessages:
    """Test message combining logic."""

    def _create_test_chat(self, tmp_path, num_files=2, msgs_per_file=10):
        """Helper to create test chat files."""
        for i in range(num_files):
            messages = []
            for j in range(msgs_per_file):
                msg_id = i * msgs_per_file + j
                messages.append({
                    "sender_name": "UserA" if msg_id % 2 == 0 else "UserB",
                    "timestamp_ms": 1000000000000 + msg_id * 1000,
                    "content": f"Message {msg_id}",
                })
            data = {
                "participants": [{"name": "UserA"}, {"name": "UserB"}],
                "title": "Test Chat",
                "messages": messages,
            }
            (tmp_path / f"message_{i + 1}.json").write_text(
                json.dumps(data), encoding="utf-8"
            )

    def test_combine_two_files(self, tmp_path):
        """Two message files are combined correctly."""
        self._create_test_chat(tmp_path, num_files=2, msgs_per_file=5)

        combined = combine_messages(str(tmp_path))
        assert len(combined["messages"]) == 10
        assert combined["participants"] == [{"name": "UserA"}, {"name": "UserB"}]
        assert combined["title"] == "Test Chat"

    def test_combine_sorts_by_timestamp(self, tmp_path):
        """Combined messages are sorted by timestamp_ms."""
        self._create_test_chat(tmp_path, num_files=2, msgs_per_file=5)

        combined = combine_messages(str(tmp_path))
        timestamps = [m["timestamp_ms"] for m in combined["messages"]]
        assert timestamps == sorted(timestamps)

    def test_combine_deduplicates(self, tmp_path):
        """Duplicate messages are removed."""
        # Create two files where message_2 has overlap with message_1
        base_msgs = []
        for j in range(5):
            base_msgs.append({
                "sender_name": "UserA",
                "timestamp_ms": 1000000000000 + j * 1000,
                "content": f"Shared message {j}",
            })
        extra_msgs = [
            {
                "sender_name": "UserB",
                "timestamp_ms": 1000000005000 + j * 1000,
                "content": f"Extra message {j}",
            }
            for j in range(3)
        ]

        (tmp_path / "message_1.json").write_text(
            json.dumps({"participants": [], "messages": base_msgs}),
            encoding="utf-8",
        )
        (tmp_path / "message_2.json").write_text(
            json.dumps({"participants": [], "messages": base_msgs[:2] + extra_msgs}),
            encoding="utf-8",
        )

        combined = combine_messages(str(tmp_path))
        # 5 from file1 + 3 unique extras (2 are duplicates)
        assert len(combined["messages"]) == 8

    def test_combined_file_is_loaded_directly(self, tmp_path):
        """If combined_message.json exists, it's used directly."""
        self._create_test_chat(tmp_path, num_files=2, msgs_per_file=10)

        # Create a combined file with different data
        combined_data = {
            "participants": [{"name": "UserA"}],
            "title": "Pre-combined",
            "messages": [{"sender_name": "UserA", "timestamp_ms": 999, "content": "only one"}],
        }
        (tmp_path / "combined_message.json").write_text(
            json.dumps(combined_data), encoding="utf-8"
        )

        combined = combine_messages(str(tmp_path))
        assert len(combined["messages"]) == 1
        assert combined["title"] == "Pre-combined"


class TestLoadChatFromDir:
    """Test the load_chat_from_dir function."""

    def _create_test_chat(self, tmp_path):
        """Create a minimal test chat."""
        data = {
            "participants": [{"name": "Alice"}, {"name": "Bob"}],
            "title": "Test Chat",
            "messages": [
                {"sender_name": "Alice", "timestamp_ms": 1000, "content": "Hello"},
                {"sender_name": "Bob", "timestamp_ms": 2000, "content": "Hi"},
            ],
        }
        (tmp_path / "combined_message.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        return str(tmp_path)

    def test_load_existing_combined(self, tmp_path):
        """Loads existing combined_message.json directly."""
        chat_dir = self._create_test_chat(tmp_path)
        data = load_chat_from_dir(chat_dir)
        assert len(data["messages"]) == 2
        assert data["title"] == "Test Chat"

    def test_load_from_message_files(self, tmp_path):
        """Combines message_*.json files when no combined file exists."""
        chat_dir = tmp_path
        data = {
            "participants": [{"name": "Alice"}, {"name": "Bob"}],
            "title": "Multi-file Chat",
            "messages": [
                {"sender_name": "Alice", "timestamp_ms": 1000, "content": "Msg1"},
                {"sender_name": "Bob", "timestamp_ms": 2000, "content": "Msg2"},
            ],
        }
        (chat_dir / "message_1.json").write_text(json.dumps(data), encoding="utf-8")

        loaded = load_chat_from_dir(str(chat_dir))
        assert len(loaded["messages"]) == 2
        assert loaded["title"] == "Multi-file Chat"
        # Should have created combined_message.json
        assert (chat_dir / "combined_message.json").exists()


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
