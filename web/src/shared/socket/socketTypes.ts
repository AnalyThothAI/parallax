import type { LivePayload, NotificationLivePayload } from "@lib/types";

export type SocketStatus =
  | "idle"
  | "connecting"
  | "authenticating"
  | "connected"
  | "closed"
  | "error";

export type MarketTargetRef = {
  target_type?: string | null;
  target_id?: string | null;
};

export type NormalizedMarketTarget = {
  target_type: string;
  target_id: string;
};

export type SocketSnapshot = {
  status: SocketStatus;
  eventItems: LivePayload[];
  notificationItems: NotificationLivePayload[];
  lastMessageAt: number | null;
};
