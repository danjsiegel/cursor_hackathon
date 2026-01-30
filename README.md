# Universal Tasker

**Autonomous UI automation powered by vision + language models.**

Give it a goal in plain English. It sees your screen, reasons about what to do, executes actions, and verifies each step—all without writing scripts or recording macros.

## The Vision

Traditional automation requires:
- Writing scripts for each task
- Maintaining brittle selectors that break when UIs change
- Different tools for different platforms

**Universal Tasker** is different:
- **Natural language goals**: "Open Calculator and add 3+3" or "Fill out the patient billing form"
- **Vision-based reasoning**: Sees the screen like a human would
- **Self-verifying**: Checks if each step actually worked
- **Platform agnostic**: Works with any UI—thick clients, legacy apps, web apps, desktop software

### Use Cases

| Domain | Example |
|--------|---------|
| **Healthcare** | Automate billing workflows in legacy EMR systems |
| **Finance** | Process invoices across multiple vendor portals |
| **IT Support** | Guided troubleshooting with automatic verification |
| **Data Entry** | Transfer data between systems that don't integrate |
| **Testing** | Exploratory UI testing with natural language test cases |
| **Accessibility** | Voice-controlled computer operation for users with disabilities |

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  1. Screenshot  │────▶│  2. AI Reasons  │────▶│  3. Execute     │
│  Capture screen │     │  "I see X, I'll │     │  pyautogui runs │
│  state          │     │   do Y"         │     │  the action     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
┌─────────────────┐     ┌─────────────────┐             │
│  5. Repeat or   │◀────│  4. Verify      │◀────────────┘
│  Complete       │     │  "Did it work?" │
└─────────────────┘     └─────────────────┘
```

1. **Screenshot** → Capture current screen state
2. **Reason** → MiniMax vision model analyzes screenshot + goal
3. **Execute** → Run pyautogui code to perform the action
4. **Verify** → AI checks if the step achieved its intent
5. **Repeat** → Continue until goal is achieved or stuck

## Quick Start

```bash
git clone <repo>
cd cursor_hackathon

# Install dependencies
uv sync

# Configure API (get key from https://platform.minimax.io)
cp .env.example .env
# Edit .env: MINIMAX_API_KEY=your_key, USE_MINIMAX_STUB=false

# Run
uv run streamlit run app.py
```

Open http://localhost:8501 and try: **"Open Calculator and add 3+3"**

## Features

- **Session-based UI**: Track progress, view history, audit failures
- **Step verification**: AI confirms each action worked before proceeding
- **Graceful failures**: Stops and explains when stuck instead of thrashing
- **Audit log**: Every step recorded in DuckDB for debugging and learning
- **Dynamic planning**: Agent estimates steps needed, adjusts as it goes
- **Self-improvement**: Post-mortem analysis generates better prompts

## macOS Setup

pyautogui requires permissions to control the computer:

1. **System Settings → Privacy & Security → Accessibility**
   - Add Terminal (or Cursor) → Toggle ON

2. **System Settings → Privacy & Security → Input Monitoring**
   - Add Terminal (or Cursor) → Toggle ON

3. **Restart Terminal/Cursor** after granting permissions

Run the diagnostic to verify: `uv run python scripts/diagnose_pyautogui.py`

## Architecture

```
cursor_hackathon/
├── app.py                      # Streamlit UI + orchestration
├── pyautogui_check.py          # Permission diagnostics
├── task_translator.py          # Rule-based code generation fallback
├── prompts/                    # LLM prompt templates
│   ├── main_agent_system.txt   # Core agent instructions
│   ├── verify_step_*.txt       # Step verification prompts
│   └── validate_goal_*.txt     # Goal completion prompts
├── scripts/
│   ├── diagnose_pyautogui.py   # Interactive permission tester
│   └── analyze_audit_log.py    # Export audit data for learning
└── data/                       # (gitignored) DuckDB, screenshots
```

## Technical Details

- **Vision Model**: MiniMax M2.1 (multimodal, sees screenshots)
- **Execution**: pyautogui for cross-platform mouse/keyboard control
- **Storage**: DuckDB for sessions, audit logs, post-mortems
- **UI**: Streamlit for rapid prototyping
- **Prompts**: Template-based with dynamic context injection

## Limitations & Future Work

**Current limitations:**
- Focus management on macOS can be tricky (browser captures shortcuts)
- Coordinate-based clicking is fragile across screen sizes
- Single-user, single-machine (no remote execution yet)

**Future directions:**
- **Element detection**: Use vision to identify clickable elements by appearance
- **Multi-monitor support**: Handle complex display setups
- **Workflow learning**: Learn from successful runs to skip AI calls
- **Remote execution**: Control machines over the network
- **Voice input**: Combine with speech-to-text for hands-free operation

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make changes
4. Test with `uv run streamlit run app.py`
5. Submit a PR

## License

MIT

---

*Built at the Cursor Hackathon 2026*
