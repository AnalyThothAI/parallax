# Responsive Token Radar Cockpit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the `web/` cockpit so mobile opens on a usable Token Radar task, while desktop keeps the high-density three-column cockpit and business data flow stays unchanged.

**Architecture:** Keep the existing React data fetching, Zustand state, query keys, and API contracts intact. Add a small responsive shell layer around the current surfaces, introduce mobile task navigation for `radar | tape | lab | detail`, and rewrite the CSS breakpoints so desktop/tablet/mobile have explicit layout rules instead of stacked compatibility patches.

**Tech Stack:** React 19, TypeScript, Vite, TanStack Query, Zustand, lucide-react, Vitest, Testing Library, CSS media queries.

---

## Scope Guard

This plan must not change backend behavior or business logic.

Do not change:

- `src/parallax/**`
- API endpoint paths or request params
- `useTraderStore` persisted field names, except adding a UI-only `mobileTask` state if chosen
- token sorting math in `sortTokenItems`
- search intent rules in `tokenForSearchQuery`
- Signal Lab chain merging or scoring helpers
- `TokenFlowItem`, `SignalLabChain`, or API response types

Allowed changes:

- DOM structure and class names needed for responsive layout
- UI-only task state in `web/src/App.tsx` or `web/src/store/useTraderStore.ts`
- presentational classes in Token Radar rows
- CSS layout, responsive breakpoints, and visual states
- frontend tests that prove existing behavior still works

## File Structure

Modify:

- `web/src/App.tsx`: owns cockpit shell composition, selected object routing, mobile task transitions, and rendering surfaces in desktop/tablet/mobile containers.
- `web/src/components/TokenRadarTable.tsx`: keeps the single Token Radar component, adds responsive-friendly wrapper labels and testable toolbar semantics.
- `web/src/components/TokenRadarRow.tsx`: keeps token business formatting, adds stable metric/action class names and selection callback semantics for mobile.
- `web/src/styles.css`: removes duplicate old responsive patches and replaces them with one desktop-default, one tablet, and one mobile section.
- `web/src/App.test.tsx`: adds behavior tests for mobile task state, detail switching, and business logic preservation.

Create:

- `web/src/components/MobileTaskNav.tsx`: bottom task navigation for small screens only.
- `web/src/components/MobileTaskNav.test.tsx`: isolated navigation accessibility and disabled-detail tests.

Do not create a separate mobile Token Radar component. `TokenRadarTable` and `TokenRadarRow` remain the single source of truth.

## Task 1: Add Mobile Task Navigation Component

**Files:**

- Create: `web/src/components/MobileTaskNav.tsx`
- Create: `web/src/components/MobileTaskNav.test.tsx`

- [ ] **Step 1: Write the failing component test**

Create `web/src/components/MobileTaskNav.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MobileTaskNav, type MobileTask } from "./MobileTaskNav";

describe("MobileTaskNav", () => {
  it("renders task buttons with accessible active and disabled states", () => {
    const onChange = vi.fn();

    render(<MobileTaskNav activeTask="radar" detailAvailable={false} onTaskChange={onChange} />);

    expect(screen.getByRole("navigation", { name: "mobile cockpit tasks" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Radar" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Detail" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Tape" }));

    expect(onChange).toHaveBeenCalledWith("tape");
  });

  it("allows detail task when a selected object exists", () => {
    const onChange = vi.fn<(task: MobileTask) => void>();

    render(<MobileTaskNav activeTask="detail" detailAvailable onTaskChange={onChange} />);

    const detail = screen.getByRole("button", { name: "Detail" });
    expect(detail).toHaveAttribute("aria-current", "page");
    expect(detail).not.toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Lab" }));

    expect(onChange).toHaveBeenCalledWith("lab");
  });
});
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax/web
npm test -- src/components/MobileTaskNav.test.tsx --run
```

Expected: FAIL because `./MobileTaskNav` does not exist.

- [ ] **Step 3: Implement `MobileTaskNav`**

Create `web/src/components/MobileTaskNav.tsx`:

