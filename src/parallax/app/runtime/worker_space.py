from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from parallax.app.runtime.current_read_model_publisher import (
    FORBIDDEN_SERVING_IDENTITY_COLUMNS,
)


class ClaimDiscipline(StrEnum):
    NONE = "none"
    DIRTY_TARGET = "dirty_target"
    LEASED_JOB = "leased_job"
    SCHEDULED_PROVIDER = "scheduled_provider"


@dataclass(frozen=True, slots=True)
class ClaimContract:
    discipline: ClaimDiscipline
    tables: tuple[str, ...] = ()
    required_before_payload_load: bool = False


@dataclass(frozen=True, slots=True)
class ProviderIOContract:
    allowed: bool
    forbid_inside_db_transaction: bool = True
    requires_bounded_batch: bool = True


@dataclass(frozen=True, slots=True)
class CurrentReadModelContract:
    tables: tuple[str, ...]
    table_identities: tuple[tuple[str, tuple[str, ...]], ...]
    payload_hash_required: bool = True
    zero_write_when_unchanged: bool = True

    def validate(self, *, worker_name: str) -> tuple[str, ...]:
        errors: list[str] = []
        if not self.tables:
            errors.append(f"{worker_name}: current read model contract has no tables")
        identities = dict(self.table_identities)
        missing_tables = sorted(set(self.tables) - set(identities))
        if missing_tables:
            errors.append(f"{worker_name}: current read model tables missing stable identities {missing_tables}")
        for table_name, identity_columns in self.table_identities:
            if not identity_columns:
                errors.append(f"{worker_name}: {table_name} current read model has no identity columns")
            forbidden = sorted(set(identity_columns) & FORBIDDEN_SERVING_IDENTITY_COLUMNS)
            if forbidden:
                errors.append(f"{worker_name}: {table_name} identity includes lifecycle columns {forbidden}")
        return tuple(errors)


@dataclass(frozen=True, slots=True)
class AgentSideEffectContract:
    ledgers: tuple[str, ...]
    reservation_required_before_claim: bool = True


@dataclass(frozen=True, slots=True)
class WorkerSpaceContract:
    worker_name: str
    claim: ClaimContract
    provider_io: ProviderIOContract
    current_read_model: CurrentReadModelContract | None = None
    agent_side_effect: AgentSideEffectContract | None = None
    advisory_lock_key: str | None = None

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if self.claim.discipline in {ClaimDiscipline.DIRTY_TARGET, ClaimDiscipline.LEASED_JOB}:
            if not self.claim.tables:
                errors.append(f"{self.worker_name}: claimed worker has no claim/control table")
            if not self.claim.required_before_payload_load:
                errors.append(f"{self.worker_name}: claim must happen before payload load")
        if self.current_read_model is not None:
            errors.extend(self.current_read_model.validate(worker_name=self.worker_name))
        if self.agent_side_effect is not None and not self.agent_side_effect.ledgers:
            errors.append(f"{self.worker_name}: agent side effect worker has no durable ledger")
        if self.provider_io.allowed and not self.provider_io.forbid_inside_db_transaction:
            errors.append(f"{self.worker_name}: provider IO must be outside DB transactions")
        return tuple(errors)


class WorkerSpaceViolation(RuntimeError):
    pass


