import {
  appStatusFixture,
  recentReplayFixture,
  signalPulseFixture,
  tokenRadarFixture,
} from "@tests/fixtures/appRouteFixtures";

import type { ApiMock } from "./fixtures";
import { defaultBootstrap, ok } from "./fixtures";

export function mockBootstrap(apiMock: ApiMock) {
  apiMock.getBootstrapImpl = async () => defaultBootstrap();
}

export function mockLiveRadarRoute(apiMock: ApiMock) {
  apiMock.getApiImpl = async (path) => {
    if (path === "/api/status") return ok(appStatusFixture());
    if (path === "/api/notification-summary") return ok(appStatusFixture().notifications?.summary);
    if (path === "/api/notifications") {
      return ok({ items: [], summary: appStatusFixture().notifications?.summary });
    }
    if (path === "/api/recent") return ok(recentReplayFixture());
    if (path === "/api/token-radar") return ok(tokenRadarFixture());
    if (path === "/api/signal-lab/pulse") return ok(signalPulseFixture());
    throw new Error(`unexpected path ${path}`);
  };
}
