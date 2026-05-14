import {
  appStatusFixture,
  notificationFixture,
  recentReplayFixture,
  searchInspectFixture,
  signalPulseFixture,
  targetPostsFixture,
  targetSocialTimelineFixture,
  tokenRadarFixture,
} from "@tests/fixtures/appRouteFixtures";

import type { ApiMock } from "./fixtures";
import { defaultBootstrap, ok } from "./fixtures";

export function mockBootstrap(apiMock: ApiMock) {
  apiMock.getBootstrapImpl = async () => defaultBootstrap();
}

export function mockLiveRadarRoute(apiMock: ApiMock) {
  apiMock.getApiImpl = async (path, requestOptions) => {
    if (path === "/api/status") return ok(appStatusFixture());
    if (path === "/api/notification-summary") return ok(appStatusFixture().notifications?.summary);
    if (path === "/api/notifications") {
      return ok({ items: [], summary: appStatusFixture().notifications?.summary });
    }
    if (path === "/api/recent") return ok(recentReplayFixture());
    if (path === "/api/token-radar") return ok(tokenRadarFixture());
    if (path === "/api/signal-lab/pulse") return ok(signalPulseFixture());
    if (path === "/api/search/inspect") {
      const q = String(requestOptions?.params?.q ?? "$RKC");
      return ok(searchInspectFixture({ query: { ...searchInspectFixture().query, q } }));
    }
    if (path === "/api/target-social-timeline") return ok(targetSocialTimelineFixture());
    if (path === "/api/target-posts") return ok(targetPostsFixture());
    throw new Error(`unexpected path ${path}`);
  };
}

export function mockNotificationRoute(apiMock: ApiMock) {
  const summary = {
    ...appStatusFixture().notifications!.summary,
    unread_count: 1,
    high_unread_count: 1,
    account_unread_counts: { traderpow: 1 },
  };
  const notification = notificationFixture();
  apiMock.getApiImpl = async (path) => {
    if (path === "/api/status") {
      return ok(
        appStatusFixture({
          notifications: {
            enabled: true,
            worker_running: true,
            summary,
          },
        }),
      );
    }
    if (path === "/api/notification-summary") return ok(summary);
    if (path === "/api/notifications") return ok({ items: [notification], summary });
    if (path === "/api/recent") return ok(recentReplayFixture());
    if (path === "/api/token-radar") return ok(tokenRadarFixture());
    if (path === "/api/signal-lab/pulse") return ok(signalPulseFixture());
    if (path === "/api/target-social-timeline") return ok(targetSocialTimelineFixture());
    if (path === "/api/target-posts") return ok(targetPostsFixture());
    throw new Error(`unexpected path ${path}`);
  };
}
