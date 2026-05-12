import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SearchData } from "../../api/types";
import { EvidenceDetailDrawer } from "../EvidenceDetailDrawer";

afterEach(() => cleanup());

describe("SearchQueryDrawer", () => {
  it("renders all loaded search items without the old eight item cap", () => {
    render(
      <EvidenceDetailDrawer
        mode="query"
        query="btc"
        data={searchData(10)}
        isFetching={false}
        hasMore={false}
        isFetchingNextPage={false}
        onLoadMore={vi.fn()}
      />,
    );

    expect(screen.getAllByText(/Search result /)).toHaveLength(10);
    expect(screen.queryByText("total")).not.toBeInTheDocument();
  });

  it("calls onLoadMore when more pages are available", () => {
    const onLoadMore = vi.fn();
    render(
      <EvidenceDetailDrawer
        mode="query"
        query="btc"
        data={searchData(2, true)}
        isFetching={false}
        hasMore={true}
        isFetchingNextPage={false}
        onLoadMore={onLoadMore}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Load more" }));

    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });
});

function searchData(count: number, hasMore = false): SearchData {
  return {
    query: { kind: "text", text: "btc", scope: "all" },
    page: { returned_count: count, has_more: hasMore, next_cursor: hasMore ? "cursor" : null },
    target_candidates: [],
    items: Array.from({ length: count }, (_, index) => ({
      event: {
        event_id: `event-${index}`,
        received_at_ms: 1_777_746_000_000 + index,
        author_handle: "searcher",
        text_clean: `Search result ${index}`,
        canonical_url: null,
      },
      match_type: "lexical",
      score: 0.5,
      match_reasons: ["fts"],
      target: null,
      route_scores: { lexical: 0.5 },
    })),
  };
}