```tsx
import { Activity, FlaskConical, ListChecks, PanelRight } from "lucide-react";

export type MobileTask = "radar" | "tape" | "lab" | "detail";

type MobileTaskNavProps = {
  activeTask: MobileTask;
  detailAvailable: boolean;
  onTaskChange: (task: MobileTask) => void;
};

const TASKS: Array<{
  task: MobileTask;
  label: string;
  icon: typeof ListChecks;
}> = [
  { task: "radar", label: "Radar", icon: ListChecks },
  { task: "tape", label: "Tape", icon: Activity },
  { task: "lab", label: "Lab", icon: FlaskConical },
  { task: "detail", label: "Detail", icon: PanelRight }
];

export function MobileTaskNav({ activeTask, detailAvailable, onTaskChange }: MobileTaskNavProps) {
  return (
    <nav aria-label="mobile cockpit tasks" className="mobile-task-nav">
      {TASKS.map(({ icon: Icon, label, task }) => {
        const disabled = task === "detail" && !detailAvailable;
        return (
          <button
            aria-current={activeTask === task ? "page" : undefined}
            className={activeTask === task ? "active" : ""}
            disabled={disabled}
            key={task}
            type="button"
            onClick={() => onTaskChange(task)}
          >
            <Icon aria-hidden />
            <span>{label}</span>
          </button>
        );
      })}
    </nav>
  );
}
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax/web
npm test -- src/components/MobileTaskNav.test.tsx --run
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax
git add web/src/components/MobileTaskNav.tsx web/src/components/MobileTaskNav.test.tsx
git commit -m "feat: add mobile cockpit task nav"
```

Expected: commit succeeds.

## Task 2: Add Mobile Task State And Preserve Existing Data Flow

**Files:**

- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`

- [ ] **Step 1: Write failing App behavior tests**

Append these tests inside the existing `describe("App Token Radar social heat cockpit", () => { ... })` block in `web/src/App.test.tsx`, before the final helper functions:

```tsx
  it("renders mobile task navigation with Token Radar as the default task", async () => {
    renderWithQuery(<App />);

    expect(await screen.findByRole("navigation", { name: "mobile cockpit tasks" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Radar" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Detail" })).not.toBeDisabled();
    expect(await screen.findByText("TOKEN RADAR")).toBeInTheDocument();
  });

  it("switches mobile task to detail after selecting a token without changing token API params", async () => {
    renderWithQuery(<App />);
    const row = await screen.findByRole("button", { name: "select token $UPEG" });
    mockedGetApi.mockClear();

    fireEvent.click(row);

    await waitFor(() => expect(screen.getByRole("button", { name: "Detail" })).toHaveAttribute("aria-current", "page"));
    expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/token-flow")).toBe(false);
    expect(screen.getByText("selected token")).toBeInTheDocument();
  });

  it("switches mobile tasks without resetting window, scope, or selected token", async () => {
    const { container } = renderWithQuery(<App />);
    await screen.findByRole("button", { name: "select token $UPEG" });

    fireEvent.click(screen.getByRole("button", { name: "Tape" }));
    expect(screen.getByRole("button", { name: "Tape" })).toHaveAttribute("aria-current", "page");

    fireEvent.click(screen.getByRole("button", { name: "Lab" }));
    expect(screen.getByRole("button", { name: "Lab" })).toHaveAttribute("aria-current", "page");

    fireEvent.click(screen.getByRole("button", { name: "Radar" }));
    expect(screen.getByRole("button", { name: "Radar" })).toHaveAttribute("aria-current", "page");

    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    expect(drawer.querySelector(".drawer-title h2")).toHaveTextContent("$UPEG");
    expect(useTraderStore.getState().window).toBe("1h");
    expect(useTraderStore.getState().scope).toBe("all");
  });
```

- [ ] **Step 2: Run the App test and verify it fails**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax/web
npm test -- src/App.test.tsx --run
```

Expected: FAIL because mobile task navigation is not rendered and token selection does not update mobile task state.

- [ ] **Step 3: Import `MobileTaskNav` and define local mobile task state**

In `web/src/App.tsx`, add the import near the other component imports:

```tsx
import { MobileTaskNav, type MobileTask } from "./components/MobileTaskNav";
```

Inside `App`, near the other `useState` calls, add:

```tsx
  const [mobileTask, setMobileTask] = useState<MobileTask>("radar");
```

- [ ] **Step 4: Route selection actions to the Detail task**

Update `selectToken` in `web/src/App.tsx`:

```tsx
  const selectToken = (item: TokenFlowItem, tapeId: string | null = null) => {
    setSelectedSignal({ kind: "token", key: tokenKey(item), item });
    setDetailTab("timeline");
    setSelectedTapeEventId(tapeId);
    setMobileTask("detail");
  };
```

Update `selectSignalChain`:

