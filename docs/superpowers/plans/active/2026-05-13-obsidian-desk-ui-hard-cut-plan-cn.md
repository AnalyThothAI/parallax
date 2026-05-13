# Obsidian Desk UI Hard Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current metric-table cockpit with the Obsidian Desk v2 case-file UI across Token Radar, Selected Token, Watchlist, Search Intel, and Signal Pulse, without retaining parallel compatibility UI.

**Architecture:** Implement the architecture review before the visual rewrite: `app/` owns providers/routes, route modules own route data/state orchestration, feature API hooks own server reads, feature model adapters own product semantics, and shared case-file primitives own the Obsidian Desk design language. CSS globals are reduced to tokens/base/shared primitives; feature CSS stops depending on `moduleKeep` and broad `:global(...)` selectors. No backend/API/schema changes are part of this plan.

**Tech Stack:** React 19, React Router 6, React Query 5, TypeScript 5.9, CSS modules/global tokens, lucide-react, Vitest, Testing Library, Playwright, MSW.

---

**Status**: Draft  
**Date**: 2026-05-13  
**Owning spec**: `docs/superpowers/specs/active/2026-05-13-obsidian-desk-ui-hard-cut-cn.md`  
**Architecture review**: `docs/superpowers/specs/active/2026-05-13-frontend-architecture-design-language-review-cn.md`  
**Worktree**: `.worktrees/obsidian-desk-ui-hard-cut/`  
**Branch**: `codex/obsidian-desk-ui-hard-cut`

## Pre-Flight

- [ ] Spec is reviewed and approved.
- [ ] Architecture review is reviewed and accepted: `docs/superpowers/specs/active/2026-05-13-frontend-architecture-design-language-review-cn.md`.
- [ ] Create implementation worktree:
  ```bash
  git worktree add .worktrees/obsidian-desk-ui-hard-cut -b codex/obsidian-desk-ui-hard-cut main
  cd .worktrees/obsidian-desk-ui-hard-cut
  ```
- [ ] Verify isolation:
  ```bash
  git worktree list
  git branch --show-current
  git status --short
  ```
  Expected: branch is `codex/obsidian-desk-ui-hard-cut`; status has no unrelated edits from the main checkout.
- [ ] Install/check frontend dependencies if needed:
  ```bash
  npm --prefix web install
  ```
- [ ] Baseline frontend gates:
  ```bash
  npm --prefix web run lint
  npm --prefix web run typecheck
  npm --prefix web run test
  npm --prefix web run build
  ```
- [ ] Baseline repository gate:
  ```bash
  make check-all
  ```

Known-failing baseline tests: none expected. If a baseline command fails before edits, record full output in `docs/superpowers/plans/active/2026-05-13-obsidian-desk-ui-hard-cut-verification.md` before implementing.

## File-Level Edits

### Architecture Groundwork Required By The Review

The audit found that `CockpitApp`, relative cross-feature imports, and global CSS are the highest-risk blockers. This groundwork must land before the feature UI rewrites so the design language has a durable owner.

- Modify `web/src/app/AppRoutes.tsx:1-5`.
  - Make this the only route-tree owner.
  - Import route elements from `@routes/live.route`, `@routes/search.route`, `@routes/signal-lab.route`, `@routes/stocks.route`, `@routes/token-target.route`, and the new `@routes/watchlist.route`.
  - It should no longer render one monolithic `CockpitApp`.
- Modify `web/src/app/CockpitApp.tsx:1-377`.
  - Split the current contents into route-owned modules.
  - Keep only provider/shell composition that is genuinely global, or delete the file if route modules fully replace it.
  - The final file must not own `useLiveData`, `useLiveSelection`, watchlist model construction, Signal Pulse selection, or feature route JSX.
- Create `web/src/features/cockpit/ui/CockpitFrame.tsx`.
  - Owns topbar, side rail, notification drawer/toast, mobile nav, and slot layout.
  - Props are slots/data/controllers, not feature query results.
  - It may render `CockpitShell` and `SearchShell` internally or replace them with a single slot-based frame.
- Modify `web/src/features/cockpit/index.ts`.
  - Export only public cockpit contracts: `CockpitFrame`, shell UI, mobile task types, and route task helpers.
  - Do not expose feature-private state files unless there is a deliberate public hook.
- Create or expand `web/src/routes/live.route.tsx`.
  - Own `useLiveRouteState`, `useLiveData`, live socket merge, `useLiveSelection`, `LivePage`, `LiveRadar`, and live-specific detail slot selection.
  - Register live market subscriptions only while the live radar route is active.
- Create or expand `web/src/routes/search.route.tsx`.
  - Own Search shell composition and `SearchIntelPage`.
  - Keep topbar submit behavior route-scoped.
- Create or expand `web/src/routes/signal-lab.route.tsx` and `web/src/routes/signal-lab.pulse.route.tsx`.
  - Own Signal Lab route state, pulse list, pulse detail route, and selected pulse case.
- Create `web/src/routes/watchlist.route.tsx`.
  - Own `/watchlist` route state and frame composition once the Watchlist feature exists.
- Modify `web/src/features/live/useLiveData.ts:1-160`.
  - Move direct `getApi`, `getBootstrap`, `setAuthToken`, status, recent, and Signal Pulse compact calls into feature API hooks:
    - `web/src/features/live/api/useBootstrapQuery.ts`
    - `web/src/features/live/api/useStatusQuery.ts`
    - `web/src/features/live/api/useRecentEventsQuery.ts`
    - existing `web/src/features/live/api/useTokenRadarQuery.ts`
    - `web/src/features/signal-lab/api/useSignalPulseQueries.ts` for Signal Pulse compact/overview data.
  - `useLiveData` may compose public hooks, but it must not call `getApi` directly.
