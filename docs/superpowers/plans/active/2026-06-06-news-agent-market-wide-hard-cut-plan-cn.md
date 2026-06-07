# News Agent Market-Wide Hard-Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace crypto-only News Item Brief admission with market-wide deterministic admission, duplicate/similar story suppression, and a market-wide agent brief harness for crypto, US equities, macro/rates, energy/geopolitics, AI semis, and private-company market news.

**Architecture:** Keep PostgreSQL facts and deterministic News services upstream of LLM output. `NewsItemProcessWorker` computes market-wide agent admission and representative targets before enqueueing `brief_input`; `NewsItemBriefWorker` rechecks the same policy and still executes only through `AgentExecutionGateway`. The brief packet/prompt/schema are hard-cut to market-wide entities, with old current briefs made stale by version changes rather than compatibility adapters.

**Tech Stack:** Python 3.13, PostgreSQL/Alembic, Pydantic, pytest, Parallax worker runtime, LiteLLM `AgentExecutionGateway`, React/TypeScript news frontend, `uv`, `make check-all`.

---

**Status**: Draft, ready for Qinghuan review before implementation
**Date**: 2026-06-06
**Owning spec**: `docs/superpowers/specs/active/2026-06-06-news-agent-market-wide-dedup-admission-cn.md`
**Worktree**: `.worktrees/news-agent-market-wide-hard-cut/`
**Branch**: `codex/news-agent-market-wide-hard-cut`

## Hard-Cut Decisions

- No LLM actor, tool loop, DB retrieval tool, request-time agent execution, or provider-specific branch inside the agent.
- No runtime compatibility for the old News brief output shape. The new output uses market-wide `affected_entities`, not legacy `affected_assets`.
- No dual packet fields. The new input packet uses `entity_lanes`, not `token_lanes`; crypto token mentions are converted into entity lanes before the packet is built.
- No crypto fallback threshold. Score >= 80 is the market-wide admission threshold; the old score >= 65 + crypto evidence path is removed.
- `analysis_admission_*` remains only as allowlisted legacy crypto-analysis diagnostic/push context. It is not an agent brief gate, input-packet field, page `agent_signal` source, item-detail agent state, or agent skip reason.
- Old current brief rows become stale through prompt/schema/validator version bump and current-contract predicates. Do not transform old rows into the new schema.
- Duplicate/similar decisions are deterministic domain decisions over DB facts/read models. Agent output never decides identity or story membership.

## Pre-Flight

- [ ] Create the implementation worktree:
  ```bash
  git worktree add .worktrees/news-agent-market-wide-hard-cut -b codex/news-agent-market-wide-hard-cut main
  cd .worktrees/news-agent-market-wide-hard-cut
  git branch --show-current
  git status --short
  ```
  Expected: branch is `codex/news-agent-market-wide-hard-cut`; status may show existing worktree-local generated files only if the worktree setup creates them.

- [ ] Confirm runtime config paths without printing secrets:
  ```bash
  uv run parallax config
  ```
  Expected: `config_path` and `workers_config_path` point under `/Users/qinghuan/.parallax/`. If this command fails because of an import error, record the import error and continue with tests; do not print secret values from config files.

- [ ] Run baseline targeted tests before edits:
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_agent_policy.py \
    tests/unit/domains/news_intel/test_news_item_brief_input.py \
    tests/unit/domains/news_intel/test_news_item_brief_stage.py \
    tests/unit/domains/news_intel/test_news_item_brief_validation.py \
    tests/unit/domains/news_intel/test_news_item_brief_worker.py \
    tests/unit/domains/news_intel/test_news_page_projection.py \
    tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py \
    tests/unit/test_api_news_contract.py
  ```
  Expected: exit 0 or exact pre-existing failures recorded before source edits.

## File-Level Overview

Create:

- `src/parallax/platform/db/alembic/versions/20260606_0151_news_agent_market_admission_hard_cut.py`
- `src/parallax/domains/news_intel/services/news_market_scope.py`
- `src/parallax/domains/news_intel/services/news_story_similarity.py`
- `src/parallax/domains/news_intel/services/news_material_delta.py`
- `src/parallax/domains/news_intel/services/news_item_agent_admission.py`
- `src/parallax/domains/news_intel/services/news_agent_admission_repair.py`
- `tests/unit/domains/news_intel/test_news_market_scope.py`
- `tests/unit/domains/news_intel/test_news_story_similarity.py`
- `tests/unit/domains/news_intel/test_news_material_delta.py`
- `tests/unit/domains/news_intel/test_news_item_agent_admission.py`
- `tests/integration/domains/news_intel/test_news_agent_admission_repository.py`
- `tests/integration/domains/news_intel/test_news_agent_admission_repair.py`

Modify:

- `src/parallax/domains/news_intel/_constants.py`
- `src/parallax/domains/news_intel/types/news_item_brief.py`
- `src/parallax/domains/news_intel/prompts/news_item_brief.md`
- `src/parallax/domains/news_intel/services/news_item_brief_input.py`
- `src/parallax/domains/news_intel/services/news_item_brief_validation.py`
- `src/parallax/domains/news_intel/services/news_item_brief_stage.py`
- `src/parallax/domains/news_intel/services/news_item_agent_policy.py`
- `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- `src/parallax/domains/news_intel/runtime/news_projection_work.py`
- `src/parallax/app/runtime/projection_dirty_targets.py`
- `src/parallax/domains/news_intel/repositories/news_repository.py`
- `src/parallax/domains/news_intel/services/news_page_projection.py`
- `src/parallax/app/surfaces/cli/parser.py`
- `src/parallax/app/surfaces/cli/commands/ops.py`
- `src/parallax/domains/news_intel/ARCHITECTURE.md`
- `docs/AGENT_EXECUTION.md`
- `docs/WORKERS.md`
- `docs/CONTRACTS.md`
- `web/src/shared/model/newsIntel.ts`
- `web/src/lib/api/client.ts`
- `web/src/features/news/ui/NewsItemEvidencePage.tsx`
- `tests/unit/domains/news_intel/test_news_item_agent_policy.py`
- `tests/unit/domains/news_intel/test_news_item_brief_input.py`
- `tests/unit/domains/news_intel/test_news_item_brief_stage.py`
- `tests/unit/domains/news_intel/test_news_item_brief_validation.py`
- `tests/unit/domains/news_intel/test_news_item_brief_worker.py`
- `tests/unit/domains/news_intel/test_news_page_projection.py`
- `tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py`
- `tests/unit/test_api_news_contract.py`
- `tests/architecture/test_news_intel_boundaries.py`
- `tests/architecture/test_news_intel_kiss_simplification.py`

