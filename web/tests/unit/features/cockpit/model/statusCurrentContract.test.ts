import {
  requireStatusData,
  requireWorkerStatusData,
} from "@features/cockpit/model/statusCurrentContract";
import { appStatusFixture } from "@tests/fixtures/appRouteFixtures";
import { describe, expect, it } from "vitest";

describe("statusCurrentContract", () => {
  it("accepts the fixed current status payload", () => {
    expect(requireStatusData(appStatusFixture())).toBeTruthy();
    expect(
      requireStatusData(appStatusFixture({ agent_execution: activeAgentExecution() })),
    ).toBeTruthy();
    expect(
      requireStatusData(
        appStatusFixture({
          agent_execution: { status: "unavailable", error: "gateway offline" },
        }),
      ),
    ).toBeTruthy();
  });

  it("rejects loose or partial agent execution status objects", () => {
    expect(() =>
      requireStatusData(appStatusFixture({ agent_execution: {} as never })),
    ).toThrowError("status_current_contract:status.agent_execution.lane");

    expect(() =>
      requireStatusData(
        appStatusFixture({
          agent_execution: { status: "unavailable" } as never,
        }),
      ),
    ).toThrowError("status_current_contract:status.agent_execution.error");
  });

  it("rejects status without the required news provider contract", () => {
    const payload = { ...appStatusFixture() } as Record<string, unknown>;
    delete payload.news_provider_contract;

    expect(() => requireStatusData(payload)).toThrowError(
      "status_current_contract:status.news_provider_contract",
    );
  });

  it("rejects missing worker fields and the retired details bucket", () => {
    const worker = { ...appStatusFixture().workers.collector } as Record<string, unknown>;
    delete worker.last_result;
    expect(() => requireWorkerStatusData(worker)).toThrowError(
      "status_current_contract:worker.last_result",
    );

    expect(() =>
      requireWorkerStatusData({
        ...appStatusFixture().workers.collector,
        details: {},
      }),
    ).toThrowError("status_current_contract:worker.details");
  });
});

function activeAgentExecution() {
  return {
    lane: "news.story_brief" as const,
    model: "deepseek-v4-flash",
    provider_family: "deepseek",
    output_strategy: "json_object" as const,
    schema_enforcement: "client_validate" as const,
    max_concurrency: 1,
    rpm_limit: 60,
    timeout_seconds: 180,
    in_flight: 0,
    provider_running: 0,
    circuit_state: "closed" as const,
    circuit_open_until_ms: null,
    capacity_denied_total: 0,
    circuit_open_total: 0,
    timeout_total: 0,
    last_denied_at_ms: null,
    last_timeout_at_ms: null,
    oldest_in_flight_age_ms: null,
  };
}