- Modify `web/src/features/live/useLiveSelection.ts:1-324`.
  - Remove relative imports from `../cockpit/...` and `../search/tokenSearchRoute`.
  - Move `tokenSearchPath` and `tokenSearchQuery` into `web/src/shared/routing/paths.ts` or export them from `@features/search` public index and consume through the alias.
  - Move route-task lookup to `@features/cockpit` public index or `web/src/shared/routing/routeTasks.ts`.
  - Split navigation concerns from selected live entity state if the function remains over 200 lines after route extraction.
- Modify `web/src/features/notifications/useNotificationsController.ts`.
  - Remove relative import from `../cockpit/model/mobileTask`; consume a public cockpit type or shared route-task contract.
- Modify `web/eslint.config.js:55-95`.
  - Keep existing alias deep-import restriction.
  - Add a guard for relative cross-feature internals, either through `no-restricted-imports` patterns or a dedicated test if ESLint cannot express it clearly.
- Create `web/src/test/feature-boundaries.test.ts`.
  - Scan `web/src/features/**` for relative imports into another feature's `api`, `model`, `state`, or `ui` directories.
  - Allow same-feature relative imports and public index alias imports.
  - Assert no `moduleKeep` import pattern remains after CSS cleanup task.
- Add/modify tests:
  - `web/src/app/AppRoutes.test.tsx` — asserts route tree contains `/`, `/search`, `/signal-lab`, `/watchlist`, `/stocks`, and `/token/:targetType/:targetId`.
  - `web/src/features/live/useLiveData.test.tsx` or existing live integration tests — assert API hooks still request bootstrap/status/recent/token radar data.
  - `web/src/test/feature-boundaries.test.ts` — blocks future boundary regression.

### Design Tokens And Shared Case Primitives

- Modify `web/src/styles/tokens.css:1-23`.
  - Replace current color-only tokens with Obsidian semantic tokens.
  - Preserve aliases for generic text/panel variables only if they point to new semantic names and are not old-theme compatibility paths.
  - Required token shape:
    ```css
    :root {
      color-scheme: dark;
      --void: #070908;
      --obsidian: #0c100e;
      --slab: #121713;
      --slab-2: #171d18;
      --slab-3: #1e261f;
      --bone: #f1ead6;
      --bone-2: #d6cdb8;
      --ash: #9a9f92;
      --dim: #646b60;
      --line: #2a312a;
      --line-2: #394236;
      --opportunity: #d99a28;
      --opportunity-soft: #392910;
      --health: #58c98a;
      --health-soft: #123225;
      --info: #7bb5d8;
      --info-soft: #132c38;
      --risk: #d86679;
      --risk-soft: #3a1720;
      --agent: #b79ae8;
      --agent-soft: #291d3a;
      --radius: 7px;
      --sans: Inter, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", system-ui, sans-serif;
      --mono: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
    }
    ```
- Modify `web/src/styles/base.css`.
  - Apply `--void`, `--bone`, `--sans`, `--line`.
  - Ensure body background is restrained desk texture, not one-color flat or purple/blue gradient.
- Create `web/src/shared/ui/caseFile.tsx`.
  - Exports: `CaseFileShell`, `CaseFileHeader`, `CaseSection`, `CaseMetric`, `CaseFactGrid`, `CaseFact`, `CaseBadge`, `CaseActionBar`, `CaseEvidenceList`.
  - Props use formatted strings/ReactNode only; no feature imports.
  - Required type definitions:
    ```ts
    export type CaseTone = "opportunity" | "health" | "info" | "risk" | "agent" | "neutral";

    export type CaseFactItem = {
      label: string;
      value: React.ReactNode;
      detail?: React.ReactNode;
      tone?: CaseTone;
      source?: "official" | "deterministic" | "agent" | "market" | "social";
    };
    ```
- Create `web/src/shared/ui/caseFile.module.css`.
  - Owns only generic case primitives. No `.token-*`, `.signal-*`, `.watchlist-*`, or route-specific selectors.
  - Use CSS module class exports for primitives. `:global(...)` is allowed only for intentionally documented global primitives and should be rare.
- Modify `web/src/shared/ui/DecisionTag.tsx`.
  - Map decision tones to `CaseTone` variables.
  - Keep current decision labels, but remove old color-class dependence if duplicated in feature CSS.
- Add `web/src/shared/ui/CaseFile.test.tsx`.
  - Assert `CaseBadge` has accessible text.
  - Assert `CaseFactGrid` renders source labels when provided.
  - Run axe on `CaseFileShell` with header, section, facts, actions.

### Token Radar And Selected Case

- Create `web/src/features/live/model/tokenCase.ts`.
  - Convert `TokenFlowItem` into `TokenCaseView`.
  - Move current helper logic from `TokenRadarRow.tsx:114-316` into pure functions.
  - Required shape:
    ```ts
    export type TokenCaseView = {
      key: string;
      identity: {
        title: string;
        subtitle: string;
        status: string;
      };
      official: {
        description: string | null;
        links: Array<{ label: string; url: string }>;
        source: "official";
      };
      community: {
        headline: string;
        detail: string;
        mentions: number;
        independentAuthors: number;
        watchedMentions: number | null;
      };
      narrative: {
        headline: string;
        detail: string;
        risks: string[];
        source: "deterministic" | "agent" | "unavailable";
      };
      market: {
        headline: string;
        detail: string;
        direction: "up" | "down" | "flat";
      };
      decision: {
        label: TokenFlowItem["opportunity"]["decision"];
        score: number;
        reasons: string[];
        risks: string[];
      };
    };

    export const toTokenCaseView = (item: TokenFlowItem): TokenCaseView => {
      // Implementation uses existing TokenFlowItem profile, identity, social_heat,
      // discussion_quality, propagation, market, timing, and opportunity fields.
    };
    ```
