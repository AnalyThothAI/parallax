import {
  domainRows,
  formatCount,
  requireOpsDiagnostics,
  requireOpsQueueData,
  statusTone,
} from "@features/ops/model/opsDiagnostics";
import {
  activeOpsAgentExecutionFixture,
  opsDiagnosticsFixture,
  opsQueueFixture,
} from "@tests/fixtures/opsFixture";
import { describe, expect, it } from "vitest";

describe("opsDiagnostics current contract", () => {
  it("accepts current diagnostics and queue payloads", () => {
    expect(requireOpsDiagnostics(opsDiagnosticsFixture())).toBeTruthy();
    expect(requireOpsQueueData(opsQueueFixture())).toBeTruthy();
  });

  it.each(["overall", "queues", "agent_execution", "domains"])(
    "rejects diagnostics without %s",
    (key) => {
      const payload = { ...opsDiagnosticsFixture() } as Record<string, unknown>;
      delete payload[key];

      expect(() => requireOpsDiagnostics(payload)).toThrowError("ops_current_contract:diagnostics");
    },
  );

  it("rejects a malformed queue count instead of treating it as zero", () => {
    const payload = opsQueueFixture();
    payload.summary = { ...payload.summary };
    delete (payload.summary as Partial<typeof payload.summary>).dead_count;

    expect(() => requireOpsQueueData(payload)).toThrowError("ops_current_contract:queue.summary");
  });

  it.each([
    ["database", "ok"],
    ["collector", "details"],
  ])("rejects a current %s section without required key %s", (sectionName, key) => {
    const payload = opsDiagnosticsFixture();
    const section = payload[sectionName as "database" | "collector"] as Record<string, unknown>;
    delete section[key];

    expect(() => requireOpsDiagnostics(payload)).toThrowError(
      `ops_current_contract:diagnostics.${sectionName}`,
    );
  });

  it("rejects unknown keys in current database and collector sections", () => {
    for (const sectionName of ["database", "collector"] as const) {
      const payload = opsDiagnosticsFixture();
      payload[sectionName].retired_detail = "compatibility residue";

      expect(() => requireOpsDiagnostics(payload)).toThrowError(
        `ops_current_contract:diagnostics.${sectionName}`,
      );
    }
  });

  it.each([
    ["token_radar", "publication"],
    ["asset_market", "provider_count"],
    ["news", "source_count"],
    ["watchlist", "configured_handle_count"],
    ["notifications", "summary"],
  ])("rejects domain %s without required key %s", (domainName, key) => {
    const payload = opsDiagnosticsFixture();
    const domain = payload.domains[domainName] as Record<string, unknown>;
    delete domain[key];

    expect(() => requireOpsDiagnostics(payload)).toThrowError(
      `ops_current_contract:diagnostics.domains.${domainName}`,
    );
  });

  it("rejects unknown domain keys and partial notification summaries", () => {
    const unknownKey = opsDiagnosticsFixture();
    unknownKey.domains.news.retired_state = "compatibility residue";
    expect(() => requireOpsDiagnostics(unknownKey)).toThrowError(
      "ops_current_contract:diagnostics.domains.news",
    );

    const partialSummary = opsDiagnosticsFixture();
    const summary = partialSummary.domains.notifications.summary as Record<string, unknown>;
    delete summary.critical_unread_count;
    expect(() => requireOpsDiagnostics(partialSummary)).toThrowError(
      "ops_current_contract:diagnostics.domains.notifications.summary",
    );
  });

  it("accepts the fixed story-brief execution object and rejects retired lanes", () => {
    const active = opsDiagnosticsFixture();
    active.agent_execution = activeOpsAgentExecutionFixture();
    expect(requireOpsDiagnostics(active)).toBeTruthy();

    const retired = opsDiagnosticsFixture() as unknown as {
      agent_execution: Record<string, unknown>;
    };
    retired.agent_execution.lanes = {};
    expect(() => requireOpsDiagnostics(retired)).toThrowError(
      "ops_current_contract:diagnostics.agent_execution",
    );
  });

  it("rejects partial active agent policy instead of accepting a loose object", () => {
    const payload = opsDiagnosticsFixture();
    payload.agent_execution = activeOpsAgentExecutionFixture();
    delete (payload.agent_execution.policy as Record<string, unknown>).model;

    expect(() => requireOpsDiagnostics(payload)).toThrowError(
      "ops_current_contract:diagnostics.agent_execution.policy",
    );
  });

  it("requires active policy/counters and nulls them for inactive status", () => {
    const activeWithoutPolicy = opsDiagnosticsFixture();
    activeWithoutPolicy.agent_execution = {
      status: "ok",
      policy: null,
      counters: null,
    };
    expect(() => requireOpsDiagnostics(activeWithoutPolicy)).toThrowError(
      "ops_current_contract:diagnostics.agent_execution.policy",
    );

    const disabledWithPolicy = opsDiagnosticsFixture();
    disabledWithPolicy.agent_execution = {
      ...activeOpsAgentExecutionFixture(),
      status: "disabled",
    };
    expect(() => requireOpsDiagnostics(disabledWithPolicy)).toThrowError(
      "ops_current_contract:diagnostics.agent_execution",
    );
  });

  it("maps explicit runtime states while leaving malformed values unknown", () => {
    expect(statusTone("running")).toBe("ok");
    expect(statusTone("unavailable")).toBe("blocked");
    expect(statusTone("intentionally_not_started")).toBe("disabled");
    expect(statusTone("malformed")).toBe("unknown");
    expect(formatCount(undefined)).toBe("未知");
  });

  it("renders absent domain backlog as unknown instead of zero", () => {
    const rows = domainRows(opsDiagnosticsFixture());

    expect(rows.every((row) => row.backlog === "未知")).toBe(true);
  });
});
