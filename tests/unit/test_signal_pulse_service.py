from __future__ import annotations

from typing import Any

import pytest

from gmgn_twitter_intel.domains.pulse_lab.read_models.signal_pulse_service import SignalPulseService


class FakePulseRepository:
    def __init__(
        self,
        *,
        pages: dict[str | None, dict[str, Any]] | None = None,
        health: dict[str, Any] | None = None,
    ):
        self.pages = pages or {}
        self.health = health or {
            "candidate_count": 0,
            "blocked_low_information_count": 0,
            "dead_job_count": 0,
            "market_ready_rate": 0.0,
            "summary": {
                "trade_candidate": 0,
                "token_watch": 0,
                "theme_watch": 0,
                "risk_rejected_high_info": 0,
                "blocked_low_information": 0,
            },
        }
        self.calls: list[dict[str, Any]] = []
        self.summary_calls: list[dict[str, Any]] = []
        self.candidate_rows: dict[str, dict[str, Any]] = {}

    def list_candidates(
        self,
        window: str,
        scope: str,
        status: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        q: str | None = None,
        handle: str | None = None,
        displayable_only: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "window": window,
                "scope": scope,
                "status": status,
                "limit": limit,
                "cursor": cursor,
                "q": q,
                "handle": handle,
                "displayable_only": displayable_only,
            }
        )
        return self.pages.get(status, {"items": [], "next_cursor": None})

    def pulse_summary(self, window: str, scope: str, q: str | None = None, handle: str | None = None) -> dict[str, Any]:
        self.summary_calls.append({"window": window, "scope": scope, "q": q, "handle": handle})
        return self.health

    def get_health(self, window: str, scope: str) -> dict[str, Any]:
        return {"window": window, "scope": scope, **self.health}

    def candidate_by_id(self, candidate_id: str) -> dict[str, Any] | None:
        return self.candidate_rows.get(candidate_id)


class FakeHarnessRepository:
    def __init__(self, coverage: float | None):
        self.coverage = coverage

    def health(self) -> dict[str, Any]:
        return {"settlement_coverage": self.coverage}


def test_signal_pulse_empty_state_uses_pulse_candidates_only() -> None:
    pulse = FakePulseRepository()

    result = SignalPulseService(pulse=pulse, harness=FakeHarnessRepository(None)).pulse(
        window="1h",
        scope="matched",
        status=None,
        handle=None,
        q=None,
        limit=20,
        cursor=None,
        agent_worker_running=False,
    )

    assert result["query"] == {
        "window": "1h",
        "scope": "matched",
        "status": None,
        "handle": None,
        "q": None,
    }
    assert result["health"] == {
        "pulse_ready": False,
        "agent_worker_running": False,
        "candidate_count": 0,
        "blocked_low_information_count": 0,
        "dead_job_count": 0,
        "market_ready_rate": 0.0,
        "settlement_coverage": None,
    }
    assert result["summary"] == {
        "trade_candidate": 0,
        "token_watch": 0,
        "theme_watch": 0,
        "risk_rejected_high_info": 0,
        "blocked_low_information": 0,
    }
    assert result["items"] == []
    assert result["returned_count"] == 0
    assert result["has_more"] is False
    assert result["next_cursor"] is None
    assert pulse.calls == [
        {
            "window": "1h",
            "scope": "matched",
            "status": None,
            "limit": 20,
            "cursor": None,
            "q": None,
            "handle": None,
            "displayable_only": True,
        }
    ]
    assert pulse.summary_calls == [{"window": "1h", "scope": "matched", "q": None, "handle": None}]


