import pytest

from parallax.domains.account_quality.read_models.account_quality_service import AccountQualityService
from parallax.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository
from parallax.domains.account_quality.services.account_quality_backfill_service import AccountQualityBackfillService
from tests.factories import open_runtime, token_event


def test_account_quality_backfill_service_backfills_first_token_mentions(tmp_path):
    conn, ingest, _signals, _tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        ingest.ingest_event(
            token_event("event-dog-first", received_at_ms=now_ms - 10_000, author_handle="early"),
            is_watched=True,
        )
        ingest.ingest_event(
            token_event("event-dog-repeat", received_at_ms=now_ms - 5_000, author_handle="early"),
            is_watched=True,
        )
        repository = AccountQualityRepository(conn)
        result = AccountQualityBackfillService(repository=repository).backfill_account_token_call_stats(limit=100)
        account = AccountQualityService(repository=repository).account_quality("early")
    finally:
        conn.close()

    assert result["stats_upserted"] == 1
    assert account["profile"]["handle"] == "early"
    assert account["token_call_stats"][0]["mention_count"] == 2
    assert account["token_call_stats"][0]["token_id"].startswith("asset:eip155:1:erc20:")
    assert account["token_call_stats"][0]["outcome_status"] == "insufficient_market_history"


def test_account_quality_backfill_runs_inside_one_connection_transaction():
    conn = FakeTransactionConn()
    repository = FakeAccountQualityBackfillRepository(conn=conn)

    result = AccountQualityBackfillService(repository=repository).backfill_account_token_call_stats(limit=100)

    assert result == {"accounts_touched": 1, "stats_upserted": 1}
    assert conn.events == ["enter", "exit"]
    assert conn.commits == 0
    assert repository.calls == [
        ("account_token_rows", 1),
        ("upsert_profile", 1),
        ("upsert_token_call_stat", 1),
        ("account_quality", 1),
        ("insert_quality_snapshot", 1),
    ]


def test_account_quality_backfill_requires_connection_transaction_before_reads_or_writes():
    repository = FakeAccountQualityBackfillRepository(conn=object())

    with pytest.raises(RuntimeError, match="account_quality_backfill_transaction_required"):
        AccountQualityBackfillService(repository=repository).backfill_account_token_call_stats(limit=100)

    assert repository.calls == []


def test_account_quality_for_handles_uses_batched_repository_read():
    repository = FakeAccountQualityReadRepository()

    data = AccountQualityService(repository=repository).account_quality_for_handles([" Early ", "@early", "Late"])

    assert repository.calls == [("accounts_quality", ("early", "late"))]
    assert data["query"] == {"handles": ["early", "late"]}
    assert [item["profile"]["handle"] for item in data["accounts"]] == ["early", "late"]
    assert data["accounts"][0]["summary"]["status"] == "ready"
    assert data["accounts"][1]["summary"]["status"] == "insufficient_sample"


class FakeAccountQualityReadRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def accounts_quality(self, handles: list[str]):
        self.calls.append(("accounts_quality", tuple(handles)))
        return [
            {
                "profile": {"handle": "early"},
                "token_call_stats": [{"token_id": "asset:early"}],
                "quality_snapshots": [{"sample_size": 5, "precision_score": 0.7}],
            },
            {
                "profile": {"handle": "late"},
                "token_call_stats": [],
                "quality_snapshots": [{"sample_size": 1, "precision_score": 0.1}],
            },
        ]

    def account_quality(self, handle: str):
        raise AssertionError(f"per-handle account_quality read is not allowed: {handle}")


class FakeAccountQualityBackfillRepository:
    def __init__(self, *, conn):
        self.conn = conn
        self.calls: list[tuple[str, int]] = []
        self._stats_by_handle: dict[str, list[dict[str, object]]] = {}

    def account_token_rows(self, *, resolver_policy_version: str, limit: int):
        assert resolver_policy_version
        assert limit == 100
        self._record("account_token_rows")
        return [
            {
                "handle": "early",
                "target_id": "asset:eip155:1:erc20:dog",
                "market_target_type": "",
                "market_target_id": "",
                "first_mention_ms": 1_700_000_000_000,
                "latest_mention_ms": 1_700_000_010_000,
                "mention_count": 2,
                "follower_max": 42,
                "watched_count": 1,
                "global_first_mention_ms": 1_700_000_000_000,
            }
        ]

    def market_ticks_for_token(self, *, target_type: str, target_id: str, first_mention_ms: int):
        assert target_type == ""
        assert target_id == ""
        assert first_mention_ms == 1_700_000_000_000
        self._record("market_ticks_for_token")
        return []

    def upsert_profile(self, *, handle: str, first_seen_ms: int, latest_seen_ms: int, commit: bool, **_kwargs):
        assert handle == "early"
        assert first_seen_ms == 1_700_000_000_000
        assert latest_seen_ms == 1_700_000_010_000
        assert commit is False
        self._record("upsert_profile")

    def upsert_token_call_stat(
        self,
        *,
        handle: str,
        token_id: str,
        first_mention_ms: int,
        mention_count: int,
        was_early_author: bool,
        outcome_status: str,
        commit: bool,
        **_kwargs,
    ):
        assert commit is False
        self._record("upsert_token_call_stat")
        self._stats_by_handle.setdefault(handle, []).append(
            {
                "token_id": token_id,
                "first_mention_ms": first_mention_ms,
                "mention_count": mention_count,
                "was_early_author": was_early_author,
                "outcome_status": outcome_status,
                "price_change_1h_pct": None,
            }
        )

    def account_quality(self, handle: str):
        self._record("account_quality")
        return {"token_call_stats": list(self._stats_by_handle.get(handle, []))}

    def insert_quality_snapshot(
        self,
        *,
        handle: str,
        window: str,
        sample_size: int,
        commit: bool,
        **_kwargs,
    ):
        assert handle == "early"
        assert window == "30d"
        assert sample_size == 1
        assert commit is False
        self._record("insert_quality_snapshot")
        return "account-quality:early:30d:current"

    def _record(self, name: str) -> None:
        self.calls.append((name, self.conn.transaction_depth))


class FakeTransactionConn:
    def __init__(self) -> None:
        self.transaction_depth = 0
        self.events: list[str] = []
        self.commits = 0

    def transaction(self):
        return FakeTransaction(self)

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("AccountQualityBackfillService must use conn.transaction(), not conn.commit()")


class FakeTransaction:
    def __init__(self, conn: FakeTransactionConn) -> None:
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_depth += 1
        self.conn.events.append("enter")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.events.append("rollback" if exc_type is not None else "exit")
        self.conn.transaction_depth -= 1
        return False
