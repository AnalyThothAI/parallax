# Security

> **Scope.** Owns secret handling, supported config-source rules, and the change-confirmation requirement for sensitive subsystems. Operational invariants live in `RELIABILITY.md`.

## Secrets

- Never print or log secrets, tokens, cookies, or `.env` values.
- Never commit `.env`, credentials, private keys, or generated config files.
- When validating live data, use `uv run parallax config` for
  redacted config-path and configured-status diagnostics. Do not paste or copy
  provider keys from `~/.parallax/config.yaml` into chat, docs, tests,
  shell history, or source files.

## Single config source boundaries

The supported operator-owned config files are
`~/.parallax/config.yaml` and
`~/.parallax/workers.yaml`. `config.yaml` owns application,
provider, credential, storage, API, and public-surface settings.
`workers.yaml` owns worker runtime knobs such as enabled state,
intervals, batches, concurrency, leases, attempts, timeouts, advisory
locks, wake channels, and worker gates.

Do not introduce a third config path, shadow config in environment
variables, or duplicate worker runtime knobs under `config.yaml`.
Schemas and public config contracts live in `CONTRACTS.md`.

## Sensitive change confirmation

Ask before changing authentication, authorisation, billing, or data-deletion behaviour.

## Frontend WebSocket token

The `ws_token` reaches the browser through the same config schema. Do not embed it in committed source; the frontend reads it from the page bootstrap injected by `api/`.
