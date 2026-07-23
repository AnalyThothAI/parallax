# Design Discipline

> **Scope.** Owns the rules that govern *what* a spec or plan may contain and *how* a feature must be designed in this repo. Workflow mechanics (lane filenames, worktree, completion gates) live in `WORKFLOW.md`.

## Spec vs plan boundary

A spec contains: background, current architecture audit, problem diagnosis, first principles, goals with falsifiable metrics, target architecture, conceptual data flow, core models, interface contracts at semantic level, out-of-scope, risks, evolution path.

A spec must NOT contain: file paths and line numbers as instruction, function signatures, SQL DDL/DML rewrites, Alembic migration code, pseudo-code beyond a 5-line formula, test names, PR sequence, or "v1 vs v2" iteration history.

A plan contains: file:line edits, function signatures, exact SQL, migration code, test names, PR breakdown, rollout order, rollback procedure, acceptance test commands.

If the user asks for a spec, do not write a plan inside it. If the user asks for a plan, do not re-litigate the spec.

## Audit before design

Before writing any new service or scoring scheme:

1. List all files in the relevant `src/parallax/<area>/` and `tests/` directories.
2. Read existing `*_service.py` candidates end to end. Most "new" features here are 80 % covered by an existing service plus a few missing joins.
3. Trace the current data flow from provider input through PostgreSQL material facts, durable targets or transactionally maintained current rows, the owning projection/read model, and the concrete HTTP/CLI/WebSocket consumer. Cite actual files and line ranges as evidence in the spec, not as instructions.
4. Identify fields already in the DB but unconsumed by retrieval services. These are usually the cheapest wins.

If a spec's background section cannot cite specific existing files, the design is ungrounded — fix that before proposing changes.

## Reuse before create

Default to extending an existing service, deriving on demand, and extending existing tables. Only create a new service / persisted entity / table when the conceptual responsibility, lifecycle, or compute budget genuinely differs from what is already there. Document the trigger in the spec's "Alternatives Considered" section.

## Avoid premature complexity

The following additions require explicit justification (cite a current pain or a measured number) before appearing in any spec:

- New PostgreSQL tables, materialised views, or background workers.
- Any model-backed product consumer. The current service has none; introducing
  one requires an approved evidence contract plus explicit cost, retry, durable
  audit/state, public-consumer, migration, and verification design.
- Bayesian / probabilistic outputs.
- Ground-truth datasets, human annotation workflows, dual-annotator review.
- Statistical inference on small samples (N < 200).
- Reinforcement learning, gradient-based weight tuning, online bandits.
- Cross-validation harnesses or holdout sets.
- New score versions without a corresponding `score_version` bump and downstream evaluation filter.

Prefer hand-tuned weighted combinations of deterministic features unit-tested with fixtures until a concrete measurement shows the limitation.

## Writing for delivery

Each spec and plan is a final artefact, not a diary. No "v1 / v2 / v3" prose, no in-document review checklists, no "what we used to think" sections. Quantitative claims either come with measurement evidence or are explicitly tagged as estimates.

## Scoring and ranking design

- Distinguish upstream identity from downstream observation; ranking signals operate on observable downstream effects within an explicit time window.
- Cite literature when proposing aggregation formulas. The relevant base lives under [`references/papers/`](references/papers/):
  - [Kleinberg 2002 — burst detection](references/papers/kleinberg-2002-burst.md)
  - [Goel et al. 2016 — structural virality](references/papers/goel-2016-structural-virality.md)
  - [Cheng et al. 2014 — cascade prediction](references/papers/cheng-2014-cascades.md)
  - [Bakshy et al. 2011 — influencer-effect refutation](references/papers/bakshy-2011-influencer-refutation.md)
  - [Centola 2010 — complex contagion](references/papers/centola-2010-complex-contagion.md)
  - [Crane & Sornette 2008 — endogenous vs exogenous](references/papers/crane-sornette-2008-endogenous-exogenous.md)
- Every ranking score returned by the API must include its component breakdown. No black-box scores.
- Every new ranking signal needs a unit test asserting a single-author copy-pasta cluster scores significantly lower than a small set of independent organic responses.
- Bump `score_version` on every formula change so downstream evaluation services do not silently mix populations.

## Pushback handling

If a user says a design is over-engineered, half-baked, ungrounded, or doesn't follow KISS: engage the critique substantively, identify which specific claim is correct, do not capitulate by deleting everything, do not over-correct in the opposite direction, and re-read the existing code if the critique implies prior design ignored it.