## Task 1: Storage Contract For Agent Admission

**Files:**

- Create: `src/parallax/platform/db/alembic/versions/20260606_0151_news_agent_market_admission_hard_cut.py`
- Modify: `src/parallax/domains/news_intel/_constants.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Test: `tests/unit/test_postgres_schema.py`
- Test: `tests/integration/domains/news_intel/test_news_agent_admission_repository.py`

- [ ] Add constants in `src/parallax/domains/news_intel/_constants.py`:
  ```python
  NEWS_ITEM_AGENT_ADMISSION_VERSION = "news_item_agent_admission_market_v1"
  NEWS_ITEM_BRIEF_PROMPT_VERSION = "news-item-brief-market-wide-v1"
  NEWS_ITEM_BRIEF_SCHEMA_VERSION = "news_item_brief_market_v1"
  NEWS_ITEM_BRIEF_VALIDATOR_VERSION = "news_item_brief_validator_market_v1"
  NEWS_ITEM_BRIEF_GUARDRAIL_VERSION = "news_item_brief_guardrails_market_v1"
  NEWS_PAGE_PROJECTION_VERSION = "news_page_rows_v5"
  ```
  Keep existing unrelated constants unchanged.

- [ ] Create Alembic migration `20260606_0151_news_agent_market_admission_hard_cut.py` with additive storage:
  ```python
  from __future__ import annotations

  from alembic import op

  revision = "20260606_0151"
  down_revision = "20260605_0150"
  branch_labels = None
  depends_on = None


  def upgrade() -> None:
      op.execute(
          """
          ALTER TABLE news_items
            ADD COLUMN IF NOT EXISTS agent_admission_status TEXT NOT NULL DEFAULT 'needs_review',
            ADD COLUMN IF NOT EXISTS agent_admission_reason TEXT NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS agent_admission_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS agent_admission_version TEXT NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS agent_representative_news_item_id TEXT NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS agent_admission_computed_at_ms BIGINT
          """
      )
      op.execute(
          """
          ALTER TABLE news_page_rows
            ADD COLUMN IF NOT EXISTS agent_admission_status TEXT NOT NULL DEFAULT 'needs_review',
            ADD COLUMN IF NOT EXISTS agent_admission_reason TEXT NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS agent_admission_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS agent_representative_news_item_id TEXT NOT NULL DEFAULT ''
          """
      )
      op.execute(
          """
          CREATE INDEX IF NOT EXISTS ix_news_items_agent_admission_published
            ON news_items(agent_admission_status, published_at_ms DESC, news_item_id)
          """
      )
      op.execute(
          """
          CREATE INDEX IF NOT EXISTS ix_news_page_rows_agent_admission
            ON news_page_rows(agent_admission_status, latest_at_ms DESC, row_id DESC)
          """
      )


  def downgrade() -> None:
      op.execute("DROP INDEX IF EXISTS ix_news_page_rows_agent_admission")
      op.execute("DROP INDEX IF EXISTS ix_news_items_agent_admission_published")
      for column_name in (
          "agent_representative_news_item_id",
          "agent_admission_json",
          "agent_admission_reason",
          "agent_admission_status",
      ):
          op.execute(f"ALTER TABLE news_page_rows DROP COLUMN IF EXISTS {column_name}")
      for column_name in (
          "agent_admission_computed_at_ms",
          "agent_representative_news_item_id",
          "agent_admission_version",
          "agent_admission_json",
          "agent_admission_reason",
          "agent_admission_status",
      ):
          op.execute(f"ALTER TABLE news_items DROP COLUMN IF EXISTS {column_name}")
  ```

- [ ] Add repository methods in `NewsRepository` with these signatures and behaviours:
  ```python
  def update_item_agent_admission(
      self,
      *,
      news_item_id: str,
      admission: Any,
      now_ms: int,
      commit: bool = True,
  ) -> int:
      # Persist admission status/reason/json/version/representative/computed_at_ms.
      # Return the updated row count.

  def load_agent_admission_contexts(self, *, news_item_ids: Sequence[str], now_ms: int) -> list[dict[str, Any]]:
      # Return one bounded context per requested item, including item,
      # entities, token mentions, fact candidates, current brief,
      # exact duplicate candidates, and story candidates.

  def list_agent_admission_repair_candidates(
      self,
      *,
      since_ms: int,
      until_ms: int,
      min_provider_score: int,
      limit: int,
  ) -> list[dict[str, Any]]:
      # Return processed provider-scored items inside the requested window
      # that need market-wide agent admission evaluation.
  ```
  `update_item_agent_admission` writes only `news_items.agent_admission_*`. It must not touch `analysis_admission_*`.

- [ ] Update `upsert_news_page_rows` payload handling so page rows persist `agent_admission_status`, `agent_admission_reason`, `agent_admission_json`, and `agent_representative_news_item_id`.

- [ ] Add schema assertions in `tests/unit/test_postgres_schema.py` for the new columns and indexes.

- [ ] Add integration tests in `tests/integration/domains/news_intel/test_news_agent_admission_repository.py`:
  Define local factories in this test file named `_seed_processed_news_item`, `_agent_admission_fixture`, and `_page_row_fixture`; do not assume these helpers already exist.
  ```python
  def test_update_item_agent_admission_persists_without_touching_analysis_admission(news_repo):
      news_item_id = _seed_processed_news_item(news_repo, analysis_admission_status="page_only")
      updated = news_repo.update_item_agent_admission(
          news_item_id=news_item_id,
          admission=_agent_admission_fixture(status="eligible", reason="provider_score_high"),
          now_ms=2_000,
      )
      row = news_repo.get_news_item_detail(news_item_id)
      assert updated == 1
      assert row["agent_admission"]["status"] == "eligible"
      assert row["analysis_admission_status"] == "page_only"

  def test_page_row_persists_agent_admission_fields(news_repo):
      row = _page_row_fixture(agent_admission_status="similar_story_covered")
      news_repo.upsert_news_page_rows([row])
      listed = news_repo.list_news_page_rows(limit=10)
      assert listed[0]["agent_admission_status"] == "similar_story_covered"
  ```

- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/test_postgres_schema.py \
    tests/integration/domains/news_intel/test_news_agent_admission_repository.py
  ```
  Expected: exit 0.

