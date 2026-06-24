import { MacroMarketEventFlowPanel } from "@features/macro/ui/workbench/MacroMarketEventFlowPanel";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("MacroMarketEventFlowPanel", () => {
  it("does not use event dates as fallback meta labels", () => {
    render(
      <MacroMarketEventFlowPanel
        flow={{
          key: "market_event_flow",
          label: "市场事件流",
          rows: [
            {
              categoryLabel: null,
              date: "2026-06-10",
              detail: "油价与美元走强。",
              impactLabel: null,
              key: "news:macro-row",
              label: "宏观事件",
              meta: null,
              severityLabel: null,
              sourceUrl: null,
              watch: "跟踪风险资产反应。",
            },
          ],
        }}
      />,
    );

    const flow = screen.getByRole("region", { name: "市场事件流" });
    expect(within(flow).getByText("宏观事件")).toBeInTheDocument();
    expect(flow).not.toHaveTextContent("2026-06-10");
  });
});
