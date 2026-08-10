# Dataset-Aware Suggestions and Readable Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate cached, executable DeepSeek recommendations for the two supported intents and render high-cardinality group comparisons as readable Top 10 horizontal charts.

**Architecture:** Add a dataset-version recommendation service behind a read-only V2 endpoint. The service builds a safe field profile, asks the active provider for strictly structured recommendations, validates them with the existing PlanCompiler, persists only sanitized accepted recommendations, and falls back to deterministic templates. Keep full pandas/Evidence results unchanged while the chart planner selects at most ten priority combinations for horizontal rendering.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, SQLAlchemy/Alembic, pandas, Matplotlib, pytest, React 19, TypeScript, TanStack Query, Vitest.

## Global Constraints

- Continue to support only `group_comparison` and `monthly_trend`; do not add a third intent.
- Do not send raw rows, sample values, API keys, physical paths, prompts, or raw model responses through the recommendation API or cache.
- Fake mode must never call DeepSeek and must return deterministic template recommendations.
- DeepSeek recommendations must pass strict schema, field existence, intent allowlist, and PlanCompiler validation before display.
- Clicking a recommendation only fills the input; it never starts a Run automatically.
- Full aggregate tables, deterministic pandas calculations, and Evidence validation remain unchanged.
- Group charts show at most Top 10 priority combinations; monthly charts retain the complete supported time range.
- Do not introduce a new charting library or redesign the page.
- Database migration remains explicit; never run Alembic in FastAPI startup.

---

### Task 1: Recommendation contracts and provider capability

**Files:**
- Create: `app/v2/schemas/recommendations.py`
- Modify: `app/v2/services/provider.py`
- Test: `tests/v2/test_recommendation_provider.py`

**Interfaces:**
- Produces: `RecommendationCandidate(intent_type, referenced_fields, label?, question?)` and `RecommendationGeneration(candidates)` Pydantic models. `label` and `question` are receive-only legacy compatibility fields and never public model instructions.
- Produces: `AnalysisProvider.recommend_questions(file_record) -> RecommendationGeneration`.
- Fake provider returns no model candidates; DeepSeek sends only `_safe_dataset_profile(file_record)` plus the two allowed intent contracts.

- [ ] **Step 1: Write failing provider tests**

Add tests asserting that DeepSeek parses two valid candidates, rejects extra keys/unsupported intent values, and that the serialized request contains field metadata but not `filepath`, raw rows, API-key markers, or sample values. Add a Fake provider test asserting deterministic empty candidate output and zero HTTP calls.

- [ ] **Step 2: Run the new tests and confirm RED**

Run: `python -m pytest tests/v2/test_recommendation_provider.py -q`

Expected: FAIL because recommendation schemas and `recommend_questions` do not exist.

- [ ] **Step 3: Implement strict contracts and provider methods**

Define:

```python
AllowedRecommendationIntent = Literal["group_comparison", "monthly_trend"]

class RecommendationCandidate(APIModel):
    intent_type: AllowedRecommendationIntent
    referenced_fields: list[str] = Field(min_length=1, max_length=12)
    label: str | None = Field(default=None, min_length=1, max_length=60)
    question: str | None = Field(default=None, min_length=1, max_length=1000)

class RecommendationGeneration(APIModel):
    candidates: list[RecommendationCandidate] = Field(max_length=2)
```

Implement a temperature-zero DeepSeek call with a bounded JSON prompt. Do not store the raw response on the provider. Fake returns `RecommendationGeneration(candidates=[])`.

- [ ] **Step 4: Run provider tests and existing provider regression**

Run: `python -m pytest tests/v2/test_recommendation_provider.py tests/v2/test_deepseek_provider.py -q`

Expected: PASS.

- [ ] **Step 5: Commit provider capability**

```powershell
git add -- app/v2/schemas/recommendations.py app/v2/services/provider.py tests/v2/test_recommendation_provider.py
git commit -m "feat: add controlled question recommendation provider"
```

### Task 2: Persistent validated recommendation service

**Files:**
- Modify: `app/v2/db/models.py`
- Create: `alembic/versions/0002_dataset_recommendations.py`
- Create: `app/v2/services/recommendations.py`
- Test: `tests/v2/test_recommendation_service.py`
- Modify: `tests/v2/conftest.py` only if model imports are explicitly enumerated.

