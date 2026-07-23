# Kleinberg 2002 — Bursty and Hierarchical Structure in Streams

**Citation:** Kleinberg, J. (2002). *Bursty and Hierarchical Structure in Streams.* KDD.
**Cited by:** `docs/DEVELOPMENT.md` (design discipline)

## Claim

Streams of timestamped events exhibit "bursts" of elevated rate that are statistically distinguishable from baseline noise. A finite-state automaton model identifies bursts as transitions to higher-rate states.

## Method

Frame the stream as a hidden two-state (or k-state) Markov model where each state has a rate parameter; the cost of state transitions and the data likelihood are jointly minimised. Bursts are detected as runs in elevated states.

## Rule it supports here

Token-mention rate spikes used by the radar's heat / propagation components must be evaluated against an expected baseline rate, not against the total volume window. A spike that does not clear the burst threshold is noise, not signal.
