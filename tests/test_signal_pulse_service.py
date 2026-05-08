from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.retrieval.signal_pulse_service import SignalPulseService


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
        market_context_json={"market_status": "fresh"},
    )
    blocked = _candidate_row(
        "candidate-blocked",
        pulse_status="blocked_low_information",
        verdict="blocked_low_information",
        market_context_json={"market_status": "fresh"},
    )
    trade = _candidate_row(
        "candidate-trade",
        pulse_status="trade_candidate",
        verdict="trade_candidate",
        market_context_json={"market_status": "stale"},
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
            "summary_zh": "PEPE 社交热度显著上升。",
            "why_now_zh": "多源讨论同步出现。",
            "bull_case_zh": ["新增独立作者扩散"],
            "bear_case_zh": ["市场确认不足"],
            "confirmation_triggers_zh": ["更多独立账号确认"],
            "invalidation_triggers_zh": ["讨论迅速降温"],
            "top_risks": ["public_stream_coverage"],
            "gate_reasons": ["fresh_attention"],
            "risk_reasons": ["thin_liquidity"],
            "evidence_event_ids": ["event-1"],
            "source_event_ids": ["event-1"],
            "radar_score_json": {"score": 0.82},
            "market_context_json": {"market_status": "fresh"},
            "thesis_json": {
                "summary_zh": "PEPE 社交热度显著上升。",
                "why_now_zh": "多源讨论同步出现。",
                "bull_case_zh": ["新增独立作者扩散"],
                "bear_case_zh": ["市场确认不足"],
                "confirmation_triggers_zh": ["更多独立账号确认"],
                "invalidation_triggers_zh": ["讨论迅速降温"],
                "top_risks": ["public_stream_coverage"],
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
        market_context_json={"market_status": "fresh"},
    )
    missing_market = _candidate_row(
        "candidate-missing-market",
        pulse_status="trade_candidate",
        verdict="trade_candidate",
        market_context_json={},
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

    assert missing_market["market_context_json"] == {}
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
    market_context_json: dict[str, Any],
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
        "market_context_json": market_context_json,
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
