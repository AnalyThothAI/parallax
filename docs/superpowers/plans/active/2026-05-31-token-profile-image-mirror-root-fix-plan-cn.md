# Token Profile Image Mirror Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** close the durable token icon lifecycle so exact profile/evidence logo sources are admitted into `token_image_source_dirty_targets`, mirrored into `token_image_assets`, and projected as same-origin `/api/token-images/{image_id}` URLs without provider URL fallback.

**Architecture:** Make `TokenProfileCurrentWorker` the runtime source-admission owner because it already sees all exact profile source families for a target. Add narrow repository state queries and a small `TokenImageSourceAdmission` service, then hard-cut projection to use full image lifecycle states instead of ready-only lookups. Remove stale compatibility surfaces such as unused mirror source scanning knobs.

**Tech Stack:** Python 3.13, PostgreSQL dirty target queues, pytest, Alembic-managed schema already in place, `parallax ops` CLI, existing asset-market worker runtime.

---

**Status**: Draft
**Date**: 2026-05-31
**Owning spec**: `docs/superpowers/specs/active/2026-05-31-token-profile-image-mirror-kiss-root-fix-cn.md`
**Worktree**: `.worktrees/token-profile-image-mirror-root-fix/`
**Branch**: `codex/token-profile-image-mirror-root-fix`

## Hard-Cut Rules

- Do not add raw provider image URL fallback in frontend, API, CLI read models, or `token_profile_current`.
- Do not reintroduce `/api/token-image?url=...`.
- Do not make `token_image_mirror` scan provider/profile tables. It consumes `token_image_source_dirty_targets`.
- Do not keep unused `--source-limit` compatibility on `ops mirror-token-images`; there is no source scan after this fix.
- Do not let multiple runtime workers enqueue image source dirty targets. Runtime ownership is `token_profile_current`.
- Do not add a new DB table. Use `token_image_assets`, `token_image_source_dirty_targets`, and `token_profile_current_dirty_targets`.
- Do not use symbol-only logo matching.

## Pre-flight

- [ ] Confirm runtime config paths before live-data verification:

  ```bash
  uv run parallax config
  ```

  Expected: output reports `config_path` and `workers_config_path` under `/Users/qinghuan/.parallax/`. Do not print secrets.

- [ ] Create the isolated worktree required by `docs/WORKFLOW.md`:

  ```bash
  git worktree add .worktrees/token-profile-image-mirror-root-fix -b codex/token-profile-image-mirror-root-fix main
  cd .worktrees/token-profile-image-mirror-root-fix
  git branch --show-current
  git status --short
  ```

  Expected: branch is `codex/token-profile-image-mirror-root-fix`; status is clean.

- [ ] Baseline targeted tests:

  ```bash
  uv run pytest \
    tests/unit/test_token_profile_current_projection.py \
    tests/unit/test_token_profile_current_worker.py \
    tests/unit/test_token_image_mirror_worker.py \
    tests/integration/test_token_image_asset_repository.py \
    tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py \
    tests/integration/test_cli.py::test_cli_ops_mirror_token_images_is_db_only_and_closes_db \
    -q
  ```

  Expected: all selected tests pass before edits. If a baseline failure appears, record the exact failing test and stop before implementation.

## File Structure

- Modify `src/parallax/domains/asset_market/repositories/token_image_asset_repository.py` to expose full image asset lifecycle rows by source URL and remove the unused asset-row due claim method.
- Modify `src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py` to expose existing dirty rows by `(source_url_hash, target_type, target_id)` for admission dedupe and backoff preservation.
- Create `src/parallax/domains/asset_market/services/token_image_source_admission.py` for exact logo source candidate extraction and durable dirty-target admission.
- Modify `src/parallax/domains/asset_market/services/token_profile_current_projection.py` to accept target-specific `image_states_by_source_key` and classify missing icons with real lifecycle flags.
- Modify `src/parallax/domains/asset_market/runtime/token_profile_current_worker.py` to run admission inside the claimed target transaction before writing `token_profile_current`.
- Modify `src/parallax/app/surfaces/cli/parser.py` and `src/parallax/app/surfaces/cli/commands/ops.py` to remove the unused `--source-limit` mirror option and add one explicit maintenance command for current stuck rows.
- Modify `src/parallax/app/runtime/worker_manifest.py`, `docs/ARCHITECTURE.md`, `docs/WORKERS.md`, `docs/CONTRACTS.md`, and generated CLI help to match the hard-cut ownership.
- Add/update tests in the existing test files named in each task below.

## Task 1: Repository Lifecycle State APIs

**Files:**

- Modify: `src/parallax/domains/asset_market/repositories/token_image_asset_repository.py`
- Modify: `src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py`
- Modify: `tests/integration/test_token_image_asset_repository.py`
- Create: `tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py`
- Modify: `tests/architecture/test_runtime_worker_constraint_hard_cut.py`

- [ ] **Step 1: Write failing image asset lifecycle lookup test**

  Add to `tests/integration/test_token_image_asset_repository.py`:

  ```python
  def test_by_source_urls_returns_all_lifecycle_states_without_claiming(tmp_path):
      conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
      try:
          migrate(conn)
          repo = TokenImageAssetRepository(conn)
          pending_url = "https://gmgn.ai/external-res/pending.png"
          ready_url = "https://gmgn.ai/external-res/ready.png"
          error_url = "https://gmgn.ai/external-res/error.png"
          unsupported_url = "https://gmgn.ai/external-res/unsupported.svg"
          repo.upsert_pending_sources(
              [
                  _source_row(pending_url),
                  _source_row(ready_url),
                  _source_row(error_url),
                  _source_row(unsupported_url),
              ],
              now_ms=NOW_MS,
          )
          ready_row = repo.mark_ready(
              ready_url,
              media_type="image/png",
              file_extension=".png",
              content_sha256="a" * 64,
              byte_size=1234,
              storage_path="aaaaaaaa.png",
              now_ms=NOW_MS + 100,
          )
          repo.mark_error(error_url, error="429", now_ms=NOW_MS + 200, retry_ms=30_000)
          repo.mark_unsupported(
              unsupported_url,
              error="unsupported_image_bytes: svg",
              now_ms=NOW_MS + 300,
          )

          rows = repo.by_source_urls(
              [unsupported_url, pending_url, ready_url, error_url, ready_url]
          )
      finally:
          conn.close()

      assert set(rows) == {pending_url, ready_url, error_url, unsupported_url}
      assert rows[pending_url]["status"] == "pending"
      assert rows[ready_url] == ready_row
      assert rows[error_url]["status"] == "error"
      assert rows[unsupported_url]["status"] == "unsupported"
  ```

  Delete or rewrite `test_claim_due_sources_sets_durable_lease_before_returning_rows`; `TokenImageAssetRepository.claim_due_sources` is removed by this hard cut because asset rows are not the mirror input queue.

