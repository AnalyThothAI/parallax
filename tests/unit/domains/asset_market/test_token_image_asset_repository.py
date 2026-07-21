from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.domains.asset_market.repositories.token_image_asset_repository import TokenImageAssetRepository

NOW_MS = 1_779_000_000_000
SOURCE_URL = "https://gmgn.ai/external-res/token-alpha.png"
SHA256_HEX = "a" * 64


@pytest.mark.parametrize("retry_ms", [0, -1, True, "30000"])
def test_token_image_asset_mark_error_rejects_malformed_retry_before_transaction(retry_ms: object) -> None:
    conn = _NoTransactionConnection(results=[])

    with pytest.raises(ValueError, match="token_image_asset_retry_ms_required"):
        TokenImageAssetRepository(conn).mark_error(
            SOURCE_URL,
            error="fetch failed",
            now_ms=NOW_MS,
            retry_ms=retry_ms,  # type: ignore[arg-type]
        )

    assert conn.sql == []


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda repo: repo.upsert_pending_sources([_source_row()], now_ms=NOW_MS),
            id="upsert_pending_sources",
        ),
        pytest.param(
            lambda repo: repo.mark_ready(
                SOURCE_URL,
                media_type="image/png",
                file_extension=".png",
                content_sha256=SHA256_HEX,
                byte_size=123,
                storage_path="token-alpha.png",
                now_ms=NOW_MS,
            ),
            id="mark_ready",
        ),
        pytest.param(
            lambda repo: repo.mark_error(
                SOURCE_URL,
                error="fetch failed",
                now_ms=NOW_MS,
                retry_ms=30_000,
            ),
            id="mark_error",
        ),
        pytest.param(
            lambda repo: repo.mark_unsupported(
                SOURCE_URL,
                error="unsupported svg",
                now_ms=NOW_MS,
            ),
            id="mark_unsupported",
        ),
    ],
)
def test_token_image_asset_lifecycle_writes_require_cursor_rowcount(
    operation: Callable[[TokenImageAssetRepository], object],
) -> None:
    conn = _ScriptedConnection(
        results=[{"image_id": "image-1", "status": "ready", "source_url": SOURCE_URL}],
        omit_rowcount=True,
    )

    with pytest.raises(TypeError, match="token_image_asset_repository_rowcount_invalid"):
        operation(TokenImageAssetRepository(conn))


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 2])
@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda repo: repo.upsert_pending_sources([_source_row()], now_ms=NOW_MS),
            id="upsert_pending_sources",
        ),
        pytest.param(
            lambda repo: repo.mark_ready(
                SOURCE_URL,
                media_type="image/png",
                file_extension=".png",
                content_sha256=SHA256_HEX,
                byte_size=123,
                storage_path="token-alpha.png",
                now_ms=NOW_MS,
            ),
            id="mark_ready",
        ),
        pytest.param(
            lambda repo: repo.mark_error(
                SOURCE_URL,
                error="fetch failed",
                now_ms=NOW_MS,
                retry_ms=30_000,
            ),
            id="mark_error",
        ),
        pytest.param(
            lambda repo: repo.mark_unsupported(
                SOURCE_URL,
                error="unsupported svg",
                now_ms=NOW_MS,
            ),
            id="mark_unsupported",
        ),
    ],
)
def test_token_image_asset_lifecycle_writes_reject_invalid_cursor_rowcount(
    operation: Callable[[TokenImageAssetRepository], object],
    rowcount: Any,
) -> None:
    conn = _ScriptedConnection(
        results=[{"image_id": "image-1", "status": "ready", "source_url": SOURCE_URL}],
        rowcount=rowcount,
    )

    with pytest.raises(TypeError, match="token_image_asset_repository_rowcount_invalid"):
        operation(TokenImageAssetRepository(conn))


@pytest.mark.parametrize(
    ("rowcount", "result"),
    [
        (0, {"image_id": "image-1"}),
        (1, None),
    ],
)
def test_upsert_pending_sources_returning_count_must_match_returned_row(
    rowcount: int,
    result: dict[str, Any] | None,
) -> None:
    conn = _ScriptedConnection(results=[result], rowcount=rowcount)

    with pytest.raises(TypeError, match="token_image_asset_repository_rowcount_invalid"):
        TokenImageAssetRepository(conn).upsert_pending_sources([_source_row()], now_ms=NOW_MS)


def _source_row() -> dict[str, Any]:
    return {
        "source_url": SOURCE_URL,
        "source_provider": "gmgn",
        "source_kind": "asset_profiles.logo_url",
        "raw_ref_json": {"asset_id": "asset-alpha"},
    }


_ROWCOUNT_FROM_RESULT = object()


class _ScriptedConnection:
    def __init__(
        self,
        *,
        results: list[dict[str, Any] | None],
        rowcount: Any = _ROWCOUNT_FROM_RESULT,
        omit_rowcount: bool = False,
    ) -> None:
        self.results = list(results)
        self.rowcount_setting = rowcount
        self.omit_rowcount = omit_rowcount
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.sql_depths: list[int] = []
        self.manual_commits = 0
        self.transaction_commits = 0
        self.transaction_rollbacks = 0
        self.transaction_depth = 0

    def execute(self, sql: str, params: Any = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params)
        self.sql_depths.append(self.transaction_depth)
        if hasattr(self, "rowcount"):
            del self.rowcount
        if not self.omit_rowcount:
            rowcount = 1 if self.results and self.results[0] is not None else 0
            self.rowcount = rowcount if self.rowcount_setting is _ROWCOUNT_FROM_RESULT else self.rowcount_setting
        return self

    def fetchone(self) -> dict[str, Any] | None:
        return self.results.pop(0) if self.results else None

    def commit(self) -> None:
        self.manual_commits += 1

    def transaction(self) -> _Transaction:
        return _Transaction(self)


class _NoTransactionConnection(_ScriptedConnection):
    transaction = None


class _Transaction:
    def __init__(self, conn: _ScriptedConnection) -> None:
        self.conn = conn

    def __enter__(self) -> _ScriptedConnection:
        self.conn.transaction_depth += 1
        return self.conn

    def __exit__(self, exc_type, *_args) -> bool:
        self.conn.transaction_depth -= 1
        if exc_type is None:
            self.conn.transaction_commits += 1
        else:
            self.conn.transaction_rollbacks += 1
        return False
