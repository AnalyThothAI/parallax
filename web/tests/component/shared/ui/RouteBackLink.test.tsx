import { RouteBackLink } from "@shared/ui/RouteBackLink";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

describe("RouteBackLink", () => {
  it("renders an accessible return link", () => {
    renderWithProviders(<RouteBackLink to="/" label="返回" ariaLabel="返回 Token Radar" />, {
      route: "/token/Asset/x",
    });

    const link = screen.getByRole("link", { name: "返回 Token Radar" });
    expect(link).toHaveAttribute("href", "/");
    expect(link).toHaveTextContent("返回");
  });

  it("navigates through the active router instead of reloading the document", () => {
    const { container } = renderWithProviders(
      <Routes>
        <Route path="/" element={<h1>Token Radar</h1>} />
        <Route
          path="/token/:targetType/:targetId"
          element={<RouteBackLink to="/" label="返回" ariaLabel="返回 Token Radar" />}
        />
      </Routes>,
      {
        route: "/token/Asset/x",
      },
    );

    fireEvent.click(within(container).getByRole("link", { name: "返回 Token Radar" }));

    expect(within(container).getByRole("heading", { name: "Token Radar" })).toBeInTheDocument();
  });

  it("does not require a router provider", () => {
    const { container } = render(
      <RouteBackLink to="/" label="返回" ariaLabel="返回 Token Radar" />,
    );

    expect(within(container).getByRole("link", { name: "返回 Token Radar" })).toHaveAttribute(
      "href",
      "/",
    );
  });
});
