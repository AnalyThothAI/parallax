# Token Radar Attribution Spec

## Objective

Token Radar must rank tradeable token candidates from public-stream evidence without turning a raw
symbol into a fake token bucket.

Raw mentions answer "what did the post contain?" Attribution answers "which tradeable token, if any,
does this mention belong to?" Radar reads attribution rows only.

## Data Model

`event_token_mentions` is the immutable raw fact table:

- Direct CA or GMGN payload mention.
- Symbol-only mention such as `$TROLL`.
- Unknown-chain CA evidence.
- Account alert first-seen evidence.

`event_token_attributions` is the derived decision table:

- `direct`: a CA or GMGN payload already identifies a tradeable token.
- `selected`: a symbol-only mention was assigned to a token candidate.
- `rejected`: a non-winning candidate for a selected symbol.
- `ambiguous`: candidates were too close to select.
- `weak_candidate`: a single candidate existed but lacked enough market evidence.
- `unresolved`: no usable candidate.

Radar includes only rows where:

- `token_id IS NOT NULL`
- `attribution_status IN ('direct', 'selected')`
- `attribution_weight > 0`
- chain/address are tradeable, not `unknown`, `evm`, or `evm_unknown`

There is no read-time symbol fallback and no `symbol:TICKER` radar identity.

## Symbol Candidate Scoring

For a symbol-only mention, candidates come from `token_aliases`. Each candidate is scored from:

- Identity: known alias candidate.
- Market quality: market cap, log-scaled.
- Liquidity and pool: liquidity value and pool presence.
- Activity: holder count or 24h volume.
- Social evidence: direct token mentions in the prior 24h.
- Recency: market snapshot freshness.
- Risk penalties: missing market, missing liquidity, missing pool, stale snapshot, low liquidity.

Selection rules:

- Multi-candidate symbol: select only if confidence >= `0.70` and margin to second >= `0.15`.
- Single-candidate symbol: select if confidence >= weak threshold and hard market evidence is present.
- Close candidates are stored as `ambiguous` with weight `0`.
- Rejected candidates are stored for auditability with weight `0`.

If a symbol post arrives before the token payload, later direct token discovery rebuilds that symbol's
raw mentions into explicit attribution rows. This is a data materialization step, not a radar fallback.

## Flow Semantics

`flow.mentions` is the count of attributed evidence events in the window.

`flow.direct_mentions` counts direct CA or GMGN payload evidence.

`flow.symbol_mentions` counts symbol-only evidence selected by attribution.

`flow.weighted_mentions` sums attribution weights.

`flow.avg_attribution_confidence` explains how much of the row depends on attribution.

`flow.previous_mentions` and `flow.mention_delta` compare the current trailing window to the immediately
previous equal trailing window. They do not use GMGN payload `previous_price`.

## Market Delta Semantics

`market.price_change_window_pct` is computed only from stored snapshots spanning the requested window.

If there is no distinct start snapshot, status is `insufficient_history`. Payload `previous_price` is not
used as a window delta because its source window is not the user's selected radar window.

## Freshness Semantics

`fresh.is_new_local_evidence` means this token's first attributed local evidence appeared inside the
selected window.

It does not claim the token itself is newly created on-chain.

## Signal Contract

`driver` requires:

- tradeable resolved token identity
- fresh market snapshot
- market cap present
- liquidity present
- pool present
- attribution confidence >= `0.70`
- at least two attributed mentions
- rolling acceleration or burst
- healthy diffusion
- no high author concentration

`watch` is used when the token is tradeable but evidence is incomplete, public-only, thin, low-confidence,
or missing some market-quality dimensions.

`discard` is used for unresolved identity, missing market cap, missing market snapshot, repeated text
clusters, or shill-risk diffusion.

Risk caps prevent a high numeric score from hiding serious issues:

- repeated/shill caps at 45
- author concentration caps at 65
- low attribution confidence caps at 60
- stale market caps at 70
- public-only caps at 85

## Search And Evidence Counts

Search responses expose:

- `total_count`: all matching evidence events
- `returned_count`: returned API items
- `has_more`: whether more evidence exists

The web focus panel displays shown/total evidence. It no longer implies that the first 8 visible rows are
the entire match set.

## Operational Notes

Existing databases need attribution materialization for old raw symbol rows. Run:

```bash
uv run gmgn-twitter-intel ops rebuild-attributions --symbol TROLL
```

Omit `--symbol` to rebuild all stored token mentions. Radar intentionally does not silently read raw symbol
mentions as token flow.
