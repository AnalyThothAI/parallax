# Narrative Intel Architecture

Narrative Intel is a CQRS read-model lane downstream of Token Radar. Its
business truth starts with material facts (`events`, token resolutions, market
facts, and current `token_radar_current_rows`) and then flows through three rebuildable
read models:

```text
token_radar_current_rows
  -> narrative_admission_dirty_targets
  -> narrative_admissions
  -> token_mention_semantics (leased rows)
  -> discussion_digest_dirty_targets
  -> token_discussion_digests
  -> last-ready epoch + current admission delta
  -> API / WebSocket / CLI reads
```

## Source-Set Truth

`narrative_admissions.source_event_ids_json` is the only current source-set
truth for a target/window/scope/schema. Downstream coverage must expand admitted
source sets and then left-check semantics rows. A source event may be counted
once for each current admission it belongs to, including across windows and
scopes. Multiple semantic fingerprints for the same admission-source row count
as one covered source row.

Prompt samples are not completeness. Digest prompts may cap the number of
mentions sent to the LLM, but completeness uses full-source aggregate counts:
source rows, semantic rows, missing rows, pending/retryable rows, labeled rows,
and terminal unavailable rows.

## Writer Ownership

`NarrativeAdmissionWorker` is the runtime writer for `narrative_admissions`.
`MentionSemanticsWorker` is the runtime writer for `token_mention_semantics`.
`TokenDiscussionDigestWorker` is the runtime writer for
`token_discussion_digests`. Repository methods may contain SQL for these tables,
but normal runtime writes are reached only through the owning worker.

Runtime discovery is control-plane first. `NarrativeAdmissionWorker` claims
`narrative_admission_dirty_targets`; `MentionSemanticsWorker` claims leased
`token_mention_semantics` rows; `TokenDiscussionDigestWorker` claims
`discussion_digest_dirty_targets`. Empty queues return without scanning Token
Radar, admissions, or semantic source rows. Historical repair uses the bounded
`ops enqueue-runtime-worker-dirty-targets` command and only enqueues work.

`ops rebuild-narrative-intel` is the maintenance exception. While it holds all
narrative worker advisory locks, it may run hard-cut cleanup to delete obsolete
queued/retryable/stale semantics and mark suppressed current digests stale. A
source fingerprint mismatch is preserved as public delta instead of demoting a
ready digest. That path is not callable from HTTP routes and is not a second
runtime writer.

## Public Digest Contract

`TokenDiscussionDigestWorker` writes sealed narrative epochs for `1h`, `4h`,
and `24h`. It does not write discussion digests for `5m`; that window is a
scanner frontier only.

Public reads do not use exact source-fingerprint equality as a display gate.
They call `current_narrative_snapshots_for_targets`, which composes the newest
ready digest with the current admitted source set and returns a required
`discussion_digest.currentness` object. Display states are:

- `current`: ready epoch matches the current source frontier.
- `updating`: ready epoch remains readable while current admissions have delta.
- `stale`: ready epoch is historical context because its display horizon passed.
- `not_ready`: an admitted frontier exists but no ready epoch exists yet.
- `out_of_frontier`: no admitted frontier exists for the target/window/scope.
- `unsupported_window`: the window intentionally has no digest, especially `5m`.

Digest and semantics budget pressure is explicit. `llm_cycle_budget_exhausted`
means the digest worker deferred an otherwise due LLM call for cycle capacity.
`llm_failure_budget_exhausted` means provider failures consumed the cycle's
failure budget and remaining LLM work backed off. `NarrativeEpochPolicy`
separately records epoch decisions such as `no_material_delta`,
`material_delta_due`, `ttl_refresh_due`, `semantic_pending`, and
`unsupported_window`.

## Hard Cut

This domain does not keep runtime compatibility aliases for removed behavior.
Source-age prune compatibility, old fallback digest hydration, and old collapsed
`digest_not_ready` reasons are removed rather than shadowed by runtime aliases.