- Add `web/src/features/live/model/tokenCase.test.ts`.
  - Use existing token radar fixtures or minimal `TokenFlowItem` builder.
  - Test `official.description` and `official.links` come from `item.profile`.
  - Test community headline includes mention/author proof.
  - Test narrative is deterministic/unavailable when no agent source exists.
  - Test decision preserves API score and risks.
- Modify `web/src/features/live/ui/TokenRadarTable.tsx:7-13`.
  - Replace user-facing sort labels:
    - `opportunity` -> `Opportunity`
    - `heat` -> `Community`
    - `quality` -> `Signal`
    - `propagation` -> `Spread`
    - `timing` -> `Timing Risk`
  - Replace table headers at `web/src/features/live/ui/TokenRadarTable.tsx:61-71` with `Identity`, `Community`, `Narrative`, `Decision`, `Actions`.
- Modify `web/src/features/live/ui/TokenRadarRow.tsx:1-316`.
  - Render `toTokenCaseView(item)`.
  - Remove row-local heat/quality/propagation/market/timing helper functions.
  - Keep venue link and Search Intel icon action.
  - Primary row click still selects token and visual selected state remains stable.
- Modify `web/src/features/live/ui/TokenDetailDrawer.tsx:35-273`.
  - Replace tab-first selected-token drawer with selected case header and sections:
    - `Official Profile`
    - `Community Proof`
    - `Narrative`
    - `Social x Market`
    - `Decision`
    - `Evidence`
  - Keep timeline/posts/score/accounts as secondary sections below the case summary, not as first-level navigation.
  - Empty state copy changes from `Select Token` to `Select Case`.
  - Search Intel stays primary action.
- Modify `web/src/features/live/ui/live.module.css`.
  - Remove old metric table grid classes tied to `heat-cell`, `quality-cell`, `propagation-cell`, `timing-cell` if they are no longer rendered.
  - Add stable row grid with responsive constraints so long token names/descriptions wrap without overlap.
- Update tests:
  - `web/src/features/live/ui/TokenRadarRow.test.tsx`
  - Rename/update `web/src/features/live/__tests__/CockpitApp.integration.test.tsx` to `web/src/routes/__tests__/live.route.integration.test.tsx`
  - `web/src/features/live/ui/LivePage.routing.test.tsx` only if route expectations depend on old labels.

### Watchlist Feature

- Create `web/src/features/watchlist/index.ts`.
  - Public exports: `WatchlistPage`, `buildWatchlistAccountCases`, `parseWatchlistRouteState`, `serializeWatchlistRouteState`.
- Create `web/src/features/watchlist/model/watchlistCase.ts`.
  - Derive account cases from handles, unread counts, live events, and existing token/entity records.
  - Required signature:
    ```ts
    export type WatchlistAccountCase = {
      handle: string;
      unreadCount: number;
      lastSeenAtMs: number | null;
      recentEventCount: number;
      tokenMentions: Array<{ label: string; detail: string; searchQuery: string }>;
      narrativeClusters: Array<{ label: string; count: number; tone: CaseTone }>;
      evidence: Array<{ id: string; text: string; receivedAtMs: number; searchQuery: string }>;
    };

    export const buildWatchlistAccountCases = (input: {
      handles: string[];
      accountUnreadCounts?: Record<string, number> | null;
      liveItems: LivePayload[];
    }): WatchlistAccountCase[] => {
      // Reuses current dedupe/sort semantics from web/src/lib/watchlist.ts.
    };
    ```
- Move or replace `web/src/lib/watchlist.ts:1-64`.
  - Either delete it and import from `@features/watchlist`, or keep only a thin exported domain-neutral function if no feature import cycle is introduced.
  - Do not leave `WatchlistRow` as the primary account detail contract.
- Create `web/src/features/watchlist/state/watchlistRouteState.ts`.
  - Parse/serialize `handle`, `window`, `scope`.
- Create `web/src/features/watchlist/ui/WatchlistPage.tsx`.
  - Layout: account case list left/main, selected account file right/main depending viewport.
  - Uses shared case primitives.
  - Selected handle empty state chooses first account or shows “No watched account selected”.
- Create `web/src/features/watchlist/ui/WatchlistAccountFile.tsx`.
  - Shows recent evidence, token mentions, narrative clusters, unread state, Search Intel links.
- Create `web/src/features/watchlist/ui/watchlist.module.css`.
  - Route-specific layout only.
- Add `web/src/features/watchlist/model/watchlistCase.test.ts`.
  - Dedupe/lowercase handles.
  - Sort unread first, then most recent event, then configured order.
  - Extract token mention labels from events/entities/token intents without inventing missing facts.
- Add `web/src/features/watchlist/ui/WatchlistPage.test.tsx`.
  - Render `/watchlist?handle=...` with MSW/live fixture and assert selected account file content.
- Modify `web/src/shared/routing/paths.ts:1-77`.
  - Add:
    ```ts
    export function watchlistPath(params: { handle?: string | null; window?: WindowKey; scope?: ScopeKey } = {}): string {
      const search = compactSearch(params);
      return "/watchlist" + (search ? `?${search}` : "");
    }
    ```
- Modify `web/src/features/cockpit/ui/CockpitSideRail.tsx:1-185`.
  - Add Watchlist as view button.
  - Make watchlist row links use `watchlistPath({ handle: row.handle })`.
  - Active handle comes from `/watchlist`, not `/signal-lab`.
- Modify `web/src/routes/watchlist.route.tsx`.
  - Import `WatchlistPage`.
  - Build `watchlistCases` using new feature model.
  - Export `WatchlistRoute` for `AppRoutes`.
  - Route element shape:
    ```tsx
    export function WatchlistRoute() {
      return <WatchlistPage cases={watchlistCases} liveItems={liveItems} />;
    }
    ```
  - Keep `/signal-lab?handle` as Signal Pulse filter only; account file detail is canonical on `/watchlist?handle=...`.
