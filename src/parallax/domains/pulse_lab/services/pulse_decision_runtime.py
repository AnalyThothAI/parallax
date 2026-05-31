from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from parallax.domains.pulse_lab.interfaces import (
    BACKEND,
    PULSE_DECISION_PROMPT_VERSION,
    PULSE_DECISION_SCHEMA_VERSION,
)
from parallax.domains.pulse_lab.providers import (
    BearCaseMemo,
    EvidenceCompletenessGateResult,
    PulseDecisionStageSpec,
    PulseEvidencePacket,
    SignalAnalystMemo,
)
from parallax.domains.pulse_lab.queries.agent_tool_queries import fetch_evidence_event_urls
from parallax.domains.pulse_lab.services.agent_output_normalization import normalize_pulse_stage_output
from parallax.domains.pulse_lab.services.agent_runtime import pulse_runtime_hash
from parallax.domains.pulse_lab.services.prompt_loader import (
    load_bear_case_prompt,
    load_risk_portfolio_judge_prompt,
    load_signal_analyst_prompt,
)
from parallax.domains.pulse_lab.types.agent_decision import (
    DecisionRoute,
    FinalDecision,
    StageRunAudit,
)


@dataclass(frozen=True, slots=True)
class PulseDecisionRuntimeService:
    db_pool: Any

    def signal_analyst_stage_spec(
        self,
        *,
        route: DecisionRoute,
        evidence_packet: PulseEvidencePacket,
        evidence_gate: EvidenceCompletenessGateResult,
    ) -> PulseDecisionStageSpec:
        packet_payload = _agent_packet_payload(evidence_packet)
        gate_payload = _model_payload(evidence_gate)
        return PulseDecisionStageSpec(
            stage="signal_analyst",
            prompt_text=load_signal_analyst_prompt(route),
            input_payload={
                "route": route,
                "evidence_packet": packet_payload,
                "evidence_gate": gate_payload,
                "source_quality_summary": _source_quality_summary(packet_payload),
                "evidence_packet_hash": _packet_hash(packet_payload),
                "allowed_evidence_refs": _allowed_evidence_refs(packet_payload),
                "allowed_evidence_ref_ids": _sorted_ref_ids(_allowed_evidence_ref_ids(packet_payload)),
                "evidence_ref_policy": _evidence_ref_policy(),
            },
        )

    def bear_case_stage_spec(
        self,
        *,
        route: DecisionRoute,
        evidence_packet: PulseEvidencePacket,
        evidence_gate: EvidenceCompletenessGateResult,
        signal_memo: SignalAnalystMemo,
    ) -> PulseDecisionStageSpec:
        packet_payload = _agent_packet_payload(evidence_packet)
        gate_payload = _model_payload(evidence_gate)
        signal_payload = _model_payload(signal_memo)
        return PulseDecisionStageSpec(
            stage="bear_case",
            prompt_text=load_bear_case_prompt(route),
            input_payload={
                "route": route,
                "evidence_packet": packet_payload,
                "evidence_gate": gate_payload,
                "signal_memo": signal_payload,
                "evidence_packet_hash": _packet_hash(packet_payload),
                "allowed_evidence_refs": _allowed_evidence_refs(packet_payload),
                "allowed_evidence_ref_ids": _sorted_ref_ids(_allowed_evidence_ref_ids(packet_payload)),
                "evidence_ref_policy": _evidence_ref_policy(),
            },
        )

    def risk_portfolio_judge_stage_spec(
        self,
        *,
        route: DecisionRoute,
        evidence_packet: PulseEvidencePacket,
        evidence_gate: EvidenceCompletenessGateResult,
        signal_memo: SignalAnalystMemo,
        bear_memo: BearCaseMemo,
        recommendation_constraints: dict[str, Any],
    ) -> PulseDecisionStageSpec:
        packet_payload = _agent_packet_payload(evidence_packet)
        gate_payload = _model_payload(evidence_gate)
        signal_payload = _model_payload(signal_memo)
        bear_payload = _model_payload(bear_memo)
        return PulseDecisionStageSpec(
            stage="risk_portfolio_judge",
            prompt_text=load_risk_portfolio_judge_prompt(route),
            input_payload={
                "route": route,
                "evidence_packet": packet_payload,
                "evidence_gate": gate_payload,
                "signal_memo": signal_payload,
                "bear_memo": bear_payload,
                "recommendation_constraints": dict(recommendation_constraints or {}),
                "evidence_packet_hash": _packet_hash(packet_payload),
                "allowed_evidence_refs": _allowed_evidence_refs(packet_payload),
                "allowed_evidence_ref_ids": _sorted_ref_ids(_allowed_evidence_ref_ids(packet_payload)),
                "evidence_ref_policy": _evidence_ref_policy(),
            },
        )

    def validate_signal_refs(
        self,
        signal_memo: SignalAnalystMemo,
        *,
        evidence_packet: PulseEvidencePacket,
    ) -> None:
        packet_payload = _model_payload(evidence_packet)
        allowed = _allowed_evidence_ref_ids(packet_payload)
        unknown = sorted(_memo_ref_ids(_model_payload(signal_memo), groups=("bull_claims",)) - allowed)
        if unknown:
            preview = unknown[:5]
            suffix = "..." if len(unknown) > 5 else ""
            raise ValueError(f"SignalAnalystMemo cites refs outside allowed_evidence_refs: {preview}{suffix}")

    def validate_bear_refs(
        self,
        bear_memo: BearCaseMemo,
        *,
        evidence_packet: PulseEvidencePacket,
    ) -> None:
        packet_payload = _model_payload(evidence_packet)
        allowed = _allowed_evidence_ref_ids(packet_payload)
        unknown = sorted(
            _memo_ref_ids(_model_payload(bear_memo), groups=("risk_claims", "missing_fact_impacts")) - allowed
        )
        if unknown:
            preview = unknown[:5]
            suffix = "..." if len(unknown) > 5 else ""
            raise ValueError(f"BearCaseMemo cites refs outside allowed_evidence_refs: {preview}{suffix}")

    def validate_final_evidence_refs(
        self,
        final: FinalDecision,
        *,
        evidence_packet: PulseEvidencePacket,
        signal_memo: SignalAnalystMemo,
        bear_memo: BearCaseMemo,
    ) -> None:
        packet_payload = _model_payload(evidence_packet)
        allowed_refs = _allowed_evidence_ref_ids(packet_payload)
        allowed_events = _packet_event_ids(packet_payload)
        memo_refs = _memo_ref_ids(_model_payload(signal_memo), groups=("bull_claims",)) | _memo_ref_ids(
            _model_payload(bear_memo),
            groups=("risk_claims", "missing_fact_impacts"),
        )
        fields = _final_ref_fields(final)
        for field_name, values in fields:
            allowed = allowed_events if field_name.endswith("event_ids") else (allowed_refs | memo_refs)
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
        evidence_packet: Any,
    ) -> Any:
        return normalize_pulse_stage_output(
            output_type=output_type,
            raw_output=raw_output,
            evidence_packet=evidence_packet,
        )

    def enrich_evidence_urls(self, final: FinalDecision) -> FinalDecision:
        event_ids = _final_url_event_ids(final)
        if not event_ids:
            return final.model_copy(update={"evidence_event_urls": {}})
        urls = fetch_evidence_event_urls(self.db_pool, event_ids=event_ids)
        return final.model_copy(update={"evidence_event_urls": urls})

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
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
        model: str,
        artifact_version_hash: str,
        workflow_name: str,
        agent_name: str,
    ) -> dict[str, Any]:
        packet_payload = _context_packet_payload(context)
        evidence_packet_hash = _packet_hash(packet_payload) if packet_payload else None
        input_hash = _sha256(
            {"evidence_packet": packet_payload or context, "route": route, "evidence_gate": completeness}
        )
        runtime_hash = pulse_runtime_hash(runtime_manifest)
        trace_metadata = {
            "backend": BACKEND,
            "run_id": str(run_id or ""),
            "job_id": str(job.get("job_id") or ""),
            "attempt_count": int(job.get("attempt_count") or 0),
            "prompt_version": PULSE_DECISION_PROMPT_VERSION,
            "schema_version": PULSE_DECISION_SCHEMA_VERSION,
            "model": str(model or ""),
            "artifact_version_hash": artifact_version_hash,
            "input_hash": input_hash,
            "runtime_version": str(runtime_manifest.get("runtime_version") or ""),
            "runtime_hash": runtime_hash,
            "candidate_id": _context_string(context, "candidate_id"),
            "candidate_type": _context_string(context, "candidate_type"),
            "subject_key": _context_string(context, "subject_key"),
            "target_type": _context_string(context, "target_type"),
            "target_id": _context_string(context, "target_id"),
            "route": route,
            "evidence_gate": completeness,
            "evidence_packet_hash": evidence_packet_hash,
            "evidence_packet_schema_version": _packet_schema_version(packet_payload),
        }
        return {
            "backend": BACKEND,
            "execution_trace_id": _trace_id(run_id),
            "workflow_name": str(workflow_name or ""),
            "agent_name": str(agent_name or ""),
            "prompt_version": PULSE_DECISION_PROMPT_VERSION,
            "schema_version": PULSE_DECISION_SCHEMA_VERSION,
            "artifact_version_hash": artifact_version_hash,
            "trace_metadata": trace_metadata,
            "input_hash": input_hash,
            "runtime_version": str(runtime_manifest.get("runtime_version") or ""),
            "runtime_hash": runtime_hash,
            "runtime_manifest": runtime_manifest,
        }

    def with_output_hash(self, audit: dict[str, Any], *, final: FinalDecision) -> dict[str, Any]:
        return {**audit, "output_hash": _sha256(final.model_dump(mode="json"))}


