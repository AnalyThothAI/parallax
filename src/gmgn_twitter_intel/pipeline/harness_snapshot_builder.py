from __future__ import annotations

import hashlib
import time
from dataclasses import asdict
from typing import Any

from .harness_scoring import base_event_score, combined_score, event_score, policy_signal, shadow_signal
from .social_event_extraction import (
    PROMPT_VERSION as EXTRACTION_PROMPT_VERSION,
)
from .social_event_extraction import (
    SCHEMA_VERSION as EXTRACTION_SCHEMA_VERSION,
)
from .social_event_extraction import (
    SocialEventExtraction,
    SocialTokenCandidate,
)

SCHEMA_VERSION = EXTRACTION_SCHEMA_VERSION
CONFIG_VERSION = "social-harness-mvp-v1"
PROMPT_VERSION = EXTRACTION_PROMPT_VERSION
SCORING_VERSION = "harness-score-v1"
WEIGHT_VERSION = "report-only-v1"
POLICY_VERSION = "shadow-policy-v1"
RISK_VERSION = "shadow-risk-v1"
BASELINE_VERSION = "benchmark-zero-v1"
HORIZONS = ("6h", "24h")


class HarnessSnapshotBuilder:
    def __init__(self, harness, *, assets=None):
        self.harness = harness
        self.assets = assets

    def materialize(
        self,
        *,
        event: dict[str, Any],
        extraction: SocialEventExtraction,
        run_id: str | None,
        model_version: str,
        commit: bool = True,
    ) -> dict[str, Any]:
        event_id = str(event["event_id"])
        received_at_ms = int(event.get("received_at_ms") or _now_ms())
        author_handle = _author_handle(event)
        extraction_id = _id("social_event_extraction", event_id)
        anchor_terms = [asdict(anchor) for anchor in extraction.anchor_terms]
        token_candidates = [asdict(candidate) for candidate in extraction.token_candidates]
        risks = list(dict.fromkeys(extraction.semantic_risks + ["public_stream_coverage"]))
        social_event = self.harness.upsert_social_event_extraction(
            extraction_id=extraction_id,
            event_id=event_id,
            run_id=run_id,
            author_handle=author_handle,
            received_at_ms=received_at_ms,
            schema_version=SCHEMA_VERSION,
            model_version=model_version,
            event_type=extraction.event_type,
            source_action=extraction.source_action,
            subject=extraction.subject,
            direction_hint=extraction.direction_hint,
            attention_mechanism=extraction.attention_mechanism,
            impact_hint=extraction.impact_hint,
            semantic_novelty_hint=extraction.semantic_novelty_hint,
            confidence=extraction.confidence,
            is_signal_event=extraction.is_signal_event,
            anchor_terms=anchor_terms,
            token_candidates=token_candidates,
            semantic_risks=risks,
            summary_zh=extraction.summary_zh,
            raw_response=extraction.raw_response,
            commit=commit,
        )
        materialized: dict[str, Any] = {
            "social_event": social_event,
            "seed": None,
            "clusters": [],
            "snapshots": [],
            "decisions": [],
        }
        if not extraction.is_signal_event:
            return materialized

        direction = _direction(extraction.direction_hint)
        resolved_assets = _resolved_candidate_assets(
            extraction.token_candidates,
            self.assets,
            event_id=event_id,
            received_at_ms=received_at_ms,
            commit=commit,
        )
        eligible_assets = [
            asset
            for asset in resolved_assets
            if direction != 0
            and _entry_market_ready(self.assets, asset_id=str(asset["asset"]), received_at_ms=received_at_ms)
        ]
        seed_status = _seed_status(
            resolved_count=len(resolved_assets),
            eligible_count=len(eligible_assets),
            direction=direction,
        )
        seed_risks = _seed_risks(
            risks=risks,
            resolved_count=len(resolved_assets),
            eligible_count=len(eligible_assets),
            direction=direction,
        )
        seed = self.harness.upsert_attention_seed(
            seed_id=_id("attention_seed", event_id),
            extraction_id=extraction_id,
            event_id=event_id,
            author_handle=author_handle,
            received_at_ms=received_at_ms,
            event_type=extraction.event_type,
            subject=extraction.subject,
            anchor_terms=anchor_terms,
            token_uptake_count=len(resolved_assets),
            top_linked_symbols=[str(asset["symbol"]) for asset in resolved_assets],
            seed_status=seed_status,
            risks=seed_risks,
            commit=commit,
        )
        materialized["seed"] = seed
        if not eligible_assets:
            return materialized

        for resolved_asset in eligible_assets:
            asset = str(resolved_asset["asset"])
            cluster = self._cluster_for_asset(
                asset=asset,
                event=event,
                extraction=extraction,
                extraction_id=extraction_id,
                seed_id=seed["seed_id"],
                received_at_ms=received_at_ms,
                author_handle=author_handle,
                risks=seed_risks,
                commit=commit,
            )
            materialized["clusters"].append(cluster)
            for horizon in HORIZONS:
                snapshot, decision = self._snapshot_and_decision(
                    asset=asset,
                    event_id=event_id,
                    seed_id=seed["seed_id"],
                    cluster=cluster,
                    decision_time_ms=received_at_ms,
                    horizon=horizon,
                    risks=seed_risks,
                    commit=commit,
                )
                materialized["snapshots"].append(snapshot)
                materialized["decisions"].append(decision)
        return materialized

    def _cluster_for_asset(
        self,
        *,
        asset: str,
        event: dict[str, Any],
        extraction: SocialEventExtraction,
        extraction_id: str,
        seed_id: str,
        received_at_ms: int,
        author_handle: str | None,
        risks: list[str],
        commit: bool,
    ) -> dict[str, Any]:
        direction = _direction(extraction.direction_hint)
        pricedness = self._pricedness(asset=asset, received_at_ms=received_at_ms)
        base_score = base_event_score(
            direction=direction,
            impact=extraction.impact_hint,
            confidence=extraction.confidence,
            novelty=extraction.semantic_novelty_hint,
            pricedness=pricedness,
        )
        scored = event_score(
            base_score,
            source_weight=1.0,
            event_type_weight=1.0,
            horizon_weight=1.0,
            time_decay=1.0,
            price_penalty=1.0,
        )
        return self.harness.upsert_event_cluster(
            cluster_id=_id("event_cluster", str(event["event_id"]), asset, extraction.event_type),
            seed_id=seed_id,
            extraction_id=extraction_id,
            event_id=str(event["event_id"]),
            asset=asset,
            event_type=extraction.event_type,
            source=author_handle or "unknown",
            first_seen_at_ms=received_at_ms,
            last_seen_at_ms=received_at_ms,
            direction=direction,
            impact=extraction.impact_hint,
            confidence=extraction.confidence,
            novelty=extraction.semantic_novelty_hint,
            pricedness=pricedness,
            base_score=base_score,
            event_score=scored,
            source_list=[author_handle] if author_handle else [],
            raw_event_ids=[str(event["event_id"])],
            representative_text=_representative_text(event, extraction),
            risks=risks,
            commit=commit,
        )

    def _pricedness(self, *, asset: str, received_at_ms: int) -> float:
        if self.assets is None:
            return 0.0
        current = self.assets.market_snapshot_at_or_before(asset, received_at_ms)
        baseline = self.assets.market_snapshot_at_or_before(asset, max(0, received_at_ms - 30 * 60_000))
        current_price = _float_or_none(current.get("price_usd")) if current else None
        baseline_price = _float_or_none(baseline.get("price_usd")) if baseline else None
        if current_price is None or not baseline_price:
            return 0.0
        pre_move = abs((current_price - baseline_price) / baseline_price)
        return max(0.0, min(pre_move / 0.20, 1.0))

    def _snapshot_and_decision(
        self,
        *,
        asset: str,
        event_id: str,
        seed_id: str,
        cluster: dict[str, Any],
        decision_time_ms: int,
        horizon: str,
        risks: list[str],
        commit: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        cluster_item = {
            "cluster_id": cluster["cluster_id"],
            "event_type": cluster["event_type"],
            "source": cluster.get("source") or "unknown",
            "event_score": cluster["event_score"],
        }
        score = combined_score([float(cluster["event_score"])])
        versions = {
            "config_version": CONFIG_VERSION,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "scoring_version": SCORING_VERSION,
            "weight_version": WEIGHT_VERSION,
            "policy_version": POLICY_VERSION,
            "risk_version": RISK_VERSION,
            "baseline_version": BASELINE_VERSION,
        }
        snapshot = self.harness.create_snapshot(
            snapshot_id=_id("harness_snapshot", event_id, asset, horizon, CONFIG_VERSION),
            source_event_id=event_id,
            seed_id=seed_id,
            asset=asset,
            decision_time_ms=decision_time_ms,
            horizon=horizon,
            combined_score=score,
            policy_signal=policy_signal(score, long_threshold=0.55, short_threshold=-0.55),
            shadow_signal=shadow_signal(score, long_threshold=0.20, short_threshold=-0.20),
            market_state={"baseline": "zero", "price_move_penalty": 1.0, "pricedness_version": "pre_move_30m_v1"},
            event_clusters=[cluster_item],
            versions=versions,
            risks=risks,
            commit=commit,
        )
        signal = str(snapshot["shadow_signal"])
        decision = self.harness.record_decision(
            decision_id=_id("harness_decision", snapshot["snapshot_id"], "shadow"),
            snapshot_id=snapshot["snapshot_id"],
            asset=asset,
            decision_time_ms=decision_time_ms,
            execution_mode="shadow",
            signal=signal,
            side=_side(signal),
            size=0.0,
            entry_price=None,
            risk_reject_reason=None,
            config_version=CONFIG_VERSION,
            commit=commit,
        )
        return snapshot, decision


def _resolved_candidate_assets(
    candidates: list[SocialTokenCandidate],
    assets,
    *,
    event_id: str,
    received_at_ms: int,
    commit: bool,
) -> list[dict[str, str]]:
    if assets is None:
        return []
    resolved: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in candidates:
        asset = _asset_for_candidate(
            assets,
            candidate,
            event_id=event_id,
            received_at_ms=received_at_ms,
            commit=commit,
        )
        if asset is None or asset["asset_id"] in seen:
            continue
        symbol = str(asset.get("canonical_symbol") or candidate.symbol or candidate.project_name or asset["asset_id"])
        display_symbol = symbol.strip().lstrip("$").upper() if symbol.isascii() else symbol
        resolved.append({"asset": str(asset["asset_id"]), "symbol": display_symbol})
        seen.add(str(asset["asset_id"]))
        if len(resolved) >= 3:
            break
    return resolved


def _asset_for_candidate(
    assets,
    candidate: SocialTokenCandidate,
    *,
    event_id: str,
    received_at_ms: int,
    commit: bool,
) -> dict[str, Any] | None:
    if candidate.address and candidate.chain:
        result = assets.upsert_dex_asset(
            chain=_asset_chain(candidate.chain),
            address=candidate.address,
            symbol=candidate.symbol or candidate.project_name or candidate.address,
            observed_at_ms=received_at_ms,
            event_id=event_id,
            provider="social_event_extraction",
            commit=commit,
        )
        return result.asset
    if candidate.symbol:
        candidates = _real_candidates(assets.candidates_for_symbol(candidate.symbol))
        asset_ids = {str(row["asset_id"]): row for row in candidates if row.get("asset_id")}
        if len(asset_ids) == 1:
            return next(iter(asset_ids.values()))
    return None


def _asset_chain(chain: str) -> str:
    normalized = chain.strip().lower()
    aliases = {
        "eth": "ethereum",
        "sol": "solana",
        "bnb": "bsc",
    }
    return aliases.get(normalized, normalized)


def _real_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in candidates
        if str(candidate.get("identity_status") or "") == "resolved"
        and not str(candidate.get("asset_id") or "").startswith(("asset:unresolved", "asset:ambiguous"))
    ]


