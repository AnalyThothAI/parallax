import {
  MacroCorrelationMatrixTable,
  MacroCorrelationPairList,
} from "@features/macro/ui/correlation/MacroCorrelationTables";
import type { MacroAssetCorrelationData, MacroAssetCorrelationPair } from "@lib/types";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("Macro correlation tables", () => {
  it("returns no matrix chrome when backend caption is absent", () => {
    const { container } = render(
      <MacroCorrelationMatrixTable
        data={correlationFixture()}
        titleByKey={{ "asset:spy": "SPY" }}
      />,
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("table", { name: "60d 资产相关性矩阵" })).not.toBeInTheDocument();
  });

  it("returns no matrix chrome when there are no drawable correlation rows", () => {
    const { container, rerender } = render(
      <MacroCorrelationMatrixTable
        data={{ ...correlationFixture(), assets: [], matrix: [] }}
        titleByKey={{}}
      />,
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("暂无可用资产")).not.toBeInTheDocument();

    rerender(
      <MacroCorrelationMatrixTable
        data={{
          ...correlationFixture(),
          matrix: [],
        }}
        titleByKey={{ "asset:spy": "SPY" }}
      />,
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("table", { name: "60d 资产相关性矩阵" })).not.toBeInTheDocument();
  });

  it("returns no pair-list chrome when there are no correlation pairs", () => {
    const { container } = render(<MacroCorrelationPairList pairs={[]} titleByKey={{}} />);

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("暂无可用配对")).not.toBeInTheDocument();
  });

  it("does not render placeholder dashes for missing correlation cells or date ranges", () => {
    render(
      <>
        <MacroCorrelationMatrixTable
          data={{
            ...correlationFixture(),
            matrix: [
              {
                concept_key: "asset:spy",
                correlations: { "asset:spy": null },
              },
            ],
          }}
          label="60日资产相关性矩阵"
          titleByKey={{ "asset:spy": "SPY" }}
        />
        <MacroCorrelationPairList
          pairs={[
            {
              available: true,
              correlation: 0.66,
              end_date: null,
              left: "asset:spy",
              reason: null,
              right: "asset:qqq",
              sample_size: 60,
              start_date: null,
            } as MacroAssetCorrelationPair,
          ]}
          titleByKey={{ "asset:qqq": "QQQ", "asset:spy": "SPY" }}
        />
      </>,
    );

    const table = screen.getByRole("table", { name: "60日资产相关性矩阵" });
    expect(within(table).queryByText("-")).not.toBeInTheDocument();
    expect(screen.getByText("样本=60")).toBeInTheDocument();
    expect(screen.queryByText("- 至 -")).not.toBeInTheDocument();
  });
});

function correlationFixture(): MacroAssetCorrelationData {
  return {
    asof_date: "2026-05-20",
    assets: [
      {
        concept_key: "asset:spy",
        end_date: "2026-05-20",
        latest_observed_at: "2026-05-20",
        observations_count: 64,
        return_count: 60,
        sources: ["yahoo"],
        start_date: "2026-02-20",
        title: "SPY",
      },
    ],
    data_gaps: [],
    matrix: [
      {
        concept_key: "asset:spy",
        correlations: { "asset:spy": 1 },
      },
    ],
    pairs: [],
    window: "60d",
  };
}