**Interfaces:**
- Produces: `DatasetRecommendationModel` with one unique row per dataset version and JSON accepted recommendations.
- Produces: `DatasetRecommendationService.get_or_generate(dataset_version_id, provider) -> RecommendationResult`.
- Consumes: `provider.recommend_questions(file_record)` from Task 1 and `PlanCompiler` validation of the bounded intent and referenced fields.

- [ ] **Step 1: Write failing service and migration tests**

Cover cache miss generation, cache hit without a second provider call, one candidate per allowed intent, nonexistent field rejection, unsupported/failed compilation rejection, DeepSeek failure fallback, Fake template-only behavior, incompatible datasets returning only executable questions, and persistence without prompt/raw response/path fields.

- [ ] **Step 2: Run tests and confirm RED**

Run: `python -m pytest tests/v2/test_recommendation_service.py tests/v2/test_migrations.py -q`

Expected: FAIL because the table and service do not exist.

- [ ] **Step 3: Add explicit migration and model**

Create `dataset_recommendations` with:

```text
id string primary key
dataset_version_id string unique foreign key files.id
recommendations_json JSON not null
source string not null, constrained to model|template
provider_name string nullable
provider_model string nullable
created_at timezone datetime not null
updated_at timezone datetime not null
```

Do not add startup migration behavior.

- [ ] **Step 4: Implement validation, templates, and cache**

The service must load `FileModel`, generate at most one candidate per intent, require every referenced field to exist, compile each candidate, and then use the deterministic intent renderer to create cacheable public labels and questions. Model-authored prose is ignored. If model generation raises or produces no accepted candidates, build field-adapted deterministic selections from the domain registry and compile them before rendering and caching.

- [ ] **Step 5: Run service, migration, and compiler tests**

Run: `python -m pytest tests/v2/test_recommendation_service.py tests/v2/test_migrations.py tests/v2/test_plan_compiler.py -q`

Expected: PASS.

- [ ] **Step 6: Commit service and migration**

```powershell
git add -- app/v2/db/models.py alembic/versions/0002_dataset_recommendations.py app/v2/services/recommendations.py tests/v2/test_recommendation_service.py tests/v2/conftest.py
git commit -m "feat: cache validated dataset recommendations"
```

### Task 3: Read-only recommendation API

**Files:**
- Modify: `app/v2/schemas/api.py`
- Modify: `app/v2/api/routes.py`
- Test: `tests/v2/test_recommendation_api.py`

**Interfaces:**
- Produces: `GET /api/v2/datasets/{dataset_version_id}/recommendations`.
- Response data: `{dataset_version_id, recommendations, source, generated_at}`; each recommendation exposes only `{id, intent_type, label, question, referenced_fields}`.
- Consumes: `DatasetRecommendationService.get_or_generate` and the existing `get_provider` dependency.

- [ ] **Step 1: Write failing API contract tests**

Assert status 200 for Fake templates, stable cached response on repeated GET, 404 for a missing dataset, strict response fields, and absence of prompt, raw response, API-key markers, and physical paths.

- [ ] **Step 2: Run API test and confirm RED**

Run: `python -m pytest tests/v2/test_recommendation_api.py -q`

Expected: FAIL with 404 route not found.

- [ ] **Step 3: Add response schemas and route**

Use existing `APIMeta`; translate service errors to `V2APIError`. Keep generation synchronous for this small bounded request and return sanitized failure codes without model response bodies.

- [ ] **Step 4: Run API and error-envelope regression**

