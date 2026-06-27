# 21_PC_AUTOMATION_ARCHITECTURE.md

## Purpose
This document defines the PC Automation Architecture for JARVIS OS. It governs how execution agents safely automate keyboard input, mouse coordinates, window management, clipboard manipulation, and OS terminal commands.

## Scope
Applies to all PC control tool adapters, subprocess executors, and window focus monitors inside the Tool Layer.

## PC Control Architecture & Rules
1. **Low-Privilege Shell Standard:** All shell execution, powershell calls, and terminal processes must run under a restricted user profile. Raw administrative or root-level shell invocation is strictly prohibited.
2. **Coordination Coordinate Checks:** Mouse and keyboard automation APIs must use relative grid boundaries.
3. **Execution Safety Rule:** Destruction terminal commands (`rm -rf`, `Format`, `del`, registry edits) are blocked by default and require explicit multi-factor human confirmation (see `27_PERMISSION_SYSTEM.md`).
4. **Active Window Containment:** Keyboard automation must check the active window title before sending keystrokes to prevent sending inputs to unintended host applications.

## Responsibilities
- **PC Control Agent:** Processes OS commands, checks coordinate positions, and manages screen captures.
- **Security Auditor Agent:** Intercepts terminal command scripts and runs safety regex scans before execution.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 4, Rule 12, and Rule 13).

## Interfaces
- Local APIs: `jarvis.pc.mouse`, `jarvis.pc.keyboard`, `jarvis.pc.clipboard`, and `jarvis.pc.terminal`.
- UI: Base64 screenshots streamed over WebSockets for human-in-the-loop observation.

## Examples
- **Correct PC Execution:** Agent needs to copy a text block -> reads clip contents via safe clipboard manager API -> logs transaction -> performs paste.
- **Incorrect PC Execution:** Agent runs `os.system("echo 'hack' > /etc/shadow")` directly on host hardware. (Violates low-privilege and security gates rules).

## Failure Cases
- **Unintended Keystroke Targets:** The active window switches during a typing loop (e.g. a popup appears). *Mitigation:* The PC Control Agent performs a window title match validation check before every keystroke block is dispatched. If the active window differs, execution halts.

## Security Considerations
- Screen capture files must be stored in secure temp directories and shredded upon task completion to prevent caching sensitive UI info.

## Future Extension
- Windows/Linux API compatibility wrappers are updated and tracked inside custom OS adapter files.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [14_PC_CONTROL_SYSTEM.md](file:///e:/jarvis/docs/14_PC_CONTROL_SYSTEM.md)
- [18_TOOL_EXECUTION_POLICY.md](file:///e:/jarvis/docs/18_TOOL_EXECUTION_POLICY.md)
- [27_PERMISSION_SYSTEM.md](file:///e:/jarvis/docs/27_PERMISSION_SYSTEM.md)
