import { MacroShell, type MacroShellHeaderModel } from "@features/macro/ui/shell/MacroShell";
import { cleanup, screen, within } from "@testing-library/react";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  cleanup();
});

describe("MacroShell", () => {
  it("renders a compact title bar, breadcrumbs, and meta items", () => {
    const header: MacroShellHeaderModel = {
      breadcrumbs: [
        { label: "宏观", href: "/macro" },
        { label: "大类资产", href: "/macro/assets" },
        { label: "美股风险", href: "/macro/assets/equities" },
      ],
      eyebrow: "宏观工作台",
      question: "美股风险偏好是否足以确认加密 beta？",
      statusItems: [
        { label: "状态", value: "部分可用" },
        { label: "截至", value: "2026-05-20" },
        { label: "历史", value: "历史样本不足" },
      ],
      title: "美股风险",
    };

    renderWithProviders(
      <MacroShell header={header} pageKind="leaf" productTier="primary">
        <section aria-label="module content">Backend content slot</section>
      </MacroShell>,
      { route: "/macro/assets/equities" },
    );

    expect(screen.getByLabelText("宏观工作台")).toHaveAttribute("data-page-kind", "leaf");
    expect(screen.getByLabelText("宏观工作台")).toHaveAttribute("data-product-tier", "primary");
    expect(screen.getByRole("heading", { name: "美股风险" })).toBeInTheDocument();
    expect(screen.queryByText("美股风险偏好是否足以确认加密 beta？")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "宏观" })).toHaveAttribute("href", "/macro");
    const breadcrumb = screen.getByRole("navigation", { name: "宏观面包屑" });
    expect(within(breadcrumb).getByRole("link", { name: "大类资产" })).toHaveAttribute(
      "href",
      "/macro/assets",
    );
    const moduleNavigation = screen.getByRole("navigation", { name: "宏观模块" });
    expect(within(moduleNavigation).getByRole("link", { name: "总览" })).toHaveAttribute(
      "href",
      "/macro",
    );
    expect(within(moduleNavigation).getByRole("link", { name: "大类资产" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(moduleNavigation).getByRole("link", { name: "利率" })).toHaveAttribute(
      "href",
      "/macro/rates/fed-funds",
    );
    const state = screen.getByLabelText("页面状态");
    expect(within(state).getByText("截至")).toBeInTheDocument();
    expect(within(state).getByText("2026-05-20")).toBeInTheDocument();
    expect(within(state).getByText("部分可用")).toBeInTheDocument();
    expect(within(state).getByText("历史样本不足")).toBeInTheDocument();
    expect(screen.queryByText("历史样本不足：无法计算 60 日变化")).not.toBeInTheDocument();
    expect(screen.queryByText("equity_breadth_missing")).not.toBeInTheDocument();
    expect(screen.getByText("Backend content slot")).toBeInTheDocument();
    expect(screen.queryByText(/frontend score/i)).not.toBeInTheDocument();
  });

  it("renders matrix header actions through the same shell structure", () => {
    const header: MacroShellHeaderModel = {
      actions: <button type="button">60d</button>,
      breadcrumbs: [
        { label: "宏观", href: "/macro" },
        { label: "大类资产", href: "/macro/assets" },
        { label: "相关性", href: "/macro/assets/correlation" },
      ],
      eyebrow: "宏观工作台",
      question: "资产之间的风险传导是否正在同步？",
      statusItems: [
        { label: "状态", value: "滚动相关性" },
        { label: "窗口", value: "60d" },
      ],
      title: "资产相关性",
    };

    renderWithProviders(
      <MacroShell header={header} pageKind="matrix" productTier="primary">
        <section aria-label="matrix content">Matrix content</section>
      </MacroShell>,
      { route: "/macro/assets/correlation" },
    );

    expect(screen.getByLabelText("宏观工作台")).toHaveAttribute("data-page-kind", "matrix");
    expect(screen.getByRole("heading", { name: "资产相关性" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "宏观模块" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "宏观面包屑" })).toHaveTextContent(
      "宏观/大类资产/相关性",
    );
    expect(screen.getByRole("button", { name: "60d" })).toBeInTheDocument();
    expect(screen.getByLabelText("页面操作")).toContainElement(
      screen.getByRole("button", { name: "60d" }),
    );
  });

  it("renders a scoped freshness alert before module content", () => {
    const header: MacroShellHeaderModel = {
      breadcrumbs: [
        { label: "宏观", href: "/macro" },
        { label: "大类资产", href: "/macro/assets" },
      ],
      eyebrow: "宏观工作台",
      question: null,
      statusItems: [
        { label: "状态", value: "数据滞后" },
        { label: "截至", value: "截至 2026-01-16" },
      ],
      title: "美股风险",
    };

    renderWithProviders(
      <MacroShell
        freshnessAlert={{
          detail: "截至 2026-01-16；页面已使用最新可用观测，少数指标仍有新鲜度缺口。",
          items: ["最新观测滞后 135 天"],
          title: "部分宏观序列滞后",
        }}
        header={header}
        pageKind="leaf"
        productTier="primary"
      >
        <section aria-label="module content">Backend content slot</section>
      </MacroShell>,
      { route: "/macro/assets/equities" },
    );

    const alert = screen.getByRole("status", { name: "部分宏观序列滞后" });
    const content = screen.getByText("Backend content slot");

    expect(alert).toHaveTextContent("截至 2026-01-16");
    expect(alert).not.toHaveTextContent("事实层尚未追上最新日期");
    expect(alert).toHaveTextContent("最新观测滞后 135 天");
    expect(alert.compareDocumentPosition(content) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("keeps compact shell semantics independent from module ids", () => {
    const header: MacroShellHeaderModel = {
      breadcrumbs: [
        { label: "宏观", href: "/macro" },
        { label: "概览", href: "/macro" },
      ],
      eyebrow: "Macro terminal",
      question: null,
      statusItems: [{ label: "状态", value: "Ready" }],
      title: "Macro Overview",
    };

    renderWithProviders(
      <MacroShell header={header} pageKind="overview" productTier="secondary">
        <section aria-label="overview content">Overview content</section>
      </MacroShell>,
      { route: "/macro" },
    );

    const shell = screen.getByLabelText("宏观工作台");
    expect(shell).toHaveAttribute("data-page-kind", "overview");
    expect(shell).toHaveAttribute("data-product-tier", "secondary");
    expect(screen.getByRole("navigation", { name: "宏观面包屑" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "宏观模块" })).toBeInTheDocument();
    expect(screen.getByLabelText("页面状态")).toBeInTheDocument();
    expect(screen.queryByText("assets/equities")).not.toBeInTheDocument();
  });
});
