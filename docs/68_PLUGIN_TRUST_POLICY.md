# 68_PLUGIN_TRUST_POLICY.md

## Purpose
This document defines the Plugin Trust Policy for JARVIS OS. It establishes the signature requirements, safety scans, sandbox execution verifications, and risk scoring methods used to validate dynamic skills.

## Scope
Applies to all dynamically compiled plugins, external skill repositories, and registry managers.

## Plugin Validation & Trust pipeline
No dynamic skill can be loaded or executed by any agent unless it successfully passes the trust pipeline:

```
Download / Generate Skill Package
        ↓
Scan Source Code for Forbidden Imports (e.g. ctypes, os.system)
        ↓
Audit package dependency manifest (requirements.txt)
        ↓
Compute Risk Score (Scale 0-100)
    ├─ [Risk > 30] → Reject Skill & Log Warning
    └─ [Risk <= 30] → Continue
        ↓
Compile & Execute Test Suite inside Sandbox
        ↓
Pass Tests? → [YES] → Generate SHA-256 Signature using Vault Key
        ↓
Install Package to Skill Registry
```

### Trust Validation Rules
1. **Signature Verification Standard:** Every time a skill is loaded into memory, the Skill Loader must verify its SHA-256 signature against the registry database.
2. **Permission Isolation:** Skills cannot request permissions (e.g. network access) unless explicitly declared in their manifest file (see `17_SKILL_SDK_SPEC.md`).
3. **Risk Scoring Metrics:**
   - Base score: 0.
   - Adds 15 points if file write is requested.
   - Adds 20 points if outbound network access is requested.
   - Adds 50 points if raw CLI command execution is requested.

## Responsibilities
- **Security Agent:** Runs static code analysis, evaluates risk scores, and generates digital signatures.
- **Skill Loader:** Validates signatures at runtime before executing imports.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 4 and Rule 14).

## Interfaces
- Local APIs: `SecurityAgent.scan_skill(path: str)` and `SkillLoader.load_skill(name: str)`.

## Examples
- **Correct Validation Flow:** Dynamic web scraper skill has a risk score of 20. Static scan passes, tests pass in sandbox, signature is written, and execution succeeds.
- **Incorrect Validation Flow:** Loading a skill package without static scanning or signature checks, letting it write files to host directly. (Violates zero-trust and signature rules).

## Failure Cases
- **Signature Mismatch:** A registered skill file is modified on disk by an external process. *Mitigation:* The Skill Loader computes the SHA-256 hash at execution time and compares it. If it differs, the loader blocks import, flags a tampering alert, and boots into Emergency Stop.

## Security Considerations
- Vault keys used for signing skills must be kept in the encrypted vault and never exposed to active agent memory pools.

## Future Extension
- Enhancing risk metrics or scanner scripts is managed under ADR logs.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [16_SKILL_SYSTEM.md](file:///e:/jarvis/docs/16_SKILL_SYSTEM.md)
- [17_SKILL_SDK_SPEC.md](file:///e:/jarvis/docs/17_SKILL_SDK_SPEC.md)
- [26_SECURITY_CONSTITUTION.md](file:///e:/jarvis/docs/26_SECURITY_CONSTITUTION.md)
- [29_SECRET_MANAGEMENT.md](file:///e:/jarvis/docs/29_SECRET_MANAGEMENT.md)
