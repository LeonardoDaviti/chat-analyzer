"""Python <-> JavaScript parity for the windowed findings engine.

Unlike the earlier version of this file (which tested a hand-copied Python
*mirror* of the JS against itself — parity theater), this module executes the
**actual** JS engine from ``src/dashboard_template.py``. The engine lives
between ``/* PARITY-BEGIN */`` and ``/* PARITY-END */`` markers; we extract that
block, run it under ``node`` against a synthetic daily table, and compare the
rule-ids it fires with what the real Python engine (``run_chat``) fires on the
same table — restricted to the set of rules the JS is supposed to mirror.

At the *full* range the JS proportional gate scale is 1, so the two engines must
agree exactly. The module skips cleanly when ``node`` is unavailable.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.insights_engine import WINDOWABLE_RULE_IDS, run_chat  # noqa: E402

TEMPLATE = ROOT / "src" / "dashboard_template.py"

# The rules the JS engine mirrors (== keys of JS_WINDOWABLE_RULES in the
# template; asserted below). Pure within-window daily-table aggregates.
PARITY_RULES = frozenset({
    "question-imbalance",
    "gottman-ratio",
    "courtesy-asymmetry",
    "media-reciprocity-gap",
    "depth-mismatch",
    "eager-waiter",
    "left-on-react",
    "unanswered-bids",
})

# Windowable in Python but intentionally NOT mirrored in JS (all-time only):
# half-of-life comparisons / weekly aggregates that are meaningless in a short
# sub-window. Verified as the complement of PARITY_RULES within WINDOWABLE.
JS_SKIPPED = frozenset({
    "monologue-drift", "night-migration", "we-ness-shift",
    "feast-and-famine", "steady-drumbeat",
})

OWNER = "B"
PARTNER = "A"
USERS = [PARTNER, OWNER]   # participants[0] is the busier sender, like real payloads

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not available")


# --------------------------------------------------------------------------- #
# Extract the JS engine block + its runner
# --------------------------------------------------------------------------- #

def _extract_parity_block() -> str:
    src = TEMPLATE.read_text(encoding="utf-8")
    a = src.index("/* PARITY-BEGIN")
    b = src.index("/* PARITY-END */") + len("/* PARITY-END */")
    return src[a:b]


PARITY_BLOCK = _extract_parity_block()

_RUNNER = """
var __block = require('fs').readFileSync(process.argv[1], 'utf8');
var vm = require('vm');
var sandbox = { console: { error: function(){}, log: function(){} } };
vm.runInNewContext(__block + '\\nthis.__cwf = computeWindowedFindings;'
                   + '\\nthis.__keys = Object.keys(JS_WINDOWABLE_RULES);', sandbox);
