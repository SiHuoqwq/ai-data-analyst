# DeepSeek Controlled Demo Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate the two supported DeepSeek learning-operations workflows against the fixed synthetic dataset with no more than six paid runs, then publish a redacted acceptance report.

**Architecture:** Run the existing application with `V2_PROVIDER=deepseek` and repository-external runtime storage. Submit exactly one formal run per fixed question, inspect persisted Run/Step/Artifact/Evidence data through public APIs, and compare all exposed figures with an independent pandas calculation. Apply only test-first minimal fixes if a run exposes a product defect.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, pandas, matplotlib, DeepSeek provider, React/Vite, pytest, Vitest, PowerShell.

## Global Constraints

- Never print, persist in Git, or include the complete API key, request headers, prompts, private paths, or raw provider responses in the report.
- Allow at most two repair retries per question and at most six complete real-model runs total.
- Do not add intents, change demo trends, relax Evidence validation, or hard-code final answers.
- Do not push the repository.
- Commit only if both workflows are passing or conditionally passing and the complete regression suite passes.

---

### Task 1: Zero-cost readiness gate

**Files:**
- Verify: `demo/learning_operations_demo.csv`
- Verify: `demo/generate_learning_operations_demo.py`
- Verify: `tests/test_demo_dataset.py`

- [ ] Confirm clean Git state, baseline commit ancestry, and linked-worktree identity.
- [ ] Regenerate the CSV and confirm SHA-256 `DBC6235CEA5638348C9CC74D7D7A5A9C4669EFEFE4B499DE654A3EDF7C606DCF`.
- [ ] Run `pytest tests/test_demo_dataset.py -q`.
- [ ] Confirm the process has a nonblank `DEEPSEEK_API_KEY` without displaying it.
- [ ] Start with `start-demo.ps1 -Provider DeepSeek`, then require `/health` to report the exact public DeepSeek status before any paid run.

### Task 2: Execute and audit group comparison

**Files:**
- Read: `app/v2/domain/learning_registry.py`
- Read: `app/v2/services/plan_compiler.py`
- Read: `app/v2/services/executor.py`

- [ ] Upload the fixed CSV and submit the exact group-comparison question once.
- [ ] Record redacted timing, Run ID, status, retry/fallback/error fields.
- [ ] Inspect intent, ordered steps, artifacts, current-Run Evidence, chart response, REST recovery, and SSE recovery.
- [ ] Independently calculate every displayed group metric with pandas and classify exact, rounded, and mismatched values.
- [ ] If failed, classify the original failure and use systematic debugging plus TDD before at most two repair retries.

### Task 3: Execute and audit monthly trend

**Files:**
- Read: `app/v2/services/analytics.py`
- Read: `app/v2/services/chart_planner.py`
- Read: `app/v2/services/evidence.py`

- [ ] Submit the exact monthly-trend question once against the same uploaded dataset.
- [ ] Record redacted timing, Run ID, status, retry/fallback/error fields.
- [ ] Inspect intent, ordered steps, artifacts, Evidence, three compatible charts, REST recovery, and SSE recovery.
- [ ] Independently verify counts, amounts, completion rates, slopes, volatility, and time range with pandas.
- [ ] If failed, classify the original failure and use systematic debugging plus TDD before at most two repair retries.

### Task 4: Report and complete regression

**Files:**
- Create: `docs/release/DEEPSEEK_DEMO_ACCEPTANCE.md`
- Modify only if required by a proven defect: affected production and regression-test files.

- [ ] Write the redacted report with environment, data hash, questions, run records, intents, steps, artifacts, comparisons, Evidence/chart checks, fallback status, boundaries, and verdicts.
- [ ] Scan the report and Git diff for secrets, private paths, raw prompts beyond the two approved questions, logs, databases, and generated charts.
- [ ] Run full pytest, release readiness, compileall, frontend tests, typecheck, lint, and build.
- [ ] Stop services and confirm ports 8000/5174 are released.
- [ ] If both verdicts and regression qualify, stage only task files and create `test: validate controlled DeepSeek demo workflows` locally.
