from gmgn_twitter_intel.storage.lancedb_client import build_lancedb_client


def test_upsert_many_updates_rows_in_one_call(tmp_path):
    client = build_lancedb_client(tmp_path / "twitter_intel.lancedb", embedding_dim=8)
    client.upsert_many(
        "raw_frames",
        key_fields=("frame_id",),
        rows=[
            {
                "frame_id": "frame-1",
                "source": "gmgn",
                "channel": "twitter_monitor_basic",
                "received_at_ms": 1000,
                "payload_hash": "old",
                "raw_payload_json": "{}",
                "created_at_ms": 1000,
            },
            {
                "frame_id": "frame-2",
                "source": "gmgn",
                "channel": "twitter_monitor_basic",
                "received_at_ms": 2000,
                "payload_hash": "new",
                "raw_payload_json": "{}",
                "created_at_ms": 2000,
            },
        ],
    )

    client.upsert_many(
        "raw_frames",
        key_fields=("frame_id",),
        rows=[
            {
                "frame_id": "frame-1",
                "source": "gmgn",
                "channel": "twitter_monitor_token",
                "received_at_ms": 3000,
                "payload_hash": "updated",
                "raw_payload_json": "{}",
                "created_at_ms": 3000,
            }
        ],
    )

    rows = client.query_where("raw_frames", order_by="frame_id")
    client.close()

    assert len(rows) == 2
    assert rows[0]["frame_id"] == "frame-1"
    assert rows[0]["channel"] == "twitter_monitor_token"
    assert rows[0]["payload_hash"] == "updated"
