from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any


def source_fingerprint(event_ids: Sequence[str], source_max_received_at_ms: int | None) -> str:
    unique_event_ids = sorted({str(event_id) for event_id in event_ids if str(event_id)})
    return _hash_payload(["source", unique_event_ids, int(source_max_received_at_ms or 0)])


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
