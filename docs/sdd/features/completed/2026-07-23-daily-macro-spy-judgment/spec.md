# Spec — Daily Macro SPY Judgment

**Status**: Verified
**Date**: 2026-07-23
**Owner**: Codex `/root`
**Approved by**: delegated user goal and GitHub Issue #6
**Approved at**: 2026-07-23
**Related**: `https://github.com/AnalyThothAI/parallax/issues/6`, `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`

## Background

GitHub Issue #6 specifies a narrow, independent daily publication lane after the deterministic six-document Macro product: [DeepAgents 每日 Macro SPY 研判最小 V1](https://github.com/AnalyThothAI/parallax/issues/6). The existing `macro_decision_v2` current snapshot remains deterministic and rebuildable. The new lane freezes the complete point-in-time evidence actually exposed to a real DeepAgents Analyst and isolated Reviewer, then publishes one immutable SPY-only judgment for each completed US regular session.

## Problem

The current six evidence pages make state inspectable but do not produce one coherent, daily, forward-looking SPY judgment. A model call against the mutable current snapshot would be unauditable and could use revised or late facts. A generic agent platform, multi-asset forecast, score, probability, or trading layer would exceed the requested product boundary.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| What is the product identity? | One completed US regular trading session; run IDs, attempts, timestamps, and model call IDs are audit metadata only. | user / Issue #6 | 2026-07-23 |
| What is predicted? | SPY direction over the next 5 and 20 completed US sessions only. | user / Issue #6 | 2026-07-23 |
| Which direction states exist? | `up`, `down`, `range`, and `no_call`; `range` means adequate evidence without material directional advantage, while `no_call` means evidence is insufficient or too conflicted. | user / Issue #6 | 2026-07-23 |
| Are scores, probabilities, positions, or trade plans allowed? | No. V1 has no score, probability, numerical confidence, holdings, sizing, entry, stop, target, or execution instruction. | user / Issue #6 | 2026-07-23 |
| Does the existing six-page Macro projection change? | No. It remains deterministic, current, exactly six documents, and without LLM fields or calls. | user / Issue #6 | 2026-07-23 |
| What evidence may an Agent read? | Only the frozen, bounded `MacroEvidencePack`, whose facts have trustworthy public availability at or before cutoff and whose complete contents and lineage are persisted. | user / Issue #6 | 2026-07-23 |
| Who owns the session clock and publication lifecycle? | Parallax owns session/cutoff, eligibility, idempotency, retries, persistence, gates, rendering, and outcomes; DeepAgents owns only the model/tool loop. | user / Issue #6 | 2026-07-23 |
| What Agent topology is allowed? | One Analyst created with `create_deep_agent` and one isolated declarative Reviewer invoked through native `task`; no other agents. | user / Issue #6 | 2026-07-23 |
| May the two roles use distinct models? | Yes. `analyst_model` and `reviewer_model` are explicit worker settings using the same provider credential/endpoint boundary; model choice does not change tool capabilities or product scope. | user follow-up | 2026-07-23 |
| Where is the judgment visible? | `/macro` renders one compact Daily AI section from the persisted-only endpoint; it adds no route, score, position layer, or request-time model call. | user follow-up | 2026-07-24 |
| What happens when evidence is locally degraded? | A publication may remain `degraded`, but every affected horizon is forced to `no_call`; untrustworthy global cutoff or lineage blocks publication. | user / Issue #6 | 2026-07-23 |
| Is implementation authorized? | Yes. The active goal explicitly requests thorough implementation of this spec. | delegated user goal | 2026-07-23 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| Freeze a complete point-in-time EvidencePack. | PostgreSQL integration proves cutoff eligibility, lineage, bounded selection, exact six-page semantics, stable content hash, and exclusion reasons. |
| Publish immutable, idempotent session records. | Non-empty migration and replay tests prove one session identity, no update/delete, zero model calls and zero writes after publication. |
| Use the real two-role DeepAgents topology. | Narrow wiring test proves `create_deep_agent`, native `task`, isolated Reviewer, scoped tools, structured output, and no browser/SQL/shell/filesystem/memory tools. |
| Enforce bounded review and deterministic gates. | Tests cover pass, one revise plus closure, block, schema/ref/cutoff/forbidden-field failures, and renderer agreement. |
| Keep the product SPY-only and simple. | Strict schemas and negative architecture tests reject other asset calls, scores, probabilities, confidence, positions, and trading instructions. |
| Operate safely as one worker. | PostgreSQL worker tests prove calendar/settle/catch-up/retry/single-writer behavior, model I/O outside transactions, and atomic publication completion. |
| Append outcomes without rewriting judgments. | 5D/20D session-aware return tests prove append-only outcome records with no hit/miss or score. |
| Expose one persisted-only typed read contract. | API/OpenAPI tests cover latest, explicit session, missing, blocked, stale, outcomes, and zero model calls on request. |
| Make the daily analysis visible without expanding scope. | Frontend route, architecture, responsive, and browser tests cover the persisted Daily section plus explicit unavailable states. |
| Preserve existing Macro and Product-AI boundaries. | Existing six-page, News, Token, current-read identity, architecture, and migration regressions stay green under a narrow exception. |
| Prove the installed runtime. | A redacted real-provider Analyst→Reviewer shadow receipt is recorded separately from deterministic test evidence. |

