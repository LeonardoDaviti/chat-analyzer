"""Insights ("Findings") engine — Tier 1 rule catalog.

Pure, deterministic rules over the SAME aggregate payloads the dashboard reads
(per-chat ``daily`` tables + ``lifetime`` + ``extras`` + ``telegram`` +
``change_points``, and the connected ``connected_<variant>`` payloads). The
engine never re-reads ``Chats/`` — every rule is a pure function of aggregates,
so it is structurally message-content-blind (contact NAMES are fine).

See ``docs/INSIGHTS.md`` for the contract. Each rule returns ``None`` (gated
out) or a Finding dict. The engine runs the registry over a payload, sorts by
``score`` descending with a deterministic ``rule id`` tie-break, and caps the
list (8 per chat, 12 for connected).

Tier 2 (LLM narrator) and Tier 3 (content analysis) are design-only — not here.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# §2 scoring & gates
# --------------------------------------------------------------------------- #

CATEGORY_WEIGHTS = {
    'dynamics': 1.0, 'attention': 0.9, 'language': 0.7, 'rhythm': 0.6,
    'portfolio': 0.8, 'platform': 0.8, 'fun': 0.4,
}

# Global gates (spec §2). A chat below MIN_MSGS is not scored at all.
MIN_MSGS = 500
MIN_SESSIONS = 60
MIN_SIDE_EVENTS = 50        # ratios need >=50 events on both sides
MIN_BASE_RATE = 0.02        # ratios only when both base rates >= 2%

# Owner requested richer output (docs/INSIGHTS.md §2 / wave-2): caps raised from
# 8/12 to 12/15. Design law #1 still holds — rules still gate hard.
CHAT_CAP = 12
CONNECTED_CAP = 15

# Fields carried per user per day in the daily table (numeric, summable).
_SUM_FIELDS = (
    'msgs', 'words', 'chars', 'emoji', 'questions', 'questions_answered',
    'laughs', 'night_msgs',
    'reactions_given', 'reactions_received', 'media', 'photos', 'videos',
    'voice', 'shares', 'resp_lat_sum_min', 'resp_lat_n', 'initiations',
    'turns', 'turns_answered', 'endings', 'self_restarts', 'reacted_leave',
    'wait_reply_sum_min', 'wait_reply_n', 'we_words', 'i_words', 'you_words',
    'pos_words', 'neg_words', 'gratitude', 'apology', 'edits',
)


def _score(w_cat: float, effect: float, effect_ref: float,
           n: float, n_gate: float) -> Tuple[float, float, float, str]:
    """Return (score, E, V, confidence) per §2."""
    E = min(1.0, effect / effect_ref) if effect_ref else min(1.0, effect)
    V = min(1.0, n / (2.0 * n_gate)) if n_gate else 1.0
    conf = 'high' if (n >= 2.0 * n_gate and E >= 0.8) else 'medium'
    return w_cat * E * V, E, V, conf


def _median(xs: List[float]) -> Optional[float]:
    ys = sorted(v for v in xs if v is not None)
    if not ys:
        return None
    m = len(ys) // 2
    return ys[m] if len(ys) % 2 else (ys[m - 1] + ys[m]) / 2.0


def _mean(xs: List[float]) -> Optional[float]:
    ys = [v for v in xs if v is not None]
    return sum(ys) / len(ys) if ys else None


def _std(xs: List[float]) -> float:
    ys = [v for v in xs if v is not None]
    if len(ys) < 2:
        return 0.0
    mu = sum(ys) / len(ys)
    return (sum((v - mu) ** 2 for v in ys) / len(ys)) ** 0.5


# --------------------------------------------------------------------------- #
# Finding builder + name helpers
# --------------------------------------------------------------------------- #

def _finding(rule_id: str, scope: str, category: str, severity: str,
             direction: str, title: str, sentence: str,
             evidence: Dict[str, Any], score: float, confidence: str,
             window: Dict[str, Any], anchor: Optional[str] = None,
             chat_id: Optional[str] = None) -> Dict[str, Any]:
    f: Dict[str, Any] = {
        'id': rule_id, 'scope': scope, 'category': category,
        'severity': severity, 'direction': direction,
        'score': round(score, 4), 'confidence': confidence,
        'title': title, 'sentence': sentence,
        'evidence': {k: (round(v, 4) if isinstance(v, float) else v)
                     for k, v in evidence.items()},
        'window': window,
    }
    if chat_id is not None:
        f['chat_id'] = chat_id
    if anchor:
        f['anchor'] = anchor
    return f


def _Name(name: str, owner: str) -> str:
    return 'You' if name == owner else name


def _name(name: str, owner: str) -> str:
    return 'you' if name == owner else name


def _poss(name: str, owner: str) -> str:
    return 'your' if name == owner else name + "'s"


def _x(r: float) -> str:
    return f'{r:.1f}×'


def _pct(v: float, dp: int = 0) -> str:
    return f'{v * 100:.{dp}f}%'


# --------------------------------------------------------------------------- #
# Chat context — precomputed aggregates over the daily table + lifetime
# --------------------------------------------------------------------------- #

class ChatCtx:
    """All aggregates a chat rule might need, computed once per chat."""

    def __init__(self, chat_id: str, payload: Dict[str, Any], owner: str):
        self.chat_id = chat_id
        self.payload = payload
        self.participants: List[str] = payload.get('participants', [])[:2]
        self.platform = payload.get('platform', 'instagram')
        self.lifetime = payload.get('lifetime', {}) or {}
        self.extras = payload.get('extras', {}) or {}
        self.telegram = payload.get('telegram')
        self.calls = payload.get('calls')
        self.change_points = payload.get('change_points', []) or []

        daily: Dict[str, Dict[str, Any]] = payload.get('daily', {}) or {}
        self.dates = sorted(daily.keys())
        self.daily = daily

        # owner / partner. participants[0] is the busier sender.
        parts = self.participants
        if owner in parts:
            self.owner = owner
            self.partner = parts[0] if parts[1] == owner else parts[1]
        else:
            # fall back: the second-listed participant is usually the owner
            self.owner = parts[1] if len(parts) > 1 else (parts[0] if parts else 'You')
            self.partner = parts[0] if parts else 'them'

        self.window = {
            'from': self.dates[0] if self.dates else None,
            'to': self.dates[-1] if self.dates else None,
        }
        self.months = sorted({d[:7] for d in self.dates})

        # all-time per-user totals
        self.tot = {u: self._sum(self.dates, u) for u in parts}
        # halves (by active-day index)
        mid = len(self.dates) // 2
        self.first_dates = self.dates[:mid]
        self.second_dates = self.dates[mid:]
        self.h1 = {u: self._sum(self.first_dates, u) for u in parts}
        self.h2 = {u: self._sum(self.second_dates, u) for u in parts}

        self.n_msgs = sum(self.tot[u]['msgs'] for u in parts)
        self.n_sessions = sum(self.tot[u]['initiations'] for u in parts)

    def _sum(self, dates: List[str], user: str) -> Dict[str, float]:
        acc = {f: 0.0 for f in _SUM_FIELDS}
        hours = [0] * 24
        for d in dates:
            cell = self.daily.get(d, {}).get(user)
            if not cell:
                continue
            for f in _SUM_FIELDS:
                acc[f] += cell.get(f, 0) or 0
            hh = cell.get('hours')
            if hh:
                for i in range(24):
                    hours[i] += hh[i]
        acc['hours'] = hours
        return acc

    def weekly_msgs(self) -> List[float]:
        """Combined messages per ISO week (chronological). Used for volatility."""
        from datetime import date
        acc: Dict[str, float] = defaultdict(float)
        for d in self.dates:
            y, m, dd = (int(x) for x in d.split('-'))
            iso = date(y, m, dd).isocalendar()
            key = f'{iso[0]}-W{iso[1]:02d}'
            for u in self.participants:
                cell = self.daily.get(d, {}).get(u)
                if cell:
                    acc[key] += cell.get('msgs', 0) or 0
        return [acc[k] for k in sorted(acc)]

    def monthly_combined(self) -> Dict[str, Dict[str, float]]:
        """Per calendar month: combined msgs/words/turns/initiations."""
        out: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {'msgs': 0.0, 'words': 0.0, 'turns': 0.0, 'sessions': 0.0})
        for d in self.dates:
            m = d[:7]
            for u in self.participants:
                cell = self.daily.get(d, {}).get(u)
                if not cell:
                    continue
                out[m]['msgs'] += cell.get('msgs', 0) or 0
                out[m]['words'] += cell.get('words', 0) or 0
                out[m]['turns'] += cell.get('turns', 0) or 0
                out[m]['sessions'] += cell.get('initiations', 0) or 0
        return out


def _night06(tot: Dict[str, float]) -> Tuple[int, int]:
    """(messages in 00:00–06:00, total messages) from an hours histogram."""
    hours = tot.get('hours') or [0] * 24
    return sum(hours[0:6]), int(tot.get('msgs', 0))


# --------------------------------------------------------------------------- #
# Chat rules (§3.1) — each returns a Finding dict or None
# --------------------------------------------------------------------------- #

def rule_asymmetric_pursuit(c: ChatCtx) -> Optional[Dict]:
    if c.n_sessions < MIN_SESSIONS:
        return None
    a, b = c.participants
    init = c.lifetime.get('initiation', {}) or {}
    rt = c.lifetime.get('response_times', {}) or {}
    lat = {c.owner: rt.get('my_median_response_minutes'),
           c.partner: rt.get('partner_median_response_minutes')}
    best = None
    for X, Y in ((a, b), (b, a)):
        share = (init.get(X, {}) or {}).get('initiation_share')
        lx, ly = lat.get(X), lat.get(Y)
        rx, ry = c.tot[X]['resp_lat_n'], c.tot[Y]['resp_lat_n']
        if share is None or lx in (None, 0) or ly is None:
            continue
        if rx < MIN_SIDE_EVENTS or ry < MIN_SIDE_EVENTS:
            continue
        if share >= 0.65 and lx <= 0.6 * ly:
            ratio = ly / lx if lx else 0
            if best is None or share > best[3]:
                best = (X, Y, ratio, share)
    if not best:
        return None
    X, Y, ratio, share = best
    effect_ref = 0.78
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], share, effect_ref,
                            c.n_sessions, MIN_SESSIONS)
    sent = (f"{_Name(X, c.owner)} start{'' if X==c.owner else 's'} {_pct(share)} "
            f"of conversations and answer{'' if X==c.owner else 's'} {_x(ratio)} "
            f"faster — {_name(X, c.owner)} do{'' if X==c.owner else 'es'} the pursuing.")
    return _finding('asymmetric-pursuit', 'chat', 'dynamics', 'signal', 'asym',
                    'One person carries the pursuit', sent,
                    {'initiator': X, 'init_share': share, 'latency_ratio': round(ratio, 2),
                     'n_sessions': int(c.n_sessions)},
                    sc, conf, c.window, anchor='cInit', chat_id=c.chat_id)


def rule_pursuit_withdrawal_trend(c: ChatCtx) -> Optional[Dict]:
    if len(c.months) < 8:
        return None
    a, b = c.participants
    for X, Y in ((a, b), (b, a)):
        i1 = c.h1[X]['initiations']; i1t = c.h1[a]['initiations'] + c.h1[b]['initiations']
        i2 = c.h2[X]['initiations']; i2t = c.h2[a]['initiations'] + c.h2[b]['initiations']
        if i1t < 20 or i2t < 20:
            continue
        s1, s2 = i1 / i1t, i2 / i2t
        # partner (Y) latency rising across halves
        l1 = (c.h1[Y]['resp_lat_sum_min'] / c.h1[Y]['resp_lat_n']) if c.h1[Y]['resp_lat_n'] >= 20 else None
        l2 = (c.h2[Y]['resp_lat_sum_min'] / c.h2[Y]['resp_lat_n']) if c.h2[Y]['resp_lat_n'] >= 20 else None
        if l1 in (None, 0) or l2 is None:
            continue
        if (s2 - s1) >= 0.10 and (l2 - l1) / l1 >= 0.50:
            effect = min((s2 - s1) / 0.20, ((l2 - l1) / l1) / 1.0)
            sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], effect, 1.0,
                                    c.n_sessions, MIN_SESSIONS)
            sent = (f"Over this chat's life, {_name(X, c.owner)} started reaching out more "
                    f"({_pct(s1)}→{_pct(s2)} of openings) while {_name(Y, c.owner)} replied "
                    f"slower — the classic chase–retreat drift.")
            return _finding('pursuit-withdrawal-trend', 'chat', 'dynamics', 'signal',
                            'shift', 'Chase and retreat', sent,
                            {'initiator': X, 'init_share_h1': round(s1, 3),
                             'init_share_h2': round(s2, 3),
                             'partner_latency_rise': round((l2 - l1) / l1, 2)},
                            sc, conf, c.window, anchor='cInit', chat_id=c.chat_id)
    return None


_METRIC_LABEL = {
    'volume': 'message volume', 'response_latency': 'reply time',
    'night_share': 'night activity', 'initiation_share': 'who starts',
    'affect_rate': 'warmth', 'depth': 'message depth', 'question_rate': 'questions',
}
_DIR_WORD = {'up': 'rose', 'down': 'fell'}


def rule_regime_change_story(c: ChatCtx) -> Optional[Dict]:
    if not c.change_points or c.n_msgs < MIN_MSGS:
        return None
    # pick the change-point with the largest total signal magnitude
    def mag(cp):
        return sum(abs(s.get('magnitude', 0)) for s in cp.get('signals', []))
    cp = max(c.change_points, key=mag)
    # strongest signal per metric (dedupe), top 3
    best_by_metric: Dict[str, Dict] = {}
    for s in cp.get('signals', []):
        m = s.get('metric')
        if m not in best_by_metric or abs(s.get('magnitude', 0)) > abs(best_by_metric[m].get('magnitude', 0)):
            best_by_metric[m] = s
    sigs = sorted(best_by_metric.values(), key=lambda s: -abs(s.get('magnitude', 0)))[:3]
    if not sigs:
        return None
    date = cp.get('date')
    parts = [f"{_METRIC_LABEL.get(s['metric'], s['metric'])} {_DIR_WORD.get(s.get('direction'), 'shifted')}"
             for s in sigs]
    top_mag = abs(sigs[0].get('magnitude', 0))
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], top_mag, 5.0,
                            c.n_msgs, MIN_MSGS)
    sent = (f"Something changed around {date}: " + ', '.join(parts) +
            ". Worth remembering what happened then.")
    return _finding('regime-change-story', 'chat', 'dynamics', 'signal', 'shift',
                    'A turning point', sent,
                    {'date': date, 'changes': [{'metric': s['metric'],
                     'direction': s.get('direction')} for s in sigs]},
                    sc, conf, c.window, anchor='cVolume', chat_id=c.chat_id)


def rule_cooling_warming(c: ChatCtx) -> Optional[Dict]:
    if len(c.months) < 9:
        return None
    mc = c.monthly_combined()
    months = sorted(mc.keys())
    if len(months) < 9:
        return None
    trailing = months[-3:]
    prior = months[-9:-3]

    def series(key: str, ms: List[str]) -> List[float]:
        if key == 'depth':
            return [(mc[m]['words'] / mc[m]['turns']) if mc[m]['turns'] else 0.0 for m in ms]
        return [mc[m][key] for m in ms]

    zs = []
    for key in ('msgs', 'depth', 'sessions'):
        prior_vals = series(key, prior)
        cur = _mean(series(key, trailing))
        mu, sd = _mean(prior_vals), _std(prior_vals)
        if cur is None or mu is None or sd == 0:
            continue
        zs.append((cur - mu) / sd)
    if len(zs) < 2:
        return None
    comp = sum(zs) / len(zs)
    if abs(comp) < 1.0:
        return None
    warming = comp >= 1.0
    effect = min(abs(comp) / 2.0, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], effect, 1.0,
                            c.n_msgs, MIN_MSGS)
    word = 'warmer' if warming else 'cooler'
    sent = (f"The last 3 months run clearly {word} than the months before "
            f"— volume, depth and how often you talk all moved together.")
    return _finding('cooling-warming', 'chat', 'dynamics', 'signal',
                    'up' if warming else 'down',
                    'Warming up' if warming else 'Cooling off', sent,
                    {'composite_z': round(comp, 2), 'direction': word,
                     'months': len(months)},
                    sc, conf, c.window, anchor='cVolume', chat_id=c.chat_id)


def rule_ending_restart_loop(c: ChatCtx) -> Optional[Dict]:
    a, b = c.participants
    endings = c.tot[a]['endings'] + c.tot[b]['endings']
    if endings < 80:
        return None
    fw = c.lifetime.get('final_word_dominance', {}) or {}
    restarts = {a: c.tot[a]['self_restarts'], b: c.tot[b]['self_restarts']}
    rt = restarts[a] + restarts[b]
    if rt < 10:
        return None
    for Y in (a, b):
        X = b if Y == a else a
        fw_share = fw.get(Y)
        r_share = restarts[X] / rt if rt else 0
        if fw_share is not None and fw_share >= 0.65 and r_share >= 0.65:
            effect = min(fw_share, r_share)
            sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], effect, 0.8,
                                    endings, 80)
            sent = (f"{_Name(Y, c.owner)} usually get{'' if Y==c.owner else 's'} the last word "
                    f"({_pct(fw_share)}); {_name(X, c.owner)} usually knock{'' if X==c.owner else 's'} "
                    f"again first ({_pct(r_share)} of restarts).")
            return _finding('ending-restart-loop', 'chat', 'dynamics', 'signal',
                            'asym', 'Who ends, who re-knocks', sent,
                            {'ender': Y, 'final_word_share': fw_share,
                             'restarter': X, 'restart_share': round(r_share, 3),
                             'n_endings': int(endings)},
                            sc, conf, c.window, anchor='cEnd', chat_id=c.chat_id)
    return None


def rule_left_on_react(c: ChatCtx) -> Optional[Dict]:
    a, b = c.participants
    ra, rb = c.tot[a]['reacted_leave'], c.tot[b]['reacted_leave']
    if ra + rb < 40:
        return None
    for X, Y, rx, ry in ((a, b, ra, rb), (b, a, rb, ra)):
        if ry <= 0:
            continue
        if rx >= 2 * ry and rx >= 20:
            ratio = rx / ry
            sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], ratio, 3.0,
                                    ra + rb, 40)
            sent = (f"When {_name(X, c.owner)} exit{'' if X==c.owner else 's'} a conversation, "
                    f"it's often with just a reaction — {int(rx)} times vs {int(ry)}.")
            return _finding('left-on-react', 'chat', 'dynamics', 'notable', 'asym',
                            'Exit by reaction', sent,
                            {'leaver': X, 'reacted_leaves': int(rx),
                             'partner_reacted_leaves': int(ry), 'ratio': round(ratio, 2)},
                            sc, conf, c.window, anchor='cRestart', chat_id=c.chat_id)
    return None


def rule_eager_waiter(c: ChatCtx) -> Optional[Dict]:
    a, b = c.participants
    na, nb = c.tot[a]['wait_reply_n'], c.tot[b]['wait_reply_n']
    if na < 30 or nb < 30:
        return None
    ma = c.tot[a]['wait_reply_sum_min'] / na
    mb = c.tot[b]['wait_reply_sum_min'] / nb
    for X, mx, my in ((a, ma, mb), (b, mb, ma)):
        if mx <= 5.0 and my > 0 and mx <= 0.5 * my:
            ratio = my / mx if mx else 0
            sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], ratio, 2.0,
                                    min(na, nb), 30)
            sent = (f"After long silences, {_name(X, c.owner)} answer{'' if X==c.owner else 's'} within "
                    f"~{mx:.0f} min of {_name(c.partner if X==c.owner else c.owner, c.owner)} coming back "
                    f"— someone keeps the chat open on their screen.")
            return _finding('eager-waiter', 'chat', 'dynamics', 'notable', 'asym',
                            'Waiting by the phone', sent,
                            {'waiter': X, 'reply_min': round(mx, 1),
                             'partner_reply_min': round(my, 1),
                             'n_waits': int(min(na, nb))},
                            sc, conf, c.window, anchor='cWait', chat_id=c.chat_id)
    return None


def rule_question_imbalance(c: ChatCtx) -> Optional[Dict]:
    a, b = c.participants
    if c.tot[a]['msgs'] < 100 or c.tot[b]['msgs'] < 100:
        return None
    qa = c.tot[a]['questions'] / c.tot[a]['msgs']
    qb = c.tot[b]['questions'] / c.tot[b]['msgs']
    for X, qx, qy in ((a, qa, qb), (b, qb, qa)):
        if qx < MIN_BASE_RATE or qy < MIN_BASE_RATE:
            continue
        if qx >= 2 * qy:
            ratio = qx / qy
            sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], ratio, 2.5,
                                    c.tot[a]['msgs'] + c.tot[b]['msgs'], 200)
            sent = (f"{_Name(X, c.owner)} ask{'' if X==c.owner else 's'} {_x(ratio)} more questions "
                    f"— {_name(X, c.owner)} carr{'y' if X==c.owner else 'ies'} the curiosity budget.")
            return _finding('question-imbalance', 'chat', 'dynamics', 'notable', 'asym',
                            'One asks, one answers', sent,
                            {'asker': X, 'q_rate': round(qx, 4),
                             'partner_q_rate': round(qy, 4), 'ratio': round(ratio, 2)},
                            sc, conf, c.window, anchor='cQ', chat_id=c.chat_id)
    return None


def rule_monologue_drift(c: ChatCtx) -> Optional[Dict]:
    if len(c.months) < 8:
        return None
    a, b = c.participants
    t1 = c.h1[a]['turns'] + c.h1[b]['turns']
    m1 = c.h1[a]['msgs'] + c.h1[b]['msgs']
    t2 = c.h2[a]['turns'] + c.h2[b]['turns']
    m2 = c.h2[a]['msgs'] + c.h2[b]['msgs']
    if not (t1 and m1 and t2 and m2):
        return None
    di1 = t1 / m1  # turns per message: higher = more back-and-forth
    di2 = t2 / m2
    if di1 <= 0:
        return None
    drop = (di1 - di2) / di1
    if drop >= 0.30:
        sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], drop, 0.5,
                                c.n_msgs, MIN_MSGS)
        sent = (f"Conversations are turning into monologues: back-and-forth is down "
                f"{_pct(drop)} from the first half of this chat's life.")
        return _finding('monologue-drift', 'chat', 'dynamics', 'signal', 'down',
                        'Turning into monologues', sent,
                        {'dialogue_index_h1': round(di1, 3),
                         'dialogue_index_h2': round(di2, 3), 'drop': round(drop, 3)},
                        sc, conf, c.window, anchor='cTurns', chat_id=c.chat_id)
    return None


def rule_depth_mismatch(c: ChatCtx) -> Optional[Dict]:
    if c.n_sessions < MIN_SESSIONS:
        return None
    a, b = c.participants

    def wpt(tot):
        return tot['words'] / tot['turns'] if tot['turns'] else 0.0
    da, db = wpt(c.tot[a]), wpt(c.tot[b])
    for X, Y, dx, dy in ((a, b, da, db), (b, a, db, da)):
        if dy <= 0:
            continue
        if dx >= 1.8 * dy:
            # stability: both halves still show >=1.5x
            def h_wpt(h, u):
                return h[u]['words'] / h[u]['turns'] if h[u]['turns'] else 0.0
            r1 = h_wpt(c.h1, X) / h_wpt(c.h1, Y) if h_wpt(c.h1, Y) else 0
            r2 = h_wpt(c.h2, X) / h_wpt(c.h2, Y) if h_wpt(c.h2, Y) else 0
            if min(r1, r2) < 1.5:
                continue
            ratio = dx / dy
            sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], ratio, 2.5,
                                    c.n_sessions, MIN_SESSIONS)
            sent = (f"{_Name(X, c.owner)} write{'' if X==c.owner else 's'} {_x(ratio)} more per turn "
                    f"— one of you sends essays, the other sends lines.")
            return _finding('depth-mismatch', 'chat', 'dynamics', 'notable', 'asym',
                            'Essays vs one-liners', sent,
                            {'writer': X, 'words_per_turn': round(dx, 1),
                             'partner_words_per_turn': round(dy, 1), 'ratio': round(ratio, 2)},
                            sc, conf, c.window, anchor='cDepth', chat_id=c.chat_id)
    return None


def rule_gottman_ratio(c: ChatCtx) -> Optional[Dict]:
    a, b = c.participants
    pos = c.tot[a]['pos_words'] + c.tot[b]['pos_words']
    neg = c.tot[a]['neg_words'] + c.tot[b]['neg_words']
    if pos + neg < 300 or neg < 5:
        return None
    ratio = pos / neg
    if ratio >= 5.0 and ratio <= 8.0:
        return None  # the healthy band — say nothing
    below = ratio < 5.0
    effect = (5.0 - ratio) / 5.0 if below else min((ratio - 8.0) / 8.0, 1.0)
    if effect <= 0:
        return None
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['language'], effect, 1.0,
                            pos + neg, 300)
    where = 'below' if below else 'above'
    sent = (f"Warm words outnumber cold ones {ratio:.1f}:1 — {where} the 5:1 line "
            f"relationship research keeps finding.")
    return _finding('gottman-ratio', 'chat', 'language', 'signal',
                    'down' if below else 'up', 'Positivity balance', sent,
                    {'pos_neg_ratio': round(ratio, 2), 'pos_words': int(pos),
                     'neg_words': int(neg)},
                    sc, conf, c.window, anchor='cSent', chat_id=c.chat_id)


def rule_we_ness_shift(c: ChatCtx) -> Optional[Dict]:
    a, b = c.participants
    def orient(h):
        we = h[a]['we_words'] + h[b]['we_words']
        i = h[a]['i_words'] + h[b]['i_words']
        return (we / (we + i)) if (we + i) else None, we + i
    o1, n1 = orient(c.h1)
    o2, n2 = orient(c.h2)
    total = (c.tot[a]['we_words'] + c.tot[b]['we_words'] +
             c.tot[a]['i_words'] + c.tot[b]['i_words'])
    if total < 500 or o1 is None or o2 is None:
        return None
    shift = o2 - o1
    if abs(shift) < 0.08:
        return None
    toward = "'we'" if shift > 0 else "'I'"
    effect = min(abs(shift) / 0.16, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['language'], effect, 1.0, total, 500)
    sent = (f"Pronouns drifted toward {toward} over time — language tends to follow closeness.")
    return _finding('we-ness-shift', 'chat', 'language', 'notable', 'shift',
                    'Pronoun drift', sent,
                    {'we_share_h1': round(o1, 3), 'we_share_h2': round(o2, 3),
                     'shift': round(shift, 3)},
                    sc, conf, c.window, anchor='cWe', chat_id=c.chat_id)


def rule_style_mirror(c: ChatCtx) -> Optional[Dict]:
    lsm = c.extras.get('lsm_monthly', {}) or {}
    pairs = sorted((m, v) for m, v in lsm.items() if v is not None)
    if len(pairs) < 6:
        return None
    vals = [v for _, v in pairs]
    mean_lsm = _mean(vals)
    half = len(vals) // 2
    rise = (_mean(vals[half:]) or 0) - (_mean(vals[:half]) or 0)
    sustained = mean_lsm is not None and mean_lsm >= 0.85
    if not sustained and rise < 0.10:
        return None
    effect = min((mean_lsm or 0), 1.0) if sustained else min(rise / 0.2, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['language'], effect, 1.0,
                            len(pairs), 6)
    if sustained:
        sent = (f"Your writing styles have converged (LSM {mean_lsm:.2f}) — heavy "
                f"mirroring, usually a closeness marker.")
        d = 'up'
    else:
        sent = (f"Your writing styles have been converging (LSM up {rise:+.2f}) — "
                f"growing mirroring, usually a closeness marker.")
        d = 'up'
    return _finding('style-mirror', 'chat', 'language', 'notable', d,
                    'Styles converging', sent,
                    {'lsm_mean': round(mean_lsm, 3) if mean_lsm else None,
                     'lsm_rise': round(rise, 3), 'months': len(pairs)},
                    sc, conf, c.window, anchor='cLSM', chat_id=c.chat_id)


def rule_courtesy_asymmetry(c: ChatCtx) -> Optional[Dict]:
    a, b = c.participants
    ca = c.tot[a]['gratitude'] + c.tot[a]['apology']
    cb = c.tot[b]['gratitude'] + c.tot[b]['apology']
    if ca + cb < 40:
        return None
    ra = ca / c.tot[a]['msgs'] if c.tot[a]['msgs'] else 0
    rb = cb / c.tot[b]['msgs'] if c.tot[b]['msgs'] else 0
    for X, rx, ry in ((a, ra, rb), (b, rb, ra)):
        if ry <= 0:
            continue
        if rx >= 2.5 * ry:
            ratio = rx / ry
            sc, E, V, conf = _score(CATEGORY_WEIGHTS['language'], ratio, 3.5,
                                    ca + cb, 40)
            sent = f"{_Name(X, c.owner)} say{'' if X==c.owner else 's'} thanks or sorry {_x(ratio)} more often."
            return _finding('courtesy-asymmetry', 'chat', 'language', 'notable', 'asym',
                            'Courtesy gap', sent,
                            {'polite': X, 'rate': round(rx, 4),
                             'partner_rate': round(ry, 4), 'ratio': round(ratio, 2)},
                            sc, conf, c.window, anchor='courtesyBox', chat_id=c.chat_id)
    return None


def rule_tg_second_guessing(c: ChatCtx) -> Optional[Dict]:
    if not c.telegram:
        return None
    pu = c.telegram.get('per_user', {}) or {}
    a, b = c.participants
    pa, pb = pu.get(a, {}), pu.get(b, {})
    if pa.get('msgs', 0) < 200 or pb.get('msgs', 0) < 200:
        return None
    for X, px, py in ((a, pa, pb), (b, pb, pa)):
        ex, ey = px.get('edit_rate', 0), py.get('edit_rate', 0)
        if ex >= 0.08 and ey > 0 and ex >= 2 * ey:
            ratio = ex / ey
            sc, E, V, conf = _score(CATEGORY_WEIGHTS['language'], ex, 0.2,
                                    min(pa.get('msgs', 0), pb.get('msgs', 0)), 200)
            sent = (f"{_Name(X, c.owner)} edit{'' if X==c.owner else 's'} {_pct(ex)} of messages after "
                    f"sending — {_x(ratio)} more than {_name(c.partner if X==c.owner else c.owner, c.owner)}. "
                    f"Careful writer, or second-guesser.")
            return _finding('tg-second-guessing', 'chat', 'language', 'notable', 'asym',
                            'Second-guessing the send', sent,
                            {'editor': X, 'edit_rate': round(ex, 4),
                             'partner_edit_rate': round(ey, 4), 'ratio': round(ratio, 2)},
                            sc, conf, c.window, anchor='cTgEdit', chat_id=c.chat_id)
    return None


def rule_night_migration(c: ChatCtx) -> Optional[Dict]:
    if len(c.months) < 6:
        return None
    a, b = c.participants
    n1, t1 = 0, 0
    n2, t2 = 0, 0
    for u in (a, b):
        h1n, h1t = _night06(c.h1[u]); n1 += h1n; t1 += h1t
        h2n, h2t = _night06(c.h2[u]); n2 += h2n; t2 += h2t
    if t1 < 50 or t2 < 50:
        return None
    s1 = n1 / t1 if t1 else 0
    s2 = n2 / t2 if t2 else 0
    if s2 >= 0.15 and s1 > 0 and s2 >= 2 * s1:
        effect = min(s2 / 0.30, 1.0)
        sc, E, V, conf = _score(CATEGORY_WEIGHTS['rhythm'], effect, 1.0,
                                c.n_msgs, MIN_MSGS)
        sent = (f"This conversation has migrated into the night: {_pct(s2)} of it now "
                f"happens after midnight, up from {_pct(s1)}.")
        return _finding('night-migration', 'chat', 'rhythm', 'notable', 'up',
                        'Into the night', sent,
                        {'night_share_h1': round(s1, 3), 'night_share_h2': round(s2, 3)},
                        sc, conf, c.window, anchor='cNight', chat_id=c.chat_id)
    return None


def rule_session_records(c: ChatCtx) -> Optional[Dict]:
    if c.n_msgs < MIN_MSGS or not c.dates:
        return None
    # longest streak of consecutive active days
    from datetime import date
    def d(s):
        y, m, dd = s.split('-')
        return date(int(y), int(m), int(dd))
    days = [d(x) for x in c.dates]
    streak = best = 1
    for i in range(1, len(days)):
        if (days[i] - days[i - 1]).days == 1:
            streak += 1
            best = max(best, streak)
        else:
            streak = 1
    # busiest single day + peak month
    per_day = {x: sum((c.daily[x].get(u, {}) or {}).get('msgs', 0)
                      for u in c.participants) for x in c.dates}
    busiest_date = max(per_day, key=per_day.get)
    busiest = per_day[busiest_date]
    mc = c.monthly_combined()
    peak_month = max(mc, key=lambda m: mc[m]['msgs'])
    peak_msgs = int(mc[peak_month]['msgs'])
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['fun'], 1.0, 1.0, c.n_msgs, MIN_MSGS)
    sent = (f"Record book: longest daily streak {best} days, busiest day {busiest_date} "
            f"with {int(busiest)} messages, peak month {peak_month} ({peak_msgs}).")
    return _finding('session-records', 'chat', 'rhythm', 'fun', 'record',
                    'The record book', sent,
                    {'streak_days': int(best), 'busiest_date': busiest_date,
                     'busiest_msgs': int(busiest), 'peak_month': peak_month,
                     'peak_month_msgs': peak_msgs},
                    sc, conf, c.window, anchor='cCal', chat_id=c.chat_id)


def rule_media_reciprocity_gap(c: ChatCtx) -> Optional[Dict]:
    a, b = c.participants
    ma = c.tot[a]['photos'] + c.tot[a]['videos'] + c.tot[a]['voice']
    mb = c.tot[b]['photos'] + c.tot[b]['videos'] + c.tot[b]['voice']
    if ma + mb < 60:
        return None
    for X, Y, mx, my in ((a, b, ma, mb), (b, a, mb, ma)):
        if my <= 0:
            continue
        if mx >= 3 * my:
            ratio = mx / my
            sc, E, V, conf = _score(CATEGORY_WEIGHTS['rhythm'], ratio, 4.0,
                                    ma + mb, 60)
            sent = (f"{_Name(X, c.owner)} send{'' if X==c.owner else 's'} the photos and voice notes; "
                    f"{_name(Y, c.owner)} answer{'' if Y==c.owner else 's'} in text ({int(mx)} vs {int(my)}).")
            return _finding('media-reciprocity-gap', 'chat', 'rhythm', 'fun', 'asym',
                            'One sends the media', sent,
                            {'sender': X, 'media': int(mx),
                             'partner_media': int(my), 'ratio': round(ratio, 2)},
                            sc, conf, c.window, anchor='cMedia', chat_id=c.chat_id)
    return None


# --------------------------------------------------------------------------- #
# Wave-2 chat rules (Part B). Windowable ones read only the daily table.
# --------------------------------------------------------------------------- #

def rule_unanswered_bids(c: ChatCtx) -> Optional[Dict]:
    """Metric 1 — bid-response. X's questions get answered far less than Y's."""
    a, b = c.participants
    qa_a, q_a = c.tot[a]['questions_answered'], c.tot[a]['questions']
    qa_b, q_b = c.tot[b]['questions_answered'], c.tot[b]['questions']
    if q_a < 40 or q_b < 40:
        return None
    ra = qa_a / q_a if q_a else 0
    rb = qa_b / q_b if q_b else 0
    for X, Y, rx, ry in ((a, b, ra, rb), (b, a, rb, ra)):
        if ry <= 0:
            continue
        if rx <= 0.6 * ry:
            hang = 1 - rx
            effect = min((ry - rx) / max(ry, 1e-6), 1.0)
            sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], effect, 0.6,
                                    q_a + q_b, 100)
            sent = (f"{_Name(Y, c.owner)} leave{'' if Y==c.owner else 's'} {_pct(hang)} of "
                    f"{_poss(X, c.owner)} questions hanging — {_name(X, c.owner)} "
                    f"get{'' if X==c.owner else 's'} answered far less than the other way round.")
            return _finding('unanswered-bids', 'chat', 'dynamics', 'signal', 'asym',
                            'Questions left hanging', sent,
                            {'asker': X, 'answer_rate': round(rx, 3),
                             'partner_answer_rate': round(ry, 3),
                             'n_questions': int(q_a + q_b)},
                            sc, conf, c.window, anchor='cQ', chat_id=c.chat_id)
    return None


def rule_shared_laughter(c: ChatCtx) -> Optional[Dict]:
    """Metric 5 — warm finding: most laugh-sessions are shared."""
    lg = c.extras.get('laughter', {}) or {}
    total = lg.get('laugh_sessions', 0)
    co = lg.get('co_laugh_sessions', 0)
    if total < 30:
        return None
    share = co / total if total else 0
    if share < 0.5:
        return None
    effect = min(share, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['language'], effect, 1.0, total, 30)
    sent = (f"You laugh together: {_pct(share)} of the conversations with any laughter "
            f"have both of you cracking up, not just one.")
    return _finding('shared-laughter', 'chat', 'language', 'fun', 'up',
                    'Laughing together', sent,
                    {'co_laugh_share': round(share, 3), 'laugh_sessions': int(total)},
                    sc, conf, c.window, anchor='cEmoji', chat_id=c.chat_id)


def rule_laughing_alone(c: ChatCtx) -> Optional[Dict]:
    """Metric 5 — gentle asymmetry: one person laughs alone most of the time."""
    lg = c.extras.get('laughter', {}) or {}
    total = lg.get('laugh_sessions', 0)
    solo = lg.get('solo_laugh_sessions', {}) or {}
    if total < 30:
        return None
    solo_total = sum(solo.values())
    if solo_total < 15:
        return None
    for X in c.participants:
        sx = solo.get(X, 0)
        share = sx / solo_total if solo_total else 0
        if share >= 0.75:
            effect = min(share, 1.0)
            sc, E, V, conf = _score(CATEGORY_WEIGHTS['language'], effect, 1.0,
                                    solo_total, 15)
            sent = (f"When laughter is one-sided, it's usually {_name(X, c.owner)} "
                    f"laughing alone — {_pct(share)} of the solo-laugh moments.")
            return _finding('laughing-alone', 'chat', 'language', 'notable', 'asym',
                            'Laughing alone', sent,
                            {'laugher': X, 'solo_share': round(share, 3),
                             'solo_laugh_sessions': int(solo_total)},
                            sc, conf, c.window, anchor='cEmoji', chat_id=c.chat_id)
    return None


def rule_feast_and_famine(c: ChatCtx) -> Optional[Dict]:
    """Metric 4 — volatility: weekly-volume CV high → bursts and silences."""
    wv = c.weekly_msgs()
    if len(wv) < 10:
        return None
    mu = _mean(wv)
    if not mu or mu <= 0:
        return None
    cv = _std(wv) / mu
    if cv < 1.2:
        return None
    effect = min(cv / 2.0, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['rhythm'], effect, 1.0, c.n_msgs, MIN_MSGS)
    sent = (f"This chat runs in bursts and silences — week-to-week volume swings wildly "
            f"(volatility {cv:.1f}×, well above a steady rhythm).")
    return _finding('feast-and-famine', 'chat', 'rhythm', 'notable', 'up',
                    'Bursts and silences', sent,
                    {'cv': round(cv, 2), 'weeks': len(wv)},
                    sc, conf, c.window, anchor='cVolume', chat_id=c.chat_id)


def rule_steady_drumbeat(c: ChatCtx) -> Optional[Dict]:
    """Metric 4 — volatility: low CV over many weeks → steady rhythm."""
    wv = c.weekly_msgs()
    if len(wv) < 26:
        return None
    mu = _mean(wv)
    if not mu or mu <= 0:
        return None
    cv = _std(wv) / mu
    if cv > 0.45:
        return None
    effect = min((0.45 - cv) / 0.45 + 0.5, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['rhythm'], effect, 1.0, c.n_msgs, MIN_MSGS)
    sent = (f"A steady drumbeat: week after week the volume barely wavers "
            f"(volatility just {cv:.2f}) — one of your most consistent chats.")
    return _finding('steady-drumbeat', 'chat', 'rhythm', 'fun', 'up',
                    'A steady drumbeat', sent,
                    {'cv': round(cv, 2), 'weeks': len(wv)},
                    sc, conf, c.window, anchor='cVolume', chat_id=c.chat_id)


# NOTE: ``rule_different_clocks`` was REMOVED in wave-2 (docs/WAVE2_REVIEW.md
# Part E item 2). Its input ``circadian_overlap`` — even after switching from
# cosine similarity to the overlap coefficient — ranges 0.79-0.99 across the
# corpus (min 0.79, p10 0.83, median 0.92), because two people in one
# conversation share an hour-of-day profile by construction. No dyad clears a
# defensible "different clocks" bar, so the rule (and its ``_soften_pursuit``
# post-pass, likewise removed) could never fire honestly. The metric itself is
# retained in ``extras.circadian_overlap`` for the future circadian card.


def rule_length_mirroring(c: ChatCtx) -> Optional[Dict]:
    """Metric 6 — turn-length elasticity: one stretches when the other does."""
    el = c.extras.get('turn_elasticity', {}) or {}
    best = None
    for u in c.participants:
        rec = el.get(u) or {}
        r, n = rec.get('r'), rec.get('n', 0)
        if r is None or n < 300:
            continue
        if r >= 0.35 and (best is None or r > best[1]):
            best = (u, r, n)
    if not best:
        return None
    u, r, n = best
    effect = min(r / 0.6, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], effect, 1.0, n, 300)
    sent = (f"Message lengths move together (r={r:.2f}): when one of you writes long, "
            f"the other stretches too — behavioral mirroring.")
    return _finding('length-mirroring', 'chat', 'dynamics', 'notable', 'up',
                    'Lengths in step', sent,
                    {'r': round(r, 3), 'n_pairs': int(n), 'responder': u},
                    sc, conf, c.window, anchor='cDepth', chat_id=c.chat_id)


def rule_openings_that_land(c: ChatCtx) -> Optional[Dict]:
    """Metric 2 — opening quality: one person's openings go much deeper."""
    oq = c.extras.get('opening_quality', {}) or {}
    a, b = c.participants
    da = (oq.get(a) or {}).get('median_msgs')
    db = (oq.get(b) or {}).get('median_msgs')
    na = (oq.get(a) or {}).get('n', 0)
    nb = (oq.get(b) or {}).get('n', 0)
    if not da or not db or na < 25 or nb < 25:
        return None
    for X, Y, dx, dy in ((a, b, da, db), (b, a, db, da)):
        if dy <= 0:
            continue
        if dx >= 1.8 * dy:
            ratio = dx / dy
            effect = min((ratio - 1) / 1.5, 1.0)
            sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], effect, 1.0,
                                    na + nb, 60)
            sent = (f"When {_name(X, c.owner)} start{'' if X==c.owner else 's'} the "
                    f"conversation it goes {_x(ratio)} deeper than when "
                    f"{_name(Y, c.owner)} do{'' if Y==c.owner else 'es'} — some openings just land.")
            return _finding('openings-that-land', 'chat', 'dynamics', 'notable', 'asym',
                            'Openings that land', sent,
                            {'opener': X, 'median_depth': round(dx, 1),
                             'partner_median_depth': round(dy, 1), 'ratio': round(ratio, 2)},
                            sc, conf, c.window, anchor='cInit', chat_id=c.chat_id)
    return None


