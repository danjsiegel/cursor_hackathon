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

4. **Code execution**
   - The app runs the agent's code with `exec()` in the same process (so `pyautogui` controls the machine where Streamlit is running). See below if steps report "Pass" but nothing happens on screen.

5. **Fail gracefully**
   - Screenshot fails → session stops with an error message; you can start a new task.
   - Step code throws → step is logged as failed, session stops with "Step failed: … No retry."
   - Step verification says "not achieved" → session stops with "Step verification failed: …"
   - API/parsing errors → warning or error in the UI; stub is used when the API is unavailable.
   - Any uncaught exception in the loop → "Task failed: … Stopping. You can start a new task."

## Steps pass but nothing happens on screen (macOS)

The code **is** being executed: we call `exec(code_to_run, _run_globals)` and you see "Step done. Outcome: Pass." So if nothing actually happens (Calculator doesn’t open, no typing, no clicks), the failure is that **pyautogui isn’t allowed to control the display**. On macOS that almost always means the process running Streamlit (Terminal or Cursor) doesn’t have **Accessibility** permission, so `pyautogui.hotkey()` / `pyautogui.click()` run but have no effect.

**How to fix**

1. Open **System Settings** (or System Preferences on older macOS).
2. Go to **Privacy & Security** → **Accessibility**.
3. Add the app that is **running** your Streamlit process:
   - If you run `uv run streamlit run app.py` from **Terminal**, add **Terminal** to the list and enable it.
   - If you run from **Cursor**’s integrated terminal, add **Cursor** (and optionally **Terminal** if Cursor uses it).
4. If the list is locked, click the lock and authenticate.
5. **Restart** the Terminal/Cursor window (or quit and reopen the app), then start Streamlit again.
6. In the app sidebar, use **Re-check automation** to run the check again; the warning should disappear when the app can control the display.

The app runs a check on load and shows a warning in the sidebar when pyautogui cannot control the display. After granting Accessibility, click **Re-check automation** in the sidebar to refresh the flag without reloading the page.

## Project layout

- `app.py` — Streamlit app, DuckDB schema, screenshot, MiniMax calls, step verification, task translator fallback.
- `pyautogui_check.py` — Display-control check (pyautogui can control the screen); used for the sidebar warning and `pyautogui_control_ok` flag.
- `prompts/` — System prompt templates (`.txt`) with `{placeholders}`; see `prompts/README.md`.
- `task_translator.py` — Rule-based thought→code (giant if/else + `data/task_translator_rules.json`). Used before the API when code is missing.
- `data/` — `universal_tasker.duckdb`, `screenshots/`, `task_translator_rules.json`.
- `scripts/analyze_audit_log.py` — List (thought, code) from DuckDB; `--export` merges them into `task_translator_rules.json`.
