from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_space import WorkerSpace, WorkerSpaceViolation


class RuntimeWorkerContext:
    def __init__(
        self,
        *,
        worker_name: str,
        db: Any,
        space: WorkerSpace,
        statement_timeout_seconds: float | None = None,
    ) -> None:
        self.worker_name = str(worker_name)
        self.db = db
        self.space = space
        self.statement_timeout_seconds = statement_timeout_seconds
        self._claimed_count = 0

    @contextmanager
    def claim_session(self) -> Iterator[Any]:
        with self._worker_session() as repos:
            yield repos

    @contextmanager
    def payload_session(self) -> Iterator[Any]:
        self.require_claimed_payload()
        with self._worker_session() as repos:
            yield repos

    @contextmanager
    def persist_session(self) -> Iterator[Any]:
        with self._worker_session() as repos:
            yield repos

    @contextmanager
    def transaction_session(self) -> Iterator[Any]:
        with self._worker_session() as repos, self.space.db_transaction(), repos.unit_of_work():
            yield repos

    def mark_claimed(self, *, count: int) -> None:
        self._claimed_count = max(0, int(count))
        self.space.mark_claimed(count=self._claimed_count)

    def require_claimed_payload(self) -> None:
        if self._claimed_count <= 0:
            raise WorkerSpaceViolation(f"{self.worker_name}: payload loaded before claim")
        self.space.require_claim_before_payload_load()

    @contextmanager
    def provider_io(self) -> Iterator[None]:
        with self.space.provider_io():
            yield

    @contextmanager
    def _worker_session(self) -> Iterator[Any]:
        with (
            self.space.db_session(),
            self.db.worker_session(
                self.worker_name,
                statement_timeout_seconds=self.statement_timeout_seconds,
            ) as repos,
        ):
            yield repos