- [ ] **Step 2: Implement `TokenImageAssetRepository.by_source_urls` and remove dead asset claiming**

  In `src/parallax/domains/asset_market/repositories/token_image_asset_repository.py`, add:

  ```python
      def by_source_urls(self, source_urls: list[str]) -> dict[str, dict[str, Any]]:
          source_url_hashes = [_source_url_hash(source_url) for source_url in _unique_source_urls(source_urls)]
          if not source_url_hashes:
              return {}

          rows = self.conn.execute(
              """
              SELECT *
              FROM token_image_assets
              WHERE source_url_hash = ANY(%s)
              """,
              (source_url_hashes,),
          ).fetchall()
          return {str(row["source_url"]): dict(row) for row in rows}
  ```

  Delete `claim_due_sources`; after this plan the only mirror input is `token_image_source_dirty_targets`.

- [ ] **Step 3: Write failing dirty-target existing-state test**

  Create `tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py`:

  ```python
  from parallax.domains.asset_market.repositories.token_image_source_dirty_target_repository import (
      TokenImageSourceDirtyTargetRepository,
  )


  def test_existing_by_source_targets_uses_exact_dirty_target_identity() -> None:
      conn = _ScriptedConnection(
          [
              [
                  {
                      "source_url_hash": "hash-source",
                      "source_url": "https://gmgn.ai/external-res/token.png",
                      "target_type": "Asset",
                      "target_id": "asset-1",
                      "due_at_ms": 1_700_000_030_000,
                      "attempt_count": 2,
                  }
              ]
          ]
      )

      rows = TokenImageSourceDirtyTargetRepository(conn).existing_by_source_targets(
          [
              {
                  "source_url": "https://gmgn.ai/external-res/token.png",
                  "target_type": "Asset",
                  "target_id": "asset-1",
              }
          ]
      )

      sql = conn.sql[-1]
      assert "FROM token_image_source_dirty_targets" in sql
      assert "JOIN incoming" in sql
      assert rows[("hash-source", "Asset", "asset-1")]["attempt_count"] == 2
  ```

  Include this connection fake in the same file:

  ```python
  class _ScriptedConnection:
      def __init__(self, results):
          self.results = list(results)
          self.sql = []
          self.params = []
          self.commits = 0

      def execute(self, sql, params=None):
          self.sql.append(str(sql))
          self.params.append(params or {})
          return self

      def fetchall(self):
          if not self.results:
              return []
          result = self.results.pop(0)
          assert isinstance(result, list)
          return result

      def fetchone(self):
          rows = self.fetchall()
          return rows[0] if rows else None

      def commit(self):
          self.commits += 1
  ```

- [ ] **Step 4: Implement dirty-target exact lookup**

  In `src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py`, add:

  ```python
      def existing_by_source_targets(
          self,
          targets: Iterable[Mapping[str, Any]],
      ) -> dict[tuple[str, str, str], dict[str, Any]]:
          records = _target_identity_records(targets)
          if not records:
              return {}
          rows = self.conn.execute(
              """
              WITH incoming AS (
                SELECT *
                FROM unnest(
                  %(source_url_hashes)s::text[],
                  %(target_types)s::text[],
                  %(target_ids)s::text[]
                ) AS incoming(source_url_hash, target_type, target_id)
              )
              SELECT queue.*
              FROM token_image_source_dirty_targets queue
              JOIN incoming
                ON queue.source_url_hash = incoming.source_url_hash
               AND queue.target_type = incoming.target_type
               AND queue.target_id = incoming.target_id
              """,
              {
                  "source_url_hashes": [record["source_url_hash"] for record in records],
                  "target_types": [record["target_type"] for record in records],
                  "target_ids": [record["target_id"] for record in records],
              },
          ).fetchall()
          return {
              (str(row["source_url_hash"]), str(row["target_type"]), str(row["target_id"])): dict(row)
              for row in rows
          }
  ```

  Add helper:

  ```python
  def _target_identity_records(targets: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
      records: dict[tuple[str, str, str], dict[str, str]] = {}
      for target in targets:
          source_url = _required_source_url(target.get("source_url"))
          target_type = _required_text(target.get("target_type"), field_name="target_type")
          target_id = _required_text(target.get("target_id"), field_name="target_id")
          source_url_hash = _source_url_hash(source_url)
          records[(source_url_hash, target_type, target_id)] = {
              "source_url_hash": source_url_hash,
              "target_type": target_type,
              "target_id": target_id,
          }
      return list(records.values())
  ```

- [ ] **Step 5: Update architecture test that currently implies asset-row claiming**

  In `tests/architecture/test_runtime_worker_constraint_hard_cut.py`, remove `token_image_assets.claim_due_sources` from the `token_image_mirror` claim marker expectation. The worker should be a dirty-target consumer, not a dual queue scanner.

- [ ] **Step 6: Run Task 1 tests**

  ```bash
  uv run pytest \
    tests/integration/test_token_image_asset_repository.py \
    tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py \
    tests/architecture/test_runtime_worker_constraint_hard_cut.py \
    -q
  ```

  Expected: all pass.

## Task 2: Token Image Source Admission Service

**Files:**

- Create: `src/parallax/domains/asset_market/services/token_image_source_admission.py`
- Create: `tests/unit/test_token_image_source_admission.py`