def rule_repair(c: ChatCtx) -> Optional[Dict]:
    """Metric 3 — rupture/repair half-life: elastic vs brittle ties."""
    rr = c.extras.get('rupture_repair', {}) or {}
    n = rr.get('n_ruptures', 0)
    if n < 3:
        return None
    med = rr.get('median_repair_weeks')
    if med is None:
        return None
    if med <= 2:
        effect = 1.0
        sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], effect, 1.0, n, 3)
        sent = (f"This chat is elastic: after {int(n)} big drop-offs it bounced back within "
                f"~{med:.0f} week(s) each time. Silences here don't stick.")
        return _finding('quick-repair', 'chat', 'dynamics', 'notable', 'up',
                        'Bounces back fast', sent,
                        {'n_ruptures': int(n), 'median_repair_weeks': round(med, 1)},
                        sc, conf, c.window, anchor='cVolume', chat_id=c.chat_id)
    if med >= 6:
        effect = min(med / 12.0, 1.0)
        sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], effect, 1.0, n, 3)
        sent = (f"This chat is brittle: after a big drop-off it takes ~{med:.0f} weeks to "
                f"recover ({int(n)} such ruptures). Silences here linger.")
        return _finding('slow-repair', 'chat', 'dynamics', 'notable', 'down',
                        'Slow to recover', sent,
                        {'n_ruptures': int(n), 'median_repair_weeks': round(med, 1)},
                        sc, conf, c.window, anchor='cVolume', chat_id=c.chat_id)
    return None


