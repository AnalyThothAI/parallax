from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from parallax.domains.pulse_lab.interfaces import (
    BACKEND,
    PULSE_DECISION_PROMPT_VERSION,
    PULSE_DECISION_SCHEMA_VERSION,
)
from parallax.domains.pulse_lab.providers import (
    EvidenceCompletenessGateResult,
    PulseDecisionStageSpec,
    PulseEvidencePacket,
)
from parallax.domains.pulse_lab.services.agent_output_normalization import normalize_pulse_stage_output
from parallax.domains.pulse_lab.services.agent_runtime import pulse_runtime_hash
from parallax.domains.pulse_lab.services.prompt_loader import (
    PULSE_DECISION_KNOWLEDGE_REFS,
    PULSE_DECISION_READ_ONLY_TOOL_REFS,
    load_pulse_decision_prompt,
    pulse_decision_prompt_text_hash,
)
from parallax.domains.pulse_lab.types.agent_decision import (
    DecisionRoute,
    FinalDecision,
    StageRunAudit,
)


@dataclass(frozen=True, slots=True)
class PulseDecisionRuntimeService:
    def prompt_text_hash(self) -> str:
        return pulse_decision_prompt_text_hash()

    def pulse_decision_stage_spec(
        self,
        *,
        route: DecisionRoute,
        evidence_packet: PulseEvidencePacket,
        evidence_gate: EvidenceCompletenessGateResult,
        recommendation_constraints: dict[str, Any],
    ) -> PulseDecisionStageSpec:
        if not isinstance(evidence_packet, PulseEvidencePacket):
            raise TypeError(
                "pulse_decision_stage_packet_contract_required: "
                f"expected PulseEvidencePacket, got {type(evidence_packet).__name__}"
            )
        if not isinstance(evidence_gate, EvidenceCompletenessGateResult):
            raise TypeError(
                "pulse_decision_stage_gate_contract_required: "
                f"expected EvidenceCompletenessGateResult, got {type(evidence_gate).__name__}"
            )
        packet_payload = _agent_packet_payload(evidence_packet)
        gate_payload = evidence_gate.to_json()
        return PulseDecisionStageSpec(
            stage="pulse_decision",
            prompt_text=load_pulse_decision_prompt(route),
            input_payload={
                "route": route,
                "evidence_packet": packet_payload,
                "evidence_gate": gate_payload,
                "recommendation_constraints": dict(recommendation_constraints or {}),
                "source_quality_summary": _source_quality_summary(packet_payload),
                "evidence_packet_hash": _packet_hash(packet_payload),
                "allowed_evidence_refs": _allowed_evidence_refs(packet_payload),
                "allowed_evidence_ref_ids": _sorted_ref_ids(_allowed_evidence_ref_ids(packet_payload)),
                "evidence_ref_policy": _evidence_ref_policy(),
            },
            knowledge_refs=PULSE_DECISION_KNOWLEDGE_REFS,
            read_only_tool_refs=PULSE_DECISION_READ_ONLY_TOOL_REFS,
        )

    def validate_final_evidence_refs(
        self,
        final: FinalDecision,
        *,
        evidence_packet: PulseEvidencePacket,
    ) -> None:
        packet_payload = _agent_packet_payload(evidence_packet)
        allowed_refs = _allowed_evidence_ref_ids(packet_payload)
        allowed_events = _packet_event_ids(packet_payload)
        fields = _final_ref_fields(final)
        for field_name, values in fields:
            allowed = allowed_events if field_name.endswith("event_ids") else allowed_refs
            unknown = [
                ref_id
                for ref_id in values
                if ref_id not in allowed and not (field_name == "data_gap_refs" and ref_id.startswith("missing:"))
            ]
            if unknown:
                preview = unknown[:5]
                suffix = "..." if len(unknown) > 5 else ""
                raise ValueError(f"{field_name} contains refs outside allowed_evidence_refs: {preview}{suffix}")

    def normalize_stage_output(
        self,
        *,
        output_type: type[Any],
        raw_output: Any,
        evidence_packet: PulseEvidencePacket,
    ) -> Any:
        return normalize_pulse_stage_output(
            output_type=output_type,
            raw_output=raw_output,
            evidence_packet=evidence_packet,
        )

    def mark_step_failed(self, step: StageRunAudit, *, error: str) -> StageRunAudit:
        return step.model_copy(
            update={
                "status": "failed",
                "error": error[:1000],
                "response_json": step.response_json,
            }
        )

    def request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: EvidenceCompletenessGateResult,
        runtime_manifest: dict[str, Any],
        model: str,
        artifact_version_hash: str,
        workflow_name: str,
        agent_name: str,
    ) -> dict[str, Any]:
        evidence_packet = _context_evidence_packet(context)
        if not isinstance(completeness, EvidenceCompletenessGateResult):
            raise TypeError(
                "pulse_decision_request_audit_gate_contract_required: "
                f"expected EvidenceCompletenessGateResult, got {type(completeness).__name__}"
            )
        packet_payload = _agent_packet_payload(evidence_packet)
        gate_payload = completeness.to_json()
        evidence_packet_hash = _packet_hash(packet_payload)
        input_hash = _sha256({"evidence_packet": packet_payload, "route": route, "evidence_gate": gate_payload})
        run_id_value = _required_request_audit_text(run_id, "pulse_decision_request_audit_run_id_required")
        try:
            job_id = _required_request_audit_text(job["job_id"], "pulse_decision_request_audit_job_id_required")
        except KeyError as exc:
            raise ValueError("pulse_decision_request_audit_job_id_required") from exc
        model_value = _required_request_audit_text(model, "pulse_decision_request_audit_model_required")
        artifact_hash = _required_request_audit_text(
            artifact_version_hash,
            "pulse_decision_request_audit_artifact_version_hash_required",
        )
        runtime_version = _runtime_manifest_version(runtime_manifest)
        runtime_model, runtime_artifact_hash = _runtime_manifest_model_identity(runtime_manifest)
        if runtime_model != model_value:
            raise ValueError("pulse_decision_runtime_manifest_model_mismatch")
        if runtime_artifact_hash != artifact_hash:
            raise ValueError("pulse_decision_runtime_manifest_artifact_version_hash_mismatch")
        workflow = _required_request_audit_text(workflow_name, "pulse_decision_request_audit_workflow_name_required")
        agent = _required_request_audit_text(agent_name, "pulse_decision_request_audit_agent_name_required")
        runtime_hash = pulse_runtime_hash(runtime_manifest)
        trace_metadata = {
            "backend": BACKEND,
            "run_id": run_id_value,
            "job_id": job_id,
            "attempt_count": _pulse_job_claim_attempt_count(job),
            "prompt_version": PULSE_DECISION_PROMPT_VERSION,
            "schema_version": PULSE_DECISION_SCHEMA_VERSION,
            "model": model_value,
            "artifact_version_hash": artifact_hash,
            "input_hash": input_hash,
            "runtime_version": runtime_version,
            "runtime_hash": runtime_hash,
            "candidate_id": _context_string(context, "candidate_id"),
            "candidate_type": _context_string(context, "candidate_type"),
            "subject_key": _context_string(context, "subject_key"),
            "target_type": _context_string(context, "target_type"),
            "target_id": _context_string(context, "target_id"),
            "route": route,
            "evidence_gate": gate_payload,
            "evidence_packet_hash": evidence_packet_hash,
            "evidence_packet_schema_version": _packet_schema_version(packet_payload),
        }
        return {
            "backend": BACKEND,
            "execution_trace_id": _trace_id(run_id_value),
            "workflow_name": workflow,
            "agent_name": agent,
            "prompt_version": PULSE_DECISION_PROMPT_VERSION,
            "schema_version": PULSE_DECISION_SCHEMA_VERSION,
            "artifact_version_hash": artifact_hash,
            "trace_metadata": trace_metadata,
            "input_hash": input_hash,
            "runtime_version": runtime_version,
            "runtime_hash": runtime_hash,
            "runtime_manifest": runtime_manifest,
        }

    def with_output_hash(self, audit: dict[str, Any], *, final: FinalDecision) -> dict[str, Any]:
        return {**audit, "output_hash": _sha256(final.model_dump(mode="json"))}


