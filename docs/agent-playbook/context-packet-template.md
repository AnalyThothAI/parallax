# Context Packet Template

Use this for parent-agent to subagent handoff. It is a bounded fact packet, not a diary and not a replacement for canonical docs. Prefer generating it from active SDD task metadata:

```bash
uv run python scripts/build_agent_context_packet.py --feature <slug> --task <number> --mode read-only
```

```md
# Context Packet - <feature> / Task <number>

Mode: <read-only | write-allowed | review-only>
Mode constraints:
- Read-only mode: do not edit files; report findings, required reading, and verification evidence only.
- Write-allowed mode: changed files must stay inside Owned scope and avoid Do not touch.
- Review-only mode: do not edit files; review existing scope and report issues only.

Current objective:
- <what the overall task is trying to achieve>

Truth boundary:
- Facts: <PostgreSQL fact tables or source files that define truth>
- Read models: <derived public/current rows involved>
- Control plane: <queues, dirty targets, leases, run ledgers, budgets>
- Cache/fan-out: <process-local or generated state, if relevant>
- Provider raw inputs: <provider frames/responses, if relevant>

Known symptoms:
- <observable issue, command output, API response, or test failure>

Canonical docs/code already checked:
- `<path>` - <what was learned>

Relevant active planning artefacts:
- `<path>` - <why it is relevant and whether code/docs confirm it>

Unknowns:
- <questions the subagent should resolve>

Redactions:
- Secrets, tokens, cookies, proxy URLs, DSNs, and private credentials are omitted.

Suggested verification:
- `<command>`
```

Rules:

- Keep the packet under one screen when possible.
- Prefer exact paths and command outputs over summaries.
- Include stale or uncertain claims under Unknowns, not as facts.
- Do not paste live secrets or full provider credentials.
