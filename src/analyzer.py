"""Core analysis logic for Instagram chat data."""

from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any

from src.data_loader import load_chat
from src.language_detection import get_language_distribution
from src.word_frequency import get_word_frequency
from src.response_time import calculate_response_times
from src.media_analyzer import get_media_stats
from src.analyzer_v3 import (
    expressive_lengthening_index,
    emotional_cooling_alert,
    final_word_dominance,
    thought_fragmentation_index,
    conversational_entropy,
    defensiveness_index,
    vocabulary_contagion_rate,
    selective_topic_avoidance,
    conversational_gini_coefficient,
    conversational_inertia,
    signal_to_noise_ratio,
    chaser_retreater_oscillation,
    tit_for_tat_retaliation_score,
    temporal_syncopation_variance
)


class ChatAnalyzer:
    """Analyzer for a single Instagram chat."""
    
    def __init__(self, chat_data: Dict[str, Any], my_name: str):
        """Initialize the analyzer.
        
        Args:
            chat_data: Parsed JSON data from a chat file
            my_name: Your name in the chat
        """
        self.chat_data = chat_data
        self.messages = chat_data.get('messages', [])
        self.participants = [p['name'] for p in chat_data.get('participants', [])]
        self.my_name = my_name
        self.partner_name = next(
            (p for p in self.participants if p != my_name), 
            "Unknown"
        )
    
    def get_messages_by_sender(self) -> Dict[str, List[Dict]]:
        """Group messages by sender."""
        by_sender = defaultdict(list)
        for msg in self.messages:
            sender = msg.get('sender_name', 'Unknown')
            by_sender[sender].append(msg)
        return dict(by_sender)
    
    def get_timestamp(self, msg: Dict) -> datetime:
        """Convert timestamp_ms to datetime."""
        return datetime.fromtimestamp(msg['timestamp_ms'] / 1000)
    
    def _get_chat_info(self) -> Dict[str, Any]:
        """Get basic chat information."""
        sorted_msgs = sorted(self.messages, key=lambda x: x['timestamp_ms'])
        
        if not sorted_msgs:
            return {
                'chat_name': self.chat_data.get('title', 'Unknown'),
                'participants': self.participants,
                'total_messages': 0
            }
        
        return {
            'chat_name': self.chat_data.get('title', 'Unknown'),
            'participants': self.participants,
            'total_messages': len(self.messages),
            'date_range': {
                'first_message': sorted_msgs[0]['timestamp_ms'],
                'last_message': sorted_msgs[-1]['timestamp_ms']
            }
        }
    
    def _get_message_counts(self) -> Dict[str, int]:
        """Get message count per participant."""
        by_sender = self.get_messages_by_sender()
        return {sender: len(msgs) for sender, msgs in by_sender.items()}
    
    def _get_day_of_week_stats(self) -> Dict[str, int]:
        """Get message frequency by day of week."""
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 
                'Friday', 'Saturday', 'Sunday']
        day_counts = {day: 0 for day in days}
        
        for msg in self.messages:
            timestamp = self.get_timestamp(msg)
            day_name = days[timestamp.weekday()]
            day_counts[day_name] += 1
        
        return day_counts
    
    def _get_first_message(self) -> Dict[str, Any]:
        """Get the first message in the chat."""
        if not self.messages:
            return {}
        
        sorted_msgs = sorted(self.messages, key=lambda x: x['timestamp_ms'])
        first = sorted_msgs[0]
        
        return {
            'timestamp': first['timestamp_ms'],
            'timestamp_formatted': self.get_timestamp(first).isoformat(),
            'sender': first.get('sender_name', 'Unknown'),
            'content': first.get('content', '')[:200]  # Truncate long messages
        }
    
    def _get_messages_per_week(self) -> Dict[str, List[float]]:
        """Get messages per week grouped by year."""
        if not self.messages:
            return {}
        
        # Group messages by ISO week
        weeks = defaultdict(lambda: defaultdict(int))
        
        for msg in self.messages:
            timestamp = self.get_timestamp(msg)
            year = str(timestamp.year)
            iso_week = timestamp.isocalendar()[1]
            weeks[year][iso_week] += 1
        
        # Convert to lists and calculate averages
        result = {}
        for year, week_data in sorted(weeks.items()):
            week_counts = [week_data.get(w, 0) for w in range(1, 54)]
            avg_per_week = sum(week_counts) / len(week_counts) if week_counts else 0
            result[year] = {
                'weekly_counts': week_counts,
                'average_per_week': round(avg_per_week, 2)
            }
        
        return result
    
    def _get_yearly_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get yearly statistics."""
        yearly = defaultdict(lambda: {'messages': defaultdict(int), 'total': 0})
        
        for msg in self.messages:
            timestamp = self.get_timestamp(msg)
            year = str(timestamp.year)
            sender = msg.get('sender_name', 'Unknown')
            yearly[year]['messages'][sender] += 1
            yearly[year]['total'] += 1
        
        result = {}
        for year, data in sorted(yearly.items()):
            msg_counts = data['messages']
            top_sender = max(msg_counts.items(), key=lambda x: x[1])[0] if msg_counts else "Unknown"
            
            result[year] = {
                'total_messages': data['total'],
                'top_sender': top_sender,
                'top_sender_count': msg_counts.get(top_sender, 0),
                'by_sender': dict(msg_counts)
            }
        
        return result
    
    def _get_response_times(self) -> Dict[str, Any]:
        """Get response time analysis."""
        return calculate_response_times(self.messages, self.my_name)
    
    def _get_media_stats(self) -> Dict[str, Any]:
        """Get media statistics."""
        return get_media_stats(self.messages)
    
    def _get_word_frequency(self) -> Dict[str, Dict[str, int]]:
        """Get word frequency for each participant."""
        result = {}
        for participant in self.participants:
            result[participant] = get_word_frequency(self.messages, participant)
        return result
    
    def _get_language_distribution(self) -> Dict[str, float]:
        """Get language distribution."""
        return get_language_distribution(self.messages)
    
    def analyze(self) -> Dict[str, Any]:
        """Run all analyses and return results."""
        # Get participants for V3.0 metrics
        users = self.participants
        
        return {
            # Existing 10 core metrics
            'chat_info': self._get_chat_info(),
            'message_counts': self._get_message_counts(),
            'language_distribution': self._get_language_distribution(),
            'day_of_week': self._get_day_of_week_stats(),
            'first_message': self._get_first_message(),
            'messages_per_week': self._get_messages_per_week(),
            'yearly_stats': self._get_yearly_stats(),
            'response_times': self._get_response_times(),
            'media_stats': self._get_media_stats(),
            'word_frequency': self._get_word_frequency(),
            
            # V3.0 Advanced Psychological Metrics (14 new metrics)
            'expressive_lengthening_index': expressive_lengthening_index(self.messages, users),
            'emotional_cooling_alert': emotional_cooling_alert(self.messages, users),
            'final_word_dominance': final_word_dominance(self.messages, users),
            'thought_fragmentation_index': thought_fragmentation_index(self.messages, users),
            'conversational_entropy': conversational_entropy(self.messages, users),
            'defensiveness_index': defensiveness_index(self.messages, users),
            'vocabulary_contagion_rate': vocabulary_contagion_rate(self.messages, users),
            'selective_topic_avoidance': selective_topic_avoidance(self.messages, users),
            'conversational_gini_coefficient': conversational_gini_coefficient(self.messages, users),
            'conversational_inertia': conversational_inertia(self.messages, users),
            'signal_to_noise_ratio': signal_to_noise_ratio(self.messages, users),
            'chaser_retreater_oscillation': chaser_retreater_oscillation(self.messages, users),
            'tit_for_tat_retaliation_score': tit_for_tat_retaliation_score(self.messages, users),
            'temporal_syncopation_variance': temporal_syncopation_variance(self.messages, users),
            
            # Store participants for visualizer
            'participants': users
        }
