# Universal Tasker (Cursor Hackathon)

Autonomous UI agent: prompt a goal, it takes screenshots, calls MiniMax for next steps, runs pyautogui code, and verifies each step. Results and audit log live in DuckDB.

## Run the UI and test

1. **Install and run**
   ```bash
   cd cursor_hackathon
   uv sync
   uv run streamlit run app.py
   ```
   Open the URL Streamlit prints (e.g. http://localhost:8501).

2. **Prompt and run**
   - Enter a **goal** (e.g. "Open Calculator and add 3+3").
   - Optionally set **Your browser** (e.g. Firefox) so the agent knows your environment.
   - Click **Start Task**. The app will capture the screen, call the agent (stub or API), run the returned code, and verify the step.

3. **Modes**
   - **Stub (default):** No API key needed. Uses built-in demo steps (e.g. open Calculator, type Hello World). Good for UI/testing.
   - **Live API:** In `.env` set `MINIMAX_API_KEY=your_key` and `USE_MINIMAX_STUB=false`, then restart. The agent uses MiniMax for reasoning and code.

4. **Fail gracefully**
   - Screenshot fails → session stops with an error message; you can start a new task.
   - Step code throws → step is logged as failed, session stops with "Step failed: … No retry."
   - Step verification says "not achieved" → session stops with "Step verification failed: …"
   - API/parsing errors → warning or error in the UI; stub is used when the API is unavailable.
   - Any uncaught exception in the loop → "Task failed: … Stopping. You can start a new task."

## Project layout

- `app.py` — Streamlit app, DuckDB schema, screenshot, MiniMax calls, step verification, task translator fallback.
- `prompts/` — System prompt templates (`.txt`) with `{placeholders}`; see `prompts/README.md`.
- `task_translator.py` — Rule-based thought→code (giant if/else + `data/task_translator_rules.json`). Used before the API when code is missing.
- `data/` — `universal_tasker.duckdb`, `screenshots/`, `task_translator_rules.json`.
- `scripts/analyze_audit_log.py` — List (thought, code) from DuckDB; `--export` merges them into `task_translator_rules.json`.
