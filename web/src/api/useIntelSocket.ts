import { useEffect, useRef, useState } from "react";
import ReconnectingWebSocket from "reconnecting-websocket";

import { websocketUrl } from "./client";
import type { LivePayload, NotificationLivePayload } from "./types";

type SocketStatus = "idle" | "connecting" | "authenticating" | "connected" | "closed" | "error";

type Options = {
  token: string;
  handles: string;
  replay: number;
  notifications?: boolean;
};

export function useIntelSocket({ token, handles, replay, notifications = false }: Options) {
  const [status, setStatus] = useState<SocketStatus>("idle");
  const [events, setEvents] = useState<LivePayload[]>([]);
  const [notificationEvents, setNotificationEvents] = useState<NotificationLivePayload[]>([]);
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null);
  const socketRef = useRef<ReconnectingWebSocket | null>(null);

  useEffect(() => {
    if (!token) {
      setStatus("idle");
      setEvents([]);
      setNotificationEvents([]);
      setLastMessageAt(null);
      return;
    }

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
      }
    });

    ws.addEventListener("close", () => setStatus("closed"));
    ws.addEventListener("error", () => setStatus("error"));

    return () => {
      socketRef.current = null;
      ws.close();
    };
  }, [token, handles, replay, notifications]);

  return { status, events, notifications: notificationEvents, lastMessageAt };
}

function normalizeHandles(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim().replace(/^@/, "").toLowerCase())
    .filter(Boolean);
}