# --------------------------------------------------------------------------- #
# M3.1 — capture-layer rules (calls, voice, reactions, edits, stickers).
# All-time; read the telegram / calls payload blocks, never the daily table.
# --------------------------------------------------------------------------- #

def _fmt_hms(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f'{s}s'
    if s < 3600:
        return f'{s // 60}m'
    h, m = s // 3600, (s % 3600) // 60
    return f'{h}h' + (f' {m}m' if m else '')


def rule_call_habit(c: ChatCtx) -> Optional[Dict]:
    """A heavy-call dyad — real time spent on calls, not just texting."""
    cl = c.calls
    if not cl:
        return None
    total = cl.get('total_calls', 0)
    answered = cl.get('answered', 0)
    talk_s = cl.get('total_talk_s', 0)
    if total < 30 or answered < 10 or talk_s < 3600:
        return None
    hours = talk_s / 3600.0
    effect = min(hours / 5.0, 1.0)   # 5h of talk time saturates
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['dynamics'], effect, 1.0,
                            total, 30)
    med = cl.get('median_talk_s', 0)
    sent = (f"You and {_name(c.partner, c.owner)} actually call: {total} calls, "
            f"{_fmt_hms(talk_s)} of talk time in total (median answered call "
            f"{_fmt_hms(med)}). This isn't a text-only relationship.")
    return _finding('call-habit', 'chat', 'dynamics', 'notable', 'record',
                    'You two get on the phone', sent,
                    {'total_calls': total, 'answered': answered,
                     'missed': cl.get('missed', 0), 'talk_hours': round(hours, 1),
                     'median_call_s': med},
                    sc, conf, c.window, anchor='cCallsTime', chat_id=c.chat_id)