```tsx
  const selectSignalChain = (item: SignalLabChain, options: { openLab?: boolean } = {}) => {
    setSelectedSignal({ kind: "signal_chain", item });
    setSignalLabInspectorTab("trace");
    setSelectedTapeEventId(item.chain_id);
    setMobileTask("detail");
    if (options.openLab) {
      setActiveView("signal_lab");
      setMobileTask("lab");
    }
  };
```

Update the event branch in `handleTapeSelect`:

```tsx
    setSelectedSignal({ kind: "event", item: item.payload });
    setMobileTask("detail");
```

- [ ] **Step 5: Route search and Open Lab behavior to mobile tasks**

In `submitEvidenceSearch`, keep the existing token matching and API behavior. Add only task routing:

```tsx
  const submitEvidenceSearch = () => {
    const query = search.trim();
    const tokenMatch = tokenForSearchQuery(query, tokenItems);
    if (tokenMatch) {
      selectToken(tokenMatch);
      setSelectedTapeEventId(null);
      setMobileTask("radar");
      return;
    }
    if (activeView === "signal_lab") {
      setSignalLabSearch(query);
      setSelectedSignal(null);
      setSelectedTapeEventId(null);
      setMobileTask("lab");
      return;
    }
    submitSearch();
    setSelectedSignal(query ? { kind: "query", query } : null);
    setSelectedTapeEventId(null);
    setMobileTask(query ? "detail" : "radar");
  };
```

For the `SignalLabPulse` prop in live mode, change:

```tsx
onOpenLab={() => setActiveView("signal_lab")}
```

to:

```tsx
onOpenLab={() => {
  setActiveView("signal_lab");
  setMobileTask("lab");
}}
```

- [ ] **Step 6: Render the mobile task nav**

Near the end of the returned `<main>`, after the `.cockpit-grid` closing `</div>` and before `</main>`, add:

```tsx
      <MobileTaskNav
        activeTask={mobileTask}
        detailAvailable={Boolean(selectedSignal || selectedToken)}
        onTaskChange={setMobileTask}
      />
```

- [ ] **Step 7: Add task state classes to the shell**

Change the cockpit grid className from:

```tsx
<div className={`cockpit-grid ${activeView === "signal_lab" ? "signal-lab-mode" : ""}`}>
```

to:

```tsx
<div className={`cockpit-grid mobile-task-${mobileTask} ${activeView === "signal_lab" ? "signal-lab-mode" : ""}`}>
```

- [ ] **Step 8: Run the App tests and verify they pass**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax/web
npm test -- src/App.test.tsx --run
```

Expected: PASS.

- [ ] **Step 9: Commit Task 2**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax
git add web/src/App.tsx web/src/App.test.tsx
git commit -m "feat: route mobile cockpit tasks"
```

Expected: commit succeeds.

## Task 3: Split Surfaces For Responsive Shell Without Duplicating Business Logic

**Files:**

- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`

- [ ] **Step 1: Write failing structure tests**

Append these tests inside the existing App test `describe` block:

```tsx
  it("exposes distinct responsive shell surfaces without duplicating Token Radar rows", async () => {
    const { container } = renderWithQuery(<App />);
    await screen.findByRole("button", { name: "select token $UPEG" });

    expect(container.querySelector(".desktop-side-rail")).toBeInTheDocument();
    expect(container.querySelector(".responsive-control-panel")).toBeInTheDocument();
    expect(container.querySelector(".mobile-task-surface")).toBeInTheDocument();
    expect(container.querySelectorAll(".token-radar-table .radar-row")).toHaveLength(1);
  });

  it("marks mobile task panels so CSS can show one task at a time", async () => {
    const { container } = renderWithQuery(<App />);
    await screen.findByText("Signal Lab Pulse");

    expect(container.querySelector('[data-mobile-task-panel="radar"]')).toBeInTheDocument();
    expect(container.querySelector('[data-mobile-task-panel="tape"]')).toBeInTheDocument();
    expect(container.querySelector('[data-mobile-task-panel="lab"]')).toBeInTheDocument();
    expect(container.querySelector('[data-mobile-task-panel="detail"]')).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the App test and verify it fails**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax/web
npm test -- src/App.test.tsx --run
```

Expected: FAIL because the new shell surface classes and task panel attributes do not exist.

- [ ] **Step 3: Extract reusable control markup helpers inside `App.tsx`**

In `web/src/App.tsx`, before the `return`, create these JSX constants. They reuse existing state and callbacks and do not change API behavior:

```tsx
  const viewControls = (
    <RailSection label="views">
      <RailButton active={activeView === "live"} label="Live" value={liveItems.length} index="1" onClick={() => setActiveView("live")} />
      <RailButton
        active={activeView === "signal_lab"}
        label="Signal Lab"
        value={totalChains(signalLabData?.summary, signalLabChains.length)}
        index="2"
        onClick={() => {
          setActiveView("signal_lab");
          setMobileTask("lab");
        }}
      />
    </RailSection>
  );

  const windowControls = (
    <RailSection label="window">
      <div className="window-stack">
        {WINDOWS.map((item, index) => (
          <button key={item} className={item === windowKey ? "active" : ""} onClick={() => setWindow(item)} type="button">
            {index + 1}<span>{item}</span>
          </button>
        ))}
      </div>
    </RailSection>
  );

  const scopeControls = (
    <RailSection label="scope">
      <div className="scope-stack">
        <button className={scope === "matched" ? "active" : ""} onClick={() => setScope("matched")} type="button">
          watched
        </button>
        <button className={scope === "all" ? "active" : ""} onClick={() => setScope("all")} type="button">
          all stream
        </button>
      </div>
      <label className="handle-filter">
        <UserRound aria-hidden />
        <input value={handles} onChange={(event) => setHandles(event.target.value)} placeholder="toly, ansem" />
      </label>
    </RailSection>
  );
```

Then create compact responsive controls:

```tsx
  const responsiveControls = (
    <section className="responsive-control-panel" aria-label="cockpit controls">
      <div className="segmented" aria-label="window">
        {WINDOWS.map((item) => (
          <button key={item} className={item === windowKey ? "active" : ""} onClick={() => setWindow(item)} type="button">
            {item}
          </button>
        ))}
      </div>
      <div className="segmented scope-toggle" aria-label="token flow scope">
        <button className={scope === "matched" ? "active" : ""} onClick={() => setScope("matched")} type="button">
          watched
        </button>
        <button className={scope === "all" ? "active" : ""} onClick={() => setScope("all")} type="button">
          all
        </button>
      </div>
      <label className="handle-filter compact">
        <UserRound aria-hidden />
        <input value={handles} onChange={(event) => setHandles(event.target.value)} placeholder="handles" />
      </label>
    </section>
  );
```

- [ ] **Step 4: Replace duplicated side rail JSX with helpers**

Inside `<aside className="side-rail">`, replace the inline views/window/scope sections with:

```tsx
          {viewControls}
          {windowControls}
          {scopeControls}
```

Keep the existing decisions, watchlist, and rail footer sections unchanged.

Add the desktop-specific class:

```tsx
<aside className="side-rail desktop-side-rail">
```

- [ ] **Step 5: Add responsive controls before the center column**

Inside `.cockpit-grid`, immediately after the side rail `</aside>`, render:

```tsx
        {responsiveControls}
```

- [ ] **Step 6: Add mobile task panel attributes**

Wrap the live-mode Token Radar block in a panel:

```tsx
              <section className="mobile-task-surface" data-mobile-task-panel="radar">
                <div className="radar-control-row">
                  ...
                </div>

                <TokenRadarTable ... />
              </section>
```

Wrap the bottom deck panels in task panels:

```tsx
              <div className="bottom-deck">
                <section data-mobile-task-panel="tape">
                  <LiveSignalTape ... />
                </section>

                <section data-mobile-task-panel="lab">
                  <SignalLabPulse ... />
                </section>
              </div>
```

For the detail area, wrap the selected detail conditional with:

```tsx
        <section className="detail-task-panel" data-mobile-task-panel="detail">
          {selectedSignalChain ? (
            <SignalLabInspector ... />
          ) : selectedEvidenceDetails ? (
            <EvidenceDetailDrawer {...selectedEvidenceDetails} />
          ) : (
            <TokenDetailDrawer ... />
          )}
        </section>
```

For `activeView === "signal_lab"`, add `data-mobile-task-panel="lab"` to the workbench wrapper by surrounding `SignalLabWorkbench`:

```tsx
            <section className="mobile-task-surface signal-lab-task-surface" data-mobile-task-panel="lab">
              <SignalLabWorkbench ... />
            </section>
```

- [ ] **Step 7: Run the App tests and verify they pass**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax/web
npm test -- src/App.test.tsx --run
```

Expected: PASS.

- [ ] **Step 8: Commit Task 3**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax
git add web/src/App.tsx web/src/App.test.tsx
git commit -m "refactor: split cockpit responsive surfaces"
```

Expected: commit succeeds.

## Task 4: Make Token Radar Rows Responsive Without Changing Metrics

**Files:**

- Modify: `web/src/components/TokenRadarTable.tsx`
- Modify: `web/src/components/TokenRadarRow.tsx`
- Modify: `web/src/App.test.tsx`

- [ ] **Step 1: Write failing semantic structure test**

Append this test inside the existing App test `describe` block:

```tsx
  it("keeps each Token Radar metric in stable responsive slots", async () => {
    renderWithQuery(<App />);

    const row = await screen.findByRole("button", { name: "select token $UPEG" });
    expect(row.querySelector('[data-radar-metric="heat"]')).toHaveTextContent("86 · 4 +3");
    expect(row.querySelector('[data-radar-metric="quality"]')).toHaveTextContent("78 · CA direct");
    expect(row.querySelector('[data-radar-metric="propagation"]')).toHaveTextContent("expansion · 3 author");
    expect(row.querySelector('[data-radar-metric="market"]')).toHaveTextContent("$1.2M");
    expect(row.querySelector('[data-radar-metric="timing"]')).toHaveTextContent("social confirms");
    expect(row.querySelector('[data-radar-action="gmgn"]')).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the App test and verify it fails**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax/web
npm test -- src/App.test.tsx --run
```

Expected: FAIL because `data-radar-metric` and `data-radar-action` attributes are not present.

- [ ] **Step 3: Add responsive metric attributes without changing text**

In `web/src/components/TokenRadarRow.tsx`, change the metric spans:

```tsx
        <span className="metric heat-cell" data-radar-metric="heat">
```

```tsx
        <span className="metric quality-cell" data-radar-metric="quality">
```

```tsx
        <span className="phase propagation-cell" data-radar-metric="propagation">
```

```tsx
        <span className="metric market-cell" data-radar-metric="market">
```

```tsx
        <span className="phase timing-cell" data-radar-metric="timing">
```

Change the GMGN cell:

```tsx
      <span className="gmgn-cell" data-radar-action="gmgn">
```

Do not change any helper functions such as `heatTitle`, `qualityMeta`, `timingMeta`, or `scoreClass`.

- [ ] **Step 4: Add a mobile summary hook to the table**

In `web/src/components/TokenRadarTable.tsx`, add an aria label to the sort controls so CSS/tests can target the toolbar without relying on text order:

```tsx
<div className="toolbar-controls" aria-label="token radar toolbar">
```

Do not alter `SORT_LABELS`, `items.map`, `tokenDecisionKey`, or `onSortModeChange`.

- [ ] **Step 5: Run focused tests and verify they pass**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax/web
npm test -- src/App.test.tsx --run
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax
git add web/src/components/TokenRadarTable.tsx web/src/components/TokenRadarRow.tsx web/src/App.test.tsx
git commit -m "refactor: mark radar rows for responsive layout"
```

Expected: commit succeeds.

## Task 5: Replace The Old Responsive CSS With Explicit Desktop, Tablet, And Mobile Rules

**Files:**

- Modify: `web/src/styles.css`

- [ ] **Step 1: Capture the current duplicate breakpoint count**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax
rg -n "@media \\(max-width: 1180px\\)|@media \\(max-width: 760px\\)|@media \\(max-width: 1279px\\)|@media \\(max-width: 767px\\)" web/src/styles.css
```

Expected before editing: existing `1180px` and `760px` media queries appear more than once.

- [ ] **Step 2: Remove old duplicate responsive blocks**

In `web/src/styles.css`, delete all existing blocks that begin with:

```css
@media (max-width: 1180px) {
```

and:

```css
@media (max-width: 760px) {
```

Remove the complete block bodies and closing braces. Do not delete non-media component rules.

- [ ] **Step 3: Add base shell rules**

Near the base `body` rules in `web/src/styles.css`, ensure these declarations exist:

```css
html,
body,
#root {
  min-width: 0;
  min-height: 100%;
}

body {
  overflow-x: clip;
}
```

Keep the existing `body` color, background, font, and `letter-spacing: 0`.

- [ ] **Step 4: Add desktop defaults for new shell classes**

Near the existing `.cockpit-grid` and `.center-column` rules, add:

```css
.responsive-control-panel,
.mobile-task-nav {
  display: none;
}

.detail-task-panel {
  min-width: 0;
  background: rgba(13, 17, 17, 0.96);
}

.detail-task-panel > .detail-drawer {
  width: 100%;
}

.bottom-deck > [data-mobile-task-panel] {
  min-width: 0;
}

.bottom-deck > [data-mobile-task-panel="tape"] {
  border-right: 1px solid var(--line);
}

.bottom-deck > [data-mobile-task-panel] > .compact-panel {
  height: 100%;
  border-right: 0;
}
```

Expected behavior: desktop still shows side rail, center, and right detail column.

- [ ] **Step 5: Add tablet breakpoint**

At the bottom of `web/src/styles.css`, add one tablet breakpoint:

```css
@media (max-width: 1279px) {
  .topbar {
    grid-template-columns: minmax(180px, 0.8fr) minmax(220px, 1fr) 32px;
    grid-auto-rows: minmax(32px, auto);
  }

  .topbar .status-pills,
  .topbar .top-stats {
    grid-column: 1 / -1;
    overflow-x: auto;
  }

  .cockpit-grid,
  .cockpit-grid.signal-lab-mode {
    grid-template-columns: minmax(0, 1fr);
  }

  .desktop-side-rail {
    display: none;
  }

  .responsive-control-panel {
    display: grid;
    grid-template-columns: auto auto minmax(160px, 1fr);
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid var(--line);
    background: rgba(13, 17, 17, 0.96);
    padding: 8px 12px;
  }

  .responsive-control-panel .handle-filter {
    margin-top: 0;
  }

  .center-column {
    border-right: 0;
  }

  .detail-task-panel {
    border-top: 1px solid var(--line);
  }

  .detail-drawer {
    position: static;
    height: auto;
  }

  .bottom-deck {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .signal-stage-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .signal-filter-bar {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
```

- [ ] **Step 6: Add mobile breakpoint**

After the tablet breakpoint, add one mobile breakpoint:

```css
@media (max-width: 767px) {
  .cockpit-shell {
    padding-bottom: calc(62px + env(safe-area-inset-bottom));
  }

  .topbar {
    position: sticky;
    grid-template-columns: minmax(0, 1fr) 32px;
    gap: 8px;
    min-height: 0;
    padding: 8px;
  }

  .brand-copy {
    display: grid;
    gap: 2px;
  }

  .brand h1 {
    font-size: 12px;
  }

  .brand p {
    max-width: 170px;
  }

  .status-pills,
  .top-stats {
    grid-column: 1 / -1;
    gap: 10px;
    overflow-x: auto;
    padding-bottom: 2px;
  }

  .searchbar {
    grid-column: 1 / -1;
    height: 36px;
  }

  .responsive-control-panel {
    grid-template-columns: 1fr;
    gap: 7px;
    padding: 8px;
  }

  .responsive-control-panel .segmented,
  .radar-control-row .segmented {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .responsive-control-panel .scope-toggle,
  .radar-control-row .scope-toggle {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .center-column {
    min-height: 0;
  }

  .radar-control-row {
    justify-content: stretch;
    flex-wrap: wrap;
    padding: 8px;
  }

  .radar-panel {
    border-right: 0;
  }

  .radar-toolbar {
    align-items: stretch;
    flex-direction: column;
    gap: 8px;
    min-height: 0;
    padding: 10px;
  }

  .toolbar-controls {
    overflow-x: auto;
  }

  .sort-toggle {
    grid-template-columns: repeat(5, minmax(92px, 1fr));
    min-width: max-content;
  }

  .token-radar-table {
    height: auto;
    max-height: none;
    overflow: visible;
  }

  .radar-head {
    display: none;
  }

  .radar-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    min-width: 0;
    min-height: 0;
    border-bottom: 1px solid var(--line);
    padding: 0;
  }

  .radar-row.selected {
    box-shadow: inset 3px 0 0 var(--accent);
  }

  .radar-row-select {
    grid-column: auto;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px;
    min-width: 0;
    padding: 12px 10px 8px 12px;
  }

  .token-cell {
    grid-column: 1 / -1;
  }

  .decision-cell {
    grid-column: 2;
    grid-row: 1;
    justify-self: end;
  }

  .metric,
  .phase {
    min-height: 42px;
    border: 1px solid var(--line-soft);
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.018);
    padding: 7px;
  }

  [data-radar-metric="heat"],
  [data-radar-metric="quality"],
  [data-radar-metric="propagation"],
  [data-radar-metric="market"],
  [data-radar-metric="timing"] {
    min-width: 0;
  }

  .gmgn-cell {
    justify-items: stretch;
    padding: 0 10px 10px 12px;
  }

  .gmgn-link {
    width: 100%;
    min-height: 32px;
  }

  .bottom-deck {
    display: contents;
  }

  [data-mobile-task-panel] {
    display: none;
  }

  .mobile-task-radar [data-mobile-task-panel="radar"],
  .mobile-task-tape [data-mobile-task-panel="tape"],
  .mobile-task-lab [data-mobile-task-panel="lab"],
  .mobile-task-detail [data-mobile-task-panel="detail"] {
    display: block;
  }

  .mobile-task-lab.signal-lab-mode [data-mobile-task-panel="radar"] {
    display: none;
  }

  .detail-task-panel {
    border-top: 0;
  }

  .detail-drawer {
    min-height: calc(100vh - 160px);
  }

  .drawer-kv,
  .timeline-summary,
  .score-overview,
  .settlement-grid,
  .evidence-query-kv {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .tabs {
    overflow-x: auto;
    grid-template-columns: repeat(5, minmax(84px, 1fr));
  }

  .signal-detail-tabs {
    grid-template-columns: repeat(4, minmax(92px, 1fr));
  }

  .signal-stage-grid,
  .signal-filter-bar {
    grid-template-columns: 1fr;
    padding-right: 10px;
    padding-left: 10px;
  }

  .signal-lab-workbench-head {
    padding: 14px 10px 10px;
  }

  .signal-lab-workbench-head h2 {
    font-size: 20px;
  }

  .signal-chain-workbench-list {
    padding: 2px 10px 12px;
  }

  .signal-chain-row,
  .signal-chain-list.compact .signal-chain-row {
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
    min-height: 0;
    padding: 12px;
  }

  .signal-chain-score {
    justify-items: start;
    text-align: left;
  }

  .tape-row {
    grid-template-columns: 52px minmax(0, 1fr) 40px;
  }

  .tape-row time {
    grid-column: 2 / -1;
  }

  .mobile-task-nav {
    position: fixed;
    right: 0;
    bottom: 0;
    left: 0;
    z-index: 30;
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    border-top: 1px solid var(--line);
    background: rgba(9, 12, 12, 0.98);
    padding: 6px 8px calc(6px + env(safe-area-inset-bottom));
    backdrop-filter: blur(14px);
  }

  .mobile-task-nav button {
    display: grid;
    min-height: 46px;
    place-items: center;
    gap: 3px;
    border: 1px solid transparent;
    border-radius: 5px;
    color: var(--muted);
    background: transparent;
    font-family: var(--mono);
    font-size: 10px;
  }

  .mobile-task-nav button.active,
  .mobile-task-nav button[aria-current="page"] {
    color: var(--accent);
    border-color: var(--accent-line);
    background: var(--accent-soft);
  }
}
```

- [ ] **Step 7: Verify there are no old duplicate breakpoints**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax
rg -n "@media \\(max-width: 1180px\\)|@media \\(max-width: 760px\\)" web/src/styles.css
```

Expected: no output.

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax
rg -n "@media \\(max-width: 1279px\\)|@media \\(max-width: 767px\\)" web/src/styles.css
```

Expected: exactly two lines, one for `1279px` and one for `767px`.

- [ ] **Step 8: Run the frontend build**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax/web
npm run build
```

Expected: TypeScript and Vite build pass.

- [ ] **Step 9: Commit Task 5**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax
git add web/src/styles.css
git commit -m "style: rebuild cockpit responsive layout"
```

Expected: commit succeeds.

## Task 6: Browser QA Responsive Layout And No Horizontal Scroll

**Files:**

- No source files are required unless browser QA reveals a defect.

- [ ] **Step 1: Run all frontend tests**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax/web
npm test -- --run
```

Expected: PASS.

- [ ] **Step 2: Run full frontend build**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax/web
npm run build
```

Expected: PASS.

- [ ] **Step 3: Start dev server for manual QA**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax/web
npm run dev -- --host 127.0.0.1 --port 5173
```

Expected: Vite serves on `http://127.0.0.1:5173/`.

- [ ] **Step 4: Browser QA with Playwright or Browser Use**

Open `http://127.0.0.1:5173/` and check these viewport sizes:

```text
1440x900:
  desktop three-column cockpit visible
  Token Radar table readable
  right drawer sticky

1024x768:
  permanent side rail hidden
  responsive control panel visible
  Token Radar remains above detail

768x1024:
  no page horizontal scroll
  controls do not crowd radar

430x932:
  Radar task active by default
  first token rows visible above bottom nav
  no page horizontal scroll
  selecting token opens Detail task

390x844:
  search, counters, and radar list fit
  metric text does not overlap
  GMGN action remains tappable
```

Use this browser console check at `430x932` and `390x844`:

```js
document.documentElement.scrollWidth <= window.innerWidth
```

Expected: `true`.

- [ ] **Step 5: Commit Task 6 if browser QA required fixes**

If browser QA required CSS or shell fixes, run:

```bash
cd /Users/qinghuan/Documents/code/parallax
git add web/src/App.tsx web/src/styles.css web/src/components/TokenRadarTable.tsx web/src/components/TokenRadarRow.tsx web/src/App.test.tsx
git commit -m "fix: polish responsive cockpit viewports"
```

Expected: commit succeeds only if fixes were made. If no files changed, skip this commit.

## Task 7: Final Regression And Cleanup

**Files:**

- Modify if needed: `web/src/App.tsx`
- Modify if needed: `web/src/styles.css`
- Modify if needed: `web/src/components/TokenRadarTable.tsx`
- Modify if needed: `web/src/components/TokenRadarRow.tsx`
- Modify if needed: `web/src/components/MobileTaskNav.tsx`

- [ ] **Step 1: Check that old breakpoints are gone**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax
rg -n "@media \\(max-width: 1180px\\)|@media \\(max-width: 760px\\)" web/src/styles.css
```

Expected: no output.

- [ ] **Step 2: Check that backend files were not modified**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax
git diff --name-only HEAD~6..HEAD
```

Expected changed paths are limited to:

```text
web/src/App.tsx
web/src/App.test.tsx
web/src/components/MobileTaskNav.tsx
web/src/components/MobileTaskNav.test.tsx
web/src/components/TokenRadarTable.tsx
web/src/components/TokenRadarRow.tsx
web/src/styles.css
```

If any `src/parallax/**` path appears, stop and inspect before proceeding.

- [ ] **Step 3: Run frontend tests and build**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax/web
npm test -- --run
npm run build
```

Expected: both commands PASS.

- [ ] **Step 4: Run Python project safety checks**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax
uv run python -m compileall src tests
uv run ruff check .
```

Expected: both commands PASS. These should pass because no backend Python code changed; run them to prove the refactor did not disturb repository health.

- [ ] **Step 5: Review final diff for accidental business logic changes**

Run:

```bash
cd /Users/qinghuan/Documents/code/parallax
git diff HEAD~6..HEAD -- web/src/App.tsx web/src/components/TokenRadarRow.tsx web/src/components/TokenRadarTable.tsx
```

Expected review findings:

- query keys unchanged;
- API endpoint paths unchanged;
- token sorting helper unchanged;
- formatter helper outputs unchanged;
- Token Radar item mapping still uses the same `items.map`;
- selection still writes the same `SelectedSignal` variants;
- only mobile task routing and layout wrappers were added.

- [ ] **Step 6: Commit cleanup if any final changes were needed**

If Step 5 required small cleanup changes, run:

```bash
cd /Users/qinghuan/Documents/code/parallax
git add web/src/App.tsx web/src/styles.css web/src/components/TokenRadarTable.tsx web/src/components/TokenRadarRow.tsx web/src/components/MobileTaskNav.tsx web/src/App.test.tsx web/src/components/MobileTaskNav.test.tsx
git commit -m "fix: polish responsive cockpit layout"
```

Expected: commit succeeds only if there are cleanup changes. If there are no cleanup changes, skip this commit.

## Plan Self-Review

Spec coverage:

- Mobile defaults to Token Radar: Task 2 adds `mobileTask = "radar"` and Task 6 verifies it.
- No business logic changes: Scope Guard, Task 2 API-param test, Task 7 diff review.
- Desktop three-column retained: Task 5 desktop defaults keep side rail, center, detail.
- Tablet compact controls: Task 3 creates `responsive-control-panel`; Task 5 tablet rules show it.
- Mobile task nav: Task 1 component; Task 2 shell integration.
- Token Radar card/list on mobile: Task 4 metric hooks; Task 5 mobile CSS.
- Signal Lab and Tape preserved: Task 3 task panels; Task 5 mobile task display rules.
- Old compatibility breakpoints removed: Task 5 and Task 7 `rg` checks.
- Browser verification matrix: Task 6.

Placeholder scan:

- Placeholder red flags were scanned and are absent.
- Every code-changing task includes exact target files, code snippets, commands, and expected results.

Type consistency:

- `MobileTask` is defined in `MobileTaskNav.tsx` and imported by `App.tsx`.
- Task values are consistently `radar`, `tape`, `lab`, `detail`.
- CSS task classes match `mobile-task-${mobileTask}`.
- `data-mobile-task-panel` values match `MobileTask`.
