# Instagram Chat Analyzer V3.0

A Python tool for analyzing Instagram chat exports and generating comprehensive analytics with advanced psychological metrics and visualizations.

## Features

### 10 Core Analysis Metrics:

1. **Message Distribution** - Who sends more messages (you vs partner)
2. **Language Distribution** - Georgian, English, or Mixed content ratio
3. **Day of Week Analysis** - Which days have the most communication
4. **First Message** - When the conversation started
5. **Messages Per Week** - Weekly activity trends grouped by year
6. **Yearly Statistics** - Top sender and message counts per year
7. **Response Time Analysis** - Average response times and who delays more
8. **Media Statistics** - Photos, videos, audio files, and shares per sender
9. **Word Frequency** - Top 50 most used words per participant
10. **Chat Information** - Participants, total messages, date range

---

### 14 V3.0 Advanced Psychological Metrics:

11. **Expressive Lengthening Index** - Frequency of elongated words (e.g., 'heyyy', 'noooo') indicating emotional expressiveness
12. **Emotional Cooling Alerts** - Detects sudden drops (>40%) in expressiveness over 14-day periods
13. **Final Word Dominance** - Who consistently sends the last message in conversation sessions
14. **Thought Fragmentation Index** - Tendency to break thoughts into rapid-fire messages (3+ in 15 seconds)
15. **Conversational Entropy** - Shannon entropy on bigram distribution (low = repetitive/rut, high = dynamic)
16. **Defensiveness Index** - Usage of justification/shielding words (just, but, technically, უბრალოდ, მარა)
17. **Vocabulary Contagion Rate** - Who adopts whose slang (cultural driver vs adopter)
18. **Selective Topic Avoidance** - Topics causing severe response delays (>3σ above baseline)
19. **Conversational Gini Coefficient** - Economic inequality of effort (rolling 30-day)
20. **Conversational Inertia** - Force (characters) required to restart a dead chat (>72h gap)
21. **Signal to Noise Ratio** - Depth of conversation vs idle filler
22. **Chaser/Retreater Oscillation** - Anxious-avoidant pursuit dynamics (rolling 3-day correlation)
23. **Tit-for-Tat Retaliation Score** - Intentional mirroring of delayed responses (Game Theory)
24. **Temporal Syncopation Variance** - Unpredictability of conversational rhythm (Music Theory)

## Project Structure

```
Instagram Analysis/
├── src/
│   ├── __init__.py
│   ├── data_loader.py       # JSON loading and parsing
│   ├── analyzer.py          # Core analysis logic (10 metrics)
│   ├── analyzer_v3.py       # V3.0 advanced metrics (14 metrics)
│   ├── statistics.py        # Statistical calculations
│   ├── language_detection.py # Language detection
│   ├── word_frequency.py    # Word frequency analysis
│   ├── response_time.py     # Response time calculations
│   ├── media_analyzer.py    # Media statistics
│   ├── visualizer.py        # Core plot generation (6 charts)
│   └── visualizer_v3.py     # V3.0 visualizations (15 charts)
├── outputs/
│   ├── analysis/            # Per-chat JSON analysis files
│   └── visualizations/      # Generated charts
├── main.py                  # Entry point
├── requirements.txt         # Dependencies
├── venv/                    # Virtual environment
├── README.md
└── V3_METRICS_IMPLEMENTATION_PLAN.md
```

## Installation

```bash
cd "/home/normie/Projects/Instagram Analysis"
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Test Run (Pre-configured)

The `main.py` is configured to analyze two test chats:
- mariammerabishvili_1756493205749663
- mariakhorava_17913165954160425

```bash
source venv/bin/activate
python main.py
```

### Output Files

After running, you'll find:

**Analysis JSON files** in `outputs/analysis/`:
- `{chat_name}_analysis.json` - Detailed analysis for each chat
- `all_chats_analysis.json` - Combined analysis of all chats

**Visualizations** in `outputs/visualizations/`:

### Core Visualizations (6 charts):
- `{chat_name}_message_distribution.png` - Pie chart of message counts
- `{chat_name}_day_of_week.png` - Bar chart of messages by day
- `{chat_name}_yearly_trends.png` - Line chart of yearly activity
- `{chat_name}_response_times.png` - Bar chart comparing response times
- `{chat_name}_language_distribution.png` - Pie chart of language usage
- `{chat_name}_{participant}_word_frequency.png` - Top words bar charts

### V3.0 Advanced Visualizations (15 charts):
- `{chat_name}_v3_expressive_lengthening.png` - Emotional expressiveness bar chart
- `{chat_name}_v3_emotional_cooling_alerts.png` - Cold shift detection timeline
- `{chat_name}_v3_final_word_dominance.png` - Session ending dominance (bar + pie)
- `{chat_name}_v3_thought_fragmentation.png` - Rapid-fire messaging analysis
- `{chat_name}_v3_conversational_entropy.png` - Rut vs dynamic over time
- `{chat_name}_v3_defensiveness_index.png` - Shielding word usage per 1000 words
- `{chat_name}_v3_vocabulary_contagion.png` - Word adoption heatmap
- `{chat_name}_v3_topic_avoidance.png` - Delayed response topics
- `{chat_name}_v3_gini_coefficient.png` - Effort inequality over time
- `{chat_name}_v3_conversational_inertia.png` - Chat revival effort gauge
- `{chat_name}_v3_signal_to_noise_ratio.png` - Conversation depth analysis
- `{chat_name}_v3_chaser_retreater.png` - Anxious-avoidant pattern detection
- `{chat_name}_v3_tit_for_tat_retaliation.png` - Delay mirroring score
- `{chat_name}_v3_temporal_syncopation.png` - Rhythm unpredictability
- `{chat_name}_v3_dashboard.png` - Comprehensive V3.0 overview dashboard

## Test Results

### Chat 1: drxnem
- **Total messages**: 2,109
- **Message distribution**: drxnem (1,030) vs David (1,079)
- **Language**: 67.75% English, 32.25% Georgian
- **First message**: 2025-05-31 21:20
- **V3.0 Insights**:
  - Expressive Lengthening: David (0.011) > drxnem (0.0016)
  - Final Word Dominance: drxnem ends 62.6% of sessions
  - Cold Shifts Detected: 4 (Dec 2025 - Feb 2026)
  - Chaser/Retreater Pattern: 10 instances detected
  - Vocabulary Contagion: drxnem adopted 39 words from David

### Chat 2: Mariam Merabishvili
- **Total messages**: 3,051
- **Message distribution**: David (1,064) vs Mariam (1,987)
- **Language**: 94.56% Georgian, 5.44% English
- **First message**: 2025-05-25 19:20
- **Response time**: You average 178.58 min, Partner averages 22.44 min

## Configuration

To change your name in the analysis, edit `main.py`:

```python
MY_NAME = "David"  # Change to your name as it appears in chats
```

To add more chats, modify the `CHAT_PATHS` list in `main.py`.

## Dependencies

- matplotlib >= 3.7.0
- numpy >= 1.24.0
- pandas >= 2.0.0
- python-dateutil >= 2.8.0