- Add e2e `web/e2e/golden-paths/watchlist-account-case.spec.ts`.
  - Start at `/`, click Watchlist rail button, assert URL `/watchlist`.
  - Select an account, assert account file, token mentions, and Search Intel link.

### Search Intel Case Layout

- Create `web/src/features/search/model/searchCase.ts`.
  - Convert `SearchInspectData` into branch-safe case sections.
  - Required export:
    ```ts
    export type SearchCaseView =
      | { kind: "token"; title: string; facts: CaseFactItem[]; sections: SearchCaseSection[] }
      | { kind: "topic"; title: string; facts: CaseFactItem[]; sections: SearchCaseSection[] }
      | { kind: "ambiguous"; title: string; facts: CaseFactItem[]; candidates: SearchTargetCandidate[] };
    ```
- Add `web/src/features/search/model/searchCase.test.ts`.
  - Token result maps official/profile facts separately from agent brief.
  - Ambiguous result keeps candidates visible.
  - Topic result does not render market facts as token facts.
- Modify `web/src/features/search/ui/SearchIntelPage.tsx:40-260`.
  - Keep route parsing/query/market subscription behavior.
  - Render `SearchCaseView` through shared `CaseFileShell`, `CaseSection`, and `CaseFactGrid`.
  - Sidebar becomes compact case index/resolver panel rather than dominant control wall.
- Modify `web/src/features/search/ui/SearchAgentBrief.tsx`.
  - Label as `Agent Memo`.
  - Keep recommendation/stance source visible.
- Modify `web/src/features/search/ui/SearchTimelinePanel.tsx` and `SearchTwitterResults.tsx` only to align evidence list styling with case primitives.
- Modify `web/src/features/search/ui/search.module.css`.
  - Remove route-only card language that duplicates shared case primitives.
  - Ensure `Search Intel` layout works at desktop and narrow widths without text overlap.
- Update tests:
  - `web/src/features/search/ui/__tests__/SearchIntelPage.routing.test.tsx`
  - `web/src/features/search/ui/__tests__/SearchAgentBrief.test.tsx`
  - Add axe assertion for token result page if not already covered.

### Signal Pulse Memo-First UI

- Create `web/src/features/signal-lab/model/pulseCase.ts`.
  - Convert `SignalPulseItem` into memo-first `PulseCaseView`.
  - Required shape:
    ```ts
    export type PulseCaseView = {
      candidateId: string;
      subject: string;
      stage: SignalPulseItem["pulse_status"];
      gate: {
        score: string;
        status: string;
        blockedReasons: string[];
      };
      agentMemo: {
        recommendation: string;
        summary: string;
        primaryReasons: string[];
        upgradeConditions: string[];
        invalidationConditions: string[];
        residualRisks: string[];
      };
      factLedger: CaseFactItem[];
      sourceEvents: string[];
      actions: Array<{ label: string; url: string }>;
      debugFacts: unknown;
    };
    ```
- Add `web/src/features/signal-lab/model/pulseCase.test.ts`.
  - Agent recommendation summary maps to memo.
  - Fact card maps to fact ledger.
  - Gate blocked reasons merge item gate + factor snapshot gate.
  - Debug JSON is present in model but not primary fact list.
- Modify `web/src/features/signal-lab/ui/SignalLabWorkbench.tsx:15-208`.
  - Keep status filtering behavior.
  - Change copy/layout from “Signal Lab workbench/status grid” to “Signal Pulse Queue” with stage explanations, counts, and candidate rows.
  - Use `PulseCaseView` for row summary where possible.
- Modify `web/src/features/signal-lab/ui/SignalLabPulse.tsx`.
  - Render candidate rows with stage/gate/agent verdict/fact chips/actions.
- Modify `web/src/features/signal-lab/ui/SignalLabInspector.tsx:21-247`.
  - Replace card stack order with:
    1. `Agent Memo`
    2. `Fact Ledger`
    3. `Gate And Data Health`
    4. `Source Events`
    5. `Actions`
    6. `Debug Facts` disclosure
  - Remove primary raw `factor_snapshot`, `gate`, `playbooks` cards from normal scan path.
- Modify `web/src/features/signal-lab/ui/PulseDetailPage.tsx`.
  - Ensure deep route `/signal-lab/pulse/:candidateId` uses the same inspector layout.
- Modify `web/src/features/signal-lab/ui/signalLab.module.css`.
  - Remove JSON-first visual hierarchy classes that are no longer used.
- Update tests:
  - `web/src/features/signal-lab/ui/SignalLabInspector.test.tsx`
  - `web/src/features/signal-lab/ui/SignalLabPulse.test.tsx`
  - `web/src/features/signal-lab/ui/__tests__/PulseDetailPage.routing.test.tsx`
  - `web/src/features/signal-lab/ui/__tests__/SignalLabPage.routing.test.tsx`
- Add e2e `web/e2e/golden-paths/signal-pulse-case.spec.ts`.
  - Open `/signal-lab`, select a candidate, assert agent memo/fact ledger/source events.
  - Open `/signal-lab/pulse/<candidateId>`, assert same selected case grammar.

### Hard-Cut Cleanup

- Rename `web/src/lib/types/legacy-ui.ts` to `web/src/lib/types/view-contracts.ts`.
  - Modify `web/src/lib/types/index.ts:24-89`: change the comment to `local-view-contract: frontend-owned view models that extend current OpenAPI schemas.` and change the export source from `./legacy-ui` to `./view-contracts` while keeping the existing named export list unchanged.
  - Do not change generated `openapi.ts`.
- Remove old user-facing strings from feature UI:
  - `selected token`
  - `Select Token`
  - Radar headers `Heat`, `Quality`, `Propagation`, `Timing`
  - JSON card titles as primary visible headings: `factor_snapshot`, `gate`, `playbooks`
