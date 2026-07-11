"""Tier 1 Insights engine tests — synthetic payloads only.

Every rule has a *trigger* test (fires on data engineered to match it) and a
*gate* test (a small tweak drops it below the gate → not emitted). Plus
determinism, ``</script>`` escaping, and missing-connected-file behaviour.

No real data, no message content — all payloads are hand-built aggregates.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.insights_engine import (  # noqa: E402
    _SUM_FIELDS, run_chat, run_connected,
)

OWNER = 'B'          # owner display name in chat payloads
PARTNER = 'A'


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #

def cell(**kw):
    c = {f: 0 for f in _SUM_FIELDS}
    c['hours'] = [0] * 24
    for k, v in kw.items():
        if k == 'hours':
            c['hours'] = v
        else:
            c[k] = v
    return c


def month_dates(n, start_year=2024, start_month=1):
    out = []
    y, m = start_year, start_month
    for _ in range(n):
        out.append(f'{y:04d}-{m:02d}-15')
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def chat_payload(daily, participants=(PARTNER, OWNER), platform='instagram',
                 lifetime=None, extras=None, telegram=None, change_points=None):
    return {
        'name': 'test', 'platform': platform, 'is_group': False,
        'participants': list(participants),
        'daily': daily,
        'lifetime': lifetime or {},
        'extras': extras or {},
        'telegram': telegram,
        'change_points': change_points or [],
    }


def spread(n_months, a_fn, b_fn, start_year=2024):
    """Build a daily table of ``n_months`` monthly cells.

    ``a_fn(i)`` / ``b_fn(i)`` return field dicts for month index i for the
    partner (A) and owner (B) respectively.
    """
    daily = {}
    for i, d in enumerate(month_dates(n_months, start_year)):
        daily[d] = {PARTNER: cell(**a_fn(i)), OWNER: cell(**b_fn(i))}
    return daily


def ids(findings):
    return {f['id'] for f in findings}


def _run(payload):
    return run_chat('t', payload, OWNER)


# --------------------------------------------------------------------------- #
# a baseline chat that clears the global gate but triggers nothing special
# --------------------------------------------------------------------------- #

def baseline_daily(n_months=12, msgs_each=60, init_each=6):
    return spread(
        n_months,
        lambda i: {'msgs': msgs_each, 'words': msgs_each * 5, 'turns': msgs_each,
                   'initiations': init_each, 'resp_lat_sum_min': 60,
                   'resp_lat_n': 60},
        lambda i: {'msgs': msgs_each, 'words': msgs_each * 5, 'turns': msgs_each,
                   'initiations': init_each, 'resp_lat_sum_min': 60,
                   'resp_lat_n': 60},
    )


def test_global_gate_below_500_msgs_no_findings():
    daily = spread(2, lambda i: {'msgs': 50, 'initiations': 5},
                   lambda i: {'msgs': 50, 'initiations': 5})
    assert _run(chat_payload(daily)) == []


def test_group_chats_skipped():
    p = chat_payload(baseline_daily())
    p['is_group'] = True
    assert run_chat('g', p, OWNER) == []


def test_baseline_only_gets_fun_records():
    # No change points, symmetric — should yield at most session-records.
    out = _run(chat_payload(baseline_daily()))
    assert 'session-records' in ids(out)
    assert 'asymmetric-pursuit' not in ids(out)


# --------------------------------------------------------------------------- #
# 1. asymmetric-pursuit
# --------------------------------------------------------------------------- #

def _pursuit_payload(share_a=0.70):
    daily = baseline_daily()
    lifetime = {
        'initiation': {PARTNER: {'initiation_share': share_a},
                       OWNER: {'initiation_share': 1 - share_a}},
        'response_times': {'my_median_response_minutes': 5.0,
                           'partner_median_response_minutes': 1.0},
    }
    return chat_payload(daily, lifetime=lifetime)


def test_asymmetric_pursuit_triggers():
    out = _run(_pursuit_payload(0.72))
    assert 'asymmetric-pursuit' in ids(out)


def test_asymmetric_pursuit_gate_low_share():
    out = _run(_pursuit_payload(0.52))
    assert 'asymmetric-pursuit' not in ids(out)


# --------------------------------------------------------------------------- #
# 2. pursuit-withdrawal-trend
# --------------------------------------------------------------------------- #

def _pw_daily(n_months=12):
    def a(i):
        return {'msgs': 60, 'initiations': 2 if i < 6 else 8}
    def b(i):
        n = 30
        return {'msgs': 60, 'initiations': 8 if i < 6 else 2,
                'resp_lat_n': n, 'resp_lat_sum_min': (30 if i < 6 else 90)}
    return spread(n_months, a, b)


def test_pursuit_withdrawal_triggers():
    out = _run(chat_payload(_pw_daily(12)))
    assert 'pursuit-withdrawal-trend' in ids(out)


def test_pursuit_withdrawal_gate_short_window():
    out = _run(chat_payload(_pw_daily(6)))
    assert 'pursuit-withdrawal-trend' not in ids(out)


# --------------------------------------------------------------------------- #
# 3. regime-change-story
# --------------------------------------------------------------------------- #

def test_regime_change_triggers():
    cp = [{'date': '2024-06-01', 'signals': [
        {'metric': 'volume', 'direction': 'up', 'magnitude': 6.0},
        {'metric': 'response_latency', 'direction': 'up', 'magnitude': 3.0}]}]
    out = _run(chat_payload(baseline_daily(), change_points=cp))
    assert 'regime-change-story' in ids(out)


def test_regime_change_gate_no_change_points():
    out = _run(chat_payload(baseline_daily(), change_points=[]))
    assert 'regime-change-story' not in ids(out)


# --------------------------------------------------------------------------- #
# 4. cooling / warming
# --------------------------------------------------------------------------- #

def _cooling_daily(cool=True):
    # 12 months; last 3 far below the prior 6 (cooling) or above (warming).
    # Prior window must carry some variance (else std==0 and z is undefined).
    def a(i):
        base = 80 + (i % 3) * 8   # 80/88/96 wobble in the prior window
        depth = 5 + (i % 2)       # words/turn wobbles 5..6 so std>0
        sess = 6 + (i % 3)        # sessions wobble so std>0
        if i >= 9:
            base = 5 if cool else 500
            depth = 2 if cool else 12
            sess = 1 if cool else 20
        return {'msgs': base, 'words': base * depth, 'turns': base,
                'initiations': sess}
    return spread(12, a, a)


def test_cooling_triggers():
    out = _run(chat_payload(_cooling_daily(cool=True)))
    assert 'cooling-warming' in ids(out)


def test_cooling_gate_short_window():
    daily = spread(6, lambda i: {'msgs': 90, 'words': 450, 'turns': 90,
                                 'initiations': 6},
                   lambda i: {'msgs': 90, 'words': 450, 'turns': 90,
                              'initiations': 6})
    out = _run(chat_payload(daily))
    assert 'cooling-warming' not in ids(out)


# --------------------------------------------------------------------------- #
# 5. ending-restart-loop
# --------------------------------------------------------------------------- #

def _endloop_payload(fw_share=0.7, restart_share=0.7):
    daily = spread(
        12,
        lambda i: {'msgs': 60, 'endings': 5,
                   'self_restarts': int(30 * (1 - restart_share) / 12 * 12) // 12 or 0},
        lambda i: {'msgs': 60, 'endings': 5})
    # set explicit restart totals: X=OWNER should do restart_share of restarts
    # simpler: rebuild with concrete per-month restarts
    daily = {}
    for i, d in enumerate(month_dates(12)):
        daily[d] = {
            PARTNER: cell(msgs=60, endings=5, self_restarts=3),   # A restarts=36
            OWNER: cell(msgs=60, endings=5, self_restarts=7),     # B restarts=84 -> 0.7
        }
    lifetime = {'final_word_dominance': {PARTNER: fw_share, OWNER: 1 - fw_share}}
    return chat_payload(daily, lifetime=lifetime)


def test_ending_restart_loop_triggers():
    out = _run(_endloop_payload(fw_share=0.7))
    assert 'ending-restart-loop' in ids(out)


def test_ending_restart_loop_gate_no_dominance():
    out = _run(_endloop_payload(fw_share=0.5))
    assert 'ending-restart-loop' not in ids(out)


# --------------------------------------------------------------------------- #
# 6. left-on-react
# --------------------------------------------------------------------------- #

def test_left_on_react_triggers():
    daily = {}
    for d in month_dates(12):
        daily[d] = {PARTNER: cell(msgs=60, reacted_leave=5),   # A=60
                    OWNER: cell(msgs=60, reacted_leave=1)}      # B=12
    out = _run(chat_payload(daily))
    assert 'left-on-react' in ids(out)


def test_left_on_react_gate_balanced():
    daily = {}
    for d in month_dates(12):
        daily[d] = {PARTNER: cell(msgs=60, reacted_leave=3),
                    OWNER: cell(msgs=60, reacted_leave=3)}
    out = _run(chat_payload(daily))
    assert 'left-on-react' not in ids(out)


# --------------------------------------------------------------------------- #
# 7. eager-waiter
# --------------------------------------------------------------------------- #

def test_eager_waiter_triggers():
    daily = {}
    for d in month_dates(12):
        daily[d] = {
            PARTNER: cell(msgs=60, wait_reply_n=5, wait_reply_sum_min=150),  # mean 30
            OWNER: cell(msgs=60, wait_reply_n=5, wait_reply_sum_min=10),     # mean 2
        }
    out = _run(chat_payload(daily))
    assert 'eager-waiter' in ids(out)


def test_eager_waiter_gate_low_n():
    daily = {}
    for d in month_dates(2):
        daily[d] = {PARTNER: cell(msgs=300, wait_reply_n=2, wait_reply_sum_min=60),
                    OWNER: cell(msgs=300, wait_reply_n=2, wait_reply_sum_min=4)}
    out = _run(chat_payload(daily))
    assert 'eager-waiter' not in ids(out)


# --------------------------------------------------------------------------- #
# 8. question-imbalance
# --------------------------------------------------------------------------- #

def test_question_imbalance_triggers():
    daily = {}
    for d in month_dates(12):
        daily[d] = {PARTNER: cell(msgs=100, questions=20),   # 0.20
                    OWNER: cell(msgs=100, questions=5)}       # 0.05
    out = _run(chat_payload(daily))
    assert 'question-imbalance' in ids(out)


def test_question_imbalance_gate_balanced():
    daily = {}
    for d in month_dates(12):
        daily[d] = {PARTNER: cell(msgs=100, questions=10),
                    OWNER: cell(msgs=100, questions=9)}
    out = _run(chat_payload(daily))
    assert 'question-imbalance' not in ids(out)


# --------------------------------------------------------------------------- #
# 9. monologue-drift
# --------------------------------------------------------------------------- #

def test_monologue_drift_triggers():
    # turns/msg falls hard between halves (more monologue)
    def side(i):
        if i < 6:
            return {'msgs': 60, 'turns': 60}     # di=1.0
        return {'msgs': 60, 'turns': 24}         # di=0.4 -> drop 0.6
    out = _run(chat_payload(spread(12, side, side)))
    assert 'monologue-drift' in ids(out)


def test_monologue_drift_gate_stable():
    def side(i):
        return {'msgs': 60, 'turns': 58}
    out = _run(chat_payload(spread(12, side, side)))
    assert 'monologue-drift' not in ids(out)


# --------------------------------------------------------------------------- #
# 10. depth-mismatch
# --------------------------------------------------------------------------- #

def test_depth_mismatch_triggers():
    def a(i):
        return {'msgs': 60, 'turns': 60, 'words': 60 * 10, 'initiations': 6}  # 10 wpt
    def b(i):
        return {'msgs': 60, 'turns': 60, 'words': 60 * 3, 'initiations': 6}   # 3 wpt
    out = _run(chat_payload(spread(12, a, b)))
    assert 'depth-mismatch' in ids(out)


def test_depth_mismatch_gate_similar():
    def side(i):
        return {'msgs': 60, 'turns': 60, 'words': 60 * 5, 'initiations': 6}
    out = _run(chat_payload(spread(12, side, side)))
    assert 'depth-mismatch' not in ids(out)


# --------------------------------------------------------------------------- #
# 11. gottman-ratio
# --------------------------------------------------------------------------- #

def test_gottman_ratio_below_triggers():
    daily = {}
    for d in month_dates(12):
        daily[d] = {PARTNER: cell(msgs=60, pos_words=10, neg_words=8),
                    OWNER: cell(msgs=60, pos_words=10, neg_words=8)}
    out = _run(chat_payload(daily))
    assert 'gottman-ratio' in ids(out)   # ratio ~1.25 < 5


def test_gottman_ratio_healthy_band_silent():
    daily = {}
    for d in month_dates(12):
        # ratio 6:1 → inside 5..8 healthy band → nothing
        daily[d] = {PARTNER: cell(msgs=60, pos_words=30, neg_words=5),
                    OWNER: cell(msgs=60, pos_words=30, neg_words=5)}
    out = _run(chat_payload(daily))
    assert 'gottman-ratio' not in ids(out)


# --------------------------------------------------------------------------- #
# 12. we-ness-shift
# --------------------------------------------------------------------------- #

def test_we_ness_shift_triggers():
    def side(i):
        if i < 6:
            return {'msgs': 60, 'we_words': 5, 'i_words': 45}    # 0.10
        return {'msgs': 60, 'we_words': 25, 'i_words': 25}       # 0.50
    out = _run(chat_payload(spread(12, side, side)))
    assert 'we-ness-shift' in ids(out)


def test_we_ness_shift_gate_stable():
    def side(i):
        return {'msgs': 60, 'we_words': 20, 'i_words': 30}
    out = _run(chat_payload(spread(12, side, side)))
    assert 'we-ness-shift' not in ids(out)


# --------------------------------------------------------------------------- #
# 13. style-mirror
# --------------------------------------------------------------------------- #

def test_style_mirror_triggers_sustained():
    extras = {'lsm_monthly': {m: 0.90 for m in
                              ['2024-0%d' % i for i in range(1, 9)]}}
    out = _run(chat_payload(baseline_daily(), extras=extras))
    assert 'style-mirror' in ids(out)


def test_style_mirror_gate_low_and_flat():
    extras = {'lsm_monthly': {m: 0.5 for m in
                              ['2024-0%d' % i for i in range(1, 9)]}}
    out = _run(chat_payload(baseline_daily(), extras=extras))
    assert 'style-mirror' not in ids(out)


# --------------------------------------------------------------------------- #
# 14. courtesy-asymmetry
# --------------------------------------------------------------------------- #

def test_courtesy_asymmetry_triggers():
    daily = {}
    for d in month_dates(12):
        daily[d] = {PARTNER: cell(msgs=100, gratitude=4, apology=1),   # rate .05
                    OWNER: cell(msgs=100, gratitude=1, apology=0)}      # rate .01
    out = _run(chat_payload(daily))
    assert 'courtesy-asymmetry' in ids(out)


def test_courtesy_asymmetry_gate_balanced():
    daily = {}
    for d in month_dates(12):
        daily[d] = {PARTNER: cell(msgs=100, gratitude=2, apology=1),
                    OWNER: cell(msgs=100, gratitude=2, apology=1)}
    out = _run(chat_payload(daily))
    assert 'courtesy-asymmetry' not in ids(out)


# --------------------------------------------------------------------------- #
# 15. tg-second-guessing  (telegram-only, structurally gated)
# --------------------------------------------------------------------------- #

def _tg_payload(edit_a=0.20, edit_b=0.05, with_block=True):
    daily = baseline_daily()
    tg = None
    if with_block:
        tg = {'per_user': {PARTNER: {'msgs': 300, 'edit_rate': edit_a},
                           OWNER: {'msgs': 300, 'edit_rate': edit_b}}}
    return chat_payload(daily, platform='telegram', telegram=tg)


def test_tg_second_guessing_triggers():
    out = _run(_tg_payload(edit_a=0.20, edit_b=0.05))
    assert 'tg-second-guessing' in ids(out)


def test_tg_second_guessing_gate_no_telegram_block():
    # Instagram chat: no telegram block → structurally never fires.
    out = _run(_tg_payload(edit_a=0.20, edit_b=0.05, with_block=False))
    assert 'tg-second-guessing' not in ids(out)


# --------------------------------------------------------------------------- #
# 16. night-migration
# --------------------------------------------------------------------------- #

def _night_hours(n):
    h = [0] * 24
    h[1] = n  # all in the 00-06 band
    return h


def test_night_migration_triggers():
    def h1_hours():
        h = [0] * 24
        h[1] = 2            # a little night (s1 > 0, needed to "double")
        h[13] = 58          # mostly daytime
        return h
    def side(i):
        if i < 6:
            return {'msgs': 60, 'hours': h1_hours()}   # ~3% night
        return {'msgs': 60, 'hours': _night_hours(40)}  # heavy night
    out = _run(chat_payload(spread(12, side, side)))
    assert 'night-migration' in ids(out)


def test_night_migration_gate_stable():
    def side(i):
        return {'msgs': 60, 'hours': [0] * 12 + [5] * 12}
    out = _run(chat_payload(spread(12, side, side)))
    assert 'night-migration' not in ids(out)


# --------------------------------------------------------------------------- #
# 17. session-records  (always, fun)
# --------------------------------------------------------------------------- #

def test_session_records_always_present():
    out = _run(chat_payload(baseline_daily()))
    assert 'session-records' in ids(out)


# --------------------------------------------------------------------------- #
# 18. media-reciprocity-gap
# --------------------------------------------------------------------------- #

def test_media_reciprocity_gap_triggers():
    daily = {}
    for d in month_dates(12):
        daily[d] = {PARTNER: cell(msgs=60, photos=4, voice=1),   # 60 media
                    OWNER: cell(msgs=60, photos=1)}               # 12 media
    out = _run(chat_payload(daily))
    assert 'media-reciprocity-gap' in ids(out)


def test_media_reciprocity_gap_gate_balanced():
    daily = {}
    for d in month_dates(12):
        daily[d] = {PARTNER: cell(msgs=60, photos=3),
                    OWNER: cell(msgs=60, photos=3)}
    out = _run(chat_payload(daily))
    assert 'media-reciprocity-gap' not in ids(out)


# --------------------------------------------------------------------------- #
# Connected rules
# --------------------------------------------------------------------------- #

def conn_base(**over):
    p = {
        'owner': OWNER, 'variant': 'all',
        'range': {'first_day': '2024-01-01', 'last_day': '2024-12-31'},
        'daily': {}, 'monthly': {}, 'attention': {}, 'contacts': [],
        'leaderboards': {}, 'code_switching': {'per_contact': []},
        'funnel': {}, 'totals': {},
    }
    p.update(over)
    return p


def conn_ids(findings):
    return {f['id'] for f in findings}


# 20. attention-volume-mismatch
def test_attention_volume_mismatch_triggers():
    p = conn_base(leaderboards={
        'attention_hierarchy': [{'name': 'Fastfriend',
                                 'reply_latency_median_min': 0.5, 'reply_n': 200}],
        'by_sent_share': [{'name': 'X%d' % i} for i in range(5)]})
    assert 'attention-volume-mismatch' in conn_ids(run_connected(p))


def test_attention_volume_mismatch_gate_in_top5():
    p = conn_base(leaderboards={
        'attention_hierarchy': [{'name': 'Loud',
                                 'reply_latency_median_min': 0.5, 'reply_n': 200}],
        'by_sent_share': [{'name': 'Loud'}] + [{'name': 'X%d' % i} for i in range(4)]})
    assert 'attention-volume-mismatch' not in conn_ids(run_connected(p))


# 21. concentration-trend
def test_concentration_trend_triggers():
    months = month_dates(12)
    gini = {m[:7]: 0.3 + 0.02 * i for i, m in enumerate(months)}
    p = conn_base(monthly={'gini': gini},
                  contacts=[{'name': 'c%d' % i} for i in range(12)])
    assert 'concentration-trend' in conn_ids(run_connected(p))


def test_concentration_trend_gate_flat():
    months = month_dates(12)
    gini = {m[:7]: 0.30 for m in months}
    p = conn_base(monthly={'gini': gini},
                  contacts=[{'name': 'c%d' % i} for i in range(12)])
    assert 'concentration-trend' not in conn_ids(run_connected(p))


# 22. span-trend
def test_span_trend_triggers():
    months = month_dates(24)
    bursts = {}
    for i, m in enumerate(months):
        bursts[m[:7]] = {'median_min': 10 if i < 12 else 20}
    p = conn_base(monthly={'bursts': bursts})
    assert 'span-trend' in conn_ids(run_connected(p))


def test_span_trend_gate_stable():
    months = month_dates(24)
    bursts = {m[:7]: {'median_min': 10} for m in months}
    p = conn_base(monthly={'bursts': bursts})
    assert 'span-trend' not in conn_ids(run_connected(p))


# 23. churn-wave
def test_churn_wave_triggers():
    churned = {m[:7]: 2 for m in month_dates(12)}
    churned['2024-06'] = 20
    p = conn_base(monthly={'churned': churned})
    assert 'churn-wave' in conn_ids(run_connected(p))


def test_churn_wave_gate_flat():
    churned = {m[:7]: 3 for m in month_dates(12)}
    p = conn_base(monthly={'churned': churned})
    assert 'churn-wave' not in conn_ids(run_connected(p))


# 24. funnel-readout
def test_funnel_readout_triggers():
    p = conn_base(funnel={'stages': {'met': 50, 'recurring': 20}})
    assert 'funnel-readout' in conn_ids(run_connected(p))


def test_funnel_readout_gate_too_few():
    p = conn_base(funnel={'stages': {'met': 5, 'recurring': 2}})
    assert 'funnel-readout' not in conn_ids(run_connected(p))


# 25. night-court
def test_night_court_triggers():
    p = conn_base(leaderboards={'night': [
        {'name': 'Owl', 'night_share': 0.7, 'night_msgs': 300},
        {'name': 'Other', 'night_share': 0.3, 'night_msgs': 100}]})
    assert 'night-court' in conn_ids(run_connected(p))


def test_night_court_gate_spread():
    p = conn_base(leaderboards={'night': [
        {'name': 'A', 'night_share': 0.3, 'night_msgs': 150},
        {'name': 'B', 'night_share': 0.3, 'night_msgs': 150}]})
    assert 'night-court' not in conn_ids(run_connected(p))


# 26. initiator-persona
def test_initiator_persona_triggers():
    contacts = [{'name': 'c%d' % i, 'sessions': 10, 'initiation_share': 0.8}
                for i in range(12)]
    p = conn_base(contacts=contacts)
    assert 'initiator-persona' in conn_ids(run_connected(p))


def test_initiator_persona_gate_mixed():
    contacts = [{'name': 'c%d' % i, 'sessions': 10,
                 'initiation_share': 0.8 if i % 2 else 0.2} for i in range(12)]
    p = conn_base(contacts=contacts)
    assert 'initiator-persona' not in conn_ids(run_connected(p))


# 27. reciprocity-debts
def test_reciprocity_debts_triggers():
    p = conn_base(leaderboards={
        'reciprocity_surplus': [{'name': 'Owed', 'reciprocity': 3.0,
                                 'sent': 300, 'received': 100}],
        'reciprocity_deficit': []})
    assert 'reciprocity-debts' in conn_ids(run_connected(p))


def test_reciprocity_debts_gate_balanced():
    p = conn_base(leaderboards={
        'reciprocity_surplus': [{'name': 'Even', 'reciprocity': 1.05,
                                 'sent': 205, 'received': 195}],
        'reciprocity_deficit': []})
    assert 'reciprocity-debts' not in conn_ids(run_connected(p))


# 28. deep-talk-budget
def test_deep_talk_budget_triggers():
    contacts = [{'name': 'Deep', 'session_types': {'deep_talk': 40}},
                {'name': 'Also', 'session_types': {'deep_talk': 5}},
                {'name': 'Bit', 'session_types': {'deep_talk': 5}}]
    assert 'deep-talk-budget' in conn_ids(run_connected(conn_base(contacts=contacts)))


def test_deep_talk_budget_gate_spread():
    contacts = [{'name': 'c%d' % i, 'session_types': {'deep_talk': 8}}
                for i in range(8)]
    assert 'deep-talk-budget' not in conn_ids(run_connected(conn_base(contacts=contacts)))


# 29. chameleon-index
def test_chameleon_index_triggers():
    per = [{'name': 'c%d' % i, 'emoji_rate': 0.01 * i,
            'avg_word_len': 4 + i,
            'lang_mix': {'georgian': (i % 2), 'english': 1 - (i % 2), 'mixed': 0}}
           for i in range(10)]
    p = conn_base(code_switching={'per_contact': per, 'lang_variance': 0.10,
                                  'emoji_rate_variance': 0.01})
    assert 'chameleon-index' in conn_ids(run_connected(p))


def test_chameleon_index_gate_low_variance():
    per = [{'name': 'c%d' % i, 'emoji_rate': 0.01, 'avg_word_len': 4,
            'lang_mix': {'georgian': 0.5, 'english': 0.5, 'mixed': 0}}
           for i in range(10)]
    p = conn_base(code_switching={'per_contact': per, 'lang_variance': 0.001,
                                  'emoji_rate_variance': 0.0001})
    assert 'chameleon-index' not in conn_ids(run_connected(p))


# 19/30. cross-platform rules (need ig + tg)
def _platform_variant(parallel, emoji_rate, msgs=8000):
    words = msgs * 5
    daily = {'2024-01-15': {'msgs': msgs, 'words': words,
                            'emoji': int(emoji_rate * words), 'hours': [0] * 24}}
    return conn_base(
        totals={'messages_sent': msgs},
        attention={'parallel_texting_rate': parallel},
        daily=daily,
        range={'first_day': '2024-01-01', 'last_day': '2024-12-31'})


def test_platform_focus_triggers():
    ig = _platform_variant(parallel=0.30, emoji_rate=0.02)
    tg = _platform_variant(parallel=0.05, emoji_rate=0.02)
    out = run_connected(conn_base(), ig=ig, tg=tg)
    assert 'platform-focus' in conn_ids(out)


def test_platform_focus_gate_similar():
    ig = _platform_variant(parallel=0.10, emoji_rate=0.02)
    tg = _platform_variant(parallel=0.09, emoji_rate=0.02)
    out = run_connected(conn_base(), ig=ig, tg=tg)
    assert 'platform-focus' not in conn_ids(out)


def test_platform_persona_triggers():
    ig = _platform_variant(parallel=0.1, emoji_rate=0.10)
    tg = _platform_variant(parallel=0.1, emoji_rate=0.01)
    out = run_connected(conn_base(), ig=ig, tg=tg)
    assert 'platform-persona' in conn_ids(out)


def test_cross_platform_gated_without_both():
    ig = _platform_variant(parallel=0.30, emoji_rate=0.10)
    out = run_connected(conn_base(), ig=ig, tg=None)
    assert 'platform-focus' not in conn_ids(out)
    assert 'platform-persona' not in conn_ids(out)


# --------------------------------------------------------------------------- #
# engine invariants: determinism, ranking, cap
# --------------------------------------------------------------------------- #

def test_determinism_identical_runs():
    p = _pursuit_payload(0.72)
    a = _run(p)
    b = _run(p)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_findings_sorted_by_score_desc():
    cp = [{'date': '2024-06-01', 'signals': [
        {'metric': 'volume', 'direction': 'up', 'magnitude': 6.0}]}]
    out = _run(_pursuit_payload_with_cp(cp))
    scores = [f['score'] for f in out]
    assert scores == sorted(scores, reverse=True)


def _pursuit_payload_with_cp(cp):
    p = _pursuit_payload(0.72)
    p['change_points'] = cp
    return p


def test_chat_cap_enforced():
    from src import insights_engine as ie
    fake = [{'id': 'r%d' % i, 'score': i / 100.0, 'chat_id': 't'}
            for i in range(20)]
    capped = ie._rank_and_cap(fake, ie.CHAT_CAP)
    assert len(capped) == ie.CHAT_CAP


# --------------------------------------------------------------------------- #
# build_insights.py — escaping + missing-connected-file behaviour
# --------------------------------------------------------------------------- #

def test_script_escaping_in_dump():
    import build_insights
    payload = {'x': [{'sentence': 'evil </script> tag',
                      'name': '</SCRIPT foo'}]}
    js = build_insights.dump_insights_js(payload)
    assert '</script' not in js
    assert '</SCRIPT' not in js
    assert '<\\/script' in js


def _write_chat_js(data_dir, slug, payload):
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    (data_dir / f'{slug}.js').write_text(
        'window.DASHBOARD_DATA = window.DASHBOARD_DATA || {};\n'
        f'window.DASHBOARD_DATA[{json.dumps(slug)}] = {body};\n',
        encoding='utf-8')


def _write_manifest(data_dir, entries):
    body = json.dumps(entries, ensure_ascii=False, separators=(',', ':'))
    (data_dir / 'manifest.js').write_text(
        f'window.DASHBOARD_MANIFEST = {body};\n', encoding='utf-8')


def test_build_insights_without_connected(tmp_path):
    import build_insights
    data = tmp_path / 'data'
    data.mkdir(parents=True)
    p = _pursuit_payload(0.72)
    p['name'] = 'chatA'
    _write_chat_js(data, 'chatA', p)
    _write_manifest(data, [{'id': 'chatA', 'name': 'chatA',
                            'file': 'data/chatA.js', 'is_group': False,
                            'platform': 'instagram'}])
    rc = build_insights.main(['--dash-dir', str(tmp_path)])
    assert rc == 0
    out = json.loads((data / 'insights.json').read_text(encoding='utf-8'))
    assert 'chatA' in out
    assert 'connected' not in out          # no connected files present
    assert (data / 'insights.js').exists()


def test_build_insights_connected_only(tmp_path):
    import build_insights
    data = tmp_path / 'data'
    data.mkdir(parents=True)
    _write_manifest(data, [])
    conn = conn_base(funnel={'stages': {'met': 50, 'recurring': 20}})
    (data / 'connected_all.json').write_text(
        json.dumps(conn, ensure_ascii=False), encoding='utf-8')
    rc = build_insights.main(['--dash-dir', str(tmp_path)])
    assert rc == 0
    out = json.loads((data / 'insights.json').read_text(encoding='utf-8'))
    assert 'connected' in out
    assert 'all' in out['connected']


# =========================================================================== #
# Wave 2 rule tests — 14 missing rules (9 chat + 5 connected)
# =========================================================================== #

# ---- 28. unanswered-bids (chat) ----
def _unanswered_daily():
    """High-volume symmetric chat with big answer-rate gap."""
    d = {}
    for i in range(12):
        day = f'2024-{i+1:02d}-15'
        d[day] = {
            PARTNER: cell(msgs=80, questions=8, questions_answered=7,
                          words=400, turns=16, initiations=3),
            OWNER: cell(msgs=80, questions=8, questions_answered=2,
                        words=400, turns=16, initiations=3),
        }
    return d

def test_unanswered_bids_triggers():
    """One person's questions get answered far less than the other's."""
    out = _run(chat_payload(_unanswered_daily(),
                            lifetime={'response_times': {
                                'my_median_response_minutes': 5.0,
                                'partner_median_response_minutes': 2.0}}))
    assert 'unanswered-bids' in ids(out)


def test_unanswered_bids_gate_balanced_answers():
    """When answer rates are similar, unanswered-bids stays silent."""
    d = _unanswered_daily()
    # Make both answer rates similar
    for day in d:
        d[day][OWNER]['questions_answered'] = 6  # 75% vs 87%
    out = _run(chat_payload(d))
    assert 'unanswered-bids' not in ids(out)


# ---- 29. shared-laughter (chat) ----
def _laughter_payload(co_share=0.7, total=50):
    extras = {'laughter': {'laugh_sessions': total,
                           'co_laugh_sessions': int(total * co_share),
                           'solo_laugh_sessions': {PARTNER: 3, OWNER: 2}}}
    return chat_payload(baseline_daily(), extras=extras)

def test_shared_laughter_triggers():
    """Most laugh-sessions are shared → fun finding."""
    out = _run(_laughter_payload(co_share=0.75, total=50))
    assert 'shared-laughter' in ids(out)


def test_shared_laughter_gate_low_share():
    """When <50% laughs are shared, stays silent."""
    out = _run(_laughter_payload(co_share=0.4, total=50))
    assert 'shared-laughter' not in ids(out)


# ---- 30. laughing-alone (chat) ----
def test_laughing_alone_triggers():
    """One person laughs alone most of the time."""
    extras = {'laughter': {
        'laugh_sessions': 50,
        'co_laugh_sessions': 30,
        'solo_laugh_sessions': {PARTNER: 20, OWNER: 3}}}
    out = _run(chat_payload(baseline_daily(), extras=extras))
    assert 'laughing-alone' in ids(out)


def test_laughing_alone_gate_balanced_solo():
    """When solo laughs are split, stays silent."""
    extras = {'laughter': {
        'laugh_sessions': 50,
        'co_laugh_sessions': 30,
        'solo_laugh_sessions': {PARTNER: 10, OWNER: 10}}}
    out = _run(chat_payload(baseline_daily(), extras=extras))
    assert 'laughing-alone' not in ids(out)


# ---- 31. feast-and-famine (chat) ----
def test_feast_and_famine_triggers():
    """High weekly-volume CV → bursts and silences."""
    daily = {}
    # 20 weeks: quiet baseline punctuated by a burst every 4th week. Simple
    # 2-level alternation only reaches CV ~0.95; the rule needs CV >= 1.2, so the
    # data must be genuinely spiky (bursty weeks amid silences) — which is
    # exactly the phenomenon the rule names. (CV ~1.66 here.)
    for week in range(20):
        base_day = week * 7
        for d_idx in range(7):
            day_num = base_day + d_idx
            day_str = (date(2024, 1, 1) + timedelta(days=day_num)).isoformat()
            vol = 2000 if week % 4 == 0 else 20
            daily[day_str] = {
                PARTNER: cell(msgs=vol // 2, words=vol * 5, turns=vol // 2,
                              initiations=2),
                OWNER: cell(msgs=vol // 2, words=vol * 5, turns=vol // 2,
                            initiations=2),
            }
    out = _run(chat_payload(daily))
    assert 'feast-and-famine' in ids(out)


def test_feast_and_famine_gate_low_cv():
    """Steady volume → stays silent."""
    daily = baseline_daily(n_months=12, msgs_each=60)
    out = _run(chat_payload(daily))
    assert 'feast-and-famine' not in ids(out)


# ---- 32. steady-drumbeat (chat) ----
def test_steady_drumbeat_triggers():
    """Very low weekly CV over many weeks → steady rhythm."""
    daily = {}
    # Build 30 weeks of nearly constant volume
    for week in range(30):
        base_day = week * 7
        for d_idx in range(7):
            day_num = base_day + d_idx
            day_str = (date(2024, 1, 1) + timedelta(days=day_num)).isoformat()
            daily[day_str] = {
                PARTNER: cell(msgs=30, words=150, turns=10, initiations=2),
                OWNER: cell(msgs=30, words=150, turns=10, initiations=2),
            }
    out = _run(chat_payload(daily))
    assert 'steady-drumbeat' in ids(out)


def test_steady_drumbeat_gate_high_cv():
    """High CV → stays silent (feast-and-famine fires instead)."""
    daily = {}
    for week in range(20):
        base_day = week * 7
        for d_idx in range(7):
            day_num = base_day + d_idx
            day_str = (date(2024, 1, 1) + timedelta(days=day_num)).isoformat()
            vol = 200 if week % 2 == 0 else 5
            daily[day_str] = {
                PARTNER: cell(msgs=vol // 2, words=vol * 5, turns=vol // 2,
                              initiations=2),
                OWNER: cell(msgs=vol // 2, words=vol * 5, turns=vol // 2,
                            initiations=2),
            }
    out = _run(chat_payload(daily))
    assert 'steady-drumbeat' not in ids(out)


# ---- 33. different-clocks — REMOVED (wave-2, docs/WAVE2_REVIEW.md Part E.2) ----
# The rule was deleted: circadian_overlap (even as the overlap coefficient) is
# 0.79-0.99 corpus-wide, so no dyad clears a defensible "different clocks" bar.
# The metric survives in extras.circadian_overlap for the future circadian card;
# there is no rule to test.


def test_different_clocks_rule_is_gone():
    """The removed rule must not be registered nor firing on any overlap."""
    from src import insights_engine as ie
    assert 'different-clocks' not in ie.CHAT_RULES
    extras = {'circadian_overlap': 0.1}   # would have fired under the old gate
    out = _run(chat_payload(baseline_daily(n_months=12, msgs_each=80),
                            extras=extras))
    assert 'different-clocks' not in ids(out)


# ---- 34. length-mirroring (chat) ----
def test_length_mirroring_triggers():
    """Turn-length elasticity r>=0.35 → finding."""
    extras = {'turn_elasticity': {
        PARTNER: {'r': 0.5, 'n': 500},
        OWNER: {'r': 0.2, 'n': 300}}}
    daily = baseline_daily(n_months=12, msgs_each=80)
    out = _run(chat_payload(daily, extras=extras))
    assert 'length-mirroring' in ids(out)


def test_length_mirroring_gate_low_r():
    """Low r (<0.35) → stays silent."""
    extras = {'turn_elasticity': {
        PARTNER: {'r': 0.25, 'n': 500},
        OWNER: {'r': 0.15, 'n': 300}}}
    daily = baseline_daily(n_months=12, msgs_each=80)
    out = _run(chat_payload(daily, extras=extras))
    assert 'length-mirroring' not in ids(out)


# ---- 35. openings-that-land (chat) ----
def test_openings_that_land_triggers():
    """One person's openings go much deeper."""
    extras = {'opening_quality': {
        PARTNER: {'median_msgs': 20, 'n': 40},
        OWNER: {'median_msgs': 8, 'n': 35}}}
    daily = baseline_daily(n_months=12, msgs_each=80)
    out = _run(chat_payload(daily, extras=extras))
    assert 'openings-that-land' in ids(out)


