# IMPLEMENTATION PROTOCOL

## 1. Development Lifecycle
AI coding agents must never jump straight to code writing. Every milestone implementation must progress through these phases sequentially:

```
    Read Phase Spec
           ↓
   Read Existing Code
           ↓
    Read Prior Tests
           ↓
   Design Architecture
           ↓
  Architecture Audit Check
           ↓
       Implement
           ↓
    Run Mini Gates
           ↓
       Audit Code
           ↓
   Freeze Spec & Plan
```

### Protocol Steps:
1. **Read Spec:** Load the active spec document. Extract all constraints, schemas, invariants, and rules.
2. **Read Existing Code:** Inspect targets, interface classes, and related layers in the directory.
3. **Read Prior Tests:** Review target unit and integration tests.
4. **Design:** Map proposed additions to files, classes, and helper functions.
5. **Architecture Audit Check:** Verify no layer boundary or import rule is violated.
6. **Implement:** Write clean, modular, typed Python code.
7. **Run Mini Gates:** Format, lint, type check, and run tests.
8. **Audit Code:** Self-review against SRP, security boundaries, and reliability standards.
9. **Freeze Spec & Plan:** Record test counts, mark status as frozen, update master index.

---

## 2. Decision Tree for Action Execution
Follow this logical decision tree for every task request:

```
               [ Start Task ]
                      │
                      ▼
             [ Read Phase Spec ]
                      │
                      ▼
             { Is Spec Frozen? }
             /               \
          (Yes)              (No)
           /                   \
          /                 [ STOP & Propose CR ]
         ▼
    [ Read Architecture ]
         │
         ▼
    { Layer/Dependency } ──(Violation?)──► [ STOP & Conflict Report ]
    { Check Passed?    }
         │
       (Yes)
         │
         ▼
    [ Load DTO Contracts ]
         │
         ▼
    { Do DTOs Exist? } ──(No)──► [ Implement & Freeze DTOs First ]
         │
       (Yes)
         │
         ▼
    [ Design Interfaces ]
         │
         ▼
    [ Implement Logic ]
         │
         ▼
    [ Run Quality Gates ]
         │
         ▼
    [ Run Audits ]
         │
         ▼
    [ Freeze Milestone ]
```
