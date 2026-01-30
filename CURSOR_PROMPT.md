# Universal Tasker - Cursor System Prompt

Copy and paste this into Cursor's Composer (Cmd+I) or a fresh Chat to continue building.

---

## The Universal Tasker - D.C. AI Hackathon

**Stack:**
- UI: Streamlit (Live dashboard with left/center/right columns)
- Reasoning/Vision: MiniMax M2.1 API (stubbed in `minimax_client.py`)
- Execution: Python `exec()` for local tasks (pyautogui for UI automation)
- Memory: DuckDB (Persistent audit log of steps, actions, and self-evaluations)

**Hackathon Challenge Core (The 10-Step Autonomous Loop):**

1. **INITIALIZATION**: Take a user goal and create a 10-step plan. Store in DuckDB `sessions` + `plan_steps`.
2. **OBSERVATION**: At each step, capture a full-screen screenshot using `capture_screenshot()`.
3. **REASONING**: Send screenshot + Goal + DuckDB History to MiniMax API.
4. **ACTION SELECTION**: MiniMax returns:
   - `thought`: Why it's taking this action
   - `code`: Valid Python snippet to execute
   - `status`: 'CONTINUE', 'SUCCESS', or 'LOST'
5. **EXECUTION & LOGGING**: Execute code via `exec()`, capture verification screenshot, log to DuckDB `audit_log`.
6. **COMPLETION**: If SUCCESS or 10 steps reached, run `generate_refined_prompt()` to create a "Perfect Prompt" in `post_mortems`.

**UI Requirements:**
- **Left Sidebar**: 10-step checklist (green for done, pulsing for active)
- **Center**: Live screenshot feed with 'thought' overlaid
- **Right Sidebar**: DuckDB Audit Log (real-time SQL queries)

**Self-Improvement Logic:**
```python
def generate_refined_prompt(con, session_id):
    # Query DuckDB for steps where the agent had to 'RETRY' or hit errors
    audit_data = con.execute("""
        SELECT action, feedback 
        FROM audit_log 
        WHERE session_id = ? AND (feedback LIKE '%Error%' OR outcome = 'Fail')
    """, [session_id]).fetchall()
    
    improvement_notes = "\n".join([
        f"Avoided: {row[0]} because {row[1]}" for row in audit_data
    ])
    
    refined_prompt = f"OPTIMIZED PROMPT FOR '{goal}':\nAlways do X. {improvement_notes}"
    return refined_prompt
```

**Files:**
- `app.py`: Main entrypoint with DB schema, screenshot utility, Streamlit UI, demo loop
- `data/universal_tasker.duckdb`: DuckDB persistence
- `data/screenshots/`: Screenshot storage

**Run:**
```bash
uv run streamlit run app.py
```

**Current Status:**
- P0 complete: UV init, DuckDB schema, screenshot utility, MiniMax stub, Streamlit shell, demo loop
- P1 pending: Full MiniMax API integration, PAUSED status for human review
- P2 pending: Dynamic 10-step plan generation

**Hackathon Deadline Context:**
- Time-boxed to 5 hours
- Priority: Demo-ability over completeness
- Show error states as features (failed steps feed into refinement)
