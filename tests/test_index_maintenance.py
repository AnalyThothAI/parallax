from gmgn_twitter_intel.storage.index_maintenance import CORE_INDEXES


def test_core_indexes_cover_health_backlog_filters():
    indexed_columns = {(spec.table_name, spec.column) for spec in CORE_INDEXES}

    assert ("twitter_events", "embedding_status") in indexed_columns
    assert ("tweet_entities", "token_resolution_status") in indexed_columns
