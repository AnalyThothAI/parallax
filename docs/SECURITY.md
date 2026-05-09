# Security

> **Scope.** Owns secret handling, the single config source rule, and the change-confirmation requirement for sensitive subsystems. Operational invariants live in `RELIABILITY.md`.

## Secrets

- Never print or log secrets, tokens, cookies, or `.env` values.
- Never commit `.env`, credentials, private keys, or generated config files.

## Single config source

The only application config source is `~/.gmgn-twitter-intel/config.yaml`. Do not invent alternative config paths. The schema lives in `CONTRACTS.md`.

## Sensitive change confirmation

Ask before changing authentication, authorisation, billing, or data-deletion behaviour.

## Frontend WebSocket token

The `ws_token` reaches the browser through the same config schema. Do not embed it in committed source; the frontend reads it from the page bootstrap injected by `api/`.
