# Task 5 Report: Top 10 horizontal group charts

## TDD record

- RED: `python -m pytest tests/v2/test_chart_planner.py tests/v2/test_analytics_tools.py tests/v2/test_real_analysis_executor.py -q` produced five expected failures: absent chart orientation and priority fields, missing planner priority argument, rejected chart input fields, and missing executor priority propagation.
- GREEN: the same command passed with `32 passed`.

## Changed files

- `app/v2/schemas/analysis.py`: chart input now carries orientation and an optional priority result source.
- `app/v2/services/chart_planner.py`: group aggregates use horizontal `重点 Top 10` specs capped at ten rows; monthly charts remain vertical and retain their supported range.
- `app/v2/services/analytics.py`: chart rendering selects priority groups by stable dimension IDs before deterministic aggregate backfill, uses horizontal bars and a height based on the selected row count, and leaves the source result unchanged.
- `app/v2/services/executor.py`: only group-aggregate chart planning receives the available `underperforming` priority source.
- Focused planner, analytics, and executor tests cover the behavior.

## Verification and self-review

- Focused tests passed: 32 tests. Existing third-party deprecation/version warnings remain outside this task.
- `python -m compileall -q app tests alembic` and `git diff --check` were run after the implementation.
- The selection path copies chart rows and does not alter aggregate tables, contracts, or Evidence. Unit grouping remains unchanged.

## Commit

`fix: render readable Top 10 group charts`

## Concerns

None within scope. Monthly display remains bounded by the existing supported 100-row chart input contract; this task preserves all rows within that contract.

## Fix round 1: ChartSpec constructor compatibility

- Root cause: the Task 5 fields `priority_source_step_id` and `orientation` were inserted before the legacy required fields without defaults, making existing keyword construction fail with missing-argument `TypeError`.
- RED: `test_chart_spec_preserves_existing_keyword_constructor_defaults` failed with the expected missing `priority_source_step_id` and `orientation` arguments.
- GREEN: the new fields now follow the original required interface and default to `orientation="vertical"` and `priority_source_step_id=None`; `arguments()` retains both serialized values.
- Verification: focused related suite passed with `33 passed`; `python -m compileall -q app tests alembic` and `git diff --check` passed.
