"""Tests for M3.2 cross-platform identity merge (MANUAL only).

All fixtures are synthetic — no real contact names or message content. The merge
is applied ONLY to the ``all`` variant; per-platform variants stay unmerged. A
false merge poisons every connected metric, so nothing is ever auto-matched:
identities come exclusively from ``Dashboard/data/identities.json``.
"""

import json

import pytest

from src.connected_export import (
    reduce_message, Chat, build_connected_data, load_identities,
)

TZ = "Asia/Tbilisi"
IG_OWNER = "Owner"
TG_OWNER = "Ownerus"
BASE = 1_700_000_000_000
MIN = 60 * 1000
DAY = 24 * 60 * MIN


def _msg(ts, sender, content="hello there friend"):
    return {"timestamp_ms": ts, "sender_name": sender,
            "content": content, "language": "english", "type": "text"}


def _chat(chat_id, participants, raw_msgs, platform="instagram"):
    recs = [reduce_message(m, TZ) for m in raw_msgs]
    recs.sort(key=lambda r: r["timestamp_ms"])
    c = Chat.__new__(Chat)
    c.chat_id = chat_id
    c.name = chat_id
    c.participants = participants
    c.is_group = len(participants) >= 3
    c.recs = recs
    c.thread_path = ""
    c.platform = platform
    return c


def _mariam_ig():
    # 2 owner-sent, 1 received; spans BASE .. BASE+2min.
    return _chat("mariam_ig", [IG_OWNER, "Mariam"], [
        _msg(BASE, IG_OWNER),
        _msg(BASE + MIN, "Mariam"),
        _msg(BASE + 2 * MIN, IG_OWNER),
    ], platform="instagram")


def _mariam_tg():
    # 1 owner-sent, 2 received; 5 days EARLIER than the IG chat.
    t0 = BASE - 5 * DAY
    return _chat("mariam_tg", [TG_OWNER, "MariamTG"], [
        _msg(t0, "MariamTG"),            # contact opens this session
        _msg(t0 + MIN, "MariamTG"),
        _msg(t0 + 2 * MIN, TG_OWNER),
    ], platform="telegram")


def _all(chats, identities=None):
    return build_connected_data(
        chats, IG_OWNER, TZ, min_msgs=0, min_replies=0,
        variant="all", platforms=["instagram", "telegram"],
        owner_names={IG_OWNER, TG_OWNER}, identities=identities)


def _by_name(payload, name):
    return next(c for c in payload["contacts"] if c["name"] == name)


# --------------------------------------------------------------------------- #
# load_identities
# --------------------------------------------------------------------------- #

def test_absent_file_is_noop(tmp_path):
    assert load_identities(str(tmp_path / "Dashboard")) == []


def test_valid_file_parses(tmp_path):
    d = tmp_path / "Dashboard" / "data"
    d.mkdir(parents=True)
    (d / "identities.json").write_text(json.dumps({"identities": [
        {"name": " Mariam ", "members": ["instagram:mariam_ig", "telegram:mariam_tg"]},
    ]}), encoding="utf-8")
    out = load_identities(str(tmp_path / "Dashboard"))
    assert out == [{"name": "Mariam",
                    "members": ["instagram:mariam_ig", "telegram:mariam_tg"]}]


@pytest.mark.parametrize("body", [
    "not json at all",
    json.dumps(["a", "b"]),                       # top-level not an object
    json.dumps({"identities": "nope"}),           # identities not a list
    json.dumps({"identities": [{"members": ["a:b"]}]}),         # no name
    json.dumps({"identities": [{"name": "X", "members": []}]}),  # empty members
    json.dumps({"identities": [{"name": "X", "members": ["nocolon"]}]}),  # bad key
    json.dumps({"identities": [{"name": "", "members": ["a:b"]}]}),        # blank name
])
def test_malformed_file_rejected(tmp_path, body):
    d = tmp_path / "Dashboard" / "data"
    d.mkdir(parents=True)
    (d / "identities.json").write_text(body, encoding="utf-8")
    with pytest.raises(ValueError):
        load_identities(str(tmp_path / "Dashboard"))


# --------------------------------------------------------------------------- #
# merge math (all variant)
# --------------------------------------------------------------------------- #

IDENT = [{"name": "Mariam",
          "members": ["instagram:mariam_ig", "telegram:mariam_tg"]}]


