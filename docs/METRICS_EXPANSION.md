# Metrics Expansion — Psychological Gap Analysis & New Metrics

**Goal:** treat the analyzer as a clinical-grade relationship instrument. This doc audits what the current 24 metrics *psychologically* measure, names the blind spots, and specifies new metrics — including composite ones — designed to be platform-agnostic (Instagram today; WhatsApp/Telegram/iMessage later).

---

## 1. What the current metrics actually cover

Mapping the 24 existing metrics onto the dimensions a relationship psychologist assesses:

| Psychological dimension | Covered today by | Coverage |
|---|---|---|
| **Effort symmetry** (who invests) | message counts, Gini, media stats | ◕ good |
| **Availability / responsiveness** | response times, tit-for-tat | ◑ partial (sleep-gap noise) |
| **Attachment dynamics** | chaser/retreater, final word, inertia | ◑ partial (detection buggy) |
| **Emotional expressiveness** | lengthening, cooling alert | ◑ partial (couple-level only) |
| **Linguistic accommodation** | vocabulary contagion | ◔ weak (stopword noise) |
| **Conflict & avoidance** | defensiveness, topic avoidance | ◔ weak (nearly never fires) |
| **Conversation quality** | SNR, entropy, fragmentation | ◔ weak (definitions off) |
| **Repair & rupture cycles** | — | ✗ none |
| **Initiation dynamics** | — | ✗ none (only "final word", not *first* word) |
| **Reciprocity of interest** (questions, follow-ups) | — | ✗ none |
| **Positivity/negativity climate** | — | ✗ none |
| **Bids for attention & turning-toward** (Gottman) | — | ✗ none |
| **Life-rhythm entanglement** (good-morning/good-night, daily rituals) | — | ✗ none |
| **Vulnerability & self-disclosure depth** | — | ✗ none (LLM-assisted) |
| **Power balance in conversation control** (topic setting, question asymmetry) | — | ✗ none |
| **Trajectory / phase of the relationship** | weekly counts only | ◔ weak |

The big structural gap: **almost everything is a whole-history scalar.** A relationship is a *time series*; a psychologist wants trajectories, change-points, and what preceded them. Every metric below must be computable **per arbitrary time window** (day/week/month/custom range) — this is also the requirement of the interactive dashboard (see `HTML_DASHBOARD_DESIGN.md`).

---

## 2. Foundational change: the metric contract

Before adding metrics, refactor to one contract so all of this becomes cheap:

```
metric(events, window, participants, config) -> {
    per_user: {...} | per_pair: {...},
    series:  [(bucket_start, value), ...],   # always emit the time series
    n:       sample size,                    # so UI can grey out low-confidence values
    ci:      optional confidence interval
}
```

- **Events, not messages:** normalize every platform into one event schema:
  `{ts_utc, sender, kind: text|photo|video|voice|call|share|reaction|sticker|edit|unsend|system, text?, duration?, reply_to?, reaction_target?}`.
  Instagram, Telegram, WhatsApp exports all map into this; metrics never see platform fields again. This is the single most important enabler for multi-platform.
- **Every metric emits `series`**, not just the lifetime scalar. The scalar is just the aggregation of the series.
- **`n` everywhere:** a 3-sample "topic avoidance" is gossip, not data. The UI must be able to show uncertainty.

---

## 3. New primary metrics

### Tier 1 — high insight, purely statistical (no LLM)

**M1. Initiation Ratio & Initiation Latency**
Who *opens* each session (chunker already stores `initiated_by` — unused!), and how long after the last session's end. Split by weekday/weekend and by time-of-day.
*Psych:* pursuit/investment asymmetry; the complement of Final Word Dominance. A shift from 50/50 to 80/20 initiation is one of the strongest early cooling signals.

**M2. Question Asymmetry (Curiosity Index)**
Per user: rate of interrogatives (`?`, wh-words, Georgian question particles: რატომ, როგორ, სად, ვინ, რა…) per 100 messages, and **question-answer rate** — fraction of partner's questions that receive a response within the session.
*Psych:* asking is bidding for the other's inner world (Gottman's "love maps"). One-sided curiosity = one-sided interest. Ignored questions are micro-rejections; track the *ignored-question rate* separately — it is a powerful avoidance measure that fixes the broken `selective_topic_avoidance` from the statistical side.