def rule_voice_note_asymmetry(c: ChatCtx) -> Optional[Dict]:
    """One side talks (voice notes), the other types."""
    if not c.telegram:
        return None
    vn = c.telegram.get('voice_notes', {}) or {}
    a, b = c.participants
    na = (vn.get(a, {}) or {}).get('n', 0)
    nb = (vn.get(b, {}) or {}).get('n', 0)
    if na + nb < 40:
        return None
    for X, Y, nx, ny in ((a, b, na, nb), (b, a, nb, na)):
        if nx < 30 or ny <= 0 or nx < 2 * ny:
            continue
        ratio = nx / ny
        med = (vn.get(X, {}) or {}).get('median_s', 0)
        sc, E, V, conf = _score(CATEGORY_WEIGHTS['rhythm'], ratio, 3.0,
                                na + nb, 40)
        sent = (f"{_Name(X, c.owner)} send{'' if X==c.owner else 's'} the voice notes — "
                f"{nx} vs {ny} (median {_fmt_hms(med)} each) — while "
                f"{_name(Y, c.owner)} mostly type{'' if Y==c.owner else 's'}. "
                f"One of you talks, one of you pings.")
        return _finding('voice-note-asymmetry', 'chat', 'rhythm', 'notable', 'asym',
                        'One talks, one types', sent,
                        {'sender': X, 'voice_notes': nx, 'partner_voice_notes': ny,
                         'ratio': round(ratio, 2), 'median_s': med},
                        sc, conf, c.window, anchor='cTgVoice', chat_id=c.chat_id)
    return None


