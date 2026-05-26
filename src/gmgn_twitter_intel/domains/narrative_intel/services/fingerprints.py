from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Sequence
from typing import Any

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")
_WHITESPACE = re.compile(r"\s+")


def text_fingerprint(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = _CONTROL_CHARS.sub(" ", normalized)
    normalized = _WHITESPACE.sub(" ", normalized).strip().casefold()
    return _hash_payload(["text", normalized])


def source_fingerprint(event_ids: Sequence[str], source_max_received_at_ms: int | None) -> str:
    unique_event_ids = sorted({str(event_id) for event_id in event_ids if str(event_id)})
    return _hash_payload(["source", unique_event_ids, int(source_max_received_at_ms or 0)])


def label_fingerprint(semantic_rows: Sequence[dict[str, Any]]) -> str:
    items = []
    for row in semantic_rows:
        confidence_bucket = int(float(row.get("semantic_confidence") or 0.0) * 10)
        computed_bucket = int(row.get("computed_at_ms") or 0) // 60_000
        items.append(
            {
                "semantic_id": str(row.get("semantic_id") or ""),
                "trade_stance": str(row.get("trade_stance") or "unknown"),
                "attention_valence": str(row.get("attention_valence") or "unknown"),
                "narrative_cluster_key": str(row.get("narrative_cluster_key") or ""),
                "confidence_bucket": confidence_bucket,
                "computed_bucket": computed_bucket,
            }
        )
    items.sort(key=lambda item: str(item["semantic_id"]))
    return _hash_payload(["labels", items])


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
