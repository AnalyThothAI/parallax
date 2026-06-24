import { MacroDiagnosticsPanel } from "@features/macro/ui/workbench/MacroDiagnosticsPanel";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

describe("MacroDiagnosticsPanel", () => {
  afterEach(() => {
    cleanup();
  });

  it("does not use source counts as diagnostics panel header meta", () => {
    const { container } = render(
      <MacroDiagnosticsPanel
        diagnostics={{
          buckets: [],
          sourceCount: 0,
          sourceMeta: "0 个来源",
          statusLabel: null,
        }}
        source={{}}
      />,
    );

    const diagnostics = screen.getByRole("region", { name: "数据诊断" });
    const summary = within(diagnostics).getByLabelText("诊断摘要");
    expect(within(summary).getByText("来源")).toBeInTheDocument();
    expect(within(summary).getByText("0 个来源")).toBeInTheDocument();
    expect(container.querySelector(".macro-panel-head span")).toBeNull();
  });

  it("does not translate macro gap severity or scope codes into diagnostics text", () => {
    render(
      <MacroDiagnosticsPanel
        diagnostics={{
          buckets: [
            {
              items: [
                {
                  detail: "后端明示缺口",
                  key: "global_history_short",
                  label: "全局历史样本不足",
                  scope: "module_blocker",
                  severity: "warning",
                },
              ],
              key: "module_gaps",
              label: "模块缺口",
            },
          ],
          sourceCount: 0,
          sourceMeta: "0 个来源",
          statusLabel: null,
        }}
        source={{}}
      />,
    );

    const diagnostics = screen.getByRole("region", { name: "数据诊断" });
    expect(within(diagnostics).getByText("全局历史样本不足")).toBeInTheDocument();
    expect(diagnostics).not.toHaveTextContent("警告");
    expect(diagnostics).not.toHaveTextContent("模块阻断");
  });
});