- [ ] **Step 1: Write candidate extraction and admission tests**

  Create `tests/unit/test_token_image_source_admission.py`:

  ```python
  from parallax.domains.asset_market.services.token_image_source_admission import (
      image_source_candidates_for_target,
      admit_token_image_sources,
  )


  NOW_MS = 1_700_000_000_000


  def test_image_source_candidates_cover_all_exact_profile_source_families():
      candidates = image_source_candidates_for_target(
          target={"target_type": "Asset", "target_id": "asset-1"},
          gmgn_openapi={
              "logo_url": "https://gmgn.ai/external-res/gmgn.png",
              "provider": "gmgn_dex_profile",
              "observed_at_ms": 10,
          },
          binance_web3={
              "logo_url": "https://bin.bnbstatic.com/static/images/web3.png",
              "provider": "binance_web3_profile",
              "observed_at_ms": 20,
          },
          gmgn_stream={
              "evidence_id": "gmgn-evidence",
              "raw_payload_json": {"i": "https://gmgn.ai/external-res/stream.png"},
              "observed_at_ms": 30,
          },
          okx_dex={
              "evidence_id": "okx-evidence",
              "raw_payload_json": {"tokenLogoUrl": "https://static.okx.com/cdn/assets/token.png"},
              "observed_at_ms": 40,
          },
          cex_profile=None,
      )

      assert [(item.source_provider, item.source_kind) for item in candidates] == [
          ("gmgn_dex_profile", "asset_profiles.logo_url"),
          ("binance_web3_profile", "asset_profiles.logo_url"),
          ("gmgn_stream_snapshot", "asset_identity_evidence.raw_payload_json.i"),
          ("okx_dex_evidence", "asset_identity_evidence.raw_payload_json.tokenLogoUrl"),
      ]
      assert [item.source_watermark_ms for item in candidates] == [10, 20, 30, 40]


  def test_image_source_candidates_skip_invalid_and_placeholder_urls():
      candidates = image_source_candidates_for_target(
          target={"target_type": "Asset", "target_id": "asset-1"},
          gmgn_openapi={"logo_url": "http://gmgn.ai/external-res/insecure.png"},
          binance_web3={"logo_url": ""},
          gmgn_stream={"raw_payload_json": {"i": "not-a-url"}},
          okx_dex={"raw_payload_json": {"tokenLogoUrl": "https://static.okx.com/cdn/wallet/logo/default-logo/0.png"}},
          cex_profile=None,
      )

      assert candidates == []


  def test_admit_token_image_sources_enqueues_missing_sources_and_preserves_backoff():
      repos = FakeRepos(
          image_assets={
              "https://gmgn.ai/external-res/ready.png": {"status": "ready"},
              "https://gmgn.ai/external-res/error.png": {
                  "status": "error",
                  "next_refresh_at_ms": NOW_MS + 60_000,
              },
              "https://gmgn.ai/external-res/unsupported.svg": {"status": "unsupported"},
          },
          dirty_existing={},
      )
      candidates = [
          candidate("https://gmgn.ai/external-res/missing.png"),
          candidate("https://gmgn.ai/external-res/ready.png"),
          candidate("https://gmgn.ai/external-res/error.png"),
          candidate("https://gmgn.ai/external-res/unsupported.svg"),
      ]

      result = admit_token_image_sources(repos=repos, candidates=candidates, now_ms=NOW_MS)

      assert result.counts["admitted"] == 2
      assert result.counts["ready_existing"] == 1
      assert result.counts["unsupported_existing"] == 1
      assert repos.dirty.enqueued[0]["source_url"] == "https://gmgn.ai/external-res/missing.png"
      assert repos.dirty.enqueued[0]["due_at_ms"] == NOW_MS
      assert repos.dirty.enqueued[1]["source_url"] == "https://gmgn.ai/external-res/error.png"
      assert repos.dirty.enqueued[1]["due_at_ms"] == NOW_MS + 60_000
      missing_key = (
          candidates[0].source_url_hash,
          candidates[0].target_type,
          candidates[0].target_id,
      )
      error_key = (
          candidates[2].source_url_hash,
          candidates[2].target_type,
          candidates[2].target_id,
      )
      assert result.image_states_by_source_key[missing_key]["status"] == "mirror_pending"
      assert result.image_states_by_source_key[error_key]["status"] == "error"
  ```

  Include these helpers in the same test file:

  ```python
  class FakeRepos:
      def __init__(self, *, image_assets, dirty_existing):
          self.token_image_assets = FakeImageAssets(image_assets)
          self.token_image_source_dirty_targets = FakeDirtyTargets(dirty_existing)
          self.dirty = self.token_image_source_dirty_targets


  class FakeImageAssets:
      def __init__(self, rows_by_url):
          self.rows_by_url = rows_by_url
          self.calls = []

      def by_source_urls(self, source_urls):
          self.calls.append(list(source_urls))
          return {
              source_url: {"source_url": source_url, **self.rows_by_url[source_url]}
              for source_url in source_urls
              if source_url in self.rows_by_url
          }


  class FakeDirtyTargets:
      def __init__(self, rows_by_key):
          self.rows_by_key = rows_by_key
          self.enqueued = []

      def existing_by_source_targets(self, targets):
          return dict(self.rows_by_key)

      def enqueue_targets(self, targets, *, reason, now_ms, commit):
          assert reason == "token_profile_current_source_admission"
          assert commit is False
          self.enqueued.extend(dict(target) for target in targets)
          return {"targets": len(targets)}


  def candidate(source_url):
      return TokenImageSourceCandidate(
          target_type="Asset",
          target_id="asset-1",
          source_url=source_url,
          source_provider="gmgn_dex_profile",
          source_kind="asset_profiles.logo_url",
          source_watermark_ms=NOW_MS,
          priority=20,
          raw_ref_json={"asset_id": "asset-1"},
      )
  ```