## Task 2: Market-Wide Brief Types And Packet Hard Cut

**Files:**

- Modify: `src/parallax/domains/news_intel/types/news_item_brief.py`
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_input.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_input.py`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_types.py`

- [ ] In `types/news_item_brief.py`, replace token-first output/input with market-wide entities:
  ```python
  NewsMarketDomain = Literal[
      "crypto",
      "us_equity",
      "macro_rates",
      "energy_geopolitics",
      "ai_semiconductors",
      "regulation",
      "private_company",
      "commodity",
      "fx",
      "unknown",
  ]
  NewsEntityType = Literal[
      "crypto_asset",
      "equity_symbol",
      "company",
      "private_company",
      "regulator",
      "central_bank",
      "country",
      "commodity",
      "macro_indicator",
      "sector",
      "unknown",
  ]

  class NewsItemBriefEntityLane(BaseModel):
      model_config = ConfigDict(extra="forbid")
      entity_id: str = Field(min_length=1, max_length=160)
      observed_label: str = Field(default="", max_length=160)
      display_symbol: str | None = Field(default=None, max_length=64)
      display_name: str | None = Field(default=None, max_length=160)
      entity_type: NewsEntityType = "unknown"
      market_domain: NewsMarketDomain = "unknown"
      resolution_status: str = Field(default="unknown", max_length=64)
      target_type: str | None = Field(default=None, max_length=80)
      target_id: str | None = Field(default=None, max_length=160)
      role: str = Field(default="mentioned", max_length=64)
      confidence: float | None = Field(default=None, ge=0.0, le=1.0)
      evidence_refs: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(default_factory=list, max_length=8)
      candidate_targets: list[dict[str, object]] = Field(default_factory=list, max_length=12)

  class AffectedEntity(BaseModel):
      model_config = ConfigDict(extra="forbid")
      label: str = Field(min_length=1, max_length=160)
      symbol: str | None = Field(default=None, max_length=64)
      name: str | None = Field(default=None, max_length=160)
      entity_type: NewsEntityType = "unknown"
      market_domain: NewsMarketDomain = "unknown"
      resolution_status: str = Field(default="unknown", max_length=64)
      target_type: str | None = Field(default=None, max_length=80)
      target_id: str | None = Field(default=None, max_length=160)
      impact_direction: NewsItemBriefDirection = "neutral"
      reason_zh: str = Field(default="", max_length=400)
      evidence_refs: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(default_factory=list, max_length=8)

  class TransmissionPath(BaseModel):
      model_config = ConfigDict(extra="forbid")
      market_domain: NewsMarketDomain = "unknown"
      channel: str = Field(min_length=1, max_length=80)
      direction: NewsItemBriefDirection = "neutral"
      strength: NewsItemBriefSideStrength = "weak"
      explanation_zh: str = Field(default="", max_length=360)
      evidence_refs: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(default_factory=list, max_length=8)
  ```

- [ ] Hard-cut `NewsItemBriefPayload`:
  - Add `event_type: str | None`.
  - Add `market_domains: list[NewsMarketDomain]`.
  - Add `transmission_paths: list[TransmissionPath]`.
  - Replace `affected_assets` with `affected_entities`.
  - Remove `AffectedAsset` and `NewsItemBriefAssetResolutionStatus` exports.

- [ ] Hard-cut `NewsItemBriefInputPacket`:
  - Replace `token_lanes` with `entity_lanes`.
  - Add `market_scope: list[NewsMarketDomain]`.
  - Add `agent_admission: dict[str, object]`.
  - Add `similarity: dict[str, object]`.
  - Add `material_delta: dict[str, object]`.
  - Keep `fact_lanes`, `provider_signal_evidence`, constraints, versions, input hash.