**M3. Bid-and-Response Ledger (turning toward/away/against)**
Detect "bids": messages that invite response (questions, shares/links, photos, "look at this", exclamations). Classify partner's next move: *toward* (engaged reply within session), *away* (ignored / topic change), *against* (dismissive — LLM-assisted later).
*Psych:* Gottman's strongest divorce predictor is the turning-toward rate (masters ≈ 86%, disasters ≈ 33%). Even the statistical approximation (bid answered within session yes/no) is gold.

**M4. Reaction & Emoji Affect Economy**
Reactions are currently *discarded as system noise*. Count given/received reactions per user, reaction reciprocity, ❤️-tier vs 😂-tier composition, and emoji usage per message as a proper affect channel (not "noise" as in current SNR).
*Psych:* reactions are the cheapest form of acknowledgment; who acknowledges whom, and the decay of reaction rate over time, is an effort-fade signal invisible to message counts.

**M5. Circadian Overlap & Sacred Hours**
2-D activity map (hour × weekday) per user; compute overlap coefficient of the two distributions; flag "sacred hours" — late-night (23:00-03:00) share of conversation.
*Psych:* late-night talk = intimacy allocation. Growing/shrinking of the night-share tracks closeness better than volume. Also enables jet-lag/timetable-change detection (life event marker).

**M6. Ritual Stability Index**
Detect recurring patterns: greeting messages after wake-up, good-night closures, daily check-ins ("გამარჯობა", "დილა მშვიდობისა", "good night" within stable time windows). Measure streaks and breaks.
*Psych:* rituals are the skeleton of attachment; ritual *break dates* are prime candidates for "what happened here?" (feeds the change-point explorer, M14, and the LLM pass).

**M7. Repair Latency (rupture → repair cycle)**
Detect ruptures statistically: session ending abruptly mid-exchange (unanswered last message), sharp negative-affect burst, or unusually long silence following an active period. Then measure: time to next contact, *who* reaches out, and effort of the repair message.
*Psych:* couples aren't distinguished by whether they fight but by how fast and who repairs. Combines the fixed `conversational_inertia` (C10) with initiation (M1). The *failed-repair count* (reach-out that got no answer) is the loneliest number in the dataset — currently a discarded edge case.

**M8. Voice/Call/Media Modality Ladder**
Share of communication by modality (text → voice note → call → video call) over time, per initiator. Call durations summed per week.
*Psych:* modality escalation = intimacy escalation; retreat from calls back to text often precedes distancing. Currently calls are counted but durations never summed or trended.

**M9. Message Depth Distribution (replaces SNR)**
Instead of a single signal/noise ratio: distribution of message lengths (words), share of substantive messages (> N content words after stopwords), median words per *turn* (consecutive burst as one unit — fixes fragmentation interplay).
*Psych:* depth histograms make "we only exchange memes now" visible as a shape change, not a fragile ratio.

**M10. Double-Texting & Re-engagement Persistence**
Per user: rate of sending another message after ≥X min of no reply; distribution of "how many unanswered messages before giving up".
*Psych:* direct behavioral measure of anxious pursuit — a much cleaner chaser signal than the 3-day Pearson correlation (bug C6).

**M11. Conversation Half-Life**
Per session: time from start to the point where inter-message intervals exceed 3× the session median (momentum loss), and who was the last to hold momentum.
*Psych:* "do our conversations die of natural causes, or does one person kill them" — quantifies who deflates conversations, complementing final-word dominance.

**M12. Read-the-Room Adaptivity (style matching)**
Language Style Matching (LSM) score: correlation of *function-word* usage rates (pronouns, particles) between users per month — the standard computational psycholinguistics measure of rapport (Pennebaker). Requires Georgian function-word list.
*Psych:* LSM predicts relationship stability in published research; replaces the noisy vocabulary contagion as the primary accommodation measure (contagion stays as a fun "who coined it" view).

**M13. Unsent/Edited Message Rate** *(platform-dependent)*
Instagram exports mark unsent messages; Telegram exposes edits. Rate per user per month.
*Psych:* self-censorship marker; spikes correlate with walking-on-eggshells periods.

### Tier 2 — composite metrics (combine primaries into higher-order constructs)

**M14. Change-Point Timeline (the backbone composite)**
Run change-point detection (PELT/binary segmentation, or simple CUSUM) jointly over the core series: daily volume, initiation ratio, response latency median, affect rate (M4), night-share (M5). Output: dated change-points with the top contributing series.
*Psych & product:* this **is** the user's question "how did the relationship change over time and what caused it". Each change-point becomes a clickable event on the dashboard timeline; the LLM pass reads the transcript ±3 days around it and writes the "what happened" narrative.

