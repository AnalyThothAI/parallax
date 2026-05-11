import { useEffect, useRef, useState } from "react";
import ReconnectingWebSocket from "reconnecting-websocket";

import { websocketUrl } from "./client";
import type { LivePayload, MarketUpdatePayload, NotificationLivePayload } from "./types";

type SocketStatus = "idle" | "connecting" | "authenticating" | "connected" | "closed" | "error";

type Options = {
  token: string;
  handles: string;
  replay: number;
  notifications?: boolean;
  marketTargets?: Array<{ target_type?: string | null; target_id?: string | null }>;
};

export function useIntelSocket({
  token,
  handles,
  replay,
  notifications = false,
  marketTargets = [],
}: Options) {
  const [status, setStatus] = useState<SocketStatus>("idle");
  const [events, setEvents] = useState<LivePayload[]>([]);
  const [notificationEvents, setNotificationEvents] = useState<NotificationLivePayload[]>([]);
  const [marketUpdates, setMarketUpdates] = useState<MarketUpdatePayload[]>([]);
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null);
  const socketRef = useRef<ReconnectingWebSocket | null>(null);
  const marketTargetKey = JSON.stringify(normalizeMarketTargets(marketTargets));

  useEffect(() => {
    if (!token) {
      setStatus("idle");
      setEvents([]);
      setNotificationEvents([]);
      setMarketUpdates([]);
      setLastMessageAt(null);
      return;
    }
    const normalizedMarketTargets = JSON.parse(marketTargetKey) as Array<{
      target_type: string;
      target_id: string;
    }>;

    const ws = new ReconnectingWebSocket(websocketUrl(), [], {
      connectionTimeout: 4_000,
      maxRetries: Infinity,
      maxReconnectionDelay: 8_000,
      minReconnectionDelay: 800,
    });
    socketRef.current = ws;
    setStatus("connecting");

    ws.addEventListener("open", () => {
      setStatus("authenticating");
      ws.send(JSON.stringify({ type: "auth", token }));
    });

    ws.addEventListener("message", (message) => {
      setLastMessageAt(Date.now());
      const payload = JSON.parse(String(message.data)) as { type?: string } | LivePayload;
      if (payload.type === "ready") {
        setStatus("connected");
        ws.send(
          JSON.stringify({
            type: "subscribe",
            handles: normalizeHandles(handles),
            notifications,
            market_targets: normalizedMarketTargets,
            replay,
          }),
        );
        return;
      }
      if (payload.type === "event") {
        setEvents((current) => [payload as LivePayload, ...current].slice(0, 100));
        return;
      }
      if (payload.type === "notification") {
        setNotificationEvents((current) =>
          [payload as NotificationLivePayload, ...current].slice(0, 50),
        );
        return;
      }
      if (payload.type === "market_update") {
        setMarketUpdates((current) => [payload as MarketUpdatePayload, ...current].slice(0, 100));
      }
    });

    ws.addEventListener("close", () => setStatus("closed"));
    ws.addEventListener("error", () => setStatus("error"));

    return () => {
      socketRef.current = null;
      ws.close();
    };
  }, [token, handles, replay, notifications, marketTargetKey]);

  return { status, events, notifications: notificationEvents, marketUpdates, lastMessageAt };
}

function normalizeHandles(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim().replace(/^@/, "").toLowerCase())
    .filter(Boolean);
}

function normalizeMarketTargets(
  values: Array<{ target_type?: string | null; target_id?: string | null }>,
): Array<{ target_type: string; target_id: string }> {
  const seen = new Set<string>();
  const targets = [];
  for (const value of values) {
    const targetType = String(value.target_type ?? "").trim();
    const targetId = String(value.target_id ?? "").trim();
    if (!targetType || !targetId) {
      continue;
    }
    const key = `${targetType}:${targetId}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    targets.push({ target_type: targetType, target_id: targetId });
  }
  return targets.sort((left, right) =>
    `${left.target_type}:${left.target_id}`.localeCompare(
      `${right.target_type}:${right.target_id}`,
    ),
  );
}