def test_openings_that_land_gate_similar():
    """Similar opening depth → stays silent."""
    extras = {'opening_quality': {
        PARTNER: {'median_msgs': 12, 'n': 30},
        OWNER: {'median_msgs': 10, 'n': 30}}}
    daily = baseline_daily(n_months=12, msgs_each=80)
    out = _run(chat_payload(daily, extras=extras))
    assert 'openings-that-land' not in ids(out)


# ---- 36. repair (chat) — quick-repair ----
def test_repair_quick_triggers():
    """Fast median repair → elastic ties."""
    extras = {'rupture_repair': {
        'n_ruptures': 5,
        'median_repair_weeks': 1.0}}
    out = _run(chat_payload(baseline_daily(n_months=12, msgs_each=80),
                            extras=extras))
    ids_out = ids(out)
    assert 'quick-repair' in ids_out or 'slow-repair' in ids_out
    # Check it's quick-repair (low median)
    for f in out:
        if f['id'] in ('quick-repair', 'slow-repair'):
            assert f['id'] == 'quick-repair'
            break


def test_repair_slow_triggers():
    """Slow median repair → brittle ties."""
    extras = {'rupture_repair': {
        'n_ruptures': 5,
        'median_repair_weeks': 8.0}}
    out = _run(chat_payload(baseline_daily(n_months=12, msgs_each=80),
                            extras=extras))
    for f in out:
        if f['id'] in ('quick-repair', 'slow-repair'):
            assert f['id'] == 'slow-repair'
            break
    else:
        pytest.fail('Expected repair finding but got none')