def rule_fast_reactor(c: ChatCtx) -> Optional[Dict]:
    """Reaction-latency asymmetry — one person is always watching."""
    if not c.telegram:
        return None
    rl = c.telegram.get('reaction_latency', {}) or {}
    a, b = c.participants
    ra, rb = rl.get(a, {}) or {}, rl.get(b, {}) or {}
    na, nb = ra.get('n', 0), rb.get('n', 0)
    ma, mb = ra.get('median_s', 0), rb.get('median_s', 0)
    if na < 50 or nb < 50 or ma <= 0 or mb <= 0:
        return None
    for X, Y, mx, my in ((a, b, ma, mb), (b, a, mb, ma)):
        if mx * 2 <= my:   # X reacts at least 2x faster than Y
            ratio = my / mx
            sc, E, V, conf = _score(CATEGORY_WEIGHTS['attention'], ratio, 3.0,
                                    min(na, nb), 50)
            sent = (f"{_Name(X, c.owner)} react{'' if X==c.owner else 's'} in a median "
                    f"{_fmt_hms(mx)}; {_name(Y, c.owner)} take{'' if Y==c.owner else 's'} "
                    f"{_fmt_hms(my)}. {_Name(X, c.owner)}"
                    f"{' are' if X==c.owner else ' is'} the one watching the chat.")
            return _finding('fast-reactor', 'chat', 'attention', 'notable', 'asym',
                            'One of you is always watching', sent,
                            {'faster': X, 'median_s': mx, 'partner_median_s': my,
                             'ratio': round(ratio, 2)},
                            sc, conf, c.window, anchor='cTgReactLat', chat_id=c.chat_id)
    return None


