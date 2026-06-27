# 49_BUILD_PIPELINE.md

## Purpose
This document defines the Build Pipeline for JARVIS OS. It establishes compiling rules, dependency packaging guidelines, Electron build tasks, and production output structures.

## Scope
Applies to all code compiling tasks, package manager configurations, and Electron builder setups.

## Build Pipeline & Compilation Standards
1. **Multi-Stage Docker Packaging:** Production backend images must use multi-stage builds to separate build dependencies from the execution image:
   - Stage 1 (Build): Compile dependencies, build native assets, run tests.
   - Stage 2 (Package): Copy compiled assets and libraries to a minimal slim image.
2. **Next.js & Electron Compilation:**
   - Next.js must build statically using the `"output": "export"` configuration.
   - Electron builder compiles the static Next.js export bundle and packages the FastAPI executable for native Windows distributions.
3. **Dependency Locking:** All dependencies must be strictly version-locked inside `requirements.txt` (Python) and `package-lock.json` (Next.js) to prevent build drift.

## Responsibilities
- **CI/CD Build Runner:** Automates execution of build tasks and uploads artifacts to registries.
- **Developer Agent:** Verifies library version conflicts before modifying packages manifests.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 13 and Rule 14).

## Interfaces
- Build configurations: `package.json` (Webpack/Electron), `Dockerfile`, and `requirements.txt`.

## Examples
- **Correct Build:** Running `npm run build` which exports Next.js pages as static HTML/JS files, followed by `electron-builder` compilation.
- **Incorrect Build:** Copying raw developer source code directly to production without compiling Next.js assets or verifying locked dependencies. (Violates Compilation Standards).

## Failure Cases
- **Dependency Version Drift:** A minor update to a third-party library breaks system interfaces during the build. *Mitigation:* The build pipeline mandates locking exact version hashes. Semantic version ranges (e.g. `^1.2.0`) are disabled in package manifests.

## Security Considerations
- Generated binaries and images are scanned for vulnerabilities (e.g. CVE databases) during Stage 1 of the build. If critical bugs are found, the pipeline halts immediately.

## Future Extension
- Enhancements to the build targets are tracked inside ADR entries and require full regression validation.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [04_TECHNICAL_REQUIREMENTS.md](file:///e:/jarvis/docs/04_TECHNICAL_REQUIREMENTS.md)
- [42_CI_CD_STANDARD.md](file:///e:/jarvis/docs/42_CI_CD_STANDARD.md)
- [43_DEPLOYMENT_STANDARD.md](file:///e:/jarvis/docs/43_DEPLOYMENT_STANDARD.md)
