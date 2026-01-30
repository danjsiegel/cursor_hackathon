"""
The Universal Tasker - D.C. AI Hackathon
A 10-step autonomous loop with MiniMax reasoning, DuckDB memory, and Streamlit UI.
"""

import base64
import json
import os
import platform
import re
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Union

import requests
from dotenv import load_dotenv

load_dotenv()

import duckdb
import pyautogui
import streamlit as st
from PIL import Image

from prompts import format_prompt, load as load_prompt
from pyautogui_check import check_pyautogui_control
from task_translator import translate_task_to_code as translate_task_rules

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "universal_tasker.duckdb"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"

# MiniMax: use stub when no API key (copy .env.example to .env and set MINIMAX_API_KEY for real API)
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
MINIMAX_BASE_URL = (os.getenv("MINIMAX_BASE_URL") or "https://api.minimax.io").rstrip("/")
MINIMAX_CHAT_URL = f"{MINIMAX_BASE_URL}/v1/text/chatcompletion_v2"
USE_MINIMAX_STUB = os.getenv("USE_MINIMAX_STUB", "true").lower() in ("true", "1", "yes") or not MINIMAX_API_KEY

# -----------------------------------------------------------------------------
# User environment (OS, browser) for prompts
# -----------------------------------------------------------------------------
def get_user_environment(browser_override: Optional[str] = None) -> str:
    """Build a short description of the user's OS, browser, and display for MiniMax context.
    Includes screen size and cursor position when available so the agent can reason about coordinates."""
    parts = []
    sys_name = platform.system()
    if sys_name == "Darwin":
        mac_ver = platform.mac_ver()
        os_part = f"macOS {mac_ver[0]}" if mac_ver[0] else "macOS"
    else:
        os_part = f"{sys_name} {platform.release()}".strip()
    parts.append(os_part)
    try:
        machine = platform.machine()
        if machine:
            parts.append(machine)
    except Exception:
        pass
    browser = (browser_override or "").strip() or "unknown"
    parts.append(f"Browser: {browser}")
    try:
        size = pyautogui.size()
        if size and len(size) >= 2 and size[0] > 0 and size[1] > 0:
            parts.append(f"Screen: {size[0]}x{size[1]} (width x height in pixels)")
    except Exception:
        pass
    try:
        pos = pyautogui.position()
        if pos is not None and len(pos) >= 2:
            parts.append(f"Cursor: ({pos[0]}, {pos[1]})")
    except Exception:
        pass
    return "; ".join(parts)

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
            step_verification_achieved VARCHAR,
            step_verification_reason VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    try:
        con.execute("ALTER TABLE audit_log ADD COLUMN step_verification_achieved VARCHAR")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE audit_log ADD COLUMN step_verification_reason VARCHAR")
    except Exception:
        pass

    # Post-mortems table
    con.execute("""
        CREATE TABLE IF NOT EXISTS post_mortems (
            session_id UUID,
            original_goal VARCHAR,
            perfect_prompt VARCHAR,
            summary VARCHAR,
            validation_achieved VARCHAR,
            validation_reason VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    try:
        con.execute("ALTER TABLE post_mortems ADD COLUMN validation_achieved VARCHAR")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE post_mortems ADD COLUMN validation_reason VARCHAR")
    except Exception:
        pass

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
def _encode_screenshot_base64(screenshot_path: str) -> Optional[str]:
    """Read image file and return base64 string, or None on error."""
    try:
        with open(screenshot_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return None


def _call_minimax_api(screenshot_path: str, goal: str, history: list, is_first_step: bool = False, user_env: str = "") -> Optional[dict]:
    """
    Call MiniMax chatcompletion_v2 with screenshot (base64), goal, and history.
    Asks for thought, code, status. On first step also asks for total_steps and checkpoints.
    user_env: e.g. "macOS 14.2.1; arm64; Browser: Firefox" for prompt context.
    Returns parsed dict or None on failure.
    """
    b64 = _encode_screenshot_base64(screenshot_path)
    history_text = ""
    if history:
        history_text = "\n".join([
            f"Step {h.get('step_number', i+1)}: thought={h.get('thought', '')[:200]} code={h.get('code', '')[:150]} status={h.get('status', '')} outcome={h.get('outcome', '')}"
            for i, h in enumerate(history)
        ])

    first_step_extra = load_prompt("main_agent_first_step_extra") if is_first_step else ""
    user_context_line = f"\n**User context:** {user_env}\n" if user_env else ""
    example_response = (
        '\nExample response:\n{"thought": "Calculator is open. I will type 42.", "code": "import pyautogui; pyautogui.write(\\"42\\"); pyautogui.press(\\"enter\\")", "status": "SUCCESS"}'
        if not is_first_step
        else ""
    )
    system_prompt = format_prompt(
        load_prompt("main_agent_system"),
        user_context_line=user_context_line,
        first_step_extra=first_step_extra,
        example_response=example_response,
    )

    history_block = f"Steps already taken (for context):\n{history_text}\n\n" if history_text else ""
    json_keys_suffix = " with keys: thought, code, status, total_steps, checkpoints." if is_first_step else " with keys: thought, code, status."
    user_text = format_prompt(
        load_prompt("main_agent_user"),
        goal=goal,
        history_block=history_block,
        json_keys_suffix=json_keys_suffix,
    )

    # MiniMax chatcompletion_v2: messages with role and content.
    # Try multimodal first (content as array with image_url). If API rejects, fall back to text-only.
    content_parts = [{"type": "text", "text": user_text}]
    if b64:
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"}
        })
    user_content = content_parts if len(content_parts) > 1 else user_text

    def do_request(content):
        return requests.post(
            MINIMAX_CHAT_URL,
            headers={
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "MiniMax-M2.1",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ],
                "max_tokens": 1024,
            },
            timeout=60
        )

    try:
        r = do_request(user_content)
        # If 400 and we sent multimodal, retry text-only (some endpoints only accept string content)
        if r.status_code == 400 and user_content != user_text:
            r = do_request(user_text + "\n\n(A screenshot was captured but could not be attached; use the goal and steps above.)")
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        st.warning(f"MiniMax API request failed: {e}")
        if hasattr(e, "response") and getattr(e, "response", None) is not None:
            try:
                st.code(e.response.text[:500] if hasattr(e.response, "text") else str(e.response))
            except Exception:
                pass
        return None

    base_resp = data.get("base_resp") or {}
    if base_resp.get("status_code") != 0:
        st.warning(f"MiniMax API error: {base_resp.get('status_msg', data)}")
        return None

    choices = data.get("choices") or []
    if not choices:
        return None
    raw_content = (choices[0].get("message") or {}).get("content") or ""

    # Parse JSON from response (allow ```json ... ``` or raw {...})
    parsed = None
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw_content)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    if not parsed:
        try:
            parsed = json.loads(raw_content.strip())
        except json.JSONDecodeError:
            # Try to find first {...} in text
            brace = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw_content)
            if brace:
                try:
                    parsed = json.loads(brace.group(0))
                except json.JSONDecodeError:
                    pass

    if not parsed or not isinstance(parsed, dict):
        st.warning("MiniMax response could not be parsed as JSON. Raw: " + (raw_content[:300] or ""))
        return None

    thought = parsed.get("thought") or parsed.get("reasoning") or "No thought."
    code = parsed.get("code") or "pass"
    status = (parsed.get("status") or "CONTINUE").strip().upper()
    if status not in ("CONTINUE", "SUCCESS", "LOST"):
        status = "CONTINUE"

    out = {"thought": thought, "code": code, "status": status, "raw": raw_content}
    if is_first_step:
        try:
            out["total_steps"] = int(parsed.get("total_steps") or 0) or None
        except (TypeError, ValueError):
            out["total_steps"] = None
        raw_cp = parsed.get("checkpoints")
        if isinstance(raw_cp, list):
            out["checkpoints"] = [int(x) for x in raw_cp if isinstance(x, (int, float))]
        else:
            out["checkpoints"] = []
    return out


def validate_goal_achieved(goal: str, screenshot_path: str, user_env: str = "") -> Optional[dict]:
    """
    Send the final screenshot to MiniMax with a validation-only prompt:
    "Was what was asked achieved in this screenshot?" Returns {achieved: bool, reason: str} or None.
    user_env: e.g. "macOS 14.2.1; Browser: Firefox" for context.
    """
    if USE_MINIMAX_STUB or not MINIMAX_API_KEY:
        return None
    b64 = _encode_screenshot_base64(screenshot_path)
    if not b64:
        return None

    user_context_line = f"\n**User context:** {user_env}" if user_env else ""
    user_context_block = f"User context: {user_env}\n\n" if user_env else ""
    system_prompt = format_prompt(
        load_prompt("validate_goal_system"),
        user_context_line=user_context_line,
    )
    user_text = format_prompt(
        load_prompt("validate_goal_user"),
        goal=goal,
        user_context_block=user_context_block,
    )

    content_parts = [{"type": "text", "text": user_text}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]
    payload = {
        "model": "MiniMax-M2.1",
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": content_parts}],
        "max_tokens": 256,
    }
    headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"}

    try:
        r = requests.post(MINIMAX_CHAT_URL, headers=headers, json=payload, timeout=30)
        if r.status_code == 400:
            r = requests.post(
                MINIMAX_CHAT_URL,
                headers=headers,
                json={
                    "model": "MiniMax-M2.1",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text + "\n\n(Screenshot was captured but could not be attached.)"},
                    ],
                    "max_tokens": 256,
                },
                timeout=30,
            )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        st.warning(f"Validation request failed: {e}")
        return None

    if (data.get("base_resp") or {}).get("status_code") != 0:
        return None
    raw = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    parsed = None
    for pattern in [r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"]:
        m = re.search(pattern, raw)
        if m:
            try:
                parsed = json.loads(m.group(1) if "```" in pattern else m.group(0))
                break
            except json.JSONDecodeError:
                pass
    if not parsed:
        try:
            parsed = json.loads(raw.strip())
        except json.JSONDecodeError:
            return None
    achieved = parsed.get("achieved") in (True, "true", "yes", 1)
    reason = str(parsed.get("reason") or "").strip() or "No reason given."
    return {"achieved": bool(achieved), "reason": reason}


def verify_step_achieved(intended_thought: str, screenshot_path: str, user_env: str = "") -> Optional[dict]:
    """
    After each step: ask MiniMax "Did I actually do what I said I would do?"
    Given the intended action (thought) and the after-screenshot, returns {achieved: bool, reason: str} or None.
    """
    if USE_MINIMAX_STUB or not MINIMAX_API_KEY:
        return None
    b64 = _encode_screenshot_base64(screenshot_path)
    if not b64:
        return None

    user_context_line = f"\n**User context:** {user_env}" if user_env else ""
    user_context_block = f"User context: {user_env}\n\n" if user_env else ""
    system_prompt = format_prompt(
        load_prompt("verify_step_system"),
        user_context_line=user_context_line,
    )
    user_text = format_prompt(
        load_prompt("verify_step_user"),
        intended_thought=intended_thought,
        user_context_block=user_context_block,
    )

    content_parts = [{"type": "text", "text": user_text}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]
    payload = {
        "model": "MiniMax-M2.1",
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": content_parts}],
        "max_tokens": 256,
    }
    headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"}

    try:
        r = requests.post(MINIMAX_CHAT_URL, headers=headers, json=payload, timeout=30)
        if r.status_code == 400:
            r = requests.post(
                MINIMAX_CHAT_URL,
                headers=headers,
                json={
                    "model": "MiniMax-M2.1",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text + "\n\n(Screenshot was captured but could not be attached.)"},
                    ],
                    "max_tokens": 256,
                },
                timeout=30,
            )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        st.warning(f"Step verification request failed: {e}")
        return None

    if (data.get("base_resp") or {}).get("status_code") != 0:
        return None
    raw = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    parsed = None
    for pattern in [r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"]:
        m = re.search(pattern, raw)
        if m:
            try:
                parsed = json.loads(m.group(1) if "```" in pattern else m.group(0))
                break
            except json.JSONDecodeError:
                pass
    if not parsed:
        try:
            parsed = json.loads(raw.strip())
        except json.JSONDecodeError:
            return None
    achieved = parsed.get("achieved") in (True, "true", "yes", 1)
    reason = str(parsed.get("reason") or "").strip() or "No reason given."
    return {"achieved": bool(achieved), "reason": reason}


def translate_step_to_code(step_description: str, user_env: str = "") -> Optional[str]:
    """
    Translate a natural-language step description into pyautogui Python code.
    Returns a single line (or block) of code, or None on failure.
    """
    if USE_MINIMAX_STUB or not MINIMAX_API_KEY:
        return None
    step_description = (step_description or "").strip()
    if not step_description:
        return None

    user_context_line = f"\n**User context:** {user_env}" if user_env else ""
    system_prompt = format_prompt(
        load_prompt("translate_step_system"),
        user_context_line=user_context_line,
    )
    user_text = format_prompt(
        load_prompt("translate_step_user"),
        step_description=step_description,
    )

    payload = {
        "model": "MiniMax-M2.1",
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}],
        "max_tokens": 256,
    }
    headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"}

    try:
        r = requests.post(MINIMAX_CHAT_URL, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        st.warning(f"Step-to-code request failed: {e}")
        return None

    if (data.get("base_resp") or {}).get("status_code") != 0:
        return None
    raw = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    raw = raw.strip()
    # Strip markdown code fence if present
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
    return raw.strip() or None


def analyze_screenshot(screenshot_path: str, goal: str, history: list, user_env: str = "") -> dict:
    """
    Analyze screenshot and determine next action.
    
    Uses stub when USE_MINIMAX_STUB=true or MINIMAX_API_KEY is unset.
    Set MINIMAX_API_KEY in .env and USE_MINIMAX_STUB=false for real MiniMax API.
    user_env: e.g. "macOS 14.2.1; Browser: Firefox" for prompt context.
    
    Returns:
        dict with keys: thought, code, status
    """
    if not USE_MINIMAX_STUB and MINIMAX_API_KEY:
        is_first = len(history) == 0
        result = _call_minimax_api(screenshot_path, goal, history, is_first_step=is_first, user_env=user_env)
        if result is not None:
            thought = result.get("thought", "")
            code = result.get("code", "")
            status = result.get("status", "")
            print("[MiniMax next step] thought:", thought[:200] if thought else "(none)")
            print("[MiniMax next step] code:", code[:300] if code else "(none)")
            print("[MiniMax next step] status:", status)
            ret = {"thought": thought, "code": code, "status": status}
            if is_first:
                if result.get("total_steps") is not None:
                    ret["total_steps"] = result["total_steps"]
                if result.get("checkpoints") is not None:
                    ret["checkpoints"] = result["checkpoints"]
            return ret
        # Fall through to stub on API failure

    # Stub: Open Calculator and type "Hello World"
    step_num = len(history) + 1
    if step_num == 1:
        return {
            "thought": "Demo stub: Opening Calculator via Run dialog",
            "code": "import pyautogui; pyautogui.hotkey('win', 'r'); pyautogui.write('calc'); pyautogui.press('enter')",
            "status": "CONTINUE",
            "total_steps": 3,
            "checkpoints": [2],
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
    if 'planned_total_steps' not in st.session_state:
        st.session_state.planned_total_steps = None  # from MiniMax first step
    if 'checkpoints' not in st.session_state:
        st.session_state.checkpoints = []  # step numbers to take validation screenshot
    if 'user_browser' not in st.session_state:
        st.session_state.user_browser = ""  # optional: "Firefox", "Chrome", etc. for prompt context
    if 'session_log' not in st.session_state:
        st.session_state.session_log = []  # chat-like activity: [{ "message", "step", "ts" }]
    if 'view_session_id' not in st.session_state:
        st.session_state.view_session_id = None  # when set, main area shows that session's full log
    # Run pyautogui display-control check once per run and store result (used in sidebar + elsewhere)
    if 'pyautogui_control_ok' not in st.session_state:
        _ok, _msg = check_pyautogui_control()
        st.session_state.pyautogui_control_ok = _ok
        st.session_state.pyautogui_control_message = _msg or ""

    # Left Sidebar: Attempt N / max M (eval cycle; no fixed 10-step)
    with st.sidebar:
        if st.session_state.get("pyautogui_control_ok", True):
            st.success("Automation: good to go")
        else:
            st.warning(st.session_state.get("pyautogui_control_message", "Automation may not control the display."))
        if st.button("Re-check automation", help="Run the pyautogui display check again (e.g. after granting Accessibility)."):
            _ok, _msg = check_pyautogui_control()
            st.session_state.pyautogui_control_ok = _ok
            st.session_state.pyautogui_control_message = _msg or ""
            st.rerun()
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

        # Historical sessions: expandable list
        st.divider()
        st.markdown("### Historical Sessions")
        init_db()
        rows = []
        con = get_connection()
        try:
            rows = con.execute("""
                SELECT id, goal, status, created_at
                FROM sessions
                ORDER BY created_at DESC
                LIMIT 50
            """).fetchall()
        finally:
            con.close()

        if rows:
            for sid, goal, status, created_at in rows:
                created_str = str(created_at)[:19] if created_at else ""
                label = f"{str(sid)[:8]}… — {status} — {created_str}"
                with st.expander(label, expanded=False):
                    st.markdown(f"**Goal:** {goal or '(none)'}")
                    st.caption(f"Status: {status} · {created_str}")
                    if st.button("View full log", key=f"view_{sid}", type="secondary"):
                        st.session_state.view_session_id = str(sid)
                        st.rerun()
                    con = get_connection()
                    try:
                        logs = con.execute("""
                            SELECT step_number, thought, status, outcome, step_verification_achieved, step_verification_reason, created_at
                            FROM audit_log
                            WHERE session_id = ?
                            ORDER BY step_number
                        """, [str(sid)]).fetchall()
                        if logs:
                            st.markdown("**Steps**")
                            for row in logs:
                                step, thought, step_status, outcome = row[0], row[1], row[2], row[3]
                                step_ver_ok = row[4] if len(row) > 4 else None
                                step_ver_reason = row[5] if len(row) > 5 else None
                                icon = "✅" if outcome == "Pass" else "❌" if outcome == "Fail" else "⏳"
                                st.markdown(f"{icon} Step {step} ({step_status})")
                                st.text(thought or "—")
                                if step_ver_ok is not None or step_ver_reason:
                                    ver_icon = "✅" if str(step_ver_ok).lower() == "true" else "❌"
                                    st.caption(f"Verified {ver_icon}: {step_ver_reason or ''}")
                        pm = con.execute("""
                            SELECT original_goal, perfect_prompt, summary, validation_achieved, validation_reason
                            FROM post_mortems
                            WHERE session_id = ?
                            LIMIT 1
                        """, [str(sid)]).fetchone()
                        if pm:
                            st.markdown("**Post-mortem**")
                            st.caption(pm[2] or "")
                            st.code(pm[1] or "", language="markdown")
                            if len(pm) >= 5 and (pm[3] is not None or pm[4]):
                                st.markdown("**End validation**")
                                if str(pm[3]).lower() == "true":
                                    st.success(f"Achieved — {pm[4] or ''}")
                                else:
                                    st.error(f"Not achieved — {pm[4] or ''}")
                    finally:
                        con.close()
        else:
            st.caption("No sessions yet. Start a task to see history here.")
    
    # Main Area: Title + Status on top; Goal + Live in middle; Session activity at bottom
    st.title("The Universal Tasker")

    # Status bar: Waiting | Running | Succeeded | Failed
    sid = st.session_state.get("session_id")
    is_running = st.session_state.get("is_running", False)
    if st.session_state.get("view_session_id"):
        status_label = "Viewing session"
        status_color = "blue"
    elif not sid:
        status_label = "Waiting"
        status_color = "gray"
    elif is_running:
        status_label = "Running"
        status_color = "orange"
    else:
        init_db()
        con = get_connection()
        try:
            row = con.execute("SELECT status FROM sessions WHERE id = ?", [sid]).fetchone()
            session_status = row[0] if row else ""
        finally:
            con.close()
        if session_status == "success":
            status_label = "Succeeded"
            status_color = "green"
        else:
            status_label = "Failed"
            status_color = "red"
    st.markdown(f"**Status:** {status_label}")
    st.divider()

    # Viewing an older session: show its full log and "Back to current"
    if st.session_state.get("view_session_id"):
        vsid = st.session_state.view_session_id
        if st.button("← Back to current session"):
            st.session_state.view_session_id = None
            st.rerun()
        st.subheader(f"Viewing session: {str(vsid)[:8]}…")
        init_db()
        con = get_connection()
        try:
            row = con.execute(
                "SELECT goal, status, created_at FROM sessions WHERE id = ?", [str(vsid)]
            ).fetchone()
            if row:
                goal, status, created = row[0], row[1], row[2]
                st.caption(f"Goal: {goal or '(none)'} · Status: {status} · {created}")
            logs = con.execute("""
                SELECT step_number, thought, code, status, outcome, step_verification_achieved, step_verification_reason, feedback,
                       screenshot_before_path, screenshot_after_path
                FROM audit_log WHERE session_id = ? ORDER BY step_number
            """, [str(vsid)]).fetchall()
        finally:
            con.close()

        if logs:
            for row in logs:
                step_n, thought, code, step_status, outcome, ver_ok, ver_reason, feedback = (
                    row[0], row[1], row[2], row[3], row[4],
                    row[5] if len(row) > 5 else None,
                    row[6] if len(row) > 6 else None,
                    row[7] if len(row) > 7 else None,
                )
                screenshot_before = row[8] if len(row) > 8 else None
                screenshot_after = row[9] if len(row) > 9 else None
                with st.expander(f"Step {step_n} — {step_status} — {outcome}", expanded=(outcome == "Fail" or step_n == len(logs))):
                    if screenshot_before and os.path.exists(screenshot_before):
                        st.image(screenshot_before, caption="Before", width="stretch")
                    st.markdown("**Thought**")
                    st.text(thought or "—")
                    if code:
                        st.markdown("**Code**")
                        st.code(code, language="python")
                    if screenshot_after and os.path.exists(screenshot_after):
                        st.image(screenshot_after, caption="After", width="stretch")
                    if ver_reason:
                        st.caption(f"Step verification: {ver_ok} — {ver_reason}")
                    if feedback:
                        st.error(feedback)
            # Stuck summary
            last = logs[-1]
            last_status, last_outcome = last[3], last[4]
            if last_status in ("LOST", "error") or last_outcome == "Fail" or (last[5] is not None and str(last[5]).lower() == "false"):
                st.error("**Stuck / failed**")
                stuck_msg = last[7] or last[6] or f"Last step: {last_status} — {last_outcome}"
                st.markdown(stuck_msg)
        else:
            st.info("No step log for this session.")
        st.stop()

    # Current session: Goal + Live Observation in middle
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Live Observation")
        if st.session_state.latest_screenshot and os.path.exists(st.session_state.latest_screenshot):
            st.image(st.session_state.latest_screenshot, caption="Latest Screenshot", width="stretch")
        else:
            st.info("No screenshot captured yet. Enter a goal and click Start.")
        if st.session_state.current_thought:
            st.markdown(f"**Current thought:** {st.session_state.current_thought}")
    with col2:
        st.subheader("Goal")
        goal_input = st.text_area("Enter your goal:", placeholder="Open Calculator and type 'Hello World'", height=100)
        st.text_input(
            "Your browser (optional)",
            placeholder="e.g. Firefox, Chrome, Safari",
            help="Included in the prompt so the agent knows your environment.",
            key="user_browser",
        )
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
            st.session_state.planned_total_steps = None
            st.session_state.checkpoints = []
            st.session_state.session_log = [
                {"message": f"Session started. Goal: {goal_input[:80]}{'…' if len(goal_input) > 80 else ''}", "step": None, "ts": datetime.now().isoformat()},
            ]
            st.session_state.view_session_id = None

            con = get_connection()
            con.execute(
                "INSERT INTO sessions (id, goal, status, max_steps) VALUES (?, ?, ?, ?)",
                [session_id, goal_input, "running", max_steps_input]
            )
            con.close()
            
            st.rerun()
        
        # MiniMax API status
        st.markdown("### MiniMax Status")
        if USE_MINIMAX_STUB or not MINIMAX_API_KEY:
            st.info("Using stub (set MINIMAX_API_KEY and USE_MINIMAX_STUB=false for real API)")
        else:
            st.success("API: Live — next steps printed to console")

    st.divider()
    st.subheader("Session activity")
    session_log = st.session_state.get("session_log") or []
    if session_log:
        try:
            log_container = st.container(height=420)
        except TypeError:
            log_container = st.container()
        with log_container:
            for entry in session_log:
                msg = entry.get("message", "")
                step = entry.get("step")
                prefix = f"**Step {step}** " if step else ""
                # Use chat message so the container auto-scrolls to show the latest entry
                with st.chat_message("assistant", avatar="📋"):
                    st.markdown(f"{prefix}{msg}")
                    code = entry.get("code")
                    if code:
                        st.code(code, language="python")
                    before = entry.get("screenshot_before")
                    after = entry.get("screenshot_after")
                    if before and os.path.exists(before):
                        st.image(before, caption="Before step", width="stretch")
                    if after and os.path.exists(after):
                        st.image(after, caption="After step", width="stretch")
    else:
        st.caption("Activity will appear here after you start a task.")
    
    # Right Sidebar: DuckDB Audit Log
    with st.sidebar:
        st.markdown("---")
        st.markdown("### DuckDB Audit Log")
        
        if st.session_state.get("session_id"):
            con = get_connection()
            logs = con.execute("""
                SELECT step_number, thought, status, outcome, step_verification_achieved, step_verification_reason, created_at
                FROM audit_log
                WHERE session_id = ?
                ORDER BY step_number
            """, [st.session_state.session_id]).fetchall()
            con.close()
            
            if logs:
                for log in logs:
                    step, thought, status, outcome = log[0], log[1], log[2], log[3]
                    step_ver_ok = log[4] if len(log) > 4 else None
                    step_ver_reason = log[5] if len(log) > 5 else None
                    status_icon = "✅" if outcome == "Pass" else "❌" if outcome == "Fail" else "⏳"
                    st.markdown(f"**Step {step}** {status_icon} ({status})")
                    st.text(thought or "—")
                    if step_ver_ok is not None or step_ver_reason:
                        ver_icon = "✅" if str(step_ver_ok).lower() == "true" else "❌"
                        st.caption(f"Step verified {ver_icon}: {step_ver_reason or ''}")
                    st.divider()
            else:
                st.text("No logs yet.")
        else:
            st.text("Start a session to see logs.")
    
    # Loop: run until SUCCESS, LOST, or step_number >= max_steps (eval / decide in agent)
    max_steps = st.session_state.get("max_steps", 10)
    step_n = st.session_state.get("step_number", 0)

    def _log(msg: str, step: Optional[int] = None, screenshot_before: Optional[str] = None, screenshot_after: Optional[str] = None, code: Optional[str] = None) -> None:
        entry = {"message": msg, "step": step, "ts": datetime.now().isoformat()}
        if screenshot_before:
            entry["screenshot_before"] = screenshot_before
        if screenshot_after:
            entry["screenshot_after"] = screenshot_after
        if code:
            entry["code"] = code
        (st.session_state.setdefault("session_log", [])).append(entry)

    if st.session_state.get("is_running") and st.session_state.get("session_id") and step_n <= max_steps:
        _log(f"Step {step_n}: Capturing screenshot…", step_n)
        screenshot_path = f"{SCREENSHOTS_DIR}/{st.session_state.session_id}/step_{step_n}_before.png"
        screenshot, screenshot_feedback = capture_screenshot(screenshot_path)
        if screenshot:
            st.session_state.current_step_screenshot_before = screenshot_path
        _log("Screenshot captured.", step_n, screenshot_before=screenshot_path if screenshot else None)

        if not screenshot:
            st.session_state.is_running = False
            con = get_connection()
            con.execute("UPDATE sessions SET status = ? WHERE id = ?", ["error", st.session_state.session_id])
            con.close()
            st.error(f"Screenshot failed: {screenshot_feedback or 'No image'}. Stopping. You can start a new task.")
            st.rerun()

        try:
            # Get goal
            con = get_connection()
            goal_row = con.execute(
                "SELECT goal FROM sessions WHERE id = ?", [st.session_state.session_id]
            ).fetchone()
            goal = goal_row[0] if goal_row else ""

            _log("Uploading to MiniMax, getting next steps…", step_n)
            user_env = get_user_environment(st.session_state.get("user_browser", ""))
            result = analyze_screenshot(
                screenshot_path, goal, st.session_state.history, user_env=user_env
            )
            
            thought = result["thought"]
            code = result["code"]
            status = result["status"]
            _log(f"Got steps: thought={(thought or '')[:60]}… status={status}", step_n)

            # If agent returned no code (or "pass"), translate step description into code:
            # try rule-based translator first (DuckDB-backed / giant if-else), then API
            if (not code or code.strip() in ("", "pass")) and (thought or "").strip():
                _log("Translating steps (rule-based or API).", step_n)
                translated = translate_task_rules(thought, user_env)
                if not translated:
                    translated = translate_step_to_code(thought, user_env)
                if translated:
                    code = translated

            # First step: use agent's total_steps as the workflow length (dynamic, not fixed 10)
            if st.session_state.step_number == 1:
                if result.get("total_steps") is not None and result["total_steps"] >= 1:
                    st.session_state.planned_total_steps = result["total_steps"]
                    st.session_state.max_steps = max(2, result["total_steps"])  # agent defines workflow length; at least 2
                if result.get("checkpoints"):
                    st.session_state.checkpoints = list(result["checkpoints"])
            
            # Fix MiniMax code: pyautogui.sleep -> time.sleep; add short delays between pyautogui calls so UI can respond
            code_to_run = code.replace("pyautogui.sleep(", "time.sleep(") if "pyautogui.sleep(" in code else code
            # Insert time.sleep(0.6) before each pyautogui call after the first, so e.g. Spotlight appears before we type
            code_to_run = code_to_run.replace("; pyautogui.", "; time.sleep(0.6); pyautogui.")
            _log("Doing steps (executing code).", step_n, code=code_to_run)
            # Run in module scope so pyautogui and time are available and actually control the desktop.
            # Explicitly inject pyautogui and time so exec'd code uses the real modules (not a restricted copy).
            _run_globals = dict(globals())
            _run_globals["pyautogui"] = pyautogui
            _run_globals["time"] = __import__("time")
            try:
                exec(code_to_run, _run_globals)
                # Brief pause so UI updates before we capture the "after" screenshot
                _run_globals["time"].sleep(0.4)
                outcome = "Pass"
                feedback = None
                _log("Step done. Outcome: Pass.", step_n)
            except Exception as e:
                _log(f"Step failed: {str(e)[:80]}", step_n)
                outcome = "Fail"
                feedback = str(e)
                # Capture after screenshot even on failure (for audit)
                after_path = f"{SCREENSHOTS_DIR}/{st.session_state.session_id}/step_{st.session_state.step_number}_after.png"
                _, after_screenshot_path = capture_screenshot(after_path)
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
                    "Step failed (no retry)",
                    feedback,
                    status,
                    outcome,
                    screenshot_path,
                    after_screenshot_path,
                ])
                con.close()
                con = get_connection()
                con.execute("UPDATE sessions SET status = ? WHERE id = ?", ["error", st.session_state.session_id])
                con.close()
                st.session_state.is_running = False
                st.error(f"Step failed: {feedback}. Stopping. No retry.")
                st.rerun()
            
            # Capture after screenshot
            after_path = f"{SCREENSHOTS_DIR}/{st.session_state.session_id}/step_{st.session_state.step_number}_after.png"
            _, after_screenshot_path = capture_screenshot(after_path)
            _log("Screenshot (after step).", step_n, screenshot_after=after_screenshot_path)

            # Per-step verification: did we actually do what we said we would?
            step_verification = verify_step_achieved(thought, after_screenshot_path, user_env)
            step_ver_achieved = None
            step_ver_reason = None
            if step_verification is not None:
                step_ver_achieved = str(step_verification.get("achieved", False))
                step_ver_reason = step_verification.get("reason", "")
                achieved = step_verification.get("achieved", True)
                _log(f"Step verification: {'achieved' if achieved else 'not achieved'} — {step_ver_reason[:80]}", step_n)
                if not achieved:
                    outcome = "Fail"
                    feedback = f"Step verification: {step_ver_reason}"
                    con = get_connection()
                    action_summary = (thought[:120] + "…") if thought and len(thought) > 120 else (thought or "—")
                    con.execute("""
                        INSERT INTO audit_log 
                        (session_id, step_number, thought, code, action, feedback, status, outcome, 
                         screenshot_before_path, screenshot_after_path, step_verification_achieved, step_verification_reason)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        st.session_state.session_id,
                        st.session_state.step_number,
                        thought,
                        code,
                        action_summary,
                        feedback,
                        status,
                        outcome,
                        screenshot_path,
                        after_screenshot_path,
                        step_ver_achieved,
                        step_ver_reason,
                    ])
                    con.execute("UPDATE sessions SET status = ? WHERE id = ?", ["error", st.session_state.session_id])
                    con.close()
                    st.session_state.is_running = False
                    st.error(f"Step verification failed: {step_ver_reason}. Stopping.")
                    st.rerun()

            # At checkpoint steps: save validation screenshot and re-confirm cycle
            if st.session_state.step_number in st.session_state.get("checkpoints", []):
                validation_path = f"{SCREENSHOTS_DIR}/{st.session_state.session_id}/step_{st.session_state.step_number}_validation.png"
                capture_screenshot(validation_path)
            
            # Log to DuckDB (action = short summary of thought for display)
            action_summary = (thought[:120] + "…") if thought and len(thought) > 120 else (thought or "—")
            con = get_connection()
            con.execute("""
                INSERT INTO audit_log 
                (session_id, step_number, thought, code, action, feedback, status, outcome, 
                 screenshot_before_path, screenshot_after_path, step_verification_achieved, step_verification_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                st.session_state.session_id,
                st.session_state.step_number,
                thought,
                code,
                action_summary,
                feedback,
                status,
                outcome,
                screenshot_path,
                after_screenshot_path,
                step_ver_achieved,
                step_ver_reason,
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
                st.error("Agent reported stuck (LOST). Stopping. No retry.")
            else:
                st.session_state.step_number += 1
                if st.session_state.step_number > max_steps:
                    st.session_state.is_running = False
                    con = get_connection()
                    con.execute("UPDATE sessions SET status = ? WHERE id = ?", ["lost", st.session_state.session_id])
                    con.close()
                    st.warning(f"Max attempts ({max_steps}) reached. Stopping.")
            
            st.rerun()
        except Exception as e:
            st.session_state.is_running = False
            # Build rich feedback for audit: exception + traceback
            err_msg = str(e)
            try:
                tb = traceback.format_exc()
                feedback_text = f"{err_msg}\n\nTraceback:\n{tb}" if tb else err_msg
            except Exception:
                feedback_text = err_msg
            # Use any screenshot we had for this step (helps debug what state we were in)
            fail_screenshot_before = st.session_state.get("current_step_screenshot_before")
            if fail_screenshot_before and not os.path.exists(fail_screenshot_before):
                fail_screenshot_before = None
            try:
                con = get_connection()
                con.execute("UPDATE sessions SET status = ? WHERE id = ?", ["error", st.session_state.session_id])
                # Log failure so "View full log" shows why it failed (audit specific failure)
                if st.session_state.get("session_id"):
                    con.execute("""
                        INSERT INTO audit_log
                        (session_id, step_number, thought, code, action, feedback, status, outcome,
                         screenshot_before_path, screenshot_after_path, step_verification_achieved, step_verification_reason)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        st.session_state.session_id,
                        0,
                        "Task failed before or during first step.",
                        None,
                        "Task initialization failed",
                        feedback_text[:8192] if len(feedback_text) > 8192 else feedback_text,  # cap size for DB
                        "error",
                        "Fail",
                        fail_screenshot_before,
                        None,
                        None,
                        None,
                    ])
                con.close()
            except Exception:
                pass
            st.error(f"Task failed: {e}. Stopping. You can start a new task.")
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
            goal_row = con.execute(
                "SELECT goal, status FROM sessions WHERE id = ?", [st.session_state.session_id]
            ).fetchone()
            original_goal = goal_row[0] if goal_row else ""
            session_status = goal_row[1] if goal_row and len(goal_row) > 1 else ""

            # End-screenshot validation: "Is what was asked achieved?"
            validation_result = None
            if session_status == "success" and st.session_state.get("latest_screenshot") and os.path.exists(st.session_state.latest_screenshot):
                if "validation_result" not in st.session_state:
                    user_env = get_user_environment(st.session_state.get("user_browser", ""))
                    st.session_state.validation_result = validate_goal_achieved(
                        original_goal, st.session_state.latest_screenshot, user_env=user_env
                    )
                validation_result = st.session_state.get("validation_result")
                if validation_result is not None:
                    st.markdown("### End screenshot validation")
                    if validation_result.get("achieved"):
                        st.success(f"**Achieved** — {validation_result.get('reason', '')}")
                    else:
                        st.error(f"**Not achieved** — {validation_result.get('reason', '')}")
                else:
                    st.caption("Validation skipped (API unavailable or error).")

            refined = generate_refined_prompt(con, st.session_state.session_id)
            st.markdown("### Optimized Prompt for Next Time")
            st.code(refined, language="markdown")

            # Save to post_mortems once (include validation if we have it)
            val_achieved = str(validation_result.get("achieved")) if validation_result else None
            val_reason = validation_result.get("reason") if validation_result else None
            existing = con.execute(
                "SELECT 1 FROM post_mortems WHERE session_id = ? LIMIT 1",
                [st.session_state.session_id],
            ).fetchone()
            if not existing:
                con.execute("""
                    INSERT INTO post_mortems (session_id, original_goal, perfect_prompt, summary, validation_achieved, validation_reason)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, [st.session_state.session_id, original_goal, refined, "Demo completion", val_achieved, val_reason])
            con.close()
            
            if st.button("Start New Session"):
                st.session_state.clear()
                st.rerun()

if __name__ == "__main__":
    main()
