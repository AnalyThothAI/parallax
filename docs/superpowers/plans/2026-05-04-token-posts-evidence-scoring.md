# Token Posts and Explainable Evidence Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Split token post facts from signal explanation highlights, remove old token-flow evidence compatibility fields, and make post scoring auditable.

**Architecture:** Add a dedicated `TokenPostsService` for full attributed post pagination and keep `TokenFlowService` focused on token signal ranking and highlights. Replace opaque additive highlight scoring with a deterministic contribution ledger and explicit risk caps. Update the React focus drawer to show token `全部帖子` and `信号解释` as separate views.

**Tech Stack:** Python 3.12, FastAPI, SQLite WAL/FTS5, pytest, React 19, TanStack Query, Vitest, TypeScript.

---

### Task 1: Document the Breaking Contract

**Files:**
- Create: `docs/superpowers/specs/2026-05-04-token-posts-evidence-scoring-design.md`
- Create: `docs/superpowers/plans/2026-05-04-token-posts-evidence-scoring.md`

- [x] Add the design spec that defines facts, highlights, scoring, storage indexes, UI behavior, and acceptance criteria.
- [x] Add this implementation plan with exact file responsibilities and verification commands.

### Task 2: Add Failing Backend Tests

**Files:**
- Create: `tests/test_token_posts_service.py`
- Modify: `tests/test_api_http.py`
- Modify: `tests/test_token_conviction_flow.py`
- Modify: `tests/test_token_attribution_flow.py`
- Modify: `tests/test_token_rolling_flow.py`

- [x] Add a service test proving `TokenPostsService.token_posts()` returns distinct token-attributed posts with `total_count`, `has_more`, and `next_cursor`.
- [x] Add an API test proving `/api/token-posts` accepts `token_id`, returns full post metadata, and rejects missing identity.
- [x] Update token-flow tests to require `evidence_highlights` and `evidence_highlight_best`.
- [x] Update token-flow tests to assert `evidence` and `evidence_best` are absent.
- [x] Add assertions that highlights include `score_version`, `contributions`, and `risk_caps`.

### Task 3: Implement Token Posts Retrieval

**Files:**
- Create: `src/gmgn_twitter_intel/retrieval/token_posts_service.py`
- Modify: `src/gmgn_twitter_intel/api/http.py`
- Modify: `src/gmgn_twitter_intel/storage/sqlite_schema.py`

- [x] Add `TokenPostsService` with keyset cursor encode/decode helpers.
- [x] Query `event_token_attributions` directly, filter to tradeable `direct/selected` resolved-token rows, and dedupe per `event_id`.
- [x] Add `GET /api/token-posts` with `token_id`, optional `chain/address`, `window`, `scope`, `limit`, and `cursor`.
- [x] Return HTTP 400 for missing token identity or malformed cursor.
- [x] Add query-oriented SQLite indexes for token ID and chain/address post pagination.

### Task 4: Replace Highlight Scoring With an Explanation Ledger

**Files:**
- Modify: `src/gmgn_twitter_intel/retrieval/token_signal_scoring.py`
- Modify: `src/gmgn_twitter_intel/retrieval/token_flow_service.py`

- [x] Change `evidence_score()` to return a score payload rather than a tuple.
- [x] Add contribution rows for identity certainty, attribution quality, source specificity, watched source, diffusion context, freshness, and market context.
- [x] Add explicit risk caps for repeated text, author concentration, low attribution confidence, stale market, and public-only context.
- [x] Keep `signal_block()` deterministic and add signal contribution metadata where useful.

### Task 5: Break the Token Flow Evidence Contract Cleanly

**Files:**
- Modify: `src/gmgn_twitter_intel/retrieval/token_flow_service.py`
- Modify: `src/gmgn_twitter_intel/retrieval/rolling_token_flow.py`
- Modify: `web/src/api/types.ts`

- [x] Return `evidence_highlight_best` and `evidence_highlights`.
- [x] Return `evidence_total_count` from attribution-derived counts.
- [x] Return `posts_query` so the UI can fetch all posts without guessing.
- [x] Remove `evidence` and `evidence_best` from token-flow response types.
- [x] Over-fetch rolling candidates in `TokenFlowService`, compute signal blocks, then sort by decision priority, signal score, watched mentions, velocity, mentions, and freshness.

### Task 6: Update Frontend Focus Drawer

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/api/types.ts`
- Modify: `web/src/styles.css`
- Modify: `web/src/App.test.tsx`
- Modify: `web/src/lib/format.test.ts`

- [x] Add `TokenPostsData` and `TokenPostItem` API types.
- [x] Fetch `/api/token-posts` with TanStack Query when a token is selected.
- [x] Add `全部帖子` and `信号解释` segmented controls in the focus drawer.
- [x] Default selected token focus to `全部帖子`.
- [x] Render full-post loaded count, total count, post score, reasons, and a load-more button.
- [x] Render `evidence_highlights` only in `信号解释`.
- [x] Remove code that treats token highlights as complete evidence.

### Task 7: Verify

**Commands:**

```bash
uv run pytest tests/test_token_posts_service.py tests/test_api_http.py tests/test_token_conviction_flow.py tests/test_token_attribution_flow.py tests/test_token_rolling_flow.py
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
cd web && npm test
cd web && npm run build
```

- [x] Confirm focused backend tests pass.
- [x] Confirm full backend test suite passes.
- [x] Confirm Python lint and compile checks pass.
- [x] Confirm frontend tests and build pass.
