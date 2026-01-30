# Universal Tasker

**Autonomous UI Agent powered by MiniMax**

Universal Tasker is an AI agent that takes control of your desktop to accomplish complex goals. Just tell it what you want—like "Open Calculator and add 3+3"—and it will:

1. Capture a screenshot of your current screen
2. Send it to MiniMax for reasoning about what action to take
3. Execute pyautogui code to interact with your UI
4. Verify the step succeeded before moving on
5. Log everything to DuckDB for audit and self-improvement

## How It Works

The agent runs in a 10-step loop, each iteration consisting of:
- **Observe** → Screenshot the current screen state
- **Reason** → MiniMax analyzes the screenshot + goal + history
- **Act** → Execute the generated pyautogui code
- **Verify** → Capture an after-screenshot and confirm success

All thoughts, code, screenshots, and outcomes are persisted in DuckDB, creating a complete audit trail for every task.

## Self-Improvement

After each task, Universal Tasker runs a post-mortem analysis—querying the audit log for failed steps and errors to build an "optimized prompt" for next time. The agent learns from its mistakes.

## Get Started

```bash
cd cursor_hackathon
uv sync
uv run streamlit run app.py
```

Then open http://localhost:8501, enter a goal, and watch the agent work.

## Demo

Check out `demo-video.mp4` to see Universal Tasker in action.
