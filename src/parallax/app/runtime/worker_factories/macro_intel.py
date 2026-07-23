from __future__ import annotations

from langchain_litellm import ChatLiteLLM

from parallax.app.runtime.worker_factories import WorkerFactoryContext, disabled_worker, unavailable_worker
from parallax.domains.macro_intel.runtime.daily_macro_judgment_worker import (
    DailyMacroJudgmentWorker,
)
from parallax.domains.macro_intel.runtime.macro_sync_worker import MacroSyncWorker
from parallax.domains.macro_intel.runtime.macro_view_projection_worker import (
    MacroViewProjectionWorker,
)
from parallax.integrations.macrodata.runner import MacrodataBundleRunner
from parallax.integrations.model_execution.macro_judgment_deepagent import MacroJudgmentDeepAgent
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
    if workers.macro_view_projection.enabled:
        worker_name = "macro_view_projection"
        constructed[worker_name] = MacroViewProjectionWorker(
            name=worker_name,
            settings=workers.macro_view_projection,
            db=ctx.db,
            telemetry=ctx.telemetry,
        )
    else:
        constructed["macro_view_projection"] = disabled_worker(ctx, "macro_view_projection")
    if not workers.daily_macro_judgment.enabled:
        constructed["daily_macro_judgment"] = disabled_worker(ctx, "daily_macro_judgment")
    elif not ctx.settings.llm.api_key or not ctx.settings.llm.base_url:
        constructed["daily_macro_judgment"] = unavailable_worker(
            ctx,
            "daily_macro_judgment",
            "llm_not_configured",
        )
    else:
        worker_name = "daily_macro_judgment"
        judgment_settings = workers.daily_macro_judgment
        effective_analyst_model = _litellm_proxy_model_name(
            judgment_settings.analyst_model,
            base_url=ctx.settings.llm.base_url,
        )
        effective_reviewer_model = _litellm_proxy_model_name(
            judgment_settings.reviewer_model,
            base_url=ctx.settings.llm.base_url,
        )
        analyst_model = ChatLiteLLM(
            model=effective_analyst_model,
            api_key=ctx.settings.llm.api_key,
            api_base=ctx.settings.llm.base_url,
            temperature=0,
            max_tokens=judgment_settings.max_tokens,
            max_retries=0,
            request_timeout=judgment_settings.model_timeout_seconds,
        )
        reviewer_model = ChatLiteLLM(
            model=effective_reviewer_model,
            api_key=ctx.settings.llm.api_key,
            api_base=ctx.settings.llm.base_url,
            temperature=0,
            max_tokens=judgment_settings.max_tokens,
            max_retries=0,
            request_timeout=judgment_settings.model_timeout_seconds,
        )
        constructed[worker_name] = DailyMacroJudgmentWorker(
            name=worker_name,
            settings=judgment_settings,
            db=ctx.db,
            telemetry=ctx.telemetry,
            agent=MacroJudgmentDeepAgent(
                model=analyst_model,
                model_name=effective_analyst_model,
                reviewer_model=reviewer_model,
                reviewer_model_name=effective_reviewer_model,
                timeout_seconds=judgment_settings.model_timeout_seconds,
            ),
        )
    return constructed


def _litellm_proxy_model_name(model_name: str, *, base_url: str) -> str:
    normalized = str(model_name or "").strip()
    if "/" in normalized or not str(base_url or "").strip():
        return normalized
    return f"openai/{normalized}"


__all__ = ["construct_macro_intel_workers"]