def _pulse_job_claim_attempt_count(job: Mapping[str, Any]) -> int:
    try:
        attempt_count = int(job["attempt_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("pulse_agent_job_claim_attempt_count_required") from exc
    if attempt_count <= 0:
        raise ValueError("pulse_agent_job_claim_attempt_count_required")
    return attempt_count


def _runtime_manifest_version(runtime_manifest: Mapping[str, Any]) -> str:
    try:
        runtime_version = str(runtime_manifest["runtime_version"]).strip()
    except (KeyError, TypeError) as exc:
        raise ValueError("pulse_decision_runtime_manifest_version_required") from exc
    if not runtime_version:
        raise ValueError("pulse_decision_runtime_manifest_version_required")
    return runtime_version


def _runtime_manifest_model_identity(runtime_manifest: Mapping[str, Any]) -> tuple[str, str]:
    try:
        model_payload = runtime_manifest["model"]
    except (KeyError, TypeError) as exc:
        raise ValueError("pulse_decision_runtime_manifest_model_required") from exc
    if not isinstance(model_payload, Mapping):
        raise ValueError("pulse_decision_runtime_manifest_model_required")
    try:
        runtime_model = _required_request_audit_text(
            model_payload["model"],
            "pulse_decision_runtime_manifest_model_required",
        )
    except KeyError as exc:
        raise ValueError("pulse_decision_runtime_manifest_model_required") from exc
    try:
        runtime_artifact_hash = _required_request_audit_text(
            model_payload["artifact_version_hash"],
            "pulse_decision_runtime_manifest_artifact_version_hash_required",
        )
    except KeyError as exc:
        raise ValueError("pulse_decision_runtime_manifest_artifact_version_hash_required") from exc
    return runtime_model, runtime_artifact_hash


def _required_request_audit_text(value: Any, error_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(error_name)
    return text


def _agent_packet_payload(packet: PulseEvidencePacket) -> dict[str, Any]:
    payload = packet.model_dump(mode="json", exclude={"summary_json", "admission_context"})
    return {
        key: item
        for key, item in payload.items()
        if key
        not in {
            "summary_json",
            "admission_context",
        }
    }


def _context_evidence_packet(context: dict[str, Any]) -> PulseEvidencePacket:
    packet = context.get("evidence_packet") if isinstance(context, dict) else None
    if not isinstance(packet, dict):
        raise ValueError("pulse_decision_request_audit_packet_contract_required")
    try:
        return PulseEvidencePacket.model_validate(packet)
    except ValueError as exc:
        raise ValueError("pulse_decision_request_audit_packet_contract_required") from exc


def _packet_hash(packet_payload: dict[str, Any]) -> str:
    return _string_value(packet_payload.get("evidence_packet_hash"))


def _packet_schema_version(packet_payload: dict[str, Any]) -> str | None:
    value = _string_value(packet_payload.get("schema_version"))
    return value or None


def _allowed_evidence_refs(packet_payload: dict[str, Any]) -> list[dict[str, Any]]:
    refs = packet_payload.get("allowed_evidence_refs")
    if not isinstance(refs, list | tuple):
        return []
    result: list[dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        ref_payload = dict(ref)
        if _string_value(ref_payload.get("ref_id")):
            result.append(ref_payload)
    return result


def _allowed_evidence_ref_ids(packet_payload: dict[str, Any]) -> set[str]:
    return {_string_value(ref.get("ref_id")) for ref in _allowed_evidence_refs(packet_payload) if ref.get("ref_id")}


def _packet_event_ids(packet_payload: dict[str, Any]) -> set[str]:
    values = packet_payload.get("source_event_ids")
    result = (
        {_string_value(value) for value in values if _string_value(value)}
        if isinstance(values, list | tuple)
        else set()
    )
    for ref_id in _allowed_evidence_ref_ids(packet_payload):
        if ref_id.startswith("event:"):
            result.add(ref_id.removeprefix("event:"))
    return result


def _sorted_ref_ids(values: set[str]) -> list[str]:
    return sorted(value for value in values if value)


def _evidence_ref_policy() -> dict[str, str]:
    return {
        "copy_only_from": "allowed_evidence_refs.ref_id",
        "do_not": "invent, shorten, paraphrase, repair, or transform evidence refs",
        "when_fact_absent": "declare a data gap and lower confidence or abstain",
    }


def _source_quality_summary(packet_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "window": packet_payload.get("window"),
        "scope": packet_payload.get("scope"),
        "social_evidence": _mapping(packet_payload.get("social_evidence")),
        "quality_metrics": _mapping(packet_payload.get("quality_metrics")),
        "risk_flags": packet_payload.get("risk_flags") if isinstance(packet_payload.get("risk_flags"), list) else [],
        "data_gaps": packet_payload.get("data_gaps") if isinstance(packet_payload.get("data_gaps"), list) else [],
    }


def _final_ref_fields(final: FinalDecision) -> tuple[tuple[str, list[str]], ...]:
    payload = final.model_dump(mode="json")
    fields: list[tuple[str, list[str]]] = []
    for key in ("supporting_evidence_refs", "risk_evidence_refs", "data_gap_refs"):
        values = payload.get(key)
        if isinstance(values, list | tuple):
            fields.append((key, [_string_value(value) for value in values if _string_value(value)]))
    fields.append(
        ("evidence_event_ids", [_string_value(value) for value in final.evidence_event_ids if _string_value(value)])
    )
    return tuple(fields)


def _context_string(context: dict[str, Any], key: str) -> str | None:
    value = context.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_value(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _trace_id(run_id: str) -> str:
    digest = hashlib.sha256(str(run_id).encode("utf-8")).hexdigest()[:24]
    return f"trace_{digest}"


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


__all__ = ["PulseDecisionRuntimeService"]
