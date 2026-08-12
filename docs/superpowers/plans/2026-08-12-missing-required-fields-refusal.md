# Missing Required Fields Refusal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop teacher-dependent questions before model or tool execution when the dataset has no teacher-related field, and return an actionable refusal without artifacts.

**Architecture:** Add a small deterministic `RequiredFieldGuard` that compares explicit question concepts with normalized dataset column names. Call it in `AnalysisExecutor` immediately after loading the question and file metadata; map its structured error through the existing failed-run contract without adding a new terminal state or frontend flow.

**Tech Stack:** Python 3.10+, SQLAlchemy, pytest, FastAPI V2 run persistence, React regression suite

## Global Constraints

- Cover only the verified teacher-dimension boundary in this change.
- Reject before DeepSeek, PlanCompiler, pandas, chart generation, or deterministic fallback.
- Use error code `MISSING_REQUIRED_FIELDS` and `retryable=false`.
- A rejected run must have zero RunSteps, zero Artifacts, and zero assistant messages.
- Preserve normal group-comparison and monthly-trend workflows.
- Do not call real DeepSeek during testing.

---

### Task 1: Deterministic teacher-field requirement guard

**Files:**
- Create: `app/v2/services/field_requirements.py`
- Create: `tests/v2/test_field_requirements.py`

**Interfaces:**
- Consumes: `question: str` and `columns_info: list[dict] | None`
- Produces: `RequiredFieldGuard.validate(question, columns_info) -> None`
- Raises: `MissingRequiredFieldsError(code, message, retryable, details)` only when a teacher concept is requested and no accepted teacher field exists

- [ ] Write parameterized failing tests for `教师`, `老师`, `讲师`, and `授课教师` questions against the nine-field learning dataset.
- [ ] Write failing tests proving `教师姓名`, `教师ID`, `教师 ID`, `授课教师`, `讲师`, or `教师评分` columns allow the question, and ordinary course/monthly questions are unaffected.
- [ ] Run `python -m pytest -q tests/v2/test_field_requirements.py` and confirm failure because the module does not exist.
- [ ] Implement Unicode-normalized deterministic matching and the actionable `MISSING_REQUIRED_FIELDS` error.
- [ ] Re-run the focused unit tests and confirm they pass.

### Task 2: Stop rejected runs before Provider and Artifact execution

**Files:**
- Modify: `app/v2/services/executor.py`
- Modify: `tests/v2/test_controlled_intent_routing.py`

**Interfaces:**
- Consumes: `RequiredFieldGuard.validate()` before `provider.set_history()` and `provider.generate_intent()`
- Produces: existing failed Run REST/SSE state with the new error code and message

- [ ] Add an integration test using the fixed teacher-quality question, a dataset without teacher fields, and a counting Provider.
- [ ] Assert Run status `failed`, error code `MISSING_REQUIRED_FIELDS`, actionable Chinese message, `retryable=false`, and zero Provider calls, RunSteps, Artifacts, and assistant messages.
- [ ] Run the integration test and confirm the old executor fails the new assertions by calling the Provider and completing an unrelated workflow.
- [ ] Inject and call `RequiredFieldGuard` before Provider history/intent work; map `MissingRequiredFieldsError` in the existing exception handler.
- [ ] Re-run the integration test plus existing supported and unsupported routing tests.

### Task 3: Full regression and local handoff

**Files:**
- No further production changes expected

**Interfaces:**
- Consumes: repository verification commands
- Produces: verified local commit and restarted local UI without a paid model request

- [ ] Run backend `V2_PROVIDER=fake python -m pytest -q`.
- [ ] Run release readiness and `python -m compileall -q app tests alembic`.
- [ ] From the physical frontend worktree path, run `npm test -- --run`, `npm run typecheck`, `npm run lint`, and `npm run build`.
- [ ] Run `git diff --check`, inspect the scoped diff, and commit only plan, implementation, and tests.
- [ ] Restart the local services in their existing configured Provider mode without submitting an analysis request; verify `/health` and frontend HTTP 200.
