"""Visualization generation for chat analysis results."""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from typing import Dict, Any


class ChatVisualizer:
    """Generate visualizations for chat analysis."""
    
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
    
    def plot_message_distribution(self, analysis: Dict, chat_name: str):
        """Plot message count distribution between participants."""
        msg_counts = analysis.get('message_counts', {})
        
        if not msg_counts:
            return
        
        plt.figure()
        participants = list(msg_counts.keys())
        counts = list(msg_counts.values())
        
        colors = ['#3498db', '#e74c3c'][:len(participants)]
        plt.pie(counts, labels=participants, autopct='%1.1f%%', colors=colors)
        plt.title(f'Message Distribution - {chat_name}')
        plt.savefig(self.output_dir / f'{chat_name}_message_distribution.png', dpi=100, bbox_inches='tight')
        plt.close()
    
    def plot_day_of_week(self, analysis: Dict, chat_name: str):
        """Plot message frequency by day of week."""
        day_stats = analysis.get('day_of_week', {})
        
        if not day_stats:
            return
        
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 
                'Friday', 'Saturday', 'Sunday']
        counts = [day_stats.get(day, 0) for day in days]
        
        plt.figure()
        plt.bar(days, counts, color='#3498db')
        plt.xlabel('Day of Week')
        plt.ylabel('Message Count')
        plt.title(f'Messages by Day of Week - {chat_name}')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_day_of_week.png', dpi=100, bbox_inches='tight')
        plt.close()
    
    def plot_yearly_trends(self, analysis: Dict, chat_name: str):
        """Plot yearly message trends."""
        yearly = analysis.get('yearly_stats', {})
        
        if not yearly:
            return
        
        years = sorted(yearly.keys())
        counts = [yearly[y]['total_messages'] for y in years]
        
        plt.figure()
        plt.plot(years, counts, marker='o', linewidth=2, markersize=8)
        plt.xlabel('Year')
        plt.ylabel('Total Messages')
        plt.title(f'Yearly Message Trends - {chat_name}')
        plt.grid(True, alpha=0.3)
        plt.savefig(self.output_dir / f'{chat_name}_yearly_trends.png', dpi=100, bbox_inches='tight')
        plt.close()
    
    def plot_response_times(self, analysis: Dict, chat_name: str):
        """Plot response time comparison."""
        resp = analysis.get('response_times', {})
        
        if not resp:
            return
        
        plt.figure()
        labels = ['You', 'Partner']
        times = [
            resp.get('my_avg_response_minutes', 0),
            resp.get('partner_avg_response_minutes', 0)
        ]
        colors = ['#3498db', '#e74c3c']
        
        plt.bar(labels, times, color=colors)
        plt.ylabel('Average Response Time (minutes)')
        plt.title(f'Response Time Comparison - {chat_name}')
        plt.savefig(self.output_dir / f'{chat_name}_response_times.png', dpi=100, bbox_inches='tight')
        plt.close()
    
    def plot_language_distribution(self, analysis: Dict, chat_name: str):
        """Plot language distribution."""
        lang_dist = analysis.get('language_distribution', {})
        
        if not lang_dist:
            return
        
        plt.figure()
        languages = list(lang_dist.keys())
        percentages = list(lang_dist.values())
        colors = ['#2ecc71', '#3498db', '#9b59b6']
        
        plt.pie(percentages, labels=[l.capitalize() for l in languages], 
                autopct='%1.1f%%', colors=colors[:len(languages)])
        plt.title(f'Language Distribution - {chat_name}')
        plt.savefig(self.output_dir / f'{chat_name}_language_distribution.png', dpi=100, bbox_inches='tight')
        plt.close()
    
    def plot_word_frequency(self, word_freq: Dict[str, int], chat_name: str, top_n: int = 20):
        """Plot top word frequencies as a horizontal bar chart."""
        if not word_freq:
            return
        
        # Get top N words
        top_words = dict(sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:top_n])
        
        plt.figure(figsize=(10, 6))
        words = list(top_words.keys())
        counts = list(top_words.values())
        
        # Create horizontal bar chart
        plt.barh(words[::-1], counts[::-1], color='#3498db')
        plt.xlabel('Frequency')
        plt.title(f'Top {top_n} Words - {chat_name}')
        plt.tight_layout()
        plt.savefig(self.output_dir / f'{chat_name}_word_frequency.png', dpi=100, bbox_inches='tight')
        plt.close()
    
    def generate_all_plots(self, analysis: Dict, chat_name: str):
        """Generate all visualizations for a chat."""
        print(f"  Generating visualizations...")
        
        self.plot_message_distribution(analysis, chat_name)
        self.plot_day_of_week(analysis, chat_name)
        self.plot_yearly_trends(analysis, chat_name)
        self.plot_response_times(analysis, chat_name)
        self.plot_language_distribution(analysis, chat_name)
        
        # Word frequency for each participant
        word_freq_data = analysis.get('word_frequency', {})
        for participant, word_freq in word_freq_data.items():
            safe_name = participant.replace(' ', '_').replace('/', '_')
            self.plot_word_frequency(word_freq, f'{chat_name}_{safe_name}')
