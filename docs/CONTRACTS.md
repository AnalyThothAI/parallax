# Public Contracts

> **Scope.** Owns the user-visible surfaces (config, WebSocket, HTTP, CLI) and the immutability discipline that protects them. Refactors must preserve these contracts; behaviour changes require a versioned spec under `docs/superpowers/specs/active/`.

These surfaces change only with a versioned spec — refactors must preserve them.

## Config (`~/.gmgn-twitter-intel/config.yaml`)

The only application config source.

- `handles` — watched Twitter handles.
- `ws_token` — public WebSocket API token.
- `api` — FastAPI bind address and replay settings.
- `storage.postgres` — DSN, password file, pool, timeout.
- `llm.openai_api_key` / `llm.openai_model` — optional, only for watched-account social-event extraction.
- Optional market-related groups (OKX, GMGN OpenAPI) for the asset / price pipelines.

## WebSocket at `/ws`

- Auth: `{"type":"auth","token":"..."}`
- Subscribe: `{"type":"subscribe","handles":[...],"replay":N}`
- Push payloads include `event`, `entities`, `alerts`, `enrichment`, and harness updates after store commit.

## HTTP

`/healthz`, `/readyz`, `/api/*`. Each endpoint owns its own response schema.

## CLI

`gmgn-twitter-intel <verb>` plus the `db` and `ops` subcommand groups. The `--help` output is the source of truth — do not enumerate verbs in this document.

## `score_version` discipline

`score_version` is bumped on any scoring change. Downstream evaluation services filter by version, otherwise A/B comparisons silently mix populations. Every ranking score returned by the API includes its component breakdown. No black-box scores.

## Privacy boundary

GMGN chains, channels, app versions, and protocol frames are internal collector strategy — never expose them in user-facing payloads.
