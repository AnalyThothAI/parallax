# CLAUDE.md

Guidance for coding agents working in this repository.

## Commands

```bash
uv sync
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
```

Run:

```bash
uv run gmgn-twitter-intel init
uv run gmgn-twitter-intel serve
```

Trader queries:

```bash
uv run gmgn-twitter-intel recent --limit 20
uv run gmgn-twitter-intel search --symbol PEPE --limit 20
uv run gmgn-twitter-intel token-flow --window 5m --limit 20
uv run gmgn-twitter-intel account-alerts --window 24h --limit 50
uv run gmgn-twitter-intel narrative-flow --window 1h --limit 20
uv run gmgn-twitter-intel account-narratives --window 24h --limit 50
```

## Architecture

This repository is a standard `uv + src/` Python service backed by PostgreSQL:

- `src/gmgn_twitter_intel/settings.py`: YAML config loader and typed runtime settings.
- `src/gmgn_twitter_intel/api/app.py`: FastAPI app, `/healthz`, `/readyz`, `/ws`, lifespan background tasks.
- `src/gmgn_twitter_intel/api/ws.py`: authenticated public WebSocket hub.
- `src/gmgn_twitter_intel/collector/direct_ws.py`: GMGN anonymous upstream WebSocket client.
- `src/gmgn_twitter_intel/collector/normalizer.py`: GMGN frame parsing and event normalization.
- `src/gmgn_twitter_intel/collector/service.py`: snapshot gate, handle filtering, store-first publish.
- `src/gmgn_twitter_intel/pipeline/entity_extractor.py`: deterministic entity extraction.
- `src/gmgn_twitter_intel/pipeline/ingest_service.py`: evidence/entity/signal ingest orchestration.
- `src/gmgn_twitter_intel/pipeline/signal_builder.py`: account token alerts and token windows.
- `src/gmgn_twitter_intel/pipeline/social_event_extraction.py`: strict social-event extraction parsing.
- `src/gmgn_twitter_intel/pipeline/enrichment_worker.py`: async watched-account enrichment jobs.
- `src/gmgn_twitter_intel/retrieval/*`: PostgreSQL-backed search, token-flow, account-alert, and harness services.
- `src/gmgn_twitter_intel/storage/*`: PostgreSQL client, Alembic migrations, and repositories.
- `src/gmgn_twitter_intel/cli.py`: `serve`, query, signal, and ops commands.

External users pass handles, symbols, or CAs to this service. GMGN chains/channels are internal collector strategy.

## Operational Notes

- Public WebSocket endpoint: `/ws`.
- Auth message: `{"type":"auth","token":"..."}`.
- Subscribe message: `{"type":"subscribe","handles":["toly"],"replay":20}`.
- Payloads include `event`, `entities`, `alerts`, and `enrichment`.
- Run one ASGI worker; multiple workers duplicate the upstream collector.
- There is no macOS LaunchAgent, systemd unit, or `service` subcommand. Use foreground CLI or Docker Compose.
- The only application config source is `~/.gmgn-twitter-intel/config.yaml`.
- Docker Compose bind-mounts host `~/.gmgn-twitter-intel` to container `/root/.gmgn-twitter-intel`.
- Local foreground and Docker use the same host config. Docker Compose runs PostgreSQL with the `gmgn-twitter-intel-postgres` named volume.
- MCP/FastMCP is optional control/query infrastructure only, not the live event push mechanism.

## Design Discipline

These rules apply when writing specs, plans, or designing new services in this repository. They encode lessons from prior iterations and should be followed unless the user explicitly overrides.

### Spec vs Plan boundary

Specs (`docs/superpowers/specs/`) answer **why and what** at a level a reviewer can debate without reading code. Plans (`docs/superpowers/plans/`) answer **how and when** at a level an engineer can execute without further design.

A spec contains: background, current architecture audit, problem diagnosis, first principles, goals with falsifiable metrics, target architecture, conceptual data flow, core models, interface contracts at semantic level, out-of-scope, risks, evolution path.

A spec must NOT contain: file paths and line numbers as instruction, function signatures, SQL DDL/DML rewrites, Alembic migration code, pseudo-code beyond a 5-line formula, test names, PR sequence, "v1 vs v2" iteration history.

A plan contains: file:line edits, function signatures, exact SQL, migration code, test names, PR breakdown, rollout order, rollback procedure, acceptance test commands.

If the user asks for a spec, do not write a plan inside it. If the user asks for a plan, do not re-litigate the spec.

### Audit before design

Before writing any new service or scoring scheme, audit the existing implementation:

1. List all files in the relevant `src/gmgn_twitter_intel/<area>/` and `tests/` directories.
2. Read the existing `*_service.py` candidates end-to-end. Most "new" features here turn out to be 80% covered by an existing service plus a few missing joins.
3. Trace the data flow from `collector → ingest → enrichment → retrieval → api/http.py → web/`. Cite the actual files and line ranges as evidence in the spec, not as instructions to follow.
4. Identify which fields are already in the DB but unconsumed by retrieval services (e.g. `events.reference_json`, `social_event_extractions.event_type`, `account_token_alerts.is_first_seen_global`). These are usually the cheapest wins.

If a spec's "现状" or "background" section cannot cite specific existing files, the design is ungrounded — fix that before proposing changes.

### Reuse before create

Default to extending an existing service. Only create a new service when:
- the new responsibility is conceptually orthogonal (different input domain or different output contract), AND
- adding it to an existing service would more than double that service's surface area.

Default to deriving on demand. Only persist a new entity when:
- the derivation cannot complete inside one HTTP request budget, OR
- multiple downstream consumers need the same derivation, OR
- the derivation is required by a background settlement/eval that runs without user requests.

Default to extending existing tables. Only add a new table when:
- the new entity has a different lifecycle than any existing table, AND
- it cannot be expressed as a view or materialized view over existing tables.

### Avoid premature complexity

These additions require explicit justification (cite a current pain or a measured number) before appearing in any spec:

- New PostgreSQL tables, materialized views, or background workers.
- LLM calls outside the existing `enrichment_worker` boundary.
- Bayesian / probabilistic outputs (posterior distributions, credible intervals).
- Ground-truth datasets, human annotation workflows, dual-annotator review.
- Statistical inference on small samples (Granger causality, change-point tests with N < 200, control-group matched-pair analysis).
- Reinforcement learning, gradient-based weight tuning, online bandits.
- Cross-validation harnesses or holdout sets.
- New score versions invented without a corresponding bump of `score_version` strings and downstream evaluation filters.

For ranking and scoring proposals, prefer hand-tuned weighted combinations of well-defined deterministic features that can be unit-tested with fixtures. Stay there until a concrete measurement shows the limitation.

### Writing for delivery

Treat each spec and plan as a final artifact, not a diary:

- Do not mention "v1 / v2 / v3" or prior drafts in the document body. Iteration is in git history, not prose.
- Do not include `[ ]` evaluation checklists asking the reader to validate the document. Invite review in the chat reply, not in the file.
- Do not include "what we used to think" or "what we corrected" sections. State the current design as the design.
- Quantitative claims (latency, sample sizes, score thresholds) should either come with measurement evidence or be explicitly tagged as estimates.

### Scoring and ranking design

When proposing any post / event / token ranking signal:

- **Distinguish upstream identity from downstream observation.** A post's followers / first-seen / watched / attribution_confidence are upstream identity attributes; they are weak proxies and in crypto are bot-dominated (especially first-seen). Ranking signals should be defined on observable downstream effects within an explicit time window.
- **Cite literature when proposing aggregation formulas.** Burst detection (Kleinberg 2002), structural virality (Goel et al. 2016 Management Science), cascade prediction (Cheng et al. 2014 WWW), influencer effect refutation (Bakshy et al. 2011 WSDM), complex contagion (Centola 2010 Science), endogenous vs exogenous decay (Crane & Sornette 2008 PNAS) are the relevant base. Indicate which paper supports each component.
- **Make components transparent in the API response.** Every ranking score must be returned alongside its component breakdown so users can audit why the rank is what it is. Black-box scores are forbidden.
- **Test against bot patterns explicitly.** Any new ranking signal must have a unit test asserting that a single-author copy-pasta cluster scores significantly lower than a small set of independent organic responses. This is the minimum bar for crypto-domain robustness.
- **Use `score_version` strings as contracts.** Every change to a scoring formula bumps the version. Downstream evaluation services must filter by version, otherwise A/B comparisons silently mix populations.

### When the user pushes back

If a user says a design is over-engineered, half-baked, ungrounded, or doesn't follow KISS:

- Engage the critique substantively. Identify which specific claim of theirs is correct before agreeing.
- Do not capitulate by deleting everything; find what is genuinely worth keeping and articulate why.
- Do not over-correct in the opposite direction (e.g. responding to "too complex" with "too thin"). Aim for the minimum design that meets the actual goal stated, not the minimum design period.
- Re-read the existing code if the critique implies the prior design ignored it.