def _entry_market_ready(assets, *, asset_id: str, received_at_ms: int) -> bool:
    if assets is None:
        return False
    snapshot = assets.market_snapshot_at_or_before(asset_id, received_at_ms)
    price = _float_or_none(snapshot.get("price_usd")) if snapshot else None
    return price is not None


def _seed_status(*, resolved_count: int, eligible_count: int, direction: int) -> str:
    if resolved_count == 0:
        return "asset_unresolved"
    if direction == 0:
        return "not_directional"
    if eligible_count == 0:
        return "market_unavailable"
    return "snapshot_ready"


def _seed_risks(*, risks: list[str], resolved_count: int, eligible_count: int, direction: int) -> list[str]:
    extra: list[str] = []
    if resolved_count == 0:
        extra.append("unresolved_symbol")
    if resolved_count > 0 and direction == 0:
        extra.append("neutral_direction")
    if resolved_count > 0 and direction != 0 and eligible_count == 0:
        extra.append("missing_entry_market")
    return list(dict.fromkeys([*risks, *extra]))


def _direction(direction_hint: str) -> int:
    if direction_hint == "attention_positive":
        return 1
    if direction_hint in {"attention_negative", "risk_negative"}:
        return -1
    return 0


def _side(signal: str) -> str:
    if signal.startswith("LONG"):
        return "LONG"
    if signal.startswith("SHORT"):
        return "SHORT"
    return "FLAT"


def _representative_text(event: dict[str, Any], extraction: SocialEventExtraction) -> str:
    for anchor in extraction.anchor_terms:
        if anchor.evidence:
            return anchor.evidence
    text = event.get("search_text") or event.get("text_clean")
    return str(text or "")[:280]


def _author_handle(event: dict[str, Any]) -> str | None:
    if event.get("author_handle"):
        return str(event["author_handle"]).strip().lstrip("@").lower()
    author = event.get("author")
    if isinstance(author, dict) and author.get("handle"):
        return str(author["handle"]).strip().lstrip("@").lower()
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _id(*parts: str) -> str:
    namespace = parts[0] if parts else "harness_id"
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"


def _now_ms() -> int:
    return int(time.time() * 1000)
