from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace

from parallax.domains.asset_market.services.token_image_source_admission import (
    TokenImageSourceCandidate,
    admit_token_image_sources,
    image_source_candidates_for_target,
)

NOW_MS = 1_779_000_000_000


def test_image_source_candidates_cover_all_exact_profile_source_families() -> None:
    candidates = image_source_candidates_for_target(
        target={"target_type": "Asset", "target_id": "asset:sol:bonk"},
        gmgn_openapi={
            "logo_url": "https://gmgn.ai/external-res/bonk.png",
            "observed_at_ms": 101,
        },
        binance_web3={
            "logo_url": "https://bin.bnbstatic.com/static/images/bonk.png",
            "updated_at_ms": 202,
        },
        gmgn_stream={
            "raw_payload_json": {"i": "https://gmgn.ai/external-res/stream-bonk.png"},
            "observed_at_ms": 303,
        },
        okx_dex={
            "raw_payload_json": {
                "tokenLogoUrl": (
                    "https://static.oklink.com/cdn/web3/currency/token/large/56-0xbonk-107/type=default_90_0?v=177"
                )
            },
            "observed_at_ms": 404,
        },
        cex_profile=None,
    )

    assert [(candidate.source_provider, candidate.source_kind) for candidate in candidates] == [
        ("gmgn_dex_profile", "asset_profiles.logo_url"),
        ("binance_web3_profile", "asset_profiles.logo_url"),
        ("gmgn_stream_snapshot", "asset_identity_evidence.raw_payload_json.i"),
        ("okx_dex_evidence", "asset_identity_evidence.raw_payload_json.tokenLogoUrl"),
    ]
    assert [candidate.source_watermark_ms for candidate in candidates] == [101, 202, 303, 404]


def test_image_source_candidates_skip_invalid_and_placeholder_urls() -> None:
    candidates = image_source_candidates_for_target(
        target={"target_type": "Asset", "target_id": "asset:sol:bad"},
        gmgn_openapi={"logo_url": "http://gmgn.ai/external-res/bad.png"},
        binance_web3={"logo_url": ""},
        gmgn_stream={"raw_payload_json": {"i": "https://example.com/not-allowlisted.png"}},
        okx_dex={"raw_payload_json": {"tokenLogoUrl": "https://static.okx.com/default-logo/bad.png"}},
        cex_profile=None,
    )

    assert candidates == []

    malformed_candidates = image_source_candidates_for_target(
        target={"target_type": "Asset", "target_id": "asset:sol:malformed"},
        gmgn_openapi={"logo_url": "https://["},
        binance_web3=None,
        gmgn_stream=None,
        okx_dex=None,
        cex_profile=None,
    )

    assert malformed_candidates == []


def test_cex_image_source_candidate_uses_cex_profile_only() -> None:
    candidates = image_source_candidates_for_target(
        target={"target_type": "CexToken", "target_id": "cex_token:BTC"},
        gmgn_openapi={"logo_url": "https://gmgn.ai/external-res/btc.png"},
        binance_web3={"logo_url": "https://bin.bnbstatic.com/static/images/btc-web3.png"},
        gmgn_stream={"raw_payload_json": {"i": "https://gmgn.ai/external-res/btc-stream.png"}},
        okx_dex={"raw_payload_json": {"tokenLogoUrl": "https://static.okx.com/cdn/assets/btc.png"}},
        cex_profile={
            "cex_token_id": "cex_token:BTC",
            "logo_url": "https://bin.bnbstatic.com/static/images/btc.png",
            "source_ref": "binance_marketing_symbol_list:BTC",
            "observed_at_ms": 909,
        },
    )

    assert len(candidates) == 1
    assert candidates[0].target_type == "CexToken"
    assert candidates[0].target_id == "cex_token:BTC"
    assert candidates[0].source_url == "https://bin.bnbstatic.com/static/images/btc.png"
    assert candidates[0].source_provider == "binance_cex_profile"
    assert candidates[0].source_kind == "cex_token_profiles.logo_url"
    assert candidates[0].priority == 20
    assert candidates[0].raw_ref_json == {
        "cex_token_id": "cex_token:BTC",
        "source_ref": "binance_marketing_symbol_list:BTC",
        "provider": "binance_cex_profile",
    }


