# Universal Tasker (Cursor Hackathon)

Autonomous UI agent: prompt a goal, it takes screenshots, calls MiniMax for next steps, runs pyautogui code, and verifies each step. Results and audit log live in DuckDB.

## Quick Start

```bash
cd cursor_hackathon
cp .env.example .env          # Add your MINIMAX_API_KEY here
uv sync
uv run streamlit run app.py
```

Open http://localhost:8501 and enter a goal like "Open Calculator and add 3+3".

## Setup

1. **Install dependencies**
   ```bash
   uv sync
   ```

2. **Configure API (optional)**
   ```bash
   cp .env.example .env
   # Edit .env and set MINIMAX_API_KEY=your_key
   # Set USE_MINIMAX_STUB=false to use real API
   ```

3. **Grant macOS permissions** (required for automation)
   - See [Troubleshooting](#troubleshooting-macos-permissions) below

4. **Run the app**
   ```bash
   uv run streamlit run app.py
   ```

## Usage

1. Enter a **goal** (e.g. "Open Calculator and add 3+3")
2. Optionally set **Your browser** (e.g. Firefox) for context
3. Click **Start Task**

The agent will:
- Take a screenshot
- Send it to MiniMax for reasoning
- Execute the returned pyautogui code
- Verify each step
- Repeat until done or stuck

## Modes

- **Stub (default):** No API key needed. Uses demo steps. Good for testing UI.
- **Live API:** Set `MINIMAX_API_KEY` and `USE_MINIMAX_STUB=false` in `.env`.

## Troubleshooting (macOS Permissions)

**Symptom:** Steps report "Pass" but nothing happens on screen (no Spotlight, no Calculator, no typing).

**Cause:** macOS requires explicit permission for apps to control keyboard and mouse.

### Run the Diagnostic Script

```bash
uv run python scripts/diagnose_pyautogui.py
```

This interactive script tests mouse, clicks, and keyboard to identify exactly what's broken.

### Grant Permissions

1. **System Settings → Privacy & Security → Accessibility**
   - Add **Terminal** (if running from Terminal)
   - Add **Cursor** (if running from Cursor's terminal)
   - Toggle ON

2. **System Settings → Privacy & Security → Input Monitoring** (macOS Catalina+)
   - Add the same apps as above
   - Toggle ON
   - **This is often the missing piece!** Mouse works without it, but keyboard doesn't.

3. **Restart Terminal/Cursor** after granting permissions

4. **Check "Secure Keyboard Entry"** is disabled:
   - Terminal menu → Edit → Uncheck "Secure Keyboard Entry"
   - Some password managers enable this and block all keyboard automation

5. **Try running from regular Terminal** instead of Cursor's integrated terminal

### Still Not Working?

- **Close password managers** (1Password, etc.) - they can enable Secure Input
- **Check Spotlight shortcut**: System Settings → Keyboard → Keyboard Shortcuts → Spotlight
- **Try a different terminal app**: iTerm2, Terminal.app, Warp
- **Reboot** after permission changes

## Project Layout

```
cursor_hackathon/
├── app.py                    # Main Streamlit app
├── pyautogui_check.py        # Display control check
├── task_translator.py        # Rule-based thought→code fallback
├── prompts/                  # System prompt templates
│   ├── main_agent_system.txt
│   ├── main_agent_first_step_extra.txt
│   └── ...
├── scripts/
│   ├── diagnose_pyautogui.py # Diagnostic script for permissions
│   └── analyze_audit_log.py  # Export audit log to rules
├── data/                     # (gitignored) DuckDB, screenshots
└── .env                      # (gitignored) API keys
```

## How It Works

1. **Screenshot** → Capture current screen state
2. **MiniMax API** → Send screenshot + goal, get thought + code + status
3. **Execute** → Run pyautogui code via `exec()`
4. **Verify** → Ask MiniMax "did the step achieve what was intended?"
5. **Repeat** → Until SUCCESS, LOST, or step limit

The agent uses Spotlight (Cmd+Space) to open apps reliably, and prefers keyboard input over mouse clicks for determinism.

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make changes
4. Test with `uv run streamlit run app.py`
5. Submit a PR

## License

MIT