- [ ] **Step 2: Implement `TokenImageSourceCandidate` and extraction**

  Create `src/parallax/domains/asset_market/services/token_image_source_admission.py`:

  ```python
  from __future__ import annotations

  from dataclasses import dataclass
  from hashlib import sha256
  from typing import Any


  @dataclass(frozen=True)
  class TokenImageSourceCandidate:
      target_type: str
      target_id: str
      source_url: str
      source_provider: str
      source_kind: str
      source_watermark_ms: int
      priority: int
      raw_ref_json: dict[str, Any]

      @property
      def source_url_hash(self) -> str:
          return sha256(self.source_url.encode("utf-8")).hexdigest()

      def as_dirty_target(self, *, due_at_ms: int) -> dict[str, Any]:
          return {
              "target_type": self.target_type,
              "target_id": self.target_id,
              "source_url": self.source_url,
              "source_provider": self.source_provider,
              "source_kind": self.source_kind,
              "source_watermark_ms": self.source_watermark_ms,
              "priority": self.priority,
              "due_at_ms": due_at_ms,
              "raw_ref_json": dict(self.raw_ref_json),
          }
  ```

  Add extraction:

  ```python
  def image_source_candidates_for_target(
      *,
      target: dict[str, Any],
      gmgn_openapi: dict[str, Any] | None,
      binance_web3: dict[str, Any] | None,
      gmgn_stream: dict[str, Any] | None,
      okx_dex: dict[str, Any] | None,
      cex_profile: dict[str, Any] | None,
  ) -> list[TokenImageSourceCandidate]:
      target_type = _required_clean(target.get("target_type"), "target_type")
      target_id = _required_clean(target.get("target_id"), "target_id")
      if target_type == "CexToken":
          return _candidate_from_row(
              target_type=target_type,
              target_id=target_id,
              source=cex_profile,
              source_url=(cex_profile or {}).get("logo_url"),
              source_provider=str((cex_profile or {}).get("provider") or "binance_cex_profile"),
              source_kind="cex_token_profiles.logo_url",
              priority=20,
              raw_ref_keys=("cex_token_id", "source_ref", "provider"),
          )
      candidates: list[TokenImageSourceCandidate] = []
      candidates.extend(
          _candidate_from_row(
              target_type=target_type,
              target_id=target_id,
              source=gmgn_openapi,
              source_url=(gmgn_openapi or {}).get("logo_url"),
              source_provider="gmgn_dex_profile",
              source_kind="asset_profiles.logo_url",
              priority=20,
              raw_ref_keys=("asset_id", "provider"),
          )
      )
      candidates.extend(
          _candidate_from_row(
              target_type=target_type,
              target_id=target_id,
              source=binance_web3,
              source_url=(binance_web3 or {}).get("logo_url"),
              source_provider="binance_web3_profile",
              source_kind="asset_profiles.logo_url",
              priority=30,
              raw_ref_keys=("asset_id", "provider"),
          )
      )
      gmgn_raw = _raw(gmgn_stream)
      candidates.extend(
          _candidate_from_row(
              target_type=target_type,
              target_id=target_id,
              source=gmgn_stream,
              source_url=gmgn_raw.get("i"),
              source_provider="gmgn_stream_snapshot",
              source_kind="asset_identity_evidence.raw_payload_json.i",
              priority=40,
              raw_ref_keys=("asset_id", "evidence_id", "source_event_id", "provider", "evidence_kind"),
          )
      )
      okx_raw = _raw(okx_dex)
      candidates.extend(
          _candidate_from_row(
              target_type=target_type,
              target_id=target_id,
              source=okx_dex,
              source_url=okx_raw.get("tokenLogoUrl"),
              source_provider="okx_dex_evidence",
              source_kind="asset_identity_evidence.raw_payload_json.tokenLogoUrl",
              priority=50,
              raw_ref_keys=("asset_id", "evidence_id", "source_event_id", "provider", "evidence_kind"),
          )
      )
      return _dedupe_candidates(candidates)
  ```

  Helper constraints:

  ```python
  def _usable_source_url(value: Any) -> str | None:
      text = str(value or "").strip()
      if not text.startswith("https://"):
          return None
      if "/default-logo/" in text:
          return None
      return text
  ```

  Use HTTPS only for new admissions. Existing HTTP rows are not introduced by this plan.

  Add the helper implementations in the same module:

  ```python
  def _candidate_from_row(
      *,
      target_type: str,
      target_id: str,
      source: dict[str, Any] | None,
      source_url: Any,
      source_provider: str,
      source_kind: str,
      priority: int,
      raw_ref_keys: tuple[str, ...],
  ) -> list[TokenImageSourceCandidate]:
      clean_url = _usable_source_url(source_url)
      if not clean_url or source is None:
          return []
      return [
          TokenImageSourceCandidate(
              target_type=target_type,
              target_id=target_id,
              source_url=clean_url,
              source_provider=source_provider,
              source_kind=source_kind,
              source_watermark_ms=_source_watermark_ms(source),
              priority=priority,
              raw_ref_json=_bounded_raw_ref(source, raw_ref_keys),
          )
      ]


  def _dedupe_candidates(candidates: list[TokenImageSourceCandidate]) -> list[TokenImageSourceCandidate]:
      deduped: dict[tuple[str, str, str], TokenImageSourceCandidate] = {}
      for candidate in candidates:
          key = (candidate.source_url_hash, candidate.target_type, candidate.target_id)
          current = deduped.get(key)
          if current is None or candidate.priority < current.priority:
              deduped[key] = candidate
      return sorted(deduped.values(), key=lambda item: (item.priority, item.source_url_hash, item.target_type, item.target_id))


  def _bounded_raw_ref(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
      return {key: str(source[key])[:256] for key in keys if source.get(key) not in (None, "")}


  def _raw(row: dict[str, Any] | None) -> dict[str, Any]:
      raw = (row or {}).get("raw_payload_json")
      return dict(raw) if isinstance(raw, dict) else {}


  def _source_watermark_ms(source: dict[str, Any]) -> int:
      value = source.get("observed_at_ms") or source.get("updated_at_ms") or 0
      try:
          return int(value)
      except (TypeError, ValueError, OverflowError):
          return 0


  def _required_clean(value: Any, field_name: str) -> str:
      text = str(value or "").strip()
      if not text:
          raise ValueError(f"token image source admission {field_name} is required")
      return text
  ```

- [ ] **Step 3: Implement admission with lifecycle states**

  Add:

  ```python
  @dataclass(frozen=True)
  class TokenImageSourceAdmissionResult:
      counts: dict[str, int]
      image_states_by_source_key: dict[tuple[str, str, str], dict[str, Any]]


  def admit_token_image_sources(
      *,
      repos: Any,
      candidates: list[TokenImageSourceCandidate],
      now_ms: int,
  ) -> TokenImageSourceAdmissionResult:
      unique_candidates = _dedupe_candidates(candidates)
      source_urls = [candidate.source_url for candidate in unique_candidates]
      asset_rows = repos.token_image_assets.by_source_urls(source_urls)
      dirty_rows = repos.token_image_source_dirty_targets.existing_by_source_targets(
          [candidate.as_dirty_target(due_at_ms=now_ms) for candidate in unique_candidates]
      )
      counts = _empty_counts()
      states: dict[tuple[str, str, str], dict[str, Any]] = {}
      enqueue_rows: list[dict[str, Any]] = []
      for candidate in unique_candidates:
          candidate_key = (candidate.source_url_hash, candidate.target_type, candidate.target_id)
          asset = asset_rows.get(candidate.source_url)
          dirty = dirty_rows.get(candidate_key)
          if asset is not None:
              status = str(asset.get("status") or "")
              counts[f"{status}_existing"] = int(counts.get(f"{status}_existing") or 0) + 1
              states[candidate_key] = dict(asset)
              if status in {"ready", "unsupported"}:
                  continue
              if status == "pending":
                  continue
              if status == "error" and dirty is not None:
                  counts["dirty_existing"] += 1
                  states[candidate_key] = {
                      "status": "mirror_pending",
                      "asset_status": "error",
                      "last_error": asset.get("last_error"),
                      "next_refresh_at_ms": asset.get("next_refresh_at_ms"),
                      **dict(dirty),
                  }
                  continue
              if dirty is None:
                  due_at_ms = _retry_due_at_ms(asset, now_ms=now_ms)
                  enqueue_rows.append(candidate.as_dirty_target(due_at_ms=due_at_ms))
              continue
          if dirty is not None:
              counts["dirty_existing"] += 1
              states[candidate_key] = {"status": "mirror_pending", **dict(dirty)}
              continue
          enqueue_rows.append(candidate.as_dirty_target(due_at_ms=now_ms))
          states[candidate_key] = {
              "status": "mirror_pending",
              "source_url": candidate.source_url,
              "source_provider": candidate.source_provider,
              "source_url_hash": candidate.source_url_hash,
          }
      if enqueue_rows:
          admitted = repos.token_image_source_dirty_targets.enqueue_targets(
              enqueue_rows,
              reason="token_profile_current_source_admission",
              now_ms=now_ms,
              commit=False,
          )
          counts["admitted"] = int(admitted.get("targets") or 0)
      counts["candidates"] = len(unique_candidates)
      return TokenImageSourceAdmissionResult(counts=counts, image_states_by_source_key=states)
  ```

  `_retry_due_at_ms` must return `max(now_ms, int(asset.get("next_refresh_at_ms") or now_ms))`, so error rows do not bypass backoff when their dirty row was lost.

  Add:

  ```python
  def _retry_due_at_ms(asset: dict[str, Any], *, now_ms: int) -> int:
      try:
          return max(int(now_ms), int(asset.get("next_refresh_at_ms") or now_ms))
      except (TypeError, ValueError, OverflowError):
          return int(now_ms)


  def _empty_counts() -> dict[str, int]:
      return {
          "candidates": 0,
          "admitted": 0,
          "ready_existing": 0,
          "pending_existing": 0,
          "error_existing": 0,
          "unsupported_existing": 0,
          "dirty_existing": 0,
      }
  ```

