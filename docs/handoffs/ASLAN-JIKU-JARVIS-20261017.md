# ASLAN — Jiku-Jarvis engineering handoff (2026-10-17)

## Product and scope
- Real existing Personal Jarvis / Dodaios source: `<USER_HOME>\.personal-jarvis`.
- `C:\AI\Jiku` contains no app source at the time of inspection; do not scaffold a replacement.
- Separate AIHub integration workspace: `<USER_HOME>\AIHub`.
- Preserve all pre-existing untracked files and unrelated working state.
- User's stricter requirement: **never delete data or damage unrelated apps**. Treat this as an operating constraint even where upstream default permission modes are permissive.
- ChatGPT conversation title "PERSONAL JARVIS EVOLVE" was not independently retrievable in full. Prior project summaries and live source are context, not substitutes for a transcript.

## Observed baseline (read-only discovery)
- Repo branch: `agent/mcp-registry-active-names`; last observed HEAD `73b7783ae`.
- The existing Jarvis repository already contains Agentic IDE OpenCode CLI integration in `jarvis/agent_chat/runner_cli.py` and project threads; do not build an unnecessary parallel IDE.
- `tests/unit/agent_chat/test_default_permissions.py` explicitly expects default `bypass` permission mode for Jarvis sessions. This is a **safety review priority**, not proof of a working OS-level deletion blocker.
- AIHub OpenCode V2 bridge online; AIHub session `AIHUB-MAIN (fork #1)` observed idle in `<USER_HOME>\AIHub` with selected model `openrouter/nvidia/nemotron-3.5-super-vl:free`. It is NOT a Jarvis repository session. Do not send Jarvis source edits to that session without explicit correct-workspace routing.
- No OpenCode session appeared from `opencode session list --format json` in the Jarvis source root.
- The dedicated virtualenv lacks `pytest` and `ruff`; global Python has pytest but lacks `pytest_asyncio`. No dependencies were installed or changed.

## Implemented patch (not committed or released)
- `jarvis/screen_context/intent.py`: mask explicit negative screen-look clauses in English, German and Spanish before screenshot intent classification, without vetoing a separate affirmative request.
- `tests/unit/screen_context/test_intent.py`: 10 new parametrized cases (7 negative, 3 mixed negative/affirmative).
- This addresses a reproduced misclassification: "Do not access my screen. Produce a text report." was SCREEN before the patch and is NONE afterward.
- No Jarvis restart; live app behavior remains unverified until a controlled restart/test.
- No Git reset, clean, checkout, commit, push, package installation or paid model call occurred.

## Verification performed
- Direct smoke matrix: 12 / 12 cases passed with the installed Jarvis Python; covered negated requests, retained positive requests, and nonvisual model-identification questions.
- A standard-library AST reader extracted existing literal parameter fixtures from the repository test file and invoked the REAL `classify()` and `requests_screen_operation()`: 154 / 154 cases passed, 0 failed; source and test files parsed successfully.
- `git diff --check`: exit 0.
- Full pytest: BLOCKED by absent `pytest` in Jarvis venv and absent `pytest_asyncio` globally. Do not call this PASS.
- Ruff: BLOCKED by absent module in venv. Do not call this PASS.
- No GUI/live desktop verification or full integration test run.

## Next priority by leverage and risk
1. Independently review and complete the screen-intent patch; run the proper focused pytest and lint in an authorized isolated test environment. Preserve current user files and sessions.
2. Audit default `bypass` permission and actual CLI execution boundary for Jarvis-spawned OpenCode threads; implement a strong deny-delete/workspace-boundary policy only after an explicit task scope and tests. Prompt text alone is insufficient.
3. Verify the existing Jarvis Agentic IDE OpenCode runner against installed OpenCode V2 wire formats and session resume behavior. Read logs/tests, do not assume version compatibility.
4. Only then test narrow self-development missions with mocked tools, budgets fixed at zero additional paid API cost and a separately verified project session.
5. Maintain additive checkpoints and stop before breaking-version migrations.

**ASLAN UNUTMAZ** — retain original project, preserve user data, verify every milestone before increasing permissions.

## Additional OpenCode V2 compatibility finding
- The installed OpenCode CLI v2.0.28 advertises `opencode run --model provider/model#variant` but does not advertise a separate `--variant` flag. `jarvis/agent_chat/runner_cli.py::plan_opencode` appends `--variant <effort>` when effort is non-empty. This is a likely CLI compatibility defect, NOT a confirmed runtime failure because no live LLM request was made. First compare historical CLI support and existing tests, then implement version/capability-aware argument construction with offline argv tests. Do not silently change the selected model or variant.
- The live AIHub OpenCode service reports v2.0.31, while CLI reports v2.0.28. Do not upgrade or restart either automatically.

