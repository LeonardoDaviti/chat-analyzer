# Bug Report — Statistical Metrics Pipeline

**Audience:** engineer fixing the metrics.
**Method:** static trace ("simulative debugging") of every metric in `src/` — no data files were touched.
**Severity legend:** 🔴 wrong results silently · 🟠 metric fires rarely/never or is misleading · 🟡 correctness edge case / hygiene.

---

## A. Data-layer bugs (corrupt every downstream metric)

### A1. 🔴 `is_system_message()` never matches "Liked a message" — case bug
`src/normalizer.py:133-143`
`content_lower = content.lower()` but the pattern list contains capitalized `'Liked a message'`. `'Liked a message' in content_lower` is **always False**, so like-notifications are treated as real messages: they get a language, enter word frequency ("liked", "message" pollute top words), inflate message counts, distort response times (a "reply" 3 seconds after a like looks like a fast response), and shift session boundaries.

**Also the inverse bug:** the pattern `'added'` is a bare lowercase substring, so a real message like *"I added you on Steam"* is flagged as system and silently dropped. Same risk for `'reacted'` (*"she reacted badly"*).

**Pseudo-fix:**
```
patterns = [p.lower() for p in SKIP_PATTERNS]           # fix case
match structural fields first: if msg has 'reactions' / 'share' / 'is_unsent' use those
use anchored regexes, not substrings:
    r'^liked a message$', r'^reacted .{1,4} to your message$', r'^.+ sent an attachment\.$'
never drop on a mid-sentence substring
```

### A2. 🔴 Georgian detection counts character **runs**, not characters
`src/normalizer.py:28,84` and `src/language_detection.py:9,34`
`GEORGIAN_PATTERN = re.compile(r'[Ⴀ-ჿ]+')` — the `+` makes `findall` return contiguous **runs**. For `"როგორ ხარ კარგად"` (16 chars, 3 words) `len(findall)` = 3, so `georgian_ratio = 3/16 = 0.19 < 0.3` → classified **"mixed"** (normalizer) or even **"english"** (language_detection, which needs ratio > 0.7). Long pure-Georgian messages are systematically misclassified; short ones ("კი" → 1/2 = 0.5) pass. The headline language distribution is therefore untrustworthy.

**Pseudo-fix:** count characters, not runs:
```
georgian_chars = sum(1 for ch in text if 'Ⴀ' <= ch <= 'ჿ')
```

### A3. 🔴 Two competing language detectors disagree
`ChatAnalyzer._get_language_distribution` calls `language_detection.detect_language` (the old **'á' heuristic**, tuned for *undecoded* text) on **already-decoded** content, while the per-message `language` field comes from `normalizer.detect_language` (different thresholds). After decoding, 'á' no longer exists, so the old detector's assumptions are void. The chart-level distribution and the per-message labels disagree.

**Pseudo-fix:** delete `language_detection.detect_language`; the analyzer should aggregate the per-message `language` field the normalizer already wrote. One detector, one source of truth.

### A4. 🔴 Timezone: all timestamps interpreted in the analyst's machine TZ
Every module uses `datetime.fromtimestamp(ts_ms / 1000)` (`analyzer.py:59`, `analyzer_v3.py:22`, `normalizer.py:115`, `session_chunker.py:85,98`, `session_markdown.py:50`). Instagram exports store UTC epoch ms. Run the pipeline on a UTC server vs a Tbilisi laptop and every hour-of-day, day-of-week, daily bucket, and session date shifts by 4 hours — this is exactly the class of "misses the correct time" errors. A 23:30 message lands on the wrong weekday.

**Pseudo-fix:** add a `timezone` config parameter (default `Asia/Tbilisi` or auto from user profile), use `datetime.fromtimestamp(ts, tz=ZoneInfo(cfg.tz))` everywhere via one shared helper. Ban raw `fromtimestamp` with a lint rule.

### A5. 🟡 Generator-truthiness: every directory "has messages"
`main.py:51-54`, `data_loader.py:194`, `data_combiner.py:187`
`chat_dir.glob("message_*.json")` returns a **generator, which is always truthy**, so `has_msgs = (glob(...) or combined.exists())` is always True — any stray subdirectory is treated as a chat and later crashes or produces garbage.

**Pseudo-fix:** `has_msgs = any(chat_dir.glob("message_*.json")) or (chat_dir / "combined_message.json").exists()`

### A6. 🟡 CLI/session parameters accepted but ignored
`main.py:61-67` — `run_chat_pipeline` takes `session_gap_hours`, `min_session_messages`, `min_session_duration_s` but never forwards them to `chunk_messages` (main.py:105). Also `chunk_messages` mutates module-level globals (`session_chunker.py:124-126`) — not re-entrant. Also hardcoded: export folder name (`main.py:41`), `some_id → <account-owner-name>` (`main.py:93`), `'Some Contact Full Name'` in the summary print (`main.py:124`).

