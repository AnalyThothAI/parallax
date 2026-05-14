import { tokenKey } from "@lib/format";
import type { ScopeKey, TokenFlowItem, WindowKey } from "@lib/types";
import { RadarControls } from "@shared/ui/RadarControls";
import { RemoteState } from "@shared/ui/RemoteState";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  type ColumnDef,
  type SortDirection,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { useMemo, useState } from "react";

import { TokenRadarRow } from "./TokenRadarRow";

type TokenRadarTableProps = {
  items: TokenFlowItem[];
  selectedKey: string | null;
  scope: ScopeKey;
  windowKey: WindowKey;
  isLoading: boolean;
  error?: Error | null;
  onSelect: (item: TokenFlowItem) => void;
  onOpenSearch: (item: TokenFlowItem) => void;
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
    onOpenSearch,
    onScopeChange,
    onWindowChange,
  } = props;
  const resultLabel = `${items.length} live ${items.length === 1 ? "case" : "cases"}`;
  const columns = useMemo<ColumnDef<TokenFlowItem>[]>(() => tokenRadarColumns(), []);
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
        {isLoading ? <RadarSkeleton /> : null}
        {error ? <RemoteState.Error error={`Token Radar 暂不可用 · ${error.message}`} /> : null}
        {!isLoading && !error && items.length === 0 ? (
          <RemoteState.Empty title="当前窗口暂无可交易 token 热度" />
        ) : null}
        {!isLoading && !error && items.length ? (
          <div className="radar-data-table">
            <div>
              {table.getHeaderGroups().map((headerGroup) => (
                <div className="token-radar-head" key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <div
                      aria-sort={ariaSort(header.column.getIsSorted())}
                      className={`radar-head-cell ${header.column.id}`}
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
                return (
                  <TokenRadarRow
                    key={row.id}
                    item={row.original}
                    selected={selectedKey === key}
                    onOpenSearch={onOpenSearch}
                    onSelect={onSelect}
                  />
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function tokenRadarColumns(): ColumnDef<TokenFlowItem>[] {
  return [
    {
      id: "case",
      header: "Token case",
      accessorFn: (item) => item.identity.symbol ?? tokenKey(item),
    },
    {
      id: "social",
      header: "Social",
      accessorFn: (item) => item.flow.mentions,
    },
    {
      id: "why",
      header: "Why now",
      accessorFn: (item) => item.discussion_quality.informative_post_count,
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
    },
    {
      id: "score",
      header: "Score",
      accessorFn: (item) => item.opportunity.score,
    },
    {
      id: "listed",
      header: "Listed",
      accessorFn: (item) =>
        item.radar?.listed_at_ms ?? item.radar?.computed_at_ms ?? item.flow.window_end_ms ?? 0,
    },
  ];
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

function ariaSort(direction: false | SortDirection): "ascending" | "descending" | "none" {
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
