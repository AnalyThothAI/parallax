import type { LiveMarketUpdatePayload, LivePayload, NotificationLivePayload } from "@lib/types";

export const socketScenario: {
  events: LivePayload[];
  lastMessageAt: number | null;
  liveMarketUpdates: LiveMarketUpdatePayload[];
  notifications: NotificationLivePayload[];
  status: string;
} = {
  events: [],
  lastMessageAt: 1_777_770_000_000,
  liveMarketUpdates: [],
  notifications: [],
  status: "connected",
};

export function resetSocketScenario() {
  socketScenario.status = "connected";
  socketScenario.events = [];
  socketScenario.notifications = [];
  socketScenario.liveMarketUpdates = [];
  socketScenario.lastMessageAt = 1_777_770_000_000;
}
