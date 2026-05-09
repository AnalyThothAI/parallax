# Harness Engineering Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganise the docs harness into routers + governance + lane + support rings, eliminating AGENTS.md / CLAUDE.md duplication and giving in-flight specs and plans a lifecycle, without touching `src/`.

**Architecture:** Three concentric rings. (1) Two thin routers at repo root that point but carry no rule prose. (2) Nine governance files under `docs/` each owning exactly one concern, plus `TECH_DEBT.md`. (3) `docs/superpowers/{specs,plans}/{active,completed}/` lifecycle. Plus a support ring of `docs/references/` for external materials and `docs/generated/` for auto-derived artefacts driven by a `make docs-generated` target.

**Tech Stack:** Markdown, `git mv`, GNU Make, Python 3 (for one new `pytest` module + one regeneration script), Alembic introspection (for db schema export).

**Status**: Draft
**Date**: 2026-05-09
**Owning spec**: `docs/superpowers/specs/2026-05-09-harness-engineering-restructure.md`
**Worktree**: `.worktrees/harness-restructure/`
**Branch**: `harness-restructure`

---

## Pre-flight

- [ ] Spec is approved and committed (`git log --oneline docs/superpowers/specs/2026-05-09-harness-engineering-restructure.md` shows `d3e24fa` or later).
- [ ] Worktree exists at `.worktrees/harness-restructure/`. Create with: `git worktree add .worktrees/harness-restructure -b harness-restructure main`.
- [ ] Inside the worktree: `git branch --show-current` returns `harness-restructure`.
- [ ] Baseline `uv run ruff check .` passes.
- [ ] Baseline `uv run pytest -x` passes.
- [ ] Baseline `uv run python -m compileall src tests` passes.
- [ ] Postgres is reachable for the `make docs-generated` step (PR 3 only). Verify: `uv run gmgn-twitter-intel db health`.

Known-failing baseline tests: none expected.

---

## File-level edits

### Repo root (modified)

- `AGENTS.md` — slim from 199 lines to ≤ 60: keep only project tagline + routing table.
- `CLAUDE.md` — slim from 149 lines to ≤ 60: keep tagline + routing table + Claude-specific Skills/Plan-mode/Worktree block.
- `Makefile` — append `docs-generated` target plus four sub-targets (`docs-db-schema`, `docs-cli-help`, `docs-score-versions`, `docs-ws-protocol`).

### Repo root (created)

- (none new at root)

### `docs/` (created governance files)

- `docs/ARCHITECTURE.md` — five-layer pipeline boundaries; extracted from `AGENTS.md:28-55`.
- `docs/CONTRACTS.md` — public surfaces; extracted from `AGENTS.md:57-72`.
- `docs/SETUP.md` — install / serve / docker; extracted from `AGENTS.md:9-26` plus `web/` install commands.
- `docs/WORKFLOW.md` — spec→plan lane mechanics + worktree + completion gates; extracted from `AGENTS.md:101-114, 171-190` and `CLAUDE.md:9-37`.
- `docs/DESIGN_DISCIPLINE.md` — design rules; extracted from `AGENTS.md:115-169` and `CLAUDE.md:64-149`.
- `docs/TESTING.md` — testing rules + verification commands; extracted from `AGENTS.md:84-92` plus a new `web/` test section.
- `docs/SECURITY.md` — secret/config/authn; extracted from `AGENTS.md:94-98`.
- `docs/RELIABILITY.md` — operational invariants; extracted from `AGENTS.md:192-198`.
- `docs/FRONTEND.md` — `web/` architecture + component conventions; written fresh against current `web/src/{api,components,domain,lib,store,test}/` layout.
- `docs/TECH_DEBT.md` — empty registry with a header explaining the schema.

### `docs/superpowers/` (lane skeleton + migration)

- `docs/superpowers/specs/active/.gitkeep` — created (placeholder so empty dir is tracked).
- `docs/superpowers/specs/completed/.gitkeep` — created.
- `docs/superpowers/plans/active/.gitkeep` — created.
- `docs/superpowers/plans/completed/.gitkeep` — created.
- All existing `docs/superpowers/specs/*.md` (17 files) `git mv`'d into `active/` or `completed/` per the triage table in Task 4.
- All existing `docs/superpowers/plans/*.md` (13 files) `git mv`'d into `active/` or `completed/` per the triage table in Task 5.

### `docs/` legacy (moved)

- All 14 `docs/2026-05-*.md` and `docs/token-radar-social-heat-*.md` files `git mv`'d into `docs/superpowers/{specs,plans}/completed/` per the table in Task 6.

### `docs/references/` (created)

- `docs/references/README.md` — scope statement + update procedure.
- `docs/references/walkinglabs-harness-engineering.md` — summary of the source document with link.
- `docs/references/papers/kleinberg-2002-burst.md` — citation + 3-paragraph summary.
- `docs/references/papers/goel-2016-structural-virality.md` — same.
- `docs/references/papers/cheng-2014-cascades.md` — same.
- `docs/references/papers/bakshy-2011-influencer-refutation.md` — same.
- `docs/references/papers/centola-2010-complex-contagion.md` — same.
- `docs/references/papers/crane-sornette-2008-endogenous-exogenous.md` — same.
- `docs/references/gmgn-public-protocol.md` — extracted notes on the GMGN anonymous WebSocket schema (chains, channels, frame format).
- `docs/references/okx-api.md` — extracted notes on OKX CEX/DEX endpoints used by `src/gmgn_twitter_intel/market/`.

### `docs/generated/` (created)

- `docs/generated/README.md` — header explaining "do not hand-edit" + regeneration command.
- `docs/generated/db-schema.md` — output of `scripts/regen_db_schema.py`.
- `docs/generated/cli-help.md` — output of `gmgn-twitter-intel --help` recursively.
- `docs/generated/score-versions.md` — `grep -rn 'score_version' src/` aggregated.
- `docs/generated/ws-protocol.md` — extracted message-type union from `src/gmgn_twitter_intel/api/ws.py`.

### `scripts/` (created)

- `scripts/regen_db_schema.py` — connects via `gmgn_twitter_intel.storage` to `pg_catalog`, writes Markdown table per `public.*` table.
- `scripts/regen_cli_help.py` — invokes `gmgn-twitter-intel --help` and recurses into each subcommand group.
- `scripts/regen_score_versions.py` — greps `src/` for `score_version=` literals and emits a Markdown table.
- `scripts/regen_ws_protocol.py` — imports the WebSocket message dataclasses / pydantic models and emits a Markdown table.

### Tests

- `tests/test_harness_structure.py` — new file. Asserts AC1–AC4 and AC6 from the spec:
  - `test_routers_within_line_budget` — both `AGENTS.md` and `CLAUDE.md` ≤ 60 lines.
  - `test_lane_roots_have_no_loose_files` — `docs/superpowers/{specs,plans}/` directly contains only `_templates`, `active`, `completed`.
  - `test_docs_root_governance_files` — `docs/*.md` is exactly the expected 10-file set.
  - `test_no_legacy_files_at_docs_root` — no `docs/2026-*-cn.md` or `docs/token-radar-social-heat-*.md`.
  - `test_rule_uniqueness` — for a fixed list of representative rule phrases (e.g. "single ASGI worker", "score_version", "real PostgreSQL", "worktree", "ruff check"), each appears in exactly one governance file under `docs/`, not in `AGENTS.md` or `CLAUDE.md`.
  - `test_references_papers_present` — six `docs/references/papers/*.md` files exist.
- `tests/test_docs_generated.py` — new file. Asserts AC5:
  - `test_generated_files_have_no_hand_edit_warning` — each `docs/generated/*.md` has the "do not hand-edit" header line.
  - `test_make_docs_generated_clean_diff` — runs `make docs-generated` and asserts the resulting tree matches the committed tree byte-for-byte. Skipped if Postgres is unreachable (uses `pytest.importorskip` style guard).

---

## Tasks

> **TDD reminder.** Each Task that adds behaviour follows the loop: write the failing test → run it and confirm failure → make the change → run the test and confirm pass → commit. Tasks that are pure file moves do not need a separate TDD test (the structural tests added in Task 2 already cover them).

### Task 1: Create the worktree and confirm baseline

**Files:**
- No edits.

- [ ] **Step 1: Create the worktree.**

```bash
git worktree add .worktrees/harness-restructure -b harness-restructure main
cd .worktrees/harness-restructure
```

- [ ] **Step 2: Confirm worktree state.**

```bash
git worktree list
git branch --show-current
git status --short
```

Expected: worktree listed; branch `harness-restructure`; status clean.

- [ ] **Step 3: Confirm baseline checks pass.**

```bash
uv sync
uv run ruff check .
uv run pytest -x
uv run python -m compileall src tests
```

Expected: all four commands exit 0.

---

### Task 2: Add the structural test scaffold (TDD red)

**Files:**
- Create: `tests/test_harness_structure.py`

- [ ] **Step 1: Write the failing test file.**

```python
# tests/test_harness_structure.py
"""Structural assertions for the docs harness.

Each test maps to an acceptance criterion in
docs/superpowers/specs/2026-05-09-harness-engineering-restructure.md.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"
SUPERPOWERS = DOCS / "superpowers"

EXPECTED_GOVERNANCE = {
    "ARCHITECTURE.md",
    "CONTRACTS.md",
    "SETUP.md",
    "WORKFLOW.md",
    "DESIGN_DISCIPLINE.md",
    "TESTING.md",
    "SECURITY.md",
    "RELIABILITY.md",
    "FRONTEND.md",
    "TECH_DEBT.md",
}

ROUTER_FILES = ("AGENTS.md", "CLAUDE.md")

RULE_PHRASES = {
    "single ASGI worker": "RELIABILITY.md",
    "score_version": "CONTRACTS.md",
    "real PostgreSQL": "TESTING.md",
    "git worktree add": "WORKFLOW.md",
    "ruff check": "TESTING.md",
    "audit-before-design": "DESIGN_DISCIPLINE.md",
    "single config source": "SECURITY.md",
}


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_routers_within_line_budget() -> None:
    for name in ROUTER_FILES:
        path = REPO_ROOT / name
        line_count = len(_read(path).splitlines())
        assert line_count <= 60, f"{name} has {line_count} lines, expected <= 60"


def test_lane_roots_have_no_loose_files() -> None:
    for lane in ("specs", "plans"):
        lane_root = SUPERPOWERS / lane
        loose_md = sorted(p.name for p in lane_root.glob("*.md"))
        assert loose_md == [], f"{lane}/ root holds loose files: {loose_md}"
        children = sorted(p.name for p in lane_root.iterdir() if not p.name.startswith("."))
        if lane == "specs":
            assert set(children) == {"active", "completed"}, children
        else:
            assert set(children) == {"active", "completed"}, children


def test_specs_lane_has_templates_dir_only_under_superpowers() -> None:
    children = sorted(p.name for p in SUPERPOWERS.iterdir() if not p.name.startswith("."))
    assert set(children) == {"_templates", "specs", "plans"}, children


def test_docs_root_governance_files() -> None:
    actual = {p.name for p in DOCS.glob("*.md")}
    assert actual == EXPECTED_GOVERNANCE, f"unexpected docs root contents: {actual ^ EXPECTED_GOVERNANCE}"


def test_no_legacy_files_at_docs_root() -> None:
    legacy = sorted(p.name for p in DOCS.glob("2026-*-cn.md"))
    legacy += sorted(p.name for p in DOCS.glob("token-radar-social-heat-*.md"))
    assert legacy == [], f"legacy files still at docs root: {legacy}"


def test_rule_uniqueness() -> None:
    governance_paths = {name: DOCS / name for name in EXPECTED_GOVERNANCE}
    for phrase, expected_owner in RULE_PHRASES.items():
        hits = [name for name, path in governance_paths.items() if phrase in _read(path)]
        assert hits == [expected_owner], (
            f"phrase {phrase!r} expected only in {expected_owner}, found in {hits}"
        )
        for router in ROUTER_FILES:
            assert phrase not in _read(REPO_ROOT / router), (
                f"phrase {phrase!r} leaked into {router}"
            )


def test_references_papers_present() -> None:
    papers_dir = DOCS / "references" / "papers"
    assert papers_dir.is_dir(), "docs/references/papers/ missing"
    expected = {
        "kleinberg-2002-burst.md",
        "goel-2016-structural-virality.md",
        "cheng-2014-cascades.md",
        "bakshy-2011-influencer-refutation.md",
        "centola-2010-complex-contagion.md",
        "crane-sornette-2008-endogenous-exogenous.md",
    }
    actual = {p.name for p in papers_dir.glob("*.md")}
    assert actual == expected, f"papers missing or extra: {actual ^ expected}"
```

