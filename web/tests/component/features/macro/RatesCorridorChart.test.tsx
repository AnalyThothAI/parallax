import { RatesCorridorChart } from "@features/macro/ui/rates/RatesCorridorChart";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("RatesCorridorChart", () => {
  it("does not render placeholder legend values when latest values are missing", () => {
    render(
      <RatesCorridorChart
        model={{
          lines: [
            {
              key: "effr",
              label: "EFFR",
              latest: null,
              points: [{ time: "2026-06-16", value: 4.5 }],
              unit: "percent",
            },
          ],
          lower: null,
          missingLabels: [],
          upper: null,
        }}
      />,
    );

    const figure = screen.getByRole("figure", { name: "联邦基金目标走廊" });
    expect(figure).toHaveTextContent("EFFR");
    expect(figure).not.toHaveTextContent("n/a");
  });

  it("returns no chart chrome when the corridor model has no drawable series", () => {
    const { container } = render(
      <RatesCorridorChart
        model={{
          lines: [],
          lower: null,
          missingLabels: ["EFFR"],
          upper: null,
        }}
      />,
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("暂无可绘制走廊数据")).not.toBeInTheDocument();
  });
});
