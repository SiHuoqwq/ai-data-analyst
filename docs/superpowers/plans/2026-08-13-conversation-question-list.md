# Conversation Question List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show every user question represented by a conversation, with the first four visible by default and an inline expand/collapse control.

**Architecture:** The existing conversation list endpoint returns user questions already ordered and filtered, avoiding per-card detail requests. A focused React `ConversationRow` component owns only expansion state and keeps navigation separate from its button.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy, Pydantic, pytest, React, TypeScript, React Router, Vitest, Testing Library, CSS.

## Global Constraints

- Only expose `role=user` message content; never include assistant output, prompts, tools, secrets, or internal configuration.
- Preserve `title`, `message_count`, existing routes, and database schema.
- Default to the first 4 questions; use `查看全部 N 个问题` and `收起问题`.
- Do not call real DeepSeek; use `V2_PROVIDER=fake` for verification.

---

### Task 1: Extend the conversation list contract

**Files:**
- Modify: `tests/v2/test_conversation_messages.py`
- Modify: `app/models/chat.py`
- Modify: `app/db/conversation_store.py`
- Modify: `app/api/conversations.py`

**Interfaces:**
- Produces: `ConversationItem.user_questions: list[str]`.
- Ordering: message `created_at` ascending with `id` as the deterministic tie-breaker.

- [ ] **Step 1: Write the failing API test**

Persist interleaved user and assistant messages for one conversation, request `GET /api/v1/files/{file_id}/conversations`, and assert `user_questions` contains only the user content in chronological order while `message_count` counts all messages.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/v2/test_conversation_messages.py -q`

Expected: the response has no `user_questions` field.

- [ ] **Step 3: Implement the contract and one-load query**

Add `user_questions` with a Pydantic `default_factory`. Load each conversation's messages with SQLAlchemy eager loading in the existing store query, and construct both `message_count` and filtered user questions in the route without calling `count_messages` per conversation.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/v2/test_conversation_messages.py -q`

Expected: all conversation-message tests pass.

### Task 2: Add the expandable question list UI

**Files:**
- Modify: `frontend-v2/src/types/api.ts`
- Modify: `frontend-v2/src/pages/dataset-overview/DatasetOverviewPage.test.tsx`
- Modify: `frontend-v2/src/pages/dataset-overview/DatasetOverviewPage.tsx`
- Modify: `frontend-v2/src/styles/globals.css`

**Interfaces:**
- Consumes: `ConversationItem.user_questions`.
- Produces: a card showing metadata and up to four numbered questions, expandable without navigation; its main link still restores the conversation.

- [ ] **Step 1: Write failing UI tests**

Mock a conversation with six questions. Assert questions 1-4 are visible, 5-6 are hidden, the expand button reveals all six, the collapse button hides 5-6, and the conversation link targets `/datasets/file-1/analysis?conversationId=conversation-1`. Add an empty-question case asserting `暂无可展示的问题` and the stored title.

- [ ] **Step 2: Verify RED**

Run from the physical frontend worktree: `npm test -- --run src/pages/dataset-overview/DatasetOverviewPage.test.tsx`

Expected: the numbered questions and expand control are absent.

- [ ] **Step 3: Implement the focused component**

Add the API type field. Extract a local `ConversationRow` component with `expanded` state, slice the questions at four when collapsed, keep the `<Link>` and `<button>` as siblings, and use a semantic ordered list.

- [ ] **Step 4: Add scoped responsive styling**

Replace the old two-column link rule with a card wrapper, body link, question list, and text-button styles. Preserve narrow-screen wrapping and do not alter other page sections.

- [ ] **Step 5: Verify GREEN**

Run: `npm test -- --run src/pages/dataset-overview/DatasetOverviewPage.test.tsx`

Expected: all dataset-overview tests pass.

### Task 3: Verify and commit the feature

**Files:** all files above.

- [ ] **Step 1: Run focused backend and frontend suites**

Run the commands from Tasks 1-2 and confirm zero failures.

- [ ] **Step 2: Check the diff**

Run: `git diff --check` and inspect `git diff` for unrelated changes.

- [ ] **Step 3: Commit only scoped files**

Commit message: `feat: list conversation questions on dataset overview`

### Task 4: Run complete project verification

**Files:** no source changes expected.

- [ ] **Step 1: Run backend verification with Fake Provider**

Run: `$env:V2_PROVIDER='fake'; python -m pytest -q; python -m pytest tests/test_release_readiness.py -q; python -m compileall -q app tests alembic`

- [ ] **Step 2: Run frontend verification from the physical worktree**

Run: `npm test -- --run; npm run typecheck; npm run lint; npm run build`

- [ ] **Step 3: Confirm repository scope**

Run: `git status --short --branch`, `git diff --check`, and inspect both new implementation commits.

