"""
Instagram V3.0 Visualizations
Psychological and Relationship Dynamics Visualizations

Adapted from Telegram Analysis V3.0 for Instagram data format.
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
from datetime import datetime
import numpy as np


class AdvancedMetricsVisualizerV3:
    """Generate V3.0 advanced visualizations for Instagram chat analysis."""
    
    def __init__(self, output_dir: str):
        """Initialize visualizer.
        
        Args:
            output_dir: Directory to save visualizations
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Set matplotlib defaults
        plt.rcParams['font.size'] = 10
        plt.rcParams['figure.figsize'] = (12, 6)
    
    def generate_all(self, analysis: dict, chat_name: str):
        """Generate all v3.0 visualizations for a chat.
        
        Args:
            analysis: Analysis dictionary containing V3.0 metrics
            chat_name: Name of the chat for file naming
        """
        print(f"  Generating V3.0 advanced visualizations...")
        
        try:
            users = analysis.get('participants', [])
            if not users and 'message_counts' in analysis:
                users = list(analysis['message_counts'].keys())
            
            # Expressive Lengthening
            if 'expressive_lengthening_index' in analysis:
                self._plot_expressive_lengthening(
                    analysis['expressive_lengthening_index'], 
                    users, 
                    chat_name
                )
            
            # Emotional Cooling Alerts
            if 'emotional_cooling_alert' in analysis:
                self._plot_emotional_cooling(
                    analysis['emotional_cooling_alert'], 
                    chat_name
                )
            
            # Final Word Dominance
            if 'final_word_dominance' in analysis:
                self._plot_final_word_dominance(
                    analysis['final_word_dominance'], 
                    users, 
                    chat_name
                )
            
            # Thought Fragmentation
            if 'thought_fragmentation_index' in analysis:
                self._plot_thought_fragmentation(
                    analysis['thought_fragmentation_index'], 
                    users, 
                    chat_name
                )
            
            # Conversational Entropy
            if 'conversational_entropy' in analysis:
                self._plot_conversational_entropy(
                    analysis['conversational_entropy'], 
                    users, 
                    chat_name
                )
            
            # Defensiveness Index
            if 'defensiveness_index' in analysis:
                self._plot_defensiveness(
                    analysis['defensiveness_index'], 
                    users, 
                    chat_name
                )
            
            # Vocabulary Contagion
            if 'vocabulary_contagion_rate' in analysis:
                self._plot_vocabulary_contagion(
                    analysis['vocabulary_contagion_rate'], 
                    users, 
                    chat_name
                )
            
            # Topic Avoidance
            if 'selective_topic_avoidance' in analysis:
                self._plot_topic_avoidance(
                    analysis['selective_topic_avoidance'], 
                    chat_name
                )
            
            # Gini Coefficient
            if 'conversational_gini_coefficient' in analysis:
                self._plot_gini_coefficient(
                    analysis['conversational_gini_coefficient'], 
                    chat_name
                )
            
            # Conversational Inertia
            if 'conversational_inertia' in analysis:
                self._plot_inertia(
                    analysis['conversational_inertia'], 
                    chat_name
                )
            
            # Signal to Noise Ratio
            if 'signal_to_noise_ratio' in analysis:
                self._plot_snr(
                    analysis['signal_to_noise_ratio'], 
                    users, 
                    chat_name
                )
            
            # Chaser/Retreater
            if 'chaser_retreater_oscillation' in analysis:
                self._plot_chaser_retreater(
                    analysis['chaser_retreater_oscillation'], 
                    chat_name
                )
            
            # Tit for Tat
            if 'tit_for_tat_retaliation_score' in analysis:
                self._plot_tit_for_tat(
                    analysis['tit_for_tat_retaliation_score'], 
                    users, 
                    chat_name
                )
            
            # Temporal Syncopation
            if 'temporal_syncopation_variance' in analysis:
                self._plot_syncopation(
                    analysis['temporal_syncopation_variance'], 
                    users, 
                    chat_name
                )
            
            # Combined dashboard
            self._plot_v3_dashboard(analysis, users, chat_name)
            
            print(f"  ✓ V3.0 visualizations complete!")
        except Exception as e:
            print(f"  Error generating V3.0 visualizations: {e}")
            import traceback
            traceback.print_exc()
    
    def _plot_expressive_lengthening(self, data: dict, users: list, chat_name: str):
        """Plot expressive lengthening index."""
        fig, ax = plt.subplots(figsize=(10, 6))
        
        user_values = [data.get(user, 0) for user in users]
        colors = plt.cm.RdYlGn(np.linspace(0.3, 0.9, len(users)))
        
        bars = ax.bar(users, user_values, color=colors, edgecolor='black')
        ax.set_ylabel('Elongated Words Ratio')
        ax.set_title('Expressive Lengthening Index\n(Emotional Expressiveness)', fontsize=14, fontweight='bold')
        ax.set_ylim(0, max(user_values) * 1.2 if max(user_values) > 0 else 1)
        
        # Add value labels
        for bar, val in zip(bars, user_values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005, 
                   f'{val:.3f}', ha='center', va='bottom', fontweight='bold')
        
        # Interpretation
        if max(user_values) > 0.1:
            ax.text(0.02, 0.98, 'High: Playful/Anxious', transform=ax.transAxes, 
                   bbox=dict(boxstyle='round', facecolor='lightyellow'), fontsize=9)
        elif max(user_values) > 0.05:
            ax.text(0.02, 0.98, 'Moderate: Normal expressiveness', transform=ax.transAxes,
                   bbox=dict(boxstyle='round', facecolor='lightgreen'), fontsize=9)
        else:
            ax.text(0.02, 0.98, 'Low: Reserved communicator', transform=ax.transAxes,
                   bbox=dict(boxstyle='round', facecolor='lightblue'), fontsize=9)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_v3_expressive_lengthening.png', dpi=150, bbox_inches='tight')
        plt.close()
    
    def _plot_emotional_cooling(self, data: dict, chat_name: str):
        """Plot emotional cooling alerts."""
        alerts = data.get('alerts', {})
        
        if not alerts:
            # No alerts - show green indicator
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, '[OK] No Cold Shifts Detected\nRelationship expressiveness is stable',
                   ha='center', va='center', fontsize=18, fontweight='bold', color='green')
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            plt.savefig(self.output_dir / f'{chat_name}_v3_emotional_cooling_alerts.png', dpi=150)
            plt.close()
            return
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        dates = list(alerts.keys())
        drops = [alerts[d]['drop_percentage'] for d in dates]
        
        colors = ['red' if d > 50 else 'orange' for d in drops]
        ax.bar(dates, drops, color=colors, edgecolor='black')
        ax.set_ylabel('Drop Percentage (%)')
        ax.set_title('Emotional Cooling Alerts (Cold Shifts)\n>40% drop in expressiveness over 14 days', fontsize=14, fontweight='bold')
        ax.tick_params(axis='x', rotation=45)
        ax.set_ylim(0, max(drops) * 1.2 if max(drops) > 0 else 100)
        
        # Add threshold line
        ax.axhline(y=40, color='orange', linestyle='--', linewidth=2, label='40% Threshold')
        ax.legend()
        
        for i, (date, drop) in enumerate(zip(dates, drops)):
            ax.text(i, drop + 2, f'{drop}%', ha='center', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_v3_emotional_cooling_alerts.png', dpi=150, bbox_inches='tight')
        plt.close()
    
    def _plot_final_word_dominance(self, data: dict, users: list, chat_name: str):
        """Plot final word dominance."""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        # Bar chart
        user_values = [data.get(user, 0) for user in users]
        colors = plt.cm.PuOr(np.linspace(0.3, 0.9, len(users)))
        
        bars = ax1.bar(users, [v * 100 for v in user_values], color=colors, edgecolor='black')
        ax1.set_ylabel('Sessions Ended (%)')
        ax1.set_title('Final Word Dominance\n(Who ends conversations)', fontsize=14, fontweight='bold')
        ax1.set_ylim(0, 100)
        ax1.axhline(y=50, color='gray', linestyle='--', alpha=0.5, label='50% (Balanced)')
        ax1.legend()
        
        for bar, val in zip(bars, user_values):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                    f'{val*100:.1f}%', ha='center', fontweight='bold')
        
        # Pie chart
        if sum(user_values) > 0:
            wedges, texts, autotexts = ax2.pie(user_values, labels=users, autopct='%1.1f%%',
                                              colors=colors, startangle=90)
            ax2.set_title('Distribution of Session Endings', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_v3_final_word_dominance.png', dpi=150, bbox_inches='tight')
        plt.close()
    
    def _plot_thought_fragmentation(self, data: dict, users: list, chat_name: str):
        """Plot thought fragmentation index."""
        fig, ax = plt.subplots(figsize=(10, 6))
        
        user_values = [data.get(user, 0) for user in users]
        colors = plt.cm.YlOrRd(np.linspace(0.3, 0.9, len(users)))
        
        bars = ax.bar(users, [v * 100 for v in user_values], color=colors, edgecolor='black')
        ax.set_ylabel('Sessions with Fragmentation (%)')
        ax.set_title('Thought Fragmentation Index\n(3+ messages in 15 seconds)', fontsize=14, fontweight='bold')
        ax.set_ylim(0, 100)
        
        # Add thresholds
        ax.axhspan(0, 30, alpha=0.1, color='green')
        ax.axhspan(30, 60, alpha=0.1, color='yellow')
        ax.axhspan(60, 100, alpha=0.1, color='red')
        ax.text(0.02, 0.15, 'Low', transform=ax.transAxes, fontsize=9)
        ax.text(0.02, 0.45, 'Medium', transform=ax.transAxes, fontsize=9)
        ax.text(0.02, 0.8, 'High (Anxiety)', transform=ax.transAxes, fontsize=9)
        
        for bar, val in zip(bars, user_values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                   f'{val*100:.1f}%', ha='center', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_v3_thought_fragmentation.png', dpi=150, bbox_inches='tight')
        plt.close()
    
    def _plot_conversational_entropy(self, data: dict, users: list, chat_name: str):
        """Plot conversational entropy over time."""
        if not data:
            return
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        for user in users:
            months = []
            entropies = []
            for month, user_data in sorted(data.items()):
                if user in user_data:
                    months.append(month)
                    entropies.append(user_data[user])
            
            if months:
                ax.plot(months, entropies, marker='o', linewidth=2, markersize=8, label=user)
        
        ax.set_ylabel('Normalized Entropy (0-1)')
        ax.set_title('Conversational Entropy Over Time\n(Low = Repetitive/Rut, High = Dynamic)', fontsize=14, fontweight='bold')
        ax.tick_params(axis='x', rotation=45)
        ax.legend()
        ax.set_ylim(0, 1.1)
        
        # Add interpretation zones
        ax.axhspan(0, 0.3, alpha=0.1, color='red')
        ax.axhspan(0.3, 0.6, alpha=0.1, color='yellow')
        ax.axhspan(0.6, 1, alpha=0.1, color='green')
        ax.text(0.02, 0.15, 'Rut', transform=ax.transAxes, fontsize=9)
        ax.text(0.02, 0.45, 'Normal', transform=ax.transAxes, fontsize=9)
        ax.text(0.02, 0.8, 'Dynamic', transform=ax.transAxes, fontsize=9)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_v3_conversational_entropy.png', dpi=150, bbox_inches='tight')
        plt.close()
    
    def _plot_defensiveness(self, data: dict, users: list, chat_name: str):
        """Plot defensiveness index."""
        fig, ax = plt.subplots(figsize=(10, 6))
        
        user_values = [data.get(user, 0) for user in users]
        colors = plt.cm.RdYlBu(np.linspace(0.9, 0.3, len(users)))
        
        bars = ax.bar(users, user_values, color=colors, edgecolor='black')
        ax.set_ylabel('Defensive Words per 1000 Words')
        ax.set_title('Defensiveness Index\n(just, but, technically, უბრალოდ, მარა, etc.)', fontsize=14, fontweight='bold')
        
        max_val = max(user_values) if user_values else 10
        ax.set_ylim(0, max_val * 1.2)
        
        # Add thresholds
        ax.axhline(y=5, color='green', linestyle='--', alpha=0.5, label='Low (<5)')
        ax.axhline(y=10, color='orange', linestyle='--', alpha=0.5, label='Medium (5-10)')
        ax.axhline(y=15, color='red', linestyle='--', alpha=0.5, label='High (>15)')
        ax.legend()
        
        for bar, val in zip(bars, user_values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                   f'{val:.1f}', ha='center', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_v3_defensiveness_index.png', dpi=150, bbox_inches='tight')
        plt.close()
    
    def _plot_vocabulary_contagion(self, data: dict, users: list, chat_name: str):
        """Plot vocabulary contagion rate."""
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Build matrix
        matrix_data = []
        for driver in users:
            row = []
            for adopter in users:
                if driver == adopter:
                    row.append(0)
                else:
                    row.append(data.get(driver, {}).get(adopter, 0))
            matrix_data.append(row)
        
        if matrix_data:
            im = ax.imshow(matrix_data, cmap='YlGnBu', aspect='auto')
            ax.set_xticks(range(len(users)))
            ax.set_yticks(range(len(users)))
            ax.set_xticklabels(users)
            ax.set_yticklabels(users)
            ax.set_xlabel('Adopter')
            ax.set_ylabel('Driver')
            ax.set_title('Vocabulary Contagion Rate\n(Words adopted by others)', fontsize=14, fontweight='bold')
            
            plt.colorbar(im, ax=ax, label='Words Adopted')
            
            # Add values
            for i in range(len(users)):
                for j in range(len(users)):
                    if matrix_data[i][j] > 0:
                        ax.text(j, i, str(matrix_data[i][j]), ha='center', va='center', 
                               color='white' if matrix_data[i][j] > 5 else 'black', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_v3_vocabulary_contagion.png', dpi=150, bbox_inches='tight')
        plt.close()
    
    def _plot_topic_avoidance(self, data: dict, chat_name: str):
        """Plot selective topic avoidance."""
        if not data:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, '[OK] No Topic Avoidance Detected\nAll topics have normal response times',
                   ha='center', va='center', fontsize=16, fontweight='bold', color='green')
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            plt.savefig(self.output_dir / f'{chat_name}_v3_topic_avoidance.png', dpi=150)
            plt.close()
            return
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        topics = list(data.keys())
        delays = [data[t]['delay_multiplier'] for t in topics]
        
        colors = ['red' if d > 5 else 'orange' if d > 3 else 'yellow' for d in delays]
        bars = ax.bar(topics, delays, color=colors, edgecolor='black')
        ax.set_ylabel('Delay Multiplier (σ above baseline)')
        ax.set_title('Selective Topic Avoidance\n(Topics causing severe response delays)', fontsize=14, fontweight='bold')
        ax.tick_params(axis='x', rotation=45)
        
        for bar, val in zip(bars, delays):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2,
                   f'{val:.1f}σ', ha='center', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_v3_topic_avoidance.png', dpi=150, bbox_inches='tight')
        plt.close()
    
    def _plot_gini_coefficient(self, data: dict, chat_name: str):
        """Plot conversational Gini coefficient over time."""
        if not data:
            return
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        periods = list(data.keys())
        gini_values = list(data.values())
        
        ax.plot(periods, gini_values, marker='o', linewidth=2, markersize=8, color='purple')
        ax.set_ylabel('Gini Coefficient (0-1)')
        ax.set_title('Conversational Gini Coefficient\n(Economic Inequality of Effort)', fontsize=14, fontweight='bold')
        ax.tick_params(axis='x', rotation=45)
        ax.set_ylim(0, 1)
        
        # Add interpretation zones
        ax.axhspan(0, 0.3, alpha=0.1, color='green')
        ax.axhspan(0.3, 0.5, alpha=0.1, color='yellow')
        ax.axhspan(0.5, 1, alpha=0.1, color='red')
        ax.text(0.02, 0.15, 'Balanced', transform=ax.transAxes, fontsize=9)
        ax.text(0.02, 0.45, 'Moderate', transform=ax.transAxes, fontsize=9)
        ax.text(0.02, 0.8, 'Unequal', transform=ax.transAxes, fontsize=9)
        
        for period, gini in zip(periods, gini_values):
            ax.text(period, gini + 0.02, f'{gini:.3f}', ha='center', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_v3_gini_coefficient.png', dpi=150, bbox_inches='tight')
        plt.close()
    
    def _plot_inertia(self, data: float, chat_name: str):
        """Plot conversational inertia."""
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Gauge-like visualization
        ax.text(0.5, 0.7, f'{data:.0f}', ha='center', va='center', 
               fontsize=48, fontweight='bold', color='darkblue')
        ax.text(0.5, 0.5, 'Average Characters', ha='center', va='center', fontsize=14)
        ax.text(0.5, 0.4, 'Needed to Restart', ha='center', va='center', fontsize=14)
        
        # Interpretation
        if data > 500:
            interpretation = "High Inertia\n(Requires significant effort to revive)"
            color = 'red'
        elif data > 200:
            interpretation = "Moderate Inertia\n(Some effort needed)"
            color = 'orange'
        else:
            interpretation = "Low Inertia\n(Easy to restart)"
            color = 'green'
        
        ax.text(0.5, 0.2, interpretation, ha='center', va='center', fontsize=14, color=color, fontweight='bold')
        
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        ax.set_title('Conversational Inertia\n(Average characters to restart after 72h gap)', fontsize=14, fontweight='bold', pad=20)
        
        plt.savefig(self.output_dir / f'{chat_name}_v3_conversational_inertia.png', dpi=150)
        plt.close()
    
    def _plot_snr(self, data: dict, users: list, chat_name: str):
        """Plot signal to noise ratio."""
        fig, ax = plt.subplots(figsize=(10, 6))
        
        user_values = [data.get(user, 0) for user in users]
        colors = plt.cm.Greens(np.linspace(0.3, 0.9, len(users)))
        
        bars = ax.bar(users, user_values, color=colors, edgecolor='black')
        ax.set_ylabel('Signal/Noise Ratio')
        ax.set_title('Signal to Noise Ratio\n(Conversation depth vs filler)', fontsize=14, fontweight='bold')
        
        max_val = max(user_values) if user_values else 1
        ax.set_ylim(0, max_val * 1.2)
        
        # Add interpretation line
        ax.axhline(y=1, color='orange', linestyle='--', linewidth=2, label='1.0 (Balanced)')
        ax.legend()
        
        for bar, val in zip(bars, user_values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                   f'{val:.2f}', ha='center', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_v3_signal_to_noise_ratio.png', dpi=150, bbox_inches='tight')
        plt.close()
    
    def _plot_chaser_retreater(self, data: dict, chat_name: str):
        """Plot chaser/retreater oscillation."""
        if not data:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, '[OK] No Chaser/Retreater Pattern Detected\nCommunication flow is healthy',
                   ha='center', va='center', fontsize=16, fontweight='bold', color='green')
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            plt.savefig(self.output_dir / f'{chat_name}_v3_chaser_retreater.png', dpi=150)
            plt.close()
            return
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        dates = list(data.keys())
        correlations = [data[d]['correlation'] for d in dates]
        
        ax.plot(dates, correlations, marker='o', linewidth=2, markersize=8, color='red')
        ax.set_ylabel('Pearson Correlation')
        ax.set_title('Chaser/Retreater Oscillation\n(Negative correlation = anxious-avoidant pattern)', fontsize=14, fontweight='bold')
        ax.tick_params(axis='x', rotation=45)
        ax.set_ylim(-1, 1)
        
        # Add threshold line
        ax.axhline(y=-0.6, color='orange', linestyle='--', linewidth=2, label='-0.6 Threshold')
        ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
        ax.legend()
        
        for date, corr in zip(dates, correlations):
            ax.text(date, corr + 0.05, f'{corr:.2f}', ha='center', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_v3_chaser_retreater.png', dpi=150, bbox_inches='tight')
        plt.close()
    
    def _plot_tit_for_tat(self, data: dict, users: list, chat_name: str):
        """Plot tit-for-tat retaliation score."""
        fig, ax = plt.subplots(figsize=(10, 6))
        
        user_values = [data.get(user, 0) for user in users]
        colors = plt.cm.Reds(np.linspace(0.3, 0.9, len(users)))
        
        bars = ax.bar(users, user_values, color=colors, edgecolor='black')
        ax.set_ylabel('R² (Retaliation Predictability)')
        ax.set_title('Tit-for-Tat Retaliation Score\n(Game Theory - Intentional delay mirroring)', fontsize=14, fontweight='bold')
        ax.set_ylim(0, 1)
        
        # Add interpretation zones
        ax.axhspan(0, 0.3, alpha=0.1, color='green')
        ax.axhspan(0.3, 0.6, alpha=0.1, color='yellow')
        ax.axhspan(0.6, 1, alpha=0.1, color='red')
        ax.text(0.02, 0.15, 'Normal', transform=ax.transAxes, fontsize=9)
        ax.text(0.02, 0.45, 'Moderate', transform=ax.transAxes, fontsize=9)
        ax.text(0.02, 0.8, 'High Pettiness', transform=ax.transAxes, fontsize=9)
        
        for bar, val in zip(bars, user_values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.03,
                   f'{val:.3f}', ha='center', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_v3_tit_for_tat_retaliation.png', dpi=150, bbox_inches='tight')
        plt.close()
    
    def _plot_syncopation(self, data: dict, users: list, chat_name: str):
        """Plot temporal syncopation variance."""
        fig, ax = plt.subplots(figsize=(10, 6))
        
        user_values = [data.get(user, 0) for user in users]
        colors = plt.cm.PuOr(np.linspace(0.3, 0.9, len(users)))
        
        bars = ax.bar(users, user_values, color=colors, edgecolor='black')
        ax.set_ylabel('Variance of Tempo Deviations')
        ax.set_title('Temporal Syncopation Variance\n(Music Theory - Rhythm unpredictability)', fontsize=14, fontweight='bold')
        
        max_val = max(user_values) if user_values else 1
        ax.set_ylim(0, max_val * 1.2)
        
        # Add interpretation
        ax.axhline(y=0.3, color='green', linestyle='--', alpha=0.5, label='Low (Predictable)')
        ax.axhline(y=0.6, color='orange', linestyle='--', alpha=0.5, label='High (Erratic)')
        ax.legend()
        
        for bar, val in zip(bars, user_values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                   f'{val:.3f}', ha='center', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_v3_temporal_syncopation.png', dpi=150, bbox_inches='tight')
        plt.close()
    
    def _plot_v3_dashboard(self, analysis: dict, users: list, chat_name: str):
        """Create a comprehensive v3.0 dashboard."""
        fig = plt.figure(figsize=(16, 12))
        
        # Create subplots
        gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)
        
        # 1. Expressive Lengthening
        ax1 = fig.add_subplot(gs[0, 0])
        if 'expressive_lengthening_index' in analysis:
            values = [analysis['expressive_lengthening_index'].get(u, 0) for u in users]
            ax1.bar(users, values, color='coral', edgecolor='black')
            ax1.set_title('Expressive\nLengthening', fontsize=10)
            ax1.tick_params(labelbottom=True, labelrotation=45)
            ax1.set_ylabel('Ratio')
        
        # 2. Defensiveness
        ax2 = fig.add_subplot(gs[0, 1])
        if 'defensiveness_index' in analysis:
            values = [analysis['defensiveness_index'].get(u, 0) for u in users]
            ax2.bar(users, values, color='lightblue', edgecolor='black')
            ax2.set_title('Defensiveness\nIndex', fontsize=10)
            ax2.tick_params(labelbottom=True, labelrotation=45)
            ax2.set_ylabel('Index')
        
        # 3. SNR
        ax3 = fig.add_subplot(gs[0, 2])
        if 'signal_to_noise_ratio' in analysis:
            values = [analysis['signal_to_noise_ratio'].get(u, 0) for u in users]
            ax3.bar(users, values, color='lightgreen', edgecolor='black')
            ax3.set_title('Signal/Noise\nRatio', fontsize=10)
            ax3.tick_params(labelbottom=True, labelrotation=45)
            ax3.set_ylabel('Ratio')
        
        # 4. Thought Fragmentation
        ax4 = fig.add_subplot(gs[1, 0])
        if 'thought_fragmentation_index' in analysis:
            values = [analysis['thought_fragmentation_index'].get(u, 0) * 100 for u in users]
            ax4.bar(users, values, color='orange', edgecolor='black')
            ax4.set_title('Thought\nFragmentation (%)', fontsize=10)
            ax4.tick_params(labelbottom=True, labelrotation=45)
            ax4.set_ylabel('%')
        
        # 5. Final Word Dominance
        ax5 = fig.add_subplot(gs[1, 1])
        if 'final_word_dominance' in analysis:
            values = [analysis['final_word_dominance'].get(u, 0) * 100 for u in users]
            ax5.bar(users, values, color='purple', edgecolor='black')
            ax5.set_title('Final Word\nDominance (%)', fontsize=10)
            ax5.tick_params(labelbottom=True, labelrotation=45)
            ax5.set_ylabel('%')
        
        # 6. Tit for Tat
        ax6 = fig.add_subplot(gs[1, 2])
        if 'tit_for_tat_retaliation_score' in analysis:
            values = [analysis['tit_for_tat_retaliation_score'].get(u, 0) for u in users]
            ax6.bar(users, values, color='pink', edgecolor='black')
            ax6.set_title('Tit-for-Tat\n(R²)', fontsize=10)
            ax6.tick_params(labelbottom=True, labelrotation=45)
            ax6.set_ylabel('Score')
        
        # 7. Gini Coefficient (time series)
        ax7 = fig.add_subplot(gs[2, 0])
        if 'conversational_gini_coefficient' in analysis:
            gini_data = analysis['conversational_gini_coefficient']
            if gini_data:
                # Keys can be timestamps (ms) or month strings (YYYY-MM)
                dates = []
                for d in gini_data.keys():
                    try:
                        dates.append(datetime.fromtimestamp(int(d)/1000).strftime('%m-%d'))
                    except ValueError:
                        dates.append(d)
                ax7.plot(dates, list(gini_data.values()), marker='o', color='brown', linewidth=2)
                ax7.set_title('Gini Coefficient\n(Over Time)', fontsize=10)
                ax7.tick_params(labelbottom=True, labelrotation=45)
                ax7.set_ylabel('Gini')
        
        # 8. Chaser/Retreater
        ax8 = fig.add_subplot(gs[2, 1])
        if 'chaser_retreater_oscillation' in analysis:
            cr_data = analysis['chaser_retreater_oscillation']
            if cr_data:
                # Keys are YYYY-MM-DD date strings
                dates = list(cr_data.keys())
                correlations = [cr_data[d]['correlation'] for d in cr_data]
                ax8.plot(dates, correlations, marker='o', color='red', linewidth=2)
                ax8.axhline(y=-0.6, color='orange', linestyle='--')
                ax8.set_title('Chaser/Retreater\n(Correlation)', fontsize=10)
                ax8.tick_params(labelbottom=True, labelrotation=45)
                ax8.set_ylabel('Correlation')
        
        # 9. Summary text
        ax9 = fig.add_subplot(gs[2, 2])
        ax9.axis('off')
        
        summary_text = "V3.0 Advanced Metrics\n"
        summary_text += "="*40 + "\n\n"
        
        # Add key insights (using ASCII-safe characters)
        if 'emotional_cooling_alert' in analysis:
            alerts = analysis['emotional_cooling_alert'].get('total_cold_shifts', 0)
            summary_text += f"[ice] Cold Shifts: {alerts}\n"
        
        if 'selective_topic_avoidance' in analysis:
            topics = len(analysis['selective_topic_avoidance'])
            summary_text += f"[stop] Avoided Topics: {topics}\n"
        
        if 'conversational_inertia' in analysis:
            inertia = analysis['conversational_inertia']
            summary_text += f"[lightning] Inertia: {inertia:.0f} chars\n"
        
        ax9.text(0.1, 0.5, summary_text, transform=ax9.transAxes, fontsize=11,
                verticalalignment='center', fontfamily='monospace')
        
        fig.suptitle(f'V3.0 Advanced Metrics Dashboard - {chat_name}', fontsize=16, fontweight='bold')
        plt.savefig(self.output_dir / f'{chat_name}_v3_dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
