from __future__ import annotations

from pathlib import Path

from parallax.app.runtime.worker_manifest import worker_names
from parallax.platform.config.settings import WorkersSettings

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"


def test_narrative_llm_workers_are_hard_removed_from_runtime_contract() -> None:
    names = set(worker_names())
    settings_fields = set(WorkersSettings.model_fields)
    lanes = set(WorkersSettings().agent_runtime.lanes)

    assert "narrative_admission" in names
    assert "mention_semantics" not in names
    assert "token_discussion_digest" not in names
    assert "mention_semantics" not in settings_fields
    assert "token_discussion_digest" not in settings_fields
    assert "narrative.mention_semantics" not in lanes
    assert "narrative.discussion_digest" not in lanes
    assert {"news.item_brief", "news.story_brief"}.issubset(lanes)


def test_narrative_llm_provider_client_and_prompts_are_removed() -> None:
    model_execution = SRC / "integrations" / "model_execution"
    narrative_domain = SRC / "domains" / "narrative_intel"
    provider_wiring = (SRC / "app" / "runtime" / "provider_wiring" / "__init__.py").read_text(encoding="utf-8")
    model_execution_wiring = (SRC / "app" / "runtime" / "provider_wiring" / "model_execution.py").read_text(
        encoding="utf-8"
    )

    assert not (model_execution / "narrative_intel_agent_client.py").exists()
    assert not (narrative_domain / "prompts" / "mention_semantics.md").exists()
    assert not (narrative_domain / "prompts" / "discussion_digest.md").exists()
    assert "litellm_narrative_intel_provider" not in provider_wiring
    assert "litellm_narrative_intel_provider" not in model_execution_wiring


def test_agent_stage_spec_has_explicit_knowledge_context() -> None:
    from pydantic import BaseModel

    from parallax.platform.agent_execution import AgentStageSpec

    class Payload(BaseModel):
        value: str

    stage = AgentStageSpec(
        lane="news.item_brief",
        stage="news_item_brief",
        instructions="Return JSON.",
        input_payload={"x": 1},
        output_type=Payload,
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        workflow_name="news_item_brief",
        agent_name="NewsItemBriefAgent",
        knowledge_refs=("market_research_harness",),
    )

    assert stage.knowledge_refs == ("market_research_harness",)