var input = '';
process.stdin.on('data', function(d){ input += d; });
process.stdin.on('end', function(){
  var p = JSON.parse(input);
  if (p.mode === 'keys') { process.stdout.write(JSON.stringify(sandbox.__keys)); return; }
  function toMs(s){ var a = s.split('-'); return Date.UTC(+a[0], +a[1]-1, +a[2]); }
  var out = sandbox.__cwf(p.daily, p.users, toMs(p.sd), toMs(p.ed),
                          toMs(p.fullStart), toMs(p.fullEnd));
  process.stdout.write(JSON.stringify(out.map(function(f){ return f.id; })));
});
"""


def _node(payload: dict):
    with_block = Path(_write_tmp())
    proc = subprocess.run(
        [NODE, "-e", _RUNNER, str(with_block)],
        input=json.dumps(payload), capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node failed: {proc.stderr}")
    return json.loads(proc.stdout)


_TMP_BLOCK = None


def _write_tmp() -> str:
    global _TMP_BLOCK
    if _TMP_BLOCK is None:
        import tempfile
        fd = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8")
        fd.write(PARITY_BLOCK)
        fd.close()
        _TMP_BLOCK = fd.name
    return _TMP_BLOCK


def _js_ids(daily, users, sd, ed, full_start, full_end):
    ids = _node({"daily": daily, "users": users, "sd": sd, "ed": ed,
                 "fullStart": full_start, "fullEnd": full_end})
    return set(ids) & PARITY_RULES


def _js_registry_keys():
    return set(_node({"mode": "keys"}))


# --------------------------------------------------------------------------- #
# Synthetic daily-table builder (shared by JS + Python sides)
# --------------------------------------------------------------------------- #

N_DAYS = 120
BASE = date(2024, 1, 1)


def _cell(**kw):
    base = {"msgs": 60, "words": 300, "turns": 16, "initiations": 1,
            "questions": 0, "questions_answered": 0,
            "pos_words": 0, "neg_words": 0, "gratitude": 0, "apology": 0,
            "photos": 0, "videos": 0, "voice": 0, "reacted_leave": 0,
            "wait_reply_sum_min": 0, "wait_reply_n": 0, "night_msgs": 0}
    base.update(kw)
    return base


def _table(a_over: dict, b_over: dict):
    """N_DAYS of daily cells; A gets a_over, B gets b_over (per-day values)."""
    daily = {}
    for i in range(N_DAYS):
        ds = (BASE + timedelta(days=i)).isoformat()
        daily[ds] = {PARTNER: _cell(**a_over), OWNER: _cell(**b_over)}
    return daily


def _full_range():
    return (BASE.isoformat(), (BASE + timedelta(days=N_DAYS - 1)).isoformat())


def _py_ids(daily):
    payload = {
        "name": "t", "platform": "instagram", "is_group": False,
        "participants": list(USERS), "daily": daily,
        "lifetime": {}, "extras": {}, "telegram": None, "change_points": [],
    }
    out = run_chat("t", payload, OWNER)
    return {f["id"] for f in out} & PARITY_RULES


def _assert_parity(daily, expect_fires):
    """JS and Python must agree (on the parity subset) at the full range, and
    the expected rule must be among what fires."""
    sd, ed = _full_range()
    js = _js_ids(daily, USERS, sd, ed, sd, ed)
    py = _py_ids(daily)
    assert js == py, f"JS {sorted(js)} != Python {sorted(py)}"
    assert expect_fires in js, f"{expect_fires} did not fire (got {sorted(js)})"


# --------------------------------------------------------------------------- #
# Registry parity
# --------------------------------------------------------------------------- #

class TestRegistryParity:
    def test_js_registry_matches_parity_rules(self):
        assert _js_registry_keys() == PARITY_RULES

    def test_parity_rules_are_windowable_in_python(self):
        assert PARITY_RULES <= WINDOWABLE_RULE_IDS

    def test_skipped_is_windowable_complement(self):
        assert JS_SKIPPED == (WINDOWABLE_RULE_IDS - PARITY_RULES)


# --------------------------------------------------------------------------- #
# Per-rule firing parity (JS executed under node == Python engine)
# --------------------------------------------------------------------------- #

class TestFiringParity:
    def test_question_imbalance(self):
        # A asks a lot (0.25) and B little (0.05); answer rates kept equal so
        # unanswered-bids does NOT fire (isolates asking-rate).
        daily = _table(a_over={"questions": 25, "questions_answered": 20, "words": 600},
                       b_over={"questions": 5, "questions_answered": 4, "words": 180})
        _assert_parity(daily, "question-imbalance")

    def test_unanswered_bids(self):
        # Equal asking rate, but A's questions answered far less than B's.
        daily = _table(a_over={"questions": 10, "questions_answered": 2},
                       b_over={"questions": 10, "questions_answered": 9})
        _assert_parity(daily, "unanswered-bids")

    def test_gottman_ratio(self):
        daily = _table(a_over={"pos_words": 10, "neg_words": 100},
                       b_over={"pos_words": 10, "neg_words": 100})
        _assert_parity(daily, "gottman-ratio")

    def test_courtesy_asymmetry(self):
        daily = _table(a_over={"msgs": 100, "gratitude": 5, "apology": 1},
                       b_over={"msgs": 100, "gratitude": 1, "apology": 0})
        _assert_parity(daily, "courtesy-asymmetry")

    def test_media_reciprocity_gap(self):
        daily = _table(a_over={"photos": 4, "voice": 1},
                       b_over={"photos": 1})
        _assert_parity(daily, "media-reciprocity-gap")

    def test_depth_mismatch(self):
        # A ~10 wpt, B ~3 wpt, stable across both halves; sessions >= 60.
        daily = _table(a_over={"words": 160, "turns": 16, "initiations": 1},
                       b_over={"words": 48, "turns": 16, "initiations": 1})
        _assert_parity(daily, "depth-mismatch")

    def test_eager_waiter(self):
        daily = _table(a_over={"wait_reply_n": 2, "wait_reply_sum_min": 60},   # 30 min
                       b_over={"wait_reply_n": 2, "wait_reply_sum_min": 4})    # 2 min
        _assert_parity(daily, "eager-waiter")

    def test_left_on_react(self):
        daily = _table(a_over={"reacted_leave": 5}, b_over={"reacted_leave": 1})
        _assert_parity(daily, "left-on-react")


# --------------------------------------------------------------------------- #
# Silence parity — neutral data fires nothing on either side
# --------------------------------------------------------------------------- #

class TestSilenceParity:
    def test_neutral_table(self):
        daily = _table(a_over={}, b_over={})
        sd, ed = _full_range()
        assert _js_ids(daily, USERS, sd, ed, sd, ed) == set()
        assert _py_ids(daily) == set()


# --------------------------------------------------------------------------- #
# Full range vs narrow window (JS-only): scaling floors don't invent findings
# --------------------------------------------------------------------------- #

class TestProportionalGating:
    def test_narrow_window_does_not_exceed_full(self):
        # left-on-react needs reacted_leave sum >= 40 (scaled). A big asymmetric
        # chat fires it at full range; a very short window has too few events
        # even after the 25% floor.
        daily = _table(a_over={"reacted_leave": 1}, b_over={"reacted_leave": 0})
        sd, ed = _full_range()
        full = _js_ids(daily, USERS, sd, ed, sd, ed)
        # 3-day window: 3 react-leaves vs a scaled gate (>= 10 = 40*0.25) -> silent
        narrow_end = (BASE + timedelta(days=2)).isoformat()
        narrow = _js_ids(daily, USERS, sd, narrow_end, sd, ed)
        assert "left-on-react" not in narrow
        assert narrow <= full


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