- [ ] Update `build_news_item_brief_input_packet` to this exact signature:
  ```python
  def build_news_item_brief_input_packet(
      *,
      item: Mapping[str, Any],
      entities: Sequence[Mapping[str, Any]],
      token_mentions: Sequence[Mapping[str, Any]],
      fact_candidates: Sequence[Mapping[str, Any]],
      agent_config: NewsItemBriefAgentConfig,
  ) -> NewsItemBriefInputPacket:
      # Build and return the market-wide packet with entity_lanes,
      # market_scope, admission, similarity, and material_delta fields.
  ```
  Convert crypto token mentions into `entity_lanes` with `entity_type="crypto_asset"` and `market_domain="crypto"`. Convert `news_item_entities` rows into company/regulator/country/private-company/macros when available. Do not expose `token_lanes` in the packet.

- [ ] Update `news_item_brief_material_input_hash` to include new `market_scope`, `agent_admission`, `similarity`, `material_delta`, and `entity_lanes` because these are material to prompt behavior.

- [ ] Update `NewsRepository.load_items_for_brief_targets` and page projection loaders to return `entities` for candidates.

- [ ] Update `NewsItemBriefWorker._packet_from_candidate`:
  ```python
  return build_news_item_brief_input_packet(
      item=_dict(candidate.get("item") or candidate),
      entities=_list_of_dicts(candidate.get("entities")),
      token_mentions=_list_of_dicts(candidate.get("token_mentions")),
      fact_candidates=_list_of_dicts(candidate.get("fact_candidates")),
      agent_config=agent_config,
  )
  ```

- [ ] Rewrite `tests/unit/domains/news_intel/test_news_item_brief_input.py`:
  - Assert `entity_lanes` exists and `token_lanes` is absent.
  - Assert BTC/SOL token mentions become crypto entity lanes.
  - Assert company/private-company/regulator entities become non-crypto entity lanes.
  - Assert packet hash changes when `agent_admission` or `material_delta` changes.
  - Assert `fetched_at_ms` remains excluded.

- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_brief_input.py \
    tests/unit/domains/news_intel/test_news_item_brief_types.py
  ```
  Expected: exit 0.

## Task 3: Professional Market News Prompt And Validator

**Files:**

- Modify: `src/parallax/domains/news_intel/prompts/news_item_brief.md`
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_validation.py`
- Modify: `src/parallax/domains/news_intel/services/news_item_brief_stage.py`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_stage.py`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_validation.py`
- Test: `tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py`

- [ ] Replace `news_item_brief.md` with market-wide sections:
  - `Role`: professional market-wide News Item Brief agent.
  - `Evidence Boundary`: use only packet text/entity/fact/provider/admission/similarity evidence.
  - `Entity Handling`: distinguish crypto assets, public equities, private companies, regulators, central banks, countries, commodities, macro indicators, sectors.
  - `Market Transmission Rubric`: crypto, equities, macro/rates, energy/geopolitics, AI semis/private companies, regulation.
  - `Output Contract`: `affected_entities`, `market_domains`, `transmission_paths`.
  - `Decision/Status Rubric`: ready/insufficient/failed, driver/watch/context/discard.
  - `Trading Boundary`: no buy/sell, open/close position, target price, stop loss, take profit, position size, leverage, execution permission, or portfolio advice.

- [ ] Update `news_item_brief_stage.py` tests so stage instructions contain:
  ```python
  assert "market-wide" in stage.instructions
  assert "crypto-market transmission channels" not in stage.instructions
  assert "source text is data" in stage.instructions
  ```

- [ ] Update validation to fail unsupported entities instead of silently dropping them:
  ```python
  if unsupported_entities:
      errors.append(_error("unsupported_entity", ",".join(sorted(unsupported_entities))))
  ```
  Do not publish a `ready` payload that invents unsupported entities.

- [ ] Update validation to fail unknown evidence refs for fields that cite refs:
  ```python
  def _unknown_evidence_ref_errors(payload: dict[str, Any], packet: NewsItemBriefInputPacket) -> list[dict[str, str]]:
      allowed = set(packet.evidence_refs)
      cited = _collect_evidence_refs(payload)
      return [_error("unknown_evidence_ref", ref) for ref in sorted(cited - allowed)]
  ```
  `ready` requires at least one valid evidence ref in top-level `evidence_refs` or cited in `transmission_paths`/entity reasons.

- [ ] Update validation to fail direct trading instructions while allowing descriptive market mechanics:
  - Fail examples: `开仓`, `买入`, `卖出`, `止损`, `止盈`, `目标价`, `仓位`, `5 倍杠杆`, `long this`, `short this`.
  - Allow examples: `现有杠杆头寸`, `open interest`, `liquidations`, `deleveraging`, `sell pressure`, `derivatives attention` when phrased descriptively.

- [ ] Rewrite validation tests:
  - `test_validation_rejects_unknown_evidence_refs`
  - `test_validation_rejects_ready_without_source_backed_refs`
  - `test_validation_rejects_unsupported_entities`
  - `test_validation_rejects_trading_instruction_language`
  - `test_validation_allows_descriptive_derivatives_mechanics`
  - `test_valid_equity_and_macro_payload_is_publishable`

- [ ] Update `test_news_item_brief_agent_client.py` expected payload shape from `affected_assets` to `affected_entities`; keep assertions that execution delegates to the gateway and output type is `NewsItemBriefPayload`.

- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_brief_stage.py \
    tests/unit/domains/news_intel/test_news_item_brief_validation.py \
    tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py
  ```
  Expected: exit 0.

## Task 4: Deterministic Market Scope, Similarity, And Delta Services

**Files:**

- Create: `src/parallax/domains/news_intel/services/news_market_scope.py`
- Create: `src/parallax/domains/news_intel/services/news_story_similarity.py`
- Create: `src/parallax/domains/news_intel/services/news_material_delta.py`
- Test: `tests/unit/domains/news_intel/test_news_market_scope.py`
- Test: `tests/unit/domains/news_intel/test_news_story_similarity.py`
- Test: `tests/unit/domains/news_intel/test_news_material_delta.py`

- [ ] Implement `news_market_scope.py` with:
  ```python
  @dataclass(frozen=True, slots=True)
  class NewsMarketScope:
      domains: list[str]
      basis: dict[str, Any]

  def infer_news_market_scope(
      *,
      item: Mapping[str, Any],
      entities: Sequence[Mapping[str, Any]],
      token_mentions: Sequence[Mapping[str, Any]],
      fact_candidates: Sequence[Mapping[str, Any]],
  ) -> NewsMarketScope:
      # Return deterministic market domains and evidence basis.
  ```
  Rules: crypto token mentions -> `crypto`; equity/private-company/company keywords/entities -> `us_equity` or `private_company`; Fed/rates/inflation/dollar -> `macro_rates`; oil/Iran/sanctions/geopolitics -> `energy_geopolitics`; NVIDIA/semiconductor/AI chip -> `ai_semiconductors`; fallback `unknown`.

- [ ] Implement `news_story_similarity.py` with:
  ```python
  @dataclass(frozen=True, slots=True)
  class NewsSimilarityEvidence:
      exact_duplicate: bool
      similar_story: bool
      reason: str
      representative_news_item_id: str
      story_key: str
      evidence: dict[str, Any]
	  ```
	  Strong exact duplicate reasons: `same_provider_article_id`, `same_article_url`, `same_content_hash`. Similar reasons: `same_story_key`, `same_material_title_bucket`, `same_entity_event_window`. Homepage/live/container URL alone is never exact.
	  Production-data constraint: existing `story_key` alone is insufficient for OpenNews-style feeds because article ids can be unique for many updates in the same event. The service must include title/entity/time-bucket similarity beyond exact `story_key`. Add a fixture shaped like the 2026-06-05 Iran/Hormuz burst where multiple score>=80 items have distinct OpenNews article keys but collapse to one representative plus similar-story suppressed members.

- [ ] Implement `news_material_delta.py` with:
  ```python
  @dataclass(frozen=True, slots=True)
  class NewsMaterialDelta:
      has_delta: bool
      reasons: list[str]
      evidence: dict[str, Any]
  ```
  Delta reasons: `source_role_upgrade`, `provider_score_upgrade`, `provider_signal_ready_upgrade`, `new_market_entity`, `new_accepted_fact`, `new_material_content`, `representative_brief_stale`.

- [ ] Unit tests:
  - SpaceX/private company -> `private_company`, not filtered as non-crypto.
  - NVIDIA/AI chip -> `ai_semiconductors`.
  - Fed/rates -> `macro_rates`.
	  - Same OpenNews article id -> exact duplicate.
	  - Distinct OpenNews article ids about the same Iran/Hormuz burst -> similar story, not independent agent runs.
	  - Same story with no new entity/fact -> no material delta.
  - Same story with official source upgrade -> material delta.

- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_market_scope.py \
    tests/unit/domains/news_intel/test_news_story_similarity.py \
    tests/unit/domains/news_intel/test_news_material_delta.py
  ```
  Expected: exit 0.

## Task 5: Market-Wide Agent Admission Policy

**Files:**

- Create: `src/parallax/domains/news_intel/services/news_item_agent_admission.py`
- Modify: `src/parallax/domains/news_intel/services/news_item_agent_policy.py`
- Test: `tests/unit/domains/news_intel/test_news_item_agent_admission.py`
- Test: `tests/unit/domains/news_intel/test_news_item_agent_policy.py`

- [ ] Implement `news_item_agent_admission.py`:
  ```python
  NewsItemAgentAdmissionStatus = Literal[
      "eligible",
      "eligible_refresh",
      "exact_duplicate",
      "similar_story_covered",
      "similar_story_burst",
      "materially_superseded",
      "score_below_threshold",
      "source_suppressed",
      "operational_disabled",
      "needs_review",
  ]

  @dataclass(frozen=True, slots=True)
  class NewsItemAgentAdmission:
      eligible: bool
      status: NewsItemAgentAdmissionStatus
      reason: str
      representative_news_item_id: str
      basis: dict[str, Any]
      version: str
  ```

- [ ] Implement base gates:
  - Reject not processed -> `needs_review/item_not_processed`.
  - Reject missing classification -> `needs_review/classification_missing`.
  - Reject suppressed/disabled source -> `source_suppressed`.
  - Reject non-provider signal -> `needs_review/source_not_provider_signal`.
  - Reject missing or <80 provider score -> `score_below_threshold`.
  - Reject missing/future/too-old published time -> `needs_review/published_at_*`.
  - Never read `analysis_admission_status` as an agent gate.

- [ ] Implement duplicate/similar decisions:
  - exact duplicate -> not eligible, status `exact_duplicate`, representative pointer required.
  - similar story without material delta -> not eligible, status `similar_story_covered`.
  - similar burst without material delta -> not eligible, status `similar_story_burst`.
  - similar story with material delta -> eligible, status `eligible_refresh`.
  - no duplicate/similar -> eligible, status `eligible`.

