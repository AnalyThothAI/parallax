import { AssetDailyBrief } from "@features/macro/ui/assets/AssetDailyBrief";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

describe("AssetDailyBrief", () => {
  afterEach(() => {
    cleanup();
  });

  it("does not translate daily brief stance codes into display labels", () => {
    render(
      <AssetDailyBrief
        brief={{
          blocks: [
            {
              body: "股票代理有最新值，但样本不足。",
              id: "growth",
              stance: "supported",
              title: "增长代理",
            },
          ],
          headline: "今日判断：样本不足",
          status: "partial",
        }}
      />,
    );

    const signals = screen.getByRole("list", { name: "今日判断信号" });
    expect(within(signals).getByText("增长代理")).toBeInTheDocument();
    expect(signals).not.toHaveTextContent("支持");
    expect(signals).not.toHaveTextContent("supported");
  });

  it("omits daily brief quality fields without numeric backend values", () => {
    render(
      <AssetDailyBrief
        brief={{
          blocks: [],
          dataQuality: {
            status: "partial",
          },
          headline: "今日判断：覆盖率缺失",
          status: "partial",
        }}
      />,
    );

    expect(screen.queryByLabelText("今日判断数据质量")).not.toBeInTheDocument();
    expect(screen.queryByText("样本不足")).not.toBeInTheDocument();
  });
});