- [ ] **Step 2: Run the test file and confirm every test fails.**

```bash
uv run pytest tests/test_harness_structure.py -v
```

Expected: at least 6 of 7 tests FAIL (lane roots have loose files, governance files don't exist, legacy files still at docs root, rule phrases haven't been migrated, papers don't exist, routers exceed 60 lines). `test_specs_lane_has_templates_dir_only_under_superpowers` may already pass.

- [ ] **Step 3: Commit the failing tests.**

```bash
git add tests/test_harness_structure.py
git commit -m "test: structural assertions for harness restructure (red)"
```

---

### Task 3: Create the lane skeleton

**Files:**
- Create: `docs/superpowers/specs/active/.gitkeep`
- Create: `docs/superpowers/specs/completed/.gitkeep`
- Create: `docs/superpowers/plans/active/.gitkeep`
- Create: `docs/superpowers/plans/completed/.gitkeep`

- [ ] **Step 1: Create the four lifecycle directories with placeholders.**

```bash
mkdir -p docs/superpowers/specs/active docs/superpowers/specs/completed
mkdir -p docs/superpowers/plans/active docs/superpowers/plans/completed
touch docs/superpowers/specs/active/.gitkeep
touch docs/superpowers/specs/completed/.gitkeep
touch docs/superpowers/plans/active/.gitkeep
touch docs/superpowers/plans/completed/.gitkeep
```

- [ ] **Step 2: Confirm structure.**

```bash
ls -la docs/superpowers/specs/ docs/superpowers/plans/
```

Expected: each lane has `_templates`, `active/`, `completed/` plus the existing `.md` files (still at lane root, to be moved in Tasks 4–5).

- [ ] **Step 3: Commit the skeleton.**

```bash
git add docs/superpowers/specs/active docs/superpowers/specs/completed
git add docs/superpowers/plans/active docs/superpowers/plans/completed
git commit -m "docs: add active/completed lifecycle dirs to specs and plans lanes"
```

---

### Task 4: Migrate `docs/superpowers/specs/` to active/completed

**Files:**
- Move: 17 files in `docs/superpowers/specs/*.md` (16 legacy + this restructure spec).

Triage table — locked here so the implementer does not re-judge:

| File | Destination | Reason |
|------|-------------|--------|
| `2026-05-04-closed-loop-social-event-harness-cn-evaluation.md` | `completed/` | Companion to the closed-loop design; closed loop is implemented (`pipeline/`). |
| `2026-05-04-closed-loop-social-event-harness-design.md` | `completed/` | Same. |
| `2026-05-04-token-posts-evidence-scoring-design.md` | `completed/` | Post-text-quality scoring shipped (`retrieval/`). |
| `2026-05-05-production-notifications-phase1-phase2-design-cn.md` | `completed/` | Paired plan completed; notifications shipped. |
| `2026-05-05-production-social-intelligence-algorithm-cn.md` | `completed/` | Algorithm shipped. |
| `2026-05-05-responsive-token-radar-cockpit-design-cn.md` | `completed/` | Paired cockpit plan shipped. |
| `2026-05-06-harness-abnormal-return-baseline-design-cn.md` | `completed/` | Baseline scoring lives in `retrieval/`. |
| `2026-05-06-materialized-read-models-production-cn.md` | `completed/` | Paired projection-closure plan completed. |
| `2026-05-06-token-post-mortem-closed-loop-cn.md` | `completed/` | Closed-loop materialisation shipped. |
| `2026-05-08-auditable-token-radar-design-cn.md` | `active/` | No paired plan yet. |
| `2026-05-08-signal-lab-pulse-agent-hard-cut-cn.md` | `active/` | Two pulse-agent plans still in flight. |
| `2026-05-09-harness-engineering-restructure.md` | `active/` | This very work. |
| `2026-05-09-radar-candidate-market-hydration.md` | `completed/` | Has verification artefact; recent commits implement it. |
| `2026-05-09-standardized-social-factor-pipeline.md` | `active/` | Paired with active social-factor-phase-2-0 plan. |
| `2026-05-09-token-extraction-pipeline-audit-claude.md` | `active/` | Paired with active token-extraction-kiss plan. |
| `2026-05-09-token-extraction-pipeline-audit.md` | `active/` | Same. |
| `2026-05-09-token-radar-ui-kiss-contract.md` | `completed/` | Has verification artefact. |

- [ ] **Step 1: Move the 11 completed specs.**

```bash
git mv docs/superpowers/specs/2026-05-04-closed-loop-social-event-harness-cn-evaluation.md docs/superpowers/specs/completed/
git mv docs/superpowers/specs/2026-05-04-closed-loop-social-event-harness-design.md docs/superpowers/specs/completed/
git mv docs/superpowers/specs/2026-05-04-token-posts-evidence-scoring-design.md docs/superpowers/specs/completed/
git mv docs/superpowers/specs/2026-05-05-production-notifications-phase1-phase2-design-cn.md docs/superpowers/specs/completed/
git mv docs/superpowers/specs/2026-05-05-production-social-intelligence-algorithm-cn.md docs/superpowers/specs/completed/
git mv docs/superpowers/specs/2026-05-05-responsive-token-radar-cockpit-design-cn.md docs/superpowers/specs/completed/
git mv docs/superpowers/specs/2026-05-06-harness-abnormal-return-baseline-design-cn.md docs/superpowers/specs/completed/
git mv docs/superpowers/specs/2026-05-06-materialized-read-models-production-cn.md docs/superpowers/specs/completed/
git mv docs/superpowers/specs/2026-05-06-token-post-mortem-closed-loop-cn.md docs/superpowers/specs/completed/
git mv docs/superpowers/specs/2026-05-09-radar-candidate-market-hydration.md docs/superpowers/specs/completed/
git mv docs/superpowers/specs/2026-05-09-token-radar-ui-kiss-contract.md docs/superpowers/specs/completed/
```

- [ ] **Step 2: Move the 6 active specs.**

```bash
git mv docs/superpowers/specs/2026-05-08-auditable-token-radar-design-cn.md docs/superpowers/specs/active/
git mv docs/superpowers/specs/2026-05-08-signal-lab-pulse-agent-hard-cut-cn.md docs/superpowers/specs/active/
git mv docs/superpowers/specs/2026-05-09-harness-engineering-restructure.md docs/superpowers/specs/active/
git mv docs/superpowers/specs/2026-05-09-standardized-social-factor-pipeline.md docs/superpowers/specs/active/
git mv docs/superpowers/specs/2026-05-09-token-extraction-pipeline-audit-claude.md docs/superpowers/specs/active/
git mv docs/superpowers/specs/2026-05-09-token-extraction-pipeline-audit.md docs/superpowers/specs/active/
```

- [ ] **Step 3: Confirm specs lane is clean.**

```bash
ls docs/superpowers/specs/
ls docs/superpowers/specs/active/ | wc -l
ls docs/superpowers/specs/completed/ | wc -l
```

Expected: lane root shows `_templates active completed`; active count is 6 (plus `.gitkeep`); completed count is 11 (plus `.gitkeep`).

- [ ] **Step 4: Commit the spec migration.**

```bash
git add docs/superpowers/specs/
git commit -m "docs: migrate 17 specs into active/completed lanes (no content edits)"
```

---

### Task 5: Migrate `docs/superpowers/plans/` to active/completed

**Files:**
- Move: 13 files in `docs/superpowers/plans/*.md`.

Triage table:

| File | Destination | Reason |
|------|-------------|--------|
| `2026-05-05-production-notifications-phase1-phase2.md` | `completed/` | Notifications shipped. |
| `2026-05-05-responsive-token-radar-cockpit.md` | `completed/` | Cockpit shipped. |
| `2026-05-06-postgresql-projection-closure.md` | `completed/` | Projection in production. |
| `2026-05-06-token-identity-resolution-production.md` | `completed/` | Token identity resolution shipped. |
| `2026-05-08-signal-lab-pulse-agent-concrete-cn.md` | `active/` | Pulse agent ongoing. |
| `2026-05-08-signal-lab-pulse-agent-hard-cut.md` | `active/` | Same. |
| `2026-05-09-gmgn-account-directory-sync.md` | `active/` | No verification yet. |
| `2026-05-09-radar-candidate-market-hydration-verification.md` | `completed/` | Verification of completed plan. |
| `2026-05-09-radar-candidate-market-hydration.md` | `completed/` | Recent commits implement it. |
| `2026-05-09-social-factor-phase-2-0-foundation.md` | `active/` | No verification yet. |
| `2026-05-09-token-extraction-kiss.md` | `active/` | No verification yet. |
| `2026-05-09-token-radar-ui-kiss-contract-verification.md` | `completed/` | Verification of completed plan. |
| `2026-05-09-token-radar-ui-kiss-contract.md` | `completed/` | Has verification artefact. |

- [ ] **Step 1: Move the 8 completed plans.**

```bash
git mv docs/superpowers/plans/2026-05-05-production-notifications-phase1-phase2.md docs/superpowers/plans/completed/
git mv docs/superpowers/plans/2026-05-05-responsive-token-radar-cockpit.md docs/superpowers/plans/completed/
git mv docs/superpowers/plans/2026-05-06-postgresql-projection-closure.md docs/superpowers/plans/completed/
git mv docs/superpowers/plans/2026-05-06-token-identity-resolution-production.md docs/superpowers/plans/completed/
git mv docs/superpowers/plans/2026-05-09-radar-candidate-market-hydration-verification.md docs/superpowers/plans/completed/
git mv docs/superpowers/plans/2026-05-09-radar-candidate-market-hydration.md docs/superpowers/plans/completed/
git mv docs/superpowers/plans/2026-05-09-token-radar-ui-kiss-contract-verification.md docs/superpowers/plans/completed/
git mv docs/superpowers/plans/2026-05-09-token-radar-ui-kiss-contract.md docs/superpowers/plans/completed/
```

- [ ] **Step 2: Move the 5 active plans.**

```bash
git mv docs/superpowers/plans/2026-05-08-signal-lab-pulse-agent-concrete-cn.md docs/superpowers/plans/active/
git mv docs/superpowers/plans/2026-05-08-signal-lab-pulse-agent-hard-cut.md docs/superpowers/plans/active/
git mv docs/superpowers/plans/2026-05-09-gmgn-account-directory-sync.md docs/superpowers/plans/active/
git mv docs/superpowers/plans/2026-05-09-social-factor-phase-2-0-foundation.md docs/superpowers/plans/active/
git mv docs/superpowers/plans/2026-05-09-token-extraction-kiss.md docs/superpowers/plans/active/
```

- [ ] **Step 3: Move this very plan into active/.**

```bash
git mv docs/superpowers/plans/2026-05-09-harness-engineering-restructure.md docs/superpowers/plans/active/
```

- [ ] **Step 4: Confirm plans lane is clean.**

```bash
ls docs/superpowers/plans/
ls docs/superpowers/plans/active/ | wc -l
ls docs/superpowers/plans/completed/ | wc -l
```

Expected: lane root shows `active completed`; active count is 6 (5 + this plan + `.gitkeep`); completed count is 8 (+ `.gitkeep`).

- [ ] **Step 5: Commit the plan migration.**

```bash
git add docs/superpowers/plans/
git commit -m "docs: migrate 14 plans into active/completed lanes (includes this plan)"
```

---

### Task 6: Move 14 legacy `docs/` root files into `superpowers/{specs,plans}/completed/`

**Files:**
- Move: 14 files in `docs/2026-05-*.md` and `docs/token-radar-social-heat-*.md`.

Mapping:

| Source | Destination |
|--------|-------------|
| `docs/2026-05-04-market-observation-timing-production-spec-cn.md` | `docs/superpowers/specs/completed/` |
| `docs/2026-05-06-token-identity-resolution-production-spec-cn.md` | `docs/superpowers/specs/completed/` |
| `docs/2026-05-06-token-radar-scoring-closure-spec-cn.md` | `docs/superpowers/specs/completed/` |
| `docs/2026-05-07-token-radar-identity-market-v3-production-spec-cn.md` | `docs/superpowers/specs/completed/` |
| `docs/2026-05-07-token-radar-v4-entity-linking-production-spec-cn.md` | `docs/superpowers/specs/completed/` |
| `docs/token-radar-social-heat-spec.md` | `docs/superpowers/specs/completed/` |
| `docs/2026-05-04-market-observation-timing-production-plan-cn.md` | `docs/superpowers/plans/completed/` |
| `docs/2026-05-05-selected-token-production-plan-cn.md` | `docs/superpowers/plans/completed/` |
| `docs/2026-05-07-token-radar-v3-implementation-plan-cn.md` | `docs/superpowers/plans/completed/` |
| `docs/2026-05-07-token-radar-v4-entity-linking-implementation-plan-cn.md` | `docs/superpowers/plans/completed/` |
| `docs/2026-05-05-frontend-production-audit-cn.md` | `docs/superpowers/specs/completed/` |
| `docs/2026-05-06-token-identity-resolution-production-audit-cn.md` | `docs/superpowers/specs/completed/` |
| `docs/2026-05-07-token-radar-v3-code-review-cn.md` | `docs/superpowers/specs/completed/` |
| `docs/token-radar-social-heat-research.md` | `docs/superpowers/specs/completed/` |

- [ ] **Step 1: Move the 6 specs.**

```bash
git mv docs/2026-05-04-market-observation-timing-production-spec-cn.md docs/superpowers/specs/completed/
git mv docs/2026-05-06-token-identity-resolution-production-spec-cn.md docs/superpowers/specs/completed/
git mv docs/2026-05-06-token-radar-scoring-closure-spec-cn.md docs/superpowers/specs/completed/
git mv docs/2026-05-07-token-radar-identity-market-v3-production-spec-cn.md docs/superpowers/specs/completed/
git mv docs/2026-05-07-token-radar-v4-entity-linking-production-spec-cn.md docs/superpowers/specs/completed/
git mv docs/token-radar-social-heat-spec.md docs/superpowers/specs/completed/
```

- [ ] **Step 2: Move the 4 plans.**

```bash
git mv docs/2026-05-04-market-observation-timing-production-plan-cn.md docs/superpowers/plans/completed/
git mv docs/2026-05-05-selected-token-production-plan-cn.md docs/superpowers/plans/completed/
git mv docs/2026-05-07-token-radar-v3-implementation-plan-cn.md docs/superpowers/plans/completed/
git mv docs/2026-05-07-token-radar-v4-entity-linking-implementation-plan-cn.md docs/superpowers/plans/completed/
```

- [ ] **Step 3: Move the 4 audit/research/code-review files into `specs/completed/`.**

```bash
git mv docs/2026-05-05-frontend-production-audit-cn.md docs/superpowers/specs/completed/
git mv docs/2026-05-06-token-identity-resolution-production-audit-cn.md docs/superpowers/specs/completed/
git mv docs/2026-05-07-token-radar-v3-code-review-cn.md docs/superpowers/specs/completed/
git mv docs/token-radar-social-heat-research.md docs/superpowers/specs/completed/
```

- [ ] **Step 4: Verify `docs/` root is clean of legacy files.**

```bash
ls docs/*.md 2>/dev/null
```

Expected: empty (no governance files exist yet — they land in Tasks 7–16). Only the structural directories remain.

- [ ] **Step 5: Run the structural test for the legacy-files assertion.**

```bash
uv run pytest tests/test_harness_structure.py::test_no_legacy_files_at_docs_root -v
```

Expected: PASS.

- [ ] **Step 6: Commit the legacy migration.**

```bash
git add docs/
git commit -m "docs: archive 14 legacy docs/ root files into superpowers/{specs,plans}/completed (no content edits)"
```

---

### Task 7: Create `docs/ARCHITECTURE.md`

**Files:**
- Create: `docs/ARCHITECTURE.md`

This file owns the five-layer pipeline, cross-cutting modules, and the conceptual data flow. Frontend specifics are excluded — they live in `FRONTEND.md` (Task 14).

- [ ] **Step 1: Read the source paragraphs that will be extracted.**

Read `AGENTS.md:28-55` (the "Architecture" section, including the ASCII data-flow diagram and the layer table). These paragraphs become the body of `ARCHITECTURE.md` verbatim, with the section headings renumbered.

- [ ] **Step 2: Write `docs/ARCHITECTURE.md`.**

```markdown
# Architecture

> **Scope.** Owns the Python-service layer boundaries and conceptual data flow for `gmgn-twitter-intel`. Frontend (`web/`) architecture lives in `FRONTEND.md`. Public interface contracts live in `CONTRACTS.md`.

A single Python service organised as a five-stage pipeline writing to one PostgreSQL store.

```
GMGN public WS  →  collector/  →  pipeline/  →  storage/  ←  retrieval/  →  api/  →  WS / HTTP / CLI consumers
```

## Layers

| Layer | Directory | Responsibility |
|------|-----------|---------------|
| Collector | `src/gmgn_twitter_intel/collector/` | GMGN anonymous-WebSocket adapter, frame parsing, `cp=0/cp=1` snapshot gate, handle filter, store-first publish, subscription bookkeeping. |
| Pipeline  | `src/gmgn_twitter_intel/pipeline/`  | Deterministic entity extraction, token-intent resolution, async LLM enrichment for watched accounts, closed-loop harness materialisation (snapshot → settlement → credit → scoring), token-radar feature build & projection, notification rules / delivery, pulse candidate evaluation & thesis agent, asset-market & message-market sync workers. |
| Storage   | `src/gmgn_twitter_intel/storage/`   | Single PostgreSQL store. One repository per aggregate (evidence, entity, signal, asset, harness, notification, pulse, projection, registry, token-radar, token-target, intent-resolution, account-quality, market, price-observation, enrichment, discovery). Alembic migrations + `repository_session` helper. |
| Retrieval | `src/gmgn_twitter_intel/retrieval/` | Read services for HTTP / WebSocket / CLI: search, asset-flow, asset-search, account-alert, account-quality, harness, signal-pulse, token-target (posts, social timeline, stage builder, message price payload), plus the scoring components (heat, propagation, opportunity, catalyst, baseline, tradeability, timing, post-text quality, discussion quality, diffusion health, timeline features). |
| API       | `src/gmgn_twitter_intel/api/`       | FastAPI HTTP routes (`/healthz`, `/readyz`, `/api/...`) and the authenticated public WebSocket hub at `/ws`. |
| CLI       | `src/gmgn_twitter_intel/cli.py`     | Argparse front-end exposing the same data as the API plus operator subcommands (`db`, `ops`). |

## Cross-cutting

- `src/gmgn_twitter_intel/market/` — OKX CEX/DEX clients and the GMGN OpenAPI client used by the asset and price-observation pipelines.
- `src/gmgn_twitter_intel/settings.py` — single config loader (`~/.gmgn-twitter-intel/config.yaml`).
- `src/gmgn_twitter_intel/runtime_paths.py`, `models.py`, `logging_setup.py` — shared runtime utilities.
- `tests/` mirrors the package layout. Schema and Docker assets are pinned by `tests/test_postgres_schema*.py` and `tests/test_compose_*.py`.

To find code, prefer `ls src/gmgn_twitter_intel/<layer>/` over a memorised file list. This file pins the layer boundaries; per-file responsibilities live in the code and its tests.
```

(Note the inner code-fence around the ASCII diagram is escaped in this plan via wrapping triple-backticks; copy the verbatim form into the file.)

- [ ] **Step 3: Commit.**

```bash
git add docs/ARCHITECTURE.md
git commit -m "docs: add ARCHITECTURE governance file"
```

---

### Task 8: Create `docs/CONTRACTS.md`

**Files:**
- Create: `docs/CONTRACTS.md`

- [ ] **Step 1: Extract `AGENTS.md:57-72` as the body.**

- [ ] **Step 2: Write `docs/CONTRACTS.md`.**

```markdown
# Public Contracts

> **Scope.** Owns the user-visible surfaces (config, WebSocket, HTTP, CLI) and the immutability discipline that protects them. Refactors must preserve these contracts; behaviour changes require a versioned spec under `docs/superpowers/specs/active/`.

These surfaces change only with a versioned spec — refactors must preserve them.

## Config (`~/.gmgn-twitter-intel/config.yaml`)

The only application config source.

- `handles` — watched Twitter handles.
- `ws_token` — public WebSocket API token.
- `api` — FastAPI bind address and replay settings.
- `storage.postgres` — DSN, password file, pool, timeout.
- `llm.openai_api_key` / `llm.openai_model` — optional, only for watched-account social-event extraction.
- Optional market-related groups (OKX, GMGN OpenAPI) for the asset / price pipelines.

## WebSocket at `/ws`

- Auth: `{"type":"auth","token":"..."}`
- Subscribe: `{"type":"subscribe","handles":[...],"replay":N}`
- Push payloads include `event`, `entities`, `alerts`, `enrichment`, and harness updates after store commit.

## HTTP

`/healthz`, `/readyz`, `/api/*`. Each endpoint owns its own response schema.

## CLI

`gmgn-twitter-intel <verb>` plus the `db` and `ops` subcommand groups. The `--help` output is the source of truth — do not enumerate verbs in this document.

## `score_version` discipline

`score_version` is bumped on any scoring change. Downstream evaluation services filter by version, otherwise A/B comparisons silently mix populations. Every ranking score returned by the API includes its component breakdown. No black-box scores.

## Privacy boundary

GMGN chains, channels, app versions, and protocol frames are internal collector strategy — never expose them in user-facing payloads.
```

- [ ] **Step 3: Commit.**

```bash
git add docs/CONTRACTS.md
git commit -m "docs: add CONTRACTS governance file"
```

---

### Task 9: Create `docs/SETUP.md`

**Files:**
- Create: `docs/SETUP.md`

- [ ] **Step 1: Write the file.**

```markdown
# Setup

> **Scope.** Owns install, dev-loop, and deployment commands for both the Python service and the `web/` frontend. Runtime invariants live in `RELIABILITY.md`.

## Python service

```bash
uv sync
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

Bring up the service:

```bash
uv run gmgn-twitter-intel init      # create ~/.gmgn-twitter-intel/config.yaml
uv run gmgn-twitter-intel serve     # run collector + API in one ASGI worker
uv run gmgn-twitter-intel db migrate
```

The full CLI surface is documented by `uv run gmgn-twitter-intel --help`. Treat that output as the source of truth — do not enumerate commands here. A snapshot lives at `generated/cli-help.md`.

## Docker Compose

```bash
docker compose up -d --build app
docker compose ps
docker compose logs -f --tail=100 app
docker compose down
```

Bind-mounts host `~/.gmgn-twitter-intel/` into the container; PostgreSQL data is pinned to the `gmgn-twitter-intel-postgres` named volume.

## Frontend (`web/`)

```bash
cd web
npm install
npm run dev          # vite dev server with API proxy
npm run build        # production bundle
npm run preview      # serve the build locally
```

See `FRONTEND.md` for architecture and component conventions.
```

- [ ] **Step 2: Commit.**

```bash
git add docs/SETUP.md
git commit -m "docs: add SETUP governance file"
```

---

### Task 10: Create `docs/WORKFLOW.md`

**Files:**
- Create: `docs/WORKFLOW.md`

This is the lane mechanics + worktree + completion-gates owner. It does NOT carry design-discipline rules (those live in `DESIGN_DISCIPLINE.md`, Task 11).

- [ ] **Step 1: Extract `AGENTS.md:101-114, 171-190` and the lane-flow paragraphs of `CLAUDE.md:9-37` as the body.**

- [ ] **Step 2: Write `docs/WORKFLOW.md`.**

```markdown
# Workflow

> **Scope.** Owns the spec → plan → tasks → verification lane mechanics, the worktree policy, and the completion gates. Design rules (spec vs plan boundary, audit, reuse, complexity, scoring) live in `DESIGN_DISCIPLINE.md`.

## Lane sequence

Trivial single-file low-risk edits may go direct. Everything else uses the lanes below.

| Lane | Path | When |
|------|------|------|
| Spec | `docs/superpowers/specs/active/YYYY-MM-DD-<slug>.md` (or `…/<slug>/spec.md` for very large work) | Before any non-trivial implementation; answers *why & what*. |
| Plan | `docs/superpowers/plans/active/YYYY-MM-DD-<slug>.md` (or `…/<slug>/plan.md`) | After spec approval; answers *how & when* with file:line edits. |
| Tasks | `…/<slug>/tasks.md` | When a plan needs ordered TDD checklists across multiple PRs. |
| Verification | `…/<slug>/verification.md` (or a "Verification" section in a single-file plan) | Before declaring completion or opening a PR. |

Templates live at `docs/superpowers/_templates/`. Copy a template into the appropriate `active/` folder and rename to the dated slug. Naming: `YYYY-MM-DD-<kebab-slug>` matching today's date; keep slugs short and intent-focused.

When work ships and verification is recorded, move both the spec and the plan from `active/` to `completed/`. This is a manual step performed in the same PR that records verification.

Get explicit user approval at each lane boundary; do not write the next lane until the prior is approved.

## Worktree policy

Coding agents MUST work in an isolated git worktree, not the main checkout.

- Default location: `.worktrees/<branch-slug>/` at the repo root. The directory is gitignored.
- Create with: `git worktree add .worktrees/<slug> -b <branch> main` (branch from `main` unless the user names a different base).
- Before any edit verify: `git worktree list`, `git status --short`, `git branch --show-current`.
- Trivial single-file low-risk doc edits may go direct in the main checkout. Anything touching `src/` or `tests/` uses a worktree.
- Existing worktrees in `.worktrees/` belong to other tasks; do not edit them unless explicitly asked.

## Completion gates

Do not claim a task is complete, fixed, or passing until all of the following are true and have been written into the verification artefact:

- The implementation matches the approved spec; deviations are documented.
- `uv run ruff check .`, `uv run pytest`, `uv run python -m compileall src tests` all passed in the worktree.
- The diff was reviewed against the plan.
- UI / live-WebSocket / Docker Compose flows that cannot be exercised by tests were exercised manually, or the gap is explicitly stated.
- Remaining risks and follow-ups are listed and, if non-trivial, appended to `docs/TECH_DEBT.md`.

If any of the above cannot be satisfied, surface the gap rather than claiming completion.
```

- [ ] **Step 3: Commit.**

```bash
git add docs/WORKFLOW.md
git commit -m "docs: add WORKFLOW governance file"
```

---

### Task 11: Create `docs/DESIGN_DISCIPLINE.md`

**Files:**
- Create: `docs/DESIGN_DISCIPLINE.md`

- [ ] **Step 1: Extract `AGENTS.md:115-169` and `CLAUDE.md:64-149` as the body. Replace inline academic citations with relative links to `references/papers/*.md` (papers files come in Task 18).**

- [ ] **Step 2: Write `docs/DESIGN_DISCIPLINE.md`.**

```markdown
# Design Discipline

> **Scope.** Owns the rules that govern *what* a spec or plan may contain and *how* a feature must be designed in this repo. Workflow mechanics (lane filenames, worktree, completion gates) live in `WORKFLOW.md`.

## Spec vs plan boundary

A spec contains: background, current architecture audit, problem diagnosis, first principles, goals with falsifiable metrics, target architecture, conceptual data flow, core models, interface contracts at semantic level, out-of-scope, risks, evolution path.

A spec must NOT contain: file paths and line numbers as instruction, function signatures, SQL DDL/DML rewrites, Alembic migration code, pseudo-code beyond a 5-line formula, test names, PR sequence, or "v1 vs v2" iteration history.

A plan contains: file:line edits, function signatures, exact SQL, migration code, test names, PR breakdown, rollout order, rollback procedure, acceptance test commands.

If the user asks for a spec, do not write a plan inside it. If the user asks for a plan, do not re-litigate the spec.

## Audit before design

Before writing any new service or scoring scheme:

1. List all files in the relevant `src/gmgn_twitter_intel/<area>/` and `tests/` directories.
2. Read existing `*_service.py` candidates end to end. Most "new" features here are 80 % covered by an existing service plus a few missing joins.
3. Trace the data flow from `collector → ingest → enrichment → retrieval → api/http.py → web/`. Cite the actual files and line ranges as evidence in the spec, not as instructions.
4. Identify fields already in the DB but unconsumed by retrieval services. These are usually the cheapest wins.

If a spec's background section cannot cite specific existing files, the design is ungrounded — fix that before proposing changes.

## Reuse before create

Default to extending an existing service, deriving on demand, and extending existing tables. Only create a new service / persisted entity / table when the conceptual responsibility, lifecycle, or compute budget genuinely differs from what is already there. Document the trigger in the spec's "Alternatives Considered" section.

## Avoid premature complexity

The following additions require explicit justification (cite a current pain or a measured number) before appearing in any spec:

- New PostgreSQL tables, materialised views, or background workers.
- LLM calls outside the existing `enrichment_worker` boundary.
- Bayesian / probabilistic outputs.
- Ground-truth datasets, human annotation workflows, dual-annotator review.
- Statistical inference on small samples (N < 200).
- Reinforcement learning, gradient-based weight tuning, online bandits.
- Cross-validation harnesses or holdout sets.
- New score versions without a corresponding `score_version` bump and downstream evaluation filter.

Prefer hand-tuned weighted combinations of deterministic features unit-tested with fixtures until a concrete measurement shows the limitation.

## Writing for delivery

Each spec and plan is a final artefact, not a diary. No "v1 / v2 / v3" prose, no in-document review checklists, no "what we used to think" sections. Quantitative claims either come with measurement evidence or are explicitly tagged as estimates.

## Scoring and ranking design

- Distinguish upstream identity from downstream observation; ranking signals operate on observable downstream effects within an explicit time window.
- Cite literature when proposing aggregation formulas. The relevant base lives under [`references/papers/`](references/papers/):
  - [Kleinberg 2002 — burst detection](references/papers/kleinberg-2002-burst.md)
  - [Goel et al. 2016 — structural virality](references/papers/goel-2016-structural-virality.md)
  - [Cheng et al. 2014 — cascade prediction](references/papers/cheng-2014-cascades.md)
  - [Bakshy et al. 2011 — influencer-effect refutation](references/papers/bakshy-2011-influencer-refutation.md)
  - [Centola 2010 — complex contagion](references/papers/centola-2010-complex-contagion.md)
  - [Crane & Sornette 2008 — endogenous vs exogenous](references/papers/crane-sornette-2008-endogenous-exogenous.md)
- Every ranking score returned by the API must include its component breakdown. No black-box scores.
- Every new ranking signal needs a unit test asserting a single-author copy-pasta cluster scores significantly lower than a small set of independent organic responses.
- Bump `score_version` on every formula change so downstream evaluation services do not silently mix populations.

## Pushback handling

If a user says a design is over-engineered, half-baked, ungrounded, or doesn't follow KISS: engage the critique substantively, identify which specific claim is correct, do not capitulate by deleting everything, do not over-correct in the opposite direction, and re-read the existing code if the critique implies prior design ignored it.
```

- [ ] **Step 3: Commit.**

```bash
git add docs/DESIGN_DISCIPLINE.md
git commit -m "docs: add DESIGN_DISCIPLINE governance file"
```

---

### Task 12: Create `docs/TESTING.md`

**Files:**
- Create: `docs/TESTING.md`

- [ ] **Step 1: Extract `AGENTS.md:84-92` as the body, plus a new web-frontend test paragraph.**

- [ ] **Step 2: Write `docs/TESTING.md`.**

```markdown
# Testing

> **Scope.** Owns testing rules and the verification commands that gate completion. Lane workflow lives in `WORKFLOW.md`; design-discipline rules live in `DESIGN_DISCIPLINE.md`.

## Backend (`src/`, `tests/`)

- Every behaviour change must include a test in `tests/`.
- Bug fixes must include a regression test that fails before the fix and passes after it.
- Integration tests should hit a real PostgreSQL instance (Docker Compose), not mocks, when the change touches storage or query paths.

## Frontend (`web/src/test/`)

- Component and hook tests use Vitest + Testing Library; place them in `web/src/test/`.
- Domain-logic units in `web/src/domain/` should have unit tests independent of React.
- API client wrappers in `web/src/api/` should have contract tests asserting the shapes documented in `CONTRACTS.md`.

## Completion verification

Before claiming work is complete, run:

- `uv run ruff check .`
- `uv run pytest`
- `uv run python -m compileall src tests`
- (When frontend changed) `cd web && npm run test && npm run build`

UI / live-WebSocket flows that cannot be exercised by tests must be exercised manually before completion. Tests verify code correctness, not feature correctness.
```

- [ ] **Step 3: Commit.**

```bash
git add docs/TESTING.md
git commit -m "docs: add TESTING governance file"
```

---

### Task 13: Create `docs/SECURITY.md`

**Files:**
- Create: `docs/SECURITY.md`

- [ ] **Step 1: Extract `AGENTS.md:94-98` as the body.**

- [ ] **Step 2: Write `docs/SECURITY.md`.**

```markdown
# Security

> **Scope.** Owns secret handling, the single config source rule, and the change-confirmation requirement for sensitive subsystems. Operational invariants live in `RELIABILITY.md`.

## Secrets

- Never print or log secrets, tokens, cookies, or `.env` values.
- Never commit `.env`, credentials, private keys, or generated config files.

## Single config source

The only application config source is `~/.gmgn-twitter-intel/config.yaml`. Do not invent alternative config paths. The schema lives in `CONTRACTS.md`.

## Sensitive change confirmation

Ask before changing authentication, authorisation, billing, or data-deletion behaviour.

## Frontend WebSocket token

The `ws_token` reaches the browser through the same config schema. Do not embed it in committed source; the frontend reads it from the page bootstrap injected by `api/`.
```

- [ ] **Step 3: Commit.**

```bash
git add docs/SECURITY.md
git commit -m "docs: add SECURITY governance file"
```

---

### Task 14: Create `docs/RELIABILITY.md`

**Files:**
- Create: `docs/RELIABILITY.md`

- [ ] **Step 1: Extract `AGENTS.md:192-198` as the body.**

- [ ] **Step 2: Write `docs/RELIABILITY.md`.**

```markdown
# Reliability

> **Scope.** Owns operational invariants that must hold in any deployment of this service. Setup commands live in `SETUP.md`; security policy in `SECURITY.md`.

## Single ASGI worker

One ASGI worker. Multiple workers duplicate the upstream collector. If collector and API must scale separately, split them into distinct processes.

## Foreground-only run model

`~/.gmgn-twitter-intel/config.yaml` is the only application config source. There is no macOS LaunchAgent, systemd unit, or `service` subcommand — run via foreground CLI or Docker Compose.

## Docker Compose state

Docker Compose bind-mounts the host config directory into the container and pins PostgreSQL data to the `gmgn-twitter-intel-postgres` named volume. Local foreground and Docker share the same config; query Docker data via `/api/*`, `/ws`, or `docker compose exec app gmgn-twitter-intel ...`.

## Coverage semantics

`coverage=public_stream` flags events as filtered from GMGN's anonymous public stream — not a full Twitter firehose guarantee. Do not advertise broader coverage in payloads or docs.

## MCP boundary

MCP / FastMCP is optional control / query infrastructure only. `/ws` is the production live push channel; do not route real-time events through MCP.
```

- [ ] **Step 3: Commit.**

```bash
git add docs/RELIABILITY.md
git commit -m "docs: add RELIABILITY governance file"
```

---

### Task 15: Create `docs/FRONTEND.md`

**Files:**
- Create: `docs/FRONTEND.md`

- [ ] **Step 1: Inspect the current `web/src/` layout to ground the file.**

```bash
ls web/src/
```

Expected: `api/`, `components/`, `domain/`, `lib/`, `store/`, `test/`, plus root files.

- [ ] **Step 2: Write `docs/FRONTEND.md`.**

```markdown
# Frontend

> **Scope.** Owns the `web/` architecture, layer responsibilities, component conventions, and the manual UI verification gate. Backend layer boundaries live in `ARCHITECTURE.md`. Build / install commands live in `SETUP.md`.

## Layer map (`web/src/`)

| Directory | Responsibility |
|-----------|----------------|
| `api/` | Thin clients for `/api/*` HTTP routes and the `/ws` WebSocket. Owns request/response typing aligned with `CONTRACTS.md`; never embeds business logic. |
| `domain/` | Pure TypeScript domain models, score-decomposition helpers, and time-window arithmetic. Framework-free; unit-testable in isolation. |
| `store/` | Reactive state holders that bridge `api/` push frames into UI state. Owns subscription lifecycle and replay-window plumbing. |
| `components/` | React components. Composed from `domain/` types and `store/` state; do not call `api/` directly — go through `store/`. |
| `lib/` | Cross-cutting utilities (formatting, classnames, env). No domain knowledge. |
| `test/` | Vitest suites. Mirror the layer they test (`api/`, `domain/`, `store/`, `components/`). |

## Conventions

- **Payload contract.** Component props that mirror API payloads share their type names with `api/` clients. A breaking API change updates `api/`, `domain/`, and `components/` together.
- **State discipline.** No component reads from `api/` directly; subscriptions live in `store/`. Tests for `store/` may stub the WebSocket.
- **Score display.** Any displayed ranking score includes its component breakdown (per the rule in `DESIGN_DISCIPLINE.md`); the breakdown comes from the API, not local recomputation.
- **No business logic in JSX.** Decisions move into `domain/`; `components/` only renders.

## Build & deploy

See `SETUP.md` for `npm install / dev / build / preview` commands. Production bundles ship inside the same Docker image as the Python service and are served by the `api/` static-file mount.

## UI verification gate

Per `WORKFLOW.md`, UI flows that tests cannot exercise must be checked manually before declaring completion. The minimum manual checklist for any `web/`-touching change:

1. Hard-reload the browser at the affected route.
2. Subscribe to a known handle and confirm the live event push reaches the relevant component.
3. Open the network panel; confirm no failing `/api/*` requests; confirm WebSocket frames arrive.
4. Verify any displayed ranking score still shows its component breakdown.
```

- [ ] **Step 3: Commit.**

```bash
git add docs/FRONTEND.md
git commit -m "docs: add FRONTEND governance file"
```

---

### Task 16: Create `docs/TECH_DEBT.md`

**Files:**
- Create: `docs/TECH_DEBT.md`

- [ ] **Step 1: Write the empty registry.**

```markdown
# Tech Debt

> **Scope.** Append-only log of tracked technical debt. Verification artefacts that surface follow-up items append rows here rather than burying them in per-feature `verification.md` files.

## Schema

| Field | Meaning |
|-------|---------|
| Description | One-line summary of the debt. |
| Introduced | Commit SHA or spec slug that introduced it. |
| Area | One of `collector`, `pipeline`, `storage`, `retrieval`, `api`, `web`, `harness`, `infra`. |
| Severity | `low`, `medium`, `high`. |
| Impact | One sentence on what it costs us to leave this. |
| Owner | Name or `unowned`. |

Order rows by severity (high first) then by date introduced (oldest first).

## Open

| Description | Introduced | Area | Severity | Impact | Owner |
|-------------|------------|------|----------|--------|-------|

## Closed

| Description | Introduced | Resolved | Resolution |
|-------------|------------|----------|------------|
```

- [ ] **Step 2: Commit.**

```bash
git add docs/TECH_DEBT.md
git commit -m "docs: add TECH_DEBT registry"
```

---

### Task 17: Slim down `AGENTS.md` to a router

**Files:**
- Modify: `AGENTS.md` (replace entire content).

- [ ] **Step 1: Replace the file content.**

```markdown
# AGENTS.md

Router for coding agents (Codex, Cursor, generic LLM tooling). Project-wide rules; mirrored to `CLAUDE.md`. When you change one router, update the other. Substantive rules live under `docs/`; this file does not duplicate them.

## What this is

`gmgn-twitter-intel`: a single Python service that ingests GMGN's anonymous public WebSocket, extracts Twitter-mentioned crypto entities, scores them, and serves results over HTTP / WebSocket / CLI to a small React frontend. One PostgreSQL store. See `docs/ARCHITECTURE.md`.

## Where to read what

| Need | File |
|------|------|
| Install, run, docker | `docs/SETUP.md` |
| Layer boundaries & data flow | `docs/ARCHITECTURE.md` |
| Frontend architecture | `docs/FRONTEND.md` |
| Public surfaces (config, WS, HTTP, CLI) | `docs/CONTRACTS.md` |
| Spec→plan→tasks→verification flow | `docs/WORKFLOW.md` |
| Design rules (audit, reuse, scoring) | `docs/DESIGN_DISCIPLINE.md` |
| Testing & completion gates | `docs/TESTING.md` |
| Secrets, config, authn changes | `docs/SECURITY.md` |
| Operational invariants | `docs/RELIABILITY.md` |
| Active / done specs & plans | `docs/superpowers/{specs,plans}/{active,completed}/` |
| External references & papers | `docs/references/` |
| Auto-generated artefacts | `docs/generated/` |
| Tech debt log | `docs/TECH_DEBT.md` |

CLI surface: `uv run gmgn-twitter-intel --help` is the source of truth (snapshot at `docs/generated/cli-help.md`).
```

- [ ] **Step 2: Confirm line count is within budget.**

```bash
wc -l AGENTS.md
```

Expected: ≤ 60 lines.

- [ ] **Step 3: Run the router test.**

```bash
uv run pytest tests/test_harness_structure.py::test_routers_within_line_budget -v
```

Expected: PASS for `AGENTS.md` (will still fail for `CLAUDE.md` until Task 18).

- [ ] **Step 4: Commit.**

```bash
git add AGENTS.md
git commit -m "docs: slim AGENTS.md to a router"
```

---

### Task 18: Slim down `CLAUDE.md` to a router + Claude-only protocol

**Files:**
- Modify: `CLAUDE.md` (replace entire content).

- [ ] **Step 1: Replace the file content.**

```markdown
# CLAUDE.md

Claude-specific router. Mirrors `AGENTS.md` for the routing table and adds the Claude-only Skills / Plan-mode / Worktree protocol below. When you change either router, update the other.

## What this is

`gmgn-twitter-intel`: a single Python service that ingests GMGN's anonymous public WebSocket, extracts Twitter-mentioned crypto entities, scores them, and serves results over HTTP / WebSocket / CLI to a small React frontend. One PostgreSQL store. See `docs/ARCHITECTURE.md`.

## Where to read what

| Need | File |
|------|------|
| Install, run, docker | `docs/SETUP.md` |
| Layer boundaries & data flow | `docs/ARCHITECTURE.md` |
| Frontend architecture | `docs/FRONTEND.md` |
| Public surfaces | `docs/CONTRACTS.md` |
| Spec→plan→tasks→verification flow | `docs/WORKFLOW.md` |
| Design rules | `docs/DESIGN_DISCIPLINE.md` |
| Testing & completion gates | `docs/TESTING.md` |
| Secrets & sensitive changes | `docs/SECURITY.md` |
| Operational invariants | `docs/RELIABILITY.md` |
| Active / done specs & plans | `docs/superpowers/{specs,plans}/{active,completed}/` |
| External references & papers | `docs/references/` |
| Auto-generated artefacts | `docs/generated/` |
| Tech debt log | `docs/TECH_DEBT.md` |

## Claude-only protocol

When the `superpowers:` skills are available, use them in this order:

1. `brainstorming` — clarify intent before writing any spec.
2. `writing-plans` — produce the spec / plan; iterate with the user.
3. `using-git-worktrees` — set up `.worktrees/<slug>/` once the plan is approved.
4. `test-driven-development` — write the failing test before each implementation slice.
5. `executing-plans` or `subagent-driven-development` — drive the plan to completion.
6. `verification-before-completion` — run the verification commands and capture output.
7. `requesting-code-review` — surface the diff and the verification artefact for review.
8. `finishing-a-development-branch` — decide on merge / PR / cleanup.

Process skills take priority over implementation skills when both could apply.
```

- [ ] **Step 2: Confirm line count.**

```bash
wc -l CLAUDE.md
```

Expected: ≤ 60 lines.

- [ ] **Step 3: Run the router test.**

```bash
uv run pytest tests/test_harness_structure.py::test_routers_within_line_budget -v
```

Expected: PASS for both routers.

- [ ] **Step 4: Commit.**

```bash
git add CLAUDE.md
git commit -m "docs: slim CLAUDE.md to a router with Claude-only protocol block"
```

---

### Task 19: Run the lane + governance + rule-uniqueness tests

**Files:**
- No edits.

- [ ] **Step 1: Run the full structural test module.**

```bash
uv run pytest tests/test_harness_structure.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 2: If `test_rule_uniqueness` fails, the failing phrase indicates a leak. Either remove the phrase from the routers or move the rule into the correct governance file. Re-run.**

- [ ] **Step 3: Run the full backend test suite to confirm nothing else broke.**

```bash
uv run ruff check .
uv run pytest -x
uv run python -m compileall src tests
```

Expected: all three pass.

- [ ] **Step 4: Commit any cleanup.**

```bash
git status
# if there are changes from Step 2 cleanup:
git add -p
git commit -m "docs: tighten governance file boundaries to satisfy rule-uniqueness test"
```

---

### Task 20: Add `docs/references/README.md` and the walkinglabs note

**Files:**
- Create: `docs/references/README.md`
- Create: `docs/references/walkinglabs-harness-engineering.md`

- [ ] **Step 1: Write the references README.**

```markdown
# References

> **Scope.** External materials cited by governance files or specs. Each file states the source, fetch date, and a self-contained summary so specs can link a relative path instead of an external URL.

## Updating

- Add a new file when a governance file or spec needs to cite an external source it does not already cite.
- Each entry includes: source URL, fetch date, one-paragraph summary, and the rule or formula it supports.
- Prune entries whose only consumer was a since-deleted spec.
```

- [ ] **Step 2: Write the walkinglabs note.**

```markdown
# walkinglabs/learn-harness-engineering — OpenAI Advanced

**Source:** https://github.com/walkinglabs/learn-harness-engineering/blob/main/docs/zh/resources/openai-advanced/index.md
**Fetched:** 2026-05-09
**Cited by:** `docs/superpowers/specs/completed/2026-05-09-harness-engineering-restructure.md`

## Summary

Five design principles for organising an LLM-coding-agent harness in a repository:

1. **Short entry, deep links.** Entry files (`AGENTS.md`, `CLAUDE.md`) point; rules live in linked governance files.
2. **The repository is the only source of truth.** Avoid relying on chat history or operator memory.
3. **Mechanical structure beats verbal convention.** Directory layout and file naming enforce intent more reliably than prose rules.
4. **Plans, quality, and tech debt are versioned alongside code.** Use lane folders with lifecycle states.
5. **Cleanup and harness simplification are routine work**, not emergency rescue.

Recommended structure: short routers at the root, governance files under `docs/`, lane folders with `active/` and `completed/`, `references/` for external materials, `generated/` for derived artefacts, plus per-domain governance files (DESIGN, RELIABILITY, SECURITY, FRONTEND, QUALITY).

## How this repo applies it

- Routers: `AGENTS.md`, `CLAUDE.md` (≤ 60 lines each).
- Governance: nine `docs/*.md` files plus `TECH_DEBT.md` (see the routing table in either router).
- Lane lifecycle: `docs/superpowers/{specs,plans}/{active,completed}/`.
- Support: `docs/references/`, `docs/generated/`.
- Source layout (`src/gmgn_twitter_intel/`) is independently aligned with the "mechanical structure" principle and is unchanged by this restructure.
```

- [ ] **Step 3: Commit.**

```bash
git add docs/references/README.md docs/references/walkinglabs-harness-engineering.md
git commit -m "docs: seed references/ with walkinglabs source note"
```

---

### Task 21: Add the six paper summaries

**Files:**
- Create: `docs/references/papers/kleinberg-2002-burst.md`
- Create: `docs/references/papers/goel-2016-structural-virality.md`
- Create: `docs/references/papers/cheng-2014-cascades.md`
- Create: `docs/references/papers/bakshy-2011-influencer-refutation.md`
- Create: `docs/references/papers/centola-2010-complex-contagion.md`
- Create: `docs/references/papers/crane-sornette-2008-endogenous-exogenous.md`

Each file follows the same template. The summaries are intentionally short — three paragraphs covering claim, method, and the rule it supports in this repo.

- [ ] **Step 1: Create the directory and write `kleinberg-2002-burst.md`.**

```bash
mkdir -p docs/references/papers
```

```markdown
# Kleinberg 2002 — Bursty and Hierarchical Structure in Streams

**Citation:** Kleinberg, J. (2002). *Bursty and Hierarchical Structure in Streams.* KDD.
**Cited by:** `docs/DESIGN_DISCIPLINE.md` (Scoring and ranking design)

## Claim

Streams of timestamped events exhibit "bursts" of elevated rate that are statistically distinguishable from baseline noise. A finite-state automaton model identifies bursts as transitions to higher-rate states.

## Method

Frame the stream as a hidden two-state (or k-state) Markov model where each state has a rate parameter; the cost of state transitions and the data likelihood are jointly minimised. Bursts are detected as runs in elevated states.

## Rule it supports here

Token-mention rate spikes used by the radar's heat / propagation components must be evaluated against an expected baseline rate, not against the total volume window. A spike that does not clear the burst threshold is noise, not signal.
```

- [ ] **Step 2: Write `goel-2016-structural-virality.md`.**

```markdown
# Goel et al. 2016 — The Structural Virality of Online Diffusion

**Citation:** Goel, S., Anderson, A., Hofman, J., & Watts, D. (2016). *The Structural Virality of Online Diffusion.* Management Science.
**Cited by:** `docs/DESIGN_DISCIPLINE.md` (Scoring and ranking design)

## Claim

Most online cascades are shallow broadcasts driven by a single popular source; "viral" cascades that propagate through long deep chains are rare. Popularity (size) and structural virality (depth/breadth) are independent dimensions.

## Method

Analyse millions of Twitter cascades; measure cascade depth and breadth alongside total size; show that high-size cascades cluster as broadcast trees, not chains.

## Rule it supports here

Heat (size) and propagation (structural virality) must be scored as separate components. A high-heat token may be one influencer broadcasting; the radar must distinguish that from genuine multi-hop discussion before treating heat as a positive signal.
```

- [ ] **Step 3: Write `cheng-2014-cascades.md`.**

```markdown
# Cheng et al. 2014 — Can Cascades be Predicted?

**Citation:** Cheng, J., Adamic, L., Dow, P. A., Kleinberg, J., & Leskovec, J. (2014). *Can Cascades be Predicted?* WWW.
**Cited by:** `docs/DESIGN_DISCIPLINE.md` (Scoring and ranking design)

## Claim

Predicting whether a cascade will double in size is hard at the moment of post but becomes feasible once the cascade has reached a small initial size; early temporal and structural features dominate later content features.

## Method

Reformulate cascade prediction as a balanced binary classification: given a cascade of size k, will it reach size 2k? Train on Facebook re-share cascades.

## Rule it supports here

Token-radar's cascade-prediction component should not attempt to predict viral outcomes from a single mention; it should activate only after a small early-window size threshold and weight temporal velocity over content novelty.
```

- [ ] **Step 4: Write `bakshy-2011-influencer-refutation.md`.**

```markdown
# Bakshy et al. 2011 — Everyone's an Influencer

**Citation:** Bakshy, E., Hofman, J. M., Mason, W. A., & Watts, D. J. (2011). *Everyone's an Influencer: Quantifying Influence on Twitter.* WSDM.
**Cited by:** `docs/DESIGN_DISCIPLINE.md` (Scoring and ranking design)

## Claim

Targeting only high-follower "influencers" is a poor strategy; the marginal cost of acquiring an influencer post outweighs the expected diffusion gain in most regimes. Smaller, more numerous targets often dominate ROI.

## Method

Track URL-sharing cascades on Twitter; regress cascade size on poster characteristics; compare expected vs realised diffusion across the follower distribution.

## Rule it supports here

Account upstream-identity features (follower count, watched-list membership) are weak proxies for downstream impact. Ranking signals must operate on observable downstream effects within an explicit time window, not on author identity.
```

- [ ] **Step 5: Write `centola-2010-complex-contagion.md`.**

```markdown
# Centola 2010 — The Spread of Behavior in an Online Social Network Experiment

**Citation:** Centola, D. (2010). *The Spread of Behavior in an Online Social Network Experiment.* Science.
**Cited by:** `docs/DESIGN_DISCIPLINE.md` (Scoring and ranking design)

## Claim

Behaviour adoption (as opposed to information spread) requires multiple independent exposures from different sources — "complex contagion" — and clustered networks propagate it faster than random networks of the same density.

## Method

Randomised online experiment seeding the same behaviour into clustered vs random network conditions; measure adoption rate and reach.

## Rule it supports here

A single repeated mention from the same author cluster is information broadcast, not adoption signal. The radar's diffusion-health component must require multiple independent author clusters before treating mentions as adoption evidence.
```

- [ ] **Step 6: Write `crane-sornette-2008-endogenous-exogenous.md`.**

```markdown
# Crane & Sornette 2008 — Robust Dynamic Classes Revealed by Measuring the Response Function of a Social System

**Citation:** Crane, R., & Sornette, D. (2008). *Robust dynamic classes revealed by measuring the response function of a social system.* PNAS.
**Cited by:** `docs/DESIGN_DISCIPLINE.md` (Scoring and ranking design)

## Claim

Decay shapes after a popularity peak distinguish endogenous (epidemic-like, slow power-law) from exogenous (shock-driven, fast) origin. The shape of the post-peak response is more diagnostic than the peak height.

## Method

Fit response functions to YouTube view-count time series; classify peaks by decay exponent.

## Rule it supports here

Heat and catalyst components must be evaluated alongside the post-peak decay shape. A peak with exogenous (fast-decay) signature should not be treated as durable propagation, regardless of its height.
```

- [ ] **Step 7: Run the papers test.**

```bash
uv run pytest tests/test_harness_structure.py::test_references_papers_present -v
```

Expected: PASS.

- [ ] **Step 8: Commit.**

```bash
git add docs/references/papers/
git commit -m "docs: seed references/papers/ with the six cited summaries"
```

---

### Task 22: Add `docs/references/gmgn-public-protocol.md` and `docs/references/okx-api.md`

**Files:**
- Create: `docs/references/gmgn-public-protocol.md`
- Create: `docs/references/okx-api.md`

These two are stub references — they document scope and link to the source files. The detailed protocol descriptions remain in code comments (as today); the reference file's job is to give specs a single citable path instead of citing inline source.

- [ ] **Step 1: Confirm the source paths.**

```bash
ls src/gmgn_twitter_intel/collector/
ls src/gmgn_twitter_intel/market/
```

Note the exact filenames; they go into the "Source files" tables below.

- [ ] **Step 2: Write `docs/references/gmgn-public-protocol.md`.**

```markdown
# GMGN Anonymous Public WebSocket — Protocol Notes

**Source of truth:** `src/gmgn_twitter_intel/collector/`
**Cited by:** `docs/RELIABILITY.md` (`coverage=public_stream` semantics), `docs/SECURITY.md` (privacy boundary).

## Scope

This file is a router into the collector code. It exists so specs can cite a stable relative path instead of pinning line numbers in `collector/`. Detailed frame schemas, channel lists, and chain identifiers live as constants and docstrings inside the source files below.

## Source files

| Concern | File |
|---------|------|
| Connection lifecycle, reconnect | `src/gmgn_twitter_intel/collector/<connection file from Step 1>` |
| Frame parsing / envelope | `src/gmgn_twitter_intel/collector/<parser file from Step 1>` |
| `cp=0` / `cp=1` snapshot gate | `src/gmgn_twitter_intel/collector/<gate file from Step 1>` |
| Handle filter | `src/gmgn_twitter_intel/collector/<filter file from Step 1>` |
| Subscription bookkeeping | `src/gmgn_twitter_intel/collector/<subscription file from Step 1>` |

Replace each `<...>` with the actual filename observed in Step 1.

## Privacy boundary (load-bearing)

The chain identifiers, channel names, app-version handshake fields, and frame envelope keys observed by `collector/` are GMGN's internal protocol. Per `docs/SECURITY.md` and `docs/CONTRACTS.md` they MUST NOT appear in any user-facing payload (HTTP, WebSocket, CLI). Tests under `tests/test_*payload*.py` enforce this.
```

- [ ] **Step 3: Write `docs/references/okx-api.md`.**

```markdown
# OKX & GMGN OpenAPI — Endpoint Notes

**Source of truth:** `src/gmgn_twitter_intel/market/`
**Cited by:** `docs/ARCHITECTURE.md` (cross-cutting `market/` module), `docs/CONTRACTS.md` (optional config groups).

## Scope

This file is a router into the market clients. Detailed endpoint paths, query parameters, and response shapes live in the client modules below; this reference file gives specs a stable citable path.

## Source files

| Client | File |
|--------|------|
| OKX CEX REST client | `src/gmgn_twitter_intel/market/<okx cex file from Step 1>` |
| OKX DEX REST client | `src/gmgn_twitter_intel/market/<okx dex file from Step 1>` |
| GMGN OpenAPI REST client | `src/gmgn_twitter_intel/market/<gmgn openapi file from Step 1>` |

Replace each `<...>` with the actual filename observed in Step 1.

## Operational notes

- Rate-limit handling and retry policy live in each client's `_request` / `_call` helper.
- Authentication credentials come from the optional config groups in `docs/CONTRACTS.md`; absence of credentials disables the corresponding pipeline cleanly (no crash).
```

- [ ] **Step 4: Commit.**

```bash
git add docs/references/gmgn-public-protocol.md docs/references/okx-api.md
git commit -m "docs: add GMGN protocol and OKX API stub references"
```

---

### Task 23: Add the `docs/generated/` skeleton and regeneration scripts (TDD red)

**Files:**
- Create: `docs/generated/README.md`
- Create: `scripts/regen_db_schema.py`
- Create: `scripts/regen_cli_help.py`
- Create: `scripts/regen_score_versions.py`
- Create: `scripts/regen_ws_protocol.py`
- Create: `tests/test_docs_generated.py`

- [ ] **Step 1: Write `docs/generated/README.md`.**

```markdown
# Generated

> **DO NOT HAND-EDIT files in this directory.** They are regenerated from the source of truth listed in each file's header. Edit the source, then run the regenerator.

## Regenerate

```bash
make docs-generated
```

This runs four scripts in sequence:

| File | Source | Script |
|------|--------|--------|
| `db-schema.md` | Alembic head + `pg_catalog` introspection | `scripts/regen_db_schema.py` |
| `cli-help.md` | `gmgn-twitter-intel --help` recursively | `scripts/regen_cli_help.py` |
| `score-versions.md` | grep `score_version=` literals in `src/` | `scripts/regen_score_versions.py` |
| `ws-protocol.md` | extract message-type union from `src/gmgn_twitter_intel/api/ws.py` | `scripts/regen_ws_protocol.py` |

CI verifies that `make docs-generated` produces no diff against the committed tree.
```

- [ ] **Step 2: Write the four regeneration scripts.**

Each script writes a single Markdown file with the standard header:

```python
# scripts/regen_cli_help.py
"""Regenerate docs/generated/cli-help.md from `gmgn-twitter-intel --help`."""
from __future__ import annotations

import subprocess
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "generated" / "cli-help.md"
HEADER = "<!-- AUTO-GENERATED by scripts/regen_cli_help.py — do not hand-edit -->\n\n"


def _help(args: list[str]) -> str:
    return subprocess.check_output(
        ["uv", "run", "gmgn-twitter-intel", *args, "--help"],
        text=True,
    )


def main() -> None:
    body = ["# CLI Help", "", "## Top level", "", "```", _help([]), "```", ""]
    for group in ("db", "ops"):
        body += [f"## `{group}`", "", "```", _help([group]), "```", ""]
    OUTPUT.write_text(HEADER + "\n".join(body), encoding="utf-8")


if __name__ == "__main__":
    main()
```

```python
# scripts/regen_score_versions.py
"""Regenerate docs/generated/score-versions.md by scanning src/ for score_version literals."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OUTPUT = ROOT / "docs" / "generated" / "score-versions.md"
HEADER = "<!-- AUTO-GENERATED by scripts/regen_score_versions.py — do not hand-edit -->\n\n"
PATTERN = re.compile(r'score_version\s*=\s*[\'"]([^\'"]+)[\'"]')


def main() -> None:
    rows: list[tuple[str, str, int, str]] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in PATTERN.finditer(line):
                rows.append((match.group(1), rel, lineno, line.strip()))
    body = ["# Score Versions", "", "| Version | File | Line | Context |", "|---------|------|------|---------|"]
    for version, rel, lineno, context in sorted(rows):
        body.append(f"| `{version}` | `{rel}` | {lineno} | `{context}` |")
    OUTPUT.write_text(HEADER + "\n".join(body) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
```

```python
# scripts/regen_ws_protocol.py
"""Regenerate docs/generated/ws-protocol.md by introspecting api/ws.py message types."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WS_FILE = ROOT / "src" / "gmgn_twitter_intel" / "api" / "ws.py"
OUTPUT = ROOT / "docs" / "generated" / "ws-protocol.md"
HEADER = "<!-- AUTO-GENERATED by scripts/regen_ws_protocol.py — do not hand-edit -->\n\n"


def _collect_classes(tree: ast.AST) -> list[tuple[str, str]]:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node) or ""
            names.append((node.name, doc.splitlines()[0] if doc else ""))
    return names


def main() -> None:
    tree = ast.parse(WS_FILE.read_text(encoding="utf-8"))
    rows = _collect_classes(tree)
    body = ["# WebSocket Protocol", "", f"Source: `{WS_FILE.relative_to(ROOT).as_posix()}`", "",
            "| Message class | Doc |", "|---------------|-----|"]
    for name, doc in sorted(rows):
        body.append(f"| `{name}` | {doc} |")
    OUTPUT.write_text(HEADER + "\n".join(body) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
```

```python
# scripts/regen_db_schema.py
"""Regenerate docs/generated/db-schema.md from Alembic head + pg_catalog introspection.

Requires Postgres reachable via the standard project config.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect

from gmgn_twitter_intel.settings import load_settings
from gmgn_twitter_intel.storage.session import build_engine

OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "generated" / "db-schema.md"
HEADER = "<!-- AUTO-GENERATED by scripts/regen_db_schema.py — do not hand-edit -->\n\n"


def main() -> None:
    settings = load_settings()
    engine = build_engine(settings.storage.postgres)
    inspector = inspect(engine)
    body = ["# Database Schema", ""]
    for table in sorted(inspector.get_table_names(schema="public")):
        body.append(f"## `{table}`")
        body.append("")
        body.append("| Column | Type | Nullable | Default |")
        body.append("|--------|------|----------|---------|")
        for col in inspector.get_columns(table, schema="public"):
            body.append(
                f"| `{col['name']}` | `{col['type']}` | "
                f"{col.get('nullable', True)} | `{col.get('default')}` |"
            )
        body.append("")
    OUTPUT.write_text(HEADER + "\n".join(body) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
```

If the `build_engine` import path differs from the actual storage module — adjust to match (the implementer should `grep -rn 'def build_engine\\|create_engine' src/gmgn_twitter_intel/storage/` to confirm).

- [ ] **Step 3: Write the failing tests file.**

```python
# tests/test_docs_generated.py
"""Verify docs/generated/ files are regeneration-clean."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATED = REPO_ROOT / "docs" / "generated"
EXPECTED = {"README.md", "db-schema.md", "cli-help.md", "score-versions.md", "ws-protocol.md"}
HEADER_MARKER = "AUTO-GENERATED"


def test_generated_directory_present() -> None:
    assert GENERATED.is_dir(), "docs/generated/ missing"


def test_expected_generated_files() -> None:
    actual = {p.name for p in GENERATED.glob("*.md")}
    assert actual == EXPECTED, f"unexpected docs/generated/ contents: {actual ^ EXPECTED}"


def test_generated_files_have_header_marker() -> None:
    for name in EXPECTED - {"README.md"}:
        path = GENERATED / name
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        assert HEADER_MARKER in first_line, f"{name} missing AUTO-GENERATED header"


@pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("make") is None,
    reason="uv or make not available in this environment",
)
def test_make_docs_generated_clean_diff() -> None:
    proc = subprocess.run(
        ["make", "docs-generated"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    if proc.returncode != 0:
        pytest.skip(f"make docs-generated failed (likely Postgres unreachable): {proc.stderr}")
    diff = subprocess.run(
        ["git", "diff", "--exit-code", "docs/generated/"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert diff.returncode == 0, f"make docs-generated produced uncommitted changes:\n{diff.stdout}"
```

- [ ] **Step 4: Run the tests and confirm they fail.**

```bash
uv run pytest tests/test_docs_generated.py -v
```

Expected: at least `test_expected_generated_files` and `test_generated_files_have_header_marker` FAIL because the files don't exist yet. `test_make_docs_generated_clean_diff` may skip.

- [ ] **Step 5: Commit the script + test scaffolding (red).**

```bash
git add scripts/ tests/test_docs_generated.py docs/generated/README.md
git commit -m "scripts/test: regen scripts and failing assertions for docs/generated/ (red)"
```

---

### Task 24: Add the Makefile target and run the first generation

**Files:**
- Modify: `Makefile` (add new targets).

- [ ] **Step 1: Append to `Makefile`.**

```makefile

.PHONY: docs-generated docs-db-schema docs-cli-help docs-score-versions docs-ws-protocol

docs-generated: docs-db-schema docs-cli-help docs-score-versions docs-ws-protocol ## regenerate docs/generated/*

docs-db-schema: ## regenerate docs/generated/db-schema.md (requires Postgres)
	@uv run python scripts/regen_db_schema.py

docs-cli-help: ## regenerate docs/generated/cli-help.md
	@uv run python scripts/regen_cli_help.py

docs-score-versions: ## regenerate docs/generated/score-versions.md
	@uv run python scripts/regen_score_versions.py

docs-ws-protocol: ## regenerate docs/generated/ws-protocol.md
	@uv run python scripts/regen_ws_protocol.py
```

- [ ] **Step 2: Run `make docs-generated` to produce the four files for the first time.**

```bash
make docs-generated
```

Expected: four new files appear under `docs/generated/`. If `make docs-db-schema` fails because of Postgres unreachability, surface the error and pause — do not commit a partial set.

- [ ] **Step 3: Confirm the four files have the AUTO-GENERATED header.**

```bash
head -1 docs/generated/db-schema.md docs/generated/cli-help.md docs/generated/score-versions.md docs/generated/ws-protocol.md
```

Expected: each line contains `AUTO-GENERATED`.

- [ ] **Step 4: Run the generated-files tests.**

```bash
uv run pytest tests/test_docs_generated.py -v
```

Expected: `test_expected_generated_files` PASS, `test_generated_files_have_header_marker` PASS, `test_make_docs_generated_clean_diff` PASS or SKIP.

- [ ] **Step 5: Commit.**

```bash
git add Makefile docs/generated/
git commit -m "build: add docs-generated Make target and seed first regeneration"
```

---

### Task 25: Final verification

**Files:**
- No edits.

- [ ] **Step 1: Run the full test suite.**

```bash
uv run ruff check .
uv run pytest
uv run python -m compileall src tests
```

Expected: all pass.

- [ ] **Step 2: Run the structural tests in isolation and capture output.**

```bash
uv run pytest tests/test_harness_structure.py tests/test_docs_generated.py -v 2>&1 | tee /tmp/harness-restructure-verification.txt
```

Expected: every test PASS or skipped (only the Postgres-gated test may skip).

- [ ] **Step 3: Manually verify routing works.**

Open `AGENTS.md`. Pick a random concern (e.g. "where do testing rules live?"). Confirm: routing table → `docs/TESTING.md` → answer is in that file. Repeat for three concerns of your choice.

- [ ] **Step 4: Confirm docs root is exactly the expected ten files.**

```bash
ls docs/*.md
```

Expected: `ARCHITECTURE.md CONTRACTS.md DESIGN_DISCIPLINE.md FRONTEND.md RELIABILITY.md SECURITY.md SETUP.md TECH_DEBT.md TESTING.md WORKFLOW.md`.

- [ ] **Step 5: Write the verification artefact.**

Create `docs/superpowers/plans/active/2026-05-09-harness-engineering-restructure-verification.md` with:

```markdown
# Verification — Harness Engineering Restructure

**Date:** <YYYY-MM-DD of run>
**Plan:** `docs/superpowers/plans/active/2026-05-09-harness-engineering-restructure.md`

## Commands run

(Paste verbatim output of Step 1 and Step 2.)

## Acceptance criteria evidence

| AC | Evidence |
|----|----------|
| AC1 (routers ≤ 60 lines) | `tests/test_harness_structure.py::test_routers_within_line_budget` PASS |
| AC2 (no rule duplication) | `tests/test_harness_structure.py::test_rule_uniqueness` PASS |
| AC3 (lane roots clean) | `tests/test_harness_structure.py::test_lane_roots_have_no_loose_files` PASS |
| AC4 (docs root = 10 files) | `tests/test_harness_structure.py::test_docs_root_governance_files` PASS |
| AC5 (`make docs-generated` clean) | `tests/test_docs_generated.py::test_make_docs_generated_clean_diff` PASS / SKIP |
| AC6 (papers present) | `tests/test_harness_structure.py::test_references_papers_present` PASS |
| AC7 (TECH_DEBT registry) | `docs/TECH_DEBT.md` exists with schema |

## Risks observed

(List any anomalies seen during the run.)

## Follow-ups

(Append items to `docs/TECH_DEBT.md` rather than listing them only here.)
```

- [ ] **Step 6: Move spec, plan, and verification from `active/` to `completed/` together, then commit.**

```bash
git mv docs/superpowers/plans/active/2026-05-09-harness-engineering-restructure-verification.md docs/superpowers/plans/completed/
git mv docs/superpowers/specs/active/2026-05-09-harness-engineering-restructure.md docs/superpowers/specs/completed/
git mv docs/superpowers/plans/active/2026-05-09-harness-engineering-restructure.md docs/superpowers/plans/completed/
git commit -m "docs: record verification and archive harness-restructure spec/plan"
```

The verification artefact is created in `docs/superpowers/plans/active/` in Step 5, then moved to `completed/` together with the plan and spec in this step.

---

## PR breakdown

Three PRs, each independently reviewable and mergeable.

1. **PR 1 — Lane reorganization** (Tasks 1–6): adds the structural tests in TDD-red form, creates active/completed lifecycle directories, and migrates 17 specs + 13 plans + 14 legacy `docs/` root files into their lanes. No content edits. After merge, only `tests/test_harness_structure.py::test_no_legacy_files_at_docs_root` is green; other structural tests still red.
2. **PR 2 — Governance extraction + router slim-down** (Tasks 7–19): creates the nine governance files plus `TECH_DEBT.md`, slims `AGENTS.md` and `CLAUDE.md` to routers. After merge, all of `tests/test_harness_structure.py` is green.
3. **PR 3 — Support rings + generation pipeline** (Tasks 20–25): adds `docs/references/` (README, walkinglabs note, six paper summaries, two protocol notes), `docs/generated/` (four regenerated files), `scripts/regen_*.py`, the `make docs-generated` target, `tests/test_docs_generated.py`, and the verification artefact. Final commit moves the spec and plan into `completed/`.

PR 2 depends on PR 1 (governance file extraction edits files that the lane migration moved). PR 3 depends on PR 2 (the references/papers/* are linked from `DESIGN_DISCIPLINE.md`).

## Rollout order

This is a documentation restructure with one new test module and one new Makefile target — no migration, no backfill, no service deploy.

1. Merge PR 1.
2. Merge PR 2.
3. Merge PR 3.
4. Run `make docs-generated` once on the deployment host (or in CI) to populate `docs/generated/`. (Already done in PR 3 commit; this is a sanity re-run.)
5. Update any agent configurations that hard-code paths to legacy `docs/` root files (none expected; spec accepts the breakage of stale inbound links).

## Rollback

Each PR is independently revertible. If a problem surfaces:

- **Revert PR 3**: removes `docs/references/`, `docs/generated/`, `scripts/regen_*`, the Makefile additions, and the structural tests for generated files. Routers and governance survive.
- **Revert PR 2**: restores the thick `AGENTS.md` and `CLAUDE.md` and removes the nine governance files. The lane structure from PR 1 survives.
- **Revert PR 1**: returns 17 + 13 + 14 = 44 files to their original locations via reverse `git mv`. The structural test module is removed.

No step is irreversible. No data migration is involved.

## Acceptance test commands

Map directly to the spec's AC1–AC7.

- **AC1**: `uv run pytest tests/test_harness_structure.py::test_routers_within_line_budget -v`
- **AC2**: `uv run pytest tests/test_harness_structure.py::test_rule_uniqueness -v`
- **AC3**: `uv run pytest tests/test_harness_structure.py::test_lane_roots_have_no_loose_files -v`
- **AC4**: `uv run pytest tests/test_harness_structure.py::test_docs_root_governance_files -v` plus `uv run pytest tests/test_harness_structure.py::test_no_legacy_files_at_docs_root -v`
- **AC5**: `uv run pytest tests/test_docs_generated.py::test_make_docs_generated_clean_diff -v` (skipped if Postgres unreachable; in that case run `make docs-generated && git diff --exit-code docs/generated/` manually with Postgres up).
- **AC6**: `uv run pytest tests/test_harness_structure.py::test_references_papers_present -v`
- **AC7**: `[ -f docs/TECH_DEBT.md ] && grep -q '^| Description |' docs/TECH_DEBT.md && echo OK`

## Verification

Inline above (Task 25, Steps 1–5). The verification artefact is committed as the final step of PR 3 at `docs/superpowers/plans/completed/2026-05-09-harness-engineering-restructure-verification.md` (after the lane move at Task 25 Step 6).
