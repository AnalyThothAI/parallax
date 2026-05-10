import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { NotificationItem, NotificationSummary } from "../api/types";

import { NotificationBell } from "./NotificationBell";
import { NotificationDrawer } from "./NotificationDrawer";
import { WatchlistNotificationDot } from "./WatchlistNotificationDot";

afterEach(() => cleanup());

const summary: NotificationSummary = {
  subscriber_key: "local",
  unread_count: 3,
  high_unread_count: 1,
  critical_unread_count: 0,
  highest_unread_severity: "high",
  account_unread_counts: { toly: 2 },
};

const notification: NotificationItem = {
  notification_id: "n1",
  dedup_key: "hot:pepe",
  rule_id: "hot_quality_token_5m",
  severity: "high",
  title: "PEPE heat",
  body: "Heat 88, quality 76",
  entity_type: "token",
  entity_key: "token:eth:pepe",
  author_handle: null,
  symbol: "PEPE",
  chain: "eth",
  address: "0xpepe",
  event_id: null,
  source_table: "token_flow",
  source_id: "token:eth:pepe",
  occurrence_count: 1,
  first_seen_at_ms: 1_700_000_000_000,
  last_seen_at_ms: 1_700_000_000_000,
  created_at_ms: 1_700_000_000_000,
  updated_at_ms: 1_700_000_000_000,
  read_at_ms: null,
  payload: { social_heat_score: 88 },
  channels: ["in_app"],
};

describe("notification center components", () => {
  it("renders bell unread count and severity state", () => {
    const onClick = vi.fn();

    render(<NotificationBell summary={summary} open={false} onClick={onClick} />);
    fireEvent.click(screen.getByRole("button", { name: /notifications/i }));

    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /notifications/i })).toHaveClass("has-high");
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("renders drawer actions for individual and bulk read state", () => {
    const onClose = vi.fn();
    const onMarkAllRead = vi.fn();
    const onMarkRead = vi.fn();
    const onOpenNotification = vi.fn();

    render(
      <NotificationDrawer
        loading={false}
        notifications={[notification]}
        open
        summary={summary}
        onClose={onClose}
        onMarkAllRead={onMarkAllRead}
        onMarkRead={onMarkRead}
        onOpenNotification={onOpenNotification}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /open PEPE heat/i }));
    fireEvent.click(screen.getByRole("button", { name: /mark PEPE heat read/i }));
    fireEvent.click(screen.getByRole("button", { name: /mark all read/i }));
    fireEvent.click(screen.getByRole("button", { name: /close notifications/i }));

    expect(screen.getByText("PEPE heat")).toBeInTheDocument();
    expect(onOpenNotification).toHaveBeenCalledWith(notification);
    expect(onMarkRead).toHaveBeenCalledWith("n1");
    expect(onMarkAllRead).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("only shows watchlist dot when the account has unread notifications", () => {
    const { rerender } = render(<WatchlistNotificationDot count={2} />);

    expect(screen.getByText("2")).toBeInTheDocument();

    rerender(<WatchlistNotificationDot count={0} />);

    expect(screen.queryByText("2")).not.toBeInTheDocument();
  });
});
