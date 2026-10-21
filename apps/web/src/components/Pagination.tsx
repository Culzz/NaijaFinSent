import { cx } from "../lib/cx";
import { formatNumber } from "../lib/format";

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
  /** Noun for the rows, e.g. "articles". */
  itemNoun?: string;
  className?: string;
}

const PAGE_SIZES = [10, 20, 50, 100];

/**
 * Offset pagination over the API's `{items,total,page,page_size}` envelope.
 *
 * Always states the range currently shown relative to the total, because
 * "page 3 of 11" hides how much corpus the user is actually reading.
 */
export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  itemNoun = "items",
  className,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = Math.min(Math.max(1, page), totalPages);
  const first = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const last = Math.min(currentPage * pageSize, total);

  const button =
    "inline-flex h-8 min-w-8 items-center justify-center rounded border px-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-40";

  return (
    <nav
      className={cx("flex flex-wrap items-center justify-between gap-3", className)}
      aria-label={`${itemNoun} pagination`}
    >
      <p className="text-xs text-slate-600" aria-live="polite">
        Showing <span className="font-medium tabular-nums">{formatNumber(first)}</span>–
        <span className="font-medium tabular-nums">{formatNumber(last)}</span> of{" "}
        <span className="font-medium tabular-nums">{formatNumber(total)}</span> {itemNoun}
      </p>

      <div className="flex items-center gap-2">
        {onPageSizeChange ? (
          <label className="flex items-center gap-1.5 text-xs text-slate-600">
            <span>Rows</span>
            <select
              value={pageSize}
              onChange={(event) => onPageSizeChange(Number(event.target.value))}
              className="rounded border border-slate-300 bg-white px-1.5 py-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
            >
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        <button
          type="button"
          onClick={() => onPageChange(1)}
          disabled={currentPage <= 1}
          aria-label="First page"
          className={cx(button, "border-slate-300 bg-white text-slate-700 hover:bg-slate-50")}
        >
          «
        </button>
        <button
          type="button"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage <= 1}
          className={cx(button, "border-slate-300 bg-white text-slate-700 hover:bg-slate-50")}
        >
          Previous
        </button>
        <span className="px-1 text-xs tabular-nums text-slate-600" aria-current="page">
          {currentPage} / {totalPages}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage >= totalPages}
          className={cx(button, "border-slate-300 bg-white text-slate-700 hover:bg-slate-50")}
        >
          Next
        </button>
        <button
          type="button"
          onClick={() => onPageChange(totalPages)}
          disabled={currentPage >= totalPages}
          aria-label="Last page"
          className={cx(button, "border-slate-300 bg-white text-slate-700 hover:bg-slate-50")}
        >
          »
        </button>
      </div>
    </nav>
  );
}
