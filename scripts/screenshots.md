# Regenerating the README screenshots

All README images live in `docs/img/` and are built from a **synthetic** corpus
(invented names and messages — never anyone's real chats). The generator is
`scripts/make_synthetic_corpus.py`; the capture driver is
`scripts/screenshots.py`.

## Automatic (preferred)

```
venv/bin/python scripts/screenshots.py
```

This creates a throwaway `CHAT_ANALYZER_HOME` under `/tmp`, generates the
corpus, runs the full pipeline + dashboard/connected/insights builders there,
drives a headless Chromium-family browser (`chromium`, `google-chrome-stable`,
or `brave`; `firefox` as a last resort) and writes five PNGs into `docs/img/`:

| File | What it shows |
|------|---------------|
| `chat.png` | Per-chat view: pulse metrics, timeline, balance charts, platform filter |
| `findings.png` | The Findings cards (hoisted to the top of the page for the shot) |
| `connected.png` | The 👤 You — Connected cross-chat profile |
| `platform_filter.png` | The chat picker open, with platform filter chips + chat list |
| `setup.png` | The launcher `/setup` drop page (folder drop, Re-analyze, Start fresh) |

Add `--keep` to keep the temp home for inspection.

> Note: the driver applies a **temp-copy-only** workaround for an upstream
> SyntaxError in the generated dashboard's inline JavaScript (an unescaped
> apostrophe in a `findings-empty` string) so the charts render for the
> screenshot. It never edits the repo's dashboard template. Once that template
> bug is fixed the workaround becomes a no-op.

## Manual (if no headless browser is available)

1. Build the corpus + dashboard into a temp home:
   ```
   export CHAT_ANALYZER_HOME=/tmp/ca-shots
   venv/bin/python scripts/make_synthetic_corpus.py --out /tmp/ca-shots
   venv/bin/python -c "import main; from pathlib import Path; \
     main.run_all(base_dir=Path('/tmp/ca-shots'), \
     output_dir='/tmp/ca-shots/Outputs', generate_visualizations=False)"
   venv/bin/python build_dashboard.py --output-dir /tmp/ca-shots/Outputs --dash-dir /tmp/ca-shots/Dashboard
   venv/bin/python build_connected.py --chats-dir /tmp/ca-shots/Chats --dash-dir /tmp/ca-shots/Dashboard
   venv/bin/python build_insights.py --dash-dir /tmp/ca-shots/Dashboard
   ```
2. Open `/tmp/ca-shots/Dashboard/index.html` in a real browser at a wide
   window (~1440px). Capture:
   - **chat.png** — the first chat selected (top of the page: pulse tiles,
     timeline, balance charts). The platform filter chips are next to the chat
     picker in the header.
   - **findings.png** — scroll to the **📋 Findings** section.
   - **platform_filter.png** — click the chat picker to open the dropdown so the
     platform filter chips and the chat list are both visible.
   - **connected.png** — pick **👤 You — Connected** from the chat picker.
3. For **setup.png**, run the launcher and open its `/setup` page:
   ```
   CHAT_ANALYZER_HOME=/tmp/ca-shots venv/bin/python launcher.py
   # then open http://127.0.0.1:8347/setup
   ```
   Capture the drop page (drop zone, "choose a folder", Re-analyze, Start fresh).
4. Save all PNGs into `docs/img/` with the filenames in the table above.
