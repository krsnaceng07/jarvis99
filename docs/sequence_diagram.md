# JARVIS OS — Mission Execution Sequence Diagram

**Version:** v0.9.0-rc1  
**Date:** 2026-07-08

## Full Mission Lifecycle

```mermaid
sequenceDiagram
    participant U as User
    participant BK as BrainKernel
    participant MO as MemoryOrchestrator
    participant MM as MissionManager
    participant PP as ParallelPlanner
    participant RA as RoleAssigner
    participant SV as Supervisor
    participant SO as SwarmOrchestrator
    participant A1 as Agent A
    participant A2 as Agent B
    participant A3 as Agent C
    participant TD as ToolDispatcher
    participant RE as RepairEngine
    participant CR as ConflictResolver
    participant RM as ResultMerger
    participant RF as ReflectionEngine

    U->>BK: Submit Goal
    activate BK

    Note over BK: OUR-PDE-RL Cognitive Loop
    BK->>BK: Observe → Understand → Reason

    rect rgb(230, 245, 255)
        Note over BK,MO: Phase 1: Memory Recall
        BK->>MO: recall(RetrievalRequest)
        MO->>MO: vector search + scoring
        MO-->>BK: RetrievalResponse(chunks)
    end

    BK->>BK: Plan → Decide
    BK->>MM: create_mission(goal)
    activate MM

    rect rgb(255, 245, 230)
        Note over MM,MO: Phase 2: Mission Planning
        MM->>MO: recall(goal, max_chunks=10)
        MO-->>MM: memory context
        MM->>MM: _decompose_goal(goal + memory)
        Note over MM: LLM decomposes → steps[]
    end

    MM->>MM: start_mission(mission_id)
    MM->>MM: append_timeline(CREATED → PLANNING → RUNNING)

    rect rgb(230, 255, 230)
        Note over MM,SV: Phase 3: Parallel Wave Planning
        MM->>PP: plan_parallel(steps)
        PP->>PP: dependency analysis
        PP-->>MM: ParallelPlan(waves[])

        loop For each ExecutionWave
            MM->>RA: assign_roles_to_wave(wave.steps)
            RA->>RA: keyword → role mapping
            RA-->>MM: RoleAssignment[]

            par Register agents with Supervisor
                MM->>SV: register_agent_task(agent_a, task, wave_idx)
                MM->>SV: register_agent_task(agent_b, task, wave_idx)
                MM->>SV: register_agent_task(agent_c, task, wave_idx)
            end
        end
    end

    rect rgb(255, 230, 255)
        Note over MM,RE: Phase 4: Parallel Execution
        par Spawn agents concurrently
            MM->>SO: spawn_task(task_a)
            activate SO
            SO->>A1: execute
            activate A1
            A1->>TD: dispatch(task, context)
            TD->>TD: executor.execute()
            alt Success
                TD-->>A1: ToolExecutionResult(SUCCESS)
            else Failure
                TD->>RE: attempt_repair(task, result)
                activate RE
                RE->>RE: classify → diagnose → plan
                RE->>RE: retry with strategies
                RE->>RE: learn → cache result
                RE-->>TD: RepairOutcome
                deactivate RE
            end
            A1-->>SO: AgentOutput
            deactivate A1
            SO-->>MM: result_a

        and
            MM->>SO: spawn_task(task_b)
            SO->>A2: execute
            activate A2
            A2->>TD: dispatch(task, context)
            A2-->>SO: AgentOutput
            deactivate A2
            SO-->>MM: result_b

        and
            MM->>SO: spawn_task(task_c)
            SO->>A3: execute
            activate A3
            A3->>TD: dispatch(task, context)
            A3-->>SO: AgentOutput
            deactivate A3
            SO-->>MM: result_c
        end
        deactivate SO
    end

    rect rgb(255, 255, 220)
        Note over MM,RM: Phase 5: Conflict Resolution & Merging
        MM->>SV: report_task_complete(agent_id, success)
        SV->>SV: is_wave_complete?

        MM->>CR: detect_conflicts(agent_outputs)
        CR->>CR: technology/approach conflict scan
        CR-->>MM: Conflict[] (if any)

        MM->>RM: merge_wave_results(outputs, wave_idx)
        RM->>RM: concatenate + synthesize
        RM-->>MM: MergedResult
    end

    Note over MM: Repeat for next wave...

    rect rgb(240, 240, 240)
        Note over MM,MO: Phase 6: Completion & Reflection
        MM->>RM: merge_mission_results(all_wave_results)
        RM-->>MM: final MergedResult

        MM->>MM: _mark_mission_completed()
        MM->>MM: append_timeline(COMPLETED)
        MM->>MM: create_checkpoint(final_state)
    end

    MM-->>BK: mission result
    deactivate MM

    BK->>BK: Reflect → Learn
    BK->>RF: analyze execution
    RF-->>BK: reflection insights

    BK->>MO: store(execution_memory)
    MO->>MO: consolidation cycle

    BK-->>U: Response
    deactivate BK
```

## Budget Gate Flow (Sequential Path)

```mermaid
sequenceDiagram
    participant MM as MissionManager
    participant DB as Database
    participant U as User

    MM->>MM: execute step (cost=5.0)
    MM->>DB: update spent_budget

    MM->>MM: check next step (cost=50.0)
    MM->>MM: spent + step_cost > budget_limit?

    alt Over Budget
        MM->>DB: status = WAITING_APPROVAL
        MM->>MM: append_timeline(WAITING_APPROVAL)
        MM-->>U: "Budget exceeded — approve?"
        U->>MM: approve / reject
        alt Approved
            MM->>DB: status = RUNNING
            MM->>MM: continue execution
        else Rejected
            MM->>DB: status = CANCELLED
        end
    else Within Budget
        MM->>MM: continue execution
    end
```

## Crash Recovery Flow

```mermaid
sequenceDiagram
    participant K as Kernel
    participant MM as MissionManager
    participant DB as Database
    participant SO as SwarmOrchestrator

    Note over K: Process restart

    K->>K: boot() — all phases
    K->>MM: initialize()
    MM->>DB: load interrupted missions

    loop For each RUNNING mission
        MM->>DB: find last checkpoint
        MM->>MM: rollback_to_checkpoint()
        MM->>SO: re-spawn from checkpoint step
        Note over MM: Resume execution
    end
```

## Component Legend

| Symbol | Component | File |
|--------|-----------|------|
| BK | BrainKernel | `core/runtime/brain_kernel.py` |
| MO | MemoryOrchestrator | `core/memory/orchestrator.py` |
| MM | MissionManager | `core/runtime/mission.py` |
| PP | ParallelPlanner | `core/runtime/parallel_planner.py` |
| RA | RoleAssigner | `core/runtime/role_assigner.py` |
| SV | Supervisor | `core/runtime/supervisor.py` |
| SO | SwarmOrchestrator | `core/runtime/orchestrator.py` |
| TD | ToolDispatcher | `core/reasoning/dispatcher.py` |
| RE | RepairEngine | `core/reasoning/repair_engine.py` |
| CR | ConflictResolver | `core/runtime/conflict_resolver.py` |
| RM | ResultMerger | `core/runtime/result_merger.py` |
| RF | ReflectionEngine | `core/reasoning/reflection.py` |
