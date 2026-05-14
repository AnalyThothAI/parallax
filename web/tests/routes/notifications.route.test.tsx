import { fireEvent, screen, waitFor } from "@testing-library/react";
import { mockNotificationRoute } from "@tests/msw/scenarios";
import { renderAppRoute } from "@tests/render/renderRoute";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { setupAppRouteTest } from "./routeTestSetup";

describe("notifications route shell", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  beforeEach(() => {
    setupAppRouteTest(mockNotificationRoute);
  });

  it("opens and closes the notification drawer from the topbar bell", async () => {
    renderAppRoute("/");

    const bell = await screen.findByRole("button", { name: "notifications" });
    await waitFor(() => expect(bell).toHaveTextContent("1"));

    fireEvent.click(bell);
    expect(
      await screen.findByRole("complementary", { name: "notification drawer" }),
    ).toBeInTheDocument();
    expect(screen.getByText("1 unread")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "open Signal Pulse" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "close notifications" }));
    expect(screen.queryByRole("complementary", { name: "notification drawer" })).toBeNull();
  });
});