def test_no_identities_keeps_contacts_separate():
    p = _all([_mariam_ig(), _mariam_tg()], identities=None)
    assert p["totals"]["contacts"] == 2
    names = {c["name"] for c in p["contacts"]}
    assert names == {"Mariam", "MariamTG"}
    assert not any(c.get("merged") for c in p["contacts"])


def test_merge_sums_volumes_and_recomputes_shares():
    p = _all([_mariam_ig(), _mariam_tg()], identities=IDENT)
    assert p["totals"]["contacts"] == 1
    m = _by_name(p, "Mariam")
    assert m["merged"] is True
    assert m["platform"] == "merged"
    # summed volumes: IG 2 owner-sent + TG 1; received 1 + 2.
    assert m["sent"] == 3
    assert m["received"] == 3
    # reciprocity recomputed from the SUMMED totals, not averaged.
    assert m["reciprocity"] == pytest.approx(1.0)
    # per-platform breakdown kept for the ⧉ badge (owner-sent per platform).
    assert m["platforms"] == {"instagram": 2, "telegram": 1}


def test_merge_min_first_max_last_dates():
    p = _all([_mariam_ig(), _mariam_tg()], identities=IDENT)
    m = _by_name(p, "Mariam")
    ig, tg = _mariam_ig(), _mariam_tg()
    from src.timeutil import to_datetime
    tg_first = to_datetime(tg.recs[0]["timestamp_ms"], TZ).strftime("%Y-%m-%d")
    ig_last = to_datetime(ig.recs[-1]["timestamp_ms"], TZ).strftime("%Y-%m-%d")
    assert m["first_day"] == tg_first     # earliest across both platforms
    assert m["last_day"] == ig_last       # latest across both platforms


def test_merge_recomputes_initiation_share():
    # Owner opens the IG session, contact opens the TG session -> 1 of 2 sessions.
    p = _all([_mariam_ig(), _mariam_tg()], identities=IDENT)
    m = _by_name(p, "Mariam")
    assert m["sessions"] == 2
    assert m["initiations"] == 1
    assert m["initiation_share"] == pytest.approx(0.5)


def test_merge_appears_in_leaderboards():
    p = _all([_mariam_ig(), _mariam_tg()], identities=IDENT)
    sent_rows = p["leaderboards"]["by_sent_share"]
    assert len(sent_rows) == 1
    row = sent_rows[0]
    assert row["name"] == "Mariam"
    assert row["platform"] == "merged"
    assert row["merged"] is True
    assert row["platforms"] == {"instagram": 2, "telegram": 1}


def test_single_present_member_not_merged():
    # Identity references a TG member that isn't loaded -> only IG present -> no merge.
    ident = [{"name": "Mariam",
              "members": ["instagram:mariam_ig", "telegram:missing"]}]
    p = _all([_mariam_ig()], identities=ident)
    assert p["totals"]["contacts"] == 1
    c = p["contacts"][0]
    assert not c.get("merged")
    assert c["platform"] == "instagram"


def test_per_platform_variant_unmerged():
    # The merge is 'all'-only: passing identities to a per-platform variant is a
    # no-op even when both mapped contacts are present.
    p = build_connected_data(
        [_mariam_ig(), _mariam_tg()], IG_OWNER, TZ, min_msgs=0, min_replies=0,
        variant="instagram", platforms=["instagram"],
        owner_names={IG_OWNER}, identities=IDENT)
    assert p["totals"]["contacts"] == 2
    assert not any(c.get("merged") for c in p["contacts"])


# --------------------------------------------------------------------------- #
# insights engine: connected rules must not break on a merged entity
# --------------------------------------------------------------------------- #

def test_insights_run_connected_on_merged_entity():
    from src.insights_engine import run_connected
    p = _all([_mariam_ig(), _mariam_tg()], identities=IDENT)
    # A merged contact has platform == "merged" (a string) + a platforms dict;
    # the connected rules read volumes/leaderboards, never the platform field,
    # so this must run cleanly and return a list.
    findings = run_connected(p)
    assert isinstance(findings, list)


# --------------------------------------------------------------------------- #
# template ships the manage panel + persistence wiring
# --------------------------------------------------------------------------- #

def test_template_has_merge_ui():
    from src.dashboard_template import render_index_html
    html = render_index_html()
    assert "function renderConnMerge(" in html
    assert "function connMergeSelected(" in html
    assert "function connUnmerge(" in html
    assert "/identities" in html
    assert "connMergePanel" in html
    # ⧉ badge for merged entities.
    assert "p==='merged'" in html
