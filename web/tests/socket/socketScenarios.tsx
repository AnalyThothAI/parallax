import type { LiveMarketUpdatePayload, NotificationLivePayload } from "@lib/types";

export const socketScenario: {
  lastMessageAt: number | null;
  liveMarketUpdates: LiveMarketUpdatePayload[];
  notifications: NotificationLivePayload[];
  status: string;
} = {
  lastMessageAt: 1_777_770_000_000,
  liveMarketUpdates: [],
  notifications: [],
  status: "connected",
};

export function resetSocketScenario() {
  socketScenario.status = "connected";
  socketScenario.notifications = [];
  socketScenario.liveMarketUpdates = [];
  socketScenario.lastMessageAt = 1_777_770_000_000;
}