def test_admit_token_image_sources_enqueues_missing_sources_and_preserves_backoff() -> None:
    missing = _candidate("https://gmgn.ai/external-res/missing.png", priority=20)
    ready = _candidate("https://gmgn.ai/external-res/ready.png", priority=30)
    error = _candidate("https://gmgn.ai/external-res/error.png", priority=40)
    unsupported = _candidate("https://gmgn.ai/external-res/unsupported.png", priority=50)
    repos = _FakeRepos(
        image_assets={
            ready.source_url: _asset_row(ready, status="ready"),
            error.source_url: _asset_row(error, status="error", next_refresh_at_ms=NOW_MS + 60_000),
            unsupported.source_url: _asset_row(unsupported, status="unsupported"),
        },
        dirty_existing={},
        enqueue_result_targets=22,
    )

    result = admit_token_image_sources(
        repos=repos,
        candidates=[missing, ready, error, unsupported],
        now_ms=NOW_MS,
    )

    assert [row["source_url"] for row in repos.dirty_targets.enqueued] == [
        missing.source_url,
        error.source_url,
    ]
    assert [row["due_at_ms"] for row in repos.dirty_targets.enqueued] == [NOW_MS, NOW_MS + 60_000]
    assert repos.dirty_targets.enqueue_calls == [
        {
            "reason": "token_profile_current_source_admission",
            "now_ms": NOW_MS,
            "commit": False,
        }
    ]
    assert result.counts == {
        "candidates": 4,
        "admitted": 22,
        "ready_existing": 1,
        "pending_existing": 0,
        "error_existing": 1,
        "unsupported_existing": 1,
        "dirty_existing": 0,
        "terminal_existing": 0,
    }
    assert result.image_states_by_source_key[_dirty_key(missing)]["status"] == "mirror_pending"
    assert result.image_states_by_source_key[_dirty_key(missing)]["source_url_hash"] == missing.source_url_hash
    assert result.image_states_by_source_key[_dirty_key(error)]["status"] == "error"
    assert result.image_states_by_source_key[_dirty_key(ready)]["status"] == "ready"
    assert result.image_states_by_source_key[_dirty_key(unsupported)]["status"] == "unsupported"


def test_admit_token_image_sources_skips_existing_dirty_targets() -> None:
    candidate = _candidate("https://gmgn.ai/external-res/pending.png")
    dirty_row = {
        "source_url_hash": candidate.source_url_hash,
        "target_type": candidate.target_type,
        "target_id": candidate.target_id,
        "source_url": candidate.source_url,
        "attempt_count": 0,
        "due_at_ms": NOW_MS + 30_000,
    }
    repos = _FakeRepos(image_assets={}, dirty_existing={_dirty_key(candidate): dirty_row})

    result = admit_token_image_sources(repos=repos, candidates=[candidate], now_ms=NOW_MS)

    assert repos.dirty_targets.enqueued == []
    assert result.counts["dirty_existing"] == 1
    assert result.counts["admitted"] == 0
    assert result.image_states_by_source_key[_dirty_key(candidate)] == {
        "status": "mirror_pending",
        **dirty_row,
    }


def test_admit_token_image_sources_reenqueues_pending_asset_without_dirty_target() -> None:
    candidate = _candidate("https://gmgn.ai/external-res/pending-asset.png")
    repos = _FakeRepos(
        image_assets={candidate.source_url: _asset_row(candidate, status="pending")},
        dirty_existing={},
    )

    result = admit_token_image_sources(repos=repos, candidates=[candidate], now_ms=NOW_MS)

    assert [row["source_url"] for row in repos.dirty_targets.enqueued] == [candidate.source_url]
    assert repos.dirty_targets.enqueued[0]["due_at_ms"] == NOW_MS
    assert result.counts["pending_existing"] == 1
    assert result.counts["dirty_existing"] == 0
    assert result.counts["admitted"] == 1
    assert result.image_states_by_source_key[_dirty_key(candidate)] == {
        "status": "mirror_pending",
        "asset_status": "pending",
        "source_url": candidate.source_url,
        "source_provider": candidate.source_provider,
        "source_url_hash": candidate.source_url_hash,
        "target_type": candidate.target_type,
        "target_id": candidate.target_id,
    }


