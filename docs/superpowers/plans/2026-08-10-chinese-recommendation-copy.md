# Chinese Recommendation Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the analysis workbench's English recommendation templates and rigid textarea placeholder with the approved Chinese copy.

**Architecture:** Keep recommendation selection and analysis execution unchanged. Update only the server-owned deterministic renderer and the React textarea placeholder, with consumer-visible regression tests for both outputs.

**Tech Stack:** Python, pytest, React, TypeScript, Vitest, Testing Library

## Global Constraints

- Preserve recommendation intent types, field selection, IDs, click behavior, and analysis execution.
- Do not change layout, styling, Provider protocol, charts, or supported analysis types.
- Do not issue a real DeepSeek analysis request during verification.
- Never print or persist the API key.

---

### Task 1: Chinese server-rendered recommendation copy

**Files:**
- Modify: `tests/v2/test_recommendation_service.py`
- Modify: `app/v2/services/recommendation_renderer.py`

**Interfaces:**
- Consumes: `DeterministicRecommendationRenderer.render(candidate, intent, file_record)`
- Produces: the same `(label, question)` tuple with approved Chinese templates

- [ ] Update literal expectations for both controlled intents in `tests/v2/test_recommendation_service.py`.
- [ ] Run the focused tests and confirm they fail because the renderer still returns English.
- [ ] Change `render()` to return `按{dimension}比较` / `不同{dimension}的关键指标表现有何差异？` and `{dimension}月度趋势` / `按{date}月份查看{dimension}的变化趋势`.
- [ ] Re-run the focused recommendation tests and confirm they pass.

### Task 2: Natural analysis input placeholder

**Files:**
- Modify: `frontend-v2/src/pages/analysis-workbench/AnalysisWorkbenchPage.test.tsx`
- Modify: `frontend-v2/src/pages/analysis-workbench/AnalysisWorkbenchPage.tsx`

**Interfaces:**
- Consumes: the existing analysis textarea
- Produces: placeholder text `你想从这份数据中了解什么？`

- [ ] Add a Testing Library assertion that finds the textarea by the approved placeholder.
- [ ] Run the focused frontend test and confirm it fails because the old placeholder is rendered.
- [ ] Replace only the textarea `placeholder` value.
- [ ] Re-run the focused frontend test and confirm it passes.

### Task 3: Regression and real-mode handoff

**Files:**
- No production file changes expected

**Interfaces:**
- Consumes: current repository scripts and `/health`
- Produces: a tested build and a locally running DeepSeek-mode UI for user-operated testing

- [ ] Run `python -m pytest -q` with `V2_PROVIDER=fake`.
- [ ] Run `python -m compileall -q app tests alembic`.
- [ ] In `frontend-v2`, run `npm test -- --run`, `npm run typecheck`, `npm run lint`, and `npm run build`.
- [ ] Review `git diff --check` and the scoped diff.
- [ ] Commit only the implementation and test files.
- [ ] Stop existing demo services, confirm the DeepSeek key exists without printing it, and run `start-demo.ps1 -Provider DeepSeek`.
- [ ] Verify `/health` reports DeepSeek mode and `http://localhost:5174/` is reachable without sending an analysis request.