def rule_signature_emoji(c: ChatCtx) -> Optional[Dict]:
    """Fun: one person's reactions are basically a single signature emoji."""
    if not c.telegram:
        return None
    se = c.telegram.get('signature_emoji', {}) or {}
    best = None
    for u in c.participants:
        o = se.get(u, {}) or {}
        if o.get('n', 0) >= 100 and o.get('concentration', 0) >= 0.5 and o.get('top'):
            if best is None or o['concentration'] > best[1].get('concentration', 0):
                best = (u, o)
    if not best:
        return None
    u, o = best
    emoji, cnt = o['top'][0][0], o['top'][0][1]
    conc = o['concentration']
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['fun'], conc, 1.0, o['n'], 100)
    sent = (f"{_poss(u, c.owner).capitalize()} reactions are basically one emoji: "
            f"{emoji} is {_pct(conc)} of everything {_name(u, c.owner)} "
            f"react{'' if u!=c.owner else ''}s with ({cnt} times).")
    return _finding('signature-emoji', 'chat', 'rhythm', 'fun', 'record',
                    'A signature reaction', sent,
                    {'person': u, 'emoji': emoji, 'concentration': round(conc, 3),
                     'count': cnt, 'reactions': o['n']},
                    sc, conf, c.window, anchor='tgSigBox', chat_id=c.chat_id)


def rule_edit_reconsideration(c: ChatCtx) -> Optional[Dict]:
    """Additive to tg-second-guessing: edits that land >1h later = rereading,
    not typo-fixing."""
    if not c.telegram:
        return None
    el = c.telegram.get('edit_latency', {}) or {}
    best = None
    for u in c.participants:
        o = el.get(u, {}) or {}
        n = o.get('n', 0)
        if n < 200:
            continue
        late = (o.get('buckets', {}) or {}).get('>1h', 0)
        share = late / n if n else 0
        if share >= 0.10 and (best is None or share > best[2]):
            best = (u, o, share, late, n)
    if not best:
        return None
    u, o, share, late, n = best
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['language'], share, 0.25, n, 200)
    sent = (f"{_pct(share)} of {_poss(u, c.owner)} edits land more than an hour after "
            f"sending ({late} of {n}) — long past a typo fix. "
            f"{_Name(u, c.owner)}{' keep' if u==c.owner else ' keeps'} rereading.")
    return _finding('edit-reconsideration', 'chat', 'language', 'notable', 'up',
                    'Editing long after the moment', sent,
                    {'person': u, 'late_share': round(share, 3),
                     'late_edits': late, 'edits': n},
                    sc, conf, c.window, anchor='cTgEditLat', chat_id=c.chat_id)


def rule_sticker_vocabulary(c: ChatCtx) -> Optional[Dict]:
    """Fun: the two sticker vocabularies overlap heavily (shared language) or
    barely at all (separate worlds). Gated on >=100 stickers total."""
    if not c.telegram:
        return None
    st = c.telegram.get('stickers', {}) or {}
    total = st.get('total', 0)
    overlap = st.get('overlap')
    if total < 100 or overlap is None:
        return None
    if overlap >= 0.6:
        shared = st.get('shared', []) or []
        share_str = ' '.join(shared[:6])
        effect = min(overlap, 1.0)
        sent = (f"You two speak the same sticker language: {_pct(overlap)} of the "
                f"smaller vocabulary is shared"
                + (f" ({share_str})" if share_str else '') + ". A private dialect.")
        direction, title = 'up', 'A shared sticker language'
    elif overlap <= 0.15:
        effect = min((0.15 - overlap) / 0.15 + 0.5, 1.0)
        sent = (f"Your sticker worlds barely touch: only {_pct(overlap)} of the smaller "
                f"vocabulary overlaps — you each have your own set.")
        direction, title = 'down', 'Separate sticker worlds'
    else:
        return None
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['fun'], effect, 1.0, total, 100)
    return _finding('sticker-vocabulary', 'chat', 'rhythm', 'fun', direction,
                    title, sent,
                    {'overlap': round(overlap, 3), 'stickers_total': total},
                    sc, conf, c.window, anchor='tgStickerBox', chat_id=c.chat_id)


CHAT_RULES: Dict[str, Callable[[ChatCtx], Optional[Dict]]] = {
    'asymmetric-pursuit': rule_asymmetric_pursuit,
    'pursuit-withdrawal-trend': rule_pursuit_withdrawal_trend,
    'regime-change-story': rule_regime_change_story,
    'cooling-warming': rule_cooling_warming,
    'ending-restart-loop': rule_ending_restart_loop,
    'left-on-react': rule_left_on_react,
    'eager-waiter': rule_eager_waiter,
    'question-imbalance': rule_question_imbalance,
    'monologue-drift': rule_monologue_drift,
    'depth-mismatch': rule_depth_mismatch,
    'gottman-ratio': rule_gottman_ratio,
    'we-ness-shift': rule_we_ness_shift,
    'style-mirror': rule_style_mirror,
    'courtesy-asymmetry': rule_courtesy_asymmetry,
    'tg-second-guessing': rule_tg_second_guessing,
    'night-migration': rule_night_migration,
    'session-records': rule_session_records,
    'media-reciprocity-gap': rule_media_reciprocity_gap,
    # wave-2
    'unanswered-bids': rule_unanswered_bids,
    'shared-laughter': rule_shared_laughter,
    'laughing-alone': rule_laughing_alone,
    'feast-and-famine': rule_feast_and_famine,
    'steady-drumbeat': rule_steady_drumbeat,
    'length-mirroring': rule_length_mirroring,
    'openings-that-land': rule_openings_that_land,
    'rupture-repair': rule_repair,   # emits id quick-repair OR slow-repair
    # M3.1 capture-layer rules
    'call-habit': rule_call_habit,
    'voice-note-asymmetry': rule_voice_note_asymmetry,
    'fast-reactor': rule_fast_reactor,
    'signature-emoji': rule_signature_emoji,
    'edit-reconsideration': rule_edit_reconsideration,
    'sticker-vocabulary': rule_sticker_vocabulary,
}

# Rules whose inputs live entirely in the per-day daily table, so the browser
# can recompute them for the selected time range (docs/INSIGHTS.md §3.3). The JS
# rule registry in dashboard_template.py MIRRORS exactly this set; the smoke
# harness parity-checks the full-range JS output against precomputed ids. Rules
# NOT in this set need lifetime/extras/change-points and stay all-time.
WINDOWABLE_RULE_IDS = frozenset({
    'question-imbalance', 'gottman-ratio', 'courtesy-asymmetry',
    'media-reciprocity-gap', 'depth-mismatch', 'night-migration',
    'monologue-drift', 'we-ness-shift', 'eager-waiter', 'left-on-react',
    'unanswered-bids', 'feast-and-famine', 'steady-drumbeat',
})


# --------------------------------------------------------------------------- #
# Connected rules (§3.2)
# --------------------------------------------------------------------------- #

def _conn_window(p: Dict) -> Dict[str, Any]:
    r = p.get('range', {}) or {}
    return {'from': r.get('first_day'), 'to': r.get('last_day')}


def crule_attention_volume_mismatch(p: Dict) -> Optional[Dict]:
    lb = p.get('leaderboards', {}) or {}
    hier = lb.get('attention_hierarchy', []) or []
    sent = lb.get('by_sent_share', []) or []
    if not hier or len(sent) < 5:
        return None
    fastest = hier[0]
    if fastest.get('reply_n', 0) < 50:
        return None
    top5 = {r.get('name') for r in sent[:5]}
    if fastest.get('name') in top5:
        return None
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['attention'], 1.0, 1.0,
                            fastest.get('reply_n', 0), 50)
    sent_str = (f"You answer {fastest['name']} fastest of everyone "
                f"({fastest['reply_latency_median_min']:.1f} min median) — yet they aren't "
                f"in your top 5 by volume. Attention and volume disagree.")
    return _finding('attention-volume-mismatch', 'connected', 'attention', 'signal',
                    'asym', 'Fast to some, loud with others', sent_str,
                    {'fastest': fastest['name'],
                     'reply_latency_median_min': fastest['reply_latency_median_min'],
                     'reply_n': fastest['reply_n'],
                     # Words alongside message volume — an insight review that
                     # judges investment by message count should see word count too.
                     'words_sent': fastest.get('words_sent', 0)},
                    sc, conf, _conn_window(p), anchor='cxLatL')


def crule_concentration_trend(p: Dict) -> Optional[Dict]:
    gini = (p.get('monthly', {}) or {}).get('gini', {}) or {}
    contacts = p.get('contacts', [])
    months = sorted(gini.keys())
    if len(months) < 12 or len(contacts) < 10:
        return None
    last12 = months[-12:]
    a, bv = gini[last12[0]], gini[last12[-1]]
    slope = bv - a
    if abs(slope) < 0.05:
        return None
    effect = min(abs(slope) / 0.15, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['portfolio'], effect, 1.0,
                            len(months), 12)
    word = 'consolidating' if slope > 0 else 'broadening'
    sent = (f"Your texting is {word}: attention Gini went {a:.2f}→{bv:.2f} over "
            f"the last year.")
    return _finding('concentration-trend', 'connected', 'portfolio', 'notable',
                    'up' if slope > 0 else 'down', 'Where attention pools', sent,
                    {'gini_from': round(a, 3), 'gini_to': round(bv, 3),
                     'direction': word},
                    sc, conf, _conn_window(p), anchor='cxGini')


def crule_span_trend(p: Dict) -> Optional[Dict]:
    mb = (p.get('monthly', {}) or {}).get('bursts', {}) or {}
    months = sorted(mb.keys())
    if len(months) < 24:
        return None
    recent = _median([mb[m]['median_min'] for m in months[-12:]])
    prior = _median([mb[m]['median_min'] for m in months[-24:-12]])
    if not recent or not prior:
        return None
    change = (recent - prior) / prior
    if abs(change) < 0.30:
        return None
    effect = min(abs(change) / 0.6, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['portfolio'], effect, 1.0,
                            len(months), 24)
    word = 'growing' if change > 0 else 'shrinking'
    sent = (f"Your texting span is {word}: median engagement burst went "
            f"{prior:.1f}→{recent:.1f} min year-over-year.")
    return _finding('span-trend', 'connected', 'portfolio', 'notable',
                    'up' if change > 0 else 'down', 'Attention span shift', sent,
                    {'burst_min_prior': round(prior, 2), 'burst_min_recent': round(recent, 2),
                     'change': round(change, 2)},
                    sc, conf, _conn_window(p), anchor='cxBurstDur')


