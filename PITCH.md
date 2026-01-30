# Universal Tasker - Pitch Notes

## One-Liner
**"Automate any UI with plain English—no scripts, no selectors, just goals."**

## The Problem

1. **Legacy systems don't integrate**
   - Healthcare: EMRs that only work through the UI
   - Finance: Vendor portals without APIs
   - Enterprise: Thick clients from the 90s still in production

2. **Traditional automation is fragile**
   - Selenium scripts break when UIs change
   - RPA tools require expensive consultants
   - Recording macros doesn't handle edge cases

3. **Knowledge workers waste time on repetitive tasks**
   - Copy-paste between systems
   - Manual data entry
   - Repetitive clicking through workflows

## The Solution: Universal Tasker

**An AI that sees your screen and does tasks like a human would.**

- **Input**: Plain English goal ("Fill out the patient billing form")
- **Process**: Vision AI reasons about what it sees, executes actions, verifies each step
- **Output**: Task completed, with full audit trail

## Key Differentiators

| Traditional RPA | Universal Tasker |
|-----------------|------------------|
| Record & playback | Understand & reason |
| Breaks when UI changes | Adapts to what it sees |
| One task = one script | One agent = infinite tasks |
| Requires developers | Anyone can use it |

## Demo Script

1. **Show the UI**: "This is Universal Tasker. I give it a goal in plain English."

2. **Enter goal**: "Open Calculator and add 3+3"

3. **Watch it work**:
   - "It takes a screenshot and sends it to the AI"
   - "The AI reasons: 'I see the desktop, I'll open Spotlight'"
   - "It executes the action and verifies it worked"
   - "It continues until the goal is achieved"

4. **Show the audit log**: "Every step is recorded—what it saw, what it did, whether it worked"

## Use Cases to Mention

- **Healthcare billing**: "Imagine automating insurance claim submissions in a legacy EMR"
- **Finance**: "Pulling data from 10 different vendor portals into a spreadsheet"
- **IT support**: "Guided troubleshooting that actually clicks the buttons for you"
- **Accessibility**: "Voice-controlled computer for users who can't use a mouse"

## Technical Highlights (if asked)

- MiniMax M2.1 for vision + reasoning
- pyautogui for cross-platform execution
- DuckDB for audit logging
- Streamlit for rapid UI prototyping
- Step verification prevents hallucination loops

## Challenges We Solved

1. **Browser focus issue**: Browser captures keyboard shortcuts; we use AppleScript to manage focus
2. **Timing**: Added delays so UI can respond before next action
3. **Verification**: AI checks each step worked before proceeding
4. **Determinism**: Prompt engineering to prefer reliable patterns (Spotlight over clicking)

## Future Vision

- **Workflow learning**: Learn from successful runs, skip AI for known patterns
- **Multi-agent**: Coordinate multiple Taskers across machines
- **Voice interface**: "Hey Tasker, submit the billing form"
- **Enterprise deployment**: Secure, audited automation at scale

## Q&A Prep

**Q: How is this different from RPA?**
A: RPA records fixed scripts. We understand intent and adapt to what we see.

**Q: What about security?**
A: Full audit trail, runs locally, no data leaves except to the AI API.

**Q: Can it handle complex workflows?**
A: It breaks goals into steps and verifies each one. For complex tasks, it plans ahead.

**Q: What if it gets stuck?**
A: It stops and explains why instead of thrashing. Graceful failure is a feature.

---

## Closing Statement

"We're not just automating tasks—we're giving every knowledge worker a digital assistant that can operate any software they can."
