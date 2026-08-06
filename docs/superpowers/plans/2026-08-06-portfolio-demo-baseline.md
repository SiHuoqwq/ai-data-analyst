# Portfolio Demo Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, public-safe demo dataset and a minimal Fake-first local demo path for the current V2 product.

**Architecture:** A standard-library Python generator owns the checked-in CSV contract. FastAPI exposes only a public Provider descriptor through `/health`; React renders that descriptor and two controlled questions. PowerShell scripts orchestrate explicit migration and the existing backend/frontend processes using repository-external runtime storage.

**Tech Stack:** Python 3.10, csv/random standard library, pytest/pandas for contract verification, FastAPI, React 19, TypeScript, Vitest, PowerShell 5.1.

## Global Constraints

- Never read from, copy, modify, move, or commit the original 520×32 workbook.
- Never call DeepSeek during implementation or verification.
- Keep the demo dataset to the 9 fields required by `LearningDomainRegistry`.
- Default all demo startup and release verification to `V2_PROVIDER=fake`.
- Do not redesign the UI, add analysis workflows, add large dependencies, or push remote state.
- Create one local commit only after every required verification passes.

---

### Task 1: Deterministic public demo data

**Files:**
- Create: `demo/generate_learning_operations_demo.py`
- Create: `demo/learning_operations_demo.csv`
- Create: `demo/README.md`
- Create: `tests/test_demo_dataset.py`

**Interfaces:**
- Produces: `generate_dataset(output_path: Path) -> None` and a 360-row UTF-8 CSV covering 2025-01 through 2026-06.
- Consumes: only Python standard library in production; tests may use pandas already present in project dependencies.

- [ ] Write contract tests for literal columns, 360 rows, 18 months, permitted rating gaps, positive/negative slopes, cross-category volatility, completion and refund ordering.
- [ ] Run `python -m pytest tests/test_demo_dataset.py -q` and confirm failure because the generator does not exist.
- [ ] Implement the smallest deterministic generator with seed `20260806`.
- [ ] Run the generator and contract test; confirm the generated file is byte-identical across two runs.
- [ ] Document origin, fields, trends, allowed public use and generation command in `demo/README.md`.

### Task 2: Runtime Provider status

**Files:**
- Modify: `app/main.py`
- Modify: `frontend-v2/src/types/api.ts`
- Modify: `frontend-v2/src/components/feedback/HealthIndicator.tsx`
- Modify: `frontend-v2/src/styles/globals.css`
- Create: `frontend-v2/src/components/feedback/HealthIndicator.test.tsx`
- Modify: `tests/test_release_readiness.py`

**Interfaces:**
- Produces: `/health.data.provider`-equivalent top-level `provider` object with `mode`, `display_name`, and `description`; no secrets.
- Consumes: runtime `settings.v2_provider`.

- [ ] Add failing backend tests for Fake, DeepSeek and unknown public descriptors and for forbidden sensitive keys.
- [ ] Add a failing frontend component test using complete health query states.
- [ ] Run both targeted suites and confirm the expected missing-contract failures.
- [ ] Implement the backend white-list mapping and frontend rendering.
- [ ] Run both targeted suites and confirm they pass.

### Task 3: Controlled example questions and honest copy

**Files:**
- Create: `frontend-v2/src/features/analysis/example-questions.ts`
- Modify: `frontend-v2/src/pages/analysis-workbench/AnalysisWorkbenchPage.tsx`
- Modify: `frontend-v2/src/pages/analysis-workbench/AnalysisWorkbenchPage.test.tsx`
- Modify: `frontend-v2/src/pages/workspace/WorkspacePage.tsx`
- Modify: `frontend-v2/src/styles/globals.css`

**Interfaces:**
- Produces: two exported question definitions whose text routes to `group_comparison` and `monthly_trend` and whose buttons only update the textarea.

- [ ] Add failing workbench tests for both buttons, exact input filling and zero run submissions.
- [ ] Run the targeted Vitest file and confirm failure because the buttons are absent.
- [ ] Add the question definitions, minimal buttons and capability copy.
- [ ] Run the targeted Vitest file and confirm it passes.

### Task 4: Port and Windows demo lifecycle

**Files:**
- Modify: `app/config.py`
- Create: `start-demo.ps1`
- Create: `stop-demo.ps1`
- Create: `tests/test_demo_scripts.py`
- Modify: `tests/test_release_readiness.py`

**Interfaces:**
- Produces: `start-demo.ps1 [-Provider Fake|DeepSeek] [-CheckOnly]` and `stop-demo.ps1` using `%TEMP%\xishu-demo-runtime`.

- [ ] Add failing tests for default Origin 5174, Fake `-CheckOnly`, and DeepSeek missing-Key refusal without secret output.
- [ ] Run the targeted tests and confirm failure because scripts and corrected default are absent.
- [ ] Implement the default port correction and the minimal scripts with explicit migration, hidden processes, readiness polling and recorded process-tree shutdown.
- [ ] Run targeted tests and confirm they pass.

### Task 5: User documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/release/DEMO_GUIDE.md`
- Modify: `docs/release/DEPLOYMENT.md`

**Interfaces:**
- Documents: data generation, Fake/DeepSeek labels, supported questions, PowerShell commands, temporary runtime location and stop procedure.

- [ ] Update only statements affected by Tasks 1–4.
- [ ] Review documentation against actual script help and current supported workflows.

### Task 6: Full verification and local commit

**Files:**
- No new production interfaces.

- [ ] Run full `python -m pytest -q` with `V2_PROVIDER=fake`.
- [ ] Run `python -m pytest tests/test_release_readiness.py -q`.
- [ ] Run `python -m compileall -q app tests alembic demo`.
- [ ] Run `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build` in `frontend-v2`.
- [ ] Run the generated data twice and compare SHA-256.
- [ ] Run `start-demo.ps1`, upload the CSV over HTTP, inspect overview, submit both questions with Fake, verify persisted recovery and chart HTTP responses, and confirm `/health` reports Fake mode.
- [ ] Run `stop-demo.ps1` and confirm ports 8000/5174 are released.
- [ ] Run `git diff --check`, inspect the exact diff and confirm the original workbook remains untouched and untracked.
- [ ] Stage only task files and create one local commit.
