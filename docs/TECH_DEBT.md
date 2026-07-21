# Technical Debt

This file contains only current, evidenced debt. Completed hard cuts belong in dated reviews and Git history, not in an ever-growing closed-debt ledger.

| Debt | Risk | Exit condition | Owner |
|---|---|---|---|
| Historical `events.raw_json` / `events.event_json` have no proven one-to-one `raw_frames` source edge and locator | Deleting them now could destroy the only replayable evidence for some events | Persist the edge for new writes, measure historical coverage at 100%, export ambiguous payloads immutably, then hard-delete the duplicate payloads | Evidence/Ingestion |
| DB-only maintenance branches in `app/surfaces/cli/commands/ops.py` still own several one-off repair transactions | Provider/client lifecycle is now outside the CLI, but reusable repair workflows can still accrete transport-owned transaction detail | Move a repair into `app/operations` when it gains a second caller or multi-step lifecycle; keep its CLI branch to argument mapping and serialization | Runtime/Operations |
| Strict mypy is relaxed for parts of `parallax.app.*` and `parallax.integrations.*` | Interface regressions can hide behind broad `Any` use | Remove overrides package-by-package after protocols and typed provider bundles cover current behavior | Runtime/Integrations |

New entries require a concrete source path or runtime symptom, user/business impact, and a verifiable deletion condition. Avoid recording speculative redesign ideas as debt.
