import { AssetDiagnosticsBoard } from "@features/macro/ui/assets/AssetDiagnosticsBoard";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("AssetDiagnosticsBoard", () => {
  it("does not translate asset gap severity or scope codes into diagnostics text", () => {
    render(
      <AssetDiagnosticsBoard
        buckets={[
          {
            items: [
              {
                detail: "后端明示缺口",
                key: "missing_asset_spy",
                label: "缺少当前数据：SPY",
                scope: "module_blocker",
                severity: "warning",
              },
            ],
            key: "module_gaps",
            label: "模块缺口",
          },
        ]}
        provenance={{}}
        summary={{ gapCount: 1, moduleStatus: null, sourceCount: 0 }}
      />,
    );

    const diagnostics = screen.getByText("缺口 1").closest("details");

    expect(diagnostics).not.toBeNull();
    expect(within(diagnostics as HTMLElement).getByText("缺少当前数据：SPY")).toBeInTheDocument();
    expect(diagnostics).not.toHaveTextContent("警告");
    expect(diagnostics).not.toHaveTextContent("模块阻断");
  });
});
