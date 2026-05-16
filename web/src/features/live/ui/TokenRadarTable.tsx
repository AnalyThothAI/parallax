import { tokenKey } from "@lib/format";
import type { ScopeKey, TokenFlowItem, WindowKey } from "@lib/types";
import { buildTokenRadarCompactCase } from "@shared/model/tokenRadarCompactCase";
import { RadarControls } from "@shared/ui/RadarControls";
import { RemoteState } from "@shared/ui/RemoteState";
import { ObsidianTokenMark } from "@shared/ui/case-file";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  type ColumnDef,
  type SortDirection,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table";
import clsx from "clsx";
import {
  ArrowDown,
  ArrowDownRight,
  ArrowUp,
  ArrowUpRight,
  ChevronsUpDown,
  Minus,
} from "lucide-react";
import { Fragment, useMemo, useState, type KeyboardEvent } from "react";

type TokenRadarTableProps = {
  items: TokenFlowItem[];
  selectedKey: string | null;
  scope: ScopeKey;
  windowKey: WindowKey;
  isLoading: boolean;
  error?: Error | null;
  onSelect: (item: TokenFlowItem) => void;
  onScopeChange: (scope: ScopeKey) => void;
  onWindowChange: (window: WindowKey) => void;
};

export function TokenRadarTable(props: TokenRadarTableProps) {
  const {
    items,
    selectedKey,
    scope,
    windowKey,
    isLoading,
    error,
    onSelect,
    onScopeChange,
    onWindowChange,
  } = props;
  const showLoading = !error && (isLoading || items.length === 0);
  const resultLabel = showLoading
    ? "loading"
    : `${items.length} live ${items.length === 1 ? "case" : "cases"}`;
  const columns = useMemo<ColumnDef<TokenFlowItem>[]>(
    () => tokenRadarColumns({ onSelect, selectedKey }),
    [onSelect, selectedKey],
  );
  const [sorting, setSorting] = useState<SortingState>([{ id: "score", desc: true }]);
  const table = useReactTable({
    data: items,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (item, index) =>
      `${tokenKey(item)}:${item.radar?.computed_at_ms ?? item.flow.window_end_ms ?? "row"}:${index}`,
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: { sorting },
  });

  return (
    <section className="radar-panel" aria-label="Token Radar">
      <header className="radar-toolbar">
        <div className="radar-scan-title">
          <h2>Token Radar</h2>
          <span>{resultLabel}</span>
        </div>
        <div className="toolbar-controls" aria-label="token radar scan controls">
          <RadarControls
            scope={scope}
            windowKey={windowKey}
            onScopeChange={onScopeChange}
            onWindowChange={onWindowChange}
          />
        </div>
      </header>

      <div className="token-radar-table">
        {showLoading ? <RadarSkeleton /> : null}
        {error ? <RemoteState.Error error={`Token Radar 暂不可用 · ${error.message}`} /> : null}
        {!showLoading && !error && items.length ? (
          <div className="radar-data-table">
            <div>
              {table.getHeaderGroups().map((headerGroup) => (
                <div className="token-radar-head" key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <div
                      className={`radar-head-cell ${header.column.id}`}
                      data-sort={sortState(header.column.getIsSorted())}
                      key={header.id}
                    >
                      <button
                        aria-label={`Sort by ${headerLabel(header.column.id).toLowerCase()}`}
                        className="radar-sort-button"
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        <span>
                          {flexRender(header.column.columnDef.header, header.getContext())}
                        </span>
                        <SortIcon direction={header.column.getIsSorted()} />
                      </button>
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <div>
              {table.getRowModel().rows.map((row) => {
                const key = tokenKey(row.original);
                const tokenCase = buildTokenRadarCompactCase(row.original);
                return (
                  <Fragment key={row.id}>
                    {/* eslint-disable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */}
                    <article
                      aria-label={`Token Radar item ${tokenCase.label}`}
                      className={clsx("token-radar-row", selectedKey === key && "selected")}
                      tabIndex={0}
                      onClick={() => onSelect(row.original)}
                      onKeyDown={(event) => handleRowKeyDown(event, row.original, onSelect)}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <div className={`token-radar-cell ${cell.column.id}`} key={cell.id}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </div>
                      ))}
                    </article>
                    {/* eslint-enable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */}
                  </Fragment>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

type TokenRadarColumnDeps = {
  onSelect: (item: TokenFlowItem) => void;
  selectedKey: string | null;
};

function tokenRadarColumns({
  onSelect,
  selectedKey,
}: TokenRadarColumnDeps): ColumnDef<TokenFlowItem>[] {
  return [
    {
      id: "case",
      header: "Token case",
      accessorFn: (item) => item.identity.symbol ?? tokenKey(item),
      cell: ({ row }) => (
        <TokenCaseCell
          item={row.original}
          selected={selectedKey === tokenKey(row.original)}
          onSelect={onSelect}
        />
      ),
    },
    {
      id: "social",
      header: "Social",
      accessorFn: (item) => item.flow.mentions,
      cell: ({ row }) => <SocialCell item={row.original} />,
    },
    {
      id: "why",
      header: "Why now",
      accessorFn: (item) => item.discussion_quality.informative_post_count,
      cell: ({ row }) => <WhyNowCell item={row.original} />,
    },
    {
      id: "market",
      header: "Market",
      accessorFn: (item) =>
        item.market.market_cap ??
        item.market.price ??
        item.market.liquidity ??
        item.market.volume_24h ??
        item.market.holder_count ??
        -1,
      cell: ({ row }) => <MarketCell item={row.original} />,
    },
    {
      id: "score",
      header: "Score",
      accessorFn: (item) => item.opportunity.score,
      cell: ({ row }) => <ScoreCell item={row.original} />,
    },
    {
      id: "listed",
      header: "Listed",
      accessorFn: (item) =>
        item.radar?.listed_at_ms ?? item.radar?.computed_at_ms ?? item.flow.window_end_ms ?? 0,
      cell: ({ row }) => <ListedCell item={row.original} />,
    },
  ];
}

function handleRowKeyDown(
  event: KeyboardEvent<HTMLElement>,
  item: TokenFlowItem,
  onSelect: (item: TokenFlowItem) => void,
) {
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }
  event.preventDefault();
  onSelect(item);
}

function TokenCaseCell({
  item,
  selected,
  onSelect,
}: {
  item: TokenFlowItem;
  selected: boolean;
  onSelect: (item: TokenFlowItem) => void;
}) {
  const tokenCase = buildTokenRadarCompactCase(item);
  return (
    <div className="radar-case-cell" data-case-section="identity">
      {tokenCase.logoUrl ? (
        <img alt="" className="radar-token-logo" src={tokenCase.logoUrl} />
      ) : (
        <ObsidianTokenMark label={tokenCase.label} tone={tokenCase.markTone} />
      )}
      <span className="radar-case-copy">
        <span className="radar-case-symbol-row">
          <button
            aria-label={`Open token item ${tokenCase.label}`}
            className={clsx("radar-case-button", selected && "selected")}
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onSelect(item);
            }}
          >
            <strong>{tokenCase.label}</strong>
          </button>
          {tokenCase.externalLinks.length ? (
            <nav className="radar-case-links" aria-label={`External links for ${tokenCase.label}`}>
              {tokenCase.externalLinks.map((link) => (
                <a
                  className={clsx("radar-case-link", link.tone)}
                  href={link.href}
                  key={`${link.label}:${link.href}`}
                  rel="noreferrer"
                  target="_blank"
                  onClick={(event) => event.stopPropagation()}
                >
                  {link.label}
                </a>
              ))}
            </nav>
          ) : null}
        </span>
        <span className="radar-case-meta">{tokenCase.subtitle}</span>
      </span>
    </div>
  );
}

function SocialCell({ item }: { item: TokenFlowItem }) {
  const tokenCase = buildTokenRadarCompactCase(item);
  return (
    <span className="radar-fact social-fact" data-case-section="social">
      <b>{tokenCase.socialFact}</b>
      <em>{tokenCase.socialDetail}</em>
    </span>
  );
}

function WhyNowCell({ item }: { item: TokenFlowItem }) {
  const tokenCase = buildTokenRadarCompactCase(item);
  return (
    <span className="radar-fact narrative-fact" data-case-section="why-now">
      <b>{tokenCase.narrative.value}</b>
      <em>{tokenCase.narrative.detail}</em>
    </span>
  );
}

function MarketCell({ item }: { item: TokenFlowItem }) {
  const tokenCase = buildTokenRadarCompactCase(item);
  return (
    <span className="radar-fact market-fact" data-radar-metric="market">
      <span className="market-primary-line">
        <b className="market-primary-value">{tokenCase.market.value}</b>
        <span className={clsx("market-move", tokenCase.marketMove.direction)}>
          {tokenCase.marketMove.direction === "up" ? <ArrowUpRight aria-hidden /> : null}
          {tokenCase.marketMove.direction === "down" ? <ArrowDownRight aria-hidden /> : null}
          {tokenCase.marketMove.direction === "flat" ? <Minus aria-hidden /> : null}
          <b>{tokenCase.marketMove.value}</b>
        </span>
      </span>
      <span className="market-stats" aria-label={tokenCase.market.detail}>
        {tokenCase.market.stats.length ? (
          tokenCase.market.stats.map((stat) => (
            <span className={clsx("market-stat", stat.tone)} key={stat.key} title={stat.status}>
              <span>{stat.label}</span>
              <b>{stat.value}</b>
            </span>
          ))
        ) : (
          <em>market data unavailable</em>
        )}
      </span>
    </span>
  );
}

function ScoreCell({ item }: { item: TokenFlowItem }) {
  const tokenCase = buildTokenRadarCompactCase(item);
  return (
    <span className="radar-score-cell" data-case-section="score">
      <span className="radar-score">{tokenCase.score}</span>
    </span>
  );
}

function ListedCell({ item }: { item: TokenFlowItem }) {
  const tokenCase = buildTokenRadarCompactCase(item);
  return (
    <span className="radar-listed-action-cell" data-case-section="action">
      <span className="radar-fact listed-fact" data-radar-metric="listed">
        <b>{tokenCase.listed.value}</b>
        <em>{tokenCase.listed.detail}</em>
      </span>
    </span>
  );
}

function headerLabel(columnId: string): string {
  const labels: Record<string, string> = {
    case: "token case",
    social: "social",
    why: "why now",
    market: "market",
    listed: "listed",
    score: "score",
  };
  return labels[columnId] ?? columnId;
}

function sortState(direction: false | SortDirection): "ascending" | "descending" | "none" {
  if (direction === "asc") {
    return "ascending";
  }
  if (direction === "desc") {
    return "descending";
  }
  return "none";
}

function SortIcon({ direction }: { direction: false | SortDirection }) {
  if (direction === "asc") {
    return <ArrowUp aria-hidden />;
  }
  if (direction === "desc") {
    return <ArrowDown aria-hidden />;
  }
  return <ChevronsUpDown aria-hidden />;
}

function RadarSkeleton() {
  return (
    <div className="radar-skeleton" aria-label="loading token radar">
      {Array.from({ length: 8 }, (_, index) => (
        <span key={index} />
      ))}
    </div>
  );
}
