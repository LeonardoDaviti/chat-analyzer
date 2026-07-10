"""Tests for zip import (main.import_zip) and owner auto-detection."""

import json
import zipfile
from pathlib import Path

import pytest

import main


def _write_inbox_zip(zip_path: Path, chats: dict) -> None:
    """Build a minimal Instagram-export zip with the inbox structure.

    ``chats`` maps ``chat_folder -> participants list`` and each chat gets a
    single ``message_1.json``.
    """
    inbox = "your_instagram_activity/messages/inbox"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for folder, participants in chats.items():
            payload = {
                "participants": [{"name": p} for p in participants],
                "messages": [{"sender_name": participants[0],
                              "timestamp_ms": 1, "content": "hi"}],
                "title": folder,
            }
            zf.writestr(f"{inbox}/{folder}/message_1.json",
                        json.dumps(payload))


def test_import_zip_extracts_and_counts(tmp_path):
    zip_path = tmp_path / "instagram-export-2026.zip"
    _write_inbox_zip(zip_path, {
        "alice_123": ["Owner", "Alice"],
        "bob_456": ["Owner", "Bob"],
    })

    target = main.import_zip(str(zip_path), tmp_path)

    inbox = Path(target).joinpath(*main._INBOX_SUFFIX)
    assert inbox.exists()
    # extracted under Chats/Instagram/<zipname>/ (platform-separated layout)
    assert Path(target) == tmp_path / "Chats" / "Instagram" / "instagram-export-2026"
    assert (inbox / "alice_123" / "message_1.json").exists()
    assert (inbox / "bob_456" / "message_1.json").exists()


def test_import_zip_cli_naming_unchanged(tmp_path):
    """dest_name=None (the CLI --import-zip path) still uses the zip's stem."""
    zip_path = tmp_path / "instagram-cli-export.zip"
    _write_inbox_zip(zip_path, {"alice_1": ["Owner", "Alice"]})
    target = main.import_zip(str(zip_path), tmp_path)
    assert Path(target) == tmp_path / "Chats" / "Instagram" / "instagram-cli-export"


def test_import_zip_dest_name_override(tmp_path):
    """A browser upload's temp path is filed under the original filename."""
    zip_path = tmp_path / "tmp2ip9o4qu.zip"
    _write_inbox_zip(zip_path, {"alice_1": ["Owner", "Alice"]})
    target = main.import_zip(str(zip_path), tmp_path, dest_name="Real Name.zip")
    # extension stripped; folder named after the upload, not the temp stem
    assert Path(target) == tmp_path / "Chats" / "Instagram" / "Real Name"
    assert not (tmp_path / "Chats" / "Instagram" / "tmp2ip9o4qu").exists()


def test_import_zip_collision_suffix(tmp_path):
    """Re-importing the same name never merges/overwrites — it gets -2, -3, ..."""
    zip_path = tmp_path / "e.zip"
    _write_inbox_zip(zip_path, {"alice_1": ["Owner", "Alice"]})
    t1 = main.import_zip(str(zip_path), tmp_path, dest_name="dup.zip")
    t2 = main.import_zip(str(zip_path), tmp_path, dest_name="dup.zip")
    t3 = main.import_zip(str(zip_path), tmp_path, dest_name="dup.zip")
    assert Path(t1) == tmp_path / "Chats" / "Instagram" / "dup"
    assert Path(t2) == tmp_path / "Chats" / "Instagram" / "dup-2"
    assert Path(t3) == tmp_path / "Chats" / "Instagram" / "dup-3"


def test_import_zip_rejects_zip_slip(tmp_path):
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("your_instagram_activity/messages/inbox/ok/message_1.json",
                    "{}")
        # member escaping the target directory
        zf.writestr("../../escaped.txt", "pwned")

    with pytest.raises(ValueError, match="zip-slip"):
        main.import_zip(str(zip_path), tmp_path)

    # nothing was written outside the target
    assert not (tmp_path.parent / "escaped.txt").exists()


def test_import_zip_missing_inbox_errors(tmp_path):
    zip_path = tmp_path / "notmessages.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("some_other_folder/file.json", "{}")

    with pytest.raises(FileNotFoundError):
        main.import_zip(str(zip_path), tmp_path)


def test_owner_detection_most_common_participant():
    # Owner is in every chat; partners each appear once.
    chats = [
        ["Owner", "Alice"],
        ["Owner", "Bob"],
        ["Owner", "Carol"],
        ["Owner", "Alice", "Eve"],  # a group chat
    ]
    assert main.detect_owner_from_participants(chats) == "Owner"


def test_owner_detection_empty():
    assert main.detect_owner_from_participants([]) is None
    assert main.detect_owner_from_participants([[], []]) is None


def test_owner_detection_end_to_end(tmp_path):
    """detect_owner reads participants from real chat dirs on disk."""
    zip_path = tmp_path / "export.zip"
    _write_inbox_zip(zip_path, {
        "alice_1": ["Owner", "Alice"],
        "bob_2": ["Owner", "Bob"],
        "carol_3": ["Owner", "Carol"],
    })
    target = main.import_zip(str(zip_path), tmp_path)
    inbox = Path(target).joinpath(*main._INBOX_SUFFIX)
    chat_dirs = [str(d) for d in inbox.iterdir() if d.is_dir()]
    assert main.detect_owner(chat_dirs) == "Owner"
