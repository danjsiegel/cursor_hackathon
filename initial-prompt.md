Act as a Senior Data Engineer. We are building "The Universal Tasker" for the D.C. AI Hackathon. 

THE STACK:
- UI: Streamlit (Focus on a live dashboard view)
- Reasoning/Vision: MiniMax M2.1 API
- Execution: Python 'exec()' for local tasks (Terminal via subprocess, UI via pyautogui)
- Memory: DuckDB (Persistent audit log of steps, actions, and self-evaluations)

HACKATHON CHALLENGE CORE (The 10-Step Autonomous Loop):
1. INITIALIZATION: Take a user goal and create a high-level 10-step plan. Store this in DuckDB.
2. OBSERVATION: At the start of every step, capture a full-screen screenshot using pyautogui.
3. REASONING (The Feedback Loop): Send the screenshot + Goal + DuckDB History (all previous actions/results) to MiniMax.
4. ACTION SELECTION: MiniMax must return:
   - 'thought': Why it's taking this action.
   - 'code': A valid Python snippet to execute.
   - 'status': 'CONTINUE', 'SUCCESS', or 'LOST'.
5. EXECUTION & LOGGING: Execute the code, capture a NEW screenshot for verification, and log the outcome (Pass/Fail) into DuckDB.
6. COMPLETION: If 'SUCCESS' or 10 steps reached, generate a "Post-Mortem" summary in DuckDB that refines the original goal into a "Perfect Prompt" for future use.

UI REQUIREMENTS:
- Center: Live feed of the latest screenshot with the 'thought' overlaid.
- Left Sidebar: The 10-step checklist (green for done, pulsing for active).
- Right Sidebar: The DuckDB Audit Log showing real-time SQL queries of agent progress.

Let's start by scaffolding the 'app.py' with the DuckDB schema and the pyautogui screenshot utility.
