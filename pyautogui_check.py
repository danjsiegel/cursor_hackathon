"""
Check whether pyautogui can control the display (required for exec'd automation to actually run).
On macOS this requires Accessibility permission for the process running the app.
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
        if size and len(size) >= 2 and size[0] > 0 and size[1] > 0:
            return True, ""
        return False, "Display size not available."
    except Exception as e:
        err = str(e).lower()
        if "accessibility" in err or "trusted" in err or "permission" in err:
            return False, (
                "macOS: Grant Accessibility permission to Terminal (or Cursor) in "
                "System Settings → Privacy & Security → Accessibility. "
                "Without it, automation runs but does nothing on screen."
            )
        return False, f"pyautogui cannot control display: {e}"
