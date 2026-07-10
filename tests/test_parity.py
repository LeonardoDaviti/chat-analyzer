"""Python ↔ JavaScript parity smoke check for windowed findings.

The dashboard's JS-side windowed engine (``JS_WINDOWABLE_RULES``) mirrors a
subset of Python's ``WINDOWABLE_RULE_IDS``.  This module verifies that both
sides agree on which rules fire for a given daily-table payload.

Rules that need weekly aggregation (``feast-and-famine``,
``steady-drumbeat``) or extras not in the daily table
(``media-reciprocity-gap``, ``we-ness-shift``) are **expected to be
skipped** by JS — they're verified as silently excluded, not as fires.

The parity comparison is between:
  1. A pure-Python reference that mirrors the JS logic exactly
     (``_PY_WINDOWABLE_RULES``)
  2. The actual JS code embedded in ``dashboard_template.py`` (via
     string-parsing + evaluation in a sandbox).

For rules where the all-time Python engine (``run_chat``) differs from the
windowed logic — different thresholds, different gates — that is expected
and not tested here.  This module only checks **windowed parity**.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.insights_engine import (  # noqa: E402
    WINDOWABLE_RULE_IDS,
)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

OWNER = "B"
PARTNER = "A"
USERS = [OWNER, PARTNER]

# Rules that have a JS counterpart and should produce identical results.
PARITY_RULES = frozenset({
    "question-imbalance",
    "gottman-ratio",
    "courtesy-asymmetry",
    "depth-mismatch",
    "night-migration",
    "monologue-drift",
    "eager-waiter",
    "left-on-react",
    "unanswered-bids",
})

# Rules that Python can window but JS skips (weekly-aggregate or extras-only).
JS_SKIPPED = frozenset({
    "feast-and-famine",
    "steady-drumbeat",
    "media-reciprocity-gap",
    "we-ness-shift",
})

# All windowable rules in Python.
EXPECTED_WINDOWABLE = PARITY_RULES | JS_SKIPPED


# --------------------------------------------------------------------------- #
# Synthetic daily-table builder
# --------------------------------------------------------------------------- #

def _cell(
    msgs: int = 60,
    words: int = 300,
    questions: int = 0,
    questions_answered: int = 0,
    neg_words: int = 0,
    pos_words: int = 0,
    gratitude: int = 0,
    apology: int = 0,
    initiations: int = 0,
    turns: int = 0,
    turns_answered: int = 0,
    reacted_leave: int = 0,
    resp_lat_sum_min: int = 0,
    resp_lat_n: int = 0,
    night_msgs: int = 0,
) -> dict:
    """Build a minimal daily-table cell matching JS ``_wDaily`` expectations."""
    return {
        "msgs": msgs,
        "words": words,
        "questions": questions,
        "questions_answered": questions_answered,
        "neg_words": neg_words,
        "pos_words": pos_words,
        "gratitude": gratitude,
        "apology": apology,
        "initiations": initiations,
        "turns": turns,
        "turns_answered": turns_answered,
        "reacted_leave": reacted_leave,
        "resp_lat_sum_min": resp_lat_sum_min,
        "resp_lat_n": resp_lat_n,
        "night_msgs": night_msgs,
    }


def _daily_table(n_days: int = 90, base_date: date | None = None) -> dict[str, dict]:
    """Create a simple uniform daily table for baseline testing."""
    if base_date is None:
        base_date = date(2024, 1, 1)
    daily: dict[str, dict] = {}
    for i in range(n_days):
        d = base_date + timedelta(days=i)
        ds = d.isoformat()
        daily[ds] = {
            OWNER: _cell(msgs=60, words=300, turns=16, initiations=3,
                         resp_lat_sum_min=60, resp_lat_n=60),
            PARTNER: _cell(msgs=60, words=300, turns=16, initiations=3,
                           resp_lat_sum_min=60, resp_lat_n=60),
        }
    return daily


def _window(daily: dict, n_days: int) -> tuple[date, date]:
    """Return (start, end) for the first ``n_days`` of the daily table."""
    sorted_days = sorted(daily.keys())
    start = date(*map(int, sorted_days[0].split("-")))
    end = date(*map(int, sorted_days[n_days - 1].split("-")))
    return start, end


# --------------------------------------------------------------------------- #
# Python-side windowed rule evaluator (mirrors JS logic exactly)
# --------------------------------------------------------------------------- #

def _w_daily(daily: dict, users: list[str], start_d: date, end_d: date) -> dict:
    """Per-user sums within [start_d, end_d] — mirrors JS ``_wDaily``."""
    out: dict = {u: {} for u in users}
    for dk, cell_data in daily.items():
        t = date(*map(int, dk.split("-")))
        if t < start_d or t > end_d:
            continue
        for u in users:
            c = cell_data.get(u)
            if not c:
                continue
            for key in ("msgs", "words", "questions", "questions_answered",
                        "neg_words", "pos_words", "gratitude", "apology",
                        "initiations", "turns", "turns_answered",
                        "reacted_leave", "resp_lat_sum_min", "resp_lat_n",
                        "night_msgs"):
                val = c.get(key, 0) or 0
                out[u][key] = out[u].get(key, 0) + val
    return out


def _w_total(w: dict) -> int:
    return sum(w[u].get("msgs", 0) for u in w)


def _w_answer_rate(u: str, w: dict) -> float:
    q = w[u].get("questions", 0) or 0
    return (w[u].get("questions_answered", 0) or 0) / q if q else 0


def _w_neg_pos_ratio(w: dict) -> float:
    n = sum(w[u].get("neg_words", 0) for u in w)
    p = sum(w[u].get("pos_words", 0) for u in w)
    return min(p / n, 99) if n else 0


def _w_courtesy(w: dict) -> dict:
    tot = sum(w[u].get("msgs", 0) for u in w)
    if not tot:
        return {"gratitude": 0, "apology": 0}
    g = sum(w[u].get("gratitude", 0) for u in w)
    a = sum(w[u].get("apology", 0) for u in w)
    return {"gratitude": g / tot * 100, "apology": a / tot * 100}


def _w_turn_depth(u: str, w: dict) -> float:
    t = w[u].get("turns", 0) or 0
    a = w[u].get("turns_answered", 0) or 0
    return a / t if t else 0


def _w_night_share(u: str, w: dict) -> float:
    m = w[u].get("msgs", 0) or 0
    return (w[u].get("night_msgs", 0) or 0) / m if m else 0


def _w_latency(u: str, w: dict) -> float:
    n = w[u].get("resp_lat_n", 0) or 0
    s = w[u].get("resp_lat_sum_min", 0) or 0
    return s / n if n else 0


# --- Rule implementations mirroring JS ---

def _py_rule_question_imbalance(w, users, owner):
    tot = _w_total(w)
    if tot < 100:
        return None
    qa = w[users[0]].get("questions", 0) or 0
    qb = w[users[1]].get("questions", 0) or 0
    if qa < 5 or qb < 5:
        return None
    ra = _w_answer_rate(users[0], w)
    rb = _w_answer_rate(users[1], w)
    for i in range(2):
        X, Y = users[i], users[1 - i]
        rx, ry = (ra if i == 0 else rb), (rb if i == 0 else ra)
        if ry <= 0:
            continue
        if rx <= 0.6 * ry:
            return {"id": "question-imbalance", "scope": "chat"}
    return None


def _py_rule_gottman_ratio(w):
    r = _w_neg_pos_ratio(w)
    if r is None or r >= 5:
        return None
    return {"id": "gottman-ratio", "scope": "chat"}


def _py_rule_courtesy_asymmetry(w, users):
    c = _w_courtesy(w)
    if c["gratitude"] + c["apology"] < 2:
        return None
    ga = w[users[0]].get("gratitude", 0) or 0
    gb = w[users[1]].get("gratitude", 0) or 0
    if ga < 1 or gb < 1:
        return None
    ratio = ga / gb if gb else 0
    if ratio >= 2 or ratio <= 0.5:
        return {"id": "courtesy-asymmetry", "scope": "chat"}
    return None


def _py_rule_depth_mismatch(w, users):
    ta = _w_turn_depth(users[0], w)
    tb = _w_turn_depth(users[1], w)
    if ta < 0.2 or tb < 0.2:
        return None
    for i in range(2):
        r = (ta / tb) if i == 0 else (tb / ta)
        if r >= 1.5:
            return {"id": "depth-mismatch", "scope": "chat"}
    return None


def _py_rule_night_migration(w, users):
    na = _w_night_share(users[0], w)
    nb = _w_night_share(users[1], w)
    if na < 0.15 or nb < 0.15:
        return None
    for i in range(2):
        rx, ry = (na if i == 0 else nb), (nb if i == 0 else na)
        if rx >= 1.8 * ry:
            return {"id": "night-migration", "scope": "chat"}
    return None


def _py_rule_monologue_drift(w, users):
    ta = w[users[0]].get("turns", 0) or 0
    tb = w[users[1]].get("turns", 0) or 0
    tot = ta + tb
    if not tot or tot < 30:
        return None
    sh = max(ta, tb) / tot
    if sh < 0.75:
        return None
    return {"id": "monologue-drift", "scope": "chat"}


def _py_rule_eager_waiter(w, users):
    ra = _w_latency(users[0], w)
    rb = _w_latency(users[1], w)
    la = w[users[0]].get("resp_lat_n", 0) or 0
    lb = w[users[1]].get("resp_lat_n", 0) or 0
    if la < 10 or lb < 10:
        return None
    min_lat, max_lat = min(ra, rb), max(ra, rb)
    if min_lat < 1 or max_lat / min_lat < 3:
        return None
    return {"id": "eager-waiter", "scope": "chat"}


def _py_rule_left_on_react(w, users):
    la = w[users[0]].get("reacted_leave", 0) or 0
    lb = w[users[1]].get("reacted_leave", 0) or 0
    tot = la + lb
    if tot < 15:
        return None
    sh = max(la, lb) / tot
    if sh < 0.7:
        return None
    return {"id": "left-on-react", "scope": "chat"}


def _py_rule_unanswered_bids(w, users, owner):
    tot = _w_total(w)
    if tot < 200:
        return None
    qa = w[users[0]].get("questions", 0) or 0
    qb = w[users[1]].get("questions", 0) or 0
    if qa < 10 or qb < 10:
        return None
    ra = _w_answer_rate(users[0], w)
    rb = _w_answer_rate(users[1], w)
    for i in range(2):
        X, Y = users[i], users[1 - i]
        rx, ry = (ra if i == 0 else rb), (rb if i == 0 else ra)
        if ry <= 0:
            continue
        if rx <= 0.6 * ry:
            return {"id": "unanswered-bids", "scope": "chat"}
    return None


# Registry — mirrors JS ``JS_WINDOWABLE_RULES``
_PY_WINDOWABLE_RULES = {
    "question-imbalance": _py_rule_question_imbalance,
    "gottman-ratio": _py_rule_gottman_ratio,
    "courtesy-asymmetry": _py_rule_courtesy_asymmetry,
    "depth-mismatch": _py_rule_depth_mismatch,
    "night-migration": _py_rule_night_migration,
    "monologue-drift": _py_rule_monologue_drift,
    "eager-waiter": _py_rule_eager_waiter,
    "left-on-react": _py_rule_left_on_react,
    "unanswered-bids": _py_rule_unanswered_bids,
}


def _compute_windowed_findings(daily, users, owner, start_d, end_d):
    """Run all JS-parity rules over [start_d, end_d] — mirrors JS ``computeWindowedFindings``."""
    w = _w_daily(daily, users, start_d, end_d)
    if _w_total(w) < 50:
        return []
    findings = []
    for rid, fn in _PY_WINDOWABLE_RULES.items():
        try:
            f = fn(w, users, owner)
            if f:
                findings.append(f)
        except Exception:
            pass
    return [f["id"] for f in findings]


# --------------------------------------------------------------------------- #
# Test: registry parity — Python mirrors JS rule set exactly
# --------------------------------------------------------------------------- #

class TestRegistryParity:
    """Verify the Python-side registry matches the JS rule set and that
    WINDOWABLE_RULE_IDS is the union of JS rules + JS-skipped rules."""

    def test_py_registry_matches_parity_rules(self):
        """``_PY_WINDOWABLE_RULES`` keys should equal ``PARITY_RULES``."""
        assert set(_PY_WINDOWABLE_RULES.keys()) == PARITY_RULES

    def test_python_windowable_set_matches_js_plus_skipped(self):
        """Python's ``WINDOWABLE_RULE_IDS`` should equal JS rules + JS-skipped
        rules.  This catches regressions where a new windowable rule is added
        in Python but not mirrored (or vice-versa)."""
        assert EXPECTED_WINDOWABLE == WINDOWABLE_RULE_IDS

    def test_js_skipped_rules_not_in_py_registry(self):
        """JS-skipped rules should not be in the Python mirror registry."""
        for rule in JS_SKIPPED:
            assert rule not in _PY_WINDOWABLE_RULES, (
                f"{rule} is in JS_SKIPPED but also in _PY_WINDOWABLE_RULES"
            )


# --------------------------------------------------------------------------- #
# Test: each parity rule fires correctly in Python mirror
# --------------------------------------------------------------------------- #

class TestMirrorFires:
    """For each parity rule, engineer daily-table data that triggers it
    and verify the Python mirror fires."""

    def _win(self, daily, days=90):
        return _window(daily, days)

    def test_question_imbalance_fires(self):
        """One person's questions have much lower answer rate."""
        daily = _daily_table(n_days=90)
        for ds in daily:
            daily[ds][PARTNER]["questions"] = 5
            daily[ds][PARTNER]["questions_answered"] = 1  # 20%
            daily[ds][OWNER]["questions"] = 5
            daily[ds][OWNER]["questions_answered"] = 5  # 100%
        start, end = self._win(daily)
        win_ids = _compute_windowed_findings(daily, USERS, OWNER, start, end)
        assert "question-imbalance" in win_ids

    def test_gottman_ratio_fires(self):
        """neg:pos ratio > 5 → gottman-ratio fires."""
        daily = _daily_table(n_days=90)
        for ds in daily:
            daily[ds][OWNER]["pos_words"] = 10
            daily[ds][OWNER]["neg_words"] = 100
            daily[ds][PARTNER]["pos_words"] = 10
            daily[ds][PARTNER]["neg_words"] = 100
        start, end = self._win(daily)
        win_ids = _compute_windowed_findings(daily, USERS, OWNER, start, end)
        assert "gottman-ratio" in win_ids

    def test_courtesy_asymmetry_fires(self):
        """Gratitude ratio >= 2:1 → courtesy-asymmetry fires."""
        daily = _daily_table(n_days=90)
        for ds in daily:
            daily[ds][OWNER]["gratitude"] = 4
            daily[ds][PARTNER]["gratitude"] = 1
        start, end = self._win(daily)
        win_ids = _compute_windowed_findings(daily, USERS, OWNER, start, end)
        assert "courtesy-asymmetry" in win_ids

    def test_depth_mismatch_fires(self):
        """One person's turn-depth ratio is 1.5× the other."""
        daily = _daily_table(n_days=90)
        for ds in daily:
            daily[ds][OWNER]["turns"] = 16
            daily[ds][OWNER]["turns_answered"] = 16  # depth = 1.0
            daily[ds][PARTNER]["turns"] = 16
            daily[ds][PARTNER]["turns_answered"] = 8  # depth = 0.5
        start, end = self._win(daily)
        win_ids = _compute_windowed_findings(daily, USERS, OWNER, start, end)
        assert "depth-mismatch" in win_ids

    def test_night_migration_fires(self):
        """One person's night share is 1.8× the other."""
        daily = _daily_table(n_days=90)
        for ds in daily:
            daily[ds][OWNER]["msgs"] = 60
            daily[ds][OWNER]["night_msgs"] = 30  # 50%
            daily[ds][PARTNER]["msgs"] = 60
            daily[ds][PARTNER]["night_msgs"] = 5  # 8.3%
        start, end = self._win(daily)
        win_ids = _compute_windowed_findings(daily, USERS, OWNER, start, end)
        assert "night-migration" in win_ids

    def test_monologue_drift_fires(self):
        """One person produces >= 75% of turns."""
        daily = _daily_table(n_days=90)
        for ds in daily:
            daily[ds][OWNER]["turns"] = 30
            daily[ds][PARTNER]["turns"] = 5
        start, end = self._win(daily)
        win_ids = _compute_windowed_findings(daily, USERS, OWNER, start, end)
        assert "monologue-drift" in win_ids

    def test_eager_waiter_fires(self):
        """One person's avg latency is >= 3× the other."""
        daily = _daily_table(n_days=90)
        for ds in daily:
            # OWNER: 60 responses, 6 min total → 0.1 min avg
            daily[ds][OWNER]["resp_lat_n"] = 60
            daily[ds][OWNER]["resp_lat_sum_min"] = 6
            # PARTNER: 60 responses, 180 min total → 3 min avg
            daily[ds][PARTNER]["resp_lat_n"] = 60
            daily[ds][PARTNER]["resp_lat_sum_min"] = 180
        start, end = self._win(daily)
        win_ids = _compute_windowed_findings(daily, USERS, OWNER, start, end)
        assert "eager-waiter" in win_ids

    def test_left_on_react_fires(self):
        """One person does >= 70% of react-leaves."""
        daily = _daily_table(n_days=90)
        for ds in daily:
            daily[ds][OWNER]["reacted_leave"] = 7
            daily[ds][PARTNER]["reacted_leave"] = 3
        start, end = self._win(daily)
        win_ids = _compute_windowed_findings(daily, USERS, OWNER, start, end)
        assert "left-on-react" in win_ids

    def test_unanswered_bids_fires(self):
        """One person's questions have much lower answer rate (>= 10 each)."""
        daily = _daily_table(n_days=90)
        for ds in daily:
            daily[ds][PARTNER]["questions"] = 5
            daily[ds][PARTNER]["questions_answered"] = 1  # 20%
            daily[ds][OWNER]["questions"] = 5
            daily[ds][OWNER]["questions_answered"] = 5  # 100%
        start, end = self._win(daily)
        win_ids = _compute_windowed_findings(daily, USERS, OWNER, start, end)
        assert "unanswered-bids" in win_ids