**Pseudo-fix:** thread parameters through function args (or a `Config` dataclass); delete the globals; derive "my name" from the export folder's profile, not hardcoded strings.

---

## B. Session-chunking bugs

### B1. 🔴 Tiny-session merging ignores time distance → corrupted sessions
`src/session_chunker.py:288-347` — `_merge_tiny_sessions` buffers every tiny (<3 msg) session and merges it into the **next** large session *no matter how far away it is*. `MERGE_THRESHOLD_MINUTES = 60` is defined (line 34) and **never used**. A 2-message exchange in March gets absorbed into a large session in May → that session's `duration_minutes` becomes tens of thousands, its `date`/`time_range` are wrong, and its avg response time includes a multi-week "response".

**Pseudo-fix:** only merge a tiny session into an adjacent session if `gap ≤ MERGE_THRESHOLD_MINUTES`; otherwise drop it into a "micro-interactions" bucket (still valuable data — see metrics doc) instead of deleting it.

### B2. 🟠 Trailing/leading tiny sessions silently deleted
Same function: tiny sessions after the last large session (and any that fail the filter) are discarded, so `sessions.json` under-reports messages with no log line. Doc comment even says "Tiny sessions before the first large session stay as-is" but the code buffers them into the *first* large session — comment and code disagree.

**Pseudo-fix:** never delete data; tag sessions `valid: false` and let consumers filter. Log counts of dropped/merged messages.

### B3. 🟠 Two conflicting session definitions in the same codebase
Pipeline chunker uses **2 h** gap (`session_chunker.py:24`); every V3 metric re-derives sessions with a **4 h** gap (`analyzer_v3.py:143,194,815`). "Final word dominance" is therefore computed on sessions that don't match `sessions.json`, and no two numbers reconcile.

**Pseudo-fix:** chunk once, pass `sessions` into V3 metrics; single `SESSION_GAP` constant in config.

---

## C. Per-metric bugs (`src/analyzer_v3.py`)

### C1. 🔴 `thought_fragmentation_index` — denominator counts messages, not sessions
Lines 220-224: the "total_sessions" loop has **no `break`**, so it increments once per *message* → denominator is message count and the index is deflated ~10-50×.
Three more bugs in the same function:
- **Last session never processed** — flush only happens on gap detection, so the final session (and for a chat with no 4h gaps, the *entire chat*) is skipped. Same missing-flush bug in `temporal_syncopation_variance` (lines 820-855).
- Attribution: when a burst is found, credit goes to `current_session[0]`'s sender (first `break` at line 218) — i.e. whoever happened to send the session's first message, not who did the rapid-fire burst.
- The 3-in-15s window doesn't require the same sender (lines 209-212) — a fast ping-pong exchange counts as "fragmentation".

**Pseudo-fix:**
```
for each session (flush last one too):
    for each user: total_sessions[user] += 1 if user sent ≥1 msg
    scan windows of 3 consecutive msgs from the SAME sender within 15s
    fragmented[user] += 1 (once per session per user, then break)
index = fragmented / total_sessions   # now ≤ 1 by construction
```

