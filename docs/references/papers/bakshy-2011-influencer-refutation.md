# Bakshy et al. 2011 — Everyone's an Influencer

**Citation:** Bakshy, E., Hofman, J. M., Mason, W. A., & Watts, D. J. (2011). *Everyone's an Influencer: Quantifying Influence on Twitter.* WSDM.
**Cited by:** `docs/DESIGN_DISCIPLINE.md` (Scoring and ranking design)

## Claim

Targeting only high-follower "influencers" is a poor strategy; the marginal cost of acquiring an influencer post outweighs the expected diffusion gain in most regimes. Smaller, more numerous targets often dominate ROI.

## Method

Track URL-sharing cascades on Twitter; regress cascade size on poster characteristics; compare expected vs realised diffusion across the follower distribution.

## Rule it supports here

Account upstream-identity features (follower count, watched-list membership) are weak proxies for downstream impact. Ranking signals must operate on observable downstream effects within an explicit time window, not on author identity.
