# JIKU → PERSONAL JARVIS — LEGACY PROJECT MERGE RECORD
**Date:** 2026-10-17
**Status:** historical **full committed source + Git history preserved**, requirements/architecture ported as a reviewed integration map; **NO runtime code merge or activation claimed**.
**Companion:** MORPHY_INTEGRATION_20261017.md and docs/heritage/morphy/README-TRANSFER.md

## 1. Identity, sources, authority and the critical distinction

There are **two uses of "Jiku"** in the user's project history:

1. **March 2026 original Jiku agent prototype**, real Git repo at C:\AI\Jiku, last HEAD 7ebaf3b7 (2026-03-08). It had JikuCore, JikuKernel, JikuBrain, JikuMemory V2/V3, ConceptGraph, agents, message queue, EvolutionEngine, SelfEvaluator and tests.
2. **October 2026 Jiku/Jiku-Jarvis development initiative**, which improves the **existing Personal Jarvis / Dodaios**. The actual existing Jarvis codebase is <USER_HOME>\.personal-jarvis. C:\AI\Jiku is NOT the recipient's live app source and must not be scaffolded into a replacement application.

The recipient's existing `AGENTS.md`, `docs/SINGLE-SOURCE-OF-TRUTH.md`, `docs/architecture-overview.md`, current code, tests and the user's actual authority are binding. Historical Jiku directives or obsolete paths never override this.

Current Jarvis maintains cross-platform/cloud-first compatibility, one uninterrupted voice/chat UX, routing to the existing mission/worker/critic architecture, safe model/provider selection and optional local acceleration. Respect its specific isolation, data and cost rules.

## 2. What was physically migrated (read-only donor, additive recipient)

Original worktree: C:\AI\Jiku. At inspection `git status` showed approximately 28 tracked paths marked DELETED, plus an untracked `nul`. **Do not infer deletion meant intended removal or user authorization to recover/rebuild it. No checkout/reset/restore/clean occurred.**

Historical commits:
- `7ebaf3b` — upgrade to concept-graph memory (HEAD)
- `23b23a4` — central JikuCore
- `e40ad68` — multi-agent Jiku kernel
- `e44b603` — autonomous evolution engine
- `ce74f7a` — semantic search examples/guide

Private archive under `docs/heritage/jiku/`:
- `JIKU_GIT_HEAD_20260308.zip` — Git HEAD archive, 35 entries including dirs, 24 Python files (actual 183659-byte ZIP at creation).
- `JIKU_GIT_HISTORY.bundle` — full historical Git graph, 183203 bytes at creation; bundle verified, master and HEAD both 7ebaf3b7c9f5ded41f2654c299a7fca7b27e5cd0.
- `JIKU_AUTONOMOUS_EVOLUTION_DIRECTIVE_20261015.txt` — 416-line October-era Jiku/OpenCode development plan from ChatGPT Library.
- `JARVIS_HOLDING_ARCHITECTURE_HISTORICAL_NOTE.txt` — 342-line AI OS holding research; historical, not an approved Windows-first stack.
- `JIKU_JARVIS_MODEL_ECOSYSTEM_HISTORICAL_CONVERSATION.txt` — 587-line model/agency planning discussion; free-tier, provider and price claims require current verification.
- `verify_legacy_snapshot.py` — nonexecuting AST reader.

**Syntax validation:** AST parsed all 24 Python modules successfully: `PYTHON=24 AST_PASSED=24 FAILED=0`. This is NOT a runtime, regression or compatibility test.

The archive contains potentially old sensitive/developer state: protected by `docs/heritage/jiku/.gitignore`. Only this reviewed handoff and the index README are meant to be candidates for Git tracking; no commits or pushes were made.

## 3. Permanent NORTH STAR: Jiku + MORPHY integrated, not stacked runtimes

Build a SINGLE durable Personal Jarvis cognitive/action system, not three agents in separate folders. The intended outcome is to turn broad human intent into **authorized, real, independently verified results** over long-running projects, retaining useful memory and context, using existing apps/tools, managing cost/latency/privacy and safely learning from observations.

The path is:
`USER GOAL → INTENT/CONSTRAINTS → STRATEGY → PROJECT/TASKS → TOOL/WORKER CHOICE → PERMISSION GATE → EXECUTE → OBSERVE → VERIFY → CHECKPOINT → LEARN → NEXT ACTION`.

Never equate an attractive UI, more code, more tools, more models or more agents with reliable goal completion. Validate objective quality, regression rate, safety, cost and user attention. **No "1000×" promise without measurements.**

The October Jiku directive's requirement to act on the REAL app, not produce plans alone, remains valuable, but must operate under current repository safety controls and independent tests. Its old `C:\AI\Jiku` working directory assumption is superseded, as is any unconditional prohibition on local models: current Jarvis supports optional Ollama use and must preserve explicit privacy/provider routing preferences rather than mandate local or cloud use.

## 4. Original Jiku modules: comprehensive crosswalk and recommendation