def crule_churn_wave(p: Dict) -> Optional[Dict]:
    churned = (p.get('monthly', {}) or {}).get('churned', {}) or {}
    if len(churned) < 12:
        return None
    vals = list(churned.values())
    med = _median(vals)
    if not med or med < 1:
        med = 1
    top_month = max(churned, key=churned.get)
    top = churned[top_month]
    if top < 2 * med or top < 4:
        return None
    effect = min((top / med) / 4.0, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['portfolio'], effect, 1.0,
                            len(churned), 12)
    sent = (f"{top_month} was a shedding month: {int(top)} regular contacts went quiet "
            f"at once — well above your monthly norm.")
    return _finding('churn-wave', 'connected', 'portfolio', 'notable', 'record',
                    'A shedding month', sent,
                    {'month': top_month, 'churned': int(top), 'monthly_median': med},
                    sc, conf, _conn_window(p), anchor='cxDyn')


def crule_funnel_readout(p: Dict) -> Optional[Dict]:
    fn = p.get('funnel', {}) or {}
    st = fn.get('stages', {}) or {}
    met, rec = st.get('met', 0), st.get('recurring', 0)
    if met < 20:
        return None
    rate = rec / met if met else 0
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['portfolio'], 1.0, 1.0, met, 20)
    sent = (f"Of {int(met)} new people, {int(rec)} became recurring — a "
            f"{_pct(rate)} stick rate.")
    return _finding('funnel-readout', 'connected', 'portfolio', 'notable', 'record',
                    'New-contact stick rate', sent,
                    {'met': int(met), 'recurring': int(rec), 'stick_rate': round(rate, 3)},
                    sc, conf, _conn_window(p), anchor='cxFunnel')


def crule_night_court(p: Dict) -> Optional[Dict]:
    night = (p.get('leaderboards', {}) or {}).get('night', []) or []
    if not night:
        return None
    total_night = sum(r.get('night_msgs', 0) for r in night)
    top = night[0]
    if total_night < 200:
        return None
    share = top.get('night_share', 0)
    if share < 0.60:
        return None
    effect = min(share, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['attention'], effect, 1.0,
                            total_night, 200)
    sent = (f"{top['name']} receives {_pct(share)} of your after-midnight messages. "
            f"The night belongs to one chat.")
    return _finding('night-court', 'connected', 'attention', 'notable', 'asym',
                    'The night belongs to one', sent,
                    {'contact': top['name'], 'night_share': round(share, 3),
                     'night_msgs': int(top.get('night_msgs', 0))},
                    sc, conf, _conn_window(p), anchor='cxNightL')


def crule_initiator_persona(p: Dict) -> Optional[Dict]:
    contacts = [c for c in p.get('contacts', []) if not c.get('gated')]
    gated = [c for c in contacts if c.get('sessions', 0) >= 5]
    if len(gated) < 10:
        return None
    hi = sum(1 for c in gated if c.get('initiation_share', 0) >= 0.6)
    lo = sum(1 for c in gated if c.get('initiation_share', 1) <= 0.4)
    n = len(gated)
    if hi / n >= 0.70:
        share, word, d = hi / n, 'starter', 'up'
        avg = _mean([c['initiation_share'] for c in gated])
        sent = (f"You're the starter: you open the conversation with {_pct(share)} of the "
                f"people in your life.")
    elif lo / n >= 0.70:
        share, word, d = lo / n, 'responder', 'down'
        avg = _mean([c['initiation_share'] for c in gated])
        sent = (f"You're the responder: other people open most of your conversations "
                f"({_pct(share)} of your contacts start more than you).")
    else:
        return None
    effect = min(share, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['attention'], effect, 1.0, n, 10)
    return _finding('initiator-persona', 'connected', 'attention', 'notable', d,
                    'Your opening move', sent,
                    {'persona': word, 'share_of_contacts': round(share, 3),
                     'n_contacts': n, 'avg_init_share': round(avg or 0, 3)},
                    sc, conf, _conn_window(p), anchor='cxInitL')


def crule_reciprocity_debts(p: Dict) -> Optional[Dict]:
    lb = p.get('leaderboards', {}) or {}
    surplus = lb.get('reciprocity_surplus', []) or []
    deficit = lb.get('reciprocity_deficit', []) or []
    cand = []
    for r in surplus[:3] + deficit[:3]:
        sent_n, recv = r.get('sent', 0), r.get('received', 0)
        tot = sent_n + recv
        if tot < 300:
            continue
        imb = abs(sent_n - recv) / tot
        if imb >= 0.25:
            cand.append((imb, r))
    if not cand:
        return None
    cand.sort(key=lambda x: -x[0])
    imb, r = cand[0]
    recip = r.get('reciprocity', 0)
    if recip >= 1:  # they send you more than you send back? reciprocity=sent/received
        sent = (f"Biggest imbalance: you send {r['name']} {recip:.1f}× what they send back "
                f"— you over-invest there.")
    else:
        inv = (r.get('received', 0) / r.get('sent', 1)) if r.get('sent') else 0
        sent = (f"Biggest imbalance: {r['name']} sends you {inv:.1f}× what you send back.")
    effect = min(imb / 0.5, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['portfolio'], effect, 1.0,
                            r.get('sent', 0) + r.get('received', 0), 300)
    return _finding('reciprocity-debts', 'connected', 'portfolio', 'notable', 'asym',
                    'An uneven ledger', sent,
                    {'contact': r['name'], 'reciprocity': round(recip, 2),
                     'sent': int(r.get('sent', 0)), 'received': int(r.get('received', 0)),
                     # Word counts beside the message ledger — same investment
                     # question, measured in words as well as messages.
                     'words_sent': int(r.get('words_sent', 0)),
                     'words_recv': int(r.get('words_recv', 0)),
                     'imbalance': round(imb, 3)},
                    sc, conf, _conn_window(p), anchor='connRecipBox')


def crule_deep_talk_budget(p: Dict) -> Optional[Dict]:
    contacts = p.get('contacts', [])
    deep = [(c.get('session_types', {}).get('deep_talk', 0), c.get('name'))
            for c in contacts]
    deep = [(n, name) for n, name in deep if n > 0]
    total = sum(n for n, _ in deep)
    if total < 30 or not deep:
        return None
    deep.sort(reverse=True)
    top2 = sum(n for n, _ in deep[:2])
    share = top2 / total
    if share < 0.60:
        return None
    names = ' and '.join(name for _, name in deep[:2])
    effect = min(share, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['portfolio'], effect, 1.0, total, 30)
    sent = (f"Nearly all your deep conversations happen with {names} — {_pct(share)} "
            f"of them.")
    return _finding('deep-talk-budget', 'connected', 'portfolio', 'notable', 'asym',
                    'Where the deep talks go', sent,
                    {'contacts': [name for _, name in deep[:2]],
                     'share': round(share, 3), 'total_deep': int(total)},
                    sc, conf, _conn_window(p), anchor='cxTypeMix')


def crule_chameleon_index(p: Dict) -> Optional[Dict]:
    cs = p.get('code_switching', {}) or {}
    per = cs.get('per_contact', []) or []
    if len(per) < 8:
        return None
    lang_var = cs.get('lang_variance', 0)
    emoji_var = cs.get('emoji_rate_variance', 0)
    # tuned population threshold: flag noticeably high shape-shifting
    if lang_var < 0.05 and emoji_var < 0.004:
        return None
    # two most different contacts by combined style distance
    def dist(x, y):
        lx = x.get('lang_mix', {}) or {}
        ly = y.get('lang_mix', {}) or {}
        dl = sum(abs(lx.get(k, 0) - ly.get(k, 0)) for k in ('georgian', 'english', 'mixed'))
        de = abs(x.get('emoji_rate', 0) - y.get('emoji_rate', 0)) * 20
        dw = abs(x.get('avg_word_len', 0) - y.get('avg_word_len', 0)) / 5.0
        return dl + de + dw
    best = None
    top = per[:15]
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            d = dist(top[i], top[j])
            if best is None or d > best[0]:
                best = (d, top[i]['name'], top[j]['name'])
    if not best:
        return None
    effect = min(lang_var / 0.15, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['language'], effect, 1.0, len(per), 8)
    sent = (f"You write to {best[1]} and {best[2]} like two different people — emoji, "
            f"length and language all switch.")
    return _finding('chameleon-index', 'connected', 'language', 'notable', 'asym',
                    'A different you per person', sent,
                    {'contact_a': best[1], 'contact_b': best[2],
                     'lang_variance': round(lang_var, 4)},
                    sc, conf, _conn_window(p), anchor='connMirrorBox')


# Cross-variant rules (need BOTH platforms) — emitted into the 'all' list.

def _owner_style(p: Dict) -> Dict[str, float]:
    daily = p.get('daily', {}) or {}
    msgs = words = emoji = night = 0
    for cell in daily.values():
        msgs += cell.get('msgs', 0)
        words += cell.get('words', 0)
        emoji += cell.get('emoji', 0)
        # Connected daily cells are flat owner cells carrying ``night_msgs`` (no
        # ``hours`` histogram — that lives only in per-chat daily). The old
        # ``cell.get('hours')`` therefore always summed to 0, making the night
        # dimension of ``platform-persona`` dead. Read ``night_msgs`` directly.
        night += cell.get('night_msgs', 0)
    return {
        'msgs': msgs,
        'emoji_rate': emoji / words if words else 0,
        'words_per_msg': words / msgs if msgs else 0,
        'night_share': night / msgs if msgs else 0,
    }


