import { websocketUrl } from "@lib/api/client";
import type { LiveMarketUpdatePayload, NotificationLivePayload } from "@lib/types";
import {
  patchTokenCaseLiveMarketUpdate,
  patchTokenRadarLiveMarketUpdate,
} from "@shared/query/patchMarketUpdate";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import ReconnectingWebSocket from "reconnecting-websocket";

import { isTarget, normalizeMarketTargets, targetFromKey, targetKey } from "./marketTargets";
import { idleSocketSnapshot, SocketContext, type SocketContextValue } from "./socketContext";
import type { MarketTargetRef, NormalizedMarketTarget, SocketSnapshot } from "./socketTypes";

type IntelSocketProviderProps = {
  token: string;
  handles: string;
  notifications?: boolean;
  children: ReactNode;
};

export function IntelSocketProvider({
  token,
  handles,
  notifications = false,
  children,
}: IntelSocketProviderProps) {
  const queryClient = useQueryClient();
  const [snapshot, setSnapshot] = useState<SocketSnapshot>(idleSocketSnapshot);
  const [marketTargetCounts, setMarketTargetCounts] = useState<Record<string, number>>({});
  const socketRef = useRef<ReconnectingWebSocket | null>(null);
  const readyRef = useRef(false);
  const subscribeRef = useRef({
    handlesKey: "[]",
    marketTargetKey: "[]",
    notifications: false,
  });
  const handlesKey = useMemo(() => JSON.stringify(normalizeHandles(handles)), [handles]);
  const marketTargets = useMemo(
    () => Object.keys(marketTargetCounts).map(targetFromKey).filter(isTarget),
    [marketTargetCounts],
  );
  const marketTargetKey = useMemo(() => JSON.stringify(marketTargets), [marketTargets]);
  const subscriptionKey = useMemo(
    () => JSON.stringify({ handlesKey, marketTargetKey, notifications }),
    [handlesKey, marketTargetKey, notifications],
  );
  subscribeRef.current = { handlesKey, marketTargetKey, notifications };

  const sendSubscribe = useCallback(() => {
    const socket = socketRef.current;
    if (!socket || !readyRef.current) {
      return;
    }
    const subscription = subscribeRef.current;
    socket.send(
      JSON.stringify({
        type: "subscribe",
        handles: JSON.parse(subscription.handlesKey) as string[],
        notifications: subscription.notifications,
        market_targets: JSON.parse(subscription.marketTargetKey) as NormalizedMarketTarget[],
        replay: 0,
      }),
    );
  }, []);

  useEffect(() => {
    sendSubscribe();
  }, [sendSubscribe, subscriptionKey]);

  useEffect(() => {
    if (!token) {
      readyRef.current = false;
      setSnapshot(idleSocketSnapshot);
      return;
    }

    const ws = new ReconnectingWebSocket(websocketUrl(), [], {
      connectionTimeout: 4_000,
      maxRetries: Infinity,
      maxReconnectionDelay: 8_000,
      minReconnectionDelay: 800,
    });
    socketRef.current = ws;
    readyRef.current = false;
    setSnapshot((current) => ({ ...current, status: "connecting" }));

    ws.addEventListener("open", () => {
      setSnapshot((current) => ({ ...current, status: "authenticating" }));
      ws.send(JSON.stringify({ type: "auth", token }));
    });

    ws.addEventListener("message", (message) => {
      setSnapshot((current) => ({ ...current, lastMessageAt: Date.now() }));
      const payload = JSON.parse(String(message.data)) as { type?: string };
      if (payload.type === "ready") {
        readyRef.current = true;
        setSnapshot((current) => ({ ...current, status: "connected" }));
        sendSubscribe();
        return;
      }
      if (payload.type === "notification") {
        setSnapshot((current) => ({
          ...current,
          notificationItems: [
            payload as NotificationLivePayload,
            ...current.notificationItems,
          ].slice(0, 50),
        }));
        return;
      }
      if (payload.type === "live_market_update") {
        const update = payload as LiveMarketUpdatePayload;
        patchTokenRadarLiveMarketUpdate(queryClient, update);
        patchTokenCaseLiveMarketUpdate(queryClient, update);
      }
    });

    ws.addEventListener("close", () => {
      readyRef.current = false;
      setSnapshot((current) => ({ ...current, status: "closed" }));
    });
    ws.addEventListener("error", () => setSnapshot((current) => ({ ...current, status: "error" })));

    return () => {
      readyRef.current = false;
      socketRef.current = null;
      ws.close();
    };
  }, [queryClient, sendSubscribe, token]);

  const registerMarketTargets = useCallback((targets: MarketTargetRef[]) => {
    const normalized = normalizeMarketTargets(targets);
    if (!normalized.length) {
      return () => undefined;
    }
    setMarketTargetCounts((current) => {
      const next = { ...current };
      for (const target of normalized) {
        const key = targetKey(target);
        next[key] = (next[key] ?? 0) + 1;
      }
      return next;
    });
    return () => {
      setMarketTargetCounts((current) => {
        const next = { ...current };
        for (const target of normalized) {
          const key = targetKey(target);
          const count = (next[key] ?? 0) - 1;
          if (count > 0) {
            next[key] = count;
          } else {
            delete next[key];
          }
        }
        return next;
      });
    };
  }, []);

  const value = useMemo<SocketContextValue>(
    () => ({ ...snapshot, registerMarketTargets }),
    [registerMarketTargets, snapshot],
  );

  return <SocketContext.Provider value={value}>{children}</SocketContext.Provider>;
}

function normalizeHandles(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim().replace(/^@/, "").toLowerCase())
    .filter(Boolean);
}
