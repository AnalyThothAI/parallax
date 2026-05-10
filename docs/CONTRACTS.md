# Public Contracts

> **Scope.** Owns the user-visible surfaces (config, WebSocket, HTTP, CLI) and the immutability discipline that protects them. Refactors must preserve these contracts; behaviour changes require a versioned spec under `docs/superpowers/specs/active/`.

These surfaces change only with a versioned spec — refactors must preserve them.

## Config (`~/.gmgn-twitter-intel/config.yaml`)

The only application config source.

- `handles` — watched Twitter handles.
- `ws_token` — public WebSocket API token.
- `api` — FastAPI bind address and replay settings.
- `storage.postgres` — DSN, password file, pool, timeout.
- `llm.api_key` / `llm.model` — optional, for watched-account social-event extraction.
- `llm.pulse_agent_*` — optional Signal Pulse recommendation worker config. Current gate knobs are:
  `pulse_agent_trigger_min_rank_score`, `pulse_agent_gate_trade_candidate_min`,
  `pulse_agent_gate_token_watch_min`,
  `pulse_agent_gate_high_info_rejection_min`, and
  `pulse_agent_gate_high_conviction_min`. Older heat / quality / propagation /
  tradeability / timing Pulse threshold keys are rejected.
- Optional market-related groups (OKX, GMGN OpenAPI) for the asset / price pipelines.

## WebSocket at `/ws`

- Auth: `{"type":"auth","token":"..."}`
- Subscribe: `{"type":"subscribe","handles":[...],"replay":N}`
- Push payloads include `event`, `entities`, `alerts`, `enrichment`, and harness updates after store commit.

## HTTP

`/healthz`, `/readyz`, `/api/*`. Each endpoint owns its own response schema.

## CLI

`gmgn-twitter-intel <verb>` plus the `db` and `ops` subcommand groups. The `--help` output is the source of truth — do not enumerate verbs in this document.

## Token Radar Factor Snapshot Discipline

`projection_version` and `factor_version` are bumped on any Token Radar factor
or ranking-contract change. Current runtime explanations come from
`factor_snapshot_json`; public Signal Pulse payloads expose `factor_snapshot`,
`agent_recommendation`, `gate`, and `fact_card`, not old score/thesis JSON
fields. Downstream evaluation services filter by version, otherwise A/B
comparisons silently mix populations. No black-box scores.

## Privacy boundary

GMGN chains, channels, app versions, and protocol frames are internal collector strategy — never expose them in user-facing payloads.
