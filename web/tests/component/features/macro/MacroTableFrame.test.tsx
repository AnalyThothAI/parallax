import { MacroTableFrame } from "@features/macro/ui/tables/MacroTableFrame";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("MacroTableFrame", () => {
  it("renders a labelled bounded horizontal scroll region", () => {
    render(
      <MacroTableFrame caption="大类资产矩阵" minWidth={720} stickyFirstColumn>
        <table>
          <thead>
            <tr>
              <th scope="col">资产</th>
              <th scope="col">状态</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">SPX</th>
              <td>可用</td>
            </tr>
          </tbody>
        </table>
      </MacroTableFrame>,
    );

    const frame = screen.getByRole("region", { name: "大类资产矩阵，可横向滚动" });
    expect(frame).toHaveAttribute("tabindex", "0");
    expect(frame).toHaveAttribute("aria-describedby");
    expect(frame).toHaveStyle({ "--macro-table-min-width": "720px" });
    expect(frame.parentElement).toHaveAttribute("data-sticky-first-column", "true");
    expect(screen.getByText("横向滚动查看完整列")).toBeInTheDocument();
  });
});
