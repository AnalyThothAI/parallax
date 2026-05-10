import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { tokenRadarRowToTokenItem } from "./lib/tokenRadar";
import type {
  ApiResponse,
  AssetFlowData,
  AssetFlowRow,
  BootstrapData,
  LivePayload,
  NotificationItem,
  NotificationLivePayload,
  SignalPulseData,
  StatusData,
  TokenFlowItem,
  TokenPostsData,
  TokenSocialTimelineData,
  WindowKey
} from "./api/types";
import { ApiError, getApi, getBootstrap, postApi } from "./api/client";
import { useTraderStore } from "./store/useTraderStore";

const socketMock: { status: string; events: LivePayload[]; notifications: NotificationLivePayload[]; lastMessageAt: number | null } = {
  status: "connected",
  events: [],
  notifications: [],
  lastMessageAt: 1_777_770_000_000
};

vi.mock("./api/client", async () => {
  const actual = await vi.importActual<typeof import("./api/client")>("./api/client");
  return {
    ...actual,
    getApi: vi.fn(),
    getBootstrap: vi.fn(),
    postApi: vi.fn()
  };
});

vi.mock("./api/useIntelSocket", () => ({
  useIntelSocket: () => socketMock
}));

const mockedGetApi = vi.mocked(getApi);
const mockedGetBootstrap = vi.mocked(getBootstrap);
const mockedPostApi = vi.mocked(postApi);

const statusData: StatusData = {
  ok: true,
  reasons: [],
  handles: ["toly", "traderpow"],
  store: "postgresql",
  collector: {
    started_at_ms: 1_777_770_000_000,
    frames_received: 88,
    twitter_events: 44,
    matched_twitter_events: 7,
    events_published: 7,
    duplicate_twitter_events: 2,
    duplicate_matched_twitter_events: 0,
    parse_errors: 0,
    last_frame_at_ms: 1_777_770_100_000,
    last_event_at_ms: 1_777_770_100_000,
    last_matched_event_at_ms: 1_777_770_090_000
  },
  enrichment: {
    llm_configured: true,
    worker_running: true,
    job_counts: { pending: 1, running: 0, failed: 0, dead: 0, done: 8 }
  },
  token_radar_projection: {
    worker_running: true,
    last_started_at_ms: 1_777_770_100_000,
    last_run_at_ms: 1_777_770_101_000,
    last_result: { rows_written: 2, source_rows: 2 }
  },
  asset_market_sync: {
    okx_cex_sync_enabled: true,
    worker_running: true,
    last_started_at_ms: 1_777_770_100_000,
    last_run_at_ms: 1_777_770_101_000,
    last_result: { ready: 1 },
    providers: {
      cex: { running: false },
      dex: { running: false }
    }
  },
  notifications: {
    enabled: true,
    worker_running: true,
    summary: {
      subscriber_key: "local",
      unread_count: 0,
      high_unread_count: 0,
      critical_unread_count: 0,
      highest_unread_severity: null,
      account_unread_counts: {}
    }
  }
};