def test_admit_token_image_sources_keeps_pending_asset_with_existing_dirty_target() -> None:
    candidate = _candidate("https://gmgn.ai/external-res/pending-dirty.png")
    dirty_row = {
        "source_url_hash": candidate.source_url_hash,
        "target_type": candidate.target_type,
        "target_id": candidate.target_id,
        "source_url": candidate.source_url,
        "source_provider": candidate.source_provider,
        "attempt_count": 0,
        "due_at_ms": NOW_MS + 30_000,
    }
    repos = _FakeRepos(
        image_assets={candidate.source_url: _asset_row(candidate, status="pending")},
        dirty_existing={_dirty_key(candidate): dirty_row},
    )

    result = admit_token_image_sources(repos=repos, candidates=[candidate], now_ms=NOW_MS)

    assert repos.dirty_targets.enqueued == []
    assert result.counts["pending_existing"] == 1
    assert result.counts["dirty_existing"] == 1
    assert result.counts["admitted"] == 0
    assert result.image_states_by_source_key[_dirty_key(candidate)] == {
        "status": "mirror_pending",
        **dirty_row,
        "asset_status": "pending",
        "source_provider": candidate.source_provider,
        "source_url": candidate.source_url,
        "source_url_hash": candidate.source_url_hash,
    }


def test_admit_token_image_sources_keeps_same_source_url_states_target_specific() -> None:
    source_url = "https://gmgn.ai/external-res/shared.png"
    dirty_candidate = _candidate(source_url, target_id="asset:sol:dirty")
    new_candidate = _candidate(source_url, target_id="asset:sol:new")
    dirty_row = {
        "source_url_hash": dirty_candidate.source_url_hash,
        "target_type": dirty_candidate.target_type,
        "target_id": dirty_candidate.target_id,
        "source_url": dirty_candidate.source_url,
        "attempt_count": 1,
        "due_at_ms": NOW_MS + 30_000,
    }
    repos = _FakeRepos(image_assets={}, dirty_existing={_dirty_key(dirty_candidate): dirty_row})

    result = admit_token_image_sources(
        repos=repos,
        candidates=[dirty_candidate, new_candidate],
        now_ms=NOW_MS,
    )

    assert [row["target_id"] for row in repos.dirty_targets.enqueued] == ["asset:sol:new"]
    assert result.counts["dirty_existing"] == 1
    assert result.counts["admitted"] == 1
    assert set(result.image_states_by_source_key) == {
        _dirty_key(dirty_candidate),
        _dirty_key(new_candidate),
    }
    assert result.image_states_by_source_key[_dirty_key(dirty_candidate)]["status"] == "mirror_pending"
    assert result.image_states_by_source_key[_dirty_key(dirty_candidate)]["attempt_count"] == 1
    assert result.image_states_by_source_key[_dirty_key(new_candidate)]["status"] == "mirror_pending"
    assert result.image_states_by_source_key[_dirty_key(new_candidate)]["target_id"] == "asset:sol:new"


def test_admit_token_image_sources_error_asset_with_existing_dirty_target_reports_pending_state() -> None:
    candidate = _candidate("https://gmgn.ai/external-res/error-pending.png")
    dirty_row = {
        "source_url_hash": candidate.source_url_hash,
        "target_type": candidate.target_type,
        "target_id": candidate.target_id,
        "source_url": candidate.source_url,
        "source_provider": candidate.source_provider,
        "attempt_count": 2,
        "due_at_ms": NOW_MS + 30_000,
    }
    repos = _FakeRepos(
        image_assets={
            candidate.source_url: {
                **_asset_row(candidate, status="error", next_refresh_at_ms=NOW_MS + 60_000),
                "last_error": "image_fetch_failed: timeout",
            }
        },
        dirty_existing={_dirty_key(candidate): dirty_row},
    )

    result = admit_token_image_sources(repos=repos, candidates=[candidate], now_ms=NOW_MS)

    assert repos.dirty_targets.enqueued == []
    assert result.counts["error_existing"] == 1
    assert result.counts["dirty_existing"] == 1
    assert result.counts["admitted"] == 0
    assert result.image_states_by_source_key[_dirty_key(candidate)] == {
        "status": "mirror_pending",
        **dirty_row,
        "asset_status": "error",
        "last_error": "image_fetch_failed: timeout",
        "next_refresh_at_ms": NOW_MS + 60_000,
        "source_provider": candidate.source_provider,
        "source_url": candidate.source_url,
        "source_url_hash": candidate.source_url_hash,
    }


