# Interactive HTML Dashboard — Design Document

**Replaces:** the 22+ static matplotlib PNGs.
**Deliverable:** one self-contained `report.html` per chat (plus an optional multi-chat index), openable by double-click, no server, no internet required (privacy: chat data never leaves the machine).

---

## 1. Product requirements (from project goals)

1. **Freedom of tuning** — user selects any date range, any granularity (day/week/month), any participant view, and every number on screen recomputes for that slice.
2. **Trajectory-first** — "how did the relationship change over time and what caused it" is the home screen, not an appendix.
3. **Evidence-linked** — every claim (metric spike, change-point, LLM narrative) links to the underlying transcript span.
4. **Premium feel** — one coherent design system, dark/light, smooth interactions; not a grid of disconnected charts.
5. **Platform-agnostic** — renders from the normalized event schema (see `METRICS_EXPANSION.md` §2), so Telegram/WhatsApp reports use the same file.

## 2. Architecture

```
pipeline (python) ──► events.json + precomputed daily aggregates + llm_annotations.json
                              │
                     build step inlines them as
                     <script type="application/json" id="data"> … </script>
                              │
                  report.html  (single file: HTML + CSS + JS + data)
```

- **Compute split:** Python precomputes the *daily* aggregate table (one row per user per day: msg count, words, chars, media counts, reactions, questions, initiations, response-latency digest, affect counts…). The browser derives **everything** else (weekly/monthly rollups, windowed metrics, comparisons) from daily rows. Rationale: daily rows for a 5-year chat ≈ a few thousand rows — trivial for JS; this is what makes arbitrary-range recomputation instant without shipping Python logic to the client.
  - Exceptions that stay in Python: change-point detection, per-session stats, LLM annotations. These are precomputed and shipped as event lists.
  - Raw transcript: shipped as compressed session blobs (only decompressed on drill-down) or, if size is a concern, as a sibling `transcript.json` the HTML lazy-loads via `fetch` when opened from disk with `--allow-file-access` issues avoided by inlining. **Default: inline everything; only split if the file exceeds ~50 MB.**
- **Library:** **ECharts** (single ~1 MB script, inlined). Justification: canvas rendering for big series, built-in crosshair tooltips/`dataZoom` brush/heatmap/calendar charts, no build toolchain needed for a single-file artifact. Alternative if bundle size matters more than features: **uPlot** + hand-rolled heatmap. Avoid Plotly (heavy) and d3-from-scratch (cost).
- **No framework.** Vanilla JS modules concatenated by the build step; state is one plain `store` object + pub/sub. Keeps the artifact auditable and dependency-free.

## 3. Global controls (the "freedom" layer)

Per the dataviz interaction rules: **one filter row, above all content; date range first; filters scope everything below them.**

```
┌────────────────────────────────────────────────────────────────────────┐
│ [Date range ▾: All time · 30d · 90d · 1y · Custom]  [Granularity: D/W/M]│
│ [View: Both ▾ | User A | User B | Difference]   [Compare: + period]  ☾ │
└────────────────────────────────────────────────────────────────────────┘
```

- **Date range**: preset rows (All time, last 30/90/365 days, each calendar year, each detected *phase* from M15) + custom range. Also settable by **brushing any timeline chart** (brush → "apply as global range" chip appears).
- **Granularity**: day/week/month bucketing for all series (auto-picks sensible default from range length).
- **View**: both users (categorical 2-series), single user, or *difference/balance* mode (diverging charts centered on 0 — who leads).
- **Compare**: pin a second period (e.g. "Jun-Aug 2025 vs Jun-Aug 2026"); charts render period B as a lighter ghost series; KPI tiles show deltas.
- **Refetch keeps the frame**: on range change, charts re-render in place from cached daily rows (<16 ms target); no skeletons, no layout jumps.
- ☾ dark-mode toggle — dark palette is its own validated ramp set, not a CSS invert.

## 4. Page structure (single scrolling page, sticky section nav)

### §A — Pulse (KPI row)
Stat tiles, not charts: total messages (in range), messages/day with delta vs previous equal-length period, median response time per user, initiation balance, turning-toward rate, current Health Score with subscale popover. Each tile: value + delta arrow + 90-day sparkline. Every tile is a click-scroll to its detail section.

### §B — Story Timeline (the centerpiece)
One full-width band, three synchronized lanes sharing an x-axis with a `dataZoom` brush:

1. **Volume river** — stacked/mirrored area, User A above axis, partner mirrored below (balance visible at a glance).
2. **Metric lane** — user-selectable overlay (dropdown: response latency, affect rate, night-share, depth, initiation ratio…), one line per user. Single y-axis; switching metric swaps the lane, never adds a second axis (dual axes are banned).
3. **Event lane** — markers: change-points (M14, diamond), ruptures/repairs (M7), ritual breaks (M6), longest-silence bars, LLM-annotated episodes. Hover = summary card; **click = opens the Evidence drawer** (see §F) with the transcript around that date and the LLM "what happened" note.

