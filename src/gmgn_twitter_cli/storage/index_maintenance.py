from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .lancedb_client import LanceDbClient

IndexKind = Literal["scalar", "fts", "vector"]


@dataclass(frozen=True, slots=True)
class IndexSpec:
    table_name: str
    column: str
    kind: IndexKind


CORE_INDEXES: tuple[IndexSpec, ...] = (
    IndexSpec("raw_frames", "frame_id", "scalar"),
    IndexSpec("raw_frames", "payload_hash", "scalar"),
    IndexSpec("twitter_events", "event_id", "scalar"),
    IndexSpec("twitter_events", "tweet_id", "scalar"),
    IndexSpec("twitter_events", "author_handle", "scalar"),
    IndexSpec("twitter_events", "channel", "scalar"),
    IndexSpec("twitter_events", "received_at_ms", "scalar"),
    IndexSpec("twitter_events", "matched_at_ms", "scalar"),
    IndexSpec("twitter_events", "token_resolution_status", "scalar"),
    IndexSpec("tweet_entities", "event_id", "scalar"),
    IndexSpec("tweet_entities", "entity_type", "scalar"),
    IndexSpec("tweet_entities", "normalized_value", "scalar"),
    IndexSpec("tweet_entities", "chain", "scalar"),
    IndexSpec("token_registry", "token_key", "scalar"),
    IndexSpec("token_registry", "ca", "scalar"),
    IndexSpec("token_registry", "symbol", "scalar"),
)


def ensure_core_indexes(client: LanceDbClient, *, replace: bool = False) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for spec in CORE_INDEXES:
        key = f"{spec.table_name}.{spec.column}.{spec.kind}"
        try:
            if spec.kind == "scalar":
                client.create_scalar_index(table_name=spec.table_name, column=spec.column, replace=replace)
            elif spec.kind == "fts":
                client.create_fts_index(table_name=spec.table_name, field_names=spec.column, replace=replace)
            else:
                client.create_vector_index(table_name=spec.table_name, vector_column=spec.column, replace=replace)
        except Exception as exc:  # noqa: BLE001
            statuses[key] = f"failed:{type(exc).__name__}"
        else:
            statuses[key] = "ok"
    return statuses