def test_admit_token_image_sources_does_not_reenqueue_unresolved_terminal_error() -> None:
    candidate = _candidate("https://gmgn.ai/external-res/exhausted.png")
    terminal_row = {
        "terminal_id": "terminal-image-exhausted",
        "target_key": f"{candidate.source_url_hash}:{candidate.target_type}:{candidate.target_id}",
        "final_status": "terminal",
        "final_reason": "image_mirror_retry_budget_exhausted: image_fetch_failed",
        "terminalized_at_ms": NOW_MS - 10,
    }
    repos = _FakeRepos(
        image_assets={
            candidate.source_url: {
                **_asset_row(candidate, status="error", next_refresh_at_ms=NOW_MS),
                "last_error": "image_fetch_failed",
            }
        },
        dirty_existing={},
        terminal_existing={_dirty_key(candidate): terminal_row},
    )

    result = admit_token_image_sources(repos=repos, candidates=[candidate], now_ms=NOW_MS)

    assert repos.dirty_targets.enqueued == []
    assert result.counts["admitted"] == 0
    assert result.counts["error_existing"] == 1
    assert result.counts["terminal_existing"] == 1
    assert result.image_states_by_source_key[_dirty_key(candidate)] == {
        "status": "error",
        "source_url": candidate.source_url,
        "source_provider": candidate.source_provider,
        "source_url_hash": candidate.source_url_hash,
        "target_type": candidate.target_type,
        "target_id": candidate.target_id,
        "asset_status": "error",
        "last_error": "image_fetch_failed",
        "next_refresh_at_ms": NOW_MS,
        "terminal_id": "terminal-image-exhausted",
        "terminal_final_reason": "image_mirror_retry_budget_exhausted: image_fetch_failed",
        "terminalized_at_ms": NOW_MS - 10,
    }


def test_admit_token_image_sources_dedupes_candidates_by_exact_target_source_key() -> None:
    high_priority = _candidate("https://gmgn.ai/external-res/dupe.png", priority=50)
    low_priority = _candidate("https://gmgn.ai/external-res/dupe.png", priority=20)
    repos = _FakeRepos(image_assets={}, dirty_existing={})

    result = admit_token_image_sources(
        repos=repos,
        candidates=[high_priority, low_priority],
        now_ms=NOW_MS,
    )

    assert result.counts["candidates"] == 1
    assert result.counts["admitted"] == 1
    assert len(repos.dirty_targets.enqueued) == 1
    assert repos.dirty_targets.enqueued[0]["priority"] == 20


def _candidate(
    source_url: str,
    *,
    priority: int = 20,
    target_id: str = "asset:sol:bonk",
) -> TokenImageSourceCandidate:
    return TokenImageSourceCandidate(
        target_type="Asset",
        target_id=target_id,
        source_url=source_url,
        source_provider="gmgn_dex_profile",
        source_kind="asset_profiles.logo_url",
        source_watermark_ms=NOW_MS - 1_000,
        priority=priority,
        raw_ref_json={"asset_id": target_id},
    )


def _asset_row(
    candidate: TokenImageSourceCandidate,
    *,
    status: str,
    next_refresh_at_ms: int | None = None,
) -> dict[str, object]:
    return {
        "image_id": candidate.source_url_hash,
        "source_url": candidate.source_url,
        "source_url_hash": candidate.source_url_hash,
        "source_provider": candidate.source_provider,
        "source_kind": candidate.source_kind,
        "status": status,
        "next_refresh_at_ms": next_refresh_at_ms if next_refresh_at_ms is not None else NOW_MS,
    }