def test_signal_pulse_transforms_rows_excludes_blocked_and_preserves_cursor() -> None:
    visible = _candidate_row(
        "candidate-token",
        pulse_status="token_watch",
        verdict="token_watch",
        market_status="fresh",
    )
    blocked = _candidate_row(
        "candidate-blocked",
        pulse_status="blocked_low_information",
        verdict="blocked_low_information",
        market_status="fresh",
    )
    trade = _candidate_row(
        "candidate-trade",
        pulse_status="trade_candidate",
        verdict="trade_candidate",
        market_status="stale",
    )
    pulse = FakePulseRepository(
        pages={
            "token_watch": {"items": [visible, blocked], "next_cursor": "next-page"},
            None: {"items": [visible, blocked, trade], "next_cursor": None},
        },
        health={
            "candidate_count": 3,
            "blocked_low_information_count": 1,
            "dead_job_count": 2,
            "market_ready_rate": 0.5,
            "summary": {
                "trade_candidate": 1,
                "token_watch": 1,
                "theme_watch": 0,
                "risk_rejected_high_info": 0,
                "blocked_low_information": 1,
            },
        },
    )

    result = SignalPulseService(pulse=pulse, harness=FakeHarnessRepository(0.75)).pulse(
        window="5m",
        scope="all",
        status="token_watch",
        handle="@Toly",
        q="pepe",
        limit=50,
        cursor="cursor-1",
        agent_worker_running=True,
    )

    assert pulse.calls == [
        {
            "window": "5m",
            "scope": "all",
            "status": "token_watch",
            "limit": 50,
            "cursor": "cursor-1",
            "q": "pepe",
            "handle": "@Toly",
            "displayable_only": True,
        },
    ]
    assert pulse.summary_calls == [{"window": "5m", "scope": "all", "q": "pepe", "handle": "@Toly"}]
    assert result["summary"] == {
        "trade_candidate": 1,
        "token_watch": 1,
        "theme_watch": 0,
        "risk_rejected_high_info": 0,
        "blocked_low_information": 1,
    }
    assert result["health"] == {
        "pulse_ready": True,
        "agent_worker_running": True,
        "candidate_count": 3,
        "blocked_low_information_count": 1,
        "dead_job_count": 2,
        "market_ready_rate": 0.5,
        "settlement_coverage": 0.75,
    }
    assert result["returned_count"] == 1
    assert result["has_more"] is True
    assert result["next_cursor"] == "next-page"
    assert result["items"] == [
        {
            "candidate_id": "candidate-token",
            "candidate_type": "token_target",
            "subject_key": "toly",
            "subject": {
                "symbol": "PEPE",
                "target_type": "Asset",
                "target_id": "asset:pepe",
                "target_market_type": "dex",
            },
            "target_type": "Asset",
            "target_id": "asset:pepe",
            "symbol": "PEPE",
            "window": "5m",
            "scope": "all",
            "pulse_status": "token_watch",
            "verdict": "token_watch",
            "social_phase": "ignition",
            "narrative_type": "direct_token",
            "candidate_score": 0.82,
            "score_band": "watch",
            "gate_reasons": ["fresh_attention"],
            "risk_reasons": ["thin_liquidity"],
            "evidence_event_ids": ["event-1"],
            "source_event_ids": ["event-1"],
            "factor_snapshot": _factor_snapshot(market_status="fresh"),
            "agent_recommendation": {
                "schema_version": "pulse_recommendation_v1",
                "recommendation": "watch",
                "summary_zh": "链上质量允许继续观察。",
            },
            "gate": {
                "eligible_for_high_alert": True,
                "blocked_reasons": [],
                "risk_reasons": [],
            },
            "fact_card": {
                "rank_score": 82,
                "recommended_decision": "high_alert",
                "target_market_type": "dex",
                "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
                "alpha_family_scores": {
                    "social_heat": 80,
                    "social_propagation": 76,
                    "semantic_catalyst": 72,
                    "timing_risk": 65,
                },
                "market_status": "ready",
                "mentions_1h": 9,
                "unique_authors": 4,
                "watched_mentions": 1,
                "eligible_for_high_alert": True,
                "blocked_reasons": [],
            },
            "agent_run_id": "run-1",
            "pulse_version": "pulse-v1",
            "gate_version": "gate-v1",
            "prompt_version": "prompt-v1",
            "schema_version": "schema-v1",
            "created_at_ms": 1_000,
            "updated_at_ms": 2_000,
            "playbooks": [],
        }
    ]


