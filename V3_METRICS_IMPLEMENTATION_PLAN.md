# Instagram Analysis V3.0 Metrics Implementation Plan

## 📋 Executive Summary

This document outlines the plan to apply our successful V3.0 psychological metrics and advanced visualization framework from the Telegram Analysis project to the Instagram Analysis project.

---

## 🎯 Objectives

1. **Port V3.0 Metrics**: Implement 14 advanced psychological metrics adapted for Instagram data
2. **Enhance Visualizations**: Create V3.0 visualization suite (15 new charts)
3. **Maintain Compatibility**: Preserve existing 10 core metrics while adding new ones
4. **Unified Framework**: Create consistent analysis approach across Telegram and Instagram

---

## 📊 Current State Analysis

### Instagram Analysis Project (Current)
- **Metrics**: 10 core metrics
- **Visualizations**: 6 chart types
- **Structure**: Similar to Telegram Analysis
- **Data Format**: Instagram DM export JSON

### Telegram Analysis Project (Reference)
- **Metrics**: 53 metrics (9 v1 + 30 v2 + 14 v3)
- **Visualizations**: 43 charts per chat
- **V3.0 Metrics**: 14 psychological metrics
- **V3.0 Visualizations**: 15 charts including dashboard

---

## 🔄 Key Differences: Instagram vs Telegram Data

| Aspect | Telegram | Instagram |
|--------|----------|-----------|
| **Message field** | `text` | `content` |
| **Timestamp** | ISO date string | `timestamp_ms` (milliseconds) |
| **Sender** | `from` | `sender_name` |
| **Media** | `photo`, `video`, `voice_message` | `media_type`, `media_url` |
| **Reactions** | Native reactions | Likes only |
| **Edits** | Edit history available | Not available |
| **Replies** | Reply-to-message structure | No reply threading |
| **Date format** | "2026-04-28T12:00:00Z" | Unix timestamp ms |

---

## ✅ V3.0 Metrics Feasibility Assessment

### 🟢 Direct Port (Instagram supports)
These metrics can be implemented with minimal changes:

| Metric | Feasibility | Adaptation Needed |
|--------|-------------|-------------------|
| **expressive_lengthening_index** | ✅ Easy | Use `content` instead of `text` |
| **final_word_dominance** | ✅ Easy | Same logic, different timestamp format |
| **thought_fragmentation_index** | ✅ Easy | 3+ messages in 15s detection |
| **conversational_entropy** | ✅ Easy | Bigram analysis on `content` |
| **defensiveness_index** | ✅ Easy | Word pattern matching |
| **vocabulary_contagion_rate** | ✅ Easy | Word tracking across users |
| **conversational_gini_coefficient** | ✅ Easy | Effort score calculation |
| **conversational_inertia** | ✅ Easy | Gap detection with ms timestamps |
| **signal_to_noise_ratio** | ✅ Easy | Content analysis |
| **chaser_retreater_oscillation** | ✅ Easy | Rolling correlation |
| **tit_for_tat_retaliation_score** | ✅ Easy | Response delay analysis |
| **temporal_syncopation_variance** | ✅ Easy | Tempo variance calculation |

### 🟡 Partial Support (Limited Instagram data)

| Metric | Limitation | Workaround |
|--------|------------|------------|
| **emotional_cooling_alert** | No edit history | Use only emoji/expressive lengthening |
| **selective_topic_avoidance** | No topic embeddings | Use keyword-based clustering |

### 🔴 Not Available (Instagram limitation)

| Metric | Reason | Alternative |
|--------|--------|-------------|
| Edit-based metrics | Instagram doesn't track edits | Remove or use placeholder |
| Reply depth | No reply threading | Skip or estimate from sequences |
| Reactions | Limited to likes only | Use likes as proxy |

---

## 📁 Proposed Project Structure

```
Instagram Analysis/
├── src/
│   ├── __init__.py
│   ├── data_loader.py          # Existing - keep
│   ├── analyzer.py             # Existing - extend
│   ├── analyzer_v2.py          # NEW: V2.0 metrics
│   ├── analyzer_v3.py          # NEW: V3.0 metrics
│   ├── statistics.py           # Existing - keep
│   ├── language_detection.py   # Existing - keep
│   ├── word_frequency.py       # Existing - keep
│   ├── response_time.py        # Existing - keep
│   ├── media_analyzer.py       # Existing - keep
│   ├── visualizer.py           # Existing - keep
│   ├── visualizer_v2.py        # NEW: V2.0 visualizations
│   └── visualizer_v3.py        # NEW: V3.0 visualizations
├── outputs/
│   ├── analysis/               # Existing
│   └── visualizations/         # Existing
├── main.py                     # Update to run all versions
├── V3_METRICS_IMPLEMENTATION_PLAN.md  # This file
└── README.md                   # Update with new features
```

