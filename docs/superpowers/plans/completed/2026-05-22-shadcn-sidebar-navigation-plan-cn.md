# Shadcn Sidebar Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the custom cockpit side rail/mobile route nav with a shadcn/ui Sidebar shell and make Token Radar row clicks route in the same tab.

**Architecture:** Add shadcn-owned shared UI primitives under `shared/ui`, introduce a data-driven `AppSidebar` in `features/cockpit`, and wrap cockpit/search shells in `SidebarProvider + SidebarInset`. Move global navigation into the sidebar and keep page filters inside page toolbars.

**Tech Stack:** React 19, React Router 6.30, Tailwind 4, shadcn/ui Sidebar, Radix Slot/Dialog/Tooltip, lucide-react, Vitest, React Testing Library, Playwright.

---

## File Structure

- Create `web/components.json`: shadcn CLI configuration aligned to existing aliases.
- Create `web/src/lib/utils.ts`: `cn()` helper for shadcn primitives.
- Create `web/src/shared/ui/sidebar.tsx`: copied and adapted shadcn Sidebar primitive.
- Create `web/src/shared/ui/sheet.tsx`: mobile offcanvas sheet primitive required by sidebar.
- Create `web/src/shared/ui/separator.tsx`: separator primitive required by sidebar.
- Create `web/src/shared/ui/tooltip.tsx`: tooltip primitive required by sidebar.
- Create `web/src/features/cockpit/ui/appNavigation.ts`: route metadata and badge keys.
- Create `web/src/features/cockpit/ui/AppSidebar.tsx`: sidebar rendering and active matching.
- Create `web/src/features/cockpit/ui/AppSidebar.css`: app-specific sidebar theme and layout overrides.
- Modify `web/src/features/cockpit/ui/CockpitShell.tsx`: use sidebar provider/inset.
- Modify `web/src/features/cockpit/ui/SearchShell.tsx`: share the sidebar shell.
- Modify `web/src/features/cockpit/ui/CockpitTopbar.tsx/css`: add sidebar trigger slot and preserve search/status controls.
- Modify `web/src/features/cockpit/ui/cockpitShell.css`: remove old fixed grid assumptions.
- Modify `web/src/features/cockpit/ui/cockpitShellContract.css`: replace `MobileRouteNav` contract with sidebar mobile contract.
- Modify `web/src/features/cockpit/ui/CockpitSideRail.tsx/css`: delete after replacement if imports are gone.
- Modify `web/src/features/cockpit/ui/MobileRouteNav.tsx`: delete after replacement if imports are gone.
- Modify `web/src/routes/AppRoutes.tsx`: reduce side rail props to sidebar badge counts.
- Modify `web/src/features/live/model/tokenRadarDetailLink.ts`: remove new-tab helper.
- Modify `web/src/features/live/ui/TokenRadarTable.tsx`: use React Router same-tab navigation.
- Modify tests under `web/tests/component/features/cockpit/ui`, `web/tests/component/features/live/ui`, `web/tests/routes`, and `web/tests/architecture`.

## Task 1: Radar Same-Tab Routing

**Files:**
- Modify: `web/src/features/live/model/tokenRadarDetailLink.ts`
- Modify: `web/src/features/live/ui/TokenRadarTable.tsx`
- Test: `web/tests/component/features/live/ui/TokenRadarTable.test.tsx`

- [ ] **Step 1: Write the failing test**

Replace the existing new-tab test with same-tab navigation expectations:

