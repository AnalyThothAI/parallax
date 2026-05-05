import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScoreBucketPanel } from "./ScoreBucketPanel";
import { SettlementCoveragePanel } from "./SettlementCoveragePanel";
import { WeightDriftPanel } from "./WeightDriftPanel";

describe("Harness evaluation panels", () => {
  it("renders score buckets, settlement coverage, and report-only weights", () => {
    render(
      <>
        <ScoreBucketPanel
          items={[
            {
              bucket: ">=0.8",
              sample_count: 32,
              avg_normalized_outcome: 0.37,
              avg_abnormal_return: 0.0042,
              hit_rate: 0.62,
              settled_count: 28,
              pending_count: 4
            }
          ]}
        />
        <SettlementCoveragePanel insufficient={3} missing_market={2} pending={7} settled={28} />
        <WeightDriftPanel
          items={[
            {
              key: "meme_phrase_seed",
              weight_type: "event_type",
              horizon: "6h",
              n: 120,
              mean_credit: 0.083,
              weight: 1.04,
              status: "report_only"
            }
          ]}
        />
      </>
    );

    expect(screen.getByText(">=0.8")).toBeInTheDocument();
    expect(screen.getByText("missing_market")).toBeInTheDocument();
    expect(screen.getByText("report_only")).toBeInTheDocument();
  });
});
