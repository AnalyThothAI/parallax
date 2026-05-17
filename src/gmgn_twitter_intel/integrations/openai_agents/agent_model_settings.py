from __future__ import annotations

from agents import ModelRetrySettings, ModelSettings, retry_policies


def default_agent_model_settings(
    *,
    disable_thinking: bool = True,
    include_usage: bool = True,
) -> ModelSettings:
    extra_body = None
    if disable_thinking:
        extra_body = {"chat_template_kwargs": {"enable_thinking": False}}
    return ModelSettings(
        retry=ModelRetrySettings(
            max_retries=2,
            backoff={"initial_delay": 0.5, "max_delay": 4.0, "multiplier": 2.0, "jitter": True},
            policy=retry_policies.any(
                retry_policies.provider_suggested(),
                retry_policies.retry_after(),
                retry_policies.network_error(),
                retry_policies.http_status([408, 409, 429, 500, 502, 503, 504]),
            ),
        ),
        extra_body=extra_body,
        include_usage=include_usage,
    )


__all__ = ["default_agent_model_settings"]