```tsx
it("routes token detail in the same tab from the compact action and whole row", () => {
  const item = mixedFreshnessToken();
  const onSelect = vi.fn();
  const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
  renderTokenRadarTable([item], { onSelect });

  const row = screen.getByRole("article", { name: "Token Radar item $TROLL" });
  const link = within(row).getByRole("link", { name: "Open token item $TROLL" });
  expect(link).toHaveAttribute(
    "href",
    "/token/Asset/asset%3Adex%3Aeth%3A0x1111111111111111111111111111111111111111",
  );
  expect(link).not.toHaveAttribute("target");

  fireEvent.click(row);

  expect(onSelect).toHaveBeenCalledWith(item);
  expect(openSpy).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Verify RED**

Run:

```bash
cd web && npm test -- --run tests/component/features/live/ui/TokenRadarTable.test.tsx
```

Expected: FAIL because current code sets `target="_blank"` and calls `window.open`.

- [ ] **Step 3: Implement same-tab routing**

Remove `openTokenRadarDetailInNewTab` and `_blank` link props. In `TokenRadarTable`, call `onSelect?.(row.original)` for row and keyboard activation. Keep external links unchanged.

- [ ] **Step 4: Verify GREEN**

Run the same test command. Expected: PASS.

## Task 2: Add Shadcn Sidebar Primitives

**Files:**
- Create: `web/components.json`
- Create: `web/src/lib/utils.ts`
- Create: `web/src/shared/ui/sidebar.tsx`
- Create: `web/src/shared/ui/sheet.tsx`
- Create: `web/src/shared/ui/separator.tsx`
- Create: `web/src/shared/ui/tooltip.tsx`
- Modify: `web/package.json`
- Modify: `web/package-lock.json`

- [ ] **Step 1: Install dependencies**

Run:

```bash
cd web && npm install @radix-ui/react-dialog @radix-ui/react-separator @radix-ui/react-slot @radix-ui/react-tooltip class-variance-authority tailwind-merge
```

Expected: package files update.

- [ ] **Step 2: Add primitives**

Use shadcn sidebar source as the starting point, adapted to:

```ts
import { cn } from "@lib/utils";
```

and imports from `@shared/ui/sheet`, `@shared/ui/separator`, and `@shared/ui/tooltip`.

- [ ] **Step 3: Verify primitive typecheck**

Run:

```bash
cd web && npm run typecheck
```

Expected: PASS or only failures from later missing shell integration if this task is run out of order.

## Task 3: Build Data-Driven AppSidebar

**Files:**
- Create: `web/src/features/cockpit/ui/appNavigation.ts`
- Create: `web/src/features/cockpit/ui/AppSidebar.tsx`
- Create: `web/src/features/cockpit/ui/AppSidebar.css`
- Test: `web/tests/component/features/cockpit/ui/AppSidebar.test.tsx`

- [ ] **Step 1: Write failing sidebar test**

Test that groups and subitems render:

```tsx
render(
  <MemoryRouter initialEntries={["/macro/assets/correlation"]}>
    <SidebarProvider>
      <AppSidebar badges={{ token: 4, stocks: 2, news: "8+" }} />
    </SidebarProvider>
  </MemoryRouter>,
);
expect(screen.getByRole("link", { name: /Token Radar/i })).toHaveAttribute("href", "/");
expect(screen.getByRole("link", { name: /Stocks/i })).toHaveTextContent("2");
expect(screen.getByRole("link", { name: /Correlation/i })).toHaveAttribute("aria-current", "page");
```

- [ ] **Step 2: Verify RED**

Run:

```bash
cd web && npm test -- --run tests/component/features/cockpit/ui/AppSidebar.test.tsx
```

Expected: FAIL because `AppSidebar` does not exist.

- [ ] **Step 3: Implement AppSidebar**

Define nav groups from the spec and render shadcn `SidebarGroup`, `SidebarMenu`, `SidebarMenuSub`, `SidebarMenuBadge`, and `NavLink` with `isActive`.

- [ ] **Step 4: Verify GREEN**

Run the same test command. Expected: PASS.

## Task 4: Replace Cockpit/Search Shells

**Files:**
- Modify: `web/src/features/cockpit/ui/CockpitShell.tsx`
- Modify: `web/src/features/cockpit/ui/SearchShell.tsx`
- Modify: `web/src/features/cockpit/ui/CockpitTopbar.tsx`
- Modify: `web/src/features/cockpit/ui/CockpitTopbar.css`
- Modify: `web/src/features/cockpit/ui/cockpitShell.css`
- Modify: `web/src/features/cockpit/ui/cockpitShellContract.css`
- Modify: `web/src/routes/AppRoutes.tsx`
- Test: `web/tests/routes/live-radar.route.test.tsx`
- Test: `web/tests/component/features/cockpit/ui/CockpitTopbar.test.tsx`

- [ ] **Step 1: Write route test updates**

Update route tests to assert sidebar links instead of old rail buttons:

```tsx
expect(await screen.findByRole("link", { name: /Token Radar/i })).toBeInTheDocument();
expect(screen.getByRole("link", { name: /Stocks/i })).toHaveTextContent("2");
expect(screen.getByRole("link", { name: /News/i })).toHaveTextContent("2+");
```

- [ ] **Step 2: Verify RED**

Run:

```bash
cd web && npm test -- --run tests/routes/live-radar.route.test.tsx tests/component/features/cockpit/ui/CockpitTopbar.test.tsx
```

Expected: FAIL because shell still renders old side rail/mobile nav.

- [ ] **Step 3: Implement shell replacement**

Wrap shell in:

```tsx
<SidebarProvider>
  <AppSidebar badges={sidebarBadges} />
  <SidebarInset>
    <CockpitTopbar {...topbar} />
    <section className="center-column">
      <Outlet />
    </section>
  </SidebarInset>
  <NotificationLayer {...notifications} />
