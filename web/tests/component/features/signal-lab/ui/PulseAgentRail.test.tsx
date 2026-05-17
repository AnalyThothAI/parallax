import { buildPulseDetailView } from "@features/signal-lab/model/pulseDetail";
import {
  tittyLegacyStages,
  tittyPulseFixture,
  tittySourceEventsFixture,
  TITTY_NOW_MS,
} from "@features/signal-lab/test/fixtures";
import { PulseAgentRail } from "@features/signal-lab/ui/PulseDetail/PulseAgentRail";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("PulseAgentRail", () => {
  it("renders v2 investigator + decision_maker stage cards", () => {
    const view = buildPulseDetailView({
      item: tittyPulseFixture,
      sourceEvents: tittySourceEventsFixture,
      now: TITTY_NOW_MS,
    });
    render(<PulseAgentRail agent={view.agent} />);
    expect(screen.getByText(/阶段 1 · 调研/)).toBeInTheDocument();
    expect(screen.getByText(/阶段 2 · 决策/)).toBeInTheDocument();
    expect(screen.queryByTestId("legacy-stage-notice")).not.toBeInTheDocument();
  });

  it("falls back to legacy placeholder cards when only analyst/critic/judge are present", () => {
    const view = buildPulseDetailView({
      item: { ...tittyPulseFixture, stages: tittyLegacyStages },
      sourceEvents: tittySourceEventsFixture,
      now: TITTY_NOW_MS,
    });
    const { container } = render(<PulseAgentRail agent={view.agent} />);

    expect(screen.getByTestId("legacy-stage-notice")).toBeInTheDocument();
    expect(screen.getByText("Legacy · analyst")).toBeInTheDocument();
    expect(screen.getByText("Legacy · critic")).toBeInTheDocument();
    expect(screen.getByText("Legacy · judge")).toBeInTheDocument();
    // Should not crash; container is rendered
    expect(container.querySelector("aside")).toBeInTheDocument();
  });

  it("does not throw when stages payload is entirely missing", () => {
    const view = buildPulseDetailView({
      item: { ...tittyPulseFixture, stages: null },
      sourceEvents: tittySourceEventsFixture,
      now: TITTY_NOW_MS,
    });
    render(<PulseAgentRail agent={view.agent} />);
    expect(screen.getByText(/暂无 stage 数据/)).toBeInTheDocument();
  });
});