---

## 🔧 Implementation Steps

### Phase 1: Foundation (Week 1)

#### Step 1.1: Create Instagram-adapted V3.0 Metrics Module
**File**: `src/analyzer_v3.py`

```python
"""
Instagram V3.0 Metrics - Adapted from Telegram Analysis
"""

def expressive_lengthening_index(messages, users):
    # Use 'content' instead of 'text'
    # Use 'sender_name' instead of 'from'
    # Handle timestamp_ms format
    pass

def final_word_dominance(messages, users):
    # Convert ms to datetime
    # Detect 4h gaps
    pass

# ... all 14 metrics adapted for Instagram
```

**Key Adaptations**:
- Replace `text` → `content`
- Replace `from` → `sender_name`
- Replace ISO dates → `timestamp_ms / 1000`
- Handle Instagram-specific media types

#### Step 1.2: Update Main Analyzer
**File**: `src/analyzer.py`

```python
from src.analyzer_v3 import (
    expressive_lengthening_index,
    # ... all V3.0 metrics
)

class ChatAnalyzer:
    def analyze(self):
        return {
            # Existing 10 metrics
            'message_counts': self._get_message_counts(),
            # ...
            
            # New V3.0 metrics
            'expressive_lengthening_index': expressive_lengthening_index(self.messages, self.participants),
            # ... all 14 V3.0 metrics
        }
```

---

### Phase 2: Visualizations (Week 2)

#### Step 2.1: Create V3.0 Visualizer
**File**: `src/visualizer_v3.py`

```python
"""
Instagram V3.0 Visualizations
Ported from Telegram Analysis visualizer_v3.py
"""

class AdvancedMetricsVisualizerV3:
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
    
    def generate_all(self, analysis, chat_name):
        self._plot_expressive_lengthening(analysis, chat_name)
        self._plot_emotional_cooling(analysis, chat_name)
        # ... all 15 V3.0 visualizations
```

**15 New Visualizations**:
1. `expressive_lengthening.png`
2. `emotional_cooling_alerts.png`
3. `final_word_dominance.png`
4. `thought_fragmentation.png`
5. `conversational_entropy.png`
6. `defensiveness_index.png`
7. `vocabulary_contagion.png`
8. `topic_avoidance.png`
9. `gini_coefficient.png`
10. `conversational_inertia.png`
11. `signal_to_noise_ratio.png`
12. `chaser_retreater.png`
13. `tit_for_tat_retaliation.png`
14. `temporal_syncopation.png`
15. `v3_dashboard.png` (comprehensive overview)

---

### Phase 3: Integration (Week 3)

#### Step 3.1: Update main.py
```python
from src.visualizer import ChatVisualizer
from src.visualizer_v3 import AdvancedMetricsVisualizerV3

# In main():
visualizer = ChatVisualizer(str(VIZ_DIR))
visualizer_v3 = AdvancedMetricsVisualizerV3(str(VIZ_DIR))

for chat_name, chat_data in chats.items():
    # ... existing code ...
    
    # Generate all visualizations
    visualizer.generate_all_plots(analysis, chat_name)
    visualizer_v3.generate_all(analysis, chat_name)
```

#### Step 3.2: Update README.md
Document all 24 metrics (10 existing + 14 V3.0) and 21 visualizations.

---

## 📊 Metrics Mapping Table

### Existing Instagram Metrics (Keep All)
| # | Metric | Purpose |
|---|--------|---------|
| 1 | message_counts | Who sends more |
| 2 | language_distribution | Georgian/English ratio |
| 3 | day_of_week | Activity by weekday |
| 4 | first_message | Chat start |
| 5 | messages_per_week | Weekly trends |
| 6 | yearly_stats | Yearly breakdown |
| 7 | response_times | Response speed |
| 8 | media_stats | Media usage |
| 9 | word_frequency | Top words |
| 10 | chat_info | Basic info |

