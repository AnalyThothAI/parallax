import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SignalLabChain } from "../api/types";
import { SignalLabPulse } from "./SignalLabPulse";

afterEach(() => cleanup());

describe("SignalLabPulse", () => {
  it("shows every pulse item instead of truncating to a date-window-sized preview", () => {
    const items = Array.from({ length: 7 }, (_, index) => chain(index));

    render(
      <SignalLabPulse
        data={{
          query: { window: "24h", horizon: "6h", scope: "all" },
          items,
          summary: { extracted: 7, seeded: 0, frozen: 0, settled: 0, credited: 0 },
          returned_count: 7,
          has_more: false,
          next_cursor: null
        }}
        onOpenLab={vi.fn()}
        onSelect={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: /TOKEN6 · 6h/ })).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(7);
  });
});

function chain(index: number): SignalLabChain {
  return {
    chain_id: `chain-${index}`,
    stage: "extracted",
    received_at_ms: 1_700_000_000_000 + index,
    updated_at_ms: 1_700_000_000_000 + index,
    asset: `TOKEN${index}`,
    horizon: "6h",
    source: "toly",
    event_type: "mention",
    title: `TOKEN${index}`,
    summary: `summary ${index}`,
    score: 0.5,
    outcome_status: null,
    credit_status: null,
    risks: [],
    evidence_chips: [],
    lineage: {},
    social_event: null,
    seed: null,
    snapshot: null,
    outcome: null,
    credits: []
  } as SignalLabChain;
}
