import { setAuthToken } from "@lib/api/client";
import { cleanup, screen } from "@testing-library/react";
import { createApiMock, resetApiMock } from "@tests/msw/fixtures";
import { apiHandlers } from "@tests/msw/handlers";
import { mockBootstrap, mockLiveRadarRoute } from "@tests/msw/scenarios";
import { server } from "@tests/msw/server";
import { renderAppRoute } from "@tests/render/renderRoute";
import { resetSocketScenario, socketScenario } from "@tests/socket/socketScenarios";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMock = createApiMock();

vi.mock("@shared/socket/IntelSocketProvider", async () => {
  const React = await vi.importActual<typeof import("react")>("react");
  return {
    IntelSocketProvider: ({ children }: { children: ReactNode }) =>
      React.createElement(React.Fragment, null, children),
  };
});

vi.mock("@shared/socket/socketContext", () => ({
  useSocketSnapshot: () => ({
    eventItems: socketScenario.events,
    lastMessageAt: socketScenario.lastMessageAt,
    notificationItems: socketScenario.notifications,
    status: socketScenario.status,
  }),
}));

vi.mock("@shared/socket/useMarketSubscription", () => ({
  useMarketSubscription: () => undefined,
}));

describe("live radar route", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    setAuthToken(null);
    resetApiMock(apiMock);
    resetSocketScenario();
    server.use(...apiHandlers(apiMock));
    mockBootstrap(apiMock);
    mockLiveRadarRoute(apiMock);
  });

  it("renders Token Radar as the default route", async () => {
    renderAppRoute("/");

    expect(await screen.findByRole("heading", { name: "Token Radar" })).toBeInTheDocument();
  });
});
