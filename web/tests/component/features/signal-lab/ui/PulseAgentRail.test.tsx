import { buildPulseDetailView } from "@features/signal-lab/model/pulseDetail";
import { PulseAgentRail } from "@features/signal-lab/ui/PulseDetail/PulseAgentRail";
import type { SignalPulseItem } from "@lib/types";
import { cleanup, render, screen } from "@testing-library/react";
import {
  tittyPulseFixture,
  tittySourceEventsFixture,
  TITTY_NOW_MS,
} from "@tests/fixtures/signal-lab";
import { afterEach, describe, expect, it } from "vitest";

describe("PulseAgentRail", () => {
  afterEach(() => {
    cleanup();
  });

  const withDecisionSurface = (): SignalPulseItem => ({
    ...tittyPulseFixture,
    decision: {
      ...tittyPulseFixture.decision,
      narrative_archetype: "KOL 扩散",
      narrative_thesis_zh: "独立作者扩散把讨论推到二级账号，链上流动性仍偏薄，需要观察后续承接。",
      bull_view: {
        strength: "moderate",
        thesis_zh: "多个独立账号在同一窗口提及，社交热度具备继续扩散的条件。",
        supporting_event_ids: [tittySourceEventsFixture[0].event_id],
      },
      bear_view: {
        strength: "weak",
        thesis_zh: "流动性偏薄且传播集中，若后续缺少新作者容易快速降温。",
        supporting_event_ids: [tittySourceEventsFixture[1].event_id],
      },
      playbook: {
        has_playbook: true,
        watch_signals: ["新增独立作者继续扩散", "流动性不再下降"],
        exit_triggers: ["社交热度回落", "流动性继续抽离"],
        monitoring_horizon: "4h",
      },
      evidence_event_urls: {
        [tittySourceEventsFixture[0].event_id]: "https://x.com/moontoklisting/status/1",
      },
    },
  });

  it("renders the public decision rail without run-step stage cards", () => {
    const view = buildPulseDetailView({
      item: tittyPulseFixture,
      sourceEvents: tittySourceEventsFixture,
      now: TITTY_NOW_MS,
    });
    render(<PulseAgentRail agent={view.agent} />);
    expect(screen.queryByText(/阶段 1 · 信号分析/)).not.toBeInTheDocument();
    expect(screen.queryByText(/阶段 2 · 反方风险/)).not.toBeInTheDocument();
    expect(screen.queryByText(/阶段 3 · 风险裁决/)).not.toBeInTheDocument();
    expect(screen.getByText(/暂无公开决策摘要/)).toBeInTheDocument();
  });

  it("renders v2 decision surface", () => {
    const view = buildPulseDetailView({
      item: withDecisionSurface(),
      sourceEvents: tittySourceEventsFixture,
      now: TITTY_NOW_MS,
    });
    render(<PulseAgentRail agent={view.agent} />);

    expect(screen.getByText("v2 决策")).toBeInTheDocument();
    expect(screen.getByText("KOL 扩散")).toBeInTheDocument();
    expect(screen.getByText(/独立作者扩散把讨论推到二级账号/)).toBeInTheDocument();
    expect(
      screen.getByText("多个独立账号在同一窗口提及，社交热度具备继续扩散的条件。"),
    ).toBeInTheDocument();
    expect(screen.getByText("新增独立作者继续扩散")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: tittySourceEventsFixture[0].event_id }),
    ).toHaveAttribute("href", "https://x.com/moontoklisting/status/1");
    expect(screen.queryByText(/阶段 1 · 信号分析/)).not.toBeInTheDocument();
  });

  it("does not render absent bull or bear decision sections", () => {
    const item = withDecisionSurface();
    const view = buildPulseDetailView({
      item: {
        ...item,
        decision: {
          ...item.decision,
          bull_view: { strength: "absent", thesis_zh: "", supporting_event_ids: [] },
          bear_view: { strength: "absent", thesis_zh: "", supporting_event_ids: [] },
        },
      },
      sourceEvents: tittySourceEventsFixture,
      now: TITTY_NOW_MS,
    });
    render(<PulseAgentRail agent={view.agent} />);

    expect(screen.queryByText("看多")).not.toBeInTheDocument();
    expect(screen.queryByText("看空")).not.toBeInTheDocument();
  });

  it("uses mismatch copy that points to decision and evidence links", () => {
    const view = buildPulseDetailView({
      item: tittyPulseFixture,
      sourceEvents: tittySourceEventsFixture,
      now: TITTY_NOW_MS,
    });
    render(<PulseAgentRail agent={view.agent} />);

    expect(
      screen.getByText(
        "策略门将该资产推到 top 区间，但 Agent 最终置信度偏低。请核对公共决策、证据链接和市场数据。",
      ),
    ).toBeInTheDocument();
  });

  it("does not need run-step stages in the public payload", () => {
    const view = buildPulseDetailView({
      item: tittyPulseFixture,
      sourceEvents: tittySourceEventsFixture,
      now: TITTY_NOW_MS,
    });
    render(<PulseAgentRail agent={view.agent} />);
    expect(screen.getByText(/暂无公开决策摘要/)).toBeInTheDocument();
  });
});