## Continuation: opt-in local vision path and verified suites (2026-10-17)

**Scope and preservation.** Changes were applied in the original Jarvis checkout, not in C:\\AI\\Jiku. No user/untracked data was deleted or reset, no running Jarvis/OpenCode processes were restarted, no dependency was installed, no model inference or paid API request was made, and no Git commit/push was performed.

**OpenCode V2 fix.** `jarvis/agent_chat/runner_cli.py` now encodes an explicit variant as `provider/model#variant`; it does not send unsupported `--variant`. Empty and conflicting model/variant choices fail closed; existing owner model selection remains intact. Targeted CLI tests added under `tests/unit/agent_chat/test_ide_cli_seats.py`.

**Screen-intent fix.** `jarvis/screen_context/intent.py` ignores explicit prohibitions such as "Do not access my screen", "Don't click anything on my screen", "Klicke nicht auf meinen Bildschirm", and "No toques mi pantalla". Positive requests still work, including "Don't forget to look at my screen" and a new affirmative clause following a prohibition. Parametrized tests added in `tests/unit/screen_context/test_intent.py`.

**Opt-in image-turn routing.** The current repository already has an Ollama provider with genuine model-specific vision capabilities. `jarvis/core/config.py::ScreenContextConfig` now declares default-empty `vision_provider` and `vision_model`. `jarvis/brain/manager.py::_lead_vision_chain` checks an explicitly configured model first on a real image turn, preserving normal router/brain behavior when the fields are empty, the model is blind, the provider is dead, or a turn/operation has its own model override. Duplicate providers are avoided. `jarvis/core/self_mod/forbidden.py` prevents agents from editing either model/provider field via self-modification, because rerouting screenshots could transmit private imagery or incur new billing. No live runtime configuration was changed. `docs/screen-context.md` documents the example of local `ollama` plus `qwen3.5:4b-8k` without enabling it.

**Observed local models.** Read-only `ollama show` and `OllamaBrain` metadata confirm `qwen3.5:4b-8k` advertises vision and tools while `deepseek-r1:8b` is text-only. Both models are installed, but GPU inference, latency, voice/chat runtime integration and vision-image quality are NOT yet live-verified. The user's working primary model/selected OpenCode model were not changed.

**Actual verification results.** A single selective combined pytest command across six relevant test files returned **829 passed, 0 failed, 1 warning** (missing optional `pytest-asyncio` config registration), in approximately 3.1 seconds:
`tests/unit/screen_context/test_intent.py`, `tests/unit/agent_chat/test_ide_cli_seats.py`, `tests/unit/brain/test_vision_lead_chain.py`, `tests/unit/self_mod/test_schema_introspect.py`, `tests/unit/self_mod/test_registry.py`, `tests/unit/test_risk_tier.py`.
Test command: process-local `PYTHONPATH=<USER_HOME>\\.personal-jarvis\\.venv\\Lib\\site-packages` and global `python -B -m pytest <files> -q --confcutdir=tests/unit -p no:cacheprovider`. No disk/environment install. Separate vision-resolver/manager suite had 6 passed and 4 tests BLOCKED because `pytest-asyncio` is absent; not a product regression. `ruff check` passes on the seven small changed files; existing `manager.py` has 30 legacy lint diagnostics but zero diagnostics within the new changed ranges. `git diff --check` succeeded.

**Security blocker.** `jarvis/society/coding_threads.py` creates agent-owned external coding CLI sessions with FULL/bypass permissions. The `run_shell` impact classifier + ask tier do not constitute a guarantee of no deletion when bypass is active, and they cannot sandbox external OpenCode subprocesses. Do NOT enable untrusted autonomous self-development on the live workspace until a real OS/workspace-isolation and no-delete boundary exists, independently tested with malicious command attempts. New vision settings being self-mod-forbidden is a separate protection, not a substitute for command isolation.

**Next high-leverage action.** Design and test a bounded, user-authorized, no-delete external CLI sandbox (or launch gate plus real filesystem isolation) for agent-owned coding threads. Independently validate the optional Ollama image-turn route through a mocked vision integration test, then a user-approved live check with explicit privacy and no-paid-fallback gates. Respect the existing correct Jarvis repo rather than the AIHub OpenCode session rooted elsewhere.

**ASLAN UNUTMAZ — observed code and tests outrank narrative confidence.**
