import { tittyPulseFixture } from "@features/signal-lab/test/fixtures";
import { SignalPulseQueue } from "@features/signal-lab/ui/SignalPulseQueue";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("SignalPulseQueue", () => {
  it("renders wide case rows with score and primary action on the right", () => {
    vi.useFakeTimers();
    vi.setSystemTime(tittyPulseFixture.updated_at_ms + 2 * 60 * 60 * 1000 + 5_000);

    const onSelect = vi.fn();
    render(
      <SignalPulseQueue
        items={[tittyPulseFixture]}
        selectedItemId={tittyPulseFixture.candidate_id}
        onSelect={onSelect}
      />,
    );

    expect(screen.getByText("$TITTY")).toBeInTheDocument();
    expect(screen.getByText("热度很高，但流动性极浅且作者集中")).toBeInTheDocument();
    expect(screen.getByText("作者 3 · 头部60%")).toBeInTheDocument();
    expect(screen.getByText("提及 5 / 1h")).toBeInTheDocument();
    expect(screen.getByText("市场过期")).toBeInTheDocument();
    expect(screen.getByText("82")).toBeInTheDocument();
    expect(screen.getByText("热度分")).toBeInTheDocument();
    expect(screen.getByText("Agent：候选")).toBeInTheDocument();
    expect(screen.getByText("conf 0.35")).toBeInTheDocument();

    const idLine = screen.getByText("$TITTY").closest("div") as HTMLElement;
    expect(Array.from(idLine.children).map((child) => child.tagName.toLowerCase())).toEqual([
      "strong",
      "nav",
      "span",
    ]);
    expect(within(idLine).getByRole("link", { name: "GMGN" })).toHaveAttribute(
      "href",
      "https://gmgn.ai/sol/token/gTi4ZMMM2M7vQqZeetyQpWpjFr57zFZ7MCu4krypump",
    );
    expect(within(idLine).queryByText("2h前")).not.toBeInTheDocument();
    const side = screen.getByText("热度分").closest("div")?.parentElement as HTMLElement;
    expect(within(side).getByText("2h前")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "查看 $TITTY 详情" }));
    expect(onSelect).toHaveBeenCalledWith(tittyPulseFixture);
  });
});