**M15. Relationship Phase Classifier**
Cluster months over a feature vector (volume, initiation balance, latency, affect, depth, night-share, modality mix) into phases: *ignition, honeymoon, plateau, drift, rupture, rekindle, dormant*. Rule-based first; refine later.
*Psych:* gives the layperson a narrative arc; gives the psychologist a segmentation to compare metrics *within* phase (comparing honeymoon SNR to drift SNR is meaningful; lifetime averages are not).

**M16. Attachment Style Profile (per user, per relationship)**
Composite score sheet from: double-texting rate (M10, anxious), repair initiation share (M7, secure), response-latency variance + retreat episodes (avoidant), initiation persistence after non-response (anxious). Present as a radar of *behaviors*, explicitly labeled "communication behaviors, not a clinical diagnosis."
*Psych:* the individual metrics are defensible; the composite is the insight users actually want. Keep wording behavioral to stay ethical.

**M17. Effort-Return Curve (investment equilibrium)**
For rolling windows: plot user A's effort (chars+media weighted) against B's *next-window* effort. Slope = responsiveness of the partner to investment; hysteresis = who adapts to whom.
*Psych:* operationalizes "I match your energy" vs "I carry this" over time — the dynamic version of the Gini metric.

**M18. Emotional Bank Account**
Running balance per user: deposits (reactions given, questions asked, fast replies, repair initiations, affection markers) minus withdrawals (ignored bids, ruptures caused, ghost gaps). Plot both balances over time.
*Psych:* Gottman's metaphor made literal; a single intuitive line that summarizes ten metrics for the non-expert view, with drill-down into components.

**M19. Health Score with Subscales**
Top-level 0-100 with four subscales: **Balance** (initiation, Gini, question symmetry), **Responsiveness** (latency, turning-toward), **Warmth** (affect economy, expressiveness, rituals), **Stability** (syncopation, rupture rate, phase volatility). Weighted, documented formula, always shown *with* its subscales to avoid horoscope-effect.

### Tier 3 — LLM-layer metrics (second pipeline stage)

These belong to the existing LLM analysis stage; the statistical layer's job is to *select and package* the right transcript slices (change-point neighborhoods, rupture sessions, phase boundaries — the session-markdown exporter already does 80% of the packaging):

- **Sentiment/affect trajectory** per user per week (valence + arousal), calibrated for Georgian/mixed text — regex sentiment won't work for Georgian; this must be LLM or a Georgian-capable model.
- **Topic map & topic ownership** — who introduces which topics, which topics die (proper replacement for keyword topic-avoidance), topic diversity over time.
- **Conflict episode annotation** — detect conflict spans, classify style per user (criticism/defensiveness/contempt/stonewalling — the Four Horsemen — plus repair attempts), success/failure of repair.
- **Self-disclosure depth ladder** (Altman & Taylor social penetration: facts → opinions → feelings → fears) per week.
- **Humor & inside-jokes registry** — recurring private references; their births and deaths are intimacy markers.
- **Future-talk index** — share of messages referencing shared future plans ("when we", "next summer") vs past; strong commitment proxy.
- **Support-seeking vs support-giving episodes** and whether support attempts landed.

**Cross-layer contract:** every LLM annotation must return message-id ranges so the dashboard can link a narrative claim back to the exact transcript span.

---

## 4. Platform-portability notes

| Capability | Instagram | Telegram | WhatsApp |
|---|---|---|---|
| Reactions | ✔ (in export) | ✔ | ✔ (newer exports) |
| Edits | ✗ | ✔ (`edited`) | partial |
| Reply-to threading | ✗ in export | ✔ (`reply_to_message_id`) | ✔ (quoted) |
| Call logs + duration | ✔ | ✔ | ✔ |
| Voice-note duration | ✔ (file) | ✔ | ✔ |

Design metrics to **degrade gracefully**: M3 (bids) uses `reply_to` when present, falls back to temporal adjacency on Instagram. Keep a per-platform capability manifest so the UI can hide metrics a platform can't support instead of showing zeros.

---

## 5. Priority recommendation

1. **Contract refactor (§2)** — everything else depends on windowed series.
2. **M1, M2, M4, M5** — cheap, high-insight, data already in hand (initiated_by, reactions, timestamps).
3. **M14 change-points + M7 repair** — powers the "what changed and why" experience, the project's stated core question.
4. **M10, M11, M9, M12** — replace/repair the weakest current metrics.
5. **Composites M15-M19** — only after primaries are trustworthy (garbage in → confident-looking garbage out).
6. **Tier 3 LLM metrics** — build alongside the dashboard's transcript-linking.
