import { readFileSync } from "node:fs";
import { join } from "node:path";

import { NewsPage } from "@features/news";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { newsItemFixture, newsRowFixture } from "@tests/fixtures/newsFixture";
import { server } from "@tests/msw/server";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

describe("NewsPage", () => {
  beforeEach(() => {
    server.use(
      http.get(/.*\/api\/news$/, () =>
        HttpResponse.json({
          ok: true,
          data: { items: [newsRowFixture()], next_cursor: null },
        }),
      ),
      http.get(/.*\/api\/news\/items\/news-1$/, () =>
        HttpResponse.json({ ok: true, data: newsItemFixture() }),
      ),
    );
  });

  afterEach(cleanup);

  it("renders a compact fact tape without an inline inspector", async () => {
    renderNews(<NewsPage token="test-token" />);

    expect((await screen.findAllByText("BTC ETF flows expand")).length).toBeGreaterThan(0);
    expect(screen.getByText("processed")).toBeInTheDocument();
    expect(screen.getByText("market_update")).toBeInTheDocument();
    expect(screen.getByText("BTC")).toBeInTheDocument();
    expect(screen.queryByLabelText("news inspector")).not.toBeInTheDocument();
  });

  it("anchors sparse and loading queue content at the top of the scroll surface", () => {
    const newsCss = readFileSync(join(process.cwd(), "src/features/news/news.css"), "utf8");
    const tableWrapRule = cssRuleBody(newsCss, ".news-table-wrap");

    expect(tableWrapRule).toContain("align-content: start");
    expect(tableWrapRule).toContain("grid-auto-rows: max-content");
  });

  it("requests lifecycle and search filters from the fact controls", async () => {
    const requests: Array<Record<string, string | null>> = [];
    server.use(
      http.get(/.*\/api\/news$/, ({ request }) => {
        const params = new URL(request.url).searchParams;
        requests.push({ q: params.get("q"), status: params.get("status") });
        return HttpResponse.json({
          ok: true,
          data: { items: [newsRowFixture()], next_cursor: null },
        });
      }),
    );

    renderNews(<NewsPage token="test-token" />);

    expect((await screen.findAllByText("BTC ETF flows expand")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Accepted" }));
    await waitFor(() =>
      expect(requests.some((request) => request.status === "accepted")).toBe(true),
    );

    fireEvent.change(screen.getByLabelText("Search news"), { target: { value: "eth" } });
    await waitFor(() =>
      expect(requests.some((request) => request.q === "eth" && request.status === "accepted")).toBe(
        true,
      ),
    );
    expect(screen.getByTestId("location")).toHaveTextContent("/news?q=eth");
  });

  it("hydrates the news search input from the route query", async () => {
    renderNews(<NewsPage token="test-token" />, "/news?q=ethereum");

    expect(await screen.findByLabelText("Search news")).toHaveValue("ethereum");
  });

  it("resets pagination to the first page when the news query changes", async () => {
    server.use(
      http.get(/.*\/api\/news$/, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        return HttpResponse.json({
          ok: true,
          data: {
            items: [newsRowFixture()],
            next_cursor: cursor ? null : "1779000000000:row-1",
          },
        });
      }),
    );

    renderNews(<NewsPage token="test-token" />);

    expect((await screen.findAllByText("BTC ETF flows expand")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Next news page" }));
    await waitFor(() => expect(screen.getByText("Page 2 · 1/100")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Search news"), { target: { value: "zec" } });
    await waitFor(() => expect(screen.getByText("Page 1 · 1/100")).toBeInTheDocument());
    expect(screen.getByTestId("location")).toHaveTextContent("/news?q=zec");
  });

  it("routes the compact tape open action to the news item page", async () => {
    renderNews(<NewsPage token="test-token" />);

    await screen.findByText("BTC ETF flows expand");
    fireEvent.click(screen.getByRole("button", { name: "Open news item BTC ETF flows expand" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/news/items/news-1");
  });

  it("renders the canonical source evidence page", async () => {
    renderNews(<NewsPage newsItemId="news-1" token="test-token" />);

    await screen.findByText("Evidence page");
    expect(screen.getByText("Original article")).toBeInTheDocument();
    expect(screen.getByText("OpenNews source content.")).toBeInTheDocument();
    expect(screen.getByText("Story membership")).toBeInTheDocument();
    expect(screen.getByText("Content classification")).toBeInTheDocument();
    expect(screen.getByText("Market scope")).toBeInTheDocument();
    expect(screen.getByText("Token identity lanes")).toBeInTheDocument();
    expect(screen.getByText("Fact lanes")).toBeInTheDocument();
    expect(screen.getByText("Observation set")).toBeInTheDocument();
    expect(screen.getByText("Source metadata")).toBeInTheDocument();
    expect(screen.getByText("BTC · Bitcoin")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /original/i })).toHaveAttribute(
      "href",
      "https://example.test/news-1",
    );
  });
});

function renderNews(children: ReactNode, route = "/news") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[route]}>
      <QueryClientProvider client={queryClient}>
        {children}
        <LocationProbe />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{`${location.pathname}${location.search}`}</span>;
}

function cssRuleBody(css: string, selector: string): string {
  const match = new RegExp(`${selector.replace(".", "\\.")}\\s*\\{(?<body>[^}]*)\\}`).exec(css);
  return match?.groups?.body ?? "";
}
