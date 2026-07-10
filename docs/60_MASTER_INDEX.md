# 60_MASTER_INDEX.md

## Purpose
This document establishes the Master Index for JARVIS OS. It compiles the clickable references, targets, and file summaries for all 74 foundational documents in the Jarvis Development Bible v1.0.

## Scope
Applies to all files written under the `docs/` folder in Phase 0.

## Master Index & Clickable File Map

### Wave 1: Foundation (Files 00-10)
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) – The core 15 pillars of developer/agent rules.
- [01_PROJECT_CHARTER.md](file:///e:/jarvis/docs/01_PROJECT_CHARTER.md) – Project charter, mission, and scope boundaries.
- [02_SYSTEM_VISION.md](file:///e:/jarvis/docs/02_SYSTEM_VISION.md) – Visual and operational vision of an AI Employee.
- [03_PRODUCT_REQUIREMENTS.md](file:///e:/jarvis/docs/03_PRODUCT_REQUIREMENTS.md) – Product Requirements Document (PRD).
- [04_TECHNICAL_REQUIREMENTS.md](file:///e:/jarvis/docs/04_TECHNICAL_REQUIREMENTS.md) – Technical Requirements Document (TRD).
- [05_SYSTEM_ARCHITECTURE.md](file:///e:/jarvis/docs/05_SYSTEM_ARCHITECTURE.md) – System components and flow diagram.
- [06_ARCHITECTURE_DECISION_RECORDS.md](file:///e:/jarvis/docs/06_ARCHITECTURE_DECISION_RECORDS.md) – **Legacy** ADR pointer (ADR-01..05 migrated to canonical on 2026-07-10; see `docs/architecture/adrs/`).
- [architecture/adrs/](file:///e:/jarvis/docs/architecture/adrs/README.md) – **Canonical** Architecture Decision Records registry (16 ADRs, Nygard format). Per `docs/governance/pre_milestone_gate.md` §2.2 (frozen M5.5.0).
- [07_DESIGN_PRINCIPLES.md](file:///e:/jarvis/docs/07_DESIGN_PRINCIPLES.md) – Six core design values (Simple, Modular, etc.).
- [08_AI_AGENT_CONSTITUTION.md](file:///e:/jarvis/docs/08_AI_AGENT_CONSTITUTION.md) – Agent roles and permission boundaries.
- [09_PROMPT_CONSTITUTION.md](file:///e:/jarvis/docs/09_PROMPT_CONSTITUTION.md) – Standards to prevent prompt drift.
- [10_CONTEXT_LOADING_RULES.md](file:///e:/jarvis/docs/10_CONTEXT_LOADING_RULES.md) – Layered context loading rules.

### Wave 2: Reasoning & Core Capabilities (Files 11-20)
- [11_REASONING_POLICY.md](file:///e:/jarvis/docs/11_REASONING_POLICY.md) – Goal stacks, reflection limits, and loop bounds.
- [12_MEMORY_ARCHITECTURE.md](file:///e:/jarvis/docs/12_MEMORY_ARCHITECTURE.md) – Multi-tier database layouts and pipelines.
- [13_MULTI_AGENT_PROTOCOL.md](file:///e:/jarvis/docs/13_MULTI_AGENT_PROTOCOL.md) – JSON communication schema.
- [14_SUBAGENT_ORCHESTRATION.md](file:///e:/jarvis/docs/14_SUBAGENT_ORCHESTRATION.md) – Spawning lifecycles and quotas.
- [15_TASK_DECOMPOSITION.md](file:///e:/jarvis/docs/15_TASK_DECOMPOSITION.md) – Goal-tree waves and dependency parsing.
- [16_SKILL_SYSTEM.md](file:///e:/jarvis/docs/16_SKILL_SYSTEM.md) – Dynamic skill generation, testing, and signing.
- [17_SKILL_SDK_SPEC.md](file:///e:/jarvis/docs/17_SKILL_SDK_SPEC.md) – Plugin structures and manifest models.
- [18_TOOL_EXECUTION_POLICY.md](file:///e:/jarvis/docs/18_TOOL_EXECUTION_POLICY.md) – Security gates and parameters scanning.
- [19_MODEL_ROUTING_POLICY.md](file:///e:/jarvis/docs/19_MODEL_ROUTING_POLICY.md) – Fallbacks and spending limits.
- [20_BROWSER_ARCHITECTURE.md](file:///e:/jarvis/docs/20_BROWSER_ARCHITECTURE.md) – Chromium Electron wrapper overlay layouts.

### Wave 3: Security & OS Policy (Files 21-30)
- [21_PC_AUTOMATION_ARCHITECTURE.md](file:///e:/jarvis/docs/21_PC_AUTOMATION_ARCHITECTURE.md) – Mouse, keyboard, and terminal automation rules.
- [22_SELF_IMPROVEMENT_POLICY.md](file:///e:/jarvis/docs/22_SELF_IMPROVEMENT_POLICY.md) – Heuristics, review structures, and gated patches.
- [23_SELF_HEALING_POLICY.md](file:///e:/jarvis/docs/23_SELF_HEALING_POLICY.md) – Crash recovery stacks and RCA.
- [24_LEARNING_ENGINE.md](file:///e:/jarvis/docs/24_LEARNING_ENGINE.md) – API scrapers and document ingestion.
- [25_KNOWLEDGE_GRAPH.md](file:///e:/jarvis/docs/25_KNOWLEDGE_GRAPH.md) – Node-edge schema definitions.
- [26_SECURITY_CONSTITUTION.md](file:///e:/jarvis/docs/26_SECURITY_CONSTITUTION.md) – Encryption standards and sandboxing.
- [27_PERMISSION_SYSTEM.md](file:///e:/jarvis/docs/27_PERMISSION_SYSTEM.md) – L0-L3 authorization levels.
- [28_SANDBOX_POLICY.md](file:///e:/jarvis/docs/28_SANDBOX_POLICY.md) – Docker limits, mounts, and network blocks.
- [29_SECRET_MANAGEMENT.md](file:///e:/jarvis/docs/29_SECRET_MANAGEMENT.md) – AES GCM vaults and environment isolation.
- [30_CONFIGURATION_STANDARD.md](file:///e:/jarvis/docs/30_CONFIGURATION_STANDARD.md) – Pydantic models and config profiles.

### Wave 4: Standards & Data Schema (Files 31-40)
- [31_FOLDER_STRUCTURE_STANDARD.md](file:///e:/jarvis/docs/31_FOLDER_STRUCTURE_STANDARD.md) – Workspace directories structure.
- [32_NAMING_STANDARD.md](file:///e:/jarvis/docs/32_NAMING_STANDARD.md) – Variable, file, and database table names.
- [33_CODE_STANDARD.md](file:///e:/jarvis/docs/33_CODE_STANDARD.md) – Styling, types, and length limits.
- [34_API_STANDARD.md](file:///e:/jarvis/docs/34_API_STANDARD.md) – REST and WebSocket JSON envelopes.
- [35_DATABASE_STANDARD.md](file:///e:/jarvis/docs/35_DATABASE_STANDARD.md) – Alembic migrations and indexing.
- [36_EVENT_STANDARD.md](file:///e:/jarvis/docs/36_EVENT_STANDARD.md) – Event bus and topic hierarchies.
- [37_LOGGING_STANDARD.md](file:///e:/jarvis/docs/37_LOGGING_STANDARD.md) – JSON structure logs and trace IDs.
- [38_ERROR_HANDLING_STANDARD.md](file:///e:/jarvis/docs/38_ERROR_HANDLING_STANDARD.md) – Exception classes and retry multipliers.
- [39_OBSERVABILITY_STANDARD.md](file:///e:/jarvis/docs/39_OBSERVABILITY_STANDARD.md) – Heartbeats, metric collections, and spans.
- [40_PERFORMANCE_STANDARD.md](file:///e:/jarvis/docs/40_PERFORMANCE_STANDARD.md) – Latency bounds and timeout thresholds.

### Wave 5: Testing & Pipeline Standards (Files 41-50)
- [41_TESTING_STANDARD.md](file:///e:/jarvis/docs/41_TESTING_STANDARD.md) – Coverage targets, mocks, and TDD checks.
- [42_CI_CD_STANDARD.md](file:///e:/jarvis/docs/42_CI_CD_STANDARD.md) – GitHub Actions pipelines and checks.
- [43_DEPLOYMENT_STANDARD.md](file:///e:/jarvis/docs/43_DEPLOYMENT_STANDARD.md) – Compose profiles and environment targets.
- [44_GIT_WORKFLOW.md](file:///e:/jarvis/docs/44_GIT_WORKFLOW.md) – Conventional commits and PR templates.
- [45_BRANCHING_STRATEGY.md](file:///e:/jarvis/docs/45_BRANCHING_STRATEGY.md) – Feature namespaces and branch protections.
- [46_RELEASE_POLICY.md](file:///e:/jarvis/docs/46_RELEASE_POLICY.md) – Version tags and changelog models.
- [47_QUALITY_GATES.md](file:///e:/jarvis/docs/47_QUALITY_GATES.md) – Checklists before PR merging is approved.
- [48_FAILSAFE_AND_ROLLBACK.md](file:///e:/jarvis/docs/48_FAILSAFE_AND_ROLLBACK.md) – Safe, Recovery, and Emergency Stop states.
- [49_BUILD_PIPELINE.md](file:///e:/jarvis/docs/49_BUILD_PIPELINE.md) – Compilation targets and binary packages.
- [50_FEATURE_TEMPLATE.md](file:///e:/jarvis/docs/50_FEATURE_TEMPLATE.md) – Standard layout for proposing new features.

### Wave 6: Templates & Roadmap (Files 51-60)
- [51_MODULE_TEMPLATE.md](file:///e:/jarvis/docs/51_MODULE_TEMPLATE.md) – Skeletons for FastAPI files and React components.
- [52_TASK_TEMPLATE.md](file:///e:/jarvis/docs/52_TASK_TEMPLATE.md) – Standard checklist layouts.
- [53_DOCUMENTATION_TEMPLATE.md](file:///e:/jarvis/docs/53_DOCUMENTATION_TEMPLATE.md) – Specification document template.
- [54_CODE_REVIEW_TEMPLATE.md](file:///e:/jarvis/docs/54_CODE_REVIEW_TEMPLATE.md) – Code review audits.
- [55_RISK_REGISTER.md](file:///e:/jarvis/docs/55_RISK_REGISTER.md) – Security vulnerabilities and cost risk mitigation matrix.
- [56_DEFINITION_OF_DONE.md](file:///e:/jarvis/docs/56_DEFINITION_OF_DONE.md) – Release checklists.
- [57_IMPLEMENTATION_ROADMAP.md](file:///e:/jarvis/docs/57_IMPLEMENTATION_ROADMAP.md) – Phase 1 to 10 roadmap milestones.
- [58_PHASE_BUILD_ORDER.md](file:///e:/jarvis/docs/58_PHASE_BUILD_ORDER.md) – Build sequence order.
- [59_PROJECT_GLOSSARY.md](file:///e:/jarvis/docs/59_PROJECT_GLOSSARY.md) – Core definitions.
- [60_MASTER_INDEX.md](file:///e:/jarvis/docs/60_MASTER_INDEX.md) – Clickable documentation map.

### Wave 7: Lifecycle, System & Health (Files 61-73)
- [61_RUNTIME_STATE_MACHINE.md](file:///e:/jarvis/docs/61_RUNTIME_STATE_MACHINE.md) – State machine.
- [62_INTER_AGENT_MESSAGE_PROTOCOL.md](file:///e:/jarvis/docs/62_INTER_AGENT_MESSAGE_PROTOCOL.md) – Subagent message schemas.
- [63_GLOBAL_EVENT_BUS.md](file:///e:/jarvis/docs/63_GLOBAL_EVENT_BUS.md) – Event bus topic definitions.
- [64_RESOURCE_MANAGER.md](file:///e:/jarvis/docs/64_RESOURCE_MANAGER.md) – Container resource quotas.
- [65_COST_GOVERNOR.md](file:///e:/jarvis/docs/65_COST_GOVERNOR.md) – Cloud spending calculations.
- [66_CONTEXT_COMPRESSION_POLICY.md](file:///e:/jarvis/docs/66_CONTEXT_COMPRESSION_POLICY.md) – Semantic pruning.
- [67_MODEL_CAPABILITY_MATRIX.md](file:///e:/jarvis/docs/67_MODEL_CAPABILITY_MATRIX.md) – Routing rules.
- [68_PLUGIN_TRUST_POLICY.md](file:///e:/jarvis/docs/68_PLUGIN_TRUST_POLICY.md) – Skill verification.
- [69_SYSTEM_DEPENDENCY_GRAPH.md](file:///e:/jarvis/docs/69_SYSTEM_DEPENDENCY_GRAPH.md) – Module mappings.
- [70_BOOT_SEQUENCE.md](file:///e:/jarvis/docs/70_BOOT_SEQUENCE.md) – Startup steps.
- [71_SHUTDOWN_SEQUENCE.md](file:///e:/jarvis/docs/71_SHUTDOWN_SEQUENCE.md) – Poweroff steps.
- [72_RECOVERY_MODE.md](file:///e:/jarvis/docs/72_RECOVERY_MODE.md) – Restore systems.
- [73_HEALTH_MONITORING.md](file:///e:/jarvis/docs/73_HEALTH_MONITORING.md) – Ping monitors.
- [74_PHASE_1_12_MASTER_SPECIFICATION.md](file:///e:/jarvis/docs/74_PHASE_1_12_MASTER_SPECIFICATION.md) – Consolidated Phase 1–12 master spec. **STATUS: FROZEN**
- [75_PHASE_13_MASTER_SPECIFICATION.md](file:///e:/jarvis/docs/75_PHASE_13_MASTER_SPECIFICATION.md) – Phase 13 Tool Ecosystem & Workflow Automation spec. **STATUS: FROZEN**
- [76_PHASE_14_API_GATEWAY_SPECIFICATION.md](file:///e:/jarvis/docs/76_PHASE_14_API_GATEWAY_SPECIFICATION.md) – Phase 14 API Gateway Layer spec. **STATUS: FROZEN**
- [77_PHASE_15_PERSISTENT_EXECUTION_SPECIFICATION.md](file:///e:/jarvis/docs/77_PHASE_15_PERSISTENT_EXECUTION_SPECIFICATION.md) – Phase 15 Persistent Execution & Run Management spec. **STATUS: FROZEN**
- [78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md](file:///e:/jarvis/docs/78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md) – Phase 17 Authentication, Authorization & API Security spec. **STATUS: FROZEN**
- [79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md](file:///e:/jarvis/docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md) – Phase 18 Dynamic Skill Framework spec. **STATUS: FROZEN**
- [80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md](file:///e:/jarvis/docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md) – Phase 19 Real Memory Architecture spec. **STATUS: FROZEN**
- [81_PHASE_19_IMPLEMENTATION_PLAN.md](file:///e:/jarvis/docs/81_PHASE_19_IMPLEMENTATION_PLAN.md) – Phase 19 Real Memory Architecture implementation plan. **STATUS: FROZEN**
- [86_PHASE_25_BROWSER_RUNTIME_SPECIFICATION.md](file:///e:/jarvis/docs/86_PHASE_25_BROWSER_RUNTIME_SPECIFICATION.md) – Phase 25 Browser Runtime & Execution Journal spec. **STATUS: FROZEN**
- [87_PHASE_26_MULTI_AGENT_PERSISTENT_RECOVERY_SPECIFICATION.md](file:///e:/jarvis/docs/87_PHASE_26_MULTI_AGENT_PERSISTENT_RECOVERY_SPECIFICATION.md) – Phase 26 Multi-Agent Runtime & Persistent Session Recovery spec. **STATUS: FROZEN**
- [88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md](file:///e:/jarvis/docs/88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md) – Phase 27 Observability, Cost Governance & Live Execution Streaming spec. **STATUS: FROZEN**
- [90_PHASE_28_SECURITY_VAULT_HARDENING_SPECIFICATION.md](file:///e:/jarvis/docs/90_PHASE_28_SECURITY_VAULT_HARDENING_SPECIFICATION.md) – Phase 28 Security & Vault Hardening spec. **STATUS: FROZEN**
- [91_PHASE_29_ADVANCED_VAULT_OPERATIONS_SPECIFICATION.md](file:///e:/jarvis/docs/91_PHASE_29_ADVANCED_VAULT_OPERATIONS_SPECIFICATION.md) – Phase 29 Advanced Vault Operations spec. **STATUS: FROZEN**
- [92_PHASE_30_CLOUD_SYNC_HIGH_AVAILABILITY_SPECIFICATION.md](file:///e:/jarvis/docs/92_PHASE_30_CLOUD_SYNC_HIGH_AVAILABILITY_SPECIFICATION.md) – Phase 30 Cloud Sync & High Availability spec. **STATUS: FROZEN**
- [93_PHASE_31_FEDERATION_SPECIFICATION.md](file:///e:/jarvis/docs/93_PHASE_31_FEDERATION_SPECIFICATION.md) – Phase 31 Platform Scale & Federation spec. **STATUS: FROZEN**
- [94_PHASE_32_ADMINISTRATION_OPERATIONS_SPECIFICATION.md](file:///e:/jarvis/docs/94_PHASE_32_ADMINISTRATION_OPERATIONS_SPECIFICATION.md) – Phase 32 Platform Administration & Operations spec. **STATUS: FROZEN**
- [95_PHASE_33_PRODUCTION_READINESS_SPECIFICATION.md](file:///e:/jarvis/docs/95_PHASE_33_PRODUCTION_READINESS_SPECIFICATION.md) – Phase 33 Enterprise Deployment & Production Readiness spec. **STATUS: FROZEN**
- [96_PHASE_34_AUTONOMOUS_AGENT_MISSION_SPECIFICATION.md](file:///e:/jarvis/docs/96_PHASE_34_AUTONOMOUS_AGENT_MISSION_SPECIFICATION.md) – Phase 34 Autonomous Mission Engine spec. **STATUS: FROZEN**
- [97_PHASE_35_DISTRIBUTED_SCALE_SPECIFICATION.md](file:///e:/jarvis/docs/97_PHASE_35_DISTRIBUTED_SCALE_SPECIFICATION.md) – Phase 35 Distributed Compute & Task Offloading spec. **STATUS: FROZEN**
- [98_PHASE_36_SWARM_INTELLIGENCE_SPECIFICATION.md](file:///e:/jarvis/docs/98_PHASE_36_SWARM_INTELLIGENCE_SPECIFICATION.md) – Phase 36 Swarm Intelligence & Consensus spec. **STATUS: FROZEN**
- [99_PHASE_37_BRAIN_KERNEL_SPECIFICATION.md](file:///e:/jarvis/docs/99_PHASE_37_BRAIN_KERNEL_SPECIFICATION.md) – Phase 37 Brain Kernel & Neural Intelligence Layer spec. **STATUS: FROZEN**
- [100_PHASE_38_UNIFIED_MEMORY_SPECIFICATION.md](file:///e:/jarvis/docs/100_PHASE_38_UNIFIED_MEMORY_SPECIFICATION.md) – Phase 38 Unified Memory & Knowledge Graph spec. **STATUS: FROZEN**
- [101_PHASE_39_WORKFLOW_GRAPH_ENGINE_SPECIFICATION.md](file:///e:/jarvis/docs/101_PHASE_39_WORKFLOW_GRAPH_ENGINE_SPECIFICATION.md) – Phase 39 Workflow Graph Engine & Autonomous Workflow Runtime spec. **STATUS: FROZEN**
- [102_PHASE_40_EVENT_BUS_REACTIVE_ARCHITECTURE_SPECIFICATION.md](file:///e:/jarvis/docs/102_PHASE_40_EVENT_BUS_REACTIVE_ARCHITECTURE_SPECIFICATION.md) – Phase 40 Event Bus & Reactive Architecture spec. **STATUS: FROZEN**
- [103_PHASE_41_CAPABILITY_REGISTRY_SPECIFICATION.md](file:///e:/jarvis/docs/103_PHASE_41_CAPABILITY_REGISTRY_SPECIFICATION.md) – Phase 41 Capability Registry & Skill Runtime spec. **STATUS: FROZEN**
- [104_PHASE_42_IDENTITY_ENGINE_SPECIFICATION.md](file:///e:/jarvis/docs/104_PHASE_42_IDENTITY_ENGINE_SPECIFICATION.md) – Phase 42 Identity Engine spec. **STATUS: FROZEN**
- [105_PHASE_43_GOAL_ENGINE_SPECIFICATION.md](file:///e:/jarvis/docs/105_PHASE_43_GOAL_ENGINE_SPECIFICATION.md) – Phase 43 Goal Engine spec. **STATUS: FROZEN**
- [106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md](file:///e:/jarvis/docs/106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md) – Phase 44 Mission & Autonomous Goal Scheduler spec. **STATUS: DRAFT**

## Responsibilities
- **Documentation Agent:** Manages links updates in this index after compiling documentation files.
- **Reviewer Agent:** Blocks PR merges if links in this index are broken.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Navigational index.

## Examples
- **Correct Index Action:** Clicking on [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) immediately loads the target file contents.
- **Incorrect Index Action:** Renaming a document file in `docs/` without updating the matching index URL link here. (Creates broken links).

## Failure Cases
- **Broken References:** A renamed file leaves a dead link in the index. *Mitigation:* The link validation task checks all URL paths in the index file during every validation wave.

## Security Considerations
- The index does not contain links to system logs, secret files, or external configurations.

## Future Extension
- Modifying the index file maps new files created during future phases.

## Canonical Entry Point

All automated coding agents (Cursor, Claude Code, Codex, Gemini CLI, GLM, Zed, etc.) MUST begin every session by reading the repository-root entry point:

- [AGENTS.md](file:///e:/jarvis/AGENTS.md) — canonical agent entry-point (authority ranking, mandatory boot sequence, STOP protocol, implementation lifecycle).

Do **not** load documentation directly without first following the **AGENTS.md Boot Sequence**. AGENTS.md governs how and when each document in this index is consulted, and declares which source wins when two documents conflict.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [53_DOCUMENTATION_TEMPLATE.md](file:///e:/jarvis/docs/53_DOCUMENTATION_TEMPLATE.md)
