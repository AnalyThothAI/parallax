from gmgn_twitter_intel.storage.lancedb_schema import table_schema


def test_twitter_events_schema_has_fixed_embedding_vector():
    schema = table_schema("twitter_events", embedding_dim=8)

    assert "event_id" in schema.names
    assert "embedding" in schema.names
    assert schema.field("embedding").type.list_size == 8


def test_raw_frames_schema_keeps_source_payloads_separate_from_tweet_facts():
    schema = table_schema("raw_frames", embedding_dim=8)

    assert schema.names == [
        "frame_id",
        "source",
        "channel",
        "received_at_ms",
        "payload_hash",
        "raw_payload_json",
        "created_at_ms",
    ]


def test_tweet_entities_schema_supports_token_query_paths():
    schema = table_schema("tweet_entities", embedding_dim=8)

    assert {"event_id", "entity_type", "normalized_value", "chain", "token_resolution_status"}.issubset(
        set(schema.names)
    )