def test_signal_pulse_uses_aggregate_for_summary_and_market_rate_independent_of_page() -> None:
    fresh = _candidate_row(
        "candidate-fresh",
        pulse_status="token_watch",
        verdict="token_watch",
        market_status="fresh",
    )
    missing_market = _candidate_row(
        "candidate-missing-market",
        pulse_status="trade_candidate",
        verdict="trade_candidate",
        market_status=None,
    )
    pulse = FakePulseRepository(
        pages={None: {"items": [fresh], "next_cursor": "after-first-visible"}},
        health={
            "candidate_count": 3,
            "blocked_low_information_count": 1,
            "dead_job_count": 0,
            "market_ready_rate": 0.5,
            "summary": {
                "trade_candidate": 1,
                "token_watch": 1,
                "theme_watch": 0,
                "risk_rejected_high_info": 0,
                "blocked_low_information": 1,
            },
        },
    )

    result = SignalPulseService(pulse=pulse).pulse(
        window="1h",
        scope="matched",
        status=None,
        handle="toly",
        q="PEPE",
        limit=1,
        cursor=None,
        agent_worker_running=False,
    )

    assert missing_market["factor_snapshot_json"]["data_health"]["market"] == "missing"
    assert result["summary"]["trade_candidate"] == 1
    assert result["summary"]["blocked_low_information"] == 1
    assert result["health"]["candidate_count"] == 3
    assert result["health"]["market_ready_rate"] == 0.5
    assert result["returned_count"] == 1
    assert result["has_more"] is True


def _candidate_row(
    candidate_id: str,
    *,
    pulse_status: str,
    verdict: str,
    market_status: str | None,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "candidate_type": "token_target",
        "subject_key": "toly",
        "target_type": "Asset",
        "target_id": "asset:pepe",
        "symbol": "PEPE",
        "window": "5m",
        "scope": "all",
        "pulse_status": pulse_status,
        "verdict": verdict,
        "social_phase": "ignition",
        "narrative_type": "direct_token",
        "candidate_score": 0.82,
        "score_band": "watch",
        "thesis_json": {
            "summary_zh": "PEPE 社交热度显著上升。",
            "why_now_zh": "多源讨论同步出现。",
            "bull_case_zh": ["新增独立作者扩散"],
            "bear_case_zh": ["市场确认不足"],
            "confirmation_triggers_zh": ["更多独立账号确认"],
            "invalidation_triggers_zh": ["讨论迅速降温"],
            "top_risks": ["public_stream_coverage"],
        },
        "radar_score_json": {"score": 0.82},
        "market_context_json": {"market_status": market_status} if market_status else {},
        "factor_snapshot_json": _factor_snapshot(market_status=market_status),
        "agent_recommendation_json": {
            "schema_version": "pulse_recommendation_v1",
            "recommendation": "watch",
            "summary_zh": "链上质量允许继续观察。",
        },
        "gate_json": {
            "pulse_status": pulse_status,
            "candidate_score": 82.0,
            "score_band": "watch",
            "max_recommendation": "watch" if pulse_status == "token_watch" else "trade_candidate",
            "eligible_for_high_alert": True,
            "blocked_reasons": [],
        },
        "gate_reasons_json": ["fresh_attention"],
        "risk_reasons_json": ["thin_liquidity"],
        "evidence_event_ids_json": ["event-1"],
        "source_event_ids_json": ["event-1"],
        "agent_run_id": "run-1",
        "pulse_version": "pulse-v1",
        "gate_version": "gate-v1",
        "prompt_version": "prompt-v1",
        "schema_version": "schema-v1",
        "created_at_ms": 1_000,
        "updated_at_ms": 2_000,
    }


def test_candidate_returns_full_item() -> None:
    row = _candidate_row(
        "cand-1",
        pulse_status="token_watch",
        verdict="token_watch",
        market_status="fresh",
    )
    pulse = FakePulseRepository()
    pulse.candidate_rows = {"cand-1": row}

    result = SignalPulseService(pulse=pulse, harness=FakeHarnessRepository(None)).candidate(candidate_id="cand-1")

    assert result is not None
    assert result["candidate_id"] == "cand-1"
    assert result["pulse_status"] == "token_watch"
    assert result["factor_snapshot"]["schema_version"] == "token_factor_snapshot_v3_social_attention"
    assert result["agent_recommendation"]["summary_zh"] == "链上质量允许继续观察。"
    assert result["playbooks"] == []


def test_candidate_returns_none_when_missing() -> None:
    pulse = FakePulseRepository()
    pulse.candidate_rows = {}
    result = SignalPulseService(pulse=pulse, harness=FakeHarnessRepository(None)).candidate(candidate_id="ghost")
    assert result is None


def test_candidate_returns_none_when_blocked() -> None:
    row = _candidate_row(
        "cand-blocked",
        pulse_status="blocked_low_information",
        verdict="blocked_low_information",
        market_status=None,
    )
    pulse = FakePulseRepository()
    pulse.candidate_rows = {"cand-blocked": row}
    result = SignalPulseService(pulse=pulse, harness=FakeHarnessRepository(None)).candidate(candidate_id="cand-blocked")
    assert result is None


