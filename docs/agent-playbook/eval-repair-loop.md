# Development Agent Eval And Repair Loop

This file defines how Parallax evaluates and repairs development-agent workflow quality. It is separate from product LLM agent evals and does not create runtime product truth.

## Reference Alignment

The loop is aligned with OpenAI Codex guidance on scored improvement loops, Spec Kit's analyze-before-implement gate, and GitHub's emphasis on acceptance criteria and PR iteration for coding agents.

References:

- [OpenAI Codex use cases](https://developers.openai.com/codex/use-cases)
- [OpenAI Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/)
- [GitHub Spec Kit](https://github.com/github/spec-kit)
- [GitHub Copilot task best practices](https://docs.github.com/en/enterprise-cloud@latest/copilot/tutorials/cloud-agent/get-the-best-results)

## Trace Dataset

Every non-trivial feature should leave enough evidence to replay the development decision:

- SDD `spec.md`, `plan.md`, `tasks.md`, and `verification.md`.
- Generated `docs/generated/sdd-work-index.md` coordination state.
- Commit diff and touched files.
- Commands run, exit status, skipped tests, and stopped gates.
- Review defect notes, if any.
- Subagent handoffs, context packets, and validated subagent reports when delegation happened.

Do not store secrets, provider credentials, private DSNs, cookies, or raw operator config. Use redacted paths, booleans, counts, and command outcomes.

## Metrics

Track these metrics when reviewing agent workflow quality:

| Metric | Meaning |
|--------|---------|
| review defect rate | Count of reviewer-found issues per feature or PR. |
| harness failure rate | Count of validator, architecture, generated-doc, or completion-gate failures. |
| repair loop count | Number of red-green-fix cycles needed after first failed verification. |
| token cost | Approximate agent effort spent on the feature, when available. |
| false completion attempts | Any claim that out-runs evidence, especially incomplete `make check-all`. |
| touch conflict count | Number of active lanes touching the same path without coordination. |
| review result | Parent decision for delegated work: `accepted`, `needs-repair`, or `blocked`. |

Metrics guide process repair; they are not product analytics and must not become product read models.

## Repair Loop

Use this loop after a harness failure or review defect:

1. Classify the issue as requirement gap, plan gap, task gap, implementation defect, harness defect, or verification gap.
2. Add or update the smallest failing test or validator case.
3. Fix the source of the failure, not the symptom.
4. Validate any returned subagent report with `uv run python scripts/validate_subagent_report.py --feature <slug> --task <number> --mode <mode> --report <report.md>`.
5. Re-run the targeted command that failed.
6. Update the SDD verification record with the command and exit status.
7. Re-run `make check-all` before claiming `Verified`.

No production claim without verification evidence. If `make check-all` is intentionally stopped, keep the SDD record active and record who stopped it and why.

## Repair Outputs

Each repair should produce at least one of:

- A stronger architecture or unit test.
- A stricter SDD validator issue code.
- A clearer task field in the template.
- A generated index field that makes coordination visible.
- A validated subagent report that proves scope adherence and verification evidence.
- A short follow-up spec for work outside the approved scope.

Avoid process folklore. If the same failure can recur, make it executable.
