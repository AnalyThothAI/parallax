from __future__ import annotations

from typing import Protocol

import pyarrow as pa

REQUIRED_TABLES: tuple[str, ...] = (
    "raw_frames",
    "llm_claims",
    "llm_entities",
    "llm_relations",
    "llm_runs",
    "token_registry",
    "token_social_windows",
    "tweet_entities",
    "twitter_events",
)


class SupportsCreateIfMissing(Protocol):
    def create_if_missing(self, table_name: str, *, embedding_dim: int | None = None) -> None: ...


def table_schema(table_name: str, *, embedding_dim: int | None = None) -> pa.Schema:
    if table_name == "raw_frames":
        return pa.schema(
            [
                pa.field("frame_id", pa.string()),
                pa.field("source", pa.string()),
                pa.field("channel", pa.string()),
                pa.field("received_at_ms", pa.int64()),
                pa.field("payload_hash", pa.string()),
                pa.field("raw_payload_json", pa.string()),
                pa.field("created_at_ms", pa.int64()),
            ]
        )
    if table_name == "twitter_events":
        vector_dim = _require_embedding_dim(table_name, embedding_dim=embedding_dim)
        return pa.schema(
            [
                pa.field("event_id", pa.string()),
                pa.field("logical_dedup_key", pa.string()),
                pa.field("canonical_url", pa.string()),
                pa.field("source_provider", pa.string()),
                pa.field("source_transport", pa.string()),
                pa.field("coverage", pa.string()),
                pa.field("channel", pa.string()),
                pa.field("action", pa.string()),
                pa.field("original_action", pa.string()),
                pa.field("tweet_id", pa.string()),
                pa.field("internal_id", pa.string()),
                pa.field("timestamp", pa.int64()),
                pa.field("received_at_ms", pa.int64()),
                pa.field("author_handle", pa.string()),
                pa.field("author_name", pa.string()),
                pa.field("author_avatar", pa.string()),
                pa.field("author_followers", pa.int64()),
                pa.field("author_tags_json", pa.string()),
                pa.field("text", pa.string()),
                pa.field("text_raw", pa.string()),
                pa.field("text_clean", pa.string()),
                pa.field("embedding_text", pa.string()),
                pa.field("urls_json", pa.string()),
                pa.field("cashtags_json", pa.string()),
                pa.field("hashtags_json", pa.string()),
                pa.field("mentions_json", pa.string()),
                pa.field("media_json", pa.string()),
                pa.field("reference_json", pa.string()),
                pa.field("unfollow_target_json", pa.string()),
                pa.field("avatar_change_json", pa.string()),
                pa.field("bio_change_json", pa.string()),
                pa.field("matched_handles_json", pa.string()),
                pa.field("is_matched", pa.bool_()),
                pa.field("matched_at_ms", pa.int64()),
                pa.field("raw_json", pa.string()),
                pa.field("event_json", pa.string()),
                pa.field("token_resolution_status", pa.string()),
                pa.field("processing_priority", pa.int64()),
                pa.field("quality_flags_json", pa.string()),
                pa.field("embedding", pa.list_(pa.float32(), vector_dim)),
                pa.field("embedding_status", pa.string()),
                pa.field("embedding_updated_at_ms", pa.int64()),
                pa.field("created_at_ms", pa.int64()),
                pa.field("updated_at_ms", pa.int64()),
            ]
        )
    if table_name == "tweet_entities":
        return pa.schema(
            [
                pa.field("entity_id", pa.string()),
                pa.field("event_id", pa.string()),
                pa.field("entity_type", pa.string()),
                pa.field("raw_value", pa.string()),
                pa.field("normalized_value", pa.string()),
                pa.field("chain", pa.string()),
                pa.field("token_resolution_status", pa.string()),
                pa.field("confidence", pa.float64()),
                pa.field("source", pa.string()),
                pa.field("created_at_ms", pa.int64()),
            ]
        )
    if table_name == "token_registry":
        return pa.schema(
            [
                pa.field("token_key", pa.string()),
                pa.field("chain", pa.string()),
                pa.field("ca", pa.string()),
                pa.field("symbol", pa.string()),
                pa.field("name", pa.string()),
                pa.field("aliases_json", pa.string()),
                pa.field("source", pa.string()),
                pa.field("created_at_ms", pa.int64()),
                pa.field("updated_at_ms", pa.int64()),
            ]
        )
    if table_name == "token_social_windows":
        return pa.schema(
            [
                pa.field("window_id", pa.string()),
                pa.field("chain", pa.string()),
                pa.field("ca", pa.string()),
                pa.field("symbol", pa.string()),
                pa.field("window", pa.string()),
                pa.field("window_start_ms", pa.int64()),
                pa.field("window_end_ms", pa.int64()),
                pa.field("mention_count", pa.int64()),
                pa.field("unique_authors", pa.int64()),
                pa.field("weighted_reach", pa.float64()),
                pa.field("share_of_voice", pa.float64()),
                pa.field("velocity", pa.float64()),
                pa.field("top_authors_json", pa.string()),
                pa.field("top_tweets_json", pa.string()),
                pa.field("narratives_json", pa.string()),
                pa.field("sentiment_json", pa.string()),
                pa.field("quality_flags_json", pa.string()),
                pa.field("created_at_ms", pa.int64()),
                pa.field("updated_at_ms", pa.int64()),
            ]
        )
    if table_name == "llm_runs":
        return pa.schema(
            [
                pa.field("llm_run_id", pa.string()),
                pa.field("scope", pa.string()),
                pa.field("model", pa.string()),
                pa.field("status", pa.string()),
                pa.field("input_event_ids_json", pa.string()),
                pa.field("error", pa.string()),
                pa.field("raw_response_json", pa.string()),
                pa.field("created_at_ms", pa.int64()),
                pa.field("updated_at_ms", pa.int64()),
            ]
        )
    if table_name == "llm_claims":
        return pa.schema(
            [
                pa.field("claim_id", pa.string()),
                pa.field("llm_run_id", pa.string()),
                pa.field("event_id", pa.string()),
                pa.field("claim", pa.string()),
                pa.field("quote", pa.string()),
                pa.field("confidence", pa.float64()),
                pa.field("created_at_ms", pa.int64()),
            ]
        )
    if table_name == "llm_entities":
        return pa.schema(
            [
                pa.field("entity_id", pa.string()),
                pa.field("llm_run_id", pa.string()),
                pa.field("event_id", pa.string()),
                pa.field("name", pa.string()),
                pa.field("entity_type", pa.string()),
                pa.field("quote", pa.string()),
                pa.field("confidence", pa.float64()),
                pa.field("created_at_ms", pa.int64()),
            ]
        )
    if table_name == "llm_relations":
        return pa.schema(
            [
                pa.field("relation_id", pa.string()),
                pa.field("llm_run_id", pa.string()),
                pa.field("event_id", pa.string()),
                pa.field("subject", pa.string()),
                pa.field("predicate", pa.string()),
                pa.field("object", pa.string()),
                pa.field("quote", pa.string()),
                pa.field("confidence", pa.float64()),
                pa.field("created_at_ms", pa.int64()),
            ]
        )
    raise ValueError(f"unsupported LanceDB table: {table_name}")


def ensure_required_tables(client: SupportsCreateIfMissing, *, embedding_dim: int | None = None) -> None:
    for table_name in REQUIRED_TABLES:
        client.create_if_missing(table_name, embedding_dim=embedding_dim)


def _require_embedding_dim(table_name: str, *, embedding_dim: int | None) -> int:
    if embedding_dim is None:
        raise ValueError(f"{table_name} requires embedding_dim")
    parsed = int(embedding_dim)
    if parsed <= 0:
        raise ValueError("embedding_dim must be positive")
    return parsed
