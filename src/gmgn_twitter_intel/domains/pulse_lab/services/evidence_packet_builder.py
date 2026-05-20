from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gmgn_twitter_intel.domains.pulse_lab.types.evidence_packet import PulseEvidencePacket
    from gmgn_twitter_intel.domains.pulse_lab.types.pulse_candidate_context import PulseCandidateContext


class PulseEvidenceBuilder:
    """Build a sealed evidence packet from repository facts before LLM stages."""

    def __init__(
        self,
        source_repository: Any,
        *,
        schema_version: str = "pulse_evidence_packet.v1",
        market_freshness_ms: int = 3_600_000,
    ) -> None:
        self._sources = source_repository
        self._schema_version = schema_version
        self._market_freshness_ms = int(market_freshness_ms)

    def build(
        self,
        context: PulseCandidateContext,
        *,
        run_id: str,
        now_ms: int,
    ) -> PulseEvidencePacket:
        factor_snapshot = _mapping(getattr(context, "factor_snapshot", {}))
        provenance_event_ids = _nested(factor_snapshot, "provenance", "source_event_ids")
        source_event_ids = _stable_strings(
            [
                *_sequence(getattr(context, "source_event_ids", ())),
                *_sequence(getattr(context, "evidence_event_ids", ())),
                *_sequence(provenance_event_ids),
            ]
        )
        events = self._list_repo("list_source_events", source_event_ids, default=())
        enriched_events = self._list_repo("list_enriched_events", source_event_ids, default=())
        market_facts = self._list_market_facts(context, now_ms=now_ms)
        identity_facts = self._list_repo("list_identity_facts", context, default=())
        discussion_digest = self._current_discussion_digest(context)

        refs: list[dict[str, Any]] = []
        social_rows = self._build_social_evidence(events, enriched_events, refs=refs)
        market_rows = self._build_market_evidence(market_facts, now_ms=now_ms, refs=refs)
        identity_rows = self._build_identity_evidence(identity_facts, now_ms=now_ms, refs=refs)
        social = _social_contract(social_rows)
        market = _market_contract(market_rows, context=context)
        identity = _identity_contract(identity_rows)
        data_gaps = self._data_gaps(social=social_rows, market=market_rows, identity=identity_rows)
        refs.extend(self._gate_refs(data_gaps, now_ms=now_ms))
        refs = sorted(_dedupe_refs(refs), key=lambda ref: str(ref["ref_id"]))
        fresh_ref_count = sum(
            1 for ref in refs if int(ref.get("observed_at_ms") or 0) >= now_ms - self._market_freshness_ms
        )

        packet_id = f"pulse-evidence:{run_id}"
        packet_payload: dict[str, Any] = {
            "evidence_packet_id": packet_id,
            "run_id": run_id,
            "evidence_packet_hash": "",
            "schema_version": self._schema_version,
            "candidate_id": str(getattr(context, "candidate_id", "") or ""),
            "target_type": _optional_str(getattr(context, "target_type", None)) or "unknown",
            "target_id": _optional_str(getattr(context, "target_id", None)) or "unknown",
            "symbol": _optional_str(getattr(context, "symbol", None)) or "",
            "window": str(getattr(context, "window", "") or ""),
            "scope": str(getattr(context, "scope", "") or ""),
            "snapshot_at_ms": int(now_ms),
            "source_event_ids": tuple(source_event_ids),
            "allowed_evidence_refs": tuple(refs),
            "social_evidence": social,
            "market_evidence": market,
            "identity_evidence": identity,
            "quality_metrics": {
                "ref_count": len(refs),
                "high_quality_ref_count": sum(1 for ref in refs if ref.get("quality") == "high"),
                "fresh_ref_count": fresh_ref_count,
                "stale_ref_count": max(0, len(refs) - fresh_ref_count),
                "completeness_score": _completeness_score(social=social, market=market, identity=identity),
            },
            "data_gaps": tuple({key: value for key, value in gap.items() if key != "ref_id"} for gap in data_gaps),
            "risk_flags": tuple(),
            "source_fingerprints": {
                "factor_snapshot_sha256": _sha256_json(_mapping(getattr(context, "factor_snapshot", {}))),
                "discussion_digest_id": _optional_str(_mapping(discussion_digest).get("digest_id")),
            },
            "admission_context": {
                "factor_snapshot": _mapping(getattr(context, "factor_snapshot", {})),
                "gate_result": _mapping(getattr(context, "gate_result", {})),
                "selected_post_count": len(_sequence(getattr(context, "selected_posts", ()))),
                "discussion_digest": _compact_discussion_digest(discussion_digest),
            },
            "summary_json": {
                "social_rows": tuple(sorted(social_rows, key=lambda row: str(row.get("ref_id") or ""))),
                "market_rows": tuple(
                    sorted(market_rows, key=lambda row: str(row.get("ref_id") or row.get("instrument_ref") or ""))
                ),
                "identity_rows": tuple(sorted(identity_rows, key=lambda row: str(row.get("ref_id") or ""))),
                "discussion_digest": _compact_discussion_digest(discussion_digest),
            },
        }
        packet_payload["evidence_packet_hash"] = _sha256_json(
            {key: value for key, value in packet_payload.items() if key != "evidence_packet_hash"}
        )
        return _packet_from_payload(packet_payload)

    def _build_social_evidence(
        self,
        events: list[Any],
        enriched_events: list[Any],
        *,
        refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        by_event_id: dict[str, dict[str, Any]] = {}
        for row in [*events, *enriched_events]:
            payload = _mapping(row)
            event_id = _optional_str(payload.get("event_id") or payload.get("id"))
            if not event_id:
                continue
            current = by_event_id.setdefault(event_id, {})
            current.update(payload)
        social: list[dict[str, Any]] = []
        for event_id, payload in sorted(by_event_id.items()):
            observed_at_ms = _int(payload.get("observed_at_ms") or payload.get("created_at_ms"))
            ref_id = f"event:{event_id}"
            summary = _summary(payload, fallback=f"社交事件 {event_id}")
            refs.append(
                _ref(
                    ref_id=ref_id,
                    ref_type="event",
                    source_table=str(payload.get("source_table") or "events"),
                    source_id=event_id,
                    observed_at_ms=observed_at_ms,
                    summary_zh=summary,
                    quality=str(payload.get("quality") or "medium"),
                )
            )
            social.append(
                {
                    "ref_id": ref_id,
                    "event_id": event_id,
                    "observed_at_ms": observed_at_ms,
                    "summary_zh": summary,
                    "url": _optional_str(payload.get("url")),
                }
            )
        return social

    def _build_market_evidence(
        self,
        market_facts: list[Any],
        *,
        now_ms: int,
        refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        metric_names = ("price_usd", "volume_24h_usd", "liquidity_usd", "open_interest_usd", "funding_rate")
        for row in market_facts:
            payload = _mapping(row)
            observed_at_ms = _int(payload.get("observed_at_ms") or payload.get("received_at_ms") or now_ms)
            pricefeed_id = _optional_str(payload.get("pricefeed_id"))
            instrument_ref = _optional_str(payload.get("instrument_ref") or pricefeed_id or payload.get("pair_ref"))
            source_provider = _optional_str(
                payload.get("source_provider") or payload.get("provider") or payload.get("source")
            )
            freshness_status = str(
                payload.get("freshness_status") or _freshness(now_ms, observed_at_ms, self._market_freshness_ms)
            )
            market_row = {
                key: payload[key]
                for key in metric_names
                if key in payload and payload.get(key) is not None
            }
            market_row.update(
                {
                    "ref_id": _market_ref_id(payload, instrument_ref=instrument_ref),
                    "route": str(payload.get("route") or _route_from_market_type(payload.get("target_market_type"))),
                    "target_market_type": _optional_str(payload.get("target_market_type")),
                    "venue_ref": _venue_ref(payload, source_provider=source_provider, instrument_ref=instrument_ref),
                    "instrument_ref": instrument_ref,
                    "pair_ref": _optional_str(payload.get("pair_ref") or payload.get("pair_address")),
                    "observed_at_ms": observed_at_ms,
                    "freshness_status": freshness_status,
                    "source_provider": source_provider,
                    "pricefeed_id": pricefeed_id,
                }
            )
            evidence.append(market_row)
            refs.append(
                _ref(
                    ref_id=str(market_row["ref_id"]),
                    ref_type="market",
                    source_table=str(payload.get("source_table") or "market_ticks"),
                    source_id=str(instrument_ref or pricefeed_id or market_row["ref_id"]),
                    observed_at_ms=observed_at_ms,
                    summary_zh="市场快照",
                    quality="high" if market_row["freshness_status"] == "fresh" else "medium",
                )
            )
            for metric_name in metric_names:
                if market_row.get(metric_name) is None:
                    continue
                ref_id = f"metric:market:{metric_name}"
                refs.append(
                    _ref(
                        ref_id=ref_id,
                        ref_type="metric",
                        source_table=str(payload.get("source_table") or "market_ticks"),
                        source_id=str(instrument_ref or pricefeed_id or metric_name),
                        observed_at_ms=observed_at_ms,
                        summary_zh=f"市场指标 {metric_name}",
                        quality="high" if market_row["freshness_status"] == "fresh" else "medium",
                    )
                )
        return evidence

    def _build_identity_evidence(
        self,
        identity_facts: list[Any],
        *,
        now_ms: int,
        refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for row in identity_facts:
            payload = _mapping(row)
            source_id = str(payload.get("source_id") or payload.get("target_id") or payload.get("id") or "").strip()
            if not source_id:
                continue
            observed_at_ms = _int(payload.get("observed_at_ms") or now_ms)
            ref_id = source_id if source_id.startswith(("identity:", "profile:")) else f"identity:{source_id}"
            ref_type = "profile" if ref_id.startswith("profile:") else "identity"
            summary = _summary(payload, fallback=f"身份事实 {source_id}")
            refs.append(
                _ref(
                    ref_id=ref_id,
                    ref_type=ref_type,
                    source_table=str(payload.get("source_table") or "asset_identity_current"),
                    source_id=source_id,
                    observed_at_ms=observed_at_ms,
                    summary_zh=summary,
                    quality=str(payload.get("quality") or "high"),
                )
            )
            evidence.append({"ref_id": ref_id, **payload, "observed_at_ms": observed_at_ms, "summary_zh": summary})
        return evidence

    def _data_gaps(
        self,
        *,
        social: list[dict[str, Any]],
        market: list[dict[str, Any]],
        identity: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        gaps: list[dict[str, Any]] = []
        if not social:
            gaps.append(
                {
                    "gap_id": "social_missing",
                    "ref_type": "event",
                    "severity": "high",
                    "summary_zh": "缺少可引用社交事件证据",
                    "ref_id": "gate:pulse:social_missing",
                }
            )
        if not market:
            gaps.append(
                {
                    "gap_id": "market_missing",
                    "ref_type": "market",
                    "severity": "high",
                    "summary_zh": "缺少可引用市场证据",
                    "ref_id": "gate:pulse:market_missing",
                }
            )
        elif any(row.get("freshness_status") == "stale" for row in market):
            gaps.append(
                {
                    "gap_id": "market_stale",
                    "ref_type": "market",
                    "severity": "medium",
                    "summary_zh": "市场证据已过期",
                    "ref_id": "gate:pulse:market_stale",
                }
            )
        if not identity:
            gaps.append(
                {
                    "gap_id": "identity_missing",
                    "ref_type": "identity",
                    "severity": "high",
                    "summary_zh": "缺少目标身份/Profile 证据",
                    "ref_id": "gate:pulse:identity_missing",
                }
            )
        return gaps

    def _gate_refs(self, data_gaps: list[dict[str, Any]], *, now_ms: int) -> list[dict[str, Any]]:
        return [
            _ref(
                ref_id=str(gap["ref_id"]),
                ref_type="gate",
                source_table="pulse_evidence_builder",
                source_id=str(gap["gap_id"]),
                observed_at_ms=now_ms,
                summary_zh=str(gap["summary_zh"]),
                quality="medium",
            )
            for gap in data_gaps
            if gap.get("ref_id")
        ]

    def _list_repo(self, method_name: str, arg: Any, *, default: tuple[Any, ...]) -> list[Any]:
        method = getattr(self._sources, method_name, None)
        if method is None:
            return list(default)
        value = method(arg)
        if value is None:
            return list(default)
        return list(value)

    def _list_market_facts(self, context: Any, *, now_ms: int) -> list[Any]:
        method = getattr(self._sources, "list_market_facts", None)
        if method is None:
            return []
        value = method(context, max_age_ms=self._market_freshness_ms, now_ms=now_ms)
        if value is None:
            return []
        return list(value)

    def _current_discussion_digest(self, context: Any) -> dict[str, Any] | None:
        method = getattr(self._sources, "get_current_discussion_digest", None)
        if method is None:
            return None
        target_type = _optional_str(getattr(context, "target_type", None))
        target_id = _optional_str(getattr(context, "target_id", None))
        window = _optional_str(getattr(context, "window", None))
        scope = _optional_str(getattr(context, "scope", None))
        if not target_type or not target_id or not window or not scope:
            return None
        return method(
            target_type=target_type,
            target_id=target_id,
            window=window,
            scope=scope,
            schema_version="narrative_intel_v1",
        )


def _packet_from_payload(payload: dict[str, Any]) -> PulseEvidencePacket:
    from gmgn_twitter_intel.domains.pulse_lab.types.evidence_packet import PulseEvidencePacket

    return PulseEvidencePacket.model_validate(payload).sealed_copy()


def _ref(
    *,
    ref_id: str,
    ref_type: str,
    source_table: str,
    source_id: str,
    observed_at_ms: int,
    summary_zh: str,
    quality: str,
) -> dict[str, Any]:
    return {
        "ref_id": ref_id,
        "ref_type": ref_type,
        "source_table": source_table,
        "source_id": source_id,
        "observed_at_ms": observed_at_ms,
        "summary_zh": summary_zh,
        "quality": quality if quality in {"high", "medium", "low"} else "medium",
    }


def _market_ref_id(payload: dict[str, Any], *, instrument_ref: str | None) -> str:
    source_id = instrument_ref or _optional_str(payload.get("pricefeed_id")) or _optional_str(payload.get("pair_ref"))
    return f"market:{source_id}" if source_id else "market:unknown"


def _venue_ref(payload: dict[str, Any], *, source_provider: str | None, instrument_ref: str | None) -> str | None:
    explicit = _optional_str(payload.get("venue_ref") or payload.get("venue_id") or payload.get("exchange"))
    if explicit:
        return explicit if explicit.startswith("venue:") else f"venue:{explicit}"
    if source_provider:
        return f"venue:{source_provider}"
    if instrument_ref and ":cex:" in instrument_ref:
        parts = instrument_ref.split(":")
        if len(parts) > 3:
            return f"venue:{parts[3]}"
    return None


def _route_from_market_type(value: Any) -> str:
    text = str(value or "").lower()
    if text in {"cex", "spot", "perp", "perpetual"}:
        return "cex"
    if text in {"dex", "meme"}:
        return "meme"
    return "unknown"


def _social_contract(rows: list[dict[str, Any]]) -> dict[str, Any]:
    event_refs = tuple(sorted(str(row.get("ref_id")) for row in rows if row.get("ref_id")))
    return {
        "status": "complete" if event_refs else "insufficient",
        "event_refs": event_refs,
        "cluster_refs": tuple(),
        "summary_zh": "；".join(str(row.get("summary_zh") or "") for row in rows if row.get("summary_zh"))[:300],
    }


def _market_contract(rows: list[dict[str, Any]], *, context: PulseCandidateContext | Any = None) -> dict[str, Any]:
    if not rows:
        factor_snapshot = _mapping(getattr(context, "factor_snapshot", {}) if context is not None else {})
        subject = _mapping(factor_snapshot.get("subject"))
        target_market_type = str(subject.get("target_market_type") or "")
        return {
            "status": "insufficient",
            "route": _route_from_market_type(target_market_type),
            "target_market_type": target_market_type,
            "freshness_status": "missing",
            "market_refs": tuple(),
        }
    row = rows[0]
    route = str(row.get("route") or "unknown")
    if route == "meme" and str(row.get("target_market_type") or "").lower() == "dex":
        route = "dex"
    freshness_status = str(row.get("freshness_status") or "unknown")
    market_refs = tuple(sorted(str(value) for value in (row.get("ref_id"), "metric:market:price_usd") if value))
    status = "stale" if freshness_status == "stale" else "complete"
    return {
        "status": status,
        "route": route if route in {"cex", "dex", "meme", "unknown"} else "unknown",
        "target_market_type": str(row.get("target_market_type") or ""),
        "price_usd": row.get("price_usd"),
        "venue_ref": row.get("venue_ref"),
        "instrument_ref": row.get("instrument_ref") or row.get("pair_ref"),
        "observed_at_ms": row.get("observed_at_ms"),
        "freshness_status": (
            freshness_status if freshness_status in {"fresh", "stale", "missing", "unknown"} else "unknown"
        ),
        "source_provider": row.get("source_provider"),
        "pricefeed_id": row.get("pricefeed_id"),
        "volume_24h_usd": row.get("volume_24h_usd"),
        "open_interest_usd": row.get("open_interest_usd"),
        "funding_rate": row.get("funding_rate"),
        "liquidity_usd": row.get("liquidity_usd"),
        "market_cap_usd": row.get("market_cap_usd"),
        "market_refs": market_refs,
    }


def _identity_contract(rows: list[dict[str, Any]]) -> dict[str, Any]:
    identity_refs = tuple(
        sorted(str(row.get("ref_id")) for row in rows if str(row.get("ref_id") or "").startswith("identity:"))
    )
    profile_refs = tuple(
        sorted(str(row.get("ref_id")) for row in rows if str(row.get("ref_id") or "").startswith("profile:"))
    )
    return {
        "status": "complete" if identity_refs or profile_refs else "insufficient",
        "identity_refs": identity_refs,
        "profile_refs": profile_refs,
        "summary_zh": "；".join(str(row.get("summary_zh") or "") for row in rows if row.get("summary_zh"))[:300],
    }


def _compact_discussion_digest(row: dict[str, Any] | None) -> dict[str, Any] | None:
    payload = _mapping(row)
    if not payload:
        return None
    currentness = _mapping(payload.get("currentness"))
    return {
        "digest_id": _optional_str(payload.get("digest_id")),
        "schema_version": _optional_str(payload.get("schema_version")),
        "computed_at_ms": _int(payload.get("computed_at_ms")),
        "semantic_coverage": payload.get("semantic_coverage"),
        "currentness": currentness,
        "headline_zh": _optional_str(payload.get("headline_zh")),
        "dominant_narratives": payload.get("dominant_narratives_json") or (),
        "bull_view": payload.get("bull_view_json") or {},
        "bear_view": payload.get("bear_view_json") or {},
        "propagation_read": payload.get("propagation_read_json") or {},
        "reflexivity_read": payload.get("reflexivity_read_json") or {},
        "evidence_refs": payload.get("evidence_refs_json") or (),
        "data_gaps": _discussion_digest_data_gaps(payload, currentness=currentness),
    }


def _discussion_digest_data_gaps(payload: dict[str, Any], *, currentness: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = [_mapping(gap) for gap in _sequence(payload.get("data_gaps_json") or payload.get("data_gaps") or ())]
    gaps = [gap for gap in gaps if gap]
    display_status = str(currentness.get("display_status") or "")
    if display_status not in {"updating", "stale"}:
        return gaps
    reason = str(currentness.get("reason") or ("digest_updating" if display_status == "updating" else "digest_stale"))
    if any(str(gap.get("reason") or "") == reason for gap in gaps):
        return gaps
    gap: dict[str, Any] = {"reason": reason}
    delta_source_event_count = currentness.get("delta_source_event_count")
    if delta_source_event_count is not None:
        gap["delta_source_event_count"] = delta_source_event_count
    gaps.append(gap)
    return gaps


def _completeness_score(*, social: dict[str, Any], market: dict[str, Any], identity: dict[str, Any]) -> float:
    ready = sum(1 for item in (social, market, identity) if item.get("status") == "complete")
    return round(ready / 3, 4)


def _freshness(now_ms: int, observed_at_ms: int, freshness_ms: int) -> str:
    if observed_at_ms <= 0:
        return "missing"
    return "fresh" if now_ms - observed_at_ms <= freshness_ms else "stale"


def _summary(payload: dict[str, Any], *, fallback: str) -> str:
    return str(
        payload.get("summary_zh")
        or payload.get("summary")
        or payload.get("text")
        or payload.get("title")
        or fallback
    ).strip()


def _nested(data: dict[str, Any], outer: str, inner: str) -> Any:
    outer_value = data.get(outer)
    if isinstance(outer_value, dict):
        return outer_value.get(inner)
    return None


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, list | tuple | set):
        return list(value)
    return []


def _stable_strings(values: list[Any]) -> list[str]:
    return sorted(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_ref: dict[str, dict[str, Any]] = {}
    for ref in refs:
        ref_id = str(ref.get("ref_id") or "")
        if ref_id and ref_id not in by_ref:
            by_ref[ref_id] = ref
    return list(by_ref.values())


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


__all__ = ["PulseEvidenceBuilder"]
