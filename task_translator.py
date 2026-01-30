"""
Rule-based task→code translator for Universal Tasker.
Maps common thought/action descriptions to pyautogui code. Try this before calling the API.

- Giant if/else: built-in patterns (open calculator, type X and press enter, etc.).
- File rules: data/task_translator_rules.json with { "patterns": [...], "code": "...", "code_macos": "..." }.
- Grow rules from DuckDB: run `uv run python scripts/analyze_audit_log.py --export` to merge
  (thought, code) pairs from audit_log into task_translator_rules.json. Then the translator can
  match future thoughts to known code without hitting the API.
"""
from pathlib import Path
import re
from typing import Optional

# Use {modifier} in rule code for win vs command (from user_env: macOS → command, else → win).
# File-based rules in data/task_translator_rules.json override/extend built-in behavior.

# Simpler: list of dicts { "patterns": [...], "code": "..." } so we can load from JSON too.
# First match wins. Pattern is matched if any phrase in "patterns" is in thought (case-insensitive).
RULES_FILE = Path(__file__).resolve().parent / "data" / "task_translator_rules.json"


def _is_macos(user_env: str) -> bool:
    return "macos" in (user_env or "").lower() or "darwin" in (user_env or "").lower()


def _modifier_key(user_env: str) -> str:
    return "command" if _is_macos(user_env) else "win"


def load_rules() -> list[dict]:
    """Load rules from JSON file; return list of {patterns: list[str], code: str, code_macos?: str}."""
    rules = []
    if RULES_FILE.exists():
        try:
            import json
            raw = json.loads(RULES_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                rules = raw
            else:
                rules = raw.get("rules", raw.get("rules_list", []))
        except Exception:
            pass
    return rules


def translate_task_to_code(thought: str, user_env: str = "") -> Optional[str]:
    """
    Translate a task description (thought) to pyautogui code using rule-based matching.
    Returns code string if any rule matches, else None (caller can fall back to API).
    """
    if not (thought or "").strip():
        return None
    text = (thought or "").strip().lower()
    modifier = _modifier_key(user_env)
    use_macos_code = _is_macos(user_env)

    # 1) File-based rules
    for rule in load_rules():
        if not rule.get("code") and not rule.get("code_macos"):
            continue
        patterns = rule.get("patterns", rule.get("pattern", []))
        if isinstance(patterns, str):
            patterns = [patterns]
        if not patterns:
            continue
        for p in patterns:
            if (p or "").lower() in text:
                code = rule.get("code_macos" if use_macos_code else "code") or rule.get("code")
                if code:
                    return code.replace("{modifier}", modifier).strip()
                break

    # 2) Built-in if/else style rules (giant translator)
    if "calculator" in text and ("open" in text or "launch" in text or "run" in text):
        if use_macos_code:
            return "import pyautogui; pyautogui.hotkey('command', 'space'); pyautogui.write('Calculator'); pyautogui.press('enter')"
        return "import pyautogui; pyautogui.hotkey('win', 'r'); pyautogui.write('calc'); pyautogui.press('enter')"

    if "type" in text and ("enter" in text or "press enter" in text):
        # Try to extract what to type: "type 3+3 and press enter" -> write('3+3')
        m = re.search(r"type\s+['\"]?([^'\"]+)['\"]?\s*(?:and\s+)?(?:press\s+enter|then\s+enter)?", text, re.I)
        if m:
            payload = m.group(1).strip()
            return f"import pyautogui; pyautogui.write('{payload}'); pyautogui.press('enter')"
        m = re.search(r"type\s+(\d+[\+\-\*\/]\d+)", text)
        if m:
            payload = m.group(1).strip()
            return f"import pyautogui; pyautogui.write('{payload}'); pyautogui.press('enter')"

    if "hello world" in text and ("type" in text or "type" in text):
        return "import pyautogui; pyautogui.write('Hello World')"

    return None
