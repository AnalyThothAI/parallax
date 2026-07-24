from __future__ import annotations

from langchain_litellm import ChatLiteLLM
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from parallax.app.runtime.worker_factories import WorkerFactoryContext, disabled_worker, unavailable_worker
from parallax.domains.macro_intel.repositories.macro_research_repository import (
    PostgresMacroResearchReadPort,
)
from parallax.domains.macro_intel.runtime.macro_research_worker import MacroResearchWorker
from parallax.domains.macro_intel.runtime.macro_sync_worker import MacroSyncWorker
from parallax.domains.macro_intel.services.completed_session_macro import (
    CompletedSessionMacro,
)
from parallax.integrations.macrodata.runner import MacrodataBundleRunner
from parallax.integrations.model_execution.macro_research_deepagent import (
    MacroResearchDeepAgent,
)
from parallax.platform.db.postgres_client import (
    local_docker_host_dsn,
    with_password_from_file,
)
from parallax.platform.runtime.worker_base import WorkerBase


def construct_macro_intel_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    constructed: dict[str, WorkerBase] = {}
    workers = ctx.settings.workers
    if not workers.macro_sync.enabled:
        constructed["macro_sync"] = disabled_worker(ctx, "macro_sync")
    elif ctx.settings.providers.macrodata.enabled:
        worker_name = "macro_sync"
        constructed[worker_name] = MacroSyncWorker(
            name=worker_name,
            settings=workers.macro_sync,
            db=ctx.db,
            telemetry=ctx.telemetry,
            settings_root=ctx.settings,
            runner=MacrodataBundleRunner(settings=ctx.settings),
        )
    else:
        constructed["macro_sync"] = disabled_worker(ctx, "macro_sync")
    if not workers.macro_research.enabled:
        constructed["macro_research"] = disabled_worker(ctx, "macro_research")
    elif not ctx.settings.llm.api_key or not ctx.settings.llm.base_url:
        constructed["macro_research"] = unavailable_worker(
            ctx,
            "macro_research",
            "llm_not_configured",
        )
    else:
        worker_name = "macro_research"
        research_settings = workers.macro_research
        effective_model = _litellm_proxy_model_name(
            research_settings.model,
            base_url=ctx.settings.llm.base_url,
        )
        model = ChatLiteLLM(
            model=effective_model,
            api_key=ctx.settings.llm.api_key,
            api_base=ctx.settings.llm.base_url,
            temperature=0,
            max_tokens=research_settings.max_tokens,
            max_retries=0,
            request_timeout=research_settings.model_request_timeout_seconds,
        )
        reader = PostgresMacroResearchReadPort(
            db=ctx.db,
            worker_name=worker_name,
            statement_timeout_seconds=research_settings.statement_timeout_seconds,
        )
        checkpoint_dsn = _checkpoint_dsn(ctx)
        agent = MacroResearchDeepAgent(
            model=model,
            model_name=effective_model,
            reader=reader,
            checkpointer_context_factory=lambda: AsyncPostgresSaver.from_conn_string(
                checkpoint_dsn,
            ),
            workspace_root=ctx.settings.app_home / "macro-agent-workspaces",
        )
        completed_session_macro = CompletedSessionMacro(
            db=ctx.db,
            settings=research_settings,
            agent=agent,
            worker_name=worker_name,
        )
        constructed[worker_name] = MacroResearchWorker(
            name=worker_name,
            settings=research_settings,
            db=ctx.db,
            telemetry=ctx.telemetry,
            completed_session_macro=completed_session_macro,
        )
    return constructed


def _litellm_proxy_model_name(model_name: str, *, base_url: str) -> str:
    normalized = str(model_name or "").strip()
    if "/" in normalized or not str(base_url or "").strip():
        return normalized
    return f"openai/{normalized}"


def _checkpoint_dsn(ctx: WorkerFactoryContext) -> str:
    postgres = ctx.settings.storage.postgres
    return local_docker_host_dsn(
        with_password_from_file(
            postgres.dsn,
            ctx.settings.postgres_password_file,
        )
    )


__all__ = ["construct_macro_intel_workers"]
