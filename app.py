"""
The Universal Tasker - D.C. AI Hackathon
A 10-step autonomous loop with MiniMax reasoning, DuckDB memory, and Streamlit UI.
"""

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Union

from dotenv import load_dotenv

load_dotenv()

import duckdb
import pyautogui
import streamlit as st
from PIL import Image

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "universal_tasker.duckdb"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"

# MiniMax: use stub when no API key (copy .env.example to .env and set MINIMAX_API_KEY for real API)
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
USE_MINIMAX_STUB = os.getenv("USE_MINIMAX_STUB", "true").lower() in ("true", "1", "yes") or not MINIMAX_API_KEY

# -----------------------------------------------------------------------------
# DuckDB Schema and Initialization
# -----------------------------------------------------------------------------
def get_db_path() -> Path:
    """Ensure data directory exists and return DB path."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DB_PATH

def get_connection() -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection."""
    return duckdb.connect(str(get_db_path()))

def init_db():
    """Initialize DuckDB schema with all required tables."""
    con = get_connection()
    
    # Sessions table (max_steps = retry cap; process ends on SUCCESS, LOST, or step >= max_steps)
    con.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id UUID PRIMARY KEY,
            goal VARCHAR,
            status VARCHAR DEFAULT 'running',
            max_steps INTEGER DEFAULT 10,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Backfill max_steps for existing tables
    try:
        con.execute("ALTER TABLE sessions ADD COLUMN max_steps INTEGER DEFAULT 10")
    except Exception:
        pass
    
    # Plan steps table
    con.execute("""
        CREATE TABLE IF NOT EXISTS plan_steps (
            session_id UUID,
            step_number INTEGER,
            description VARCHAR,
            completed_at TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    
    # Audit log table with action/feedback for refinement
    con.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            session_id UUID,
            step_number INTEGER,
            thought VARCHAR,
            code VARCHAR,
            action VARCHAR,
            feedback VARCHAR,
            status VARCHAR,
            outcome VARCHAR,
            screenshot_before_path VARCHAR,
            screenshot_after_path VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    
    # Post-mortems table
    con.execute("""
        CREATE TABLE IF NOT EXISTS post_mortems (
            session_id UUID,
            original_goal VARCHAR,
            perfect_prompt VARCHAR,
            summary VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    
    con.close()
    return True

# -----------------------------------------------------------------------------
# Screenshot Utility with Error Handling
# -----------------------------------------------------------------------------
def capture_screenshot(save_path: Optional[str] = None) -> Tuple[Optional[Image.Image], str]:
    """
    Capture a screenshot using pyautogui.
    
    Returns:
        tuple: (PIL.Image or None, file_path or "screenshot_failed")
    """
    try:
        screenshot = pyautogui.screenshot()
        
        if save_path is None:
            # Generate a temp path
            save_path = f"/tmp/screenshot_{uuid.uuid4().hex[:8]}.png"
        
        # Ensure parent directory exists
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        
        screenshot.save(save_path)
        return screenshot, save_path
    
    except Exception as e:
        st.error(f"Screenshot failed: {e}")
        return None, "screenshot_failed"

# -----------------------------------------------------------------------------
# MiniMax API (stub when USE_MINIMAX_STUB or no MINIMAX_API_KEY; real API when key set)
# -----------------------------------------------------------------------------
def analyze_screenshot(screenshot_path: str, goal: str, history: list) -> dict:
    """
    Analyze screenshot and determine next action.
    
    Uses stub when USE_MINIMAX_STUB=true or MINIMAX_API_KEY is unset.
    Set MINIMAX_API_KEY in .env and USE_MINIMAX_STUB=false for real MiniMax API.
    
    Returns:
        dict with keys: thought, code, status
    """
    if not USE_MINIMAX_STUB and MINIMAX_API_KEY:
        # TODO: call MiniMax API with base64-encoded image, goal, history
        pass
    # Stub: Open Calculator and type "Hello World"
    
    step_num = len(history) + 1
    
    if step_num == 1:
        return {
            "thought": "Demo stub: Opening Calculator via Run dialog",
            "code": "import pyautogui; pyautogui.hotkey('win', 'r'); pyautogui.write('calc'); pyautogui.press('enter')",
            "status": "CONTINUE"
        }
    elif step_num == 2:
        return {
            "thought": "Demo stub: Typing 'Hello World' in Calculator",
            "code": "import pyautogui; pyautogui.write('Hello World')",
            "status": "SUCCESS"
        }
    else:
        return {
            "thought": "Goal achieved",
            "code": "pass",
            "status": "SUCCESS"
        }

# -----------------------------------------------------------------------------
# Self-Improvement: Refinement Query
# -----------------------------------------------------------------------------
def generate_refined_prompt(con: duckdb.DuckDBPyConnection, session_id: str) -> str:
    """
    Generate an optimized prompt from lessons learned.
    
    Queries audit_log for failed steps and builds improvement notes.
    """
    # Get the goal
    goal_row = con.execute(
        "SELECT goal FROM sessions WHERE id = ?", [session_id]
    ).fetchone()
    goal = goal_row[0] if goal_row else "Unknown"
    
    # Query failed/errored steps
    audit_data = con.execute("""
        SELECT action, feedback 
        FROM audit_log 
        WHERE session_id = ? AND (feedback LIKE '%Error%' OR outcome = 'Fail')
    """, [session_id]).fetchall()
    
    if not audit_data:
        improvement_notes = "No errors encountered."
    else:
        improvement_notes = "\n".join([
            f"- Avoided: {row[0]} because {row[1]}" for row in audit_data
        ])
    
    refined_prompt = f"""OPTIMIZED PROMPT FOR '{goal}':
Always do X. {improvement_notes}

Original Goal: {goal}"""
    
    return refined_prompt

# -----------------------------------------------------------------------------
# Streamlit UI
# -----------------------------------------------------------------------------
def main():
    st.set_page_config(layout="wide", page_title="The Universal Tasker")
    
    # Initialize session state
    if 'session_id' not in st.session_state:
        st.session_state.session_id = None
    if 'step_number' not in st.session_state:
        st.session_state.step_number = 0
    if 'max_steps' not in st.session_state:
        st.session_state.max_steps = 10
    if 'history' not in st.session_state:
        st.session_state.history = []
    if 'current_thought' not in st.session_state:
        st.session_state.current_thought = ""
    if 'latest_screenshot' not in st.session_state:
        st.session_state.latest_screenshot = None
    if 'is_running' not in st.session_state:
        st.session_state.is_running = False
    
    # Left Sidebar: Attempt N / max M (eval cycle; no fixed 10-step)
    with st.sidebar:
        st.title("Session Progress")
        max_s = st.session_state.get("max_steps", 10)
        step = st.session_state.get("step_number", 0)
        st.metric("Attempt", f"{step} / {max_s}")
        if st.session_state.get("is_running") and st.session_state.get("session_id") and step > 0 and step <= max_s:
            st.markdown("""
            <style>
            @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
            .pulsing { animation: pulse 1s infinite; color: #FF4B4B; }
            </style>
            <span class="pulsing">● Running...</span>
            """, unsafe_allow_html=True)
        st.divider()
        st.markdown("### Session Info")
        if st.session_state.get("session_id"):
            st.text(f"Session: {str(st.session_state.session_id)[:8]}...")
    
    # Main Area: Live Screenshot + Thought
    st.title("The Universal Tasker")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("Live Observation")
        
        if st.session_state.latest_screenshot and os.path.exists(st.session_state.latest_screenshot):
            st.image(st.session_state.latest_screenshot, caption="Latest Screenshot", use_column_width=True)
        else:
            st.info("No screenshot captured yet. Enter a goal and click Start.")
        
        if st.session_state.current_thought:
            st.markdown(f"""
            ### Current Thought
            > {st.session_state.current_thought}
            """)
    
    with col2:
        st.subheader("Goal")
        goal_input = st.text_area("Enter your goal:", placeholder="Open Calculator and type 'Hello World'", height=100)
        max_steps_input = st.number_input("Max attempts (retry cap)", min_value=1, max_value=100, value=10, help="Stop after this many steps or when agent returns SUCCESS/LOST.")
        
        start_btn = st.button("Start Task", type="primary", disabled=st.session_state.get("is_running"))
        
        if start_btn and goal_input:
            # Initialize DB
            init_db()
            
            # Create new session
            session_id = str(uuid.uuid4())
            st.session_state.session_id = session_id
            st.session_state.step_number = 1
            st.session_state.max_steps = max_steps_input
            st.session_state.history = []
            st.session_state.current_thought = "Session started..."
            st.session_state.is_running = True
            
            con = get_connection()
            con.execute(
                "INSERT INTO sessions (id, goal, status, max_steps) VALUES (?, ?, ?, ?)",
                [session_id, goal_input, "running", max_steps_input]
            )
            con.close()
            
            st.rerun()
        
        # MiniMax API status
        st.markdown("### MiniMax Status")
        st.success("API: Ready (Stub)")
    
    # Right Sidebar: DuckDB Audit Log
    with st.sidebar:
        st.markdown("---")
        st.markdown("### DuckDB Audit Log")
        
        if st.session_state.get("session_id"):
            con = get_connection()
            logs = con.execute("""
                SELECT step_number, thought, status, outcome, created_at
                FROM audit_log
                WHERE session_id = ?
                ORDER BY step_number
            """, [st.session_state.session_id]).fetchall()
            con.close()
            
            if logs:
                for log in logs:
                    step, thought, status, outcome, created = log
                    status_icon = "✅" if outcome == "Pass" else "❌" if outcome == "Fail" else "⏳"
                    st.markdown(f"**Step {step}** {status_icon}")
                    st.text(thought[:100] + "..." if len(thought) > 100 else thought)
                    st.divider()
            else:
                st.text("No logs yet.")
        else:
            st.text("Start a session to see logs.")
    
    # Loop: run until SUCCESS, LOST, or step_number >= max_steps (eval / decide in agent)
    max_steps = st.session_state.get("max_steps", 10)
    if st.session_state.get("is_running") and st.session_state.get("session_id") and st.session_state.step_number <= max_steps:
        # Capture before screenshot
        screenshot_path = f"{SCREENSHOTS_DIR}/{st.session_state.session_id}/step_{st.session_state.step_number}_before.png"
        screenshot, _ = capture_screenshot(screenshot_path)
        
        if screenshot:
            # Get goal
            con = get_connection()
            goal_row = con.execute(
                "SELECT goal FROM sessions WHERE id = ?", [st.session_state.session_id]
            ).fetchone()
            goal = goal_row[0] if goal_row else ""
            
            # Call MiniMax (stub)
            result = analyze_screenshot(
                screenshot_path, goal, st.session_state.history
            )
            
            thought = result["thought"]
            code = result["code"]
            status = result["status"]
            
            # Execute the action (pyautogui)
            try:
                exec(code)
                outcome = "Pass"
                feedback = None
            except Exception as e:
                outcome = "Fail"
                feedback = str(e)
            
            # Capture after screenshot
            after_path = f"{SCREENSHOTS_DIR}/{st.session_state.session_id}/step_{st.session_state.step_number}_after.png"
            _, after_screenshot_path = capture_screenshot(after_path)
            
            # Log to DuckDB
            con.execute("""
                INSERT INTO audit_log 
                (session_id, step_number, thought, code, action, feedback, status, outcome, 
                 screenshot_before_path, screenshot_after_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                st.session_state.session_id,
                st.session_state.step_number,
                thought,
                code,
                "Demo action",  # action summary
                feedback,
                status,
                outcome,
                screenshot_path,
                after_screenshot_path
            ])
            con.close()
            
            # Update state
            st.session_state.history.append({
                "step_number": st.session_state.step_number,
                "thought": thought,
                "code": code,
                "status": status,
                "outcome": outcome
            })
            st.session_state.current_thought = thought
            st.session_state.latest_screenshot = after_screenshot_path
            
            if status == "SUCCESS":
                st.session_state.step_number = max_steps + 1  # signal done
                st.session_state.is_running = False
                con = get_connection()
                con.execute("UPDATE sessions SET status = ? WHERE id = ?", ["success", st.session_state.session_id])
                con.close()
                st.success("Task completed successfully!")
            elif status == "LOST":
                st.session_state.step_number = max_steps + 1  # signal done (stuck)
                st.session_state.is_running = False
                con = get_connection()
                con.execute("UPDATE sessions SET status = ? WHERE id = ?", ["stuck", st.session_state.session_id])
                con.close()
                st.warning("Agent reported stuck (LOST). Stopping.")
            else:
                st.session_state.step_number += 1
                if st.session_state.step_number > max_steps:
                    st.session_state.is_running = False
                    con = get_connection()
                    con.execute("UPDATE sessions SET status = ? WHERE id = ?", ["lost", st.session_state.session_id])
                    con.close()
                    st.warning(f"Max attempts ({max_steps}) reached. Stopping.")
            
            st.rerun()
    
    # Completion: Self-Improvement (when SUCCESS, LOST/stuck, or max_steps reached)
    max_s = st.session_state.get("max_steps", 10)
    done = st.session_state.get("is_running") and st.session_state.get("session_id") and (
        st.session_state.step_number > max_s or st.session_state.step_number == max_s + 1
    )
    if done:
        st.markdown("---")
        st.subheader("Task Completed - Self-Improvement")
        
        if st.session_state.get("session_id"):
            con = get_connection()
            refined = generate_refined_prompt(con, st.session_state.session_id)
            
            st.markdown("### Optimized Prompt for Next Time")
            st.code(refined, language="markdown")
            
            # Save to post_mortems
            goal_row = con.execute(
                "SELECT goal FROM sessions WHERE id = ?", [st.session_state.session_id]
            ).fetchone()
            original_goal = goal_row[0] if goal_row else ""
            
            con.execute("""
                INSERT INTO post_mortems (session_id, original_goal, perfect_prompt, summary)
                VALUES (?, ?, ?, ?)
            """, [st.session_state.session_id, original_goal, refined, "Demo completion"])
            con.close()
            
            if st.button("Start New Session"):
                st.session_state.clear()
                st.rerun()

if __name__ == "__main__":
    main()
