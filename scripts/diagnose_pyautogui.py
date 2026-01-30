#!/usr/bin/env python3
"""
Diagnostic script to check if pyautogui can control your Mac.
Run this from Terminal (not Cursor) to test permissions.

Usage:
    cd cursor_hackathon
    uv run python scripts/diagnose_pyautogui.py
"""
import platform
import sys
import time

print("=" * 60)
print("Universal Tasker - PyAutoGUI Diagnostic")
print("=" * 60)
print()

# Check OS
print(f"OS: {platform.system()} {platform.release()}")
print(f"Python: {sys.version}")
print()

# Check pyautogui import
try:
    import pyautogui
    print("✅ pyautogui imported successfully")
except ImportError as e:
    print(f"❌ Failed to import pyautogui: {e}")
    print("   Run: uv sync")
    sys.exit(1)

# Check screen size
try:
    size = pyautogui.size()
    print(f"✅ Screen size: {size.width}x{size.height}")
except Exception as e:
    print(f"❌ Cannot get screen size: {e}")

# Check mouse position
try:
    pos = pyautogui.position()
    print(f"✅ Mouse position: ({pos.x}, {pos.y})")
except Exception as e:
    print(f"❌ Cannot get mouse position: {e}")

print()
print("-" * 60)
print("TEST 1: Mouse Movement")
print("-" * 60)
print("Moving mouse to (100, 100) then back...")
try:
    original_pos = pyautogui.position()
    pyautogui.moveTo(100, 100, duration=0.5)
    time.sleep(0.2)
    new_pos = pyautogui.position()
    pyautogui.moveTo(original_pos.x, original_pos.y, duration=0.3)
    
    if abs(new_pos.x - 100) < 10 and abs(new_pos.y - 100) < 10:
        print(f"✅ Mouse movement works! Moved to ({new_pos.x}, {new_pos.y})")
    else:
        print(f"⚠️  Mouse moved but not to expected position. Got ({new_pos.x}, {new_pos.y}), expected (100, 100)")
except Exception as e:
    print(f"❌ Mouse movement failed: {e}")

print()
print("-" * 60)
print("TEST 2: Click (at current position)")
print("-" * 60)
print("Performing a click at current mouse position...")
try:
    pyautogui.click()
    print("✅ Click executed (no exception)")
    print("   NOTE: We can't verify if the click registered with the OS.")
except Exception as e:
    print(f"❌ Click failed: {e}")

print()
print("-" * 60)
print("TEST 3: Keyboard - Simple Key Press")
print("-" * 60)
print("This will press 'a' key. Position cursor in a text field first!")
input("Press Enter when ready (cursor in a text field)...")
try:
    pyautogui.press('a')
    time.sleep(0.3)
    print("✅ Key press executed (check if 'a' appeared)")
except Exception as e:
    print(f"❌ Key press failed: {e}")

print()
print("-" * 60)
print("TEST 4: Hotkey - Command+Space (Spotlight)")
print("-" * 60)
print("This will press Cmd+Space to open Spotlight.")
print("Watch your screen - Spotlight search should appear.")
input("Press Enter when ready...")
try:
    pyautogui.hotkey('command', 'space')
    time.sleep(1)
    print("✅ Hotkey executed")
    print()
    did_it_work = input("Did Spotlight open? (y/n): ").strip().lower()
    if did_it_work == 'y':
        print("✅ Great! Keyboard control is working.")
        # Close Spotlight
        pyautogui.press('escape')
    else:
        print()
        print("❌ PROBLEM IDENTIFIED: Hotkey didn't work.")
        print()
        print("This usually means one of:")
        print()
        print("1. ACCESSIBILITY PERMISSION MISSING")
        print("   → System Settings → Privacy & Security → Accessibility")
        print("   → Add Terminal (or the app running this script)")
        print()
        print("2. INPUT MONITORING PERMISSION MISSING (macOS Catalina+)")
        print("   → System Settings → Privacy & Security → Input Monitoring")
        print("   → Add Terminal (or the app running this script)")
        print()
        print("3. SECURE INPUT MODE ENABLED")
        print("   Some apps (1Password, banking apps, password fields) enable")
        print("   'Secure Input' which blocks all keyboard automation.")
        print("   → Close password managers and try again")
        print("   → Check: In Terminal menu bar → Edit → 'Secure Keyboard Entry' should be UNCHECKED")
        print()
        print("4. ANOTHER APP CAPTURING CMD+SPACE")
        print("   → Check System Settings → Keyboard → Keyboard Shortcuts → Spotlight")
        print("   → Make sure Cmd+Space is set for Spotlight")
        print("   → Check if any other app (Alfred, Raycast) uses this shortcut")
        print()
except Exception as e:
    print(f"❌ Hotkey failed with exception: {e}")

print()
print("-" * 60)
print("TEST 5: Type Text")
print("-" * 60)
print("This will type 'hello'. Position cursor in a text field first!")
input("Press Enter when ready (cursor in a text field)...")
try:
    pyautogui.write('hello', interval=0.1)
    time.sleep(0.3)
    print("✅ Typing executed (check if 'hello' appeared)")
except Exception as e:
    print(f"❌ Typing failed: {e}")

print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
print()
print("If mouse moves but keyboard doesn't work:")
print()
print("1. Grant BOTH permissions in System Settings → Privacy & Security:")
print("   - Accessibility: ✅ (for mouse and basic control)")
print("   - Input Monitoring: ✅ (for keyboard input)")
print()
print("2. RESTART Terminal/Cursor after granting permissions")
print()
print("3. Check 'Secure Keyboard Entry' is DISABLED:")
print("   Terminal menu → Edit → uncheck 'Secure Keyboard Entry'")
print()
print("4. Try running from a REGULAR Terminal window, not Cursor's terminal")
print()
