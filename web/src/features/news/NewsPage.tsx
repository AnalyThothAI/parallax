import { newsItemPath, newsPath } from "@shared/routing/paths";
import * as PageState from "@shared/ui/PageState";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import "./news.css";
import type { NewsFactRow } from "./model/newsFactViewModel";
import { NewsItemEvidencePage } from "./ui/NewsItemEvidencePage";
import { NewsTape } from "./ui/NewsTape";
import { NEWS_PAGE_SIZE, useNewsItemWithToken, useNewsPageWithToken } from "./useNewsPage";

type NewsPageProps = {
  token: string;
  newsItemId?: string | null;
};

const EMPTY_NEWS_ROWS: NewsFactRow[] = [];
type LifecycleFilter = "all" | "accepted" | "attention" | "rejected";
type NewsCursorState = {
  searchQuery: string;
  stack: Array<string | null>;
};

export function NewsPage({ token, newsItemId = null }: NewsPageProps) {
  if (newsItemId) return <NewsItemRoute newsItemId={newsItemId} token={token} />;
  return <NewsQueueRoute token={token} />;
}

function NewsQueueRoute({ token }: { token: string }) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [lifecycleFilter, setLifecycleFilter] = useState<LifecycleFilter>("all");
  const searchQuery = searchParams.get("q") ?? "";
  const [cursorState, setCursorState] = useState<NewsCursorState>(() => ({
    searchQuery,
    stack: [null],
  }));
  const cursorStack = cursorState.searchQuery === searchQuery ? cursorState.stack : [null];
  const cursor = cursorStack[cursorStack.length - 1] ?? null;
  const query = useNewsPageWithToken(token, {
    cursor,
    limit: NEWS_PAGE_SIZE,
    q: searchQuery.trim() || null,
    status: lifecycleFilter === "all" ? null : lifecycleFilter,
  });
  const rows = query.data?.items ?? EMPTY_NEWS_ROWS;
  const resetCursor = () => setCursorState({ searchQuery, stack: [null] });
  const updateSearchQuery = (value: string) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value.trim()) {
          next.set("q", value);
        } else {
          next.delete("q");
        }
        return next;
      },
      { replace: true },
    );
  };

  useEffect(() => {
    setCursorState((state) =>
      state.searchQuery === searchQuery ? state : { searchQuery, stack: [null] },
    );
  }, [searchQuery]);

  return (
    <section className="radar-panel news-panel news-queue-shell" aria-label="News intel">
      <div aria-label="News intel page container" className="news-table-wrap">
        <div className="news-compact-controls" aria-label="News filters">
          <div className="news-status-controls" aria-label="Lifecycle filters">
            {(["all", "accepted", "attention", "rejected"] as const).map((value) => (
              <button
                aria-pressed={lifecycleFilter === value}
                key={value}
                type="button"
                onClick={() => {
                  setLifecycleFilter(value);
                  resetCursor();
                }}
              >
                {lifecycleFilterLabel(value)}
              </button>
            ))}
            <label className="news-search-filter">
              <span>Search</span>
              <input
                aria-label="Search news"
                value={searchQuery}
                onChange={(event) => {
                  updateSearchQuery(event.target.value);
                }}
                placeholder="headline, token, source"
              />
            </label>
          </div>
          <NewsPager
            hasNextPage={Boolean(query.data?.next_cursor)}
            isFetching={query.isFetching}
            pageNumber={cursorStack.length}
            rowCount={rows.length}
            onNext={() => {
              const nextCursor = query.data?.next_cursor;
              if (nextCursor) {
                setCursorState((state) => {
                  const stack = state.searchQuery === searchQuery ? state.stack : [null];
                  return { searchQuery, stack: [...stack, nextCursor] };
                });
              }
            }}
            onPrevious={() =>
              setCursorState((state) => {
                const stack = state.searchQuery === searchQuery ? state.stack : [null];
                return { searchQuery, stack: stack.length > 1 ? stack.slice(0, -1) : stack };
              })
            }
          />
        </div>

        {query.isLoading && !rows.length ? (
          <PageState.Loading layout="panel" rows={8} label="loading news tape" />
        ) : null}
        {query.isError ? <PageState.Error error={query.error ?? "News unavailable"} /> : null}
        {!query.isLoading && !query.isError && !rows.length ? (
          <PageState.Empty
            title="No news rows"
            hint="No persisted news facts match the current filters."
          />
        ) : null}
        {!query.isLoading && !query.isError && rows.length ? (
          <PageState.Stale updating={query.isFetching && !query.isLoading}>
            <NewsTape rows={rows} onOpen={(newsId) => navigate(newsItemPath(newsId))} />
          </PageState.Stale>
        ) : null}
      </div>
    </section>
  );
}

function NewsPager({
  hasNextPage,
  isFetching,
  pageNumber,
  rowCount,
  onNext,
  onPrevious,
}: {
  hasNextPage: boolean;
  isFetching: boolean;
  pageNumber: number;
  rowCount: number;
  onNext: () => void;
  onPrevious: () => void;
}) {
  return (
    <nav className="news-pager" aria-label="News pagination">
      <button
        aria-label="Previous news page"
        className="news-page-button"
        disabled={pageNumber <= 1 || isFetching}
        type="button"
        onClick={onPrevious}
      >
        <ChevronLeft aria-hidden />
      </button>
      <span className="news-page-label">
        Page {pageNumber} · {rowCount}/{NEWS_PAGE_SIZE}
      </span>
      <button
        aria-label="Next news page"
        className="news-page-button"
        disabled={!hasNextPage || isFetching}
        type="button"
        onClick={onNext}
      >
        <ChevronRight aria-hidden />
      </button>
    </nav>
  );
}

function NewsItemRoute({ token, newsItemId }: { token: string; newsItemId: string }) {
  const query = useNewsItemWithToken(token, newsItemId);
  const item = query.data ?? null;
  return (
    <section className="radar-panel news-panel news-evidence-shell" aria-label="News item evidence">
      <header className="radar-toolbar news-toolbar">
        <Link className="news-back-link" to={newsPath()}>
          <ArrowLeft aria-hidden />
          Queue
        </Link>
        <div className="news-pagination" aria-label="news item status">
          <span>{query.isFetching ? "updating" : "live"}</span>
        </div>
      </header>
      {query.isLoading && !item ? (
        <PageState.Loading layout="panel" rows={8} label="loading news item" />
      ) : null}
      {query.isError ? <PageState.Error error={query.error ?? "News item unavailable"} /> : null}
      {!query.isLoading && !query.isError && !item ? (
        <PageState.Empty title="News item not found" />
      ) : null}
      {item ? (
        <PageState.Stale updating={query.isFetching}>
          <NewsItemEvidencePage item={item} />
        </PageState.Stale>
      ) : null}
    </section>
  );
}

function lifecycleFilterLabel(value: LifecycleFilter): string {
  if (value === "accepted") return "Accepted";
  if (value === "attention") return "Attention";
  if (value === "rejected") return "Rejected";
  return "All";
}