class WorkerSpace:
    def __init__(self, contract: WorkerSpaceContract) -> None:
        errors = contract.validate()
        if errors:
            raise WorkerSpaceViolation("; ".join(errors))
        self.contract = contract
        self._db_session_depth = 0
        self._db_transaction_depth = 0
        self._claimed = False
        self._agent_capacity_reserved = False

    @contextmanager
    def db_session(self) -> Iterator[None]:
        self._db_session_depth += 1
        try:
            yield
        finally:
            self._db_session_depth -= 1

    @contextmanager
    def db_transaction(self) -> Iterator[None]:
        self._db_transaction_depth += 1
        try:
            yield
        finally:
            self._db_transaction_depth -= 1

    @contextmanager
    def provider_io(self) -> Iterator[None]:
        if not self.contract.provider_io.allowed:
            raise WorkerSpaceViolation(f"{self.contract.worker_name}: provider IO is not allowed")
        if self.contract.provider_io.forbid_inside_db_transaction and (
            self._db_session_depth > 0 or self._db_transaction_depth > 0
        ):
            raise WorkerSpaceViolation(
                f"{self.contract.worker_name}: provider IO inside DB session; provider IO inside DB transaction"
            )
        yield

    def mark_claimed(self, *, count: int) -> None:
        if self.contract.claim.discipline is ClaimDiscipline.NONE:
            raise WorkerSpaceViolation(f"{self.contract.worker_name}: claim is not part of this worker contract")
        self._claimed = count > 0

    def require_claim_before_payload_load(self) -> None:
        if self.contract.claim.required_before_payload_load and not self._claimed:
            raise WorkerSpaceViolation(f"{self.contract.worker_name}: payload loaded before claim")

    def reserve_agent_capacity(self, *, token: object | None) -> None:
        if self.contract.agent_side_effect is None:
            raise WorkerSpaceViolation(f"{self.contract.worker_name}: agent reservation is not part of this contract")
        if token is None:
            raise WorkerSpaceViolation(f"{self.contract.worker_name}: missing agent capacity token")
        self._agent_capacity_reserved = True

    def require_agent_capacity_before_claim(self) -> None:
        if self.contract.agent_side_effect is None:
            return
        if self.contract.agent_side_effect.reservation_required_before_claim and not self._agent_capacity_reserved:
            raise WorkerSpaceViolation(f"{self.contract.worker_name}: claim happened before agent capacity reservation")


def contract_from_manifest(manifest: Any) -> WorkerSpaceContract:
    dirty_tables = tuple(getattr(manifest, "dirty_target_tables", ()) or ())
    queue_table = getattr(manifest, "queue_depth_table", None)
    side_effect_ledgers = tuple(getattr(manifest, "side_effect_ledgers", ()) or ())
    writes_read_models = tuple(getattr(manifest, "writes_read_models", ()) or ())
    current_read_model_identities = tuple(getattr(manifest, "current_read_model_identities", ()) or ())
    uses_provider_io = bool(getattr(manifest, "uses_provider_io", False))

    if dirty_tables:
        claim = ClaimContract(
            discipline=ClaimDiscipline.DIRTY_TARGET,
            tables=dirty_tables,
            required_before_payload_load=True,
        )
    elif queue_table:
        claim = ClaimContract(
            discipline=ClaimDiscipline.LEASED_JOB,
            tables=(str(queue_table),),
            required_before_payload_load=True,
        )
    else:
        claim = ClaimContract(
            discipline=ClaimDiscipline.SCHEDULED_PROVIDER if uses_provider_io else ClaimDiscipline.NONE
        )

    provider_io = ProviderIOContract(
        allowed=uses_provider_io,
        forbid_inside_db_transaction=True,
        requires_bounded_batch=True,
    )

    current_read_model = None
    if writes_read_models:
        current_read_model = CurrentReadModelContract(
            tables=writes_read_models,
            table_identities=current_read_model_identities,
        )

    agent_side_effect = None
    if side_effect_ledgers:
        agent_side_effect = AgentSideEffectContract(ledgers=side_effect_ledgers)

    return WorkerSpaceContract(
        worker_name=str(manifest.name),
        claim=claim,
        provider_io=provider_io,
        current_read_model=current_read_model,
        agent_side_effect=agent_side_effect,
        advisory_lock_key=getattr(manifest, "advisory_lock_key", None),
    )


def contracts_from_manifests(manifests: Sequence[Any]) -> tuple[WorkerSpaceContract, ...]:
    return tuple(contract_from_manifest(manifest) for manifest in manifests)