- [ ] Hard-cut `news_item_agent_policy.py` so existing imports keep working but old behavior is gone:
  ```python
  def news_item_agent_brief_eligibility(
      *,
      item: Mapping[str, Any],
      token_mentions: Sequence[Mapping[str, Any]],
      fact_candidates: Sequence[Mapping[str, Any]],
      now_ms: int,
      max_published_age_ms: int = NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS,
  ) -> NewsItemAgentBriefEligibility:
      admission = decide_news_item_agent_admission(
          item=item,
          entities=[],
          token_mentions=token_mentions,
          fact_candidates=fact_candidates,
          context=NewsItemAgentAdmissionContext.empty(),
          now_ms=now_ms,
          max_published_age_ms=max_published_age_ms,
      )
      return NewsItemAgentBriefEligibility(eligible=admission.eligible, reason=admission.reason)
  ```
  Remove `_has_explicit_crypto_admission_basis`, `NEWS_ITEM_AGENT_BRIEF_MIN_ADMITTED_PROVIDER_SCORE`, and all crypto evidence fallback code.

- [ ] Rewrite `tests/unit/domains/news_intel/test_news_item_agent_policy.py`:
  - `test_high_score_page_only_us_equity_is_eligible`
  - `test_high_score_macro_without_crypto_is_eligible`
  - `test_low_score_crypto_fallback_is_removed`
  - `test_analysis_not_admitted_is_never_agent_skip_reason`
  - existing processed/classification/source/score/time gates still pass.

- [ ] Add `tests/unit/domains/news_intel/test_news_item_agent_admission.py` for exact duplicate, similar covered, burst, and material delta statuses.

- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_item_agent_admission.py \
    tests/unit/domains/news_intel/test_news_item_agent_policy.py
  ```
  Expected: exit 0.

## Task 6: Repository Context Queries And Representative Selection

**Files:**

- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Test: `tests/integration/domains/news_intel/test_news_agent_admission_repository.py`
- Test: `tests/integration/domains/news_intel/test_news_repository.py`

- [ ] Implement `load_agent_admission_contexts` as a bounded query returning:
  ```python
  {
      "item": {"news_item_id": "news-1", "provider_signal_json": {"source": "provider", "score": 95}},
      "entities": [{"entity_id": "entity-1", "label": "NVIDIA", "entity_type": "company"}],
      "token_mentions": [{"mention_id": "token-1", "observed_symbol": "BTC"}],
      "fact_candidates": [{"fact_candidate_id": "fact-1", "event_type": "regulation"}],
      "current_brief": {"status": "ready", "input_hash": "sha256:current"} | None,
      "exact_duplicate_candidates": [{"news_item_id": "news-rep", "match_type": "same_content_hash"}],
      "story_candidates": [{"news_item_id": "news-story-rep", "story_key": "news-story:title:x:t1"}],
  }
  ```
  Query by explicit `news_item_ids`; do not add idle full-table scans.

- [ ] Exact duplicate candidate query must consider:
  - Same non-empty `provider_article_keys_json`.
  - Same `canonical_item_key` when non-empty.
  - Same article-like public URL only when `url_identity_kind='article'`.
  - Same strong `content_hash`.
  - Exclude the current item.

- [ ] Similar story candidate query must consider:
  - Same non-empty `story_key` inside the existing story projection window.
  - Enabled sources only.
  - Current brief contract predicate, so obsolete brief versions are stale.
  - Provider score and source role/trust for representative selection.

- [ ] Representative ordering:
  ```text
  current ready/insufficient brief with current contract
  > provider_signal.status=ready
  > source_role official/regulator/company/exchange
  > trust_tier official/high
  > provider score DESC
  > published_at_ms DESC
  > news_item_id ASC
  ```

- [ ] Integration tests:
  - Same OpenNews article id returns exact duplicate representative.
  - Same content hash returns exact duplicate representative.
  - Homepage/live URL alone does not return exact duplicate.
  - Same story with ready current brief returns similar story context.
  - Obsolete prompt/schema current brief is not treated fresh.

- [ ] Run:
  ```bash
  uv run pytest \
    tests/integration/domains/news_intel/test_news_agent_admission_repository.py \
    tests/integration/domains/news_intel/test_news_repository.py::test_load_items_for_brief_targets
  ```
  Expected: exit 0. If the named repository test does not exist, run the closest `load_items_for_brief_targets` test selected by `pytest -k load_items_for_brief_targets`.

## Task 7: Worker Flow Hard Cut

**Files:**

- Modify: `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_item_brief_worker.py`
- Modify: `src/parallax/app/runtime/projection_dirty_targets.py`
- Modify: `src/parallax/domains/news_intel/runtime/news_projection_work.py`
- Test: `tests/unit/domains/news_intel/test_news_workers.py`
- Test: `tests/unit/domains/news_intel/test_news_item_brief_worker.py`
- Test: `tests/unit/domains/news_intel/test_news_projection_work.py`

- [ ] Update `NewsItemProcessWorker` after story identity persistence:
  1. Load agent admission context for the processed item.
  2. Decide market-wide agent admission.
  3. Persist `agent_admission_*`.
  4. Always enqueue page reprojection.
  5. Enqueue `brief_input` only when admission status is `eligible` or `eligible_refresh`, using `representative_news_item_id`.

- [ ] Ensure process worker never gates brief work on `analysis_admission_status`.

- [ ] Update `NewsItemBriefWorker` claim loop:
  - Recompute admission with current DB context before packet build.
  - If admission is duplicate/similar/superseded, persist latest admission, mark target done, dirty page row, and do not call `provider.request_audit()` or `provider.brief_item()`.
  - If current brief is fresh, mark done without run ledger, as today.
  - If eligible, build new market-wide packet and execute through provider/gateway.

- [ ] Update `projection_dirty_targets.py` to use market-wide policy for manual/repair brief target enqueue. Remove any path where `analysis_admission_status` decides brief input eligibility.

- [ ] Unit tests:
  - Process worker enqueues score 95 US equity with `analysis_admission_status=page_only`.
  - Process worker does not enqueue exact duplicate and persists representative pointer.
  - Brief worker policy skip does not call request audit and writes no run ledger.
  - Brief worker eligible path still reserves before claim and releases reservation.

- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_workers.py \
    tests/unit/domains/news_intel/test_news_item_brief_worker.py \
    tests/unit/domains/news_intel/test_news_projection_work.py
  ```
  Expected: exit 0.

