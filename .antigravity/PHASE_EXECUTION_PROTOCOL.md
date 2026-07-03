# PHASE EXECUTION PROTOCOL

## 1. Milestone Checkpoints
Execution must proceed strictly milestone by milestone. Never run multiple milestones concurrently.

```
       [ Start Milestone ]
                │
                ▼
      [ Implement Milestone ]
                │
                ▼
     [ Run Mini Quality Gate ]
                │
                ▼
     [ Create Milestone Report ]
                │
                ▼
  [ Wait for Architect Approval ]
```

Every milestone requires the developer or coding agent to emit the standard milestone report verbatim and pause execution until explicit human authorization is received.

---

## 2. Milestone Report Template
```
MILESTONE <N> REPORT

Completed:           <one-line summary of what was accomplished>
Files Modified:      <list of absolute or relative paths>
Responsibilities:    <what specific responsibility each file or class now holds>
Architecture Impact: <none / additive / CR-XXX>
Public Interface Changes: <none / list of new public methods/APIs>
Tests Added:         <count + paths of new tests>
Frozen modules touched: <NONE / list of modified files in frozen baseline>
Ruff:                <pass/fail>
Mypy:                <pass/fail>
Coverage:            <% code coverage for the affected files>
Gate status:         PASS / BLOCKED (<reason if blocked>)

Awaiting approval before proceeding. Not proceeding.
```

---

## 3. Phase Completion Checklist
A phase or major sub-milestone cannot be marked COMPLETE until all of the following are checked and verified:
- [ ] **Specification:** Spec status set to `FROZEN` in Phase Status Board.
- [ ] **Implementation Plan:** Plan status is approved.
- [ ] **Walkthrough:** Detailed historical walkthrough generated with screenshots/evidence.
- [ ] **Tests:** Total tests added and total test suite execution verified.
- [ ] **Coverage:** Coverage checks meet requirements.
- [ ] **Ruff Format & Check:** Clean outputs.
- [ ] **Mypy strict annotations:** Clean outputs.
- [ ] **Architecture Audit:** No layer violations or dependency cycles.
- [ ] **Authority Audit:** No frozen components modified without CR validation.
- [ ] **No STOP conditions open:** Resolved conflict reports.
- [ ] **User Approval:** Human sign-off recorded in Git logs or documentation history.

---

## 4. Freeze Validation Protocol
1. Mark Phase Spec Status as `✅ FROZEN` in [AGENTS.md](file:///e:/jarvis/AGENTS.md) and record the exact date and test count.
2. Re-run the full codebase test suite. Verify 0 failures, 0 regressions, and no unexpected changes to previously frozen components.
3. Commit modified and new files under conventional git commit message standards (e.g. `feat(memory): freeze phase 19 implementation`).
