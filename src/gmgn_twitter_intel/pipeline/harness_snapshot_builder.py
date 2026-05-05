from __future__ import annotations

import hashlib
import time
from dataclasses import asdict
from typing import Any

from .harness_scoring import base_event_score, combined_score, event_score, policy_signal, shadow_signal
from .social_event_extraction import AnchorTerm, SocialEventExtraction, SocialTokenCandidate

SCHEMA_VERSION = "social-event-v1"
CONFIG_VERSION = "social-harness-mvp-v1"
PROMPT_VERSION = "social-event-extractor-v1"
SCORING_VERSION = "harness-score-v1"
WEIGHT_VERSION = "report-only-v1"
POLICY_VERSION = "shadow-policy-v1"
RISK_VERSION = "shadow-risk-v1"
BASELINE_VERSION = "baseline-zero-v0"
HORIZONS = ("6h", "24h")


class HarnessSnapshotBuilder:
    def __init__(self, harness):
        self.harness = harness

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

        candidate_assets = _candidate_asset_expressions(extraction.token_candidates)
        assets = candidate_assets or _anchor_asset_expressions(extraction.anchor_terms)
        seed_status = "snapshot_ready" if candidate_assets else "seed_only" if assets else "asset_unknown"
        seed_risks = risks if candidate_assets else list(dict.fromkeys(risks + ["unresolved_symbol"]))
        seed = self.harness.upsert_attention_seed(
            seed_id=_id("attention_seed", event_id),
            extraction_id=extraction_id,
            event_id=event_id,
            author_handle=author_handle,
            received_at_ms=received_at_ms,
            event_type=extraction.event_type,
            subject=extraction.subject,
            anchor_terms=anchor_terms,
            token_uptake_count=len(assets),
            top_linked_symbols=[asset for asset in assets if asset != "UNKNOWN"],
            seed_status=seed_status,
            risks=seed_risks,
            commit=commit,
        )
        materialized["seed"] = seed
        if not assets:
            return materialized

        for asset in assets:
            cluster = self._cluster_for_asset(
                asset=asset,
                event=event,
                extraction=extraction,
                extraction_id=extraction_id,
                seed_id=seed["seed_id"],
                received_at_ms=received_at_ms,
                author_handle=author_handle,
                risks=risks,
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
                    risks=risks,
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
        base_score = base_event_score(
            direction=direction,
            impact=extraction.impact_hint,
            confidence=extraction.confidence,
            novelty=extraction.semantic_novelty_hint,
            pricedness=0.35,
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
            pricedness=0.35,
            base_score=base_score,
            event_score=scored,
            source_list=[author_handle] if author_handle else [],
            raw_event_ids=[str(event["event_id"])],
            representative_text=_representative_text(event, extraction),
            risks=risks,
            commit=commit,
        )

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
            policy_signal=policy_signal(score, long_threshold=0.70, short_threshold=-0.70),
            shadow_signal=shadow_signal(score, long_threshold=0.25, short_threshold=-0.25),
            market_state={"baseline": "zero", "price_move_penalty": 1.0},
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


def _candidate_asset_expressions(candidates: list[SocialTokenCandidate]) -> list[str]:
    assets: list[str] = []
    for candidate in candidates:
        asset = candidate.symbol or candidate.address or candidate.project_name
        if not asset:
            continue
        normalized = asset.strip().lstrip("$").upper() if asset.isascii() else asset.strip()
        if normalized and normalized not in assets:
            assets.append(normalized)
        if len(assets) >= 3:
            break
    return assets


def _anchor_asset_expressions(anchors: list[AnchorTerm]) -> list[str]:
    assets: list[str] = []
    for anchor in anchors:
        if anchor.role not in {"asset", "meme_phrase", "product"}:
            continue
        term = anchor.term.strip().lstrip("$")
        if not term or len(term) > 20 or any(ch.isspace() for ch in term):
            continue
        normalized = "".join(ch for ch in term if ch.isalnum()).upper()
        if len(normalized) < 2:
            continue
        if normalized and normalized not in assets:
            assets.append(normalized)
        if len(assets) >= 3:
            break
    return assets


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


def _id(*parts: str) -> str:
    namespace = parts[0] if parts else "harness_id"
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"


def _now_ms() -> int:
    return int(time.time() * 1000)
