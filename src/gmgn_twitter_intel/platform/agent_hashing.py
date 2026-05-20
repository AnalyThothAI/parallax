from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def _json_ready(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _json_ready(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_json_ready(child) for child in value]
    if isinstance(value, tuple):
        return [_json_ready(child) for child in value]
    return value


def json_sha256(value: Any) -> str:
    data = json.dumps(_json_ready(value), ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def text_sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def trace_id_for(value: Any, *, length: int = 32) -> str:
    digest = hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()
    return "trace_" + digest[: max(8, int(length))]


def artifact_hash_for(
    *,
    model: str,
    prompt_version: str,
    schema_version: str,
    runtime_version: str,
    output_schema_hash: str,
    provider_family: str = "openai_compatible",
    output_strategy: str = "json_schema",
    schema_enforcement: str = "provider",
) -> str:
    return json_sha256(
        {
            "model": model,
            "provider_family": provider_family,
            "output_strategy": output_strategy,
            "schema_enforcement": schema_enforcement,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "runtime_version": runtime_version,
            "output_schema_hash": output_schema_hash,
        }
    )


__all__ = ["artifact_hash_for", "json_sha256", "text_sha256", "trace_id_for"]