- [ ] **Step 4: Run Task 2 tests**

  ```bash
  uv run pytest tests/unit/test_token_image_source_admission.py -q
  ```

  Expected: all pass.

## Task 3: Wire Admission Into Token Profile Current Projection

**Files:**

- Modify: `src/parallax/domains/asset_market/runtime/token_profile_current_worker.py`
- Modify: `src/parallax/domains/asset_market/services/token_profile_current_projection.py`
- Modify: `tests/unit/test_token_profile_current_worker.py`
- Modify: `tests/unit/test_token_profile_current_projection.py`

- [ ] **Step 1: Write failing projection lifecycle classification tests**

  In `tests/unit/test_token_profile_current_projection.py`, replace ready-only parameter usage with target-specific `image_states_by_source_key`. Add:

  ```python
  def test_project_token_profile_current_marks_unsupported_logo_without_pending():
      logo_url = "https://gmgn.example/logo.svg"
      row = project_token_profile_current(
          target={"target_type": "Asset", "target_id": ASSET_ID},
          gmgn_openapi=gmgn_openapi_row(status="ready", logo_url=logo_url, symbol="GMGN"),
          binance_web3=None,
          gmgn_stream=None,
          okx_dex=None,
          image_states_by_source_key={(_source_hash(logo_url), "Asset", ASSET_ID): {"status": "unsupported", "last_error": "svg"}},
          computed_at_ms=10_000,
      )

      assert row["logo_url"] is None
      assert row["quality_flags"] == ["logo_mirror_unsupported"]


  def test_project_token_profile_current_marks_failed_logo_without_fake_pending():
      logo_url = "https://gmgn.example/logo.png"
      row = project_token_profile_current(
          target={"target_type": "Asset", "target_id": ASSET_ID},
          gmgn_openapi=gmgn_openapi_row(status="ready", logo_url=logo_url, symbol="GMGN"),
          binance_web3=None,
          gmgn_stream=None,
          okx_dex=None,
          image_states_by_source_key={(_source_hash(logo_url), "Asset", ASSET_ID): {"status": "error", "last_error": "429"}},
          computed_at_ms=10_000,
      )

      assert row["logo_url"] is None
      assert row["quality_flags"] == ["logo_mirror_failed"]
  ```

- [ ] **Step 2: Hard-cut projection signature**

  Change `project_token_profile_current` signature:

  ```python
  def project_token_profile_current(
      *,
      target: dict[str, Any],
      gmgn_openapi: dict[str, Any] | None,
      binance_web3: dict[str, Any] | None,
      gmgn_stream: dict[str, Any] | None,
      okx_dex: dict[str, Any] | None,
      computed_at_ms: int,
      cex_profile: dict[str, Any] | None = None,
      image_states_by_source_key: dict[tuple[str, str, str], dict[str, Any]] | None = None,
  ) -> dict[str, Any]:
  ```

  Delete the old `ready_images_by_source_url` parameter instead of keeping compatibility. Update every caller and test.

- [ ] **Step 3: Replace ready-only logo projection with lifecycle-aware state**

  Update `_project_logo`:

  ```python
  def _project_logo(
      provider_logo_url: Any,
      image_states_by_source_key: dict[tuple[str, str, str], dict[str, Any]],
      *,
      selected_source_provider: str | None = None,
  ) -> dict[str, Any]:
      source_url = _clean(provider_logo_url)
      fields = _empty_logo([])
      missing_flags = _source_without_logo_flags(source_url)
      if missing_flags:
          fields["quality_flags"] = missing_flags
          return fields

      source_key = (_source_url_hash(str(source_url)), str(target_type), str(target_id))
      image_state = image_states_by_source_key.get(source_key)
      status = str((image_state or {}).get("status") or "")
      public_url = _clean((image_state or {}).get("public_url"))
      if status == "ready" and public_url:
          fields["logo_url"] = public_url
          fields["logo_image_id"] = _clean((image_state or {}).get("image_id"))
          fields["logo_source_provider"] = _clean(selected_source_provider) or _clean(
              (image_state or {}).get("source_provider")
          )
          fields["logo_source_url_hash"] = _clean((image_state or {}).get("source_url_hash"))
          return fields
      if status == "unsupported":
          fields["quality_flags"] = ["logo_mirror_unsupported"]
          return fields
      if status == "error":
          fields["quality_flags"] = ["logo_mirror_failed"]
          return fields
      if status in {"pending", "mirror_pending"}:
          fields["quality_flags"] = ["logo_mirror_pending"]
          return fields
      fields["quality_flags"] = ["source_not_admitted"]
      return fields
  ```

  Update `_select_logo` so lower-priority ready candidates still win over higher-priority pending/error/unsupported candidates. If no ready candidate exists, return the first non-ready lifecycle flag in candidate priority order.