### C2. 🔴 `final_word_dominance` — first session's ender can be lost + wrong gap
Lines 149-168: `current_session_end_user` starts as `None`; if the first session contains a single message, its ender is never counted (session counted in `total_sessions`, ender dropped → percentages don't sum to 1). Uses 4h gap (see B3).

**Pseudo-fix:** iterate the *chunker's* sessions and count `session['participants']['ended_by']` — the field already exists.

### C3. 🟠 `emotional_cooling_alert` — overlapping windows can't drop 40%; negative-slice edge
Lines 108-115: `prev_window = sorted_dates[i-14:i]` vs `curr_window = sorted_dates[i-13:i+1]` — the two windows **share 13 of 14 days**, so a genuine cooling of 40% between them is nearly impossible; the metric almost never fires (a "missed queries" bug). At `i=13`, `i-14 = -1` → Python negative slice returns the wrong window entirely. Additional problems: `sorted_dates` holds only *active* days, so "14 days" is really "14 active days" (could span months); both scores divide by literal `14` instead of window length; the emoji regex misses `❤` (U+2764), U+1F900-1F9FF, skin-tone modifiers; the metric is computed for the couple jointly, so you can't see *who* cooled.

**Pseudo-fix:** build a continuous daily calendar (0 for silent days); compare **disjoint** windows (previous 14 calendar days vs current 14); compute per user; widen emoji regex or use a library; also normalize by message volume so "fewer messages" ≠ "less expressive per message".

### C4. 🟠 `selective_topic_avoidance` — threshold statistically unreachable
Lines 458-476: flags a topic when its **mean** is >3σ above the population mean, where σ is the std of *individual* response times. Response times are heavy-tailed (overnight gaps push σ to hundreds of minutes), so a topic mean 3σ out essentially never happens → metric silently returns `{}` for real data. Also: topic keyword lists are ~5 words; `kw in prev_text` is substring matching (Georgian `"დედა"` matches inside unrelated words; `"პარტია"` means political party, not "party"); only the *previous* message is topic-tagged and `break` stops at the first topic.

**Pseudo-fix:** compare medians (robust); test significance with Mann-Whitney U or use standard-error of the mean (σ/√n) with a 2σ threshold; log-transform delays or cap at session boundaries; word-boundary matching; allow multi-topic tagging. Longer-term: topic assignment belongs to the LLM pass, statistics stay here.

### C5. 🟠 `tit_for_tat_retaliation_score` — measures the wrong thing
Lines 759-799: docstring promises "mirroring of delayed responses" (A delays → B retaliates), but the code computes lag-1 autocorrelation of a user's **own** delay series — self-consistency, not retaliation. Cross-session gaps (sleep) dominate the correlation so even that number is noise. `r` is also squared and called R² while the sign (the interesting part) is thrown away.

**Pseudo-fix:** build pairs `(delay_of_A_at_turn_k, delay_of_B_at_turn_k+1)` **within sessions only**, log-transform, report the signed Pearson r per user; positive r for B = B mirrors A's delays.

### C6. 🟠 `chaser_retreater_oscillation` — silent days dropped, negative-slice, n=3 Pearson
Lines 705-716: `for i in range(2, ...)` with `sorted_dates[i-3:i]` → at `i=2` the slice is `[-1:2]`, wrong window (same class of bug as C3). Only days *with* messages exist in `daily_counts` — but a day where the retreater sent **0** is exactly the signal, and it's excluded. Pearson over 3 points crosses the −0.6 threshold constantly by chance → false positives.

**Pseudo-fix:** continuous calendar with zero-filled days; window ≥ 7 days; require minimum total volume in window; report the rolling correlation series (for the dashboard) instead of only threshold crossings.

### C7. 🟠 `conversational_entropy` — normalization makes every month ≈ 1.0
Lines 287-291: normalizing Shannon entropy by `log2(unique_bigrams)` yields ~1.0 whenever most bigrams occur once (which is always true for chat text) → flat, uninformative series. Also the return shape is `{month: {user: v}}` but the no-message early return is `{user: 0.0}` — inconsistent shape breaks consumers.

**Pseudo-fix:** report raw entropy alongside a **vocabulary-size-controlled** baseline (compare to shuffled text of same length), or use type-token ratio / MTLD instead; unify return shape.

### C8. 🟠 `signal_to_noise_ratio` — tokens never cleaned before stopword check
Lines 655-666: `words = text.split()` then `if word in stop_words` — tokens keep punctuation and case, so `"Ok,"`, `"Yes."`, `"The"` are never counted as noise. `text_lower` is computed and never used (line 654). Meanwhile 4+-char stopwords ("been", "have") count as *signal*, and a word like "been" can be counted as **both** signal and noise. Emojis counted as noise is also psychologically backwards — emoji are affect signal (see metrics doc).

**Pseudo-fix:** normalize token once (`lower`, strip punctuation), classify each token exactly once (stopword → noise, ≥4 chars → signal, else neutral); move emoji to its own affect channel.

### C9. 🟡 `conversational_gini_coefficient` — crash risk + misdocumented
Lines 511-528: docstring says "rolling 30-day" and type hint says per-user `Dict[str, float]`, but it returns `{month: gini}` over calendar months. `calculate_gini` divides by `cumsum[-1]` *before* the `if cumsum[-1] > 0` guard (line 520-521) → `ZeroDivisionError` on a month where both users' effort is 0 (possible: only system/like messages). Gini over exactly 2 values is just `|a−b|/(a+b)` — fine, but say so.

**Pseudo-fix:** guard first, divide second; fix docstring/type; consider returning the simple effort-share ratio per month, which is more interpretable for 2 people.

### C10. 🟡 `conversational_inertia` — dead code + discarded failed restarts
Lines 541-581 are an entire **dead first implementation** (its guard condition can never become true) left above the "simplified approach" — delete it (it also contains an O(n²) `sorted_msgs.index(msg)` call). In the live loop: if a second >72h gap occurs while still in recovery, `recovery_effort = effort` silently **resets**, so failed restarts (messages into the void that never got an answer) are discarded — psychologically the most interesting case. Returns a single blended float; can't see *who* pays the restart cost.

**Pseudo-fix:** on new dead-gap while in recovery, first `append` the pending effort tagged `answered: false`; track per initiating user; return `{user: {avg_restart_effort, failed_restarts, answered_restarts}}`.

### C11. 🟡 `vocabulary_contagion_rate` — stopwords count as "slang"
Lines 361-389: any ≥3-char word counts, so "the", "and", "რომ" register as adopted vocabulary; whoever texted first is the "cultural driver" of the entire common language. `adopter_ts >= first_ts` also credits simultaneous first use.

**Pseudo-fix:** filter both stopword sets; require the word be *distinctive* (used ≥N times by driver **before** adopter's first use, and rare globally — e.g. not in the chat's top-quartile frequency); require a minimum time gap between first uses.

### C12. 🟡 `expressive_lengthening_index` — regex over-matches
Line 43: `(.)\1{2,}` matches `"www"` in URLs, `"..."`, `"2000"`, and repeated emoji. Fine as a v1, but URLs and numerals should be stripped first, and repeated punctuation (`!!!`, `???`) deserves its own counter (it's emphasis, not lengthening).

### C13. 🟡 `response_time.py` — headline number dominated by sleep
`calculate_response_times` runs over the raw message list with no session awareness, so the "avg response 178 min" headline is mostly overnight gaps, and replies to system messages count as replies. `_stats` percentiles use naive indexing (`n//4`, `3*n//4`, `n//2`) — biased for small n.

**Pseudo-fix:** compute within sessions (or cap at the session gap); lead with **median** everywhere; use `statistics.quantiles`; keep "time to re-open conversation" as its own, separate metric (initiation latency — see metrics doc).

### C14. 🟡 `_get_messages_per_week` — ISO week / calendar year mismatch, diluted averages
`analyzer.py:115-138`: pairs `timestamp.year` with `isocalendar()[1]` — Dec 29-31 can be ISO week 1 (of *next* year) and Jan 1-3 can be week 52/53 of the *previous* year, so year-boundary messages land in phantom buckets ("week 1 of 2025" containing December 2025 messages). `average_per_week` divides by all 53 weeks even if the chat existed for 6 → underestimates. 

**Pseudo-fix:** use `ts.isocalendar()` for *both* year and week (`iso_year, iso_week, _ = ...`); average only over weeks between first and last message.

### C15. 🟡 Counting: system/media rows inflate core counts
`message_counts`, `day_of_week`, `yearly_stats`, `messages_per_week` all iterate raw `self.messages` including likes/attachment notices (worsened by A1). Decide one rule — e.g. real messages for text metrics, all events for an "interactions" metric — and apply it via a single shared `is_real_message` predicate (there are currently two: `normalizer.is_system_message` and `session_chunker.is_real_message`, with different logic).

### C16. 🟡 `session_markdown.py` — media invisible to the LLM, groups span days
`group_consecutive_msgs` (lines 41-76): `msg.get('type')` is checked, but the normalizer never writes a `type` field, so photos/videos/shares have empty content → `continue` → the LLM transcript **silently omits all media exchanges** (a hug-photo or a 40-minute call disappears from the story). Groups join consecutive same-sender messages regardless of time gap, showing only the first timestamp — messages days apart appear as one breath; the `{new_date}` marker logic can also miss a date change that happens *inside* a group.

**Pseudo-fix:** derive `type` in the normalizer (`photos`→photo, `videos`→video, `audio_files`→voice, `share`→share, `call_duration`→call w/ duration); render placeholders like `[PHOTO]`, `[CALL 12min]`; break groups on gap > ~10 min and on date change.

---

## D. Fix priority for the engineer

| Order | Items | Why first |
|---|---|---|
| 1 | A1, A2, A3, A4 | Every metric consumes this data; fixing later invalidates all tuning |
| 2 | B1, B3, C1, C2 | Session identity is the unit of nearly all psychology metrics |
| 3 | C3-C8, C13, C14 | Metrics that currently mislead or never fire |
| 4 | C9-C12, C15, C16, A5, A6, B2 | Hygiene, crashes, LLM-input quality |

**Regression safety:** before refactoring, snapshot current `analysis.json` for one chat, then assert intentional diffs only. Add unit tests with tiny synthetic message lists (5-10 messages, known answers) per metric — `tests/test_metrics.py` exists; extend it with the failure cases above (e.g. "Liked a message" filtering, ISO week at year boundary, last-session flush).
