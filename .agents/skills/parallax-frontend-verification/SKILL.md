---
name: parallax-frontend-verification
description: Run Parallax frontend verification for UI, CSS, route shell, responsive layout, and component ownership changes. Use for "Frontend CSS Or Route Shell" tasks and fixed UI QA.
---

# Parallax Frontend Verification

Use this skill after any `web/src` UI, route shell, CSS, responsive layout, or shared component change. The frontend harness is architectural, not optional style preference.

## Required Reading

1. `AGENTS.md`
2. `docs/agent-playbook/task-reading-matrix.md`
3. `docs/FRONTEND.md`
4. `docs/WORKFLOW.md`
5. Owning feature files under `web/src/features/<feature>/`
6. Existing component tests under `web/tests/`

## Workflow

1. Classify the task as `Frontend CSS Or Route Shell`.
2. Identify the owning feature namespace and route shell.
3. Confirm no retired CSS buckets return: `cockpit.css`, `macro.css`, `macroResponsive.css`, `shared.css`, or `signalLab.css`.
4. Confirm feature CSS does not restyle shared UI internals, notification internals, or Obsidian `.ods-*` selectors.
5. Prefer local owner CSS beside the component or route that imports it.
6. Confirm `frontendDataOwnership.test.ts` stays green: route modules and presentational UI must not directly call `useQuery`, `useMutation`, `useInfiniteQuery`, `getApi`, `postApi`, or `queryClient.set`; feature API hooks, page hooks, and controllers own server reads/writes.
7. Run `cd web && npm run lint`.
8. Run `cd web && npm run test:architecture`.
9. Run `cd web && npm run typecheck`.
10. Run targeted `npm run test -- <path>` when a component test exists.
11. For visible layout changes, use browser screenshots across desktop and mobile. Check blank states, text overflow, overlap, and missing data states.

## Verification Commands

- `cd web && npm run lint`
- `cd web && npm run test:architecture`
- `cd web && npm run typecheck`
- Targeted component or unit test under `web/tests/`

## Output

- Routes and viewports checked.
- Screenshots or browser evidence when layout changed.
- Verification commands with exit status.
- Any UI surface not covered by automated tests.
