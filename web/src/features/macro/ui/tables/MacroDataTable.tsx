import type { MacroModuleTable } from "@lib/types";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  type ColumnDef,
  type SortingFn,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";

import {
  buildMacroTableModel,
  compareMacroTableSortValues,
  type MacroTableRowModel,
} from "../../model/macroTableColumns";

import { MacroTableFrame } from "./MacroTableFrame";
import "./macroTables.css";

export function MacroDataTable({
  caption,
  state,
  table,
}: {
  caption: string;
  state?: "idle" | "loading";
  table: MacroModuleTable;
}) {
  const model = useMemo(() => buildMacroTableModel(table), [table]);
  const [sorting, setSorting] = useState<SortingState>([]);
  const columns = useMemo<ColumnDef<MacroTableRowModel>[]>(
    () =>
      model.columns.map((column) => ({
        id: column.id,
        accessorFn: (row) => row.cells[column.id]?.sortValue ?? undefined,
        cell: ({ row }) => row.original.cells[column.id]?.displayValue ?? "暂无",
        enableSorting: true,
        header: column.label,
        sortDescFirst: false,
        sortUndefined: "last",
        sortingFn: macroCellSorting,
      })),
    [model.columns],
  );
  const reactTable = useReactTable({
    columns,
    data: model.rows,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => row.id,
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: { sorting },
  });

  if (state === "loading") {
    return <TableState caption={caption} label="表格加载中" stateName="加载" />;
  }
  if (model.rows.length === 0) {
    return <TableState caption={caption} label="暂无表格行" stateName="空" />;
  }

  return (
    <MacroTableFrame caption={caption} minWidth={420} stickyFirstColumn>
      <table aria-label={caption} className="macro-data-table">
        <caption>{caption}</caption>
        <thead>
          {reactTable.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th
                  aria-sort={ariaSortValue(header.column.getIsSorted())}
                  key={header.id}
                  scope="col"
                >
                  <button
                    aria-label={`按${String(header.column.columnDef.header)}排序`}
                    type="button"
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    <span className="macro-table-sort-indicator" aria-hidden="true">
                      {sortIndicator(header.column.getIsSorted())}
                    </span>
                  </button>
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {reactTable.getRowModel().rows.map((row) => (
            <tr key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </MacroTableFrame>
  );
}

const macroCellSorting: SortingFn<MacroTableRowModel> = (left, right, columnId) =>
  compareMacroTableSortValues(
    left.original.cells[columnId]?.sortValue ?? null,
    right.original.cells[columnId]?.sortValue ?? null,
  );

function ariaSortValue(sortState: false | "asc" | "desc"): "ascending" | "descending" | "none" {
  if (sortState === "asc") {
    return "ascending";
  }
  if (sortState === "desc") {
    return "descending";
  }
  return "none";
}

function sortIndicator(sortState: false | "asc" | "desc"): string {
  if (sortState === "asc") {
    return "↑";
  }
  if (sortState === "desc") {
    return "↓";
  }
  return "↕";
}

function TableState({
  caption,
  label,
  stateName,
}: {
  caption: string;
  label: string;
  stateName: string;
}) {
  return (
    <div
      aria-label={`${caption}${stateName}状态`}
      className="macro-table-state-panel"
      role="status"
    >
      {label}
    </div>
  );
}
