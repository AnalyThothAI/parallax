import { MacroMetricStrip } from "@features/macro/ui/primitives/MacroMetricStrip";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

describe("MacroMetricStrip", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders compact market labels in stable metric zones", () => {
    render(
      <MacroMetricStrip
        ariaLabel="关键指标"
        metrics={[
          {
            key: "asset:spx",
            label: "标普500",
            observedAtLabel: "观测于 2026-05-22",
            quality: "ok",
            qualityLabel: "可用",
            shortLabel: "SPX",
            unitLabel: "点",
            value: "7473.47",
          },
          {
            key: "macro:payrolls",
            label: "Payrolls",
            observedAtLabel: "观测于 2026-05-03",
            quality: "partial",
            qualityLabel: "部分可用",
            shortLabel: "Payrolls",
            unitLabel: null,
            value: "177K",
          },
        ]}
      />,
    );

    const strip = screen.getByRole("region", { name: "关键指标" });
    expect(strip).toHaveAttribute("data-density", "auto");
    expect(screen.getByText("SPX")).toHaveAttribute("data-macro-metric-label", "true");
    expect(screen.getByText("Payrolls")).toHaveAttribute("data-macro-metric-label", "true");
    expect(within(strip).getByText("7473.47")).toBeInTheDocument();
    expect(within(strip).getByText("观测于 2026-05-03")).toBeInTheDocument();
  });

  it("renders a stable empty status when no metrics are available", () => {
    render(<MacroMetricStrip ariaLabel="关键指标" density="compact" metrics={[]} />);

    const strip = screen.getByRole("region", { name: "关键指标" });
    expect(strip).toHaveAttribute("data-density", "compact");
    expect(within(strip).getByRole("status")).toHaveTextContent("暂无关键指标");
  });
});