def test_signal_pulse_missing_factor_snapshot_does_not_fallback_to_legacy_runtime_fields() -> None:
    row = _candidate_row(
        "candidate-legacy",
        pulse_status="token_watch",
        verdict="token_watch",
        market_status="fresh",
    )
    row["factor_snapshot_json"] = {}
    pulse = FakePulseRepository(
        pages={None: {"items": [row], "next_cursor": None}},
        health={"candidate_count": 1, "summary": {"token_watch": 1}},
    )

    result = SignalPulseService(pulse=pulse).pulse(
        window="1h",
        scope="all",
        status=None,
        handle=None,
        q=None,
        limit=20,
        cursor=None,
        agent_worker_running=True,
    )

    assert result["items"] == []
    assert result["returned_count"] == 0


def test_signal_pulse_item_contains_factor_snapshot_contract_without_legacy_display_fields() -> None:
    row = _candidate_row(
        "candidate-token",
        pulse_status="token_watch",
        verdict="token_watch",
        market_status="fresh",
    )
    row["radar_score_json"] = {"score": 999, "old": "must_not_render"}
    row["thesis_json"] = {
        "summary_zh": "旧 thesis 不应展示",
        "confirmation_triggers_zh": ["旧确认"],
        "top_risks": ["旧风险"],
    }

    pulse = FakePulseRepository(pages={None: {"items": [row], "next_cursor": None}})
    item = SignalPulseService(pulse=pulse).pulse(
        window="1h",
        scope="all",
        status=None,
        handle=None,
        q=None,
        limit=20,
        cursor=None,
        agent_worker_running=True,
    )["items"][0]

    assert "radar_score_json" not in item
    assert "market_context_json" not in item
    assert "thesis_json" not in item
    assert "confirmation_triggers_zh" not in item
    assert "top_risks" not in item
    assert item["factor_snapshot"]["schema_version"] == "token_factor_snapshot_v3_social_attention"
    assert item["fact_card"]["market_status"] == "ready"


def test_signal_pulse_fact_card_does_not_fallback_to_legacy_market_context() -> None:
    row = _candidate_row(
        "candidate-legacy-market-context",
        pulse_status="token_watch",
        verdict="token_watch",
        market_status="fresh",
    )
    row["factor_snapshot_json"]["data_health"].pop("market")
    row["market_context_json"] = {"market_status": "fresh"}

    pulse = FakePulseRepository(pages={None: {"items": [row], "next_cursor": None}})
    item = SignalPulseService(pulse=pulse).pulse(
        window="1h",
        scope="all",
        status=None,
        handle=None,
        q=None,
        limit=20,
        cursor=None,
        agent_worker_running=True,
    )["items"][0]

    assert item["fact_card"]["market_status"] is None
    assert "market_context_json" not in item


def test_signal_pulse_fact_card_reads_market_facts_from_anchor_row_only() -> None:
    row = _candidate_row(
        "candidate-anchor-market",
        pulse_status="token_watch",
        verdict="token_watch",
        market_status="fresh",
    )
    row["anchor_price"] = {
        "market_cap_usd": 12_500_000,
        "liquidity_usd": 820_000,
        "holders": 14_200,
        "volume_24h_usd": 2_300_000,
    }
    row["market_context_json"] = {
        "market_cap_usd": 999_000_000,
        "liquidity_usd": 999_000_000,
        "holders": 999_000_000,
        "volume_24h_usd": 999_000_000,
    }
    row["factor_snapshot_json"]["families"]["timing_risk"]["facts"] = {
        "market_cap_usd": 888_000_000,
        "liquidity_usd": 888_000_000,
        "holders": 888_000_000,
        "volume_24h_usd": 888_000_000,
    }

    pulse = FakePulseRepository(pages={None: {"items": [row], "next_cursor": None}})
    item = SignalPulseService(pulse=pulse).pulse(
        window="1h",
        scope="all",
        status=None,
        handle=None,
        q=None,
        limit=20,
        cursor=None,
        agent_worker_running=True,
    )["items"][0]

    assert item["fact_card"]["market_cap_usd"] == 12_500_000
    assert item["fact_card"]["liquidity_usd"] == 820_000
    assert item["fact_card"]["holders"] == 14_200
    assert item["fact_card"]["volume_24h_usd"] == 2_300_000
    assert "market_context_json" not in item