## Task 8: Page Projection, API Contract, And Frontend Hard Cut

**Files:**

- Modify: `src/parallax/domains/news_intel/services/news_page_projection.py`
- Modify: `src/parallax/domains/news_intel/repositories/news_repository.py`
- Modify: `tests/unit/test_api_news_contract.py`
- Modify: `tests/unit/domains/news_intel/test_news_page_projection.py`
- Modify: `web/src/shared/model/newsIntel.ts`
- Modify: `web/src/lib/api/client.ts`
- Modify: `web/src/features/news/ui/NewsItemEvidencePage.tsx`
- Modify: `web/tests/component/features/news/NewsPage.test.tsx`

- [ ] Update `build_news_page_row` to include:
  ```python
  "agent_admission_status": item.get("agent_admission_status") or "needs_review",
  "agent_admission_reason": item.get("agent_admission_reason") or "",
  "agent_admission": _json_object(item.get("agent_admission_json")),
  "agent_representative_news_item_id": item.get("agent_representative_news_item_id") or item["news_item_id"],
  ```

- [ ] Update `_compact_agent_brief` to use `affected_entities`, `market_domains`, and `transmission_paths`. Remove `affected_assets` from public payload. Do not include old-field aliases.

- [ ] Update `signal_json.agent_signal`:
  - For eligible/pending: status stays `pending` or current brief status.
  - For duplicate/similar/superseded: status is `exact_duplicate`, `similar_story_covered`, `similar_story_burst`, or `materially_superseded`.
  - Include `representative_news_item_id`, `agent_admission_reason`, and compact similarity evidence.

- [ ] Keep external push logic separate:
  - `external_push_block_reason="analysis_not_admitted"` may remain only inside external push eligibility.
  - It must not appear as `agent_signal.status`, `agent_skip_reason`, or score>=80 brief admission reason.

- [ ] Update `_public_agent_brief_payload` to allow only new market-wide public fields:
  ```python
  public_fields = {
      "status",
      "direction",
      "decision_class",
      "event_type",
      "market_domains",
      "title_zh",
      "summary_zh",
      "market_read_zh",
      "bull_view",
      "bear_view",
      "affected_entities",
      "transmission_paths",
      "watch_triggers",
      "invalidation_conditions",
      "data_gaps",
      "evidence_refs",
      "prompt_version",
      "schema_version",
      "validator_version",
      "computed_at_ms",
  }
  ```

- [ ] Update frontend type `NewsAgentBrief`:
  - Remove `affected_assets`.
  - Add `affected_entities`, `market_domains`, `transmission_paths`, `event_type`.
  - Add row-level agent admission fields.

- [ ] Update `normalizeAgentBrief` in `web/src/lib/api/client.ts` to normalize `affected_entities` only.

- [ ] Update `NewsItemEvidencePage.tsx` label from `Affected assets JSON` to `Affected entities JSON`.

- [ ] Run:
  ```bash
  uv run pytest \
    tests/unit/domains/news_intel/test_news_page_projection.py \
    tests/unit/test_api_news_contract.py
  npm run lint --prefix web
  ```
  Expected: exit 0.

## Task 9: Bounded Repair / Backfill Command

**Files:**

- Create: `src/parallax/domains/news_intel/services/news_agent_admission_repair.py`
- Modify: `src/parallax/app/surfaces/cli/parser.py`
- Modify: `src/parallax/app/surfaces/cli/commands/ops.py`
- Test: `tests/integration/domains/news_intel/test_news_agent_admission_repair.py`
- Test: `tests/integration/test_api_http.py`

- [ ] Implement repair service:
  ```python
  def repair_news_agent_market_admission(
      *,
      conn: Any,
      since_ms: int,
      until_ms: int,
      min_provider_score: int = 80,
      limit: int = 500,
      dry_run: bool = True,
      now_ms: int | None = None,
  ) -> dict[str, Any]:
      # Return a dry-run/apply report and optionally persist agent admission
      # plus enqueue representative brief targets.
  ```
  It re-evaluates existing processed items in a bounded window, persists admission and enqueues `brief_input` only when `dry_run=False`.

- [ ] Add CLI command:
  ```text
  uv run parallax repair-news-agent-market-admission \
    --since-ms <ms> \
    --until-ms <ms> \
    --min-provider-score 80 \
    --limit 500 \
    --dry-run
  ```
  Add `--execute` as the only mutating mode. Default is dry-run.

