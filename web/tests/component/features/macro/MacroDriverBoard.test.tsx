import { MacroDriverBoard } from "@features/macro/ui/workbench/MacroDriverBoard";
import type { MacroTransmissionNode } from "@lib/types";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

describe("MacroDriverBoard", () => {
  afterEach(() => {
    cleanup();
  });

  it("drops transmission nodes without backend key, label, or value", () => {
    render(
      <MacroDriverBoard
        ariaLabel="传导链"
        drivers={{
          evidenceCount: 0,
          evidenceGroups: [],
          transmissionCount: 3,
        }}
        title="传导链"
        transmission={
          [
            { key: "flow:yahoo", label: "真实传导", value: "风险偏好" },
            { key: "empty:value", label: "空值传导", value: "暂无" },
            { key: "kind:fallback", kind: "flow", status_label: "部分可用" },
            { label: "缺少 key", value: "风险偏好" },
            { value: "缺少标签" },
          ] as MacroTransmissionNode[]
        }
      />,
    );

    const flow = screen.getByRole("group", { name: "传导路径" });
    expect(within(flow).getByText("真实传导")).toBeInTheDocument();
    expect(within(flow).getByText("风险偏好")).toBeInTheDocument();
    expect(within(flow).queryByText("空值传导")).not.toBeInTheDocument();
    expect(within(flow).queryByText("flow")).not.toBeInTheDocument();
    expect(within(flow).queryByText("部分可用")).not.toBeInTheDocument();
    expect(within(flow).queryByText("缺少 key")).not.toBeInTheDocument();
    expect(within(flow).queryByText("缺少标签")).not.toBeInTheDocument();
    expect(flow).not.toHaveTextContent("暂无");
    expect(screen.queryByText("0 条证据")).not.toBeInTheDocument();
  });
});