Run: `python -m pytest tests/v2/test_recommendation_api.py tests/v2/test_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit API**

```powershell
git add -- app/v2/schemas/api.py app/v2/api/routes.py tests/v2/test_recommendation_api.py
git commit -m "feat: expose dataset analysis recommendations"
```

### Task 4: Frontend dataset-aware recommendation cards

**Files:**
- Modify: `frontend-v2/src/api/v2-contracts.ts`
- Create: `frontend-v2/src/api/v2-recommendations.ts`
- Create: `frontend-v2/src/features/analysis/recommendation-queries.ts`
- Modify: `frontend-v2/src/pages/analysis-workbench/AnalysisWorkbenchPage.tsx`
- Modify: `frontend-v2/src/pages/analysis-workbench/AnalysisWorkbenchPage.test.tsx`
- Delete: `frontend-v2/src/features/analysis/example-questions.ts`

**Interfaces:**
- Produces: `getDatasetRecommendations(datasetId): Promise<DatasetRecommendationResponse>`.
- Produces: `useDatasetRecommendations(datasetId)` with TanStack key `['analysis', 'recommendations', datasetId]`.
- Consumes the Task 3 endpoint and displays the backend `source` without inferring Provider mode.

- [ ] **Step 1: Write failing component and client tests**

Test loading placeholders, two different dataset responses, model/template source copy, partial one-card response, recoverable query failure with manual input still enabled, and click-to-fill without `createConversation` or `createRun`.

- [ ] **Step 2: Run tests and confirm RED**

Run: `npm test -- --run src/pages/analysis-workbench/AnalysisWorkbenchPage.test.tsx`

Expected: FAIL because the page still imports fixed examples.

- [ ] **Step 3: Implement typed client, query, and UI states**

Replace `ANALYSIS_EXAMPLE_QUESTIONS` with API data. Render `模型选题` for `source=model` and `字段模板` for `source=template`; retain manual textarea and click-only fill behavior. `source=model` describes bounded topic selection, not model-authored public copy. Do not expose prompt or model diagnostics.

- [ ] **Step 4: Run focused frontend checks**

Run: `npm test -- --run src/pages/analysis-workbench/AnalysisWorkbenchPage.test.tsx src/api/v2-client.test.ts`

Run: `npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit frontend recommendations**

```powershell
git add -- frontend-v2/src/api/v2-contracts.ts frontend-v2/src/api/v2-recommendations.ts frontend-v2/src/features/analysis/recommendation-queries.ts frontend-v2/src/pages/analysis-workbench/AnalysisWorkbenchPage.tsx frontend-v2/src/pages/analysis-workbench/AnalysisWorkbenchPage.test.tsx frontend-v2/src/features/analysis/example-questions.ts
git commit -m "feat: show dataset-aware analysis recommendations"
```

### Task 5: Top 10 horizontal group charts

**Files:**
- Modify: `app/v2/schemas/analysis.py`
- Modify: `app/v2/services/chart_planner.py`
- Modify: `app/v2/services/analytics.py`
- Modify: `app/v2/services/executor.py`
- Test: `tests/v2/test_chart_planner.py`
- Test: `tests/v2/test_analytics_tools.py`

**Interfaces:**
- Extend `ChartSpec` and `CreateChartInput` with `orientation: Literal['vertical', 'horizontal'] = 'vertical'`.
- Extend them with `priority_source_step_id: str | None = None`; the executor supplies `underperforming` when planning `group_aggregate` charts and that result exists.
- Group comparison charts produce `orientation='horizontal'`, `limit=10`, title suffix `重点 Top 10`.
- Monthly charts remain `orientation='vertical'` and preserve their complete time-series limit.

- [ ] **Step 1: Write failing planner tests**

Assert that multi-category non-time results use horizontal Top 10 specs, `group_aggregate` receives `priority_source_step_id='underperforming'`, time-series results stay vertical with 90 rows, and low-cardinality behavior is not accidentally truncated below available rows.

- [ ] **Step 2: Write failing renderer tests**

Execute a group chart and inspect its returned summary/spec to assert no more than ten labels, priority rows precede enrollment backfill, compact labels preserve all four dimension values, and percentage/count/score remain separate charts.

- [ ] **Step 3: Run focused tests and confirm RED**

Run: `python -m pytest tests/v2/test_chart_planner.py tests/v2/test_analytics_tools.py -q`

Expected: FAIL because group specs still use vertical bars and limit 50.

- [ ] **Step 4: Implement Top 10 selection and horizontal rendering**

In the executor, attach `underperforming` as the priority source only for `group_aggregate`. In `_create_chart`, match priority rows to the aggregate by stable dimension IDs, append aggregate rows in their existing deterministic sort order until ten unique rows, and leave other chart sources unchanged except for the ten-row cap. Use `ax.barh`, invert the y-axis so the highest priority appears first, format labels as `类别｜难度｜渠道｜设备`, and adjust figure height based on the actual row count. Do not mutate either source table or the Evidence registry.

- [ ] **Step 5: Run chart and executor regression**