def crule_platform_focus(ig: Dict, tg: Dict) -> Optional[Dict]:
    if not ig or not tg:
        return None
    if (ig.get('totals', {}).get('messages_sent', 0) < 5000 or
            tg.get('totals', {}).get('messages_sent', 0) < 5000):
        return None
    pa = (ig.get('attention', {}) or {}).get('parallel_texting_rate', 0)
    pb = (tg.get('attention', {}) or {}).get('parallel_texting_rate', 0)
    lo, hi = sorted((pa, pb))
    if lo <= 0 or hi < 2 * lo:
        return None
    ig_first = pa >= pb
    A, pA, B, pB = ('Instagram', pa, 'Telegram', pb) if ig_first else ('Telegram', pb, 'Instagram', pa)
    ratio = hi / lo
    effect = min(ratio / 3.0, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['platform'], effect, 1.0,
                            min(ig['totals']['messages_sent'], tg['totals']['messages_sent']),
                            5000)
    sent = (f"On {A} you juggle ({_pct(pA, 1)} of windows hold two chats at once); on {B} "
            f"you focus ({_pct(pB, 1)}). Two different attention modes per platform.")
    return _finding('platform-focus', 'connected', 'platform', 'signal', 'asym',
                    'One platform to juggle, one to focus', sent,
                    {'instagram_parallel': round(pa, 3), 'telegram_parallel': round(pb, 3),
                     'ratio': round(ratio, 2)},
                    sc, conf, _conn_window(ig), anchor='cxFocus')


def crule_platform_persona(ig: Dict, tg: Dict) -> Optional[Dict]:
    if not ig or not tg:
        return None
    si, st = _owner_style(ig), _owner_style(tg)
    if si['msgs'] < 5000 or st['msgs'] < 5000:
        return None
    dims = []
    for key, label in (('emoji_rate', 'emoji'), ('words_per_msg', 'message length'),
                       ('night_share', 'night texting')):
        a, b = si[key], st[key]
        base = max(a, b)
        if base <= 0:
            continue
        rel = abs(a - b) / base
        dims.append((rel, label, key, a, b))
    dims.sort(reverse=True)
    if not dims or dims[0][0] < 0.50:
        return None
    top = dims[0]
    effect = min(top[0], 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['platform'], effect, 1.0,
                            min(si['msgs'], st['msgs']), 5000)
    def fmt(k, v):
        return _pct(v, 1) if k in ('emoji_rate', 'night_share') else f'{v:.1f}'
    sent = (f"Instagram-you and Telegram-you are different texters: {top[1]} differs by "
            f"{_pct(top[0])} ({fmt(top[2], top[3])} vs {fmt(top[2], top[4])}).")
    return _finding('platform-persona', 'connected', 'platform', 'notable', 'asym',
                    'Two texting personas', sent,
                    {'dimension': top[1], 'instagram': round(top[3], 4),
                     'telegram': round(top[4], 4), 'rel_diff': round(top[0], 3)},
                    sc, conf, _conn_window(ig), anchor='cxFocus')


def crule_drifting_away(p: Dict) -> Optional[Dict]:
    """Metric 8 — attention debt: a top-volume contact you now answer >=2x slower."""
    debt = p.get('attention_debt', []) or []
    cand = [d for d in debt if d.get('volume_rank', 999) < 15
            and (d.get('ratio') or 0) >= 2.0]
    if not cand:
        return None
    cand.sort(key=lambda d: -(d.get('ratio') or 0))
    d = cand[0]
    ratio = d['ratio']
    effect = min(ratio / 4.0, 1.0)
    sc, E, V, conf = _score(CATEGORY_WEIGHTS['attention'], effect, 1.0, 60, 60)
    sent = (f"You're drifting from {d['name']}: your replies there went from "
            f"~{d['earlier_median_min']:.0f} to ~{d['recent_median_min']:.0f} min "
            f"({_x(ratio)} slower) even though they're a top-15 chat.")
    return _finding('drifting-away', 'connected', 'attention', 'signal', 'down',
                    'Drifting from someone close', sent,
                    {'contact': d['name'], 'earlier_median_min': d['earlier_median_min'],
                     'recent_median_min': d['recent_median_min'], 'ratio': ratio},
                    sc, conf, _conn_window(p), anchor='cxLatL')


def crule_dormancy_resilience(p: Dict) -> Optional[Dict]:
    """Metric 9 — elastic vs brittle ties: do revived chats recover?"""
    dm = p.get('dormancy', {}) or {}
    revivals = dm.get('revivals', 0)
    share = dm.get('recover_share')
    if revivals < 5 or share is None:
        return None
    if share >= 0.70:
        effect = min(share, 1.0)
        sc, E, V, conf = _score(CATEGORY_WEIGHTS['portfolio'], effect, 1.0, revivals, 5)
        sent = (f"Your ties are elastic: {_pct(share)} of the {int(revivals)} chats that "
                f"went quiet for a month came roaring back afterwards.")
        return _finding('elastic-ties', 'connected', 'portfolio', 'notable', 'up',
                        'Ties that bounce back', sent,
                        {'revivals': int(revivals), 'recover_share': round(share, 3)},
                        sc, conf, _conn_window(p), anchor='cxDyn')
    if share <= 0.30:
        effect = min(1.0 - share, 1.0)
        sc, E, V, conf = _score(CATEGORY_WEIGHTS['portfolio'], effect, 1.0, revivals, 5)
        sent = (f"Your ties are brittle: only {_pct(share)} of the {int(revivals)} chats that "
                f"went quiet ever recovered. When they lapse, they mostly stay lapsed.")
        return _finding('brittle-ties', 'connected', 'portfolio', 'notable', 'down',
                        'Ties that stay lapsed', sent,
                        {'revivals': int(revivals), 'recover_share': round(share, 3)},
                        sc, conf, _conn_window(p), anchor='cxDyn')
    return None


def crule_novelty(p: Dict) -> Optional[Dict]:
    """Metric 10 — explorer vs consolidator: share of new texting to young ties."""
    nv = p.get('novelty', {}) or {}
    tn = nv.get('trailing_6mo')
    n_contacts = nv.get('n_contacts', 0)
    if tn is None or n_contacts < 15:
        return None
    if tn >= 0.25:
        effect = min(tn / 0.5, 1.0)
        sc, E, V, conf = _score(CATEGORY_WEIGHTS['portfolio'], effect, 1.0, n_contacts, 15)
        sent = (f"You're an explorer: {_pct(tn)} of what you've sent lately goes to "
                f"contacts under three months old. Fresh connections keep arriving.")
        return _finding('explorer-vs-consolidator', 'connected', 'portfolio', 'notable',
                        'up', 'An explorer right now', sent,
                        {'trailing_novelty': round(tn, 3), 'mode': 'explorer'},
                        sc, conf, _conn_window(p), anchor='cxFunnel')
    if tn <= 0.03:
        effect = min((0.03 - tn) / 0.03 + 0.5, 1.0)
        sc, E, V, conf = _score(CATEGORY_WEIGHTS['portfolio'], effect, 1.0, n_contacts, 15)
        sent = (f"You're a consolidator: barely {_pct(tn)} of what you send goes to new "
                f"faces — your attention stays with the people you already know.")
        return _finding('explorer-vs-consolidator', 'connected', 'portfolio', 'notable',
                        'down', 'A consolidator right now', sent,
                        {'trailing_novelty': round(tn, 3), 'mode': 'consolidator'},
                        sc, conf, _conn_window(p), anchor='cxFunnel')
    return None


CONNECTED_RULES: Dict[str, Callable[[Dict], Optional[Dict]]] = {
    'attention-volume-mismatch': crule_attention_volume_mismatch,
    'drifting-away': crule_drifting_away,
    'dormancy-resilience': crule_dormancy_resilience,
    'novelty': crule_novelty,
    'concentration-trend': crule_concentration_trend,
    'span-trend': crule_span_trend,
    'churn-wave': crule_churn_wave,
    'funnel-readout': crule_funnel_readout,
    'night-court': crule_night_court,
    'initiator-persona': crule_initiator_persona,
    'reciprocity-debts': crule_reciprocity_debts,
    'deep-talk-budget': crule_deep_talk_budget,
    'chameleon-index': crule_chameleon_index,
}


# --------------------------------------------------------------------------- #
# Engine — run registry, sort, cap
# --------------------------------------------------------------------------- #

def _rank_and_cap(findings: List[Dict], cap: int) -> List[Dict]:
    findings = [f for f in findings if f is not None]
    # deterministic: score desc, then rule id asc, then chat id
    findings.sort(key=lambda f: (-f['score'], f['id'], f.get('chat_id') or ''))
    return findings[:cap]


def run_chat(chat_id: str, payload: Dict, owner: str) -> List[Dict]:
    """Run every chat rule over one chat payload. Groups get no findings."""
    if payload.get('is_group'):
        return []
    if len(payload.get('participants', [])) < 2:
        return []
    c = ChatCtx(chat_id, payload, owner)
    if c.n_msgs < MIN_MSGS:
        return []
    out = []
    for rid, fn in CHAT_RULES.items():
        try:
            r = fn(c)
        except Exception:
            r = None
        if r:
            out.append(r)
    # NOTE: the ``_soften_pursuit`` post-pass (which capped 'asymmetric-pursuit'
    # severity when 'different-clocks' fired) was removed alongside the
    # 'different-clocks' rule — see docs/WAVE2_REVIEW.md Part E item 2.
    return _rank_and_cap(out, CHAT_CAP)


def run_connected(payload: Dict,
                  ig: Optional[Dict] = None,
                  tg: Optional[Dict] = None) -> List[Dict]:
    """Run connected rules over one variant. When ``ig`` and ``tg`` are both
    provided (the 'all' variant), also run the cross-platform rules."""
    out = []
    for rid, fn in CONNECTED_RULES.items():
        try:
            r = fn(payload)
        except Exception:
            r = None
        if r:
            out.append(r)
    if ig and tg:
        for fn in (crule_platform_focus, crule_platform_persona):
            try:
                r = fn(ig, tg)
            except Exception:
                r = None
            if r:
                out.append(r)
    return _rank_and_cap(out, CONNECTED_CAP)


def detect_owner(payloads: Dict[str, Dict]) -> Optional[str]:
    """Owner = participant present in the most (dyadic) chats."""
    from collections import Counter
    counter: Counter = Counter()
    for p in payloads.values():
        if p.get('is_group'):
            continue
        for name in set(p.get('participants', [])[:2]):
            counter[name] += 1
    return counter.most_common(1)[0][0] if counter else None