</SidebarProvider>
```

Move `SidebarTrigger` into topbar brand/control area.

- [ ] **Step 4: Verify GREEN**

Run the same route/topbar test command. Expected: PASS.

## Task 5: Retire Old SideRail and MobileRouteNav Contracts

**Files:**
- Delete: `web/src/features/cockpit/ui/CockpitSideRail.tsx`
- Delete: `web/src/features/cockpit/ui/CockpitSideRail.css`
- Delete: `web/src/features/cockpit/ui/MobileRouteNav.tsx`
- Modify: `web/src/features/cockpit/index.ts`
- Modify: `web/tests/component/features/cockpit/ui/CockpitSideRail.test.tsx`
- Modify: `web/tests/architecture/cssArchitectureHarness.test.ts`
- Modify: `web/tests/architecture/cssResponsiveContract.test.ts`
- Modify: `web/tests/e2e/golden-paths/mobile-shell.spec.ts`
- Modify: `web/tests/e2e/golden-paths/tablet-shell.spec.ts`
- Modify: `web/tests/e2e/golden-paths/mobile-route-cold-load.spec.ts`

- [ ] **Step 1: Update tests away from old classes**

Replace assertions for `.desktop-side-rail` and `.mobile-route-nav` with sidebar landmarks, trigger, and offcanvas visibility.

- [ ] **Step 2: Verify RED**

Run:

```bash
cd web && npm run test:architecture
```

Expected: FAIL until CSS namespace and responsive contracts are updated.

- [ ] **Step 3: Delete old components and update exports**

Remove old files and exports after no imports remain.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
cd web && npm run test:architecture
```

Expected: PASS.

## Task 6: Full Verification

**Files:**
- Modify: `docs/superpowers/plans/active/2026-05-22-shadcn-sidebar-navigation-plan-cn.md`

- [ ] **Step 1: Run focused checks**

```bash
cd web && npm run lint
cd web && npm run typecheck
cd web && npm test -- --run
cd web && npm run build
```

- [ ] **Step 2: Run browser verification**

Start dev server:

```bash
cd web && npm run dev
```

Verify `/`, `/token/Asset/example?window=1h&scope=all`, `/stocks`, `/news`, `/macro`, `/watchlist`, `/ops`, `/search` at 1366, 834, and 390 widths.

- [ ] **Step 3: Record verification**

Append command outputs and manual notes to a verification section or a dedicated verification file before declaring completion.