def _model_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json")
        return payload if isinstance(payload, dict) else {}
    return {}


def _agent_packet_payload(value: Any) -> dict[str, Any]:
    payload = _model_payload(value)
    if not payload and isinstance(value, dict):
        payload = dict(value)
    if not payload:
        return {}
    return {
        key: item
        for key, item in payload.items()
        if key
        not in {
            "summary_json",
            "admission_context",
        }
    }


def _context_packet_payload(context: dict[str, Any]) -> dict[str, Any]:
    packet = context.get("evidence_packet") if isinstance(context, dict) else None
    if isinstance(packet, dict):
        return dict(packet)
    packet_payload = _model_payload(packet)
    if packet_payload:
        return packet_payload
    return dict(context) if isinstance(context, dict) and context.get("evidence_packet_hash") else {}


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
        ref_payload = _model_payload(ref)
        if not ref_payload and isinstance(ref, dict):
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


def _memo_ref_ids(memo_payload: dict[str, Any], *, groups: tuple[str, ...]) -> set[str]:
    refs: set[str] = set()
    for key in groups:
        claims = memo_payload.get(key)
        if not isinstance(claims, list | tuple):
            continue
        for claim in claims:
            claim_payload = _model_payload(claim)
            values = claim_payload.get("evidence_refs") if claim_payload else None
            if isinstance(values, list | tuple):
                for value in values:
                    ref_id = _string_value(value)
                    if not ref_id:
                        continue
                    if ref_id.startswith("missing:"):
                        continue
                    refs.add(ref_id)
    return refs


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


def _final_url_event_ids(final: FinalDecision) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in (
        *final.evidence_event_ids,
        *final.bull_view.supporting_event_ids,
        *final.bear_view.supporting_event_ids,
    ):
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


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
    digest = hashlib.sha256(str(run_id or "").encode("utf-8")).hexdigest()[:24]
    return f"trace_{digest}"


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


__all__ = ["PulseDecisionRuntimeService"]