- Remove or rename obsolete CSS selectors in:
  - `web/src/features/live/ui/live.module.css`
  - `web/src/features/cockpit/ui/cockpit.module.css`
  - `web/src/features/signal-lab/ui/signalLab.module.css`
  - `web/src/features/search/ui/search.module.css`
  - `web/src/shared/ui/shared.module.css`
- Update `docs/FRONTEND.md:5-62`.
  - Add Watchlist route to UI verification gate.
  - Replace “compatibility UI payload types” wording with “frontend view contracts”.
  - Document Obsidian Desk case-file grammar and no-dual-renderer rule.
- Update `web/src/test/app-test-case-matrix.md` if it already tracks route expectations.
- Cleanup scan command:
  ```bash
  rg -n "selected token|Select Token|\\bHeat\\b|\\bQuality\\b|\\bPropagation\\b|factor_snapshot|legacy-ui|compatibility UI" web/src docs/FRONTEND.md
  ```
  Expected: no old user-facing UI references. Internal API enum values may remain only in model tests or type names with comments explaining they are API sort modes, not compatibility UI.

## Task Checklist

### Task 0: Audit-Aligned Architecture Groundwork

**Files:**
- Modify: `web/src/app/AppRoutes.tsx`
- Modify: `web/src/app/CockpitApp.tsx`
- Create: `web/src/features/cockpit/ui/CockpitFrame.tsx`
- Modify: `web/src/features/cockpit/index.ts`
- Modify: `web/src/routes/live.route.tsx`
- Modify: `web/src/routes/search.route.tsx`
- Modify: `web/src/routes/signal-lab.route.tsx`
- Modify: `web/src/routes/signal-lab.pulse.route.tsx`
- Create: `web/src/routes/watchlist.route.tsx`
- Modify: `web/src/features/live/useLiveData.ts`
- Modify: `web/src/features/live/useLiveSelection.ts`
- Modify: `web/src/features/notifications/useNotificationsController.ts`
- Modify: `web/src/shared/routing/paths.ts`
- Modify: `web/eslint.config.js`
- Create: `web/src/test/feature-boundaries.test.ts`
- Test: `web/src/app/AppRoutes.test.tsx`

- [ ] Write failing `web/src/test/feature-boundaries.test.ts` that fails on the current relative cross-feature imports from `live` into `cockpit/search` and from `notifications` into `cockpit`.
- [ ] Write failing `web/src/app/AppRoutes.test.tsx` that expects route-owned entries for `/`, `/search`, `/signal-lab`, `/watchlist`, `/stocks`, and `/token/:targetType/:targetId`.
- [ ] Run:
  ```bash
  npm --prefix web run test -- \
    web/src/test/feature-boundaries.test.ts \
    web/src/app/AppRoutes.test.tsx
  ```
  Expected: fail before route/boundary refactor.
- [ ] Move route-tree ownership out of `CockpitApp` into `AppRoutes` and route modules.
- [ ] Create `CockpitFrame` so routes pass shell slots instead of routing through one monolithic cockpit component.
- [ ] Move direct live API calls into feature API hooks and consume Signal Pulse compact data through the Signal Lab public API layer.
- [ ] Move `tokenSearchPath`/`tokenSearchQuery` to `shared/routing/paths.ts` or expose through `@features/search`; remove relative import from `live`.
- [ ] Move mobile route task contracts to `@features/cockpit` public exports or `shared/routing/routeTasks.ts`; remove relative imports from `live` and `notifications`.
- [ ] Add ESLint or test guard for future relative cross-feature internal imports.
- [ ] Run:
  ```bash
  npm --prefix web run test -- \
    web/src/test/feature-boundaries.test.ts \
    web/src/app/AppRoutes.test.tsx \
    web/src/routes/__tests__/live.route.integration.test.tsx
  npm --prefix web run lint
  npm --prefix web run typecheck
  ```
  Expected: pass.
- [ ] Commit: `git add web/src/app web/src/routes web/src/features/cockpit web/src/features/live web/src/features/notifications web/src/shared/routing web/src/test web/eslint.config.js && git commit -m "refactor(web): make routes own cockpit surfaces"`.

### Task 1: Shared Obsidian Case Language And CSS Boundary

**Files:**
- Modify: `web/src/styles/tokens.css`
- Modify: `web/src/styles/base.css`
- Create: `web/src/shared/ui/caseFile.tsx`
- Create: `web/src/shared/ui/caseFile.module.css`
- Modify: `web/src/shared/ui/DecisionTag.tsx`
- Test: `web/src/shared/ui/CaseFile.test.tsx`

- [ ] Write failing `CaseFile.test.tsx` for fact source labels, badge tones, and axe.
- [ ] Run `npm --prefix web run test -- web/src/shared/ui/CaseFile.test.tsx`; expected failure because components do not exist.
- [ ] Implement `caseFile.tsx` and `caseFile.module.css`.
- [ ] Replace global tokens in `tokens.css` and `base.css`.
- [ ] Update `DecisionTag.tsx` to use semantic tone classes.
- [ ] Verify new primitives are imported by components through normal CSS module bindings or explicit shared primitive exports, not by adding another `moduleKeep` entry to `main.tsx`.
- [ ] Run `rg -n "moduleKeep|:global\\(" web/src/shared/ui/caseFile.module.css web/src/main.tsx`; expected: no new `moduleKeep`, and any `:global(...)` in `caseFile.module.css` has a short comment explaining why it is global.
- [ ] Run `npm --prefix web run test -- web/src/shared/ui/CaseFile.test.tsx web/src/shared/ui/RemoteState.test.tsx`; expected pass.
- [ ] Run `npm --prefix web run typecheck`; expected pass.
- [ ] Commit: `git add web/src/styles web/src/shared/ui && git commit -m "feat(web): add obsidian case file primitives"`.

