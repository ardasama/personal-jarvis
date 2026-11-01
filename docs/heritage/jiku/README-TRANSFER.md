# JIKU historical source — non-executable archive and transfer index

**Date:** 2026-10-17. **Recipient:** the existing Personal Jarvis/Dodaios source at <USER_HOME>\.personal-jarvis.
**Source:** C:\AI\Jiku, historical Git repository, HEAD 7ebaf3b7c9f5ded41f2654c299a7fca7b27e5cd0 (2026-03-08).

Jiku was an earlier project/prototype as well as a later **development name for Personal Jarvis**. Do not accidentally create a third Jarvis/AI OS based on this archive.

## Local archive files

- JIKU_GIT_HEAD_20260308.zip — **complete HEAD snapshot** of historical Git-tracked Jiku source files (35 ZIP entries including directories, 24 Python modules).
- JIKU_GIT_HISTORY.bundle — **complete Git history** including the master branch at the HEAD named above. Git bundle verification succeeded.
- JIKU_AUTONOMOUS_EVOLUTION_DIRECTIVE_20261015.txt — 416-line Jiku evolution directive from the user's ChatGPT Library, recording subsequent October 2026 goals and OpenCode development guidance.
- JARVIS_HOLDING_ARCHITECTURE_HISTORICAL_NOTE.txt — 342-line older Windows AI OS / multi-agent holding proposal; ideas only, **not** an approved implementation stack.
- JIKU_JARVIS_MODEL_ECOSYSTEM_HISTORICAL_CONVERSATION.txt — 587-line historical model/provider/project discussion; model names, free-tier claims and API prices must be reverified.
- verify_legacy_snapshot.py — safe **AST-only** syntax check of Python files in the ZIP; does not import/run Jiku source and does not install dependencies.

These artifacts are intentionally excluded from source control by the local .gitignore. The original Jiku working tree currently shows deleted tracked files. No reset, checkout, restore, deletion or modification of that working tree was performed during this transfer. The untracked item named "nul" was also not touched.

## What this archive establishes

Historical Jiku contained central JikuCore orchestration, a second kernel/task scheduler, concept-graph memory with semantic retrieval, multi-agent message queues and specialists, autonomous evolution engine, self-evaluation metrics, and CLI/Brain interfaces. Its historical dependencies and assumptions are **not** proof that the code is compatible with current Personal Jarvis.

The snapshot's 24 Python files parsed successfully as Python syntax. **AST parse does not prove runtime correctness, integration, security, compatibility, unit tests, or functionality.**

## How to continue

Read docs/handoffs/JIKU_INTEGRATION_20261017.md first. Then inspect current Jarvis AGENTS.md, docs/SINGLE-SOURCE-OF-TRUTH.md, tests and actual code. Use the archive selectively for ideas, contract behavior and tests; never load Jiku's redundant kernel/evolution loop into the live Jarvis process.

MORPHY provenance is separately archived under docs/heritage/morphy/ and mapped in docs/handoffs/MORPHY_INTEGRATION_20261017.md.

### Privacy and security

The ZIP and bundle potentially preserve old developer-specific history, data, model settings or personal material. Treat as private. Do not commit, upload to public CI or expose without dedicated secret/license review. Passwords and API keys must never be imported to new Jarvis state. The old direct self-modification implementation must not be executed in production.
