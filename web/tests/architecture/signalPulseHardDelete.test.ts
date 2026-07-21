import { existsSync, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");
const repoRoot = join(webRoot, "..");
const srcRoot = join(webRoot, "src");

const deletedPaths = ["features/signal-lab", "features/live/state/liveTaskStore.ts"].map((path) =>
  join(srcRoot, path),
);

const currentFiles = [
  "features/live/model/liveMobileTask.ts",
  "features/live/ui/LivePage.tsx",
  "features/live/ui/LiveTaskNav.tsx",
  "features/live/useLiveSelection.ts",
  "features/notifications/useNotificationsController.ts",
  "features/ops/ui/OpsDiagnosticsPage.tsx",
  "lib/tokenRadar.ts",
  "lib/types/frontend-contracts.ts",
  "lib/types/openapi.ts",
  "lib/venue.ts",
  "routes/live.route.tsx",
  "routes/shellChromeData.ts",
  "shared/query/queryKeys.ts",
].map((path) => join(srcRoot, path));

const contractFiles = [
  join(repoRoot, "docs/CONTRACTS.md"),
  join(repoRoot, "docs/FRONTEND.md"),
  join(repoRoot, "docs/generated/openapi.json"),
];

const forbiddenTokens = [
  "signalpulse",
  "signal_pulse",
  "signal pulse",
  "signal-pulse",
  "pulse_candidate",
  "pulse candidate",
  "pulse overlay",
  "pulse_agent_jobs",
  "pulse_overlay",
  "/api/signal-lab/pulse",
  "mobile-task-lab",
];

describe("Signal Pulse hard delete", () => {
  it("deletes the Signal Lab feature and global Live task store", () => {
    const existing = deletedPaths.filter(existsSync).map((path) => relative(webRoot, path));

    expect(existing).toEqual([]);
  });

  it("removes Pulse contracts from current frontend and canonical public docs", () => {
    const hits = [...currentFiles, ...contractFiles].flatMap((path) => {
      if (!existsSync(path)) {
        return [];
      }
      const source = readFileSync(path, "utf8").toLowerCase();
      return forbiddenTokens
        .filter((token) => source.includes(token))
        .map((token) => relative(repoRoot, path) + " contains " + token);
    });

    expect(hits).toEqual([]);
  });

  it("keeps Live mobile navigation on Radar and Tape only", () => {
    const source = readFileSync(join(srcRoot, "features/live/model/liveMobileTask.ts"), "utf8");

    expect(source).toContain('"radar"');
    expect(source).toContain('"tape"');
    expect(source).not.toContain('"lab"');
  });

  it("keeps Ops diagnostics on its parameter-free backend contract", () => {
    const source = readFileSync(
      join(srcRoot, "features/ops/api/useOpsDiagnosticsQuery.ts"),
      "utf8",
    );

    expect(source).not.toContain("since_hours");
    expect(source).not.toContain("scope");
    expect(source).not.toContain("window");
    expect(source).toContain('getApi<OpsDiagnostics>("/api/ops/diagnostics", { token })');
  });
});
