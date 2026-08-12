# Single-Group Result Presentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace meaningless one-bar charts with a truthful compact single-object summary while preserving the aggregate table.

**Architecture:** `ChartPlanner` owns the decision that a non-time result with fewer than two rows is not chartable. The executor treats chart artifacts as conditional output. `TableArtifactView` renders a one-row summary above the existing table without changing multi-row results.

**Tech Stack:** Python 3, FastAPI service layer, pandas result contracts, pytest, React, TypeScript, Vitest, Testing Library, CSS.

## Global Constraints

- Do not call real DeepSeek; use `V2_PROVIDER=fake` for verification.
- Do not change pandas calculations, Evidence validation, multi-row charts, or time-series charts.
- Keep the original one-row table visible and do not invent targets, comparisons, or positive/negative labels.

---

### Task 1: Suppress non-comparative chart plans

**Files:**
- Modify: `tests/v2/test_chart_planner.py`
- Modify: `app/v2/services/chart_planner.py`

**Interfaces:**
- Consumes: `ToolExecutionResult.row_count` and `ResultSchema.dimensions`.
- Produces: `ChartPlanner.plan(...) -> []` only when there is no time dimension and `row_count < 2`.

- [ ] **Step 1: Write failing planner tests**

Add a one-row category test expecting `[]`, plus explicit guards that a three-row category result still produces a bar and a one-row time result still produces a line chart.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/v2/test_chart_planner.py -q`

Expected: the one-row category assertion fails because a bar chart is currently planned.

- [ ] **Step 3: Implement the minimal planner guard**

After detecting `time_dimension`, return `[]` when `time_dimension is None and result.row_count < 2`. Preserve existing empty-result handling outside this planner.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/v2/test_chart_planner.py -q`

Expected: all planner tests pass.

### Task 2: Allow a successful run with no chart artifact

**Files:**
- Modify: `tests/v2/test_controlled_intent_routing.py`
- Modify: `app/v2/services/executor.py`

**Interfaces:**
- Consumes: the empty list returned by `ChartPlanner.plan`.
- Produces: a completed single-group run with table artifacts and zero chart artifacts.

- [ ] **Step 1: Write the failing executor integration test**

Create a controlled dataset whose category column has one unique value, execute the group-comparison workflow with the Fake Provider, and assert status `completed`, at least one table artifact, and zero chart artifacts.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/v2/test_controlled_intent_routing.py -q`

Expected: the run fails required-artifact validation because `chart_planning` currently declares a chart unconditionally.

- [ ] **Step 3: Make chart output conditional**

Remove `chart` from the static expected output for `chart_planning`. When that step actually creates one or more chart drafts, add `chart` to `expected_artifact_types`; when it creates none, leave it absent.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/v2/test_controlled_intent_routing.py -q`

Expected: the integration test and existing controlled-flow tests pass.

### Task 3: Render the compact single-object summary

**Files:**
- Modify: `frontend-v2/src/features/analysis/artifact-views.test.tsx`
- Modify: `frontend-v2/src/features/analysis/ArtifactView.tsx`
- Modify: `frontend-v2/src/styles/globals.css`

**Interfaces:**
- Consumes: a valid `TableArtifactPayload` with exactly one row.
- Produces: `单对象概览`, a readable object label, numeric metrics using `formatCell`, the boundary statement, and the unchanged table.

- [ ] **Step 1: Write the failing component test**

Render a one-row table containing `课程类别`, `报名人数`, and `平均完成率`. Assert the overview heading, `AI 应用`, formatted metrics, boundary sentence, and original table caption are all present.

- [ ] **Step 2: Verify RED**

Run from the physical frontend worktree: `npm test -- --run src/features/analysis/artifact-views.test.tsx`

Expected: the overview heading and boundary sentence are missing.

- [ ] **Step 3: Implement summary markup and scoped styles**

For one row, derive non-number columns as the object identity and number columns as metrics. Render a compact summary before `.table-scroll`; fall back to `当前对象` if every column is numeric. Reuse `formatCell` and keep the table unchanged.

- [ ] **Step 4: Verify GREEN**

Run: `npm test -- --run src/features/analysis/artifact-views.test.tsx`

Expected: all artifact-view tests pass.

### Task 4: Verify and commit the feature

**Files:** all files above.

- [ ] **Step 1: Run focused backend and frontend suites**

Run the commands from Tasks 1-3 and confirm zero failures.

- [ ] **Step 2: Check the diff**

Run: `git diff --check` and inspect `git diff` for unrelated changes.

- [ ] **Step 3: Commit only scoped files**

Commit message: `fix: present single-group results without charts`

