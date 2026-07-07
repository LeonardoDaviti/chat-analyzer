"""
V4 Metrics Visualizations - Relationship dynamics.

One matplotlib chart per V4 metric, styled consistently with
``visualizer_v3`` (PNG, dpi=150). Every plot is wrapped in try/except so a
single failure never kills the rest of the batch, and charts whose metric has
``n == 0`` are skipped (with a printed note). The change-point chart is the
centerpiece and renders even with zero change-points.
"""

import matplotlib
matplotlib.use('Agg')  # headless-safe
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

from src.output_manager import truncate_component


class MetricsVisualizerV4:
    """Generate V4 relationship-dynamics visualizations."""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        plt.rcParams['font.size'] = 10
        plt.rcParams['figure.figsize'] = (12, 6)

    # ------------------------------------------------------------------ #
    def generate_all(self, analysis: dict, chat_name: str):
        """Render every V4 chart. Each is isolated in its own try/except."""
        print("  Generating V4 relationship-dynamics visualizations...")
        chat_name = truncate_component(chat_name, max_bytes=60)

        users = analysis.get('participants', [])
        if not users and 'message_counts' in analysis:
            users = list(analysis['message_counts'].keys())

        # Group chats: skip the pair charts and render a single group overview.
        if analysis.get('group_metrics'):
            print("  [group] skipping V4 pair charts; rendering group overview")
            try:
                self._plot_group_overview(analysis['group_metrics'], chat_name)
            except Exception as e:
                print(f"    [error] group overview chart failed: {e}")
            print("  V4 visualizations complete.")
            return

        charts = [
            ('initiation', self._plot_initiation),
            ('question_asymmetry', self._plot_questions),
            ('bid_response', self._plot_bids),
            ('affect_economy', self._plot_affect),
            ('circadian', self._plot_circadian),
            ('repair', self._plot_repair),
            ('double_texting', self._plot_double_texting),
            ('half_life', self._plot_half_life),
        ]
        for key, fn in charts:
            metric = analysis.get(key)
            if metric is None:
                continue
            if metric.get('n', 0) == 0:
                print(f"    [skip] {key}: n=0 (no data)")
                continue
            try:
                fn(metric, users, chat_name)
            except Exception as e:
                print(f"    [error] {key} chart failed: {e}")

        # Change-points render even at n=0 (annotates "no changes").
        try:
            self._plot_change_points(analysis.get('change_points', {}), chat_name)
        except Exception as e:
            print(f"    [error] change_points chart failed: {e}")

        print("  V4 visualizations complete.")

    # ------------------------------------------------------------------ #
    @staticmethod
    def _sorted_buckets(series: dict) -> list:
        return sorted(series.keys())

    def _save(self, fig, name: str):
        fig.savefig(self.output_dir / name, dpi=150, bbox_inches='tight')
        plt.close(fig)

    # Group overview (member share + reaction matrix) -------------------- #
    def _plot_group_overview(self, gm, chat_name):
        """Single figure: member message-share bar + who-reacts-to-whom heatmap."""
        member_stats = gm.get('member_stats', {})
        reaction_matrix = gm.get('reaction_matrix', {})
        # Members ordered by share, most active first.
        members = sorted(member_stats.keys(),
                         key=lambda u: -member_stats[u].get('msgs', 0))

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, max(5, 0.5 * len(members) + 2)))

        # Left: horizontal message-share bar.
        shares = [member_stats[u].get('share', 0.0) * 100 for u in members]
        y = np.arange(len(members))
        ax1.barh(y, shares, color='#4DB6AC', edgecolor='black')
        ax1.set_yticks(y)
        ax1.set_yticklabels(members)
        ax1.invert_yaxis()
        ax1.set_xlabel('Message share (%)')
        ax1.set_title(f'Member Message Share ({len(members)} members)',
                      fontsize=13, fontweight='bold')
        for i, v in enumerate(shares):
            ax1.text(v, i, f' {v:.1f}%', va='center', fontsize=9)

        # Right: reaction matrix heatmap (giver row -> receiver column).
        n = len(members)
        idx = {u: i for i, u in enumerate(members)}
        mat = np.zeros((n, n))
        for giver, row in reaction_matrix.items():
            if giver not in idx:
                continue
            for receiver, cnt in row.items():
                if receiver in idx:
                    mat[idx[giver]][idx[receiver]] = cnt
        im = ax2.imshow(mat, cmap='magma', aspect='auto')
        ax2.set_xticks(range(n))
        ax2.set_yticks(range(n))
        ax2.set_xticklabels(members, rotation=45, ha='right', fontsize=8)
        ax2.set_yticklabels(members, fontsize=8)
        ax2.set_xlabel('Reacted to (receiver)')
        ax2.set_ylabel('Reactor (giver)')
        ax2.set_title('Who Reacts to Whom', fontsize=13, fontweight='bold')
        fig.colorbar(im, ax=ax2, fraction=0.046, pad=0.04, label='Reactions')
        for i in range(n):
            for j in range(n):
                if mat[i][j] > 0:
                    ax2.text(j, i, int(mat[i][j]), ha='center', va='center',
                             color='white' if mat[i][j] > mat.max() / 2 else 'black',
                             fontsize=7)

        fig.suptitle(f'Group Overview - {chat_name}', fontsize=15, fontweight='bold')
        plt.tight_layout()
        self._save(fig, f'{chat_name}_group_overview.png')

    # 1. Initiation ------------------------------------------------------ #
    def _plot_initiation(self, metric, users, chat_name):
        per_user = metric['per_user']
        series = metric['series']
        buckets = self._sorted_buckets(series)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9))
        colors = plt.cm.Set2(np.linspace(0, 1, max(len(users), 1)))

        # Monthly initiation share (stacked bars).
        bottom = np.zeros(len(buckets))
        for u, c in zip(users, colors):
            shares = [series[b].get(u, {}).get('share', 0.0) for b in buckets]
            ax1.bar(buckets, shares, bottom=bottom, label=u, color=c, edgecolor='white')
            bottom += np.array(shares)
        ax1.set_ylabel('Initiation share')
        ax1.set_title('Who Opens Conversations (monthly initiation share)',
                      fontsize=13, fontweight='bold')
        ax1.set_ylim(0, 1)
        ax1.tick_params(axis='x', rotation=45)
        ax1.legend(loc='upper right', fontsize=8)
        for u in users:
            lifetime = per_user.get(u, {}).get('initiation_share', 0.0)
            ax1.plot([], [], ' ', label=f'{u}: {lifetime:.0%} lifetime')

        # Reopen latency (second subplot, never dual axis).
        lat = [per_user.get(u, {}).get('median_reopen_latency_hours', 0.0) for u in users]
        ax2.bar(users, lat, color=colors, edgecolor='black')
        ax2.set_ylabel('Median reopen latency (h)')
        ax2.set_title('Median Silence Before Reopening', fontsize=12, fontweight='bold')
        for i, v in enumerate(lat):
            ax2.text(i, v, f'{v:.1f}h', ha='center', va='bottom', fontweight='bold')

        fig.suptitle(f'Initiation Dynamics - {chat_name}', fontsize=14, fontweight='bold')
        plt.tight_layout()
        self._save(fig, f'{chat_name}_v4_initiation.png')

    # 2. Questions ------------------------------------------------------- #
    def _plot_questions(self, metric, users, chat_name):
        per_user = metric['per_user']
        series = metric['series']
        buckets = self._sorted_buckets(series)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9))
        colors = plt.cm.Set2(np.linspace(0, 1, max(len(users), 1)))

        rates = [per_user.get(u, {}).get('questions_per_100_msgs', 0.0) for u in users]
        bars = ax1.bar(users, rates, color=colors, edgecolor='black')
        ax1.set_ylabel('Questions per 100 messages')
        ax1.set_title('Curiosity Index (question rate per user)',
                      fontsize=13, fontweight='bold')
        for bar, u, v in zip(bars, users, rates):
            ar = per_user.get(u, {}).get('answered_rate', 0.0)
            ax1.text(bar.get_x() + bar.get_width() / 2, v,
                     f'{v:.1f}\n({ar:.0%} answered)', ha='center', va='bottom', fontsize=9)

        for u, c in zip(users, colors):
            ir = [series[b].get(u, {}).get('ignored_rate', 0.0) for b in buckets]
            ax2.plot(buckets, ir, marker='o', label=u, color=c, linewidth=2)
        ax2.set_ylabel('Ignored-question rate')
        ax2.set_title('Monthly Ignored-Question Rate (micro-rejections)',
                      fontsize=12, fontweight='bold')
        ax2.set_ylim(0, 1)
        ax2.tick_params(axis='x', rotation=45)
        ax2.legend(fontsize=8)

        plt.tight_layout()
        self._save(fig, f'{chat_name}_v4_questions.png')

    # 3. Bids ------------------------------------------------------------ #
    def _plot_bids(self, metric, users, chat_name):
        per_user = metric['per_user']
        series = metric['series']
        buckets = self._sorted_buckets(series)

        fig, ax = plt.subplots(figsize=(12, 6))
        colors = plt.cm.Set2(np.linspace(0, 1, max(len(users), 1)))
        for u, c in zip(users, colors):
            vals = [series[b].get(u, {}).get('partner_turned_toward_rate', 0.0) for b in buckets]
            ax.plot(buckets, vals, marker='o', label=u, color=c, linewidth=2)
            lifetime = per_user.get(u, {}).get('partner_turned_toward_rate', 0.0)
            ax.axhline(lifetime, color=c, linestyle='--', alpha=0.5)
            ax.text(0.01, lifetime, f'{u}: {lifetime:.0%} lifetime',
                    transform=ax.get_yaxis_transform(), fontsize=8, va='bottom', color=c)

        ax.set_ylabel('Turning-toward rate (bids engaged)')
        ax.set_title('Bid-and-Response: Monthly Turning-Toward Rate\n'
                     '(Gottman masters ~86%, disasters ~33%)',
                     fontsize=13, fontweight='bold')
        ax.set_ylim(0, 1)
        ax.axhspan(0.86, 1.0, alpha=0.08, color='green')
        ax.axhspan(0.0, 0.33, alpha=0.08, color='red')
        ax.tick_params(axis='x', rotation=45)
        ax.legend(fontsize=8)
        plt.tight_layout()
        self._save(fig, f'{chat_name}_v4_bids.png')

    # 4. Affect ---------------------------------------------------------- #
    def _plot_affect(self, metric, users, chat_name):
        per_user = metric['per_user']
        series = metric['series']
        buckets = self._sorted_buckets(series)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9))

        x = np.arange(len(users))
        w = 0.35
        given = [per_user.get(u, {}).get('reactions_given', 0) for u in users]
        received = [per_user.get(u, {}).get('reactions_received', 0) for u in users]
        ax1.bar(x - w / 2, given, w, label='Given', color='#4C9F70', edgecolor='black')
        ax1.bar(x + w / 2, received, w, label='Received', color='#E4A11B', edgecolor='black')
        ax1.set_xticks(x)
        ax1.set_xticklabels(users)
        ax1.set_ylabel('Reactions')
        ax1.set_title('Affect Economy: Reactions Given vs Received',
                      fontsize=13, fontweight='bold')
        ax1.legend()

        colors = plt.cm.Set2(np.linspace(0, 1, max(len(users), 1)))
        for u, c in zip(users, colors):
            er = [series[b].get(u, {}).get('emoji_per_100_msgs', 0.0) for b in buckets]
            ax2.plot(buckets, er, marker='o', label=u, color=c, linewidth=2)
        ax2.set_ylabel('Emoji per 100 messages')
        ax2.set_title('Monthly Emoji Rate (affect channel)', fontsize=12, fontweight='bold')
        ax2.tick_params(axis='x', rotation=45)
        ax2.legend(fontsize=8)

        plt.tight_layout()
        self._save(fig, f'{chat_name}_v4_affect.png')

    # 5. Circadian ------------------------------------------------------- #
    def _plot_circadian(self, metric, users, chat_name):
        matrices = metric.get('matrices', {})
        series = metric['series']
        buckets = self._sorted_buckets(series)
        overlap = metric.get('overlap_coefficient', 0.0)
        weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

        # Use the top-2 users by matrix mass.
        ranked = sorted(users, key=lambda u: -sum(sum(r) for r in matrices.get(u, [[0]])))
        shown = ranked[:2] if len(ranked) >= 2 else ranked
        note = '' if len(users) <= 2 else f' (top {len(shown)} of {len(users)})'

        vmax = max((max(max(r) for r in matrices.get(u, [[0]])) for u in shown), default=1) or 1
        fig = plt.figure(figsize=(14, 8))
        gs = fig.add_gridspec(2, len(shown), height_ratios=[3, 2], hspace=0.4, wspace=0.25)

        im = None
        for i, u in enumerate(shown):
            ax = fig.add_subplot(gs[0, i])
            mat = np.array(matrices.get(u, [[0] * 24 for _ in range(7)]))
            im = ax.imshow(mat, aspect='auto', cmap='magma', vmin=0, vmax=vmax)
            ax.set_title(u, fontsize=11, fontweight='bold')
            ax.set_xlabel('Hour')
            ax.set_yticks(range(7))
            ax.set_yticklabels(weekdays)
            ax.set_xticks(range(0, 24, 3))
        if im is not None:
            fig.colorbar(im, ax=fig.axes, fraction=0.02, pad=0.02, label='Messages')

        ax_trend = fig.add_subplot(gs[1, :])
        colors = plt.cm.Set2(np.linspace(0, 1, max(len(users), 1)))
        for u, c in zip(users, colors):
            ns = [series[b].get(u, {}).get('night_share', 0.0) for b in buckets]
            ax_trend.plot(buckets, ns, marker='o', label=u, color=c, linewidth=2)
        ax_trend.set_ylabel('Night share (23:00-03:00)')
        ax_trend.set_title('Monthly Sacred-Hours (late-night) Share', fontsize=12, fontweight='bold')
        ax_trend.tick_params(axis='x', rotation=45)
        ax_trend.legend(fontsize=8)

        fig.suptitle(f'Circadian Overlap = {overlap:.2f}{note} - {chat_name}',
                     fontsize=14, fontweight='bold')
        self._save(fig, f'{chat_name}_v4_circadian.png')

    # 6. Repair ---------------------------------------------------------- #
    def _plot_repair(self, metric, users, chat_name):
        per_user = metric['per_user']
        fig, ax = plt.subplots(figsize=(11, 6))

        x = np.arange(len(users))
        w = 0.35
        ruptures = [per_user.get(u, {}).get('ruptures_caused', 0) for u in users]
        repairs = [per_user.get(u, {}).get('repairs_made', 0) for u in users]
        ax.bar(x - w / 2, ruptures, w, label='Ruptures caused', color='#D64550', edgecolor='black')
        ax.bar(x + w / 2, repairs, w, label='Repairs made', color='#3B8EA5', edgecolor='black')
        ax.set_xticks(x)
        ax.set_xticklabels(users)
        ax.set_ylabel('Count')
        ax.set_title('Repair Ledger: Ruptures Caused vs Repairs Made\n'
                     '(rupture = session end + >48h silence)',
                     fontsize=13, fontweight='bold')
        ax.legend()

        for i, u in enumerate(users):
            lat = per_user.get(u, {}).get('median_repair_latency_hours', 0.0)
            if repairs[i]:
                ax.text(i + w / 2, repairs[i], f'{lat:.0f}h', ha='center',
                        va='bottom', fontsize=9, fontweight='bold')
        plt.tight_layout()
        self._save(fig, f'{chat_name}_v4_repair.png')

    # 7. Double-texting -------------------------------------------------- #
    def _plot_double_texting(self, metric, users, chat_name):
        per_user = metric['per_user']
        series = metric['series']
        buckets = self._sorted_buckets(series)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9))

        # Streak histograms (grouped bars).
        keys = [str(k) for k in range(2, 10)] + ['10+']
        x = np.arange(len(keys))
        w = 0.8 / max(len(users), 1)
        colors = plt.cm.Set2(np.linspace(0, 1, max(len(users), 1)))
        for i, (u, c) in enumerate(zip(users, colors)):
            hist = per_user.get(u, {}).get('streak_histogram', {})
            vals = [hist.get(k, 0) for k in keys]
            ax1.bar(x + i * w - 0.4 + w / 2, vals, w, label=u, color=c, edgecolor='black')
        ax1.set_xticks(x)
        ax1.set_xticklabels(keys)
        ax1.set_xlabel('Unanswered-streak length')
        ax1.set_ylabel('Count')
        ax1.set_title('Unanswered-Streak Distribution (persistence)',
                      fontsize=13, fontweight='bold')
        ax1.legend(fontsize=8)

        for u, c in zip(users, colors):
            dr = [series[b].get(u, {}).get('double_text_rate', 0.0) for b in buckets]
            ax2.plot(buckets, dr, marker='o', label=u, color=c, linewidth=2)
        ax2.set_ylabel('Double-texts / 100 msgs')
        ax2.set_title('Monthly Double-Text Rate (anxious pursuit)',
                      fontsize=12, fontweight='bold')
        ax2.tick_params(axis='x', rotation=45)
        ax2.legend(fontsize=8)

        plt.tight_layout()
        self._save(fig, f'{chat_name}_v4_double_texting.png')

    # 8. Half-life ------------------------------------------------------- #
    def _plot_half_life(self, metric, users, chat_name):
        per_user = metric['per_user']
        series = metric['series']
        buckets = self._sorted_buckets(series)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9))
        colors = plt.cm.Set2(np.linspace(0, 1, max(len(users), 1)))

        kill = [per_user.get(u, {}).get('momentum_kill_share', 0.0) for u in users]
        bars = ax1.bar(users, kill, color=colors, edgecolor='black')
        ax1.set_ylabel('Momentum-kill share')
        hl = metric.get('median_half_life_minutes', 0.0)
        ax1.set_title(f'Who Kills Conversations (median half-life {hl:.0f} min)',
                      fontsize=13, fontweight='bold')
        for bar, v in zip(bars, kill):
            ax1.text(bar.get_x() + bar.get_width() / 2, v, f'{v:.0%}',
                     ha='center', va='bottom', fontweight='bold')

        # Monthly momentum-lost share = sum of kills / sessions per bucket.
        lost = []
        for b in buckets:
            ud = series[b]
            kills = sum(v.get('kills', 0) for v in ud.values())
            sess = max((v.get('sessions', 0) for v in ud.values()), default=0)
            lost.append(kills / sess if sess else 0.0)
        ax2.plot(buckets, lost, marker='o', color='#B5179E', linewidth=2)
        ax2.set_ylabel('Momentum-lost share')
        ax2.set_title('Monthly Share of Conversations That Lost Momentum',
                      fontsize=12, fontweight='bold')
        ax2.set_ylim(0, 1)
        ax2.tick_params(axis='x', rotation=45)

        plt.tight_layout()
        self._save(fig, f'{chat_name}_v4_half_life.png')

    # 9. Change points (centerpiece) ------------------------------------- #
    def _plot_change_points(self, metric, chat_name):
        weekly = (metric or {}).get('weekly_series', {})
        change_points = (metric or {}).get('change_points', [])

        fig, ax = plt.subplots(figsize=(14, 6))
        volume = weekly.get('volume', {})
        weeks = sorted(volume.keys())

        if weeks:
            xs = range(len(weeks))
            ys = [volume[w] for w in weeks]
            ax.fill_between(xs, ys, color='#3B8EA5', alpha=0.35)
            ax.plot(xs, ys, color='#2A6F86', linewidth=1.5)
            ax.set_xticks(list(xs)[::max(1, len(weeks) // 12)])
            ax.set_xticklabels([weeks[i] for i in list(xs)[::max(1, len(weeks) // 12)]],
                               rotation=45, ha='right', fontsize=8)
            week_pos = {w: i for i, w in enumerate(weeks)}

            ymax = max(ys) if ys else 1
            ax.set_ylim(0, ymax * 1.08)
            for cp in change_points:
                pos = week_pos.get(cp['week'])
                if pos is None:
                    continue
                ax.axvline(pos, color='#D64550', linestyle='--', linewidth=1.8)
                if cp.get('signals'):
                    labels = ', '.join(
                        f"{s['metric']}{'↑' if s['direction'] == 'up' else '↓'}"
                        for s in cp['signals'][:3])
                    # Keep annotations inside the axes so they never collide
                    # with the title; anchor top-down next to the line.
                    ax.annotate(f'{cp.get("date", cp["week"])}  |  {labels}',
                                xy=(pos, ymax * 1.05), xytext=(pos - 0.4, ymax * 1.04),
                                fontsize=7.5, rotation=90, va='top', ha='right',
                                color='#7A1420',
                                bbox=dict(boxstyle='round,pad=0.15',
                                          facecolor='white', alpha=0.75,
                                          edgecolor='none'))
            ax.set_ylabel('Weekly message volume')
        else:
            ax.text(0.5, 0.5, 'No weekly data', ha='center', va='center',
                    transform=ax.transAxes, fontsize=16)

        if not change_points:
            ax.text(0.5, 0.9, 'No structural changes detected',
                    ha='center', va='center', transform=ax.transAxes,
                    fontsize=14, fontweight='bold', color='green',
                    bbox=dict(boxstyle='round', facecolor='honeydew'))

        ax.set_title(f'Change-Point Timeline - {chat_name}\n'
                     '(weekly volume; dashed lines = detected structural shifts)',
                     fontsize=13, fontweight='bold')
        plt.tight_layout()
        self._save(fig, f'{chat_name}_v4_change_points.png')