Run: `python -m pytest tests/v2/test_chart_planner.py tests/v2/test_analytics_tools.py tests/v2/test_executor.py -q`

Expected: PASS.

- [ ] **Step 6: Commit chart readability fix**

```powershell
git add -- app/v2/schemas/analysis.py app/v2/services/chart_planner.py app/v2/services/analytics.py app/v2/services/executor.py tests/v2/test_chart_planner.py tests/v2/test_analytics_tools.py
git commit -m "fix: render readable Top 10 group charts"
```

### Task 6: Full verification and controlled demo acceptance

**Files:**
- Modify: `README.md` only if the public behavior description is now stale.
- Modify: `docs/release/DEEPSEEK_DEMO_ACCEPTANCE.md` only with a new dated addendum; do not rewrite prior evidence.

**Interfaces:**
- Verifies all Task 1–5 interfaces together.

- [ ] **Step 1: Apply migration explicitly in a disposable/demo database**

Run: `python -m alembic upgrade head`

Expected: current revision becomes `0002_dataset_recommendations` without startup migration behavior.

- [ ] **Step 2: Run complete backend verification**

Run: `python -m pytest -q`

Run: `python -m pytest tests/test_release_readiness.py -q`

Run: `python -m compileall -q app tests alembic demo`

Expected: all commands exit 0.

- [ ] **Step 3: Run complete frontend verification**

From `frontend-v2` run:

```powershell
npm test -- --run
npm run typecheck
npm run lint
npm run build
```

Expected: all commands exit 0.

- [ ] **Step 4: Verify Fake HTTP workflow without paid calls**

Start with `start-demo.ps1` default Fake mode. Confirm two compatible datasets receive field-adapted but deterministic recommendations, repeated GET is stable, clicks only fill the input, a group Run produces readable Top 10 horizontal PNGs, monthly charts retain all months, refresh restores artifacts, and `/health` reports Fake.

- [ ] **Step 5: Stop and request explicit DeepSeek acceptance authorization**

Do not make a paid recommendation request unless the user separately authorizes a bounded acceptance budget. If authorized, record only request count, sanitized status, dataset hash/version, recommendation source, accepted intent/field selections, server-rendered questions, and cache-hit behavior.

- [ ] **Step 6: Update only necessary public documentation and commit**

```powershell
git add -- README.md docs/release/DEEPSEEK_DEMO_ACCEPTANCE.md
git commit -m "docs: record dataset-aware recommendation validation"
```

Skip this commit if neither document needs a truthful update.

- [ ] **Step 7: Confirm final repository boundary**

Run: `git status --short --branch`

Expected: clean worktree; no `.env`, database, uploaded file, chart PNG, model response, or runtime log tracked; no remote push.

---

## Security hardening Round 4 implementation addendum

**Goal:** Make every recommendation response and selected Run derive from one freshly validated, server-owned intent selection, including legacy cache hits and database race winners.

**Architecture:** Treat cached recommendation JSON as untrusted input. Reconstruct only `intent_type` and `referenced_fields`, validate them against the current dataset and Provider identity, compile the resulting `AnalysisIntent`, and deterministically re-render public copy before either returning it or resolving a Run selection. A dataset-, Provider-, and cache-generation-bound recommendation ID is the only new client selection handle; the server also requires the submitted message to equal the freshly rendered question, then passes the same validated `AnalysisIntent` object to `AnalysisExecutor`. Exact idempotency replays are resolved from their persisted request hash before mutable recommendation-cache validation, so a lost response can still recover its already-created Run without authorizing a new Run.

**Global constraints:** Provider outer envelopes remain strict; invalid candidate items are dropped independently. Non-registry field names never enter public grammar. Fake and DeepSeek selections share the same resolver and executor path. Evidence and deterministic pandas outputs do not change. No real DeepSeek request is permitted.

### Task 7: Cache reconstruction, aliases, and compact sensitive windows

**Files:**
- Modify: `app/v2/services/recommendations.py`
- Modify: `app/v2/services/recommendation_renderer.py`
- Modify: `app/v2/services/recommendation_safety.py`
- Test: `tests/v2/test_recommendation_service.py`
- Test: `tests/v2/test_recommendation_provider.py`