## First principles

- PostgreSQL material facts remain the only business truth. Model output is a derived immutable publication, not a material fact or replacement for `macro_decision_v2`.
- Evidence availability is different from ingestion time. A fact without a trustworthy source/public availability timestamp cannot support a directional call.
- Deterministic work remains outside Agents: point-in-time selection, session math, schema validation, evidence-reference closure, failure policy, rendering, persistence, and outcomes.
- Publication is fail closed. A stale prior publication may be returned as stale but may never be represented as the target session.
- The new lane has one writer and no database wake plane.

## Target architecture

```text
PostgreSQL material facts
  -> deterministic point-in-time EvidencePack compiler
  -> immutable session job + frozen pack
  -> DeepAgents Macro Analyst
       -> native task delegation -> isolated Reviewer
  -> deterministic post-gates
  -> atomic immutable DailyMacroJudgment + fixed Chinese memo
  -> persisted-only latest / explicit-session read
  -> compact persisted Daily AI section on /macro
  -> append-only SPY 5D / 20D outcomes
```

The existing `macro_observations -> macro_decision_v2 exactly-six current snapshot` lane remains separate and unchanged.

## Core models

- **MacroEvidencePack**: session date, official close cutoff, seal time, compiler/selection versions, six typed deterministic evidence documents, bounded official/high-quality persisted texts, per-item source/available/ingested timestamps, selection rule, content hash, exclusions, health, and a canonical pack hash.
- **DailyMacroJudgment**: strict minimal product truth with session/cutoff/data health, one macro-state summary, one to four pressure mechanisms, SPY 5D/20D calls, one to four key counterevidence observations, nested evidence refs, experimental marker, and audit versions.
- **ReviewerResult**: `pass`, `revise`, or `block` plus structured issues. It cannot replace or silently edit Analyst directions.
- **Publication job**: stable session-keyed lifecycle with frozen EvidencePack, bounded attempts, lease, safe failure state, and atomic completion.
- **Outcome**: append-only 5D or 20D SPY close-to-close realized return linked to the publication session.

## Interface contracts

- One read-only HTTP endpoint returns the latest publication by default or an explicit session when requested. It reads PostgreSQL only and never runs Agents, repairs, or backfills.
- The Macro Overview renders the latest persisted publication as macro state/pressures, SPY 5D/20D calls, theses, and counterevidence. It keeps generation states explicit and performs no frontend inference.
- Response states distinguish current publication, stale prior publication, pending/retryable/blocked/failed target job, and missing explicit session.
- The Chinese memo is rendered deterministically from the final structured judgment in this order: cutoff/data health; macro state/pressures; SPY 5D/20D; key counterevidence.
- Published records are immutable. Latest is a query over history, not a second current row.
- Agent audit stores versions, bounded dispositions, tool/delegation receipts, and sanitized errors, never hidden reasoning or credentials.

