# 43_DEPLOYMENT_STANDARD.md

## Purpose
This document defines the Deployment Standard for JARVIS OS. It establishes target environment parameters, staging configurations, container build layers, and server staging bounds.

## Scope
Applies to all deployment setups, Dockerfiles, cloud orchestrations, and native Electron packages.

## Deployment standards & Staging Profiles
1. **Containerized Execution:** Production backend services must run inside Docker containers built from minimal, secure base images (e.g. `python:3.11-slim`).
2. **Environment Staging Bounds:**
   - **Local Development:** Native launch via Electron wrappers, local SQLite or Docker Postgres/Redis.
   - **Staging / Testing:** Docker Compose cluster containing Postgres, Redis, and API containers running on a local testing server.
   - **Production:** High-availability cluster using managed Postgres (with pgvector), Redis clusters, and secure sandbox executors (see `28_SANDBOX_POLICY.md`).
3. **Immutability Principle:** Production containers are immutable. Dynamic settings modifications must occur via database configurations or environment variables, not local file changes inside the container.

## Responsibilities
- **DevOps Agent:** Manages deployment configurations, build pipelines, and container scaling.
- **Security Auditor:** Validates base image updates and checks for container security vulnerabilities.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 13 and Rule 14).

## Interfaces
- Docker Compose config file: `docker-compose.yaml`.
- Deployment scripts: `scripts/deploy.sh`.

## Examples
- **Correct Deployment:** Building the API image with multi-stage Docker builds to keep the production layer slim and free of compile dependencies.
- **Incorrect Deployment:** Manually installing updates and packages directly on a live production server VM. (Violates Containerized Execution and Immutability rules).

## Failure Cases
- **Database Connection Failure during Boot:** Managed database takes too long to wake up during server cluster startup. *Mitigation:* The API container boot script uses a connection loop checking connection status every 2 seconds for a maximum of 30 seconds before failing.

## Security Considerations
- Production containers must never run as the `root` user. The Dockerfile must explicitly configure a low-privilege system user (e.g. `RUN useradd jarvis && USER jarvis`).

## Future Extension
- Transitioning to cloud orchestration engines (e.g. Kubernetes) requires updating this standard and logging an ADR.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [28_SANDBOX_POLICY.md](file:///e:/jarvis/docs/28_SANDBOX_POLICY.md)
- [30_CONFIGURATION_STANDARD.md](file:///e:/jarvis/docs/30_CONFIGURATION_STANDARD.md)
- [42_CI_CD_STANDARD.md](file:///e:/jarvis/docs/42_CI_CD_STANDARD.md)
- [49_BUILD_PIPELINE.md](file:///e:/jarvis/docs/49_BUILD_PIPELINE.md)