def test_repair_gate_no_ruptures():
    """No ruptures → stays silent."""
    extras = {'rupture_repair': {
        'n_ruptures': 0,
        'median_repair_weeks': None}}
    out = _run(chat_payload(baseline_daily(n_months=12, msgs_each=80),
                            extras=extras))
    ids_out = ids(out)
    assert 'quick-repair' not in ids_out
    assert 'slow-repair' not in ids_out


# ---- 37. dormancy-resilience (connected) — elastic ----
def test_dormancy_resilience_elastic_triggers():
    """High recover share → elastic ties."""
    p = conn_base(dormancy={'revivals': 10, 'recover_share': 0.80})
    out = run_connected(p)
    ids_out = conn_ids(out)
    assert 'elastic-ties' in ids_out


def test_dormancy_resilience_gate_low_share():
    """Low recover share → stays silent."""
    p = conn_base(dormancy={'revivals': 10, 'recover_share': 0.50})
    out = run_connected(p)
    ids_out = conn_ids(out)
    assert 'elastic-ties' not in ids_out
    assert 'brittle-ties' not in ids_out


# ---- 38. drifting-away (connected) ----
def test_drifting_away_triggers():
    """Top-volume contact you now answer much slower."""
    p = conn_base(attention_debt=[
        {'name': 'Drifting', 'volume_rank': 5,
         'earlier_median_min': 2.0, 'recent_median_min': 10.0, 'ratio': 5.0}])
    out = run_connected(p)
    assert 'drifting-away' in conn_ids(out)