- [ ] **Step 4: Write failing worker admission test**

  In `tests/unit/test_token_profile_current_worker.py`, update fakes and add:

  ```python
  def test_rebuild_token_profile_current_once_admits_missing_image_sources_before_projection():
      repos = FakeRepos(
          claims=[claim("Asset", "asset:gmgn")],
          gmgn_openapi={
              "asset:gmgn": {
                  "asset_id": "asset:gmgn",
                  "provider": "gmgn_dex_profile",
                  "status": "ready",
                  "symbol": "GMGN",
                  "logo_url": "https://gmgn.ai/external-res/gmgn.png",
                  "raw_payload_json": {"profile": True},
                  "observed_at_ms": 1_000,
              }
          },
          binance_web3={},
          gmgn_stream={},
          okx_dex={},
          cex_profiles={},
          image_assets_by_source_url={},
          dirty_existing={},
      )

      result = module.rebuild_token_profile_current_once(
          repos=repos,
          now_ms=10_000,
          limit=100,
          lease_owner="profile-worker",
          lease_ms=60_000,
          retry_ms=30_000,
      )

      assert result["image_candidates"] == 1
      assert result["image_sources_admitted"] == 1
      assert repos.image_dirty.enqueued[0]["source_url"] == "https://gmgn.ai/external-res/gmgn.png"
      assert repos.token_profiles.rows[0]["logo_url"] is None
      assert repos.token_profiles.rows[0]["quality_flags"] == ["logo_mirror_pending"]
  ```

- [ ] **Step 5: Implement worker admission before projection**

  In `src/parallax/domains/asset_market/runtime/token_profile_current_worker.py`, import:

  ```python
  from parallax.domains.asset_market.services.token_image_source_admission import (
      admit_token_image_sources,
      image_source_candidates_for_target,
  )
  ```

  Replace `_ready_images_by_source_url(...)` with:

  ```python
  def _image_source_candidates_for_targets(
      *,
      targets: list[dict[str, str]],
      gmgn_openapi: dict[str, dict[str, Any]],
      binance_web3: dict[str, dict[str, Any]],
      gmgn_stream: dict[str, dict[str, Any]],
      okx_dex: dict[str, dict[str, Any]],
      cex_profiles: dict[str, dict[str, Any]],
  ) -> list[Any]:
      candidates: list[Any] = []
      for target in targets:
          target_id = str(target.get("target_id") or "")
          candidates.extend(
              image_source_candidates_for_target(
                  target=target,
                  gmgn_openapi=gmgn_openapi.get(target_id),
                  binance_web3=binance_web3.get(target_id),
                  gmgn_stream=gmgn_stream.get(target_id),
                  okx_dex=okx_dex.get(target_id),
                  cex_profile=cex_profiles.get(target_id),
              )
          )
      return candidates
  ```

  In `_project_claimed_token_profiles`, after loading profile sources:

  ```python
      image_candidates = _image_source_candidates_for_targets(
          targets=targets,
          gmgn_openapi=gmgn_openapi,
          binance_web3=binance_web3,
          gmgn_stream=gmgn_stream,
          okx_dex=okx_dex,
          cex_profiles=cex_profiles,
      )
      admission = admit_token_image_sources(
          repos=repos,
          candidates=image_candidates,
          now_ms=now_ms,
      )
      _record_image_admission(result, admission.counts)
      image_states_by_source_key = admission.image_states_by_source_key
  ```

  Then pass `image_states_by_source_key=image_states_by_source_key` into `project_token_profile_current`.

- [ ] **Step 6: Update worker result counters**

  Add to `_empty_result`:

  ```python
          "image_candidates": 0,
          "image_sources_admitted": 0,
          "image_ready_existing": 0,
          "image_pending_existing": 0,
          "image_error_existing": 0,
          "image_unsupported_existing": 0,
          "image_dirty_existing": 0,
  ```

  Add:

  ```python
  def _record_image_admission(result: dict[str, Any], counts: dict[str, int]) -> None:
      result["image_candidates"] += int(counts.get("candidates") or 0)
      result["image_sources_admitted"] += int(counts.get("admitted") or 0)
      result["image_ready_existing"] += int(counts.get("ready_existing") or 0)
      result["image_pending_existing"] += int(counts.get("pending_existing") or 0)
      result["image_error_existing"] += int(counts.get("error_existing") or 0)
      result["image_unsupported_existing"] += int(counts.get("unsupported_existing") or 0)
      result["image_dirty_existing"] += int(counts.get("dirty_existing") or 0)
  ```

- [ ] **Step 7: Run Task 3 tests**

  ```bash
  uv run pytest \
    tests/unit/test_token_profile_current_projection.py \
    tests/unit/test_token_profile_current_worker.py \
    -q
  ```

  Expected: all pass and no call site still references `ready_images_by_source_url`.

## Task 4: Hard-Cut CLI and Maintenance Repair Path

**Files:**

- Modify: `src/parallax/app/surfaces/cli/parser.py`
- Modify: `src/parallax/app/surfaces/cli/commands/ops.py`
- Modify: `tests/integration/test_cli.py`
- Modify: `docs/generated/cli-help.md`

- [ ] **Step 1: Remove unused `--source-limit` from mirror command tests**

  In `tests/integration/test_cli.py`, change invocations from:

  ```python
  ["ops", "mirror-token-images", "--limit", "3", "--source-limit", "9"]
  ```

  to:

  ```python
  ["ops", "mirror-token-images", "--limit", "3"]
  ```

  Assert the worker override only includes `batch_size=3`; do not assert `source_limit`.

- [ ] **Step 2: Hard-cut parser and ops command signature**

  In `src/parallax/app/surfaces/cli/parser.py`, delete:

  ```python
  mirror_token_images.add_argument("--source-limit", type=int, default=5000)
  ```

  In `src/parallax/app/surfaces/cli/commands/ops.py`, change:

  ```python
  def _run_token_image_mirror_worker_once(settings: object, *, limit: int, now_ms: int) -> dict:
  ```

  and remove the `source_limit` override. Dispatch should call:

  ```python
  data = _run_token_image_mirror_worker_once(
      settings,
      limit=args.limit,
      now_ms=_now_ms(),
  )
  ```

