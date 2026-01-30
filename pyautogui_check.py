"""
Check whether pyautogui can control the display (required for exec'd automation to actually run).
On macOS this requires Accessibility AND Input Monitoring permissions for the process running the app.
"""
from typing import Tuple

try:
    import pyautogui
except ImportError:
    pyautogui = None


def check_pyautogui_control() -> Tuple[bool, str]:
    """
    Check if pyautogui can control the display.

    The code is executed via exec() and you see "Step done. Outcome: Pass.", but if pyautogui
    isn't allowed to control the display, keypresses/clicks have no effect. On macOS that
    almost always means the process running Streamlit (Terminal or Cursor) doesn't have
    Accessibility permission.

    Returns:
        (ok, message): ok is True if display control works; message is non-empty when ok is False.
    """
    if pyautogui is None:
        return False, "pyautogui is not installed."
    try:
        size = pyautogui.size()
        if not (size and len(size) >= 2 and size[0] > 0 and size[1] > 0):
            return False, "Display size not available."
        # Try a harmless mouse position read/write to check control
        pos = pyautogui.position()
        if pos is None:
            return False, "Cannot read mouse position."
        # Try moving mouse by 0 pixels (no visible effect) to test control
        pyautogui.moveRel(0, 0, _pause=False)
        return True, ""
    except Exception as e:
        err = str(e).lower()
        if "accessibility" in err or "trusted" in err or "permission" in err:
            return False, (
                "macOS: Grant Accessibility permission to Terminal (or Cursor) in "
                "System Settings → Privacy & Security → Accessibility. "
                "Without it, automation runs but does nothing on screen."
            )
        return False, f"pyautogui cannot control display: {e}"


def test_click_works() -> Tuple[bool, str]:
    """
    Actually test that a click can be performed (mouse down + up at current position).
    This is a more robust check than just reading screen size.
    Returns (ok, message).
    """
    if pyautogui is None:
        return False, "pyautogui is not installed."
    try:
        # Get current position
        start_pos = pyautogui.position()
        # Do a tiny move and click at current position (should be harmless)
        pyautogui.click(_pause=False)
        # If we get here without exception, click probably worked
        # (We can't know for sure without a target to click on)
        return True, ""
    except Exception as e:
        err = str(e).lower()
        if "accessibility" in err or "trusted" in err or "permission" in err:
            return False, (
                "Clicks not working: grant Accessibility permission to Terminal (or Cursor) "
                "in System Settings → Privacy & Security → Accessibility."
            )
        return False, f"Click test failed: {e}"


def get_permission_help() -> str:
    """
    Return a help message about macOS permissions.
    Mouse can work with just Accessibility, but keyboard needs Input Monitoring too.
    """
    return """
**If mouse moves but keyboard doesn't work:**

1. **Accessibility** (System Settings → Privacy & Security → Accessibility)
   - Add Terminal or Cursor → Toggle ON

2. **Input Monitoring** (System Settings → Privacy & Security → Input Monitoring)
   - Add Terminal or Cursor → Toggle ON
   - ⚠️ This is often missing! Mouse works without it, keyboard doesn't.

3. **Restart Terminal/Cursor** after granting permissions

4. **Disable Secure Keyboard Entry**
   - Terminal menu → Edit → Uncheck "Secure Keyboard Entry"

5. **Run diagnostic:** `uv run python scripts/diagnose_pyautogui.py`
""".strip()