- [ ] Repair output shape:
  ```json
  {
    "mode": "dry_run",
    "window": {"since_ms": 0, "until_ms": 0},
    "min_provider_score": 80,
    "evaluated": 0,
    "would_enqueue": 0,
    "enqueued": 0,
    "counts_by_status": {},
    "counts_by_previous_reason": {}
  }
  ```

- [ ] Integration tests:
  - Dry-run changes no rows and enqueues zero targets.
  - Execute enqueues non-duplicate score>=80 page-only equity/macro items.
  - Execute skips exact duplicate/similar no-delta items with persisted reason.
  - Running execute twice on the same window enqueues zero additional unchanged targets.

- [ ] Run:
  ```bash
  uv run pytest tests/integration/domains/news_intel/test_news_agent_admission_repair.py
  ```
  Expected: exit 0.

## Task 10: Architecture, Contracts, And Verification

**Files:**

- Modify: `src/parallax/domains/news_intel/ARCHITECTURE.md`
- Modify: `docs/AGENT_EXECUTION.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `tests/architecture/test_news_intel_boundaries.py`
- Modify: `tests/architecture/test_news_intel_kiss_simplification.py`
- Modify: `docs/superpowers/plans/active/2026-06-06-news-agent-market-wide-hard-cut-verification-cn.md`

- [ ] Update `src/parallax/domains/news_intel/ARCHITECTURE.md`:
  - Replace “admitted crypto-analysis rows” with “market-wide agent admission after deterministic duplicate/similar gate”.
  - State `analysis_admission_*` is legacy crypto-analysis/push diagnostic, not News Item Brief admission.
  - State prompt/schema/validator versions hard-cut old current briefs.

- [ ] Update `docs/AGENT_EXECUTION.md`:
  - Keep no runtime tool loop.
  - Change News item brief packet description from token lanes only to market-wide entity/fact/provider/admission/similarity packet.

- [ ] Update `docs/WORKERS.md`:
  - `news_item_process` owns market-wide admission/enqueue.
  - `news_item_brief` owns model execution and current brief writes only.
  - no-start backpressure behavior remains unchanged.

- [ ] Update `docs/CONTRACTS.md`:
  - `/api/news` returns `affected_entities`, `market_domains`, `transmission_paths`, and `agent_admission`.
  - Remove public mention of `affected_assets` for News brief.
  - Explain `analysis_not_admitted` only as external push block where applicable, not item brief skip.

- [ ] Add architecture tests:
  ```python
  def test_news_item_agent_policy_does_not_gate_on_analysis_admission() -> None:
      source = (SRC_ROOT / "domains/news_intel/services/news_item_agent_policy.py").read_text()
      assert "analysis_admission_status" not in source
      assert "analysis_not_admitted" not in source

  def test_news_item_brief_prompt_is_market_wide_not_crypto_only() -> None:
      prompt = (SRC_ROOT / "domains/news_intel/prompts/news_item_brief.md").read_text()
      assert "market-wide" in prompt
      assert "crypto-market transmission channels" not in prompt
  ```

- [ ] Generate/update public contracts if required by existing workflow:
  ```bash
  make regen-contract
  ```
  Expected: generated files update only if OpenAPI/frontend contract snapshots are part of this branch.

- [ ] Run targeted backend gate:
  ```bash
  uv run pytest \
    tests/architecture/test_news_intel_boundaries.py \
    tests/architecture/test_news_intel_kiss_simplification.py \
    tests/unit/domains/news_intel/test_news_item_agent_admission.py \
    tests/unit/domains/news_intel/test_news_item_agent_policy.py \
    tests/unit/domains/news_intel/test_news_item_brief_input.py \
    tests/unit/domains/news_intel/test_news_item_brief_stage.py \
    tests/unit/domains/news_intel/test_news_item_brief_validation.py \
    tests/unit/domains/news_intel/test_news_item_brief_worker.py \
    tests/unit/domains/news_intel/test_news_page_projection.py \
    tests/unit/integrations/model_execution/test_news_item_brief_agent_client.py \
    tests/integration/domains/news_intel/test_news_agent_admission_repository.py \
    tests/integration/domains/news_intel/test_news_agent_admission_repair.py \
    tests/unit/test_api_news_contract.py
  ```
  Expected: exit 0.

- [ ] Run frontend gate:
  ```bash
  npm run lint --prefix web
  ```
  Expected: exit 0.

- [ ] Run full completion gate:
  ```bash
  make check-all
  ```
  Expected: exit 0 before claiming completion.

- [ ] Create verification file `docs/superpowers/plans/active/2026-06-06-news-agent-market-wide-hard-cut-verification-cn.md` containing:
  - full command output for `make check-all`;
  - targeted command outputs;
  - `Coverage`;
  - `Skipped tests`;
  - `E2E golden path`;
  - known residual risks;
  - confirmation that no runtime compatibility path exists.

## Implementation Notes

- Keep each created service focused and under roughly 200 lines where practical. Prefer small dataclasses and pure functions for market scope, similarity, material delta, and final admission.
- Avoid ad hoc string parsing when existing normalized fields exist. Prefer provider article keys, canonical item key, URL identity kind, content hash, story key, existing entity/fact rows, and current brief contract predicates.
- The first implementation phase remains item-scoped. Do not introduce story-scoped `news_item_agent_briefs` storage or `target_kind=story` in this branch.
- Existing historical rows can remain in storage. They are not compatibility paths if current-contract predicates and schema versions prevent them from being served as fresh current output.
- If a test currently asserts permissive behavior such as allowing direct trading instructions, replace the assertion. Do not keep old permissive tests beside new strict tests.
