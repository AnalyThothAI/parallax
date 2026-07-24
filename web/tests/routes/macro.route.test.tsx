import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { macroLiveEvidenceFixture, macroResearchFixture } from "@tests/fixtures/macroFixture";
import { ok } from "@tests/msw/fixtures";
import { mockLiveRadarRoute } from "@tests/msw/scenarios";
import { renderAppRoute } from "@tests/render/renderRoute";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiMock, setupAppRouteTest } from "./routeTestSetup";

describe("macro live evidence and research workbench", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  beforeEach(() => {
    configureMacroApi(macroResearchFixture());
  });

  it("renders the live six-category dashboard and compact research card", async () => {
    renderAppRoute("/macro");

    expect(await screen.findByRole("heading", { level: 1, name: "宏观实时数据" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "总览与官方催化" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "利率与通胀" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "增长与就业" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "流动性与资金" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "信用" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "跨资产" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "宏观研究：增长与实际利率的拉锯" })).toBeVisible();
    expect(screen.getByText(/最近成功读取/)).toBeVisible();
    expect(screen.getByText("读取正常")).toBeVisible();
    expect(screen.getByText(/未分类最新事实/)).toBeVisible();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/evidence/dashboard", {
        params: { window: "90d" },
        token: "secret",
      }),
    );
  });

  it("renders a complete live detail page with chart, missing row, and searchable table", async () => {
    renderAppRoute("/macro/rates-inflation?window=90d");

    expect(await screen.findByRole("heading", { level: 1, name: "利率与通胀" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "历史序列" })).toBeVisible();
    expect(screen.getByRole("img", { name: /美国 10 年期国债收益率历史折线图/ })).toBeVisible();
    expect(screen.getByRole("heading", { name: "完整明细" })).toBeVisible();
    expect(screen.getAllByText("该行尚无持久化观测").length).toBeGreaterThan(0);
    expect(screen.getByText(/最近研究交易日/)).toBeVisible();

    fireEvent.change(screen.getByPlaceholderText("搜索名称、concept、source、series"), {
      target: { value: "美国 10" },
    });
    expect(screen.getByText("rates:dgs10")).toBeVisible();
    expect(screen.queryByText("rates:dgs10:missing")).toBeNull();
  });

  it("keeps the live history window in URL-backed query state", async () => {
    renderAppRoute("/macro/credit?window=30d");

    expect(await screen.findByRole("heading", { level: 1, name: "信用" })).toBeVisible();
    expect(screen.getByLabelText("历史窗口")).toHaveValue("30d");
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/evidence/credit", {
        params: { window: "30d" },
        token: "secret",
      }),
    );
  });

  it("renders one persisted Chinese research document", async () => {
    renderAppRoute("/macro/research");

    expect(await screen.findByRole("heading", { level: 1, name: "宏观研究工作台" })).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 2, name: "宏观研究：增长与实际利率的拉锯" }),
    ).toBeVisible();
    expect(screen.getByRole("heading", { name: "核心机制" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "关键反证" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "证据缺口与开放问题" })).toBeVisible();
    expect(screen.getByText("期限溢价历史窗口不足")).toBeVisible();
    const citations = screen.getByRole("heading", { name: "引用与事实溯源" }).closest("section");
    expect(citations).not.toBeNull();
    expect(within(citations!).getByText("U.S. Treasury 10Y")).toBeVisible();
    expect(within(citations!).getByRole("link", { name: "来源" })).toHaveAttribute(
      "href",
      "https://fred.stlouisfed.org/series/DGS10",
    );
    expect(document.body.textContent).not.toMatch(
      /macro_decision_v2|八类风险|daily.?judgment|买入|卖出|仓位/i,
    );
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/research", { token: "secret" }),
    );
  });

  it("keeps audit metadata collapsed until requested", async () => {
    renderAppRoute("/macro/research");

    await screen.findByRole("heading", { name: "核心机制" });
    const details = document.querySelector("details.macro-research-audit");
    expect(details).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("审阅与运行审计"));
    expect(details).toHaveAttribute("open");
    expect(screen.getByText("反证已覆盖，但期限溢价仍应标为缺口。")).toBeVisible();
    expect(screen.getByText(/planning_used/)).toBeVisible();
  });

  it("preserves GFM research structure and safe link behavior", async () => {
    const fixture = macroResearchFixture();
    const publication = fixture.publication;
    if (!publication) throw new Error("current fixture must include a publication");
    publication.sections[0]!.body_markdown = [
      "| 指标 | 观察 |",
      "| --- | --- |",
      "| 实际利率 | 高位 |",
      "",
      "1. 先核对增长",
      "2. 再检查信用",
      "",
      "> **关键反证**仍在，需结合 *期限溢价*。",
      "",
      "内联变量 `real_yield`，参见 [M001](#citation-M001) 与 [外部资料](https://example.com/macro)。",
      "",
      "```text",
      "growth != credit",
      "```",
    ].join("\n");
    configureMacroApi(fixture);

    renderAppRoute("/macro/research");

    expect(await screen.findByRole("table")).toBeVisible();
    expect(screen.getByRole("columnheader", { name: "指标" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "实际利率" })).toBeVisible();
    const orderedListItem = screen.getByText("先核对增长");
    expect(orderedListItem.closest("ol")).not.toBeNull();
    const blockquote = document.querySelector<HTMLElement>(".macro-research-markdown blockquote");
    expect(blockquote).not.toBeNull();
    expect(within(blockquote!).getByText("关键反证").tagName).toBe("STRONG");
    expect(screen.getByText("期限溢价").tagName).toBe("EM");
    expect(screen.getByText("real_yield").tagName).toBe("CODE");
    expect(screen.getByText("growth != credit").closest("pre")).not.toBeNull();

    const citationLink = screen.getByRole("link", { name: "M001" });
    expect(citationLink).toHaveAttribute("href", "#citation-M001");
    expect(citationLink).not.toHaveAttribute("target");
    expect(citationLink).not.toHaveAttribute("rel");

    const externalLink = screen.getByRole("link", { name: "外部资料" });
    expect(externalLink).toHaveAttribute("href", "https://example.com/macro");
    expect(externalLink).toHaveAttribute("target", "_blank");
    expect(externalLink).toHaveAttribute("rel", "noreferrer noopener");
  });

  it("drops raw HTML and keeps dangerous URLs inert", async () => {
    const fixture = macroResearchFixture();
    const publication = fixture.publication;
    if (!publication) throw new Error("current fixture must include a publication");
    publication.sections[0]!.body_markdown = [
      "安全正文。",
      "",
      '<script>window.__macroInjected = "yes"</script>',
      "",
      '<img src="x" alt="恶意图片" onerror="window.__macroInjected = \'yes\'">',
      "",
      "[危险链接](javascript:window.__macroInjected='yes')",
    ].join("\n");
    configureMacroApi(fixture);

    renderAppRoute("/macro/research");

    expect(await screen.findByText("安全正文。")).toBeVisible();
    expect(document.querySelector(".macro-research-markdown script")).toBeNull();
    expect(screen.queryByRole("img", { name: "恶意图片" })).toBeNull();
    const dangerousLink = screen.getByText("危险链接").closest("a");
    expect(dangerousLink).not.toBeNull();
    expect(dangerousLink).not.toHaveAttribute("href");
    expect(document.body.textContent).not.toContain("window.__macroInjected");
    expect(
      (window as typeof window & { __macroInjected?: string }).__macroInjected,
    ).toBeUndefined();
  });

  it("reads an explicit completed session from URL state", async () => {
    configureMacroApi(macroResearchFixture("historical"));
    renderAppRoute("/macro/research?session_date=2026-07-22");

    expect(await screen.findByText("历史研究")).toBeVisible();
    expect(screen.getByText(/请求交易日 2026-07-22/)).toBeVisible();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/research", {
        params: { session_date: "2026-07-22" },
        token: "secret",
      }),
    );
  });

  it.each([
    ["generating", "研究正在生成", "页面只轮询持久化状态"],
    ["failed", "本次研究生成失败", "provider_timeout"],
    ["missing", "该交易日尚无宏观研究", "选择其他已完成交易日"],
  ] as const)("renders persisted %s state", async (state, title, hint) => {
    configureMacroApi(macroResearchFixture(state));
    renderAppRoute("/macro/research");

    expect(await screen.findByText(title)).toBeVisible();
    expect(screen.getByText(new RegExp(hint))).toBeVisible();
    expect(screen.queryByRole("heading", { name: "核心机制" })).toBeNull();
  });

  it("switches between explicit history and latest without child navigation", async () => {
    renderAppRoute("/macro/research?session_date=2026-07-22");

    const input = await screen.findByLabelText("已完成交易日");
    fireEvent.change(input, { target: { value: "2026-07-21" } });
    fireEvent.click(screen.getByRole("button", { name: "读取" }));
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/research", {
        params: { session_date: "2026-07-21" },
        token: "secret",
      }),
    );
    expect(screen.queryByRole("navigation", { name: "宏观数据分类" })).toBeNull();
  });
});

function configureMacroApi(data: ReturnType<typeof macroResearchFixture>) {
  setupAppRouteTest((mock) => {
    mockLiveRadarRoute(mock);
    const baseGetApi = mock.getApiImpl;
    mock.getApiImpl = async (path, options) => {
      if (path === "/api/macro/research") return ok(data);
      if (path.startsWith("/api/macro/evidence/")) {
        const viewId = path.split("/").at(-1);
        if (
          viewId === "dashboard" ||
          viewId === "overview" ||
          viewId === "rates-inflation" ||
          viewId === "growth-labor" ||
          viewId === "liquidity-funding" ||
          viewId === "credit" ||
          viewId === "cross-asset"
        ) {
          return ok(macroLiveEvidenceFixture(viewId));
        }
      }
      return baseGetApi(path, options);
    };
  });
}