## Acceptance criteria

- AC1. WHEN a completed US session becomes eligible THEN the system SHALL compile and persist one bounded, canonical, full-content EvidencePack using only facts with trustworthy public availability at or before the official close cutoff.
- AC2. WHEN current Macro, official event, Fed/Treasury, and eligible high-quality News facts are selected THEN the EvidencePack SHALL preserve exact agent-visible content, sources, available and ingestion timestamps, selection rules, versions, exclusions, hashes, and the existing six-page deterministic semantics.
- AC3. WHEN an eligible publication job runs THEN the system SHALL invoke a Macro Analyst created by `create_deep_agent`, delegate review to exactly one isolated declarative Reviewer through native `task`, and expose only EvidencePack-scoped read/submit tools.
- AC4. WHEN the Analyst and Reviewer return output THEN strict deterministic gates SHALL enforce schema, session/cutoff equality, direction enums, evidence-reference closure, forbidden-content rules, data-health policy, review disposition, bounded revision, and renderer consistency before publication.
- AC5. WHEN evidence is adequate or locally degraded THEN the product SHALL publish only SPY 5D and SPY 20D calls using `up`, `down`, `range`, or `no_call`, force affected degraded horizons to `no_call`, and include no score, probability, numerical confidence, position, sizing, or trade instruction.
- AC6. WHEN a global cutoff, calendar, lineage, EvidencePack, model, Reviewer, schema, or reference gate fails THEN the system SHALL publish nothing for that session and SHALL retain a safe auditable job failure state without changing a prior publication.
- AC7. WHEN a session is already published THEN every replay SHALL perform zero model calls and zero publication writes, and the published judgment, memo, frozen EvidencePack, review, and audit versions SHALL reject update and delete.
- AC8. WHEN the daily worker operates across normal, weekend, holiday, early-close, restart, retry, and catch-up conditions THEN it SHALL use one writer, bounded work, model I/O outside database transactions, and one atomic publication-plus-job-completion transaction without a wake plane.
- AC9. WHEN the fifth or twentieth completed session matures THEN the system SHALL append the SPY close-to-close realized return as a separate immutable outcome without modifying the judgment or producing hit/miss, scores, baselines, or rankings.
- AC10. WHEN a client requests the latest or an explicit DailyMacroJudgment session THEN the API SHALL return only persisted typed state and outcomes, distinguish missing/blocked/stale/current correctly, and SHALL make zero model or provider calls.
- AC11. WHEN architecture and migration guards run THEN the existing exactly-six deterministic Macro projection, material facts, News/Token model prohibitions, current read identities, and retired `macro_daily_briefs` absence SHALL remain intact while only the new lane may create a DeepAgent.
- AC12. WHEN the feature is accepted THEN canonical docs, pinned dependencies, generated contracts, focused non-empty PostgreSQL tests, full repository checks, installed Docker runtime, and a redacted real-provider Analyst-to-Reviewer shadow receipt SHALL agree with the experimental/shadow product contract.
- AC13. WHEN an operator opens `/macro` THEN the frontend SHALL render the persisted DailyMacroJudgment as a compact experimental section with currentness, cutoff, data health, macro state/pressures, SPY 5D/20D directions and theses, counterevidence, review status, and model identity; missing or failed states SHALL remain explicit and no page read SHALL invoke a model.

## Out of scope

- Any independent non-SPY asset forecast, multi-asset trade map, technical/flow signal, portfolio, position, execution, alert, or personalized recommendation.
- Scores, probabilities, numerical confidence, expected return, complex neutral bands, hit rate, benchmark, leaderboard, or automatic model optimization.
- Intraday or premarket publication, 1D prediction, unlimited historical backfill, unrestricted news research, new providers, arbitrary browsing/SQL/shell/filesystem access, or free long-term Agent memory.
- A generic Product-AI platform, more than two roles, parallel research teams, Report Writer, open-ended review, or a second writing model.
- Refactoring the six existing deterministic Macro documents, adding a new Macro route, or redesigning unrelated frontend surfaces.