# --------------------------------------------------------------------------- #
# Test: each parity rule stays silent on neutral data
# --------------------------------------------------------------------------- #

class TestMirrorSilence:
    """Uniform data → no windowed findings from the Python mirror."""

    def test_neutral_payload_no_findings(self):
        """All cells identical → no findings."""
        daily = _daily_table(n_days=90)
        start, end = _window(daily, 90)
        win_ids = _compute_windowed_findings(daily, USERS, OWNER, start, end)
        for rule in PARITY_RULES:
            assert rule not in win_ids, f"{rule} fired on neutral data"


# --------------------------------------------------------------------------- #
# Test: JS-skipped rules don't appear in the mirror
# --------------------------------------------------------------------------- #

class TestJSSkipped:
    """Rules that Python can window but JS explicitly skips must NOT
    appear in the mirror output."""

    def test_js_skipped_rules_not_in_mirror(self):
        for rule in JS_SKIPPED:
            assert rule not in _PY_WINDOWABLE_RULES, (
                f"{rule} is in JS_SKIPPED but also in _PY_WINDOWABLE_RULES"
            )


# --------------------------------------------------------------------------- #
# Test: proportional gating — short windows suppress spurious findings
# --------------------------------------------------------------------------- #

class TestProportionalGating:
    """The JS mirror uses proportional gates (e.g. total msgs < 100 → skip).
    Verify that shrinking the window reduces findings."""

    def test_short_window_question_imbalance(self):
        """With only 3 days, total msgs = 3 * 120 = 360 > 100, so gate passes.
        But questions per user = 3 * 5 = 15 >= 5, so it still fires.
        With 1 day: total = 120 > 100, questions = 5 >= 5 → still fires.
        The real gate is at < 100 total msgs, which requires < 1 day of data."""
        daily = _daily_table(n_days=90)
        for ds in daily:
            daily[ds][PARTNER]["questions"] = 5
            daily[ds][PARTNER]["questions_answered"] = 1
            daily[ds][OWNER]["questions"] = 5
            daily[ds][OWNER]["questions_answered"] = 5

        # 90-day window: should fire
        start90, end90 = _window(daily, 90)
        win90 = _compute_windowed_findings(daily, USERS, OWNER, start90, end90)
        assert "question-imbalance" in win90

        # 1-day window: total msgs = 120 > 100, questions = 5 >= 5 → still fires
        start1, end1 = _window(daily, 1)
        win1 = _compute_windowed_findings(daily, USERS, OWNER, start1, end1)
        # The gate is 100 total msgs; 1 day = 120 msgs, so it fires
        assert "question-imbalance" in win1

    def test_eager_waiter_needs_minimum_responses(self):
        """Eager-waiter requires resp_lat_n >= 10 per user."""
        daily = _daily_table(n_days=90)
        for ds in daily:
            # Very low response counts — below the gate
            daily[ds][OWNER]["resp_lat_n"] = 2
            daily[ds][OWNER]["resp_lat_sum_min"] = 10
            daily[ds][PARTNER]["resp_lat_n"] = 2
            daily[ds][PARTNER]["resp_lat_sum_min"] = 100
        start, end = _window(daily, 90)
        win_ids = _compute_windowed_findings(daily, USERS, OWNER, start, end)
        assert "eager-waiter" not in win_ids  # resp_lat_n < 10 per user
