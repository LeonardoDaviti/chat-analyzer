"""Tests for the hide-chats feature (M1.4) builder side.

The dashboard writes ``Dashboard/data/hidden.json`` (a list of chat ids); the
builders read it as the single source of truth and drop those chats on the next
re-analyze. Synthetic payloads only — no real chats.
"""

import json

import build_connected
import build_insights


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_load_hidden_parsing(tmp_path):
    dash = tmp_path / "Dashboard"
    # Missing file -> empty set for both builders.
    assert build_insights.load_hidden(dash) == set()
    assert build_connected._load_hidden(str(dash)) == set()

    hj = dash / "data" / "hidden.json"
    # Valid list, with non-string entries filtered out.
    _write(hj, json.dumps(["a", "b", 3, None]))
    assert build_insights.load_hidden(dash) == {"a", "b"}
    assert build_connected._load_hidden(str(dash)) == {"a", "b"}

    # A non-list JSON value -> empty set (not an error).
    _write(hj, '{"not": "a list"}')
    assert build_insights.load_hidden(dash) == set()
    assert build_connected._load_hidden(str(dash)) == set()

    # Invalid JSON -> empty set.
    _write(hj, "not json at all")
    assert build_insights.load_hidden(dash) == set()
    assert build_connected._load_hidden(str(dash)) == set()


def test_build_insights_excludes_hidden(tmp_path, monkeypatch):
    dash = tmp_path / "Dashboard"
    data = dash / "data"
    data.mkdir(parents=True)
    manifest = [
        {"id": "keep", "file": "data/keep.js", "is_group": False, "platform": "instagram"},
        {"id": "drop", "file": "data/drop.js", "is_group": False, "platform": "instagram"},
    ]
    (data / "manifest.js").write_text(
        "window.DASHBOARD_MANIFEST = " + json.dumps(manifest) + ";", encoding="utf-8")
    payload = {"is_group": False, "platform": "instagram",
               "participants": ["Me", "You"], "daily": {}}
    (data / "keep.js").write_text(
        'window.DASHBOARD_DATA["keep"] = ' + json.dumps(payload) + ";", encoding="utf-8")
    (data / "drop.js").write_text(
        'window.DASHBOARD_DATA["drop"] = ' + json.dumps(payload) + ";", encoding="utf-8")
    (data / "hidden.json").write_text(json.dumps(["drop"]), encoding="utf-8")

    seen = []
    monkeypatch.setattr(build_insights, "run_chat",
                        lambda cid, p, owner: seen.append(cid) or [])
    monkeypatch.setattr(build_insights, "run_connected", lambda *a, **k: [])

    build_insights.build(dash)
    assert "keep" in seen
    assert "drop" not in seen


def test_template_has_new_ui_surfaces():
    """The template ships the three wave-2 UI features (M1.4, M2.2, M2.3)."""
    from src.dashboard_template import render_index_html
    html = render_index_html()
    # M1.4 hide chats
    assert "function hideChat(" in html
    assert "function unhideChat(" in html
    assert "/hidden" in html
    # M2.2 findings under charts
    assert "function injectStripHosts(" in html
    assert "var ANCHOR_IDS=" in html
    assert "function fStrip(" in html
    # M2.3 compare mode
    assert "function selectCompare(" in html
    assert "var CMP_METRICS=" in html
    assert "function toggleCompare(" in html
