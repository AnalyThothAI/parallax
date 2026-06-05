# Subagent Handoff Template

Use this template when delegating work to a subagent. Keep the prompt narrow and self-contained. Prefer one subagent per independent question or write scope.

```md
You are a <read-only scout | implementation worker | reviewer> subagent for Parallax.

Mode: <read-only | write allowed | review only>

Goal:
- <single concrete outcome>

Owned scope:
- <files, modules, docs, tests, or question domain this subagent owns>

Do not touch:
- <files, modules, user changes, live config, unrelated domains>

Must read:
- `AGENTS.md`
- `docs/agent-playbook/task-reading-matrix.md`
- <canonical docs for this task>
- <owning domain ARCHITECTURE.md when relevant>

Context packet:
- <paste or link the filled context-packet-template.md>

Conflict set:
- <files or concerns owned by the parent agent or another subagent>

Expected output:
- Findings first, with file paths and evidence.
- Changed files, if write allowed.
- Remaining risks and open questions.
- Verification evidence, including command and exit status.

Verification evidence:
- <targeted command the subagent must run or explain why it could not run>

Constraints:
- Work with existing user changes; never revert unrelated edits.
- Never print secrets from `~/.parallax/` or environment variables.
- Do not treat active specs/plans as current truth until checked against canonical docs and code.
```

Parent agent review checklist:

- Did the subagent stay inside Owned scope?
- Did it avoid the Conflict set?
- Are findings tied to file paths, commands, or source lines?
- If files changed, are they disjoint from other subagents' write scopes?
- Is Verification evidence fresh and relevant?
- Did the parent agent independently inspect the diff before integrating?
