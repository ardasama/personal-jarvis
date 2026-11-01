# MANTRA persistence verification — 2026-10-17

## Scope and ownership

Existing AIHub root MANTRA.md is the single shared methodology authority. Its
additive Persistence protocol v2.0 section preserves the existing AIHub-specific
executor contract and each recipient's own AGENTS.md. Small references were
added to the four existing root AGENTS.md files: Jarvis, AIHub, AI-AgentsforHub
and ProjectOracle. No policy was installed globally and no new skill, runtime,
memory store, scheduler or orchestrator was created.

All four repositories had pre-existing changes. The AIHub MANTRA and Oracle
MANTRA files were already untracked. No other writer's changes were staged,
reset, deleted or incorporated as this task's work. Existing Agent Bus board
reported TASK-0002/3/4 proposed, with no execution evidence; these are not done.

## Independent discovery result

A fresh-context read-only reviewer started from Jarvis AGENTS.md and followed
the references without receiving the answers. All eight criteria were found:

| Criterion | Evidence source |
|---|---|
| Primary product | Jarvis AGENTS.md, MANTRA project continuity |
| Governance owner | AIHub AGENTS.md and MANTRA.md |
| Specialist versus planning ownership | AI-AgentsforHub AGENTS.md; Oracle AGENTS.md |
| Single methodology | AIHub MANTRA.md, Persistence protocol v2.0 |
| Research and verification skills | AIHub skills/registry.json and actual enabled skill files |
| No unnecessary code or duplicate systems | MANTRA reuse and persistence sections; Jarvis lineage rules |
| Data and cost protection | MANTRA authority/recovery rules; Jarvis AGENTS.md cost rules |
| Current checkpoint | ASLAN-JIKU-JARVIS-20261017.md plus current dirty source and tests |

Reviewer found no blocking contradiction in the new paragraphs. Research and
verification reuse covers system-design, release-radar, security-review,
gpt-opencode-control, testing-strategy, gpt-opencode-review and
gpt-opencode-memory. Existing ASLAN quality_gate.py retains quality ownership.
No missing procedure justified a duplicate skill.

This proves independent static discovery, NOT a fresh Codex CLI auto-loading
test. The [official instruction-discovery documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
was fetched: discovery follows the project-root-to-working-directory chain;
sibling writable roots are not automatically included. No global instruction
file or project_doc override was found in the inspected standard configuration.
Client-specific hidden context and future sessions remain unverified.

## Engineering continuation and exact results

The previous checkpoint was checked against source at HEAD
73b7783ae60ea071983ae005263c8b93f45f08fa, branch
agent/mcp-registry-active-names, with pre-existing dirty source/tests.
The opt-in vision route, protected configuration fields, OpenCode variant
handling and screen-intent changes remain local work, not this task's code.

- Required virtual-environment Python could not import pytest. No install made.
- Global Python with process-local PYTHONPATH pointing at the existing project
  environment ran the six checkpoint suites. First attempt: 822 passed and
  seven setup errors from the sandbox temporary-directory permissions.
- A retry with a unique writable basetemp stalled in subprocess pump tests
  and was interrupted. It has no passing-suite verdict.
- Bounded offline subset: **823 passed, six subprocess tests deselected, one
  warning**, exit 0. Files: test_intent.py, test_ide_cli_seats.py,
  test_vision_lead_chain.py, test_schema_introspect.py, test_registry.py,
  test_risk_tier.py. Arguments: `python -B -m pytest <files> -q
  --confcutdir=tests/unit -p no:cacheprovider --basetemp <unique writable path>
  --tb=short`, excluding the six subprocess pump tests. Deselection limits
  evidence; it does not satisfy the full checkpoint gate.
- Existing scheduler automation suite: **three passed, ten setup errors**,
  exit 1. Missing pytest-asyncio prevents async fixture execution. This does
  not prove scheduler regression or successful completion of TASK-0003.
- A pyreadline console-finalizer error appeared after global pytest output;
  it did not change the successful offline subset's exit code.
- Scoped `git diff --check` passed in all four repositories.
- ContinuityVault audit returned ok with zero conflicts, but maintenance
  failed with `vault-not-initialized` in this execution environment. Audit
  alone is not proof of an initialized vault, snapshot or restore. No new
  vault or recovery system was created.

No production source changed, no paid model/API probe ran, and no live app,
provider, vision or cross-platform acceptance was claimed. Failures are
environment observations, not exact-base regression classifications.

## Next bounded milestone

Use the existing project priorities and native finite Goal. First establish
an authorized test environment with pytest/pytest-asyncio, then rerun the
complete focused suites and scheduler invariants. Preserve all existing dirty
patches and independently review them before landing.

The next security design gap is current and source-backed:
jarvis/society/coding_threads.py opens agent-owned CLI sessions with full/bypass
access. Existing runner sandbox modes and mission worktree isolation are reuse
candidates, not proof of a cross-provider no-delete boundary. Do not change the
documented default bypass behavior merely to make a smoke test green. A scoped
design and adversarial filesystem proof must precede untrusted autonomous
self-development. No safe minimal runtime patch was established in this audit.

Repository instructions and the existing checkpoint are durable local files;
untracked shared authority documents and pre-existing edits still require their
owners' reviewed integration before Git-only recovery can be claimed.
