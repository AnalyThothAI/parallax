# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues in `AnalyThothAI/parallax`. Use the `gh` CLI for operations not exposed by the connected GitHub app.

## Conventions

- **Create an issue**: create it in `AnalyThothAI/parallax` with a descriptive title, complete Markdown body, and the appropriate triage label.
- **Read an issue**: include comments and labels.
- **List issues**: filter by state and label, retaining issue number, title, body, labels, and comments.
- **Comment on an issue**: add durable decisions or verification evidence to the issue.
- **Apply / remove labels**: keep exactly one canonical triage state where applicable.
- **Close**: include a final comment that states the disposition or implementation evidence.

Infer the repository from `git remote -v` when operating inside the clone.

## Pull requests as a triage surface

**PRs as a request surface: no.** Pull requests are implementation and review surfaces, not feature-request intake.

GitHub shares one number space across issues and pull requests, so resolve an ambiguous bare number before acting.

## When a skill says "publish to the issue tracker"

Create a GitHub issue in `AnalyThothAI/parallax`.

## When a skill says "fetch the relevant ticket"

Read the GitHub issue, including comments and labels.

## Wayfinding operations

Used by `/wayfinder`. A map is one issue and its child issues are tickets.

- **Map**: one issue labelled `wayfinder:map`, containing Notes, Decisions-so-far, and Fog.
- **Child ticket**: a GitHub sub-issue linked to the map. If sub-issues are unavailable, use a task-list link and a `Part of #<map>` line. Apply the appropriate `wayfinder:<type>` label.
- **Blocking**: use native issue dependencies. If unavailable, use a `Blocked by: #<n>` line.
- **Frontier query**: choose the first open, unassigned child in map order with no open blockers.
- **Claim**: assign the ticket to the driving developer; this is the session's first write.
- **Resolve**: comment with the answer, close the ticket, and add a durable context pointer to the map.
