import { PulseDetailRoutePage } from "@features/signal-lab";
import { ApiError, setAuthToken } from "@lib/api/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { marketContextFixture } from "@tests/fixtures/marketFixtures";
import { createApiMock, ok, resetApiMock } from "@tests/msw/fixtures";
import { apiHandlers } from "@tests/msw/handlers";
import { server } from "@tests/msw/server";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

const apiMock = createApiMock();

beforeEach(() => {
  setAuthToken("test-token");
  resetApiMock(apiMock);
  server.use(...apiHandlers(apiMock));
});

afterEach(() => cleanup());

function renderAt(url: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/signal-lab/pulse/:candidateId" element={<PulseDetailRoutePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PulseDetailRoutePage", () => {
  it("renders a structural skeleton while the candidate request is pending", () => {
    apiMock.readApiImpl = () => new Promise(() => undefined);
    renderAt("/signal-lab/pulse/cand-1");

    expect(screen.getByLabelText("loading pulse detail")).toBeInTheDocument();
  });

  it("renders detail view when candidate exists", async () => {
    apiMock.readApiImpl = async () => ok(minimalPulseItem());
    renderAt("/signal-lab/pulse/cand-1");
    await waitFor(() => {
      expect(screen.getAllByText(/\$PEPE|cand-1/).length).toBeGreaterThan(0);
    });
    expect(screen.getByRole("link", { name: "返回列表" })).toHaveAttribute("href", "/signal-lab");
  });

  it("passes hidden visibility through to the candidate endpoint", async () => {
    apiMock.readApiImpl = async () =>
      ok({ ...minimalPulseItem(), display_status: "hidden_invalid_output" });
    renderAt("/signal-lab/pulse/cand-1?visibility=hidden");
    await waitFor(() => {
      expect(apiMock.readApi).toHaveBeenCalledWith(
        "/api/signal-lab/pulse/cand-1",
        expect.objectContaining({
          params: expect.objectContaining({ visibility: "hidden" }),
        }),
      );
    });
    expect(screen.getByRole("link", { name: "返回列表" })).toHaveAttribute(
      "href",
      "/signal-lab?visibility=hidden",
    );
  });

  it("renders in-page 404 when candidate is missing", async () => {
    apiMock.readApiImpl = async () => {
      throw new ApiError("not found", 404);
    };
    renderAt("/signal-lab/pulse/ghost");
    await waitFor(() => {
      expect(screen.getByText(/不存在|失效|not found/i)).toBeInTheDocument();
    });
  });
});

function minimalPulseItem() {
  return {
    candidate_id: "cand-1",
    candidate_type: "token_target",
    subject_key: "toly",
    target_type: "Asset",
    target_id: "asset:pepe",
    symbol: "PEPE",
    window: "1h",
    scope: "all",
    evidence_status: "complete",
    decision_status: "token_watch",
    display_status: "display_token_watch",
    evidence_packet_hash: "sha256:detail-packet",
    verdict: "token_watch",
    social_phase: "ignition",
    candidate_score: 0.82,
    score_band: "watch",
    evidence_event_ids: [],
    source_event_ids: [],
    factor_snapshot: {
      schema_version: "token_factor_snapshot_v3_social_attention",
      subject: {
        target_type: "Asset",
        target_id: "asset:pepe",
        symbol: "PEPE",
        chain: "solana",
        address: "pepe",
      },
      market: marketContextFixture({ event_anchor: null, decision_latest: null }),
      gates: {
        eligible_for_high_alert: false,
        max_decision: "watch",
        blocked_reasons: [],
        risk_reasons: [],
      },
      data_health: { identity: "ready", market: "missing", social: "ready", alpha: "ready" },
      families: {
        social_heat: {
          raw_score: 82,
          score: 82,
          weight: 0.35,
          data_health: "ready",
          facts: {},
          factors: {},
        },
        social_propagation: {
          raw_score: 70,
          score: 70,
          weight: 0.3,
          data_health: "ready",
          facts: {},
          factors: {},
        },
        semantic_catalyst: {
          raw_score: 68,
          score: 68,
          weight: 0.25,
          data_health: "ready",
          facts: {},
          factors: {},
        },
        timing_risk: {
          raw_score: 50,
          score: 50,
          weight: 0.1,
          data_health: "missing",
          facts: {},
          factors: {},
        },
      },
      normalization: {
        status: "ready",
        cohort: {},
        factor_ranks: {},
        alpha_rank: 1,
        cohort_size: 1,
      },
      composite: {
        rank_score: 82,
        recommended_decision: "watch",
        family_scores: {
          social_heat: 82,
          social_propagation: 70,
          semantic_catalyst: 68,
          timing_risk: 50,
        },
      },
      provenance: { source_event_ids: ["event-1"], computed_at_ms: 1_700_000_000_000 },
    },
    decision: {
      route: "meme",
      recommendation: "watchlist",
      confidence: 0.62,
      abstain_reason: null,
      stage_count: 3,
      summary_zh: "summary",
      invalidation_conditions: [],
      residual_risks: [],
      evidence_event_ids: ["event-1"],
    },
    gate: {
      candidate_score: 82,
      score_band: "watch",
      blocked_reasons: [],
    },
    fact_card: { mentions_1h: 1, unique_authors: 1 },
    agent_run_id: null,
    pulse_version: "v1",
    gate_version: "v1",
    prompt_version: "v1",
    schema_version: "v1",
    created_at_ms: 1_000,
    updated_at_ms: 2_000,
    playbooks: [],
  };
}