| Original Git path/component | Donor value | Present Jarvis primitive to examine | Decision |
|---|---|---|---|
| `Jiku_Core/core/jiku_core.py` (1089 lines) | unified lifecycle, registry, task state, heartbeat, error tracking | mission manager, bootstrap, EventBus, Agent Chat | **REUSE Jarvis; do not import second coordinator** |
| `Jiku_Core/jiku_kernel.py` (1313 lines) | priority queue, resource allocation, module loading, health | missions capacity, scheduler, worker lifecycle, health | review fairness/priority/resource budgeting only |
| `Jiku_Core/jiku_brain_v2.py` | cognition/semantic recall | Brain Router + memory/recall | compare only missing testable behavior |
| `Jiku_Core/jiku_cli.py`, `jiku_start.py`, `core/jiku_core.py` | CLI/start pathway | Jarvis CLI, agent_chat, OpenCode runner | use native; avoid side-effectful imports |
| `Jiku_Core/jiku_memory_v2.py` | semantic/episodic recall | `jarvis/memory/semantic.py`, Wiki | reuse; measure retrieval quality |
| `Jiku_Core/memory/concept_graph.py` (1154 lines) | typed edges, provenance, graph neighborhood, concept/prerequisite links | Wiki wikilinks, semantic recall, project knowledge | **candidate unique legacy insight**; implement only if real use case & tests show gap |
| `Jiku_Core/memory/jiku_memory_v3.py` (854 lines) | combined graph + episodic/semantic + embeddings | existing Wiki/core memory/storage | do not add NumPy/sentence-transformers as mandatory, no second DB |
| `Jiku_Core/multi_agent/message_queue.py` (429 lines) | message priority/topic/TTL/requests | mission event bus, worker/task queues | review queue priority/TTL/idempotency, not parallel bus |
| `Jiku_Core/multi_agent/{agent_base,coder_agent,memory_agent,planner_agent,research_agent,jiku_core}.py` | specialist boundary, planning, result routing | existing Jarvis spawn-worker, Agentic IDE, skills, CLI workers | use template/contract ideas, not fixed agents |
| `Jiku_Core/tools/evolution_engine.py` (951 lines) | discover bottlenecks, propose OpenCode patches, record lessons | `jarvis/core/self_mod`, Jarvis learning, missions, tests | **do not activate**; convert into gated proposal/eval workflow |
| `Jiku_Core/tools/self_evaluator.py` (437 lines) | error/success metrics, response latency, health score | Jarvis board, flight recorder, metrics, critic | reuse measurable evaluation ideas; reject unchecked automatic patch triggers |
| `Jiku_Core/test_jiku_core.py`, `test_self_evaluator.py`, `test_semantic_search.py`, `memory/test_concept_graph.py`, `multi_agent/test_multi_agent.py` | reusable behavior examples | existing Jarvis pytest suites | translate test *contracts* once scoped; do not execute legacy effects blindly |
| `SEMANTIC_SEARCH_GUIDE.md` and `examples/semantic_search_demo.py` | usage semantics, top-k similarity and concept linking | Wiki search/semantic interfaces | reference for acceptance criteria |
| `jiku_evolution_history.json` | historical evolution log | Jarvis event/flight recorder | retain private; never import as verified success or public telemetry |

The originally committed Jiku project as a whole is in the ZIP/bundle even where individual modules are not itemized above. This table maps every major functional family, not every method. No claim of 100% method-level behavior equivalence.

## 5. Unique Jiku features worth serious review (not already proven missing)

### A. Typed semantic/concept relationship graph
Donor graph exposes nodes `CONCEPT`, `EVENT`, `SKILL`, `USER`, `GOAL`, `TASK`, `RELATIONSHIP`; edges include `RELATED_TO`, `CAUSED_BY`, `LEARNED_FROM`, `USED_IN`, `PREREQUISITE_FOR`, `SIMILAR_TO`, `OPPOSITE_OF`, `EXAMPLE_OF`.
- Test whether Jarvis Wiki and tasks can already retrieve useful typed relationships.
- If missing and product-relevant, define provider-neutral explicit schema/queries and migration tests using tiny fixtures; avoid requiring local embedding weights.
- Add source/provenance, certainty, revision/expiry and access-control tests before any persistent user graph.

### B. Priority/resource-budgeted orchestration
Donor supports priority tasks and resource categories. Verify whether Jarvis scheduling handles starvation, queue backpressure, cancellation, deadlines, retry jitter, concurrency, paid-provider budgets, and user attention costs. **Do not duplicate queues**.

### C. Self-evaluation and safe evolution
Donor observed error count, successes, response time, memory usage and periodically requested OpenCode patches. Carry over the objective **metrics**, but do not automatically merge or run self-generated executable code.
- Replace autonomous patch activation with `OBSERVE → HYPOTHESIS → REPRO TEST → ISOLATED CHANGE → BENCHMARK → REVIEW → PROMOTE/ROLLBACK`.
- Jarvis already has protected self-mod config and learning; test isolation of external CLI agents first.