### Task 2: Token Radar Item And Selected Case

**Files:**
- Create: `web/src/features/live/model/tokenCase.ts`
- Test: `web/src/features/live/model/tokenCase.test.ts`
- Modify: `web/src/features/live/ui/TokenRadarTable.tsx`
- Modify: `web/src/features/live/ui/TokenRadarRow.tsx`
- Modify: `web/src/features/live/ui/TokenDetailDrawer.tsx`
- Modify: `web/src/features/live/ui/live.module.css`
- Test: `web/src/features/live/ui/TokenRadarRow.test.tsx`
- Test: `web/src/routes/__tests__/live.route.integration.test.tsx`

- [ ] Write `tokenCase.test.ts` for official/community/narrative/market/decision mapping.
- [ ] Run `npm --prefix web run test -- web/src/features/live/model/tokenCase.test.ts`; expected failure.
- [ ] Implement `toTokenCaseView`.
- [ ] Run model test; expected pass.
- [ ] Update `TokenRadarTable` labels and headers.
- [ ] Update `TokenRadarRow` to render `TokenCaseView`.
- [ ] Update `TokenDetailDrawer` to selected-case sections.
- [ ] Update live CSS and remove old rendered metric-cell selectors.
- [ ] Update row/integration tests to assert `Identity`, `Community`, `Narrative`, `Decision`, `Select Case`, `Official Profile`, `Search Intel`.
- [ ] Run:
  ```bash
  npm --prefix web run test -- \
    web/src/features/live/model/tokenCase.test.ts \
    web/src/features/live/ui/TokenRadarRow.test.tsx \
    web/src/routes/__tests__/live.route.integration.test.tsx
  ```
  Expected: pass.
- [ ] Commit: `git add web/src/features/live && git commit -m "feat(web): hard cut token radar to case rows"`.

### Task 3: Watchlist First-Class Page

**Files:**
- Create: `web/src/features/watchlist/index.ts`
- Create: `web/src/features/watchlist/model/watchlistCase.ts`
- Create: `web/src/features/watchlist/model/watchlistCase.test.ts`
- Create: `web/src/features/watchlist/state/watchlistRouteState.ts`
- Create: `web/src/features/watchlist/ui/WatchlistPage.tsx`
- Create: `web/src/features/watchlist/ui/WatchlistAccountFile.tsx`
- Create: `web/src/features/watchlist/ui/watchlist.module.css`
- Modify or delete: `web/src/lib/watchlist.ts`
- Modify: `web/src/shared/routing/paths.ts`
- Modify: `web/src/features/cockpit/ui/CockpitSideRail.tsx`
- Modify: `web/src/features/cockpit/ui/CockpitSideRail.test.tsx`
- Modify: `web/src/routes/watchlist.route.tsx`
- Modify: `web/src/app/AppRoutes.tsx`
- E2E: `web/e2e/golden-paths/watchlist-account-case.spec.ts`

- [ ] Write `watchlistCase.test.ts` for handle normalization, sorting, token mention extraction, empty clusters.
- [ ] Run model test; expected failure.
- [ ] Implement `buildWatchlistAccountCases`.
- [ ] Add route-state parser/serializer tests if route logic is more than one function.
- [ ] Add `watchlistPath` and unit coverage through side rail test.
- [ ] Implement `WatchlistPage` and `WatchlistAccountFile`.
- [ ] Wire Cockpit side rail and route-owned `/watchlist` entry through `AppRoutes`.
- [ ] Update side rail test to assert Watchlist view button and watchlist row link target `/watchlist?handle=...`.
- [ ] Add Playwright golden path with MSW fixture.
- [ ] Run:
  ```bash
  npm --prefix web run test -- \
    web/src/features/watchlist/model/watchlistCase.test.ts \
    web/src/features/watchlist/ui/WatchlistPage.test.tsx \
    web/src/features/cockpit/ui/CockpitSideRail.test.tsx
  npm --prefix web run test:e2e -- web/e2e/golden-paths/watchlist-account-case.spec.ts
  ```
  Expected: pass.
- [ ] Commit: `git add web/src/features/watchlist web/src/shared/routing web/src/features/cockpit web/src/routes web/src/app web/e2e && git commit -m "feat(web): add watchlist account case route"`.

### Task 4: Search Intel Case Layout

**Files:**
- Create: `web/src/features/search/model/searchCase.ts`
- Create: `web/src/features/search/model/searchCase.test.ts`
- Modify: `web/src/features/search/ui/SearchIntelPage.tsx`
- Modify: `web/src/features/search/ui/SearchAgentBrief.tsx`
- Modify: `web/src/features/search/ui/SearchTimelinePanel.tsx`
- Modify: `web/src/features/search/ui/SearchTwitterResults.tsx`
- Modify: `web/src/features/search/ui/search.module.css`
- Test: `web/src/features/search/ui/__tests__/SearchIntelPage.routing.test.tsx`
- Test: `web/src/features/search/ui/__tests__/SearchAgentBrief.test.tsx`

- [ ] Write `searchCase.test.ts` for token/topic/ambiguous branches.
- [ ] Run model test; expected failure.
- [ ] Implement `toSearchCaseView`.
- [ ] Update Search Intel page to render shared case sections while preserving route/query behavior.
- [ ] Update Search Agent Brief label to `Agent Memo`.
- [ ] Align timeline/twitter evidence styling.
- [ ] Update tests to assert resolver remains available and token case sections render.
- [ ] Run:
  ```bash
  npm --prefix web run test -- \
    web/src/features/search/model/searchCase.test.ts \
    web/src/features/search/ui/__tests__/SearchIntelPage.routing.test.tsx \
    web/src/features/search/ui/__tests__/SearchAgentBrief.test.tsx
  ```
  Expected: pass.