This section *is* the answer to "how did it change over time and what caused that".

### §C — Rhythm
- **Hour × weekday heatmap** per user, side by side (sequential ramp, one hue; shared color scale).
- **Calendar heatmap** (GitHub-style, per year) of daily volume; click a day → Evidence drawer for that day.
- **Session gallery**: beeswarm/strip of sessions (x = date, y = duration, size = messages, color = initiator — 2 fixed categorical hues). Click session → drawer with per-session stats + transcript.

### §D — Balance & Effort
- Diverging bars centered at 0: initiation share, question share, reaction share, effort share, final-word share per bucket.
- **Effort-return curve** (M17) as connected scatter with time-colored (sequential) trail.
- Emotional Bank Account (M18): two cumulative lines.

### §E — Language & Affect
- Depth distribution (histogram, per user, overlaid at 60% opacity with 2px surface ring).
- Emoji/reaction economy: top-N table + trend sparkline each (tables beat >7-slice charts).
- Word/phrase explorer: search box → frequency-over-time chart for any word ("when did we stop saying X"); top distinctive words per user per phase (log-odds, not raw counts).
- LSM / style matching line with phase bands shaded behind.

### §F — Evidence drawer (right-side panel, the trust layer)
Opens from any event/day/session click: header (date, participants, session stats) → LLM annotation if present → virtualized transcript viewer (sender-colored 3px left border, day separators, media placeholders `[PHOTO] [CALL 12min]`). Search-within-transcript. **Never render message text via innerHTML — textContent only** (chat text is untrusted input; this is the top XSS vector in this product).

### §G — LLM Insights
Narrative cards from the LLM pass (phase summaries, conflict episodes, inside-joke registry, future-talk trend). Every card carries "show evidence" → drawer with the exact message range. Cards without evidence links must not ship.

## 5. Visual design system

Follow the dataviz skill procedure; parameters:

- **Categorical (identity):** exactly 2 series nearly everywhere — user A gets hue 1, user B gets hue 2, **fixed for the entire report** (color follows the entity; filters never repaint). Start from the reference palette in the skill (`references/palette.md`) and **run `scripts/validate_palette.js` for both light and dark surfaces before shipping** — don't eyeball CVD safety.
- **Sequential (magnitude):** one hue light→dark for heatmaps/calendars.
- **Diverging (balance views):** user-A-hue ↔ user-B-hue with neutral gray midpoint at 0 = perfect balance. This makes "balance" a *visual language* used consistently across §D.
- **Status:** reserved good/warning/serious set for Health subscales and rupture markers only; always icon + label, never color alone.
- Marks: 2px lines, thin bars with 4px rounded data-end, 2px surface gaps between adjacent fills, ≥8px markers with ≥24px hit areas, recessive grid.
- Tooltips: crosshair on time charts listing **both** users' values at that X (value leads, label follows, line-keys not boxes); per-mark tooltips on bars/cells with hover lift.
- Every chart gets a ⋮ menu: *view as table* (accessibility requirement), *copy data (CSV)*, *export PNG*.
- Typography: one sans stack; hero numbers ≥48px; text always in ink tokens, never in series colors.
- Low-confidence values (small `n` from the metric contract) render muted with an `n=…` badge — the anti-horoscope rule.

## 6. State, URLs, and reproducibility

- Global state (`range, granularity, view, compare, section`) serialized into `location.hash` → any view is shareable/bookmarkable and the exact view can be cited in a discussion ("look at `#range=2025-11..2026-01&metric=latency`").
- A "Method" footnote per metric (small ⓘ) showing the formula and its parameters (session gap, thresholds) — the tuning transparency the current PNGs completely lack.
- Optional **settings panel** exposing pipeline parameters that are safe to recompute client-side (session gap for session-derived views if session boundaries are shipped at multiple gap levels: precompute sessions at 1h/2h/4h and let the user switch).

## 7. Build & migration plan

1. **Phase 1 — data:** implement the daily-aggregate exporter + `report_data.json` (blocked on bug fixes A1-A4; do not ship a premium UI over broken numbers).
2. **Phase 2 — skeleton:** filter row + §A KPI + §B volume lane, from real data. This alone already beats all 22 PNGs.
3. **Phase 3 — interactivity core:** brush-to-range, Evidence drawer, session gallery.
4. **Phase 4 — full sections** (§C-§E), dark mode, palette validation, table views.
5. **Phase 5 — LLM integration** (§G + event-lane annotations).
6. Keep matplotlib output behind a `--legacy-plots` flag during transition, then delete.

**Definition of done per chart:** passes the anti-pattern checklist (no dual axes, no cycled hues, no color-alone identity), palette validator passes light+dark, has tooltip + table view, renders correctly for: 1-week chat, 5-year chat, chat with 6-month silence, single-sided chat.
