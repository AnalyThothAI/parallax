from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from gmgn_twitter_intel.app.runtime.runtime_worker_context import RuntimeWorkerContext
from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.app.runtime.worker_space import (
    ClaimContract,
    ClaimDiscipline,
    ProviderIOContract,
    WorkerSpace,
    WorkerSpaceContract,
    WorkerSpaceViolation,
)


def test_provider_io_fails_inside_db_session() -> None:
    context = RuntimeWorkerContext(
        worker_name="runtime_context_test",
        db=_Db(),
        space=WorkerSpace(_contract(provider_allowed=True, claim_required=False)),
    )

    with (
        pytest.raises(WorkerSpaceViolation, match="provider IO inside DB session"),
        context.claim_session(),
        context.provider_io(),
    ):
        pass


def test_payload_load_requires_claim() -> None:
    context = RuntimeWorkerContext(
        worker_name="runtime_context_test",
        db=_Db(),
        space=WorkerSpace(_contract(provider_allowed=False, claim_required=True)),
    )

    with (
        pytest.raises(WorkerSpaceViolation, match="payload loaded before claim"),
        context.payload_session(),
    ):
        pass

    context.mark_claimed(count=1)
    with context.payload_session() as repos:
        assert repos.name == "runtime_context_test"


def test_worker_base_runtime_context_requires_explicit_contract() -> None:
    worker = _RuntimeContextProbeWorker(
        name="token_radar_projection",
        settings=SimpleNamespace(enabled=True, statement_timeout_seconds=None),
        db=_Db(),
        telemetry=SimpleNamespace(),
    )

    with pytest.raises(RuntimeError, match="missing WorkerSpace contract"):
        worker._runtime_context()


def _contract(*, provider_allowed: bool, claim_required: bool) -> WorkerSpaceContract:
    if not claim_required:
        return WorkerSpaceContract(
            worker_name="runtime_context_test",
            claim=ClaimContract(discipline=ClaimDiscipline.SCHEDULED_PROVIDER),
            provider_io=ProviderIOContract(allowed=provider_allowed),
        )
    return WorkerSpaceContract(
        worker_name="runtime_context_test",
        claim=ClaimContract(
            discipline=ClaimDiscipline.DIRTY_TARGET,
            tables=("runtime_context_targets",),
            required_before_payload_load=claim_required,
        ),
        provider_io=ProviderIOContract(allowed=provider_allowed),
    )


class _Db:
    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        yield SimpleNamespace(name=name, statement_timeout_seconds=statement_timeout_seconds)


class _RuntimeContextProbeWorker(WorkerBase):
    async def run_once(self) -> WorkerResult:
        return WorkerResult()
