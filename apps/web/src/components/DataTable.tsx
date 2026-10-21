import { useMemo, useState, type ReactNode } from "react";

import { cx } from "../lib/cx";

export interface Column<T> {
  /** Stable key; also used as the sort key when `sortValue` is provided. */
  key: string;
  header: string;
  /** Cell renderer. */
  render: (row: T) => ReactNode;
  /** Return a comparable value to make this column sortable. */
  sortValue?: (row: T) => string | number | null;
  align?: "left" | "right" | "center";
  /** Applied to both th and td, e.g. "w-32" or "hidden md:table-cell". */
  className?: string;
  /** Short description surfaced via the column header's title attribute. */
  description?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  /** Announced to screen readers and printed above the table. */
  caption: string;
  /** Hide the caption visually but keep it for assistive tech. Default false. */
  captionVisible?: boolean;
  onRowClick?: (row: T) => void;
  /** Default sort column key. */
  initialSortKey?: string;
  initialSortDirection?: "asc" | "desc";
  emptyState?: ReactNode;
  className?: string;
  /** Highlight a row, e.g. because it is a duplicate. */
  rowClassName?: (row: T) => string | undefined;
}

/**
 * A real semantic table with keyboard-sortable headers.
 *
 * Deliberately not a virtualised grid: the corpus pages are small, and a real
 * table gives us scope="col"/"row", caption, and native keyboard navigation for
 * free. Sorting is a button inside <th>, reachable by Tab and fired by Enter.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  captionVisible = false,
  onRowClick,
  initialSortKey,
  initialSortDirection = "asc",
  emptyState,
  className,
  rowClassName,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(initialSortKey ?? null);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">(initialSortDirection);

  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;
    const column = columns.find((candidate) => candidate.key === sortKey);
    if (!column?.sortValue) return rows;
    const sortValue = column.sortValue;

    return [...rows].sort((a, b) => {
      const left = sortValue(a);
      const right = sortValue(b);
      if (left === null && right === null) return 0;
      if (left === null) return 1;
      if (right === null) return -1;
      let comparison: number;
      if (typeof left === "number" && typeof right === "number") {
        comparison = left - right;
      } else {
        comparison = String(left).localeCompare(String(right), undefined, { numeric: true });
      }
      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [rows, columns, sortKey, sortDirection]);

  function toggleSort(key: string) {
    if (sortKey === key) {
      setSortDirection((previous) => (previous === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("asc");
    }
  }

  if (rows.length === 0 && emptyState) {
    return <>{emptyState}</>;
  }

  return (
    <div className={cx("overflow-x-auto rounded-md border border-slate-200", className)}>
      <table className="min-w-full border-collapse text-sm">
        <caption className={captionVisible ? "px-3 py-2 text-left text-xs text-slate-600" : "sr-only"}>
          {caption}
        </caption>
        <thead className="bg-slate-50">
          <tr>
            {columns.map((column) => {
              const sortable = Boolean(column.sortValue);
              const active = sortKey === column.key;
              return (
                <th
                  key={column.key}
                  scope="col"
                  title={column.description}
                  className={cx(
                    "border-b border-slate-200 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-600",
                    column.align === "right" ? "text-right" : column.align === "center" ? "text-center" : "text-left",
                    column.className,
                  )}
                  aria-sort={active ? (sortDirection === "asc" ? "ascending" : "descending") : sortable ? "none" : undefined}
                >
                  {sortable ? (
                    <button
                      type="button"
                      onClick={() => toggleSort(column.key)}
                      className={cx(
                        "inline-flex items-center gap-1 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-1",
                        active && "text-brand-800",
                      )}
                    >
                      {column.header}
                      <span aria-hidden="true" className="text-[0.6rem]">
                        {active ? (sortDirection === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                      <span className="sr-only">
                        {active
                          ? `, sorted ${sortDirection === "asc" ? "ascending" : "descending"}, activate to reverse`
                          : ", activate to sort"}
                      </span>
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cx(
                "border-b border-slate-100 last:border-b-0",
                onRowClick && "cursor-pointer hover:bg-slate-50",
                rowClassName?.(row),
              )}
            >
              {columns.map((column, index) => (
                <td
                  key={column.key}
                  className={cx(
                    "px-3 py-2 align-top text-slate-800",
                    column.align === "right" ? "text-right" : column.align === "center" ? "text-center" : "text-left",
                    column.className,
                  )}
                >
                  {onRowClick && index === 0 ? (
                    // The whole row is clickable, but keyboard users need a real
                    // control. A button in the first cell provides that.
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onRowClick(row);
                      }}
                      className="text-left font-medium text-brand-800 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-1"
                    >
                      {column.render(row)}
                    </button>
                  ) : (
                    column.render(row)
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
