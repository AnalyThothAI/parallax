import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type {
  ApiResponse,
  BootstrapData,
  LivePayload,
  NotificationLivePayload,
  StatusData,
  TokenFlowData,
  TokenFlowItem,
  TokenPostsData,
  TokenSocialTimelineData,
  TradingAttentionData
} from "./api/types";
import { getApi, getBootstrap } from "./api/client";
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
    getBootstrap: vi.fn()
  };
});

vi.mock("./api/useIntelSocket", () => ({
  useIntelSocket: () => socketMock
}));

const mockedGetApi = vi.mocked(getApi);
const mockedGetBootstrap = vi.mocked(getBootstrap);

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
  market_observations: {
    pending: 0,
    running: 0,
    ready: 1,
    cached: 0,
    provider_error: 0,
    rate_limited: 0,
    dead: 0,
    worker_running: true
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
      watchedPostsOnly: false,
      activeView: "live",
      signalLabKind: "all",
      signalLabHandle: "",
      signalLabSearch: ""
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
    expect(within(row).getByText("86 · 4 +3")).toBeInTheDocument();
    expect(within(row).getByText("4 posts · z3.2 · share 25%")).toBeInTheDocument();
    expect(within(row).getByText("78 · CA direct")).toBeInTheDocument();
    expect(within(row).getByText("dup 0% · info 3")).toBeInTheDocument();
    expect(within(row).getByText("expansion · 3 author")).toBeInTheDocument();
    expect(within(row).getByText("top 50% · repro 1.5")).toBeInTheDocument();
    expect(within(row).getByText("+12% fresh")).toBeInTheDocument();
    expect(within(row).getByText("neutral")).toBeInTheDocument();
    expect(within(row).getByText("+12% since social")).toBeInTheDocument();
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

  it("exposes a GMGN link for resolved radar tokens", async () => {
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
    expect(rowButton.querySelector('[data-radar-metric="heat"]')).toHaveTextContent("86 · 4 +3");
    expect(rowButton.querySelector('[data-radar-metric="quality"]')).toHaveTextContent("78 · CA direct");
    expect(rowButton.querySelector('[data-radar-metric="propagation"]')).toHaveTextContent("expansion · 3 author");
    expect(rowButton.querySelector('[data-radar-metric="market"]')).toHaveTextContent("$60K");
    expect(rowButton.querySelector('[data-radar-metric="timing"]')).toHaveTextContent("neutral");
    expect(row.querySelector('[data-radar-action="gmgn"]')).toBeInTheDocument();
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
    expect(await within(pulse).findByText(/@cz_binance · watch · updated/)).toBeInTheDocument();
    expect(within(pulse).getByText("CZ 提到 build on BNB，形成 BNB 生态关注。")).toBeInTheDocument();
    expect(within(pulse).queryByText("extractor configured")).not.toBeInTheDocument();
    expect(within(pulse).queryByLabelText("signal lab pulse stages")).not.toBeInTheDocument();
    expect(screen.getByText("Token")).toBeInTheDocument();

    fireEvent.click(await within(pulse).findByRole("button", { name: "open trading attention BNB" }));

    await waitFor(() => expect(screen.getByText("selected trading attention")).toBeInTheDocument());
    expect(screen.getByText("Token")).toBeInTheDocument();
    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    expect(within(drawer).getByText("Why it matters")).toBeInTheDocument();
    expect(within(drawer).getByText("Linked tokens")).toBeInTheDocument();
  });

  it("switches the left rail into the Signal Lab workbench without losing the selected attention item", async () => {
    const { container } = renderWithQuery(<App />);

    const rail = container.querySelector(".side-rail") as HTMLElement;
    fireEvent.click(await within(rail).findByRole("button", { name: /Signal Lab/ }));

    const workbench = await screen.findByText("Track watched-account trading attention across direct tokens, topics, ecosystems, risk, and market structure.");
    expect(workbench).toBeInTheDocument();
    expect(screen.getByText("Trading Attention")).toBeInTheDocument();
    const views = within(container.querySelector(".side-rail") as HTMLElement).getByText("views").closest("section") as HTMLElement;
    expect(within(views).queryByText("Tokens")).not.toBeInTheDocument();
    expect(within(views).queryByText("Accounts")).not.toBeInTheDocument();
    expect(within(views).queryByText("Jobs/Ops")).not.toBeInTheDocument();
    expect(screen.getByText("Direct token")).toBeInTheDocument();
    expect(screen.getByText("Topic heat")).toBeInTheDocument();
    expect(screen.getByText("Ecosystem")).toBeInTheDocument();
    expect(screen.getByText("Structure")).toBeInTheDocument();
    expect(screen.getByText("Risk")).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: "open trading attention BNB" }));
    expect(await screen.findByText("selected trading attention")).toBeInTheDocument();
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

  it("renders the selected token drawer with the mock structure and no extra override controls", async () => {
    const { container } = renderWithQuery(<App />);

    await screen.findByRole("button", { name: "select token $UPEG" });

    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    expect(drawer).toBeInTheDocument();
    expect(drawer.querySelector(".detail-focus")).not.toBeInTheDocument();
    expect(drawer.querySelector(".drawer-title .eyebrow")).toHaveTextContent("selected token");
    expect(drawer.querySelector(".drawer-title h2")).toHaveTextContent("$UPEG");
    expect(drawer.querySelector(".opportunity-score")).toHaveTextContent("79");
    expect(within(drawer).getByText("86 / burst")).toBeInTheDocument();
    expect(within(drawer).getByText("78 / direct")).toBeInTheDocument();
    expect(within(drawer).getByText("3 authors")).toBeInTheDocument();
    expect(within(drawer).getByText("neutral")).toBeInTheDocument();
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
      expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/token-social-timeline")).toBe(true);
      expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/token-posts")).toBe(true);
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
      const timelineCall = mockedGetApi.mock.calls.find(([path]) => path === "/api/token-social-timeline");
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
      const postsCall = mockedGetApi.mock.calls.find(([path]) => path === "/api/token-posts");
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
      const postsCall = mockedGetApi.mock.calls.find(([path]) => path === "/api/token-posts");
      expect(postsCall?.[1]?.params).toMatchObject({ sort: "catalyst", cursor: undefined });
    });
  });

  it("removes narrative product surface and exposes signal lab entry points", async () => {
    renderWithQuery(<App />);

    await screen.findByText("Token");
    expect(screen.queryByText("Narratives")).not.toBeInTheDocument();
    expect(screen.getAllByText("Signal Lab").length).toBeGreaterThan(0);
  });

  it("uses the trading-attention read model as the only Signal Lab product source in the UI", async () => {
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
      const tokenFlowCall = mockedGetApi.mock.calls.find(([path]) => path === "/api/token-flow");
      expect(tokenFlowCall?.[1]?.params).toMatchObject({ window: "1h", limit: 48, scope: "all" });
      expect(tokenFlowCall?.[1]?.params).not.toHaveProperty("horizon");
    });
  });

  it("routes Signal Lab toolbar filters into the trading-attention read model", async () => {
    const { container } = renderWithQuery(<App />);

    const rail = container.querySelector(".side-rail") as HTMLElement;
    fireEvent.click(await within(rail).findByRole("button", { name: /Signal Lab/ }));

    fireEvent.click(await screen.findByRole("button", { name: /Topic heat/ }));
    fireEvent.change(screen.getByLabelText("Signal Lab source filter"), { target: { value: "@cz_binance" } });
    fireEvent.change(screen.getByLabelText("Signal Lab text filter"), { target: { value: "build on BNB" } });

    await waitFor(() => {
      expect(
        mockedGetApi.mock.calls.some(
          ([path, options]) =>
            path === "/api/signal-lab/pulse" &&
            options?.params?.kind === "topic_heat" &&
            options?.params?.handle === "@cz_binance" &&
            options?.params?.q === "build on BNB"
        )
      ).toBe(true);
    });
  });

  it("uses the Signal Lab cursor to load additional attention items in the workbench", async () => {
    const firstPage = tradingAttentionData();
    const secondItem = {
      ...firstPage.items[0],
      item_id: "attention-sol-product",
      title: "SOL",
      summary: "SOL ecosystem attention loaded from cursor.",
      linked_tokens: [],
      linked_topics: [{ key: "sol", label: "SOL", role: "asset" }]
    };
    mockApi({
      tradingAttentionPages: {
        "": { ...firstPage, has_more: true, next_cursor: "80" },
        "80": {
          ...firstPage,
          items: [secondItem],
          returned_count: 1,
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
    expect(await screen.findByText("SOL ecosystem attention loaded from cursor.")).toBeInTheDocument();
  });

  it("renders trading-attention rows and opens the right-side inspector", async () => {
    const { container } = renderWithQuery(<App />);

    const pulse = (await screen.findByText("Signal Lab Pulse")).closest("section") as HTMLElement;
    const signalChainRow = await within(pulse).findByRole("button", { name: "open trading attention BNB" });

    fireEvent.click(signalChainRow);

    await waitFor(() => expect(screen.getByText("selected trading attention")).toBeInTheDocument());
    const drawer = container.querySelector(".detail-drawer") as HTMLElement;
    expect(within(drawer).getByText("Why it matters")).toBeInTheDocument();
    expect(within(drawer).getByText("Original post")).toBeInTheDocument();
    expect(within(drawer).getByText("Linked tokens")).toBeInTheDocument();
    expect(within(drawer).getByText("Linked topics")).toBeInTheDocument();
    expect(within(drawer).getByText("Risks")).toBeInTheDocument();
    expect(within(drawer).queryByRole("tab", { name: "Trace" })).not.toBeInTheDocument();
    expect(within(drawer).queryByText("Snapshot Ledger")).not.toBeInTheDocument();
    expect(screen.queryByText("harness-score-v1")).not.toBeInTheDocument();
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
    expect(within(tokenButton).getByText("86 · 4 +3")).toBeInTheDocument();
    expect(within(tokenButton).getByText("market pending")).toBeInTheDocument();
    expect(within(tokenButton).getByText("market observation pending")).toBeInTheDocument();
  });

  it("keeps replay rows visible when websocket disconnects", async () => {
    socketMock.status = "disconnected";
    renderWithQuery(<App />);

    expect(await screen.findByText("ws disconnected")).toBeInTheDocument();
    expect(await screen.findByText("@traderpow -> $UPEG")).toBeInTheDocument();
  });

  it("requests selected token detail by chain and address when token_id is absent", async () => {
    mockApi({ missingTokenId: true });
    renderWithQuery(<App />);

    await screen.findByRole("button", { name: "select token $UPEG" });
    await waitFor(() => {
      const timelineCall = mockedGetApi.mock.calls.find(([path]) => path === "/api/token-social-timeline");
      const postsCall = mockedGetApi.mock.calls.find(([path]) => path === "/api/token-posts");
      expect(timelineCall?.[1]?.params).toMatchObject({ chain: "eth", address: "0x6982508145454Ce325dDbE47a25d4ec3d2311933" });
      expect(postsCall?.[1]?.params).toMatchObject({ chain: "eth", address: "0x6982508145454Ce325dDbE47a25d4ec3d2311933" });
    });
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
    socketMock.events = [liveUpegEvent({ tokenId: "token:eth:0x1111111111111111111111111111111111111111", address: "0x1111111111111111111111111111111111111111" })];
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
    expect(mockedGetApi.mock.calls.some(([path]) => path === "/api/token-flow")).toBe(false);
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
    await screen.findByText("Track watched-account trading attention across direct tokens, topics, ecosystems, risk, and market structure.");
    expect(useTraderStore.getState().activeView).toBe("signal_lab");

    fireEvent.click(within(mobileNav).getByRole("button", { name: "Radar" }));
    expect(useTraderStore.getState().activeView).toBe("live");
    expect(within(mobileNav).getByRole("button", { name: "Radar" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByText("TOKEN RADAR")).toBeInTheDocument();

    const livePulse = (await screen.findByText("Signal Lab Pulse")).closest("section") as HTMLElement;
    fireEvent.click(within(livePulse).getByRole("button", { name: "Open Lab" }));
    await screen.findByText("Track watched-account trading attention across direct tokens, topics, ecosystems, risk, and market structure.");
    fireEvent.click(within(mobileNav).getByRole("button", { name: "Tape" }));
    expect(useTraderStore.getState().activeView).toBe("live");
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

  it("links Signal Lab pulse attention to the source tweet without nesting controls", async () => {
    renderWithQuery(<App />);
    const pulse = (await screen.findByText("Signal Lab Pulse")).closest("section") as HTMLElement;

    expect(await within(pulse).findByRole("button", { name: "open trading attention BNB" })).toBeInTheDocument();
    expect(within(pulse).getByRole("link", { name: "open source post for BNB" })).toHaveAttribute(
      "href",
      "https://x.com/cz_binance/status/42"
    );
  });
});

function mockApi(options: {
  missingTokenId?: boolean;
  duplicateSymbol?: boolean;
  insufficientTiming?: boolean;
  windowSwapToken?: boolean;
  searchResult?: boolean;
  tradingAttention?: TradingAttentionData;
  tradingAttentionPages?: Record<string, TradingAttentionData>;
} = {}) {
  mockedGetApi.mockImplementation(async (path, requestOptions) => {
    if (path === "/api/status") return ok(statusData);
    if (path === "/api/notification-summary") {
      return ok(statusData.notifications?.summary);
    }
    if (path === "/api/notifications") {
      return ok({ items: [], summary: statusData.notifications?.summary });
    }
    if (path === "/api/recent") return ok({ scope: requestOptions?.params?.scope, events: [], items: [liveUpegEvent()] });
    if (path === "/api/token-flow") {
      if (options.duplicateSymbol) {
        return ok<TokenFlowData>({
          window: "1h",
          scope: "all",
          items: [
            tokenFlowItem({ tokenId: "token:eth:0x1111111111111111111111111111111111111111", address: "0x1111111111111111111111111111111111111111" }),
            tokenFlowItem({ tokenId: "token:eth:0x2222222222222222222222222222222222222222", address: "0x2222222222222222222222222222222222222222", score: 60 })
          ]
        });
      }
      const window = String(requestOptions?.params?.window ?? "1h");
      const swapped = options.windowSwapToken && window === "5m";
      return ok<TokenFlowData>({
        window: window as TokenFlowData["window"],
        scope: "all",
        items: [
          tokenFlowItem({
            tokenId: swapped ? "token:eth:0x2222222222222222222222222222222222222222" : options.missingTokenId ? null : undefined,
            address: swapped ? "0x2222222222222222222222222222222222222222" : undefined,
            symbol: swapped ? "ALT" : undefined,
            insufficientTiming: options.insufficientTiming
          })
        ]
      });
    }
    if (path === "/api/token-social-timeline") return ok<TokenSocialTimelineData>(timelineData());
    if (path === "/api/token-posts") return ok<TokenPostsData>(postsData());
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
      return ok(options.tradingAttentionPages?.[cursor] ?? options.tradingAttention ?? tradingAttentionData());
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
    token_attributions: [],
    alerts: []
  };
}

function tokenFlowItem(options: { tokenId?: string | null; address?: string; symbol?: string; score?: number; insufficientTiming?: boolean } = {}): TokenFlowItem {
  const address = options.address ?? "0x6982508145454Ce325dDbE47a25d4ec3d2311933";
  const tokenId = options.tokenId === undefined ? `token:eth:${address}` : options.tokenId;
  const symbol = options.symbol ?? "UPEG";
  return {
    identity: {
      identity_key: tokenId ?? `eth:${address}`,
      identity_status: "resolved_ca",
      token_id: tokenId,
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
    posts_query: { token_id: tokenId, chain: "eth", address, window: "1h", scope: "all", range: "current_window" },
    timeline_query: { token_id: tokenId, chain: "eth", address, window: "1h", scope: "all" }
  };
}

function timelineData(): TokenSocialTimelineData {
  return {
    query: { ...tokenFlowItem().timeline_query, bucket: "5m" },
    summary: {
      posts: 3,
      authors: 2,
      effective_authors: 1.8,
      first_seen_ms: 1_777_746_010_000,
      latest_seen_ms: 1_777_746_060_000,
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
    authors: [
      { handle: "traderpow", first_seen_ms: 1_777_746_010_000, latest_seen_ms: 1_777_746_010_000, posts: 1, followers: 168_905, role: "watched", quality_score: null },
      { handle: "alien19710628", first_seen_ms: 1_777_746_060_000, latest_seen_ms: 1_777_746_060_000, posts: 2, followers: 220, role: "amplifier", quality_score: null }
    ],
    posts: postsData().items.map((item, index) => ({
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

function postsData(): TokenPostsData {
  return {
    query: tokenFlowItem().posts_query,
    score_window: { window: "1h" },
    total_count: 3,
    returned_count: 3,
    has_more: false,
    next_cursor: null,
    items: [
      post("event-upeg-1", "traderpow", "$UPEG watched account evidence", true, 86),
      post("event-upeg-2", "alien19710628", "$UPEG public follow-through", false, 74),
      post("event-upeg-3", "alien19710628", "$UPEG another public post", false, 68)
    ]
  };
}

function post(eventId: string, handle: string, text: string, watched: boolean, score: number) {
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

function tradingAttentionData(): TradingAttentionData {
  return {
    query: {
      window: "1h",
      scope: "all",
      kind: null,
      handle: null,
      q: null
    },
    summary: {
      direct_token: 1,
      topic_heat: 1,
      ecosystem_signal: 1,
      market_structure: 0,
      risk_alert: 0,
      low_signal: 0,
      hot: 0,
      watch: 2,
      context: 1,
      muted: 0
    },
    items: [
      {
        item_id: "attention-bnb",
        kind: "ecosystem_signal",
        kind_label: "Ecosystem",
        priority: "watch",
        heat_score: 72,
        received_at_ms: 1_777_746_020_000,
        updated_at_ms: 1_777_746_040_000,
        source: { handle: "cz_binance", followers: 9_000_000 },
        event: {
          event_id: "event-cz-bnb",
          tweet_id: "42",
          canonical_url: "https://x.com/cz_binance/status/42",
          author_handle: "cz_binance",
          text: "build on BNB",
          received_at_ms: 1_777_746_020_000
        },
        event_type: "meme_phrase_seed",
        direction_hint: "attention_positive",
        attention_mechanism: "meme_phrase",
        title: "BNB",
        summary: "CZ 提到 build on BNB，形成 BNB 生态关注。",
        why_it_matters: "Watched account attention can pull liquidity into the BNB ecosystem without forcing a trade label.",
        linked_tokens: [
          {
            token_id: "token:bsc:bnb",
            identity_key: "token:bsc:bnb",
            symbol: "BNB",
            chain: "bsc",
            address: null,
            relation: "candidate",
            confidence: 0.82,
            status: "resolved",
            source: "social_event"
          }
        ],
        linked_topics: [{ key: "build-on-bnb", label: "build on BNB", role: "meme_phrase" }],
        metrics: {
          impact: 72,
          novelty: 68,
          confidence: 0.86,
          direct_token_count: 1,
          topic_count: 1,
          account_alert_count: 0,
          window_mentions: 2,
          watched_author_count: 1
        },
        risks: ["public_stream_coverage"],
        next_action: "Inspect BNB ecosystem tape and confirm whether mentions broaden across watched accounts."
      }
    ],
    returned_count: 1,
    has_more: false,
    next_cursor: null
  };
}

function liveUpegEvent(options: { tokenId?: string; address?: string } = {}): LivePayload {
  const address = options.address ?? "0x6982508145454Ce325dDbE47a25d4ec3d2311933";
  const tokenId = options.tokenId ?? `token:eth:${address}`;
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
    token_attributions: [
      {
        token_id: tokenId,
        identity_key: tokenId,
        identity_status: "resolved_ca",
        chain: "eth",
        address,
        symbol: "UPEG",
        attribution_status: "direct",
        attribution_confidence: 1,
        attribution_weight: 1,
        attribution_rank: 0
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
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}

function ok<T>(data: T): ApiResponse<T> {
  return { ok: true, data };
}
