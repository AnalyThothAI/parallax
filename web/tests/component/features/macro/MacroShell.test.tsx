import { MacroShell } from "@features/macro/ui/shell/MacroShell";
import { screen, within } from "@testing-library/react";
import { macroModuleFixture } from "@tests/fixtures/macroFixture";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { describe, expect, it } from "vitest";

describe("MacroShell", () => {
  it("renders the module header, grouped tabs, gaps, and caller content", () => {
    renderWithProviders(
      <MacroShell moduleId="assets/equities" module={macroModuleFixture()}>
        <section aria-label="module content">Backend content slot</section>
      </MacroShell>,
      { route: "/macro/assets/equities" },
    );

    expect(screen.getByRole("heading", { name: "美股风险" })).toBeInTheDocument();
    expect(screen.getByText("美股风险偏好是否足以确认加密 beta？")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "宏观" })).toHaveAttribute("href", "/macro");
    const breadcrumb = screen.getByRole("navigation", { name: "宏观面包屑" });
    expect(within(breadcrumb).getByRole("link", { name: "大类资产" })).toHaveAttribute(
      "href",
      "/macro/assets",
    );
    const primaryTabs = screen.getByRole("navigation", { name: "宏观主模块" });
    expect(within(primaryTabs).getByRole("link", { name: "总览" })).toHaveAttribute(
      "href",
      "/macro",
    );
    expect(within(primaryTabs).getByRole("link", { name: "大类资产" })).toHaveAttribute(
      "data-active",
      "true",
    );
    const secondaryTabs = screen.getByRole("navigation", { name: "宏观模块" });
    expect(within(secondaryTabs).getByRole("link", { name: "美股" })).toHaveAttribute(
      "data-active",
      "true",
    );
    expect(within(secondaryTabs).getByRole("link", { name: "相关性" })).toHaveAttribute(
      "href",
      "/macro/assets/correlation",
    );
    const state = screen.getByLabelText("模块状态");
    expect(within(state).getByText("截至 2026-05-20")).toBeInTheDocument();
    expect(within(state).getByText("部分可用")).toBeInTheDocument();
    expect(within(state).getByText("历史样本不足")).toBeInTheDocument();
    expect(screen.getByText("历史样本不足：无法计算 60 日变化")).toBeInTheDocument();
    expect(screen.queryByText("equity_breadth_missing")).not.toBeInTheDocument();
    expect(screen.getByText("Backend content slot")).toBeInTheDocument();
    expect(screen.queryByText(/frontend score/i)).not.toBeInTheDocument();
  });
});
