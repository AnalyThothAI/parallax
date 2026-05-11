import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as client from "../../api/client";
import { PulseDetailPage } from "../PulseDetailPage";
import { useTraderStore } from "../../store/useTraderStore";

beforeEach(() => {
  useTraderStore.setState({ token: "test-token" });
  vi.restoreAllMocks();
});

function renderAt(url: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/signal-lab/pulse/:candidateId" element={<PulseDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PulseDetailPage", () => {
  it("renders a structural skeleton while the candidate request is pending", () => {
    vi.spyOn(client, "getApi").mockReturnValue(new Promise(() => undefined) as any);
    renderAt("/signal-lab/pulse/cand-1");

    expect(screen.getByLabelText("loading pulse detail")).toBeInTheDocument();
  });

  it("renders inspector when candidate exists", async () => {
    vi.spyOn(client, "getApi").mockResolvedValue({
      ok: true,
      data: minimalPulseItem()
    } as any);
    renderAt("/signal-lab/pulse/cand-1");
    await waitFor(() => {
      expect(screen.getAllByText(/PEPE|cand-1/).length).toBeGreaterThan(0);
    });
  });

  it("renders in-page 404 when candidate is missing", async () => {
    vi.spyOn(client, "getApi").mockRejectedValue({ status: 404 });
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
    pulse_status: "token_watch",
    verdict: "token_watch",
    social_phase: "ignition",
    narrative_type: "direct_token",
    candidate_score: 0.82,
    score_band: "watch",
    evidence_event_ids: [],
    source_event_ids: [],
    factor_snapshot: {
      schema_version: "token_factor_snapshot_v1",
      subject: { target_type: "Asset", target_id: "asset:pepe", symbol: "PEPE", chain: "solana", address: "pepe" },
      families: {},
      hard_gates: { eligible_for_high_alert: false, blocked_reasons: [] },
      composite: { rank_score: 82, recommended_decision: "watch" }
    },
    agent_recommendation: {
      schema_version: "pulse_recommendation_v1",
      recommendation: "watch",
      summary_zh: "summary",
      primary_reasons: [],
      upgrade_conditions: [],
      invalidation_conditions: [],
      residual_risks: []
    },
    gate: { pulse_status: "token_watch", candidate_score: 82, score_band: "watch", blocked_reasons: [] },
    fact_card: { mentions_1h: 1, unique_authors: 1 },
    agent_run_id: null,
    pulse_version: "v1",
    gate_version: "v1",
    prompt_version: "v1",
    schema_version: "v1",
    created_at_ms: 1_000,
    updated_at_ms: 2_000,
    playbooks: []
  };
}