- [ ] **Step 3: Add explicit maintenance command for existing stuck profile rows**

  Add parser:

  ```python
  repair_token_profile_images = ops_subcommands.add_parser(
      "repair-token-profile-images",
      help="enqueue current profile targets so token image source admission can repair stuck icons",
  )
  repair_token_profile_images.add_argument("--limit", type=int, default=500)
  ```

  Add command behavior in `ops.py`: it must not download images and must not call external profile providers. It should open a repository session, select current `token_profile_current` targets where `quality_flags_json` contains `logo_mirror_pending` or `source_not_admitted`, enqueue those targets into `token_profile_current_dirty_targets` with reason `token_profile_image_repair`, then run `TokenProfileCurrentWorker` once.

  Use this helper:

  ```python
  def _run_token_profile_image_repair_once(settings: object, *, limit: int, now_ms: int) -> dict:
      telemetry = TelemetryRegistry()
      db = None
      worker = None
      try:
          db = DBPoolBundle.create(settings, telemetry=telemetry)
          with db.worker_session("token_profile_image_repair") as repos, repos.transaction():
              targets = repos.conn.execute(
                  """
                  SELECT target_type, target_id, updated_at_ms AS source_watermark_ms
                  FROM token_profile_current
                  WHERE status = 'ready'
                    AND (
                      quality_flags_json ? 'logo_mirror_pending'
                      OR quality_flags_json ? 'source_not_admitted'
                    )
                  ORDER BY updated_at_ms DESC, target_type ASC, target_id ASC
                  LIMIT %s
                  """,
                  (max(1, int(limit)),),
              ).fetchall()
              enqueue_result = repos.token_profile_current_dirty_targets.enqueue_targets(
                  [
                      {
                          "target_type": str(row["target_type"]),
                          "target_id": str(row["target_id"]),
                          "source_watermark_ms": int(row["source_watermark_ms"] or now_ms),
                          "priority": 25,
                      }
                      for row in targets
                  ],
                  reason="token_profile_image_repair",
                  now_ms=now_ms,
                  commit=False,
              )
          worker = TokenProfileCurrentWorker(
              name="token_profile_current",
              settings=_worker_settings_with_overrides(settings.workers.token_profile_current, batch_size=limit),
              db=db,
              telemetry=telemetry,
          )
          worker_result = asyncio.run(worker.run_once(now_ms=now_ms))
          return {
              "selected_targets": len(targets),
              "profile_targets_enqueued": int(enqueue_result.get("targets") or 0),
              "profile_rebuild": dict(worker_result.notes.get("result") or {}),
          }
      finally:
          if worker is not None:
              asyncio.run(worker.aclose())
          if db is not None:
              _close_db_bundle(db)
  ```

  This command is a bounded ops maintenance path. It delegates runtime admission to `TokenProfileCurrentWorker`; it does not write `token_image_source_dirty_targets` directly.

- [ ] **Step 4: Test CLI hard cut and repair path**

  Add/modify tests in `tests/integration/test_cli.py`:

  ```python
  def test_cli_ops_mirror_token_images_has_no_source_limit_option():
      parser = build_parser()
      with pytest.raises(SystemExit):
          parser.parse_args(["ops", "mirror-token-images", "--source-limit", "9"])
  ```

  Add a monkeypatched repair test that asserts:

  - DB session name is `token_profile_image_repair`;
  - `token_profile_current_dirty_targets.enqueue_targets` receives ready pending-logo targets;
  - `TokenProfileCurrentWorker` runs after enqueue;
  - no asset provider bundle is constructed.

- [ ] **Step 5: Regenerate CLI help**

  ```bash
  uv run parallax --help > /tmp/parallax-help.txt
  uv run parallax ops --help > /tmp/parallax-ops-help.txt
  ```

  Run the project generator and confirm the output:

  ```bash
  make docs-cli-help
  rg -n "repair-token-profile-images|source-limit" docs/generated/cli-help.md
  ```

  Expected: `repair-token-profile-images` appears and `source-limit` has no matches.

- [ ] **Step 6: Run Task 4 tests**

  ```bash
  uv run pytest tests/integration/test_cli.py -q
  ```

  Expected: all CLI integration tests pass.

## Task 5: Worker Manifest, Docs, and Architecture Contracts

**Files:**

- Modify: `src/parallax/app/runtime/worker_manifest.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/WORKERS.md`
- Modify: `docs/CONTRACTS.md`
- Modify: `src/parallax/domains/asset_market/ARCHITECTURE.md`
- Modify: `tests/architecture/test_worker_runtime_contracts.py`

- [ ] **Step 1: Fix manifest writer ownership**

  In `src/parallax/app/runtime/worker_manifest.py`:

  - Remove `token_image_source_dirty_targets` from `asset_profile_refresh.writes_control_plane`.
  - Add `token_image_source_dirty_targets` to `token_profile_current.writes_control_plane`.
  - Add idempotency evidence for image admission:

  ```python
  idempotency_evidence=(
      "token_profile_current target primary key",
      "token image source dirty target source_url_hash/target key",
      "dirty target payload hash",
  ),
  dirty_target_tables=("token_profile_current_dirty_targets",),
  ```

  `token_image_source_dirty_targets` is a `writes_control_plane` admission output
  from `token_profile_current`, not a dirty target table consumed/claimed by that
  worker.

- [ ] **Step 2: Update worker runtime contract tests**

  In `tests/architecture/test_worker_runtime_contracts.py`, assert:

  ```python
  assert "token_image_source_dirty_targets" not in manifest_by_name["asset_profile_refresh"].writes_control_plane
  assert "token_image_source_dirty_targets" in manifest_by_name["token_profile_current"].writes_control_plane
  ```

  Keep `token_image_mirror` as the only worker writing `token_image_assets`.

- [ ] **Step 3: Update architecture docs**

  In `docs/ARCHITECTURE.md`, replace the asset profile lane with:

  ```text
  resolved/current profile target
    -> token_profile_current_dirty_targets
    -> TokenProfileCurrentWorker
    -> exact persisted profile/evidence sources
    -> token_image_source_dirty_targets for usable logo candidates
    -> TokenImageMirrorWorker
    -> token_image_assets + cache/token-images
    -> token_profile_current.logo_url = /api/token-images/{image_id}
    -> TokenProfileReadModel
    -> /api/token-radar + /api/search/inspect + CLI asset-flow + frontend
  ```

  State that `asset_profile_refresh` writes `asset_profiles` and profile-current dirty targets only; it does not own image admission.

- [ ] **Step 4: Update `docs/WORKERS.md` worker inventory**

  Change rows:

  - `asset_profile_refresh` writes: `asset_profiles`, refresh target state, `token_profile_current_dirty_targets` when source facts change.
  - `token_profile_current` reads: profile dirty targets, exact profile/evidence sources, full `token_image_assets` states, existing image dirty targets.
  - `token_profile_current` writes: `token_profile_current`, `token_image_source_dirty_targets`.
  - `token_image_mirror` reads: due `token_image_source_dirty_targets` only; it does not scan source tables.

- [ ] **Step 5: Update contracts**

  In `docs/CONTRACTS.md`, add:

  ```text
  `profile.identity.logo_url` is either `NULL` or a same-origin `/api/token-images/{image_id}` path. `logo_mirror_pending` means an image dirty target is already pending or in flight. `logo_mirror_unsupported` is terminal. `logo_mirror_failed` means the current mirrored asset is in error/backoff and may be retried; clients must still render no provider URL.
  ```

