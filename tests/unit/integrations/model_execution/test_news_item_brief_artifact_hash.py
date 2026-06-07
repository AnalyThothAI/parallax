from __future__ import annotations

from parallax.platform.agent_hashing import artifact_hash_for, json_sha256


def _artifact_hash(*, prompt_text_hash: str) -> str:
    return artifact_hash_for(
        model="gpt-news",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        runtime_version="runtime-v1",
        output_schema_hash="sha256:schema",
        prompt_text_hash=prompt_text_hash,
    )


def test_artifact_hash_changes_when_prompt_text_hash_changes() -> None:
    assert _artifact_hash(prompt_text_hash="sha256:prompt-a") != _artifact_hash(prompt_text_hash="sha256:prompt-b")


def test_artifact_hash_without_prompt_text_hash_preserves_legacy_payload_shape() -> None:
    expected = json_sha256(
        {
            "model": "gpt-news",
            "provider_family": "litellm",
            "output_strategy": "json_object",
            "schema_enforcement": "client_validate",
            "request_options_hash": json_sha256({}),
            "prompt_version": "prompt-v1",
            "schema_version": "schema-v1",
            "runtime_version": "runtime-v1",
            "output_schema_hash": "sha256:schema",
        }
    )

    assert (
        artifact_hash_for(
            model="gpt-news",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            runtime_version="runtime-v1",
            output_schema_hash="sha256:schema",
        )
        == expected
    )
