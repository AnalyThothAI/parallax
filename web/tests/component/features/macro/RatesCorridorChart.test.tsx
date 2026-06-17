import { RatesCorridorChart } from "@features/macro/ui/rates/RatesCorridorChart";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("RatesCorridorChart", () => {
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
