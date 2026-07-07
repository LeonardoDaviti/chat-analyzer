"""Tests for group-chat (3+ participants) support.

Covers: group detection, thread_path dedup, group member_stats + reaction /
reply matrices, and the dashboard Others-merging in daily aggregates.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

import main
from src.analyzer import ChatAnalyzer
from src.group_metrics import compute_group_metrics, order_members_by_volume
from src.dashboard_export import build_daily_aggregates, choose_participants, OTHERS_KEY
from src.timeutil import DEFAULT_TIMEZONE

TZ = ZoneInfo(DEFAULT_TIMEZONE)
BASE = datetime(2025, 1, 6, 12, 0, 0, tzinfo=TZ)  # a Monday


def _msg(sender, offset_min, content='', reactions=None):
    m = {
        'sender_name': sender,
        'timestamp_ms': int((BASE + timedelta(minutes=offset_min)).timestamp() * 1000),
        'content': content,
        'language': 'english' if content else 'media',
    }
    if reactions is not None:
        m['reactions'] = [{'reaction': 'x', 'actor': a} for a in reactions]
    return m


# A tiny 4-member group (D is a lurker), all in one session.
GROUP_MSGS = [
    _msg('A', 0, 'hello there', reactions=['B', 'C']),
    _msg('B', 1, 'hi', reactions=['A']),
    _msg('C', 2, 'sup?'),                # question
    _msg('A', 3, 'not much'),
    _msg('B', 4, 'ok cool'),
]
MEMBERS = ['A', 'B', 'C', 'D']


def _chat_data(participants, messages):
    return {'participants': [{'name': p} for p in participants],
            'messages': messages, 'title': 'The Group'}


# --------------------------------------------------------------------------- #
# Group detection
# --------------------------------------------------------------------------- #

class TestGroupDetection:
    def test_three_plus_is_group(self):
        a = ChatAnalyzer(_chat_data(['A', 'B', 'C'], GROUP_MSGS), 'A')
        assert a.is_group is True
        out = a.analyze()
        assert out.get('is_group') is True
        assert 'group_metrics' in out
        assert out['member_count'] == 3
        # The V3/V4 pair metrics must NOT be computed for groups.
        for k in ('initiation', 'bid_response', 'change_points',
                  'response_times', 'final_word_dominance'):
            assert k not in out

    def test_two_is_not_group(self):
        a = ChatAnalyzer(_chat_data(['A', 'B'], GROUP_MSGS), 'A')
        assert a.is_group is False
        out = a.analyze()
        assert not out.get('is_group')
        assert 'group_metrics' not in out
        assert 'initiation' in out  # pair metrics present for 1v1

    def test_participants_active_first(self):
        # A and B send 2 each, C 1, D none -> D last.
        order = order_members_by_volume(GROUP_MSGS, MEMBERS)
        assert order[:2] == ['A', 'B'] or order[:2] == ['B', 'A']
        assert order[-1] == 'D'


# --------------------------------------------------------------------------- #
# group_metrics content
# --------------------------------------------------------------------------- #

class TestGroupMetrics:
    def setup_method(self):
        self.gm = compute_group_metrics(GROUP_MSGS, MEMBERS)

    def test_member_stats_counts(self):
        ms = self.gm['member_stats']
        assert ms['A']['msgs'] == 2 and ms['A']['words'] == 4
        assert ms['B']['msgs'] == 2 and ms['B']['words'] == 3
        assert ms['C']['msgs'] == 1
        assert ms['D']['msgs'] == 0
        # shares sum to 1 across the 5 real messages
        assert abs(ms['A']['share'] - 0.4) < 1e-9
        assert abs(ms['C']['share'] - 0.2) < 1e-9
        assert ms['C']['questions_per_100'] == 100.0

    def test_reactions(self):
        ms = self.gm['member_stats']
        assert ms['B']['reactions_given'] == 1
        assert ms['C']['reactions_given'] == 1
        assert ms['A']['reactions_given'] == 1
        assert ms['A']['reactions_received'] == 2
        assert ms['B']['reactions_received'] == 1

    def test_reaction_matrix(self):
        rm = self.gm['reaction_matrix']
        assert rm['B']['A'] == 1
        assert rm['C']['A'] == 1
        assert rm['A']['B'] == 1

    def test_reply_matrix(self):
        rp = self.gm['reply_matrix']
        # sender sequence A,B,C,A,B -> B<-A twice, C<-B, A<-C
        assert rp['B']['A'] == 2
        assert rp['C']['B'] == 1
        assert rp['A']['C'] == 1

    def test_initiations_endings_lurkers(self):
        ms = self.gm['member_stats']
        assert ms['A']['initiations'] == 1  # opener
        assert ms['B']['endings'] == 1      # closer
        assert self.gm['lurkers'] == ['D']
        assert self.gm['member_count'] == 4


# --------------------------------------------------------------------------- #
# Dedup by thread_path
# --------------------------------------------------------------------------- #

def _write_chat(dirpath: Path, thread_path: str, n_bytes_content: int):
    dirpath.mkdir(parents=True, exist_ok=True)
    payload = {
        'participants': [{'name': 'A'}, {'name': 'B'}, {'name': 'C'}],
        'thread_path': thread_path,
        'title': 'g',
        'messages': [{'sender_name': 'A', 'timestamp_ms': 1,
                      'content': 'x' * n_bytes_content}],
    }
    (dirpath / 'message_1.json').write_text(json.dumps(payload), encoding='utf-8')


class TestDedup:
    def test_dedup_keeps_biggest(self, tmp_path):
        big = tmp_path / 'SemperFi'
        small = tmp_path / 'sempeghpghaii_123'
        other = tmp_path / 'unarebi_999'
        _write_chat(big, 'inbox/semp', 5000)
        _write_chat(small, 'inbox/semp', 50)      # same thread_path -> duplicate
        _write_chat(other, 'inbox/unarebi', 100)  # distinct

        discovered = [('E', str(small)), ('E', str(big)), ('E', str(other))]
        kept, skipped = main.dedup_by_thread_path(discovered)

        kept_dirs = {d for _, d in kept}
        assert str(big) in kept_dirs
        assert str(other) in kept_dirs
        assert str(small) not in kept_dirs
        assert skipped == [(str(big), str(small))]

    def test_missing_thread_path_never_dropped(self, tmp_path):
        d = tmp_path / 'nothreadpath'
        d.mkdir()
        (d / 'message_1.json').write_text(
            json.dumps({'participants': [{'name': 'A'}, {'name': 'B'}],
                        'messages': []}), encoding='utf-8')
        kept, skipped = main.dedup_by_thread_path([('E', str(d))])
        assert len(kept) == 1 and not skipped


# --------------------------------------------------------------------------- #
# Others-merging in the dashboard daily aggregates
# --------------------------------------------------------------------------- #

class TestOthersMerging:
    def test_untracked_folds_into_others(self):
        # Track only A and B; C must fold into Others.
        daily = build_daily_aggregates(GROUP_MSGS, ['A', 'B'],
                                       others_key=OTHERS_KEY)
        totals = {}
        for day in daily.values():
            for user, cell in day.items():
                totals[user] = totals.get(user, 0) + cell['msgs']
        assert totals['A'] == 2
        assert totals['B'] == 2
        assert totals[OTHERS_KEY] == 1  # C's single message

    def test_no_others_key_drops_untracked(self):
        # Without others_key (1v1 behaviour), C is dropped entirely.
        daily = build_daily_aggregates(GROUP_MSGS, ['A', 'B'])
        for day in daily.values():
            assert OTHERS_KEY not in day
            assert 'C' not in day

    def test_choose_participants_group_limit(self):
        top = choose_participants(GROUP_MSGS, ['A', 'B', 'C', 'D'], limit=6)
        assert top[:2] in (['A', 'B'], ['B', 'A'])
        assert 'D' in top  # padded from fallback (D never sent)
        assert len(top) <= 6
