# Cheng et al. 2014 — Can Cascades be Predicted?

**Citation:** Cheng, J., Adamic, L., Dow, P. A., Kleinberg, J., & Leskovec, J. (2014). *Can Cascades be Predicted?* WWW.
**Cited by:** `docs/DESIGN_DISCIPLINE.md` (Scoring and ranking design)

## Claim

Predicting whether a cascade will double in size is hard at the moment of post but becomes feasible once the cascade has reached a small initial size; early temporal and structural features dominate later content features.

## Method

Reformulate cascade prediction as a balanced binary classification: given a cascade of size k, will it reach size 2k? Train on Facebook re-share cascades.

## Rule it supports here

Token-radar's cascade-prediction component should not attempt to predict viral outcomes from a single mention; it should activate only after a small early-window size threshold and weight temporal velocity over content novelty.
