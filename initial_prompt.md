Universal Tasker – App Scaffold Plan

Scaffold the entrypoint and persistence layer so the 10-step autonomous loop and Streamlit dashboard can be built on top. This phase delivers: DuckDB schema + init, pyautogui screenshot utility, UV for deps, self-improvement refinement query (and schema support for it), minimal Streamlit shell, and a Cursor prompt doc for the user to paste next time.



0. MiniMax API Contract (Critical for Loop)

Define the interface early so the loop can drive even without a live API key. Create minimax_client.py with:

def analyze_screenshot(screenshot_path: str, goal: str, history: list[dict]) -> dict:
    """
    Sends screenshot + context to MiniMax, returns:
    {
        "thought": "Why I'm taking this action",
        "code": "pyautogui.write('hello')",
        "status": "CONTINUE|SUCCESS|LOST"
    }
    """
    # TODO: Implement actual API call with base64-encoded image
    # Stub for demo purposes:
    return {
        "thought": "Demo stub: opening Calculator",
        "code": "import pyautogui; pyautogui.hotkey('win', 'r'); pyautogui.write('calc'); pyautogui.press('enter')",
        "status": "CONTINUE"
    }





Image encoding: Use base64 for the API payload (MiniMax likely accepts it).



History format: List of dicts with step_number, thought, code, status.



MVP priority: Wire this stub to the loop first; replace with real API later.



1. DuckDB schema design

Use a single DuckDB file (e.g. data/universal_tasker.duckdb) with tables aligned to the hackathon flow:







Table



Purpose





sessions



One row per run: id, goal (user input), status (running/success/lost), created_at.





plan_steps



The 10-step plan: session_id, step_number (1–10), description, completed_at (nullable).





audit_log



Per-step audit: session_id, step_number, thought, code, action (short summary for refinement), feedback (error/retry text), status (CONTINUE/SUCCESS/LOST), outcome (Pass/Fail), screenshot_before_path, screenshot_after_path, created_at.





post_mortems



Final summary: session_id, original_goal, perfect_prompt, summary, created_at.





Screenshots: Store file paths (not BLOBs) so Streamlit can show the latest image and the audit log can reference them. The screenshot utility will write PNGs to a dedicated directory (e.g. data/screenshots/<session_id>/).



Initialization: One function that creates the DB file (if missing), ensures data/ and the screenshots dir exist, and runs CREATE TABLE IF NOT EXISTS for all four tables.



Self-improvement: audit_log.action and audit_log.feedback support the refinement query: steps where the agent retried or hit errors are queried by feedback LIKE '%Error%' (or outcome = 'Fail'); goal is resolved via sessions joined on session_id.



2. Pyautogui screenshot utility





Function: capture_screenshot(save_path: str | None = None) -> tuple[PIL.Image.Image, str].





Use pyautogui.screenshot() (returns PIL Image).



If save_path is provided, save the image as PNG there and return (image, save_path); otherwise write to a temp file and return (image, path) so the caller can always log a path.



Error handling: Wrap pyautogui.screenshot() in try/except. On failure (headless server, no display), return (None, "screenshot_failed") so the loop logs the error and continues (or pauses for human review).



Convention: Caller passes a path like data/screenshots/{session_id}/step_{n}_before.png (or _after.png) so the audit log and UI can load by path.



Dependency: pyautogui and Pillow (pyautogui may already use it; add via UV).



3. UV (dependency management)





Use UV for the project: uv init (creates pyproject.toml), then uv add streamlit duckdb pyautogui Pillow.



Run the app with uv run streamlit run app.py. Optionally keep a minimal requirements.txt exported via uv pip compile for judges who prefer pip, but primary workflow is UV.



pyproject.toml: script entrypoint optional; dependencies live there. Python version constraint (e.g. >=3.10) in project.requires-python.



4. Self-improvement (refinement query)





When the agent hits SUCCESS (or 10 steps), run a refinement step that builds an "OPTIMIZED PROMPT" from lessons learned.



Function generate_refined_prompt(con, session_id) (or goal if you pass goal + con):





Join audit_log with sessions on session_id to get goal.



Query rows where feedback LIKE '%Error%' or outcome = 'Fail' (and optionally action is not null).



Build: improvement_notes = "\n".join([f"Avoided: {row['action']} because {row['feedback']}" for row in audit_data]).



Return (and optionally write to post_mortems): refined_prompt = f"OPTIMIZED PROMPT FOR '{goal}':\nAlways do X. {improvement_notes}".



Implement this in app.py (or a small refinement.py) and call it from the completion path; store the result in post_mortems.perfect_prompt or a dedicated column so the user can copy it for "next time."



Completion conditions: Add a "PAUSED" status for manual review. If the agent gets stuck or the user wants to intervene, set status = 'PAUSED' in sessions and surface a "Resume / Abort" button in the UI.



4.1 10-Step Plan Generation





The loop assumes a 10-step plan exists but doesn't specify how it's created.



For MVP: Seed plan_steps with a hardcoded template or a simple rule-based splitter (split goal by commas/semicolons into 10 chunks).



For full implementation: Call MiniMax once at initialization to generate the 10-step plan from the goal and insert into plan_steps.



4.2 Security Note: exec()





Using exec() to run MiniMax-returned code is risky (sandbox escape, data exfiltration).



Document this risk in comments and in the CURSOR_PROMPT.md.



For the hackathon: Accept the risk but add a warning log before execution. In production, use a sandbox (e.g., Docker,  RestrictedPython).



5. File layout and app.py structure