def _dirty_key(candidate: TokenImageSourceCandidate) -> tuple[str, str, str]:
    return (candidate.source_url_hash, candidate.target_type, candidate.target_id)


class _FakeRepos:
    def __init__(
        self,
        *,
        image_assets: dict[str, dict[str, object]],
        dirty_existing: dict[tuple[str, str, str], dict[str, object]],
        terminal_existing: dict[tuple[str, str, str], dict[str, object]] | None = None,
        enqueue_result_targets: int | None = None,
    ) -> None:
        self.token_image_assets = _FakeImageAssets(image_assets)
        self.dirty_targets = _FakeDirtyTargets(
            dirty_existing,
            terminal_existing=terminal_existing or {},
            enqueue_result_targets=enqueue_result_targets,
        )
        self.token_image_source_dirty_targets = self.dirty_targets


class _FakeImageAssets:
    def __init__(self, rows: dict[str, dict[str, object]]) -> None:
        self.rows = rows
        self.source_url_calls: list[list[str]] = []

    def by_source_urls(self, source_urls: list[str]) -> dict[str, dict[str, object]]:
        self.source_url_calls.append(list(source_urls))
        return {source_url: self.rows[source_url] for source_url in source_urls if source_url in self.rows}


class _FakeDirtyTargets:
    def __init__(
        self,
        rows: dict[tuple[str, str, str], dict[str, object]],
        *,
        terminal_existing: dict[tuple[str, str, str], dict[str, object]],
        enqueue_result_targets: int | None,
    ) -> None:
        self.rows = rows
        self.terminal_rows = terminal_existing
        self.enqueue_result_targets = enqueue_result_targets
        self.identity_calls: list[list[dict[str, object]]] = []
        self.terminal_identity_calls: list[list[dict[str, object]]] = []
        self.enqueue_calls: list[dict[str, object]] = []
        self.enqueued: list[dict[str, object]] = []

    def existing_by_source_targets(
        self,
        targets: list[dict[str, object]],
    ) -> dict[tuple[str, str, str], dict[str, object]]:
        self.identity_calls.append(list(targets))
        return {
            (
                str(target["source_url_hash"]),
                str(target["target_type"]),
                str(target["target_id"]),
            ): self.rows[
                (
                    str(target["source_url_hash"]),
                    str(target["target_type"]),
                    str(target["target_id"]),
                )
            ]
            for target in targets
            if (
                str(target["source_url_hash"]),
                str(target["target_type"]),
                str(target["target_id"]),
            )
            in self.rows
        }

    def unresolved_terminal_by_source_targets(
        self,
        targets: list[dict[str, object]],
        *,
        worker_name: str,
    ) -> dict[tuple[str, str, str], dict[str, object]]:
        assert worker_name == "token_image_mirror"
        self.terminal_identity_calls.append(list(targets))
        return {
            (
                str(target["source_url_hash"]),
                str(target["target_type"]),
                str(target["target_id"]),
            ): self.terminal_rows[
                (
                    str(target["source_url_hash"]),
                    str(target["target_type"]),
                    str(target["target_id"]),
                )
            ]
            for target in targets
            if (
                str(target["source_url_hash"]),
                str(target["target_type"]),
                str(target["target_id"]),
            )
            in self.terminal_rows
        }

    def enqueue_targets(
        self,
        targets: list[dict[str, object]],
        *,
        reason: str,
        now_ms: int,
        commit: bool = True,
    ) -> dict[str, int]:
        self.enqueue_calls.append({"reason": reason, "now_ms": now_ms, "commit": commit})
        self.enqueued.extend(dict(target) for target in targets)
        return {"targets": self.enqueue_result_targets if self.enqueue_result_targets is not None else len(targets)}


def test_source_url_hash_matches_repository_identity() -> None:
    candidate = _candidate("https://gmgn.ai/external-res/hash.png")

    assert candidate.source_url_hash == sha256(candidate.source_url.encode("utf-8")).hexdigest()
    assert SimpleNamespace(**candidate.as_dirty_target(due_at_ms=NOW_MS)).source_url_hash == candidate.source_url_hash
