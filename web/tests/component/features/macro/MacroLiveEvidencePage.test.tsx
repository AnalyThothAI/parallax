import { MacroLiveEvidencePage } from "@features/macro";
import { cleanup, screen } from "@testing-library/react";
import { macroLiveEvidenceFixture } from "@tests/fixtures/macroFixture";
import { server } from "@tests/msw/server";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

describe("MacroLiveEvidencePage", () => {
  beforeEach(() => {
    server.use(
      http.get(/.*\/api\/macro\/evidence\/rates-inflation$/, () =>
        HttpResponse.json({
          ok: true,
          data: macroLiveEvidenceFixture("rates-inflation"),
        }),
      ),
    );
  });

  afterEach(cleanup);

  it("keeps material clocks, source identity, refresh, and category navigation reachable", async () => {
    renderWithProviders(<MacroLiveEvidencePage token="test-token" viewId="rates-inflation" />, {
      route: "/macro/rates-inflation?window=90d",
    });

    expect(await screen.findByRole("heading", { level: 1, name: "利率与通胀" })).toBeVisible();
    expect(screen.getByRole("button", { name: "刷新宏观实时数据" })).toBeEnabled();
    expect(screen.getByLabelText("历史窗口")).toBeEnabled();
    expect(screen.getByRole("navigation", { name: "宏观数据分类" })).toBeVisible();
    expect(screen.getByRole("link", { name: "完整研究" })).toHaveAttribute(
      "href",
      "/macro/research",
    );
    expect(screen.getAllByText("fixture").length).toBeGreaterThan(0);
    expect(screen.getAllByText("fred:DGS10").length).toBeGreaterThan(0);
    expect(screen.getByText(/最近成功读取/)).toBeVisible();
  });
});
