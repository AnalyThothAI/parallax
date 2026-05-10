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
    summary_zh: "summary",
    why_now_zh: "why",
    bull_case_zh: [],
    bear_case_zh: [],
    confirmation_triggers_zh: [],
    invalidation_triggers_zh: [],
    top_risks: [],
    gate_reasons: [],
    risk_reasons: [],
    evidence_event_ids: [],
    source_event_ids: [],
    radar_score_json: {},
    market_context_json: {},
    thesis_json: {},
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
