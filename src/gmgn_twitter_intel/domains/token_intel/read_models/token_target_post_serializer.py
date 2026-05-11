from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.token_intel.scoring.post_text_quality import post_quality_score

from .token_message_price_payload import message_price_payload


def token_target_post_payload(
    row: dict[str, Any],
    *,
    stage: dict[str, Any] | None = None,
    bucket_ms: int | None = None,
    since_ms: int | None = None,
) -> dict[str, Any]:
    text = row.get("text_clean") or row.get("text")
    watched = bool(row.get("is_watched"))
    confidence = float(row.get("confidence") or 0.0)
    quality = post_quality_score(
        {
            "text": text,
            "mention_source": "token_intent",
            "attribution_status": "direct",
            "attribution_confidence": confidence,
            "attribution_weight": confidence,
            "is_watched": watched,
        }
    )
    payload = {
        "event_id": row.get("event_id"),
        "tweet_id": row.get("tweet_id"),
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "symbol": row.get("symbol"),
        "handle": row.get("author_handle"),
        "author_handle": row.get("author_handle"),
        "text": text,
        "url": row.get("canonical_url"),
        "received_at_ms": row.get("received_at_ms"),
        "mention_source": "token_intent",
        "attribution_status": row.get("attribution_status"),
        "attribution_confidence": confidence,
        "attribution_weight": confidence,
        "is_watched": row.get("is_watched"),
        "is_first_seen_by_watched_for_token": watched,
        "event_type": "watched_token_intent" if watched else "public_token_intent",
        "reference": _reference(row.get("reference_json")),
        "catalyst_score": int(quality.get("score") or 0) if watched else None,
        "catalyst_components": None,
        "price": message_price_payload(row),
        "post_quality": quality,
        "stage_id": stage.get("stage_id") if stage else None,
        "stage_phase": stage.get("stage_phase") if stage else None,
        "author_role": stage.get("author_role") if stage else None,
        "is_stage_representative": bool(stage.get("is_stage_representative")) if stage else False,
        "price_delta_from_previous_post_pct": stage.get("price_delta_from_previous_post_pct") if stage else None,
    }
    if bucket_ms is not None and since_ms is not None:
        received_at_ms = int(row.get("received_at_ms") or 0)
        payload["bucket_start_ms"] = since_ms + ((received_at_ms - since_ms) // bucket_ms) * bucket_ms
    return payload


def _reference(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "tweet_id": value.get("tweet_id"),
        "author_handle": value.get("author_handle") or value.get("handle"),
        "type": value.get("type"),
    }
