# Universal Tasker - Pitch Notes

## DevPost Description (2-3 sentences)

> **Universal Tasker is an autonomous UI agent that automates any desktop application using natural language.** Powered by MiniMax M2.1 vision, it sees your screen, reasons about what to do, and executes real mouse/keyboard actions—turning goals like "open calculator and add 3+3" into completed tasks with a full audit trail. No scripts, no selectors, no API integrations required.

---

## Social Post (LinkedIn/X)

> Just built Universal Tasker at the #DCCursorMiniMaxHackathon! 🤖
>
> An autonomous UI agent that automates ANY desktop app with plain English. Powered by @MiniMax vision AI—it sees your screen, thinks, and acts.
>
> No scripts. No selectors. Just goals → results.
>
> [demo link] [repo link]

---

## One-Liner (for pitch)
**"Automate any UI with plain English—powered by MiniMax vision."**

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

## Demo Video

**`demo-video.mp4`** — 3 min recorded demo (ready for DevPost submission)

---

## Live Pitch Script (4 min: 2 demo + 1 explain + 1 Q&A)

### Demo (2 min)
1. **Hook** (10s): "What if you could automate any desktop app just by describing what you want?"
2. **Show UI** (10s): "Universal Tasker. Plain English in, task done."
3. **Enter goal** (10s): "Open Calculator and add 3+3"
4. **Watch it work** (60s): Let MiniMax see, reason, execute, verify
5. **Show audit trail** (30s): "Full history—screenshots, actions, verifications"

### Explanation (1 min)
- "$50B RPA market problem—legacy systems don't have APIs"
- "MiniMax M2.1 vision understands ANY interface"
- "Unlike macros, we reason—so it adapts"
- "Healthcare, finance, IT—anywhere humans click"

### Q&A (1 min) — see prep below

## Use Cases to Mention

- **Healthcare billing**: "Imagine automating insurance claim submissions in a legacy EMR"
- **Finance**: "Pulling data from 10 different vendor portals into a spreadsheet"
- **IT support**: "Guided troubleshooting that actually clicks the buttons for you"
- **Accessibility**: "Voice-controlled computer for users who can't use a mouse"

## Technical Highlights (if asked)

- **MiniMax M2.1** for vision + reasoning (sponsor!)
- pyautogui for cross-platform execution
- DuckDB for persistent memory & audit logging
- Streamlit for rapid UI prototyping
- Step verification prevents hallucination loops

## Why This Wins (Judging Criteria Alignment)

| Criteria | How We Score |
|----------|--------------|
| **40% Technical Execution** | Real pyautogui execution, not just chat. Actually clicks, types, and verifies. |
| **25% Impact** | Solves $50B/yr RPA market problem. Healthcare, finance, IT—anyone with legacy UIs. |
| **15% Creativity** | Novel approach: vision-first UI automation vs. brittle selectors/recording. |
| **10% UX/UI** | Clean Streamlit interface, live observation, audit trail. |
| **10% Pitch** | Clear demo: goal → plan → execute → verify → done. |

## MiniMax Integration (Sponsor Track)

- **Primary model**: MiniMax M2.1 via API
- **Usage**: Vision understanding, step planning, code generation, verification
- **Why MiniMax**: Multimodal vision + reasoning in one call; fast inference for real-time automation

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