def test_drifting_away_gate_low_ratio():
    """Small latency increase → stays silent."""
    p = conn_base(attention_debt=[
        {'name': 'Slow', 'volume_rank': 5,
         'earlier_median_min': 4.0, 'recent_median_min': 5.0, 'ratio': 1.25}])
    out = run_connected(p)
    assert 'drifting-away' not in conn_ids(out)


# ---- 39. novelty (connected) — explorer ----
def test_novelty_explorer_triggers():
    """High trailing novelty → explorer."""
    p = conn_base(novelty={'trailing_6mo': 0.35, 'n_contacts': 20})
    out = run_connected(p)
    ids_out = conn_ids(out)
    assert 'explorer-vs-consolidator' in ids_out
    for f in out:
        if f['id'] == 'explorer-vs-consolidator':
            assert f.get('sentence') and 'explorer' in f['sentence'].lower()
            break
    else:
        pytest.fail('Expected explorer-vs-consolidator finding')


def test_novelty_consolidator_triggers():
    """Very low trailing novelty → consolidator."""
    p = conn_base(novelty={'trailing_6mo': 0.01, 'n_contacts': 20})
    out = run_connected(p)
    for f in out:
        if f['id'] == 'explorer-vs-consolidator':
            assert f.get('sentence') and 'consolidator' in f['sentence'].lower()
            break
    else:
        pytest.fail('Expected explorer-vs-consolidator finding')