**app.py**: Single entrypoint (Streamlit app + schema + screenshot in one file for hackathon speed, or split into db.py and screenshot.py if you prefer; the plan assumes a single file with clear sections).





Imports: streamlit, duckdb, pyautogui, PIL, os, etc.



DB section: get_db_path(), init_db() (create tables), get_connection() (duckdb.connect).



Screenshot section: capture_screenshot(save_path=None) as above.



Streamlit shell: st.set_page_config(layout="wide"), left sidebar placeholder (e.g. “10-step checklist”), main area placeholder (e.g. “Live screenshot + thought”), right sidebar placeholder (e.g. “DuckDB audit log”), and a minimal “Goal” input + “Start” button that for now only calls init_db() and maybe captures one screenshot to verify the utility.



UV: pyproject.toml with streamlit, duckdb, pyautogui, Pillow (and later MiniMax SDK when you add the API). Run with uv run streamlit run app.py.



Cursor prompt for next time: Add a doc (e.g. CURSOR_PROMPT.md) in the repo containing the full "Universal Tasker" system prompt you pasted (Goal, Plan, Tool, Memory, 10-step loop, UI requirements, and the self-improvement SQL logic snippet). The user can copy-paste it into Cursor Composer (Cmd+I) or a new Chat to continue the build.



6. Implementation order

6. Implementation Order and Priorities

For a 5-hour hackathon window (deadline 3:00 PM), prioritize ruthlessly:







Step



Task



Time Box



Priority





1



UV init + deps: uv init, uv add streamlit duckdb pyautogui Pillow



5 min



P0









2



DuckDB schema: init_db() with all four tables



10 min





3



Screenshot utility: capture_screenshot() with error handling



10 min



P0





4



MiniMax stub: minimax_client.py with analyze_screenshot()



10 min



P0





5



Streamlit shell: Layout (left/center/right), Goal input, Start button



15 min



P0





6



Demo loop: Wire Start button to run ONE full loop (screenshot -> reasoning -> action -> verify)



15 min



P0





7



Self-improvement: generate_refined_prompt()



10 min



P1 (if time permits)





8



CURSOR_PROMPT.md: Add the system prompt doc



5 min



P1 (if time permits)





9



Plan generation: Seed plan_steps or call MiniMax at init



10 min



P2 (nice-to-have)





10



PAUSED status: Human review fallback



10 min



P2 (nice-to-have)

Strategy: Steps 1-6 deliver an end-to-end demo. Skip P1/P2 items if time runs short.



6.1 Demo-ability Over Completeness

Judges want to see the loop run, even if the goal is trivial.





Demo goal: "Open Calculator and type 'Hello World'" (hardcoded or user input).



Demo flow:





User enters goal, clicks Start.



System captures screenshot (before).



MiniMax stub returns action (open Calculator).



System executes pyautogui.hotkey('win', 'r'); pyautogui.write('calc'); pyautogui.press('enter').



System captures screenshot (after).



System logs outcome to DuckDB.



UI shows: latest screenshot, thought overlay, audit log row.



UI polish: Implement the 10-step checklist (green for done, pulsing for active) before the audit log—it gives the audience immediate progress visibility.



6.2 Error States as Features

Showing how the system handles failure proves the self-improvement loop works.





Log "failed" outcomes prominently in audit_log.outcome = 'Fail'.



The refinement query uses these failures to build the "OPTIMIZED PROMPT".



Consider a demo where the agent fails once, retries, succeeds, and the post-mortem reflects the lesson learned.                                                                                       |                                                                           |          |          |
| 3. Implement screenshot utility: capture_screenshot(save_path=None), returning (PIL.Image, path) and ensuring the parent directory exists.                                                                                                                    |                                                                           |          |          |
| 4. Implement self-improvement: generate_refined_prompt(con, session_id) that queries audit_log (join sessions for goal) where feedback LIKE '%Error%' or outcome = 'Fail', builds the refined prompt string, and optionally writes to post_mortems.       |                                                                           |          |          |
| 5. Add Streamlit shell in app.py: layout (left / center / right), placeholders, goal input, “Start” button that runs init_db() and one test screenshot into data/screenshots/ (or a temp session_id) and displays it in the center to confirm the pipeline. |                                                                           |          |          |
| 6. Add CURSOR_PROMPT.md: paste the full Universal Tasker system prompt (stack, 10-step loop, UI requirements) plus the self-improvement SQL logic snippet so the user can reuse it in Cursor next time.                                                           |                                                                           |          |          |



7. Resulting Data Flow (for later phases)

flowchart LR
  subgraph init [Initialization]
    Goal[User Goal] --> Plan[10-Step Plan]
    Plan --> DuckDB1[(sessions, plan_steps)]
  end
  subgraph loop [Per-Step Loop]
    DuckDB1 --> Observe[pyautogui screenshot]
    Observe --> Reason[MiniMax + history]
    Reason --> Act[thought, code, status]
    Act --> Exec[exec code + log]
    Exec --> DuckDB2[(audit_log)]
  end
  subgraph completion [Completion]
    DuckDB2 --> PostMortem[Post-Mortem]
    PostMortem --> DuckDB3[(post_mortems)]
  end

After this scaffold, you will have: UV-managed deps and uv run streamlit run app.py; DuckDB schema (sessions, plan_steps, audit_log with action/feedback, post_mortems); a screenshot utility with error handling; a MiniMax API contract stub; a self-improvement refinement function; a minimal dashboard shell (checklist, live feed, audit log); CURSOR_PROMPT.md for continuity; and a time-boxed implementation order that prioritizes an end-to-end demo over polish.