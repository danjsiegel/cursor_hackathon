"""
The Universal Tasker - D.C. AI Hackathon
A 10-step autonomous loop with MiniMax reasoning, DuckDB memory, and Streamlit UI.
"""

import base64
import json
import os
import platform
import re
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
    """Build a short description of the user's OS and browser for MiniMax context."""
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
            f"Step {h.get('step_number', i+1)}: thought={h.get('thought', '')[:200]} status={h.get('status', '')} outcome={h.get('outcome', '')}"
            for i, h in enumerate(history)
        ])

    first_step_extra = ""
    if is_first_step:
        first_step_extra = """
## First step only: plan and checkpoints
On the **first** response (this one), also include:
- "total_steps": (integer) How many steps you expect to need to complete the goal. We use this as a recommended stop point.
- "checkpoints": (array of step numbers, e.g. [2, 4]) Step numbers at which we should take a validation screenshot and re-confirm the cycle. These are good points to pause, screenshot, and validate progress before continuing. If none, use [].

Example first response:
{"thought": "I see the desktop. I will open Calculator via Run.", "code": "import pyautogui; pyautogui.hotkey('command', 'space'); pyautogui.write('Calculator'); pyautogui.press('enter')", "status": "CONTINUE", "total_steps": 3, "checkpoints": [2]}
"""

    user_context_line = f"\n**User context:** {user_env}\n" if user_env else ""
    system_prompt = """You are the reasoning engine for the Universal Tasker: an autonomous UI agent that completes a user's goal by controlling the computer with Python.
""" + user_context_line + """
## What we do
- We send you the current screen (screenshot image) and the user's goal.
- You respond with exactly one "next step": your reasoning, one snippet of Python code we will execute, and a status.
- We run your code with pyautogui on the live machine, then capture a new screenshot and call you again with the updated state.
- This repeats until you return status SUCCESS (goal done), LOST (stuck), or we hit a step limit.
- If we get stuck (LOST or code error), we stop immediately and do not retry or self-solve.

## What we need from you (exactly one JSON object, no markdown, no text outside the JSON)
- "thought": 1–2 sentences: what you see in the screenshot and what you will do in this step. Be specific (e.g. "I see the Calculator window; I will type the number 42.").
- "code": Valid Python code that we will run via exec(). It must use only the pyautogui API and Python built-ins. Prefer a single line with semicolons; if you need multiple lines, keep it minimal. Each response is executed in isolation, so include "import pyautogui" in the snippet if you use it.
- "status": Exactly one of:
  - "CONTINUE" — more steps needed to reach the goal.
  - "SUCCESS" — the goal is achieved; we will stop.
  - "LOST" — you cannot proceed (wrong screen, missing element, or need human input); we will stop. We do not retry; we error out.
""" + first_step_extra + """
## Allowed Python tools (pyautogui only)
- Mouse: pyautogui.click(x, y) or click() for current position, doubleClick(), rightClick(), moveTo(x,y), moveRel(dx,dy), drag(x,y), scroll(amount)
- Keyboard: pyautogui.write("text"), pyautogui.press("enter"), pyautogui.hotkey("ctrl", "c") or hotkey("command", "v")
- Modifier keys: On macOS use "command" and "option"; on Windows use "win" and "alt". Use "ctrl", "shift", "enter", "tab", "space" as needed.
- Do not use: PIL, selenium, other libs, or file/network operations. Only pyautogui and built-ins (e.g. time.sleep(1) for short delays).

## Rules
- One atomic action per response (e.g. one click, one type, one key combo). We will call you again for the next step.
- Code must run without user input and without opening dialogs that block (prefer direct keystrokes or clicks).
- Respond with only the JSON object. No preamble, no markdown code fence, no explanation after the JSON.
"""

    if not is_first_step:
        system_prompt += '\nExample response:\n{"thought": "Calculator is open. I will type 42.", "code": "import pyautogui; pyautogui.write(\\"42\\"); pyautogui.press(\\"enter\\")", "status": "SUCCESS"}'

    user_text = f"Goal: {goal}\n\n"
    if history_text:
        user_text += f"Steps already taken (for context):\n{history_text}\n\n"
    user_text += "The current screenshot is attached. Respond with exactly one JSON object"
    if is_first_step:
        user_text += " with keys: thought, code, status, total_steps, checkpoints."
    else:
        user_text += " with keys: thought, code, status."

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

    system_prompt = """You are a validator. Given a user's goal and a screenshot of the final state after a task, determine if what was asked was achieved.
Respond with exactly one JSON object, no markdown, no other text:
- "achieved": true or false
- "reason": one or two sentences explaining what you see and why it does or does not match the goal."""
    if user_env:
        system_prompt += f"\n**User context:** {user_env}"

    user_text = f"The user asked for: {goal}\n\n"
    if user_env:
        user_text += f"User context: {user_env}\n\n"
    user_text += "This screenshot shows the final state. Is what was asked achieved? Respond with only a JSON object: {\"achieved\": true or false, \"reason\": \"...\"}."

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

    system_prompt = """You are a step verifier. The agent said it would do something. This screenshot shows the state AFTER that step.
Your job: did the agent actually do what it said? (e.g. if it said "open Calculator", is Calculator open?)
Respond with exactly one JSON object, no markdown:
- "achieved": true or false
- "reason": one or two sentences: what you see in the screenshot and whether it matches what was intended."""
    if user_env:
        system_prompt += f"\n**User context:** {user_env}"

    user_text = f"I intended to do: {intended_thought}\n\n"
    if user_env:
        user_text += f"User context: {user_env}\n\n"
    user_text += "This screenshot is the state after the step. Did I actually do these things? Respond with only a JSON object: {\"achieved\": true or false, \"reason\": \"...\"}."

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

    system_prompt = """You convert a step description into exactly one line of Python code using only pyautogui and built-ins.
Output ONLY the code, no explanation, no markdown. Use semicolons for multiple statements. Include "import pyautogui" if needed.
Examples:
- "press Windows key and type Calculator" -> import pyautogui; pyautogui.press('win'); pyautogui.write('Calculator'); pyautogui.press('enter')
- "type 3+3 and press Enter" -> import pyautogui; pyautogui.write('3+3'); pyautogui.press('enter')
On macOS use 'command' not 'win'; on Windows use 'win'."""
    if user_env:
        system_prompt += f"\n**User context:** {user_env}"

    user_text = f"Convert this step into pyautogui code (one line, no explanation): {step_description}"

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
    
    # Main Area: Live Screenshot + Thought
    st.title("The Universal Tasker")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("Live Observation")
        
        if st.session_state.latest_screenshot and os.path.exists(st.session_state.latest_screenshot):
            st.image(st.session_state.latest_screenshot, caption="Latest Screenshot", use_container_width=True)
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
            
            # Call MiniMax (or stub) with user context (OS, browser)
            user_env = get_user_environment(st.session_state.get("user_browser", ""))
            result = analyze_screenshot(
                screenshot_path, goal, st.session_state.history, user_env=user_env
            )
            
            thought = result["thought"]
            code = result["code"]
            status = result["status"]

            # If agent returned no code (or "pass"), translate step description into code
            if (not code or code.strip() in ("", "pass")) and (thought or "").strip():
                translated = translate_step_to_code(thought, user_env)
                if translated:
                    code = translated

            # First step: store planned total_steps and checkpoints from MiniMax
            if st.session_state.step_number == 1:
                if result.get("total_steps") is not None and result["total_steps"] > 0:
                    st.session_state.planned_total_steps = result["total_steps"]
                    st.session_state.max_steps = result["total_steps"]
                if result.get("checkpoints"):
                    st.session_state.checkpoints = list(result["checkpoints"])
            
            # Execute the action (pyautogui). On failure: error out, do not continue.
            try:
                exec(code)
                outcome = "Pass"
                feedback = None
            except Exception as e:
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

            # Per-step verification: did we actually do what we said we would?
            step_verification = verify_step_achieved(thought, after_screenshot_path, user_env)
            step_ver_achieved = None
            step_ver_reason = None
            if step_verification is not None:
                step_ver_achieved = str(step_verification.get("achieved", False))
                step_ver_reason = step_verification.get("reason", "")
                if not step_verification.get("achieved", True):
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