- [x] Add RED tests that seed same-Provider/model cache rows with hostile `label` and `question`, and assert both a normal cache hit and an `IntegrityError` winner return newly rendered copy only.
- [x] Add RED tests proving one-token English, one-token Chinese, and separator-rich non-registry fields render as stable `field-<position>-<digest>` aliases, while registered fields retain registry labels.
- [x] Add RED MockTransport cases for prefix/suffix forms such as `prefix.a.pi.key.hash` and `meta.ac.cess.key.version`, plus collision controls such as `source_pathway` and `storage_keynote`.
- [x] Implement one cache canonicalization path used by normal hits, race winners, and selection resolution. Template rows are regenerated from current template candidates; model rows retain only independently valid controlled selections.
- [x] Implement exact compact equality over every contiguous semantic-token window and remove the non-registry single-token display exception.
- [x] Run `python -m pytest tests/v2/test_recommendation_service.py tests/v2/test_recommendation_provider.py -q` and confirm GREEN.

### Task 8: Per-item Provider parsing

**Files:**
- Modify: `app/v2/schemas/recommendations.py`
- Modify: `app/v2/services/provider.py`
- Test: `tests/v2/test_recommendation_provider.py`

- [x] Add RED tests where a valid candidate is adjacent to an unsupported intent or extra-key candidate and survives, while an outer extra key, non-array `candidates`, or more than two items still raises `PROVIDER_INVALID_RESPONSE`.
- [x] Parse the strict outer envelope first, then `RecommendationCandidate.model_validate` each item independently and retain only valid items.
- [x] Run `python -m pytest tests/v2/test_recommendation_provider.py -q` and confirm GREEN.

### Task 9: Trusted recommendation selection through Run execution

**Files:**
- Modify: `app/v2/schemas/api.py`
- Modify: `app/v2/api/routes.py`
- Modify: `app/v2/services/recommendations.py`
- Modify: `app/v2/services/runs.py`
- Modify: `app/v2/services/executor.py`
- Modify: `frontend-v2/src/types/v2.ts`
- Modify: `frontend-v2/src/pages/analysis-workbench/AnalysisWorkbenchPage.tsx`
- Test: `tests/v2/test_recommendation_api.py`
- Test: `tests/v2/test_recommendation_service.py`
- Test: `tests/v2/test_run_lifecycle.py`
- Test: `frontend-v2/src/pages/analysis-workbench/AnalysisWorkbenchPage.test.tsx`
- Test: `frontend-v2/src/api/v2-client.test.ts`

- [x] Add RED service/API tests for valid selection, wrong dataset/cache/Provider, real cache-generation replacement, stale ID, question tampering, and lost-response idempotency replay. The API must reject invalid selections before creating a new Run while exact retries recover an already-created Run.
- [x] Add a RED executor test whose Provider raises if `generate_intent` is called; a validated non-registry recommendation must still complete through the supplied `AnalysisIntent`.
- [x] Add RED frontend tests proving a card click stores and submits `recommendation_id`, any textarea edit clears it, and manual questions omit it.
- [x] Generate each public recommendation ID from dataset, cache generation, Provider/model, controlled intent type, and ordered referenced fields. Resolve the handle only from that matching cache generation, require an exact freshly rendered question, and return the freshly compiled `AnalysisIntent`.
- [x] Include `recommendation_id` in Run idempotency identity and context metadata, and construct `AnalysisExecutor(provider, trusted_intent=resolved_intent)` only for a newly created Run.
- [x] In `AnalysisExecutor`, bypass Provider intent recognition when `trusted_intent` is present, then compile and validate that same object against the Run dataset before execution.
- [x] Track the selected recommendation independently from retry idempotency state in React; clear it on dataset changes, successful submission, and every manual textarea change.
- [x] Run focused backend and frontend suites and confirm GREEN.

### Task 10: Verification, report, and commits

- [x] Run full backend pytest, release readiness, compileall, full frontend test/typecheck/lint/build, and a fresh disposable Fake HTTP workflow containing recommendation selection plus group/monthly Runs.
- [x] Run `git diff --check` and inspect the scoped diff for secrets, paths, private data, and unrelated edits.
- [x] Append Round 4 TDD evidence, verification results, commits, and remaining concerns to `security-hardening-report.md`.
- [x] Commit the current Round 3 work and Round 4 changes as one scoped local commit; do not push.