### New V3.0 Metrics (Add)
| # | Metric | Instagram Adaptation |
|---|--------|---------------------|
| 11 | expressive_lengthening_index | Use `content` field |
| 12 | emotional_cooling_alert | Emoji + lengthening only |
| 13 | final_word_dominance | Use `timestamp_ms` |
| 14 | thought_fragmentation_index | 3+ msgs in 15s |
| 15 | conversational_entropy | Bigram on `content` |
| 16 | defensiveness_index | Word patterns |
| 17 | vocabulary_contagion_rate | Word adoption tracking |
| 18 | selective_topic_avoidance | Keyword clusters |
| 19 | conversational_gini_coefficient | Effort inequality |
| 20 | conversational_inertia | 72h gap restart |
| 21 | signal_to_noise_ratio | Depth vs filler |
| 22 | chaser_retreater_oscillation | Correlation analysis |
| 23 | tit_for_tat_retaliation_score | Delay mirroring |
| 24 | temporal_syncopation_variance | Rhythm variance |

---

## 🔍 Instagram-Specific Considerations

### Data Format Differences

```python
# Telegram
msg['text']  # → Instagram: msg['content']
msg['from']  # → Instagram: msg['sender_name']
msg['date']  # → Instagram: datetime.fromtimestamp(msg['timestamp_ms'] / 1000)
```

### Media Handling

```python
# Instagram media types
if msg.get('media_type') == 'photo':
    # Count as photo
elif msg.get('media_type') == 'video':
    # Count as video
elif msg.get('media_type') == 'audio':
    # Count as voice message
```

### Missing Features Workarounds

| Missing Feature | Workaround |
|----------------|------------|
| Edit history | Skip edit-based metrics |
| Reply threading | Use message sequences as proxy |
| Reactions | Use likes only |
| Service messages | Filter by message type |

---

## 📈 Expected Output

### Per Chat
- **analysis.json**: 24 metrics (10 existing + 14 V3.0)
- **Visualizations**: 21 charts (6 existing + 15 V3.0)

### Total for All Chats
If analyzing 5 chats:
- 5 × 24 = 120 metric data points
- 5 × 21 = 105 visualization files
- Combined analysis with cross-chat comparisons

---

## 🧪 Testing Strategy

### Test Data
- Use existing Instagram chat exports in `Chats/` directory
- Expected 3-5 chats for initial testing

### Validation
1. **Data Loading**: Verify all messages loaded correctly
2. **Metric Calculation**: Spot-check 3-5 metrics manually
3. **Visualization**: Ensure all charts render without errors
4. **Performance**: Measure analysis time per chat (target: <5 min)

### Test Cases
```python
# Test expressive lengthening
assert expressive_lengthening_index(['hey', 'heyyy', 'ok'], ['user1'])['user1'] > 0

# Test final word dominance
# Verify last message in session is counted correctly

# Test response times
# Verify ms timestamps convert correctly
```

---

## 🚀 Rollout Timeline

| Week | Task | Deliverable |
|------|------|-------------|
| 1 | Port V3.0 metrics | `analyzer_v3.py` with 14 metrics |
| 2 | Create visualizations | `visualizer_v3.py` with 15 charts |
| 3 | Integration & testing | Updated `main.py`, test on all chats |
| 4 | Documentation | Updated README, metrics guide |

---

## 📝 Success Criteria

- ✅ All 14 V3.0 metrics calculating correctly
- ✅ All 15 V3.0 visualizations generating without errors
- ✅ Backward compatibility maintained (existing 10 metrics still work)
- ✅ Performance acceptable (<5 min per chat)
- ✅ Documentation complete
- ✅ Tested on all available Instagram chats

---

## 🔗 Cross-Project Synergy

### Shared Code
- Core V3.0 metric logic can be shared between Telegram and Instagram
- Create `shared_metrics.py` in a common location if needed

### Unified Metrics Guide
- Update `METRICS_GUIDE.md` to include Instagram-specific notes
- Maintain single source of truth for metric definitions

### Consistent Output Format
- Both projects should produce similar JSON structure
- Enables cross-platform comparison analysis

---

## 📞 Next Steps

1. **Review this plan** and approve modifications
2. **Start Phase 1**: Create `analyzer_v3.py` with adapted metrics
3. **Test incrementally**: Add and test 3-4 metrics at a time
4. **Iterate**: Adjust based on Instagram data quirks
5. **Finalize**: Complete all phases and document

---

*Generated for Instagram Analysis V3.0 Implementation*
*Reference: Telegram Analysis V3.0 (src/metrics_v3.py, src/visualizer_v3.py)*