def test_signal_pulse_rejects_v1_factor_snapshot_with_hard_gates() -> None:
    row = _candidate_row(
        "candidate-v1",
        pulse_status="token_watch",
        verdict="token_watch",
        market_status="fresh",
    )
    row["factor_snapshot_json"] = {
        "schema_version": "token_factor_snapshot_v1",
        "subject": {"symbol": "PEPE", "target_type": "Asset", "target_id": "asset:pepe"},
        "families": {"market_quality": {"facts": {"market_status": "fresh"}}},
        "hard_gates": {"eligible_for_high_alert": True, "blocked_reasons": []},
        "composite": {"rank_score": 82},
    }
    pulse = FakePulseRepository(pages={None: {"items": [row], "next_cursor": None}})

    result = SignalPulseService(pulse=pulse).pulse(
        window="1h",
        scope="all",
        status=None,
        handle=None,
        q=None,
        limit=20,
        cursor=None,
        agent_worker_running=True,
    )

    assert result["items"] == []


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda snapshot: snapshot["families"].__setitem__("market_quality", {"facts": {}}), "market_quality"),
        (lambda snapshot: snapshot.pop("normalization"), "normalization"),
        (lambda snapshot: snapshot.pop("provenance"), "provenance"),
        (lambda snapshot: snapshot.__setitem__("legacy_score", {"score": 100}), "legacy_score"),
    ],
)
def test_signal_pulse_rejects_malformed_v3_snapshot_shape(mutate, match: str) -> None:
    row = _candidate_row(
        "candidate-malformed-v2",
        pulse_status="token_watch",
        verdict="token_watch",
        market_status="fresh",
    )
    mutate(row["factor_snapshot_json"])
    pulse = FakePulseRepository(pages={None: {"items": [row], "next_cursor": None}})

    result = SignalPulseService(pulse=pulse).pulse(
        window="1h",
        scope="all",
        status=None,
        handle=None,
        q=None,
        limit=20,
        cursor=None,
        agent_worker_running=True,
    )

    assert match
    assert result["items"] == []


def _factor_snapshot(*, market_status: str | None) -> dict[str, Any]:
    market_health = "ready" if market_status == "fresh" else "missing"
    market = {
        "market_status": "anchored" if market_status else "missing",
        "event_price_readiness": {"status": "ready" if market_status else "missing"},
        "provider": "okx" if market_status else None,
        "anchor_price_usd": 0.42 if market_status else None,
        "anchor_price_quote": None,
        "anchor_quote_symbol": "USD" if market_status else None,
        "anchor_price_basis": "usd" if market_status else None,
        "anchor_observed_at_ms": 1_700_000_000_500 if market_status else None,
        "social_signal_start_ms": 1_700_000_000_000,
        "anchor_lag_ms": 500 if market_status else None,
    }
    return {
        "schema_version": "token_factor_snapshot_v3_social_attention",
        "subject": {
            "symbol": "PEPE",
            "target_type": "Asset",
            "target_id": "asset:pepe",
            "target_market_type": "dex",
        },
        "market": market,
        "gates": {"eligible_for_high_alert": True, "blocked_reasons": [], "risk_reasons": []},
        "data_health": {"identity": "ready", "market": market_health, "social": "ready", "alpha": "ready"},
        "families": {
            "social_heat": _family(80, 0.35, {"mentions_1h": 9, "unique_authors": 3, "watched_mentions": 1}),
            "social_propagation": _family(76, 0.3, {"independent_authors": 4}),
            "semantic_catalyst": _family(72, 0.25, {"phase": "ignition"}),
            "timing_risk": _family(65, 0.1, {"price_change_status": market_status}),
        },
        "normalization": {"status": "pending_cross_section"},
        "composite": {
            "rank_score": 82,
            "recommended_decision": "high_alert",
            "family_scores": {
                "social_heat": 80,
                "social_propagation": 76,
                "semantic_catalyst": 72,
                "timing_risk": 65,
            },
        },
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1_700_000_000_000},
    }


def _family(score: int, weight: float, facts: dict[str, Any]) -> dict[str, Any]:
    return {
        "raw_score": score,
        "score": score,
        "weight": weight,
        "data_health": "ready",
        "facts": facts,
        "factors": {},
    }