- [ ] Commit: `git add web/src/features/search && git commit -m "feat(web): align search intel with case files"`.

### Task 5: Signal Pulse Memo-First UI

**Files:**
- Create: `web/src/features/signal-lab/model/pulseCase.ts`
- Create: `web/src/features/signal-lab/model/pulseCase.test.ts`
- Modify: `web/src/features/signal-lab/ui/SignalLabWorkbench.tsx`
- Modify: `web/src/features/signal-lab/ui/SignalLabPulse.tsx`
- Modify: `web/src/features/signal-lab/ui/SignalLabInspector.tsx`
- Modify: `web/src/features/signal-lab/ui/PulseDetailPage.tsx`
- Modify: `web/src/features/signal-lab/ui/signalLab.module.css`
- Test: `web/src/features/signal-lab/ui/SignalLabInspector.test.tsx`
- Test: `web/src/features/signal-lab/ui/SignalLabPulse.test.tsx`
- Test: `web/src/features/signal-lab/ui/__tests__/PulseDetailPage.routing.test.tsx`
- E2E: `web/e2e/golden-paths/signal-pulse-case.spec.ts`

- [ ] Write `pulseCase.test.ts` for agent memo, fact ledger, merged blocked reasons, debug facts.
- [ ] Run model test; expected failure.
- [ ] Implement `toPulseCaseView`.
- [ ] Update Signal Pulse list rows to consume `PulseCaseView`.
- [ ] Update inspector and pulse detail page to memo-first order.
- [ ] Keep raw JSON only under `Debug Facts` disclosure if still needed.
- [ ] Update unit/route tests.
- [ ] Add Playwright golden path.
- [ ] Run:
  ```bash
  npm --prefix web run test -- \
    web/src/features/signal-lab/model/pulseCase.test.ts \
    web/src/features/signal-lab/ui/SignalLabInspector.test.tsx \
    web/src/features/signal-lab/ui/SignalLabPulse.test.tsx \
    web/src/features/signal-lab/ui/__tests__/PulseDetailPage.routing.test.tsx
  npm --prefix web run test:e2e -- web/e2e/golden-paths/signal-pulse-case.spec.ts
  ```
  Expected: pass.
- [ ] Commit: `git add web/src/features/signal-lab web/e2e && git commit -m "feat(web): make signal pulse memo first"`.

### Task 6: Hard-Cut Cleanup, Docs, And Visual QA

**Files:**
- Rename: `web/src/lib/types/legacy-ui.ts` -> `web/src/lib/types/view-contracts.ts`
- Modify: `web/src/lib/types/index.ts`
- Modify: `docs/FRONTEND.md`
- Modify: `web/src/test/app-test-case-matrix.md` if route matrix needs update
- Modify: `web/src/main.tsx`
- Modify CSS modules as cleanup requires

- [ ] Rename local UI type contract and update imports.
- [ ] Remove `moduleKeep` imports/classes from `web/src/main.tsx` once feature CSS is locally imported by components or replaced by shared primitives.
- [ ] Run CSS global scan:
  ```bash
  rg -n ":global\\(|moduleKeep|document\\.documentElement\\.classList\\.add" web/src
  ```
  Expected: only deliberate shared/global primitive selectors remain; no feature-level `moduleKeep` pattern remains.
- [ ] Run old-copy scan:
  ```bash
  rg -n "selected token|Select Token|\\bHeat\\b|\\bQuality\\b|\\bPropagation\\b|factor_snapshot|legacy-ui|compatibility UI" web/src docs/FRONTEND.md
  ```
  Expected: no user-facing old UI references. If API enum names remain in model code, add a nearby comment explaining they map backend sort modes to new labels.
- [ ] Update `docs/FRONTEND.md` with Obsidian Desk grammar, Watchlist route, and verification checklist.
- [ ] Update `docs/FRONTEND.md` to reflect the audited architecture: route modules own route orchestration, `app/` owns providers/routes only, feature model adapters own case semantics, and feature CSS must not rely on broad `:global(...)` selectors.
- [ ] Run:
  ```bash
  npm --prefix web run lint
  npm --prefix web run typecheck
  npm --prefix web run test
  npm --prefix web run build
  ```
  Expected: pass.
- [ ] Start local dev server:
  ```bash
  npm --prefix web run dev -- --host 127.0.0.1 --port 5173
  ```
- [ ] Browser QA with screenshots:
  - `/`
  - `/search?q=HYPE&window=24h&scope=all`
  - `/watchlist`
  - `/watchlist?handle=<fixture-handle>`
  - `/signal-lab`
  - `/signal-lab/pulse/<fixture-candidate-id>`
  - `/token/<fixture-target-type>/<fixture-target-id>`
- [ ] Run e2e:
  ```bash
  npm --prefix web run test:e2e
  ```
- [ ] Run final repository gate:
  ```bash
  make check-all
  ```
- [ ] Record verification in `docs/superpowers/plans/active/2026-05-13-obsidian-desk-ui-hard-cut-verification.md` with full command outputs, Coverage, Skipped tests, E2E golden path, screenshots, residual risks.
- [ ] Commit: `git add web docs && git commit -m "chore(web): finish obsidian desk hard cut cleanup"`.

## PR Breakdown

1. **PR 0 — Route ownership and architecture guardrails**: Task 0. Mergeable before UI work; proves route modules, feature boundaries, and API-hook ownership are aligned with the audit.
2. **PR 1 — Case primitives and tokens**: Task 1. Depends on PR 0. Mergeable on its own if route tests still pass.
3. **PR 2 — Token Radar and Selected Case**: Task 2. Depends on PR 1. Removes the old metric-table user experience.
4. **PR 3 — Watchlist account case route**: Task 3. Depends on PR 0 and PR 1; should be mergeable independently from Search/Signal changes.
5. **PR 4 — Search Intel case layout**: Task 4. Depends on PR 1.
6. **PR 5 — Signal Pulse memo-first and hard-cut cleanup**: Tasks 5 and 6. Depends on PRs 0-4 because cleanup scan must run after all surfaces migrate.