### D. Real action gap vs conversational simulation
Historical Jiku sometimes behaved as a chat front end to DeepSeek/OpenRouter without genuine tool execution. Jarvis has existing mission/worker/action systems; maintain tests distinguishing a generated answer, a tool call, completed action and independently verified postcondition.

### E. Cloud-first vs optional local providers
The October directive preferred cloud/API-first without installing local inference. Current user's infrastructure has optional local vision and models; avoid reinstalling or forbidding them. Preserve provider-neutral routing, privacy opt-ins and no silent additional paid billing.

## 6. Concrete integration order and gates

0. **Preserve** original Jiku Git worktree unchanged; retain standalone archive and complete history for future inspection.
1. **Orient** within existing Jarvis repo: read AGENTS.md, docs/SINGLE-SOURCE-OF-TRUTH.md, architecture, latest handoffs, source and user-uncommitted diff. Do not reset or stage anyone else's work.
2. **Security**: existing Jarvis coding session bypass/external CLI permissions are not proof of a real no-delete filesystem sandbox. Before unattended autonomous self-development, verify a real workspace-level deny-delete/isolation boundary, with adversarial tests. No such live proof was produced by THIS migration.
3. **Test-driven gap audit**: classify Jiku's graph, memory, scheduling and learning contracts as EXISTING/PARTIAL/MISSING/UNNEEDED/UNKNOWN, with code path + test evidence; remember false-negative checks and restart.
4. **Small migrations only**: port unique behavior to existing `jarvis/memory/wiki`, `jarvis/missions`, or `jarvis/core/self_mod` modules; never instantiate `JikuKernel` beside the real supervisor.
5. **Compare outcomes**: use deterministic tests, cross-platform CI, check that no new paid model calls occur during tests, run `git diff --check`, update ADR and selective Git commit if authorized.
6. **Maintain continuity**: next session reads this file and MORPHY integration brief, then current code/last events before acting; never replay a previous agent's patch blindly.

## 7. Acceptance matrix: migration scope vs actual verification

| Property | Status on 2026-10-17 | Evidence |
|---|---|---|
| Original Jiku Git repository exists | VERIFIED | `git status`, `git log`, `git ls-tree` on C:\AI\Jiku |
| Current worktree marked many tracked paths deleted | VERIFIED | read-only `git status` |
| Jiku full committed Git history archived | VERIFIED | `git bundle verify` reports complete history |
| Jiku last committed source snapshot archived | VERIFIED | `git archive HEAD` zip |
| Old Jiku Python source syntax readable | VERIFIED (24/24 AST) | `verify_legacy_snapshot.py` |
| October 2026 Jiku evolution directive archived | VERIFIED | complete 416-line Library text copied |
| Jiku conceptual requirements mapped to existing Jarvis modules | DOCUMENTED | this review; behavior-level parity not measured |
| Original user/Jiku working tree recovered to code files | NOT DONE BY DESIGN | could overwrite user deletions |
| Jiku runtime embedded in Personal Jarvis | NOT DONE BY DESIGN | competing, outdated orchestration + unbounded self-mod risk |
| Feature-level Jiku/Jarvis parity | UNVERIFIED | needs tests and compatibility audit |
| Jarvis integration/regression tests rerun after this archival transfer | NOT RUN | no executable Jarvis modifications |
| Every prior ChatGPT Jiku conversation recovered byte-for-byte | UNVERIFIED | selected Library directive & prior context recovered |
| No original runtime/user data overwritten | VERIFIED within performed operations | only new recipient docs and ignored archive created |
| Jarvis processes/models/configuration changed | NO | none touched |

## 8. Future-session instruction

JIKU is both a historical standalone prototype and the user's continuing DEVELOPMENT INITIATIVE for existing PERSONAL JARVIS. No new executable "Jiku" package should be created simply from historical prompt material. Preserve and study original Jiku at C:\AI\Jiku (Git history source) and the ignored archive. For today's implementation use <USER_HOME>\.personal-jarvis. Never use the unrelated AIHub OpenCode session for Jarvis source modifications without verified target.

Read current AGENTS.md → architecture/source/tests → this JIKU handoff → MORPHY integration handoff → donor references only as needed. Apply highest-value, measured, safe unique improvements. Keep user state and existing source intact, and report ALREADY_PRESENT/PORT_CANDIDATE/NO_CHANGE rather than claiming all donor runtime behaviors migrated.

## 9. Summary

**Actual transfer**: historical Jiku *entire committed HEAD snapshot and complete Git history*, its October engineering directive, and a reusable, security-first integration/crosswalk document are now present inside the recipient's locally protected heritage folder and handoffs.

**Not asserted**: the historical Jiku applications automatically run within Personal Jarvis, that legacy dependencies are usable, or that every chat/working-tree state was copied.

**Guiding rule**: transplant durable Jiku insights into the one genuine Personal Jarvis system; do not resurrect redundant Jiku components as competing services.