describe("App Token Radar social heat cockpit", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mockedGetApi.mockReset();
    mockedGetBootstrap.mockReset();
    mockedPostApi.mockReset();
    mockedPostApi.mockResolvedValue(ok({ notification_id: "notification-1", updated: true }));
    socketMock.status = "connected";
    socketMock.events = [liveUpegEvent()];
    socketMock.notifications = [];
    socketMock.lastMessageAt = 1_777_770_000_000;
    useTraderStore.setState({
      token: "",
      window: "1h",
      scope: "all",
      handles: "",
      search: "$PEPE",
      submittedSearch: "$PEPE",
      radarSortMode: "opportunity",
      detailTab: "timeline",
      detailWindow: "1h",
      detailMode: "compact",
      selectedBucketStartMs: null,
      selectedEventId: null,
      postRange: "current_window",
      postSortMode: "recent",
      hideDuplicateClusters: false,
      watchedPostsOnly: false
    });
    mockedGetBootstrap.mockResolvedValue(ok<BootstrapData>({ ws_token: "secret", handles: ["toly", "traderpow"], replay_limit: 100 }));
    mockApi();
  });

  it("renders radar rows with mock-aligned semantic fields and selected state", async () => {
    const { container } = renderWithQuery(<App />);

    expect(await screen.findByText("Token")).toBeInTheDocument();
    expect(screen.getAllByText("Heat").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Quality").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Propagation").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Market").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Timing").length).toBeGreaterThan(0);
    expect(screen.getByText("Decision")).toBeInTheDocument();
    expect(screen.queryByText("EV")).not.toBeInTheDocument();
    expect(screen.queryByText("Evidence")).not.toBeInTheDocument();
    const row = await screen.findByRole("button", { name: "select token $UPEG" });
    expect(row).toHaveClass("selected");
    expect(row).not.toHaveClass("is-selected");
    expect(within(row).getByText("86 · 4 +4")).toBeInTheDocument();
    expect(within(row).getByText("4 posts · new burst · share 0%")).toBeInTheDocument();
    expect(within(row).getByText("78 · resolved asset")).toBeInTheDocument();
    expect(within(row).getByText("dup 0% · info 3")).toBeInTheDocument();
    expect(within(row).getByText("expansion · 3 author")).toBeInTheDocument();
    expect(within(row).getByText("top 33% · repro -")).toBeInTheDocument();
    expect(within(row).getByText("- missing")).toBeInTheDocument();
    expect(within(row).getByText("market pending")).toBeInTheDocument();
    expect(within(row).getByText("market observation pending")).toBeInTheDocument();
    expect(row.querySelector(".barline")).toBeInTheDocument();
    expect(screen.getAllByText("driver").length).toBeGreaterThan(0);
    expect(container.querySelector(".decision-controls")).not.toBeInTheDocument();
    expect(await screen.findByText("实时信号 Tape")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("$UPEG").length).toBeGreaterThan(0));
  });

  it("keeps search results in the evidence drawer instead of a bottom panel", async () => {
    mockApi({ searchResult: true });
    const { container } = renderWithQuery(<App />);

    const input = await screen.findByPlaceholderText("搜索 CA / $TOKEN / @handle / 文本");
    fireEvent.change(input, { target: { value: "PEPE ignition" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    await waitFor(() => expect(screen.getByText("selected evidence")).toBeInTheDocument());
    expect(screen.queryByText("检索结果")).not.toBeInTheDocument();
    const drawer = container.querySelector(".evidence-drawer") as HTMLElement;
    await waitFor(() => expect(within(drawer).getByText("PEPE ignition from search")).toBeInTheDocument());
    expect(within(drawer).getByText("@searcher")).toBeInTheDocument();
    expect(screen.queryByText("Select Token")).not.toBeInTheDocument();
  });

  it("selects the current radar token instead of running evidence search for token-like input", async () => {
    const { container } = renderWithQuery(<App />);

    const input = await screen.findByPlaceholderText("搜索 CA / $TOKEN / @handle / 文本");
    await screen.findByRole("button", { name: "select token $UPEG" });
    mockedGetApi.mockClear();

    fireEvent.change(input, { target: { value: "$UPEG" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    await waitFor(() => {
      const drawer = container.querySelector(".detail-drawer") as HTMLElement;
      expect(drawer.querySelector(".drawer-title .eyebrow")).toHaveTextContent("selected token");
      expect(drawer.querySelector(".drawer-title h2")).toHaveTextContent("$UPEG");
    });
    expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/search")).toBe(false);
  });

  it("treats bare uppercase as token lookup only when the current radar has a unique match", async () => {
    const { container } = renderWithQuery(<App />);

    const input = await screen.findByPlaceholderText("搜索 CA / $TOKEN / @handle / 文本");
    await screen.findByRole("button", { name: "select token $UPEG" });
    mockedGetApi.mockClear();

    fireEvent.change(input, { target: { value: "UPEG" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    await waitFor(() => {
      const drawer = container.querySelector(".detail-drawer") as HTMLElement;
      expect(drawer.querySelector(".drawer-title h2")).toHaveTextContent("$UPEG");
    });
    const mobileNav = screen.getByRole("navigation", { name: "mobile cockpit tasks" });
    expect(within(mobileNav).getByRole("button", { name: "Detail" })).toHaveAttribute("aria-current", "page");
    expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/search")).toBe(false);
  });

  it("opens an evidence drawer from a non-token live tape event", async () => {
    socketMock.events = [plainLiveEvent()];
    renderWithQuery(<App />);

    const liveEventTitle = await screen.findByText("@anon -> macro headline without token");
    fireEvent.click(liveEventTitle.closest("button") as HTMLButtonElement);

    await waitFor(() => expect(screen.getByText("selected evidence")).toBeInTheDocument());
    expect(screen.getAllByText("macro headline without token").length).toBeGreaterThan(0);
  });

  it("exposes a venue link for resolved radar tokens", async () => {
    renderWithQuery(<App />);

    const link = await screen.findByRole("link", { name: "Open $UPEG on GMGN" });
    expect(link).toHaveAttribute(
      "href",
      "https://gmgn.ai/eth/token/0x6982508145454Ce325dDbE47a25d4ec3d2311933"
    );
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("keeps each Token Radar metric in stable responsive slots", async () => {
    renderWithQuery(<App />);

    const rowButton = await screen.findByRole("button", { name: "select token $UPEG" });
    const row = rowButton.closest(".radar-row") as HTMLElement;
    expect(rowButton.querySelector('[data-radar-metric="heat"]')).toHaveTextContent("86 · 4 +4");
    expect(rowButton.querySelector('[data-radar-metric="quality"]')).toHaveTextContent("78 · resolved asset");
    expect(rowButton.querySelector('[data-radar-metric="propagation"]')).toHaveTextContent("expansion · 3 author");
    expect(rowButton.querySelector('[data-radar-metric="market"]')).toHaveTextContent("- missing");
    expect(rowButton.querySelector('[data-radar-metric="timing"]')).toHaveTextContent("market pending");
    expect(row.querySelector('[data-radar-action="venue"]')).toBeInTheDocument();
  });

  it("renders valid token radar rows regardless of backend projection version metadata", async () => {
    mockApi({ projectionVersion: "token-radar-next-internal-version" });

    renderWithQuery(<App />);

    expect(await screen.findByRole("button", { name: "select token $UPEG" })).toBeInTheDocument();
    expect(screen.getByText("TOKEN RADAR")).toBeInTheDocument();
  });

  it("renders fresh CEX token-radar market as tradeable instead of pending", async () => {
    mockApi({
      assetFlowRows: [
        assetFlowRow({
          symbol: "BTC",
          assetType: "cex_asset",
          assetId: "asset:cex:BTC",
          primaryVenue: {
            venue_id: "venue:cex:okx:SPOT:BTC-USDT",
            venue_type: "cex",
            exchange: "okx",
            chain: null,
            address: null,
            inst_id: "BTC-USDT",
            base_symbol: "BTC",
            quote_symbol: "USDT",
            inst_type: "SPOT"
          },
          price: {
            market_status: "fresh",
            market_observation_status: "ready",
            price_change_status: "ready",
            provider: "okx_cex",
            price_usd: 69_000,
            market_cap_usd: null,
            liquidity_usd: null,
            volume_24h_usd: 123_000_000,
            open_interest_usd: null,
            holders: null,
            snapshot_age_ms: 30_000,
            snapshot_observed_at_ms: 1_777_746_270_000,
            price_change_5m_pct: null,
            price_change_1h_pct: null,
            price_change_24h_pct: null
          }
        })
      ]
    });

    renderWithQuery(<App />);

    const rowButton = await screen.findByRole("button", { name: "select token $BTC" });
    expect(within(rowButton).getByText("OKX · BTC-USDT")).toBeInTheDocument();
    expect(rowButton.querySelector('[data-radar-metric="market"]')).toHaveTextContent("$69K");
    expect(rowButton.querySelector('[data-radar-metric="market"]')).toHaveTextContent("fresh");
    expect(rowButton.querySelector('[data-radar-metric="timing"]')).toHaveTextContent("neutral");
    expect(rowButton.querySelector('[data-radar-metric="timing"]')).toHaveTextContent("fresh");
    expect(rowButton.querySelector('[data-radar-metric="timing"]')).not.toHaveTextContent("历史不足");
    expect(rowButton.querySelector('[data-radar-metric="timing"]')).not.toHaveTextContent("market pending");
    expect(await screen.findByRole("link", { name: "Open $BTC on OKX" })).toHaveAttribute(
      "href",
      "https://www.okx.com/trade-spot/btc-usdt"
    );
  });

  it("renders token prices with price precision instead of compact integer rounding", async () => {
    mockApi({
      assetFlowRows: [
        assetFlowRow({
          symbol: "TON",
          assetType: "cex_asset",
          assetId: "asset:cex:TON",
          primaryVenue: {
            venue_id: "venue:cex:okx:SPOT:TON-USDT",
            venue_type: "cex",
            exchange: "okx",
            chain: null,
            address: null,
            inst_id: "TON-USDT",
            base_symbol: "TON",
            quote_symbol: "USDT",
            inst_type: "SPOT"
          },
          price: {
            market_status: "fresh",
            market_observation_status: "ready",
            price_change_status: "insufficient_history",
            provider: "okx_cex",
            price_usd: 2.753,
            market_cap_usd: null,
            liquidity_usd: null,
            volume_24h_usd: 12_000_000,
            open_interest_usd: null,
            holders: null,
            snapshot_age_ms: 30_000,
            snapshot_observed_at_ms: 1_777_746_270_000,
            price_change_since_social_pct: null,
            price_change_before_social_pct: null
          }
        }),
        assetFlowRow({
          symbol: "",
          assetId: "asset:dex:eth:0x1111111111111111111111111111111111111111",
          address: "0x1111111111111111111111111111111111111111",
          price: {
            market_status: "fresh",
            market_observation_status: "ready",
            price_change_status: "insufficient_history",
            provider: "okx_dex_price",
            price_usd: 0.00001360704303591779,
            market_cap_usd: null,
            liquidity_usd: null,
            volume_24h_usd: null,
            open_interest_usd: null,
            holders: null,
            snapshot_age_ms: 30_000,
            snapshot_observed_at_ms: 1_777_746_270_000,
            price_change_since_social_pct: null,
            price_change_before_social_pct: null
          }
        })
      ]
    });

    renderWithQuery(<App />);

    const tonRow = await screen.findByRole("button", { name: "select token $TON" });
    expect(tonRow.querySelector('[data-radar-metric="market"]')).toHaveTextContent("$2.75");
    expect(tonRow.querySelector('[data-radar-metric="market"]')).not.toHaveTextContent("$3");

    const microRow = await screen.findByRole("button", { name: /select token 0x111111/ });
    expect(microRow.querySelector('[data-radar-metric="market"]')).toHaveTextContent("$0.00001361");
    expect(microRow.querySelector('[data-radar-metric="market"]')).not.toHaveTextContent("$0 fresh");
  });

  it("renders token-radar timing changes from backend market baselines", async () => {
    mockApi({
      assetFlowRows: [
        assetFlowRow({
          symbol: "USDUC",
          price: {
            market_status: "fresh",
            market_observation_status: "ready",
            provider: "okx_dex",
            price_usd: 0.02,
            market_cap_usd: 20_000_000,
            liquidity_usd: 1_000_000,
            volume_24h_usd: null,
            open_interest_usd: null,
            holders: 16_000,
            snapshot_age_ms: 30_000,
            snapshot_observed_at_ms: 1_777_746_270_000,
            price_change_5m_pct: 0.1,
            price_change_1h_pct: 0.2,
            price_change_24h_pct: null,
            price_at_social_start: 0.018,
            price_change_since_social_pct: 0.111111,
            price_before_social_start: 0.017,
            price_change_before_social_pct: 0.058823,
            price_change_status: "ready"
          }
        })
      ]
    });

    renderWithQuery(<App />);

    const rowButton = await screen.findByRole("button", { name: "select token $USDUC" });
    expect(rowButton.querySelector('[data-radar-metric="timing"]')).toHaveTextContent("+11% since social");
  });

  it("uses Signal Lab as the trader-facing product label", async () => {
    renderWithQuery(<App />);

    expect(await screen.findAllByText("Signal Lab")).not.toHaveLength(0);
    expect(screen.queryByText("Harness")).not.toBeInTheDocument();
    expect(screen.queryByText("harness_snapshot")).not.toBeInTheDocument();
  });

  it("keeps Signal Lab Pulse visible in the live cockpit and opens the shared inspector", async () => {
    const { container } = renderWithQuery(<App />);

    const pulseTitle = await screen.findByText("Signal Lab Pulse");
    const pulse = pulseTitle.closest("section") as HTMLElement;
    expect(await within(pulse).findByText(/ignition · A/)).toBeInTheDocument();
    expect(within(pulse).getByText("CZ 推动 BNB build 叙事，候选处于点火阶段。")).toBeInTheDocument();
    expect(within(pulse).queryByText("extractor configured")).not.toBeInTheDocument();
    expect(within(pulse).queryByLabelText("signal lab pulse stages")).not.toBeInTheDocument();
    expect(screen.getByText("Token")).toBeInTheDocument();

    fireEvent.click(await within(pulse).findByRole("button", { name: "open Signal Pulse BNB" }));

    await waitFor(() => expect(screen.getByText("selected Signal Pulse")).toBeInTheDocument());
    expect(screen.getByText("Token")).toBeInTheDocument();
    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    expect(within(drawer).getByText("Why now")).toBeInTheDocument();
    expect(within(drawer).getByText("bull_case_zh")).toBeInTheDocument();
  });

  it("routes Signal Pulse notifications into Signal Lab instead of token search", async () => {
    mockApi({
      notifications: [signalPulseNotification()],
      signalPulseWorkbench: signalPulseData()
    });

    renderWithQuery(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "notifications" }));
    fireEvent.click(await screen.findByRole("button", { name: "open $BNB trade candidate" }));

    expect(await screen.findByText("Review Signal Pulse agent candidates by status, source, and query.")).toBeInTheDocument();
    expect(mockedPostApi).toHaveBeenCalledWith("/api/notifications/notification-1/read", { token: "secret" });
  });

  it("queries the compact Signal Lab Pulse as a fresh live feed", async () => {
    renderWithQuery(<App />);

    await screen.findByText("Signal Lab Pulse");

    await waitFor(() => {
      expect(
        mockedGetApi.mock.calls.some(
          ([path, options]) =>
            path === "/api/signal-lab/pulse" &&
            options?.params?.window === "1h" &&
            options?.params?.scope === "all" &&
            options?.params?.limit === 80 &&
            options?.params?.sort === "recent"
        )
      ).toBe(true);
    });
  });

  it("switches the left rail into the Signal Lab workbench without losing the selected pulse item", async () => {
    const { container } = renderWithQuery(<App />);

    const rail = container.querySelector(".side-rail") as HTMLElement;
    fireEvent.click(await within(rail).findByRole("button", { name: /Signal Lab/ }));

    const workbench = await screen.findByText("Review Signal Pulse agent candidates by status, source, and query.");
    expect(workbench).toBeInTheDocument();
    expect(screen.getByText("Signal Pulse")).toBeInTheDocument();
    const views = within(container.querySelector(".side-rail") as HTMLElement).getByText("views").closest("section") as HTMLElement;
    expect(within(views).queryByText("Tokens")).not.toBeInTheDocument();
    expect(within(views).queryByText("Accounts")).not.toBeInTheDocument();
    expect(within(views).queryByText("Jobs/Ops")).not.toBeInTheDocument();
    expect(screen.getByText("Trade candidate")).toBeInTheDocument();
    expect(screen.getByText("Token watch")).toBeInTheDocument();
    expect(screen.getByText("Theme watch")).toBeInTheDocument();
    expect(screen.getByText("Rejected high info")).toBeInTheDocument();
    expect(screen.queryByText("blocked_low_information")).not.toBeInTheDocument();
    expect(screen.queryByText(["Direct", "token"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(["Topic", "heat"].join(" "))).not.toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: "open Signal Pulse BNB" }));
    expect(await screen.findByText("selected Signal Pulse")).toBeInTheDocument();
    expect(container.querySelector(".signal-lab-workbench")).toBeInTheDocument();
  });

  it("marks the desktop watchlist as the left rail fill section", async () => {
    const { container } = renderWithQuery(<App />);

    await screen.findByText("Token");
    const rail = container.querySelector(".desktop-side-rail") as HTMLElement;
    const watchlistSection = within(rail).getByText("watchlist").closest("section") as HTMLElement;

    expect(watchlistSection).toHaveClass("watchlist-section");
    expect(watchlistSection.querySelector(".watchlist")).toBeInTheDocument();
    expect(rail.querySelector(".rail-footer")?.previousElementSibling).toBe(watchlistSection);
  });

  it("uses watchlist clicks as a Signal Lab account lens", async () => {
    const { container } = renderWithQuery(<App />);

    await screen.findByText("Token");
    const rail = container.querySelector(".desktop-side-rail") as HTMLElement;
    const traderpowLink = await within(rail).findByRole("link", { name: /@traderpow/ });
    expect(traderpowLink).toHaveAttribute("href", "/signal-lab?handle=traderpow");

    fireEvent.click(traderpowLink);

    expect(await screen.findByRole("heading", { name: "Signal Lab" })).toBeInTheDocument();
    expect(screen.getByLabelText("Signal Lab source filter")).toHaveValue("traderpow");
    expect(screen.getByLabelText("Signal Lab identity filter")).toHaveValue("");
    expect(traderpowLink).toHaveClass("active");
    await waitFor(() => {
      expect(
        mockedGetApi.mock.calls.some(
          ([path, options]) =>
            path === "/api/signal-lab/pulse" &&
            options?.params?.window === "1h" &&
            options?.params?.scope === "all" &&
            options?.params?.handle === "traderpow" &&
            options?.params?.q === undefined
        )
      ).toBe(true);
    });
  });

  it("shows watched account events when an account lens has no Signal Pulse candidates", async () => {
    mockApi({
      recentItemsByHandle: { traderpow: [watchedAccountLensEvent("traderpow")] },
      signalPulseByHandle: { traderpow: emptySignalPulseData("@traderpow") }
    });
    const { container } = renderWithQuery(<App />);

    await screen.findByText("Token");
    const rail = container.querySelector(".desktop-side-rail") as HTMLElement;
    const traderpowLink = await within(rail).findByRole("link", { name: /@traderpow/ });

    fireEvent.click(traderpowLink);

    expect(await screen.findByText("Watched account events")).toBeInTheDocument();
    expect(screen.getByText("Account lens raw post without pulse")).toBeInTheDocument();
    expect(screen.queryByText("No matching Signal Pulse items")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(
        mockedGetApi.mock.calls.some(
          ([path, options]) =>
            path === "/api/recent" &&
            options?.params?.scope === "all" &&
            options?.params?.handles === "traderpow" &&
            options?.params?.limit === 80
        )
      ).toBe(true);
    });

    fireEvent.click(screen.getByRole("button", { name: "open watched post Account lens raw post without pulse" }));

    await waitFor(() => expect(screen.getByText("selected evidence")).toBeInTheDocument());
    const drawer = container.querySelector(".evidence-drawer") as HTMLElement;
    expect(within(drawer).getByText("@traderpow")).toBeInTheDocument();
    expect(within(drawer).getByText("Account lens raw post without pulse")).toBeInTheDocument();
  });

  it("renders the selected token drawer with the mock structure and no extra override controls", async () => {
    const { container } = renderWithQuery(<App />);

    await screen.findByRole("button", { name: "select token $UPEG" });

    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    expect(drawer).toBeInTheDocument();
    expect(drawer.querySelector(".detail-focus")).not.toBeInTheDocument();
    expect(drawer.querySelector(".drawer-title .eyebrow")).toHaveTextContent("selected token");
    expect(drawer.querySelector(".drawer-title h2")).toHaveTextContent("$UPEG");
    expect(drawer.querySelector(".opportunity-score")).toHaveTextContent("79");
    expect(within(drawer).getByText("86 / rising")).toBeInTheDocument();
    expect(within(drawer).getByText("78 / resolved asset")).toBeInTheDocument();
    expect(within(drawer).getByText("3 authors")).toBeInTheDocument();
    expect(within(drawer).getByText("market pending")).toBeInTheDocument();
    expect(within(drawer).getByText("driver")).toBeInTheDocument();
    expect(within(drawer).getByText("public_stream_coverage")).toBeInTheDocument();
    expect(drawer.querySelector(".tabs")).toBeInTheDocument();
    expect(drawer.querySelector(".focus-tabs")).not.toBeInTheDocument();
    expect(drawer.querySelector(".decision-controls")).not.toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Timeline" })).toHaveClass("active");
  });

  it("opens Timeline by default, requests timeline/posts, and keeps token Lab as a pointer into Signal Lab", async () => {
    const { container } = renderWithQuery(<App />);

    const tokenButton = await screen.findByRole("button", { name: "select token $UPEG" });
    fireEvent.click(tokenButton);

    expect(await screen.findByRole("button", { name: "Timeline" })).toHaveClass("active");
    await waitFor(() => {
      expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/target-social-timeline")).toBe(true);
      expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/target-posts")).toBe(true);
    });

    fireEvent.click(screen.getByRole("button", { name: "Posts" }));
    await waitFor(() => expect(screen.getAllByText("$UPEG watched account evidence").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("button", { name: "Score" }));
    await waitFor(() => expect(screen.getAllByText("Opportunity").length).toBeGreaterThan(0));
    expect(screen.getAllByText("Tradeability").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Accounts" }));
    await waitFor(() => expect(screen.getAllByText("样本不足").length).toBeGreaterThan(0));
    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    fireEvent.click(within(drawer).getByRole("button", { name: "Lab" }));
    await waitFor(() =>
      expect(
        within(drawer).getByText("Open Signal Lab to inspect watched-account token, topic, ecosystem, structure, and risk attention.")
      ).toBeInTheDocument()
    );
    expect(within(drawer).queryByText("Active Snapshots")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("Credit Rows")).not.toBeInTheDocument();
  });

  it("maps radar evidence count from source event ids instead of empty intent evidence", () => {
    const row = {
      ...assetFlowRow(),
      intent: { intent_id: "intent-upeg", display_symbol: "UPEG", display_name: null, evidence: [] },
      source_event_ids: ["event-1", "event-2", "event-3", "event-4"]
    };

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.evidence_total_count).toBe(4);
  });

  it("uses the resolved target symbol for identity when a mention symbol disagrees", () => {
    const row = {
      ...assetFlowRow({ symbol: "SLOP" }),
      intent: { intent_id: "intent-shit-mention", display_symbol: "SHIT", display_name: null, evidence: [] }
    };

    const item = tokenRadarRowToTokenItem(row, "1h", "all");

    expect(item.identity.symbol).toBe("SLOP");
    expect(item.identity.target_id).toBe(row.target?.target_id);
    expect(item.posts_query.target_id).toBe(row.target?.target_id);
  });

  it("rejects token radar rows when the backend omits score versions", () => {
    const row = {
      ...assetFlowRow(),
      score: {
        heat: scoreBlock({ score: 11, reasons: [], risks: [] }),
        quality: scoreBlock({ score: 12, reasons: [], risks: [] }),
        propagation: scoreBlock({ score: 13, reasons: [], risks: [] }),
        tradeability: scoreBlock({ score: 14, reasons: [], risks: [] }),
        timing: scoreBlock({ score: 15, reasons: [], risks: [] }),
        opportunity: scoreBlock({ score: 16, reasons: [], risks: [] })
      }
    } as unknown as AssetFlowRow;

    expect(() => tokenRadarRowToTokenItem(row, "1h", "all")).toThrow(/score\.heat\.score_version/);
  });

  it("rejects token radar rows when baseline fields are missing", () => {
    const row = assetFlowRow();
    const attention = { ...(row.attention as Partial<AssetFlowRow["attention"]>) };
    delete attention.baseline_status;

    expect(() => tokenRadarRowToTokenItem({ ...row, attention } as unknown as AssetFlowRow, "1h", "all")).toThrow(/attention\.baseline_status/);
  });

  it("drives selected token detail by production windows instead of manual timeline buckets", async () => {
    const { container } = renderWithQuery(<App />);

    await screen.findByRole("button", { name: "select token $UPEG" });
    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    const detailWindow = await within(drawer).findByLabelText("selected token detail window") as HTMLSelectElement;

    expect(detailWindow).toHaveValue("1h");
    expect(drawer.querySelector(".detail-window-control button")).not.toBeInTheDocument();
    expect(container.querySelector(".desktop-side-rail .window-stack")).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "30 秒" })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "1 分钟" })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "5 分钟" })).not.toBeInTheDocument();
    expect(await within(drawer).findByText("auto bucket 5m")).toBeInTheDocument();
    expect(within(drawer).getByLabelText("social heat timeline")).toBeInTheDocument();
    expect(within(drawer).queryByText("$UPEG watched account evidence")).not.toBeInTheDocument();

    mockedGetApi.mockClear();
    fireEvent.change(detailWindow, { target: { value: "4h" } });

    await waitFor(() => {
      const timelineCall = mockedGetApi.mock.calls.find(([path]) => path === "/api/target-social-timeline");
      expect(timelineCall?.[1]?.params).toMatchObject({ window: "4h" });
      expect(timelineCall?.[1]?.params).not.toHaveProperty("bucket");
    });
  });

  it("opens replay focus mode by clicking a timeline bucket", async () => {
    const { container } = renderWithQuery(<App />);

    await screen.findByRole("button", { name: "select token $UPEG" });
    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    const bucket = await within(drawer).findByRole("button", { name: /open replay bucket .*2 posts/i });

    fireEvent.click(bucket);

    await waitFor(() => expect(within(drawer).getByText("Replay Focus")).toBeInTheDocument());
    expect(within(drawer).getByText("selected bucket · 2 posts · 1 new author")).toBeInTheDocument();
    expect(within(drawer).getAllByText("$UPEG watched account evidence").length).toBeGreaterThan(0);
    expect(within(drawer).getByRole("button", { name: "Back to timeline" })).toBeInTheDocument();
  });

  it("keeps Posts as the evidence surface with explicit range controls", async () => {
    const { container } = renderWithQuery(<App />);

    await screen.findByRole("button", { name: "select token $UPEG" });
    fireEvent.click(screen.getByRole("button", { name: "Posts" }));
    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    const postRange = await within(drawer).findByLabelText("token post range");

    expect(within(postRange).getByRole("button", { name: "window" })).toHaveClass("active");
    expect(within(postRange).getByRole("button", { name: "ignition" })).toBeInTheDocument();
    expect(within(postRange).getByRole("button", { name: "history" })).toBeInTheDocument();
    expect(await within(drawer).findByText("3 total · 3 loaded · score window 1h")).toBeInTheDocument();

    mockedGetApi.mockClear();
    fireEvent.click(within(postRange).getByRole("button", { name: "history" }));

    await waitFor(() => {
      const postsCall = mockedGetApi.mock.calls.find(([path]) => path === "/api/target-posts");
      expect(postsCall?.[1]?.params).toMatchObject({ range: "all_history" });
    });
    expect(await within(drawer).findByText("history does not all participate in current score")).toBeInTheDocument();
  });

  it("requests catalyst post sorting from the server", async () => {
    const { container } = renderWithQuery(<App />);

    await screen.findByRole("button", { name: "select token $UPEG" });
    fireEvent.click(screen.getByRole("button", { name: "Posts" }));
    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    const sortControl = await within(drawer).findByLabelText("token post sort");

    mockedGetApi.mockClear();
    fireEvent.click(within(sortControl).getByRole("button", { name: "catalyst" }));

    await waitFor(() => {
      const postsCall = mockedGetApi.mock.calls.find(([path]) => path === "/api/target-posts");
      expect(postsCall?.[1]?.params).toMatchObject({ sort: "catalyst", cursor: undefined });
    });
  });

  it("removes narrative product surface and exposes signal lab entry points", async () => {
    renderWithQuery(<App />);

    await screen.findByText("Token");
    expect(screen.queryByText("Narratives")).not.toBeInTheDocument();
    expect(screen.getAllByText("Signal Lab").length).toBeGreaterThan(0);
  });

  it("uses the Signal Pulse read model as the only Signal Lab product source in the UI", async () => {
    renderWithQuery(<App />);

    await screen.findByText("Signal Lab Pulse");

    await waitFor(() => expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/signal-lab/pulse")).toBe(true));
    expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/signal-lab/chains")).toBe(false);
    expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/social-events")).toBe(false);
    expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/attention-seeds")).toBe(false);
    expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/harness-snapshots")).toBe(false);
    expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/harness-outcomes")).toBe(false);
    expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/harness-credits")).toBe(false);
  });

  it("keeps settlement horizons out of the trader-facing Signal Lab and global token radar rail", async () => {
    renderWithQuery(<App />);

    await screen.findByText("Token");

    expect(screen.queryByRole("heading", { name: "horizon" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("settlement horizon")).not.toBeInTheDocument();

    await waitFor(() => {
      const tokenFlowCall = mockedGetApi.mock.calls.find(([path]) => path === "/api/token-radar");
      expect(tokenFlowCall?.[1]?.params).toMatchObject({ window: "1h", limit: 48, scope: "all" });
      expect(tokenFlowCall?.[1]?.params).not.toHaveProperty("horizon");
    });
  });

  it("routes Signal Lab toolbar filters into the Signal Pulse read model", async () => {
    const { container } = renderWithQuery(<App />);

    const rail = container.querySelector(".side-rail") as HTMLElement;
    fireEvent.click(await within(rail).findByRole("button", { name: /Signal Lab/ }));

    fireEvent.click(await screen.findByRole("button", { name: /Token watch/ }));
    fireEvent.change(screen.getByLabelText("Signal Lab source filter"), { target: { value: "@cz_binance" } });
    fireEvent.change(screen.getByLabelText("Signal Lab identity filter"), { target: { value: "BNB" } });

    await waitFor(() => {
      expect(
        mockedGetApi.mock.calls.some(
          ([path, options]) =>
            path === "/api/signal-lab/pulse" &&
            options?.params?.window === "1h" &&
            options?.params?.scope === "all" &&
            options?.params?.status === "token_watch" &&
            !("kind" in (options?.params ?? {})) &&
            options?.params?.handle === "@cz_binance" &&
            options?.params?.q === "BNB"
        )
      ).toBe(true);
    });
  });

  it("uses the Signal Lab cursor without duplicating aggregate summary or overlapping rows", async () => {
    const firstPage = {
      ...signalPulseData(),
      summary: {
        ...signalPulseData().summary,
        trade_candidate: 2
      }
    };
    const secondItem = {
      ...firstPage.items[0],
      candidate_id: "pulse-sol-product",
      subject_key: "token:SOL",
      symbol: "SOL",
      summary_zh: "SOL pulse loaded from cursor.",
      why_now_zh: "SOL pulse loaded from cursor."
    };
    mockApi({
      signalPulsePages: {
        "": { ...firstPage, has_more: true, next_cursor: "80" },
        "80": {
          ...firstPage,
          items: [firstPage.items[0], secondItem],
          returned_count: 2,
          has_more: false,
          next_cursor: null
        }
      }
    });
    const { container } = renderWithQuery(<App />);

    const rail = container.querySelector(".side-rail") as HTMLElement;
    fireEvent.click(await within(rail).findByRole("button", { name: /Signal Lab/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Load more" }));

    await waitFor(() => {
      expect(
        mockedGetApi.mock.calls.some(
          ([path, options]) => path === "/api/signal-lab/pulse" && options?.params?.cursor === "80"
        )
      ).toBe(true);
    });
    expect(await screen.findByText("SOL pulse loaded from cursor.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "open Signal Pulse BNB" })).toHaveLength(1);
    const statusGrid = screen.getByLabelText("Signal Pulse statuses");
    const tradeStatus = within(statusGrid).getByRole("button", { name: /Trade candidate/ });
    expect(within(tradeStatus).getByText("2")).toBeInTheDocument();
  });

  it("keeps live compact pulse selection independent from workbench status filters", async () => {
    const emptyWorkbench = {
      ...signalPulseData(),
      items: [],
      returned_count: 0,
      summary: {
        trade_candidate: 0,
        token_watch: 0,
        theme_watch: 0,
        risk_rejected_high_info: 0,
        blocked_low_information: 0
      }
    };
    mockApi({ signalPulseCompact: signalPulseData(), signalPulseWorkbench: emptyWorkbench });
    const { container } = renderWithQuery(<App />);

    const pulse = (await screen.findByText("Signal Lab Pulse")).closest("section") as HTMLElement;
    fireEvent.click(await within(pulse).findByRole("button", { name: "open Signal Pulse BNB" }));

    await waitFor(() => expect(screen.getByText("selected Signal Pulse")).toBeInTheDocument());
    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    expect(drawer.querySelector(".drawer-title h2")).toHaveTextContent("BNB");
  });

  it("renders Signal Pulse rows and opens the right-side inspector", async () => {
    const { container } = renderWithQuery(<App />);

    const pulse = (await screen.findByText("Signal Lab Pulse")).closest("section") as HTMLElement;
    const signalChainRow = await within(pulse).findByRole("button", { name: "open Signal Pulse BNB" });

    fireEvent.click(signalChainRow);

    await waitFor(() => expect(screen.getByText("selected Signal Pulse")).toBeInTheDocument());
    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    expect(drawer.querySelectorAll(".detail-drawer-card").length).toBeGreaterThanOrEqual(10);
    expect(drawer.querySelector(".detail-drawer-field")).toBeInTheDocument();
    expect(within(drawer).getByText("Why now")).toBeInTheDocument();
    expect(within(drawer).getByText("bull_case_zh")).toBeInTheDocument();
    expect(within(drawer).getByText("bear_case_zh")).toBeInTheDocument();
    expect(within(drawer).getByText("source_event_ids")).toBeInTheDocument();
    expect(within(drawer).getByText("evidence_event_ids")).toBeInTheDocument();
    expect(within(drawer).getByText("radar_score_json")).toBeInTheDocument();
    expect(within(drawer).getByText("market_context_json")).toBeInTheDocument();
    expect(within(drawer).getByText("gate_reasons_json")).toBeInTheDocument();
    expect(within(drawer).getByText("risk_reasons_json")).toBeInTheDocument();
    expect(within(drawer).getByText("playbooks")).toBeInTheDocument();
    expect(within(drawer).getByText("outcome_json")).toBeInTheDocument();
    expect(within(drawer).queryByRole("tab", { name: "Trace" })).not.toBeInTheDocument();
    expect(within(drawer).queryByText("Snapshot Ledger")).not.toBeInTheDocument();
    expect(screen.queryByText("harness-score-v1")).not.toBeInTheDocument();
    expect(screen.queryByText(["NO", "TRADE"].join("_"))).not.toBeInTheDocument();
    expect(screen.queryByText(["missing", "market"].join("_"))).not.toBeInTheDocument();
  });

  it("dedupes replay/live tape rows and token tape click does not change sort mode", async () => {
    renderWithQuery(<App />);

    await screen.findByText("实时信号 Tape");
    const tape = screen.getByText("实时信号 Tape").closest("section") as HTMLElement;
    expect(await screen.findByText("@traderpow -> $UPEG")).toBeInTheDocument();
    expect(screen.getAllByText("@traderpow -> $UPEG")).toHaveLength(1);
    expect(within(tape).getByText("$UPEG watched account evidence")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Heat" }));
    expect(screen.getByRole("button", { name: "Heat" })).toHaveClass("active");
    fireEvent.click(screen.getByText("@traderpow -> $UPEG"));
    expect(screen.getByRole("button", { name: "Heat" })).toHaveClass("active");
    expect(screen.getByRole("button", { name: "Timeline" })).toHaveClass("active");
  });

  it("shows actionable radar row context when timing has sparse market data", async () => {
    mockApi({ insufficientTiming: true });
    renderWithQuery(<App />);

    const tokenButton = await screen.findByRole("button", { name: "select token $UPEG" });
    expect(within(tokenButton).getByText("86 · 4 +4")).toBeInTheDocument();
    expect(within(tokenButton).getByText("market pending")).toBeInTheDocument();
    expect(within(tokenButton).getByText("market observation pending")).toBeInTheDocument();
  });

  it("keeps replay rows visible when websocket disconnects", async () => {
    socketMock.status = "disconnected";
    renderWithQuery(<App />);

    expect(await screen.findByText("ws disconnected")).toBeInTheDocument();
    expect(await screen.findByText("@traderpow -> $UPEG")).toBeInTheDocument();
  });

  it("requests selected token detail by target identity", async () => {
    mockApi({ missingTokenId: true });
    renderWithQuery(<App />);

    await screen.findByRole("button", { name: "select token $UPEG" });
    await waitFor(() => {
      const timelineCall = mockedGetApi.mock.calls.find(([path]) => path === "/api/target-social-timeline");
      const postsCall = mockedGetApi.mock.calls.find(([path]) => path === "/api/target-posts");
      expect(timelineCall?.[1]?.params).toMatchObject({
        target_type: "Asset",
        target_id: "asset:dex:eth:0x6982508145454ce325ddbe47a25d4ec3d2311933"
      });
      expect(postsCall?.[1]?.params).toMatchObject({
        target_type: "Asset",
        target_id: "asset:dex:eth:0x6982508145454ce325ddbe47a25d4ec3d2311933"
      });
    });
  });


  it("does not offer an audit page for unresolved token radar rows", async () => {
    mockApi({ assetFlowRows: [unresolvedAssetFlowRow()] });
    renderWithQuery(<App />);

    await screen.findByRole("button", { name: "select token $UPEG" });
    expect(screen.queryByText("Page")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /open token audit page/i })).not.toBeInTheDocument();
  });

  it("realigns the drawer when the selected token disappears after a window switch", async () => {
    mockApi({ windowSwapToken: true });
    const { container } = renderWithQuery(<App />);

    await screen.findByRole("button", { name: "select token $UPEG" });
    const radarSurface = container.querySelector('[data-mobile-task-panel="radar"]') as HTMLElement;
    fireEvent.click(within(radarSurface).getByRole("button", { name: "5m" }));

    const altRow = await screen.findByRole("button", { name: "select token $ALT" });
    await waitFor(() => expect(altRow).toHaveClass("selected"));
    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    expect(drawer.querySelector(".drawer-title h2")).toHaveTextContent("$ALT");
  });

  it("uses live token attribution before ambiguous cashtag matching in the tape", async () => {
    socketMock.events = [liveUpegEvent({ address: "0x1111111111111111111111111111111111111111" })];
    mockApi({ duplicateSymbol: true });
    const { container } = renderWithQuery(<App />);

    await screen.findAllByRole("button", { name: "select token $UPEG" });
    await screen.findByText("@traderpow -> $UPEG");
    fireEvent.click(screen.getByText("@traderpow -> $UPEG"));

    await waitFor(() => {
      const drawer = container.querySelector(".detail-drawer") as HTMLElement;
      expect(within(drawer).getByText((content) => content.includes("0x111111"))).toBeInTheDocument();
      expect(within(drawer).queryByText((content) => content.includes("0x222222"))).not.toBeInTheDocument();
    });
  });

  it("renders mobile task navigation with Token Radar as the default task", async () => {
    renderWithQuery(<App />);

    const mobileNav = await screen.findByRole("navigation", { name: "mobile cockpit tasks" });
    expect(mobileNav).toBeInTheDocument();
    expect(within(mobileNav).getByRole("button", { name: "Radar" })).toHaveAttribute("aria-current", "page");
    await waitFor(() => expect(within(mobileNav).getByRole("button", { name: "Detail" })).not.toBeDisabled());
    expect(await screen.findByText("TOKEN RADAR")).toBeInTheDocument();
  });

  it("switches mobile task to detail after selecting a token without changing token API params", async () => {
    renderWithQuery(<App />);
    const row = await screen.findByRole("button", { name: "select token $UPEG" });
    mockedGetApi.mockClear();

    fireEvent.click(row);

    const mobileNav = await screen.findByRole("navigation", { name: "mobile cockpit tasks" });
    await waitFor(() => expect(within(mobileNav).getByRole("button", { name: "Detail" })).toHaveAttribute("aria-current", "page"));
    expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/token-radar")).toBe(false);
    expect(screen.getByText("selected token")).toBeInTheDocument();
  });

  it("switches mobile tasks without resetting window, scope, or selected token", async () => {
    const { container } = renderWithQuery(<App />);
    await screen.findByRole("button", { name: "select token $UPEG" });
    const mobileNav = await screen.findByRole("navigation", { name: "mobile cockpit tasks" });

    fireEvent.click(within(mobileNav).getByRole("button", { name: "Tape" }));
    expect(within(mobileNav).getByRole("button", { name: "Tape" })).toHaveAttribute("aria-current", "page");

    fireEvent.click(within(mobileNav).getByRole("button", { name: "Lab" }));
    expect(within(mobileNav).getByRole("button", { name: "Lab" })).toHaveAttribute("aria-current", "page");

    fireEvent.click(within(mobileNav).getByRole("button", { name: "Radar" }));
    expect(within(mobileNav).getByRole("button", { name: "Radar" })).toHaveAttribute("aria-current", "page");

    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    expect(drawer.querySelector(".drawer-title h2")).toHaveTextContent("$UPEG");
    expect(useTraderStore.getState().window).toBe("1h");
    expect(useTraderStore.getState().scope).toBe("all");
  });

  it("returns mobile Radar and Tape tasks to the live cockpit after opening Signal Lab", async () => {
    renderWithQuery(<App />);
    const mobileNav = await screen.findByRole("navigation", { name: "mobile cockpit tasks" });
    const pulse = (await screen.findByText("Signal Lab Pulse")).closest("section") as HTMLElement;

    fireEvent.click(within(pulse).getByRole("button", { name: "Open Lab" }));
    await screen.findByText("Review Signal Pulse agent candidates by status, source, and query.");

    fireEvent.click(within(mobileNav).getByRole("button", { name: "Radar" }));
    expect(within(mobileNav).getByRole("button", { name: "Radar" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByText("TOKEN RADAR")).toBeInTheDocument();

    const livePulse = (await screen.findByText("Signal Lab Pulse")).closest("section") as HTMLElement;
    fireEvent.click(within(livePulse).getByRole("button", { name: "Open Lab" }));
    await screen.findByText("Review Signal Pulse agent candidates by status, source, and query.");
    fireEvent.click(within(mobileNav).getByRole("button", { name: "Tape" }));
    expect(within(mobileNav).getByRole("button", { name: "Tape" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByText("实时信号 Tape")).toBeInTheDocument();
  });

  it("exposes distinct responsive shell surfaces without duplicating Token Radar rows", async () => {
    const { container } = renderWithQuery(<App />);
    await screen.findByRole("button", { name: "select token $UPEG" });
    const responsiveControls = container.querySelector(".responsive-control-panel") as HTMLElement;

    expect(container.querySelector(".desktop-side-rail")).toBeInTheDocument();
    expect(responsiveControls).toBeInTheDocument();
    expect(responsiveControls).not.toHaveAttribute("hidden");
    expect(container.querySelector(".mobile-task-surface")).toBeInTheDocument();
    expect(container.querySelectorAll(".token-radar-table .radar-row")).toHaveLength(1);
  });

  it("marks mobile task panels so CSS can show one task at a time", async () => {
    const { container } = renderWithQuery(<App />);
    await screen.findByText("Signal Lab Pulse");

    expect(container.querySelector('[data-mobile-task-panel="radar"]')).toBeInTheDocument();
    expect(container.querySelector('[data-mobile-task-panel="tape"]')).toHaveClass("compact-panel");
    expect(container.querySelector('[data-mobile-task-panel="lab"]')).toHaveClass("compact-panel");
    expect(container.querySelector('[data-mobile-task-panel="detail"]')).toBeInTheDocument();
  });

  it("renders Signal Lab pulse rows without nested source controls", async () => {
    renderWithQuery(<App />);
    const pulse = (await screen.findByText("Signal Lab Pulse")).closest("section") as HTMLElement;

    expect(await within(pulse).findByRole("button", { name: "open Signal Pulse BNB" })).toBeInTheDocument();
    expect(within(pulse).queryByRole("link", { name: /source post/ })).not.toBeInTheDocument();
  });
});

function mockApi(options: {
  missingTokenId?: boolean;
  duplicateSymbol?: boolean;
  insufficientTiming?: boolean;
  windowSwapToken?: boolean;
  searchResult?: boolean;
  signalPulse?: SignalPulseData;
  signalPulseCompact?: SignalPulseData;
  signalPulseWorkbench?: SignalPulseData;
  signalPulseByHandle?: Record<string, SignalPulseData>;
  signalPulsePages?: Record<string, SignalPulseData>;
  recentItemsByHandle?: Record<string, LivePayload[]>;
  notifications?: NotificationItem[];
  assetFlowRows?: AssetFlowRow[];
  assetFlowRowsByWindow?: Partial<Record<WindowKey, AssetFlowRow[]>>;
  projectionVersion?: string;
} = {}) {
  mockedGetApi.mockImplementation(async (path, requestOptions) => {
    if (path === "/api/status") return ok(statusData);
    if (path === "/api/notification-summary") {
      return ok(statusData.notifications?.summary);
    }
    if (path === "/api/notifications") {
      return ok({ items: options.notifications ?? [], summary: statusData.notifications?.summary });
    }
    if (path === "/api/recent") {
      const handle = normalizedHandle(String(requestOptions?.params?.handles ?? ""));
      return ok({ scope: requestOptions?.params?.scope, events: [], items: options.recentItemsByHandle?.[handle] ?? [liveUpegEvent()] });
    }
    if (path === "/api/token-radar") {
      if (options.duplicateSymbol) {
        return ok<AssetFlowData>({
          window: "1h",
          scope: "all",
          targets: [
            assetFlowRow({ address: "0x1111111111111111111111111111111111111111" }),
            assetFlowRow({ address: "0x2222222222222222222222222222222222222222" })
          ],
          attention: [],
          projection: assetFlowProjection(options.projectionVersion)
        });
      }
      const window = String(requestOptions?.params?.window ?? "1h");
      const swapped = options.windowSwapToken && window === "5m";
      const rowsForWindow = options.assetFlowRowsByWindow?.[window as WindowKey];
      return ok<AssetFlowData>({
        window: window as AssetFlowData["window"],
        scope: "all",
        targets: rowsForWindow ?? options.assetFlowRows ?? [
          assetFlowRow({
            address: swapped ? "0x2222222222222222222222222222222222222222" : undefined,
            symbol: swapped ? "ALT" : undefined,
            insufficientTiming: options.insufficientTiming
          })
        ],
        attention: [],
        projection: assetFlowProjection(options.projectionVersion)
      });
    }
    if (path === "/api/target-social-timeline") {
      return ok<TokenSocialTimelineData>(timelineData(targetFixtureOptions(requestOptions?.params?.target_id)));
    }
    if (path === "/api/target-posts") {
      return ok<TokenPostsData>(postsData(targetFixtureOptions(requestOptions?.params?.target_id)));
    }
    if (path === "/api/account-quality") {
      return ok({
        query: { handles: ["traderpow", "alien19710628"] },
        accounts: [
          {
            profile: { handle: "traderpow", first_seen_ms: 1_777_746_010_000, latest_seen_ms: 1_777_746_010_000, follower_max: 168_905, watched_status: "watched" },
            summary: { status: "insufficient_sample", sample_size: 1, precision_score: null, early_call_score: 100, spam_risk_score: 0, avg_realized_return: null },
            token_call_stats: [],
            quality_snapshots: []
          }
        ]
      });
    }
    if (path === "/api/signal-lab/pulse") {
      const cursor = String(requestOptions?.params?.cursor ?? "");
      const window = String(requestOptions?.params?.window ?? "");
      const sort = String(requestOptions?.params?.sort ?? "");
      const handle = normalizedHandle(String(requestOptions?.params?.handle ?? ""));
      if (handle && options.signalPulseByHandle?.[handle]) {
        return ok(options.signalPulseByHandle[handle]);
      }
      if (window === "1h" && sort === "recent" && options.signalPulseCompact) {
        return ok(options.signalPulseCompact);
      }
      if (window === "1h" && options.signalPulsePages) {
        return ok(options.signalPulsePages[cursor] ?? options.signalPulsePages[""] ?? signalPulseData());
      }
      if (window === "1h" && options.signalPulseWorkbench) {
        return ok(options.signalPulseWorkbench);
      }
      return ok(options.signalPulse ?? signalPulseData());
    }
    if (path.startsWith("/api/signal-lab/pulse/")) {
      const candidateId = decodeURIComponent(path.slice("/api/signal-lab/pulse/".length));
      const sources: SignalPulseData[] = [];
      if (options.signalPulseCompact) sources.push(options.signalPulseCompact);
      if (options.signalPulseWorkbench) sources.push(options.signalPulseWorkbench);
      if (options.signalPulse) sources.push(options.signalPulse);
      if (options.signalPulseByHandle) sources.push(...Object.values(options.signalPulseByHandle));
      if (options.signalPulsePages) sources.push(...Object.values(options.signalPulsePages));
      sources.push(signalPulseData());
      for (const data of sources) {
        const match = data.items.find((item) => item.candidate_id === candidateId);
        if (match) {
          return ok(match);
        }
      }
      throw new ApiError("not found", 404);
    }
    if (path === "/api/enrichment-jobs") return ok({ items: [], counts: { pending: 1, running: 0, failed: 0, dead: 0, done: 8 } });
    if (path === "/api/search") {
      if (options.searchResult) {
        return ok({
          query: { kind: "text", text: String(requestOptions?.params?.q ?? ""), scope: "all" },
          total_count: 1,
          returned_count: 1,
          has_more: false,
          items: [
            {
              event: {
                event_id: "event-pepe-search",
                canonical_url: "https://x.com/searcher/status/42",
                author_handle: "searcher",
                received_at_ms: 1_777_746_080_000,
                text_clean: "PEPE ignition from search",
                cashtags: ["PEPE"],
                hashtags: ["alpha"],
                mentions: ["watcher"],
                is_watched: 0
              },
              match_type: "fts",
              score: -2.1
            }
          ]
        });
      }
      return ok({
        query: { kind: "symbol", text: String(requestOptions?.params?.q ?? ""), scope: "all", symbol: "PEPE" },
        total_count: 0,
        returned_count: 0,
        has_more: false,
        items: []
      });
    }
    throw new Error(`unexpected path ${path}`);
  });
}

function plainLiveEvent(): LivePayload {
  return {
    type: "event",
    event: {
      event_id: "event-plain-live",
      canonical_url: "https://x.com/anon/status/plain",
      author_handle: "anon",
      received_at_ms: 1_777_746_090_000,
      text_clean: "macro headline without token",
      cashtags: [],
      hashtags: ["macro"],
      mentions: [],
      is_watched: 0
    },
    entities: [{ entity_type: "hashtag", normalized_value: "macro", received_at_ms: 1_777_746_090_000 }],
    token_intents: [],
    token_resolutions: [],
    alerts: [],
    harness: null
  };
}

function assetFlowRow(
  options: {
    address?: string;
    symbol?: string;
    assetId?: string;
    assetType?: string;
    primaryVenue?: {
      venue_id?: string | null;
      venue_type?: string | null;
      exchange?: string | null;
      chain?: string | null;
      address?: string | null;
      inst_id?: string | null;
      inst_type?: string | null;
      base_symbol?: string | null;
      quote_symbol?: string | null;
    };
    price?: AssetFlowRow["price"];
    attention?: Partial<AssetFlowRow["attention"]>;
    score?: Partial<NonNullable<AssetFlowRow["score"]>>;
    insufficientTiming?: boolean;
  } = {}
): AssetFlowRow {
  const address = options.address ?? "0x6982508145454Ce325dDbE47a25d4ec3d2311933";
  const symbol = options.symbol ?? "UPEG";
  const assetId = options.assetId ?? `asset:dex:eth:${address.toLowerCase()}`;
  const isCex = options.assetType === "cex_asset" || options.primaryVenue?.venue_type === "cex";
  const targetType = isCex ? "CexToken" : "Asset";
  const targetId = isCex ? assetId.replace(/^asset:cex:/, "cex_token:") : assetId;
  const price = options.price ?? {
    market_status: "missing",
    market_observation_status: "pending",
    price_change_status: "pending_observation",
    provider: null,
    price_usd: null,
    market_cap_usd: null,
    liquidity_usd: null,
    volume_24h_usd: null,
    open_interest_usd: null,
    holders: null,
    snapshot_age_ms: null,
    snapshot_observed_at_ms: null,
    price_change_since_social_pct: null,
    price_change_before_social_pct: null
  };
  const marketFresh = price.market_status === "fresh" || price.market_status === "ready" || price.market_status === "stale";
  const timingStatus = options.insufficientTiming ? "market_pending" : marketFresh ? "neutral" : "market_pending";
  const timingRisks = timingStatus === "market_pending" ? ["market_observation_pending"] : [];
  return {
    intent: {
      intent_id: `intent:${assetId}`,
      display_symbol: symbol,
      display_name: null,
      evidence: []
    },
    target: isCex
      ? {
          target_type: "CexToken",
          target_id: targetId,
          symbol,
          status: "canonical",
          provider: options.primaryVenue?.exchange ?? "okx",
          native_market_id: options.primaryVenue?.inst_id ?? `${symbol}-USDT`,
          feed_type: options.primaryVenue?.inst_type ?? "cex_spot",
          quote_symbol: options.primaryVenue?.quote_symbol ?? "USDT"
        }
      : {
          target_type: "Asset",
          target_id: targetId,
          symbol,
          status: "candidate",
          chain_id: "eip155:1",
          token_standard: "erc20",
          address,
          pricefeed_id: `pricefeed:dex-token:gmgn_payload:eip155:1:${address.toLowerCase()}`
        },
    attention: {
      mentions_5m: 2,
      mentions_1h: 4,
      mentions_4h: 4,
      mentions_24h: 4,
      mentions_window: 4,
      unique_authors: 3,
      watched_mentions: 1,
      latest_seen_ms: 1_777_746_300_000,
      previous_mentions: 0,
      mention_delta: 4,
      mention_delta_pct: null,
      z_score: null,
      z_ewma: null,
      robust_z: null,
      new_burst_score: 80,
      stream_share: 0,
      baseline_version: "token_baseline_v2",
      baseline_status: "insufficient_history",
      baseline_sample_count: 0,
      baseline_nonzero_sample_count: 0,
      zero_slot_count: 6,
      ...options.attention
    },
    price,
    resolution: {
      status: "EXACT",
      resolution_status: "EXACT",
      target_type: targetType,
      target_id: targetId,
      reason_codes: ["CHAIN_ADDRESS_EXACT"],
      candidate_ids: [targetId],
      lookup_keys: []
    },
    score: {
      heat: scoreBlock({ score_version: "social_heat_v1", score: 86, status: "rising", reasons: ["rising"], risks: ["public_stream_coverage"] }),
      quality: scoreBlock({ score_version: "discussion_quality_v1", score: 78, reasons: ["resolved_asset"], risks: [] }),
      propagation: scoreBlock({ score_version: "propagation_v1", score: 72, reasons: ["independent_expansion"], risks: [] }),
      tradeability: scoreBlock({
        score_version: "tradeability_v2",
        score: marketFresh ? 80 : 60,
        reasons: ["resolved_target"],
        risks: [],
        identity_tradeable: true,
        market_fresh: marketFresh,
        market_cap_present: true,
        liquidity_present: true,
        pool_present: marketFresh
      }),
      timing: scoreBlock({
        score_version: "timing_v4",
        score: options.insufficientTiming ? 45 : marketFresh ? 50 : 45,
        status: timingStatus,
        chase_risk: false,
        reasons: [],
        risks: timingRisks
      }),
      opportunity: scoreBlock({
        score_version: "social_opportunity_v3",
        score: 79,
        reasons: ["backend_decision"],
        risks: ["public_stream_coverage"],
        components: { heat: 86, quality: 78, propagation: 72, tradeability: marketFresh ? 80 : 60, timing: options.insufficientTiming ? 45 : marketFresh ? 50 : 45 }
      })
      ,
      ...options.score
    },
    decision: "driver",
    data_health: { identity: "EXACT", market: price.market_observation_status ?? "pending", coverage: "public_stream" },
    source_event_ids: ["event-upeg-1", "event-upeg-2", "event-upeg-3", "event-upeg-4"]
  };
}

function unresolvedAssetFlowRow(): AssetFlowRow {
  const row = assetFlowRow();
  return {
    ...row,
    target: {
      target_type: null,
      target_id: null,
      symbol: row.target?.symbol ?? "UPEG",
      status: "unresolved"
    },
    resolution: {
      status: "UNRESOLVED",
      resolution_status: "UNRESOLVED",
      target_type: null,
      target_id: null,
      reason_codes: ["NO_DETERMINISTIC_TARGET"],
      candidate_ids: [],
      lookup_keys: []
    },
    decision: "investigate"
  };
}

function assetFlowProjection(version = "token-radar-fixture-current"): AssetFlowData["projection"] {
  return {
    status: "fresh",
    version,
    source: "token_radar_rows",
    source_max_received_at_ms: 1_777_746_300_000,
    computed_at_ms: 1_777_746_300_000
  };
}

function tokenFlowItem(options: { address?: string; symbol?: string; score?: number; insufficientTiming?: boolean } = {}): TokenFlowItem {
  const address = options.address ?? "0x6982508145454Ce325dDbE47a25d4ec3d2311933";
  const assetId = `asset:dex:eth:${address.toLowerCase()}`;
  const symbol = options.symbol ?? "UPEG";
  return {
    identity: {
      identity_key: assetId,
      identity_status: "resolved",
      target_type: "Asset",
      target_id: assetId,
      asset_id: assetId,
      asset_type: "dex_token",
      venue_type: "dex",
      exchange: "gmgn",
      chain: "eth",
      address,
      symbol
    },
    market: {
      market_status: "fresh",
      price: 0.001,
      market_cap: 60490,
      liquidity: 250000,
      pool_status: "ready",
      snapshot_age_ms: 120_000,
      snapshot_received_at_ms: 1_777_746_050_000,
      social_signal_start_ms: 1_777_746_000_000,
      reference_ms: 1_777_746_300_000,
      price_at_social_start: 0.001,
      price_at_reference: 0.00112,
      price_change_since_social_pct: 0.12,
      price_before_social_start: 0.0009,
      price_change_before_social_pct: 0.111111,
      market_observation_status: "ready",
      price_change_status: "ready"
    },
    flow: {
      window: "1h",
      window_start_ms: 1_777_746_000_000,
      window_end_ms: 1_777_746_300_000,
      mentions: 4,
      direct_mentions: 3,
      watched_mentions: 1,
      previous_mentions: 1,
      mention_delta: 3,
      mention_delta_pct: 3,
      z_score: 3.2,
      new_burst_score: null,
      stream_dominance: 0.25,
      baseline_status: "ready",
      baseline_sample_count: 20
    },
    social_heat: scoreBlock({
      score_version: "social_heat_v1",
      score: 86,
      reasons: ["z_score_above_3", "positive_mention_delta"],
      risks: ["public_stream_coverage"],
      window: "1h",
      mentions: 4,
      mentions_5m: 2,
      mentions_1h: 4,
      mentions_4h: 6,
      mentions_24h: 9,
      weighted_mentions: 3.8,
      previous_mentions: 1,
      mention_delta: 3,
      mention_delta_pct: 3,
      z_score: 3.2,
      new_burst_score: null,
      stream_share: 0.25,
      watched_share: 0.25,
      status: "burst"
    }),
    discussion_quality: scoreBlock({
      score_version: "discussion_quality_v1",
      score: 78,
      reasons: ["resolved_direct_evidence", "informative_discussion"],
      risks: [],
      evidence_specificity: 0.75,
      avg_post_quality: 82,
      avg_attribution_confidence: 1,
      duplicate_text_share: 0,
      informative_post_count: 3,
      watched_source_count: 1
    }),
    propagation: scoreBlock({
      score_version: "propagation_v1",
      score: 72,
      reasons: ["independent_expansion"],
      risks: [],
      independent_authors: 3,
      effective_authors: 2.6,
      new_authors: 3,
      top_author_share: 0.5,
      duplicate_text_share: 0,
      author_entropy: 1,
      reproduction_rate: 1.5,
      phase: "expansion",
      top_authors: [{ handle: "traderpow", count: 1, followers: 168_905, watched_count: 1 }]
    }),
    tradeability: scoreBlock({
      score_version: "tradeability_v1",
      score: 80,
      reasons: ["resolved_ca", "fresh_market"],
      risks: [],
      identity_tradeable: true,
      market_fresh: true,
      market_cap_present: true,
      liquidity_present: true,
      pool_present: true
    }),
    timing: options.insufficientTiming
      ? {
          score_version: "timing_v4",
          score: 45,
          status: "market_pending",
          chase_risk: false,
          social_signal_start_ms: 1_777_746_000_000,
          price_change_since_social_pct: null,
          price_change_before_social_pct: null,
          market_observation_status: "pending",
          reasons: [],
          risks: ["market_observation_pending"]
        }
      : {
          score_version: "timing_v4",
          score: 50,
          status: "neutral",
          chase_risk: false,
          social_signal_start_ms: 1_777_746_000_000,
          price_change_since_social_pct: 0.12,
          price_change_before_social_pct: 0.111111,
          market_observation_status: "ready",
          reasons: [],
          risks: []
        },
    opportunity: scoreBlock({
      score_version: "social_opportunity_v3",
      score: options.score ?? 79,
      decision: "driver",
      decision_priority: 3,
      reasons: ["z_score_above_3", "independent_expansion"],
      risks: ["public_stream_coverage"],
      components: { heat: 86, quality: 78, propagation: 72, tradeability: 80, timing: 50 }
    }),
    watch: {
      status: "direct_watch",
      direct_mentions: 1,
      direct_authors: 1,
      seed_link_count: 0,
      top_seed: null,
      reasons: ["watched_direct_mention"],
      risks: []
    },
    evidence_total_count: 4,
    posts_query: { target_type: "Asset", target_id: assetId, window: "1h", scope: "all", range: "current_window" },
    timeline_query: { target_type: "Asset", target_id: assetId, window: "1h", scope: "all" }
  };
}

function targetFixtureOptions(targetId: unknown): { symbol?: string; address?: string } {
  const id = String(targetId ?? "");
  if (id.includes("2222222222222222222222222222222222222222")) {
    return { symbol: "ALT", address: "0x2222222222222222222222222222222222222222" };
  }
  return {};
}

function timelineData(options: { symbol?: string; address?: string } = {}): TokenSocialTimelineData {
  const token = tokenFlowItem(options);
  return {
    query: { ...token.timeline_query, bucket: "5m" },
    summary: {
      posts: 3,
      authors: 2,
      effective_authors: 1.8,
      first_seen_ms: 1_777_746_010_000,
      latest_seen_ms: 1_777_746_060_000,
      watched_posts: 1,
      phase: "expansion",
      top_author_share: 0.5,
      duplicate_text_share: 0,
      peak_posts_per_bucket: 2,
      peak_new_authors_per_bucket: 1,
      reproduction_rate: 1.5
    },
    buckets: [
      { start_ms: 1_777_746_000_000, end_ms: 1_777_746_300_000, posts: 2, authors: 1, new_authors: 1, watched_posts: 1, duplicate_text_share: 0, price: null, price_change_from_start_pct: null },
      { start_ms: 1_777_746_300_000, end_ms: 1_777_746_600_000, posts: 1, authors: 1, new_authors: 1, watched_posts: 0, duplicate_text_share: 0, price: null, price_change_from_start_pct: null }
    ],
    market_overlay: {
      target_type: "Asset",
      target_id: token.identity.target_id,
      chain_id: "eip155:1",
      address: token.identity.address,
      symbol: token.identity.symbol,
      pricefeed_id: "pricefeed:test"
    },
    stages: [
      {
        stage_id: "seed:1777746010000:1",
        phase: "seed",
        start_ms: 1_777_746_010_000,
        end_ms: 1_777_746_010_000,
        duration_ms: 0,
        trigger_reason: "first_token_evidence",
        confidence: 0.61,
        people: { posts: 1, authors: 1, new_authors: 1, watched_posts: 1, watched_authors: 1, top_author_share: 1 },
        representative_event_ids: [`event-${(options.symbol ?? "UPEG").toLowerCase()}-1`],
        price: { status: "pending_observation", start_price: null, end_price: null, delta_pct: null, observation_ids: [], max_observation_lag_ms: null },
        risks: []
      }
    ],
    authors: [
      { handle: "traderpow", first_seen_ms: 1_777_746_010_000, latest_seen_ms: 1_777_746_010_000, posts: 1, followers: 168_905, role: "watched", quality_score: null },
      { handle: "alien19710628", first_seen_ms: 1_777_746_060_000, latest_seen_ms: 1_777_746_060_000, posts: 2, followers: 220, role: "amplifier", quality_score: null }
    ],
    posts: postsData(options).items.map((item, index) => ({
      ...item,
      bucket_start_ms: index < 2 ? 1_777_746_000_000 : 1_777_746_300_000
    })),
    cascade: {
      edges: [
        {
          event_id: "event-upeg-2",
          parent_event_id: "event-upeg-1",
          parent_tweet_id: "tweet-upeg-1",
          edge_type: "quote",
          parent_author_handle: "traderpow",
          resolved: true
        }
      ],
      unresolved_parents: []
    },
    returned_count: 3,
    has_more: false,
    next_cursor: null
  };
}

function postsData(options: { symbol?: string; address?: string } = {}): TokenPostsData {
  const symbol = options.symbol ?? "UPEG";
  return {
    query: tokenFlowItem(options).posts_query,
    score_window: { window: "1h" },
    total_count: 3,
    returned_count: 3,
    has_more: false,
    next_cursor: null,
    items: [
      post(`event-${symbol.toLowerCase()}-1`, "traderpow", `$${symbol} watched account evidence`, true, 86),
      post(`event-${symbol.toLowerCase()}-2`, "alien19710628", `$${symbol} public follow-through`, false, 74),
      post(`event-${symbol.toLowerCase()}-3`, "alien19710628", `$${symbol} another public post`, false, 68)
    ]
  };
}

function post(eventId: string, handle: string, text: string, watched: boolean, score: number) {
  const phase = eventId.endsWith("-1") ? "seed" : "ignition";
  return {
    event_id: eventId,
    tweet_id: eventId.replace("event", "tweet"),
    handle,
    received_at_ms: 1_777_746_010_000,
    text,
    url: `https://x.com/${handle}/status/${eventId}`,
    mention_source: "gmgn_token_payload",
    attribution_status: "direct",
    attribution_confidence: 1,
    attribution_weight: 1,
    is_watched: watched,
    is_first_seen_by_watched_for_token: watched,
    event_type: watched ? "watched_token_call" : "public_followup",
    reference: eventId === "event-upeg-2" ? { tweet_id: "tweet-upeg-1", author_handle: "traderpow", type: "quote" } : null,
    stage_id: `${phase}:1777746010000:1`,
    stage_phase: phase,
    author_role: watched ? "watched" : "early_amplifier",
    is_stage_representative: watched,
    price_delta_from_previous_post_pct: null,
    post_quality: {
      score_version: "post_quality_v1",
      score,
      reasons: ["structured_token_payload"],
      risks: [],
      contributions: [{ feature: "source_specificity", value: 18, reason: "structured_token_payload" }],
      risk_caps: []
    }
  };
}

function signalPulseData(): SignalPulseData {
  return {
    query: {
      window: "1h",
      scope: "all",
      status: null,
      handle: null,
      q: null
    },
    health: {
      pulse_ready: true,
      agent_worker_running: true,
      candidate_count: 3,
      blocked_low_information_count: 1,
      dead_job_count: 0,
      market_ready_rate: 0.67,
      settlement_coverage: 0.5
    },
    summary: {
      trade_candidate: 1,
      token_watch: 1,
      theme_watch: 1,
      risk_rejected_high_info: 0,
      blocked_low_information: 1
    },
    items: [
      {
        candidate_id: "pulse-bnb",
        candidate_type: "token",
        subject_key: "token:BNB",
        target_type: "CexToken",
        target_id: "asset:cex:okx:BNB-USDT",
        symbol: "BNB",
        window: "1h",
        scope: "all",
        pulse_status: "trade_candidate",
        verdict: "candidate",
        social_phase: "ignition",
        narrative_type: "token",
        candidate_score: 84,
        score_band: "A",
        summary_zh: "CZ 提到 build on BNB，形成 BNB 生态关注。",
        why_now_zh: "CZ 推动 BNB build 叙事，候选处于点火阶段。",
        bull_case_zh: ["强账号触发", "BNB 叙事扩散"],
        bear_case_zh: ["单一账号驱动"],
        confirmation_triggers_zh: ["更多 watched 账号跟进", "成交量确认"],
        invalidation_triggers_zh: ["讨论未扩散", "价格追高失败"],
        top_risks: ["public_stream_coverage"],
        gate_reasons: [{ code: "market_ready", passed: true }],
        risk_reasons: [{ code: "source_concentration", severity: "medium" }],
        evidence_event_ids: ["event-cz-bnb"],
        source_event_ids: ["event-cz-bnb", "event-bnb-2"],
        radar_score_json: { heat: 72, opportunity: 84 },
        market_context_json: { market_ready: true, outcome: { status: "pending" } },
        thesis_json: { setup: "watched_account_ignition", outcome: { horizon: "6h" } },
        agent_run_id: "agent-run-bnb",
        pulse_version: "pulse-v10",
        gate_version: "gate-v10",
        prompt_version: "prompt-v10",
        schema_version: "signal-pulse-v1",
        created_at_ms: 1_777_746_020_000,
        updated_at_ms: 1_777_746_040_000,
        playbooks: [{ name: "watch_breakout", state: "armed" }]
      }
    ],
    returned_count: 1,
    has_more: false,
    next_cursor: null
  };
}

function emptySignalPulseData(handle: string | null = null): SignalPulseData {
  const data = signalPulseData();
  return {
    ...data,
    query: {
      ...data.query,
      handle
    },
    health: {
      ...data.health,
      pulse_ready: false,
      candidate_count: 0,
      blocked_low_information_count: 0
    },
    summary: {
      trade_candidate: 0,
      token_watch: 0,
      theme_watch: 0,
      risk_rejected_high_info: 0,
      blocked_low_information: 0
    },
    items: [],
    returned_count: 0,
    has_more: false,
    next_cursor: null
  };
}

function watchedAccountLensEvent(handle: string): LivePayload {
  return {
    type: "event",
    event: {
      event_id: `event-${handle}-lens`,
      canonical_url: `https://x.com/${handle}/status/lens`,
      author_handle: handle,
      received_at_ms: 1_777_746_070_000,
      text_clean: "Account lens raw post without pulse",
      cashtags: [],
      hashtags: ["macro"],
      mentions: [],
      is_watched: 1
    },
    entities: [{ entity_type: "hashtag", normalized_value: "macro", received_at_ms: 1_777_746_070_000 }],
    token_intents: [],
    token_resolutions: [],
    alerts: [],
    harness: null
  };
}

function signalPulseNotification(): NotificationItem {
  return {
    notification_id: "notification-1",
    dedup_key: "signal_pulse_candidate:pulse-bnb:signature:1",
    rule_id: "signal_pulse_candidate",
    severity: "critical",
    title: "$BNB trade candidate",
    body: "BNB Signal Pulse trade candidate",
    entity_type: "pulse_candidate",
    entity_key: "pulse_candidate:pulse-bnb",
    author_handle: null,
    symbol: "BNB",
    chain: null,
    address: null,
    event_id: null,
    source_table: "pulse_candidates",
    source_id: "pulse-bnb",
    occurrence_count: 1,
    first_seen_at_ms: 1_777_746_040_000,
    last_seen_at_ms: 1_777_746_040_000,
    created_at_ms: 1_777_746_040_000,
    updated_at_ms: 1_777_746_040_000,
    read_at_ms: null,
    payload: {
      candidate_id: "pulse-bnb",
      pulse_status: "trade_candidate",
      symbol: "BNB"
    },
    channels: ["in_app", "pushdeer"]
  };
}

function normalizedHandle(handle: string): string {
  return handle.trim().replace(/^@/, "").toLowerCase();
}

function liveUpegEvent(options: { assetId?: string; address?: string } = {}): LivePayload {
  const address = options.address ?? "0x6982508145454Ce325dDbE47a25d4ec3d2311933";
  const assetId = options.assetId ?? `asset:dex:eth:${address.toLowerCase()}`;
  return {
    type: "event",
    event: {
      event_id: "event-upeg-1",
      canonical_url: "https://x.com/traderpow/status/1",
      author_handle: "traderpow",
      received_at_ms: 1_777_746_010_000,
      text_clean: "$UPEG watched account evidence",
      cashtags: ["UPEG"],
      is_watched: 1
    },
    entities: [{ entity_type: "symbol", normalized_value: "UPEG", received_at_ms: 1_777_746_010_000 }],
    token_intents: [
      {
        intent_id: `intent:${assetId}`,
        event_id: "event-upeg-1",
        display_symbol: "UPEG",
        chain_hint: "eth",
        address_hint: address,
        intent_status: "active",
        intent_confidence: 1
      }
    ],
    token_resolutions: [
      {
        resolution_id: `resolution:${assetId}`,
        intent_id: `intent:${assetId}`,
        event_id: "event-upeg-1",
        target_type: "Asset",
        target_id: assetId,
        pricefeed_id: `pricefeed:dex-token:gmgn_payload:eip155:1:${address.toLowerCase()}`,
        resolution_status: "EXACT",
        reason_codes_json: ["CHAIN_ADDRESS_EXACT"]
      }
    ],
    alerts: []
  };
}

function scoreBlock<T extends Record<string, unknown>>(extra: T) {
  return {
    contributions: [{ feature: "test", value: 10, reason: "test_reason" }],
    risk_caps: [],
    ...extra
  } as T & { contributions: Array<{ feature: string; value: number; reason: string }>; risk_caps: [] };
}

function renderWithQuery(children: ReactNode) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0
      }
    }
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

function ok<T>(data: T): ApiResponse<T> {
  return { ok: true, data };
}