If a single PR is preferred, keep the same internal commit order and still run verification after each task.

## Rollout Order

1. Merge route ownership and architecture guardrails.
2. Merge shared tokens/case primitives.
3. Merge Token Radar/Selected Case hard cut.
4. Merge Watchlist first-class route.
5. Merge Search Intel case layout.
6. Merge Signal Pulse memo-first UI.
7. Merge cleanup/docs/verification.

No migrations or backend deploy ordering are required.

## Rollback

- PR 0 rollback: revert route-ownership split and boundary-test commit; do this before reverting dependent UI PRs.
- PR 1 rollback: revert shared primitive/token commit; dependent UI PRs must be reverted first.
- PR 2 rollback: revert Token Radar/Selected Case commit; Search/Watchlist/Signal can remain if independent.
- PR 3 rollback: remove `/watchlist` route and side rail link by reverting PR 3.
- PR 4 rollback: revert Search UI case layout; `/search` API behavior unchanged.
- PR 5 rollback: revert Signal Pulse UI and cleanup; if `legacy-ui.ts` rename causes package import issues, restore file name and `index.ts` export in one commit.

Because this is frontend-only, rollback is code revert plus redeploy; no data repair is required.

## Acceptance Test Commands

- **Architecture Review P1/P2:**  
  ```bash
  npm --prefix web run test -- \
    web/src/test/feature-boundaries.test.ts \
    web/src/app/AppRoutes.test.tsx
  npm --prefix web run lint
  rg -n "../cockpit/(model|state|ui|api)|../search/(model|state|ui|api)|../signal-lab/(model|state|ui|api)|../live/(model|state|ui|api)" web/src/features
  ```
  Expected: tests and lint pass; grep returns no cross-feature internal relative imports.
- **AC1/AC2/AC3:**  
  ```bash
  npm --prefix web run test -- \
    web/src/features/live/model/tokenCase.test.ts \
    web/src/features/live/ui/TokenRadarRow.test.tsx \
    web/src/routes/__tests__/live.route.integration.test.tsx
  ```
- **AC4:**  
  ```bash
  npm --prefix web run test -- \
    web/src/features/search/model/searchCase.test.ts \
    web/src/features/search/ui/__tests__/SearchIntelPage.routing.test.tsx
  ```
- **AC5/AC6:**  
  ```bash
  npm --prefix web run test -- \
    web/src/features/watchlist/model/watchlistCase.test.ts \
    web/src/features/watchlist/ui/WatchlistPage.test.tsx \
    web/src/features/cockpit/ui/CockpitSideRail.test.tsx
  npm --prefix web run test:e2e -- web/e2e/golden-paths/watchlist-account-case.spec.ts
  ```
- **AC7/AC8:**  
  ```bash
  npm --prefix web run test -- \
    web/src/features/signal-lab/model/pulseCase.test.ts \
    web/src/features/signal-lab/ui/SignalLabInspector.test.tsx \
    web/src/features/signal-lab/ui/SignalLabPulse.test.tsx
  npm --prefix web run test:e2e -- web/e2e/golden-paths/signal-pulse-case.spec.ts
  ```
- **AC9:**  
  ```bash
  rg -n "selected token|Select Token|\\bHeat\\b|\\bQuality\\b|\\bPropagation\\b|factor_snapshot|legacy-ui|compatibility UI" web/src docs/FRONTEND.md
  rg -n ":global\\(|moduleKeep|document\\.documentElement\\.classList\\.add" web/src
  ```
  Expected: no old user-facing UI references; no feature-level `moduleKeep` pattern; intentional backend enum references and deliberate shared globals documented.
- **AC10:**  
  ```bash
  npm --prefix web run lint
  npm --prefix web run typecheck
  npm --prefix web run test
  npm --prefix web run build
  npm --prefix web run test:e2e
  make check-all
  ```

## Verification

Create `docs/superpowers/plans/active/2026-05-13-obsidian-desk-ui-hard-cut-verification.md` before declaring implementation complete.

Required verification sections:

- `Command Output`: full output for lint, typecheck, tests, build, e2e, `make check-all`.
- `Architecture Guardrails`: output from `feature-boundaries.test.ts`, `AppRoutes.test.tsx`, cross-feature import scan, and CSS global/moduleKeep scan.
- `Coverage`: note new unit tests by model/UI area.
- `Skipped Tests`: explicitly list none, or every skipped case with reason.
- `E2E Golden Path`: list live cold load, search submit, watchlist account case, signal pulse case, existing notification navigation, radar-to-token-target.
- `Browser Visual QA`: include screenshots or paths for `/`, `/search`, `/watchlist`, `/watchlist?handle=...`, `/signal-lab`, `/signal-lab/pulse/...`, `/token/...`.
- `Residual Risks`: missing data fields, known visual compromises, or follow-up backend opportunities.

## Self-Review

- Spec coverage: Tasks 0-6 cover G1-G8, AC1-AC10, and the architecture review's P1/P2 findings.
- Placeholder scan: This plan avoids placeholder markers and unspecified “add tests” steps; all test files and commands are named.
- Type consistency: `CaseTone`, `CaseFactItem`, `TokenCaseView`, `WatchlistAccountCase`, `SearchCaseView`, and `PulseCaseView` are defined once and consumed by later tasks.
- Architecture consistency: Task 0 addresses route ownership, feature-boundary enforcement, live data ownership, and selection/navigation split before UI migration starts.
- Scope control: No migrations, new APIs, new backend workers, or new agent prompts are included.