- [ ] **Step 6: Run docs/architecture checks**

  ```bash
  uv run pytest \
    tests/architecture/test_worker_runtime_contracts.py \
    tests/architecture/test_runtime_worker_constraint_hard_cut.py \
    tests/unit/test_postgres_schema.py \
    -q
  ```

  Expected: all pass.

## Task 6: End-to-End Verification and Live Repair

**Files:**

- Create: `docs/superpowers/plans/active/2026-05-31-token-profile-image-mirror-root-fix-verification-cn.md`

- [ ] **Step 1: Run full backend checks in worktree**

  ```bash
  make check-all
  ```

  Expected: exits 0. Paste full output into the verification artefact.

- [ ] **Step 2: Confirm no provider URL fallback remains**

  ```bash
  rg -n "external-res|tokenLogoUrl|logo_url.*https?://|/api/token-image\\?url|source-limit" \
    src/parallax/app/surfaces/api \
    src/parallax/domains/asset_market \
    src/parallax/domains/token_intel \
    web/src \
    tests
  ```

  Expected: matches are source ingestion/provenance, tests for rejection, or docs only. No public read path or frontend renderer uses provider image URLs as fallback.

- [ ] **Step 3: Verify real runtime config before live repair**

  ```bash
  uv run parallax config
  ```

  Expected: `config_path=/Users/qinghuan/.parallax/config.yaml` and `workers_config_path=/Users/qinghuan/.parallax/workers.yaml`.

- [ ] **Step 4: Record live before counts**

  ```bash
  uv run parallax ops worker-status
  uv run parallax asset-flow --window 1h --scope all --limit 20
  ```

  Expected before repair: `token_image_source_dirty_targets` may be 0 and rows may still show missing `profile.identity.logo_url`.

- [ ] **Step 5: Enqueue stuck profile rows and run admission**

  ```bash
  uv run parallax ops repair-token-profile-images --limit 500
  ```

  Expected JSON shape:

  ```json
  {
    "selected_targets": 1,
    "profile_targets_enqueued": 1,
    "profile_rebuild": {
      "image_candidates": 1,
      "image_sources_admitted": 1
    }
  }
  ```

  Counts can be higher in live data; the required property is `image_sources_admitted > 0` when stuck candidates exist.

- [ ] **Step 6: Mirror admitted sources**

  ```bash
  uv run parallax ops mirror-token-images --limit 200
  ```

  Expected: `claimed > 0` and at least one of `mirrored`, `unsupported`, or `error` is non-zero. `reason` must not be `no_due_token_image_source_targets` immediately after Step 5 admitted sources.

- [ ] **Step 7: Rebuild profiles after mirror completion**

  ```bash
  uv run parallax ops rebuild-token-profiles --limit 500
  uv run parallax asset-flow --window 1h --scope all --limit 20
  ```

  Expected: targets with successfully mirrored images return `profile.identity.logo_url` as `/api/token-images/{image_id}`. Rows whose sources are unsupported or failed show no public provider URL and have non-pending quality flags.

- [ ] **Step 8: Write verification artefact**

  Create `docs/superpowers/plans/active/2026-05-31-token-profile-image-mirror-root-fix-verification-cn.md` with:

  - full `make check-all` output;
  - targeted pytest command outputs;
  - live command JSON summaries with secret-free paths only;
  - coverage statement;
  - skipped tests;
  - E2E golden path result;
  - remaining risks.

## PR Breakdown

1. **PR 1 — lifecycle state APIs:** repository lookup APIs, removal of unused asset due claiming, tests.
2. **PR 2 — source admission service:** candidate extraction, admission state machine, unit tests.
3. **PR 3 — profile-current runtime wiring:** projection hard-cut, worker admission, worker tests.
4. **PR 4 — ops/docs/contracts:** CLI hard cut, maintenance repair command, manifest/docs/generated help, architecture tests.

Each PR is independently reviewable, but PR 3 is the first one that fixes live icon admission. PR 4 is required before declaring the root fix complete because it removes stale ownership and compatibility surfaces.

## Rollout Order

1. Deploy code with repository APIs, admission service, worker wiring, CLI cleanup, and docs.
2. Confirm workers are enabled in `/Users/qinghuan/.parallax/workers.yaml` via `uv run parallax config` and `uv run parallax ops worker-status`.
3. Run `uv run parallax ops repair-token-profile-images --limit 500`.
4. Run `uv run parallax ops mirror-token-images --limit 200`.
5. Run `uv run parallax ops rebuild-token-profiles --limit 500`.
6. Verify `/api/token-radar` or `uv run parallax asset-flow --window 1h --scope all --limit 20` shows same-origin icon URLs for mirrored rows and no provider URLs.

## Rollback

- Code rollback is safe before live repair because new admission only writes existing dirty-target rows.
- After live repair, rollback leaves `token_image_source_dirty_targets` and `token_image_assets` rows behind. Older code should ignore the dirty rows, but mirrored ready assets are valid facts and do not need deletion.
- If repair accidentally enqueues too much work, disable `token_image_mirror` in `~/.parallax/workers.yaml` and drain/delete only `token_image_source_dirty_targets` rows with `dirty_reason='token_profile_current_source_admission'` after taking a DB backup.
- Do not delete `token_image_assets` ready rows during rollback unless a specific bad provider source was admitted; ready rows are content-addressed public cache facts.

## Acceptance Test Mapping

- AC1: `uv run pytest tests/unit/test_token_image_source_admission.py::test_admit_token_image_sources_enqueues_missing_sources_and_preserves_backoff -q`
- AC2: `uv run pytest tests/unit/test_token_profile_current_projection.py::test_project_token_profile_current_prefers_gmgn_openapi_ready_profile -q`
- AC3: `uv run pytest tests/unit/test_token_profile_current_projection.py::test_project_token_profile_current_marks_unsupported_logo_without_pending -q`
- AC4: `uv run pytest tests/unit/test_token_profile_current_projection.py::test_project_token_profile_current_marks_source_without_logo_when_no_provider_logo_candidates -q`
- AC5: `uv run pytest tests/unit/test_token_image_mirror_worker.py -q`
- AC6: live sequence `repair-token-profile-images`, `mirror-token-images`, `rebuild-token-profiles`, `asset-flow`.
- AC7: `rg -n "/api/token-image\\?url|logo_url.*https?://" web/src src/parallax/app/surfaces/api src/parallax/domains/token_intel`
- AC8: `uv run parallax ops repair-token-profile-images --limit 500`
- AC9: `uv run pytest tests/unit/test_token_profile_current_projection.py tests/unit/test_token_image_source_admission.py -q`

## Verification Gate

The implementation is not complete until `make check-all` exits 0 in the worktree and the verification artefact records full output plus live repair evidence. Do not move this plan or the owning spec to `completed/` until the verification artefact exists.
