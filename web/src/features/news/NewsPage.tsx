import type { NewsRow } from "@shared/model/newsIntel";
import { newsItemPath, newsPath } from "@shared/routing/paths";
import * as PageState from "@shared/ui/PageState";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import "./news.css";
import { NewsItemEvidencePage } from "./ui/NewsItemEvidencePage";
import { NewsTape } from "./ui/NewsTape";
import { NEWS_PAGE_SIZE, useNewsItemWithToken, useNewsPageWithToken } from "./useNewsPage";

type NewsPageProps = {
  token: string;
  newsItemId?: string | null;
};

const EMPTY_NEWS_ROWS: NewsRow[] = [];
type TokenMode = "with-token" | "no-token";
type SignalFilter = "all" | "bullish" | "bearish" | "neutral";

export function NewsPage({ token, newsItemId = null }: NewsPageProps) {
  if (newsItemId) return <NewsItemRoute newsItemId={newsItemId} token={token} />;
  return <NewsQueueRoute token={token} />;
}

function NewsQueueRoute({ token }: { token: string }) {
  const navigate = useNavigate();
  const [tokenMode, setTokenMode] = useState<TokenMode>("with-token");
  const [signalFilter, setSignalFilter] = useState<SignalFilter>("all");
  const [minScore, setMinScore] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [cursorStack, setCursorStack] = useState<Array<string | null>>([null]);
  const cursor = cursorStack[cursorStack.length - 1] ?? null;
  const query = useNewsPageWithToken(token, {
    cursor,
    has_token: tokenMode === "with-token",
    limit: NEWS_PAGE_SIZE,
    min_score: minScore,
    q: searchQuery.trim() || null,
    signal: signalFilter === "all" ? null : signalFilter,
  });
  const rows = query.data?.items ?? EMPTY_NEWS_ROWS;
  const resetCursor = () => setCursorStack([null]);

  return (
    <section className="radar-panel news-panel news-queue-shell" aria-label="News intel">
      <div aria-label="News intel page container" className="news-table-wrap">
        <div className="news-compact-controls" aria-label="News filters">
          <div className="news-token-mode" aria-label="Token mode">
            <button
              aria-pressed={tokenMode === "with-token"}
              type="button"
              onClick={() => {
                setTokenMode("with-token");
                resetCursor();
              }}
            >
              有 Token
            </button>
            <button
              aria-pressed={tokenMode === "no-token"}
              type="button"
              onClick={() => {
                setTokenMode("no-token");
                resetCursor();
              }}
            >
              无 Token
            </button>
          </div>
          <div className="news-signal-controls" aria-label="Signal filters">
            {(["all", "bullish", "bearish", "neutral"] as const).map((value) => (
              <button
                aria-pressed={signalFilter === value}
                key={value}
                type="button"
                onClick={() => {
                  setSignalFilter(value);
                  resetCursor();
                }}
              >
                {signalFilterLabel(value)}
              </button>
            ))}
            <button
              aria-pressed={minScore === 70}
              type="button"
              onClick={() => {
                setMinScore((current) => (current === 70 ? null : 70));
                resetCursor();
              }}
            >
              ≥70
            </button>
            <label className="news-search-filter">
              <span>Search</span>
              <input
                aria-label="Search news"
                value={searchQuery}
                onChange={(event) => {
                  setSearchQuery(event.target.value);
                  resetCursor();
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
              if (nextCursor) setCursorStack((stack) => [...stack, nextCursor]);
            }}
            onPrevious={() =>
              setCursorStack((stack) => (stack.length > 1 ? stack.slice(0, -1) : stack))
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
            hint="No provider signal rows match the current filters."
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

function signalFilterLabel(value: SignalFilter): string {
  if (value === "bullish") return "利好";
  if (value === "bearish") return "利空";
  if (value === "neutral") return "中性";
  return "全部";
}
