# 73_HEALTH_MONITORING.md

## Purpose
This document defines the Health Monitoring policy for JARVIS OS. It establishes the ping interval rates, active status checks, resource gauges, and dashboard alert thresholds to monitor system availability.

## Scope
Applies to the System Supervisor, observability daemons, database connection monitors, and container engines.

## Health Monitoring & Ping Policies
1. **Daemon Ping Intervals:**
   - Database connection check: Every **15 seconds** (executes `SELECT 1`).
   - Redis connectivity check: Every **10 seconds** (executes `PING`).
   - Docker daemon socket check: Every **30 seconds**.
   - Outbound internet gateway check: Every **60 seconds** (pings public DNS).
2. **Resource Alert Thresholds:**
   - Host Memory utilization > 90%: Trigger Warning Alert.
   - Host CPU utilization > 95% for more than 2 minutes: Throttle active subagents.
   - Host Disk Space < 10%: Block new database writes and log warnings.
3. **Telemetry Streaming:** System health indicators (Database: OK, Redis: OK, Docker: OK, Internet: OK) must stream to the dashboard header using WebSocket packages every 5 seconds.

## Responsibilities
- **Observability Daemon:** Gathers status pings and compiles health metrics.
- **System Supervisor:** Listens to status pings, and executes failsafe operations when pings fail.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- REST API: `/api/v1/system/health` (returns standard JSON health envelopes, see `34_API_STANDARD.md`).

## Examples
- **Correct Monitoring:** Observatory daemon pings Redis -> Redis fails to respond -> daemon flags connection drop -> supervisor initiates connection reconnect loop.
- **Incorrect Monitoring:** Disabling all ping checks to reduce CPU load, leaving background worker crashes unnoticed until a manual query fails. (Violates health monitoring requirements).

## Failure Cases
- **Ping Storms:** Too many concurrent pings create overhead on the database engine. *Mitigation:* Health pings are serialized in a single, lightweight async thread that shares connection pools (see `35_DATABASE_STANDARD.md`).

## Security Considerations
- Health metrics must not return path structures or system configurations to public endpoints. The `/api/v1/system/health` route is protected by L0 read-only permissions.

## Future Extension
- Integrating cloud-based observability dashboards (e.g. Datadog / Grafana Cloud) is planned for Phase 10.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [39_OBSERVABILITY_STANDARD.md](file:///e:/jarvis/docs/39_OBSERVABILITY_STANDARD.md)
- [48_FAILSAFE_AND_ROLLBACK.md](file:///e:/jarvis/docs/48_FAILSAFE_AND_ROLLBACK.md)
- [70_BOOT_SEQUENCE.md](file:///e:/jarvis/docs/70_BOOT_SEQUENCE.md)
