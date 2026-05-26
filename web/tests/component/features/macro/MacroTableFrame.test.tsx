import { readFileSync } from "node:fs";
import { join } from "node:path";

import { MacroTableFrame } from "@features/macro/ui/tables/MacroTableFrame";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

describe("MacroTableFrame", () => {
  afterEach(() => {
    cleanup();
  });

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

  it("scopes sticky first-column matching to the direct table only", () => {
    render(
      <MacroTableFrame caption="嵌套表格" stickyFirstColumn>
        <table>
          <thead>
            <tr>
              <th scope="col">外层资产</th>
              <th scope="col">外层状态</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">SPX</th>
              <td>
                <table aria-label="内嵌详情">
                  <thead>
                    <tr>
                      <th scope="col">内层字段</th>
                      <th scope="col">内层值</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>beta</td>
                      <td>1.0</td>
                    </tr>
                  </tbody>
                </table>
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td>外层脚注</td>
              <td>已校验</td>
            </tr>
          </tfoot>
        </table>
      </MacroTableFrame>,
    );

    const stickySelector = macroTableStickySelector();
    const matchedText = Array.from(document.querySelectorAll(stickySelector)).map(
      (element) => element.textContent,
    );

    expect(matchedText).toEqual(["外层资产", "SPX", "外层脚注"]);
    expect(matchedText).not.toContain("内层字段");
    expect(matchedText).not.toContain("beta");
  });
});

function macroTableStickySelector(): string {
  const macroTableFrameCss = readFileSync(
    join(process.cwd(), "src/features/macro/ui/tables/macroTableFrame.css"),
    "utf8",
  );
  expect(macroTableFrameCss).toContain("position: sticky");
  const selectors = Array.from(
    macroTableFrameCss.matchAll(/([^{}]+)\{[^{}]*position:\s*sticky;[^{}]*\}/g),
    (match) => match[1]?.trim() ?? "",
  ).filter(Boolean);
  expect(selectors).toHaveLength(1);
  return selectors[0] ?? "";
}