def test_novelty_gate_low_contacts():
    """Too few contacts → stays silent."""
    p = conn_base(novelty={'trailing_6mo': 0.40, 'n_contacts': 5})
    out = run_connected(p)
    ids_out = conn_ids(out)
    assert 'explorer-vs-consolidator' not in ids_out


# ---- 40/41. platform-focus & platform-persona (connected) ----
# NOTE: ``test_platform_focus_triggers``, ``test_platform_focus_gate_similar``
# and ``test_platform_persona_triggers`` were previously RE-DEFINED here,
# silently shadowing the earlier (working) definitions above that use
# ``_platform_variant``. The duplicates were removed (docs/WAVE2_REVIEW.md Part D
# item 6). Only the persona GATE test was unique to this block; it is kept below,
# now built with FLAT owner daily cells — the real connected ``daily`` shape that
# ``_owner_style`` sums (item 5). Real dates avoid the day-collision bug (item 4).
def test_platform_persona_gate_similar():
    """Similar writing style across platforms → stays silent."""
    ig_daily = {}
    tg_daily = {}
    for i in range(200):
        day_str = (date(2024, 1, 1) + timedelta(days=i)).isoformat()
        # FLAT owner cells (matches connected_*.json), not chat-style {'B': ...}.
        ig_daily[day_str] = cell(msgs=50, words=250, emoji=15)   # emoji_rate 0.06
        tg_daily[day_str] = cell(msgs=50, words=250, emoji=14)   # emoji_rate 0.056
    ig = conn_base(totals={'messages_sent': 10000}, daily=ig_daily)
    tg = conn_base(totals={'messages_sent': 10000}, daily=tg_daily)
    out = run_connected(conn_base(), ig=ig, tg=tg)
    assert 'platform-persona' not in conn_ids(out)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
