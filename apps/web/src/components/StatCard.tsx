import type { ReactNode } from "react";

import { cx } from "../lib/cx";

interface StatCardProps {
  label: string;
  value: ReactNode;
  /** Small clarification under the value, e.g. "news coverage measurement". */
  hint?: ReactNode;
  /** Signed change rendered with an arrow; null hides it. */
  delta?: number | null;
  deltaSuffix?: string;
  /** Higher-is-better vs lower-is-better affects only the arrow colour. */
  deltaPolarity?: "up-good" | "down-good" | "neutral";
  icon?: ReactNode;
  loading?: boolean;
  className?: string;
}

/**
 * A single headline number.
 *
 * Every StatCard carries a `hint`. For aggregate language metrics the caller
 * should pass the "news coverage measurement" wording so the card can never be
 * read as an investor-sentiment or price statistic.
 */
export function StatCard({
  label,
  value,
  hint,
  delta,
  deltaSuffix,
  deltaPolarity = "neutral",
  icon,
  loading = false,
  className,
}: StatCardProps) {
  const deltaTone =
    delta === null || delta === undefined || deltaPolarity === "neutral"
      ? "text-slate-600"
      : (delta >= 0) === (deltaPolarity === "up-good")
        ? "text-emerald-700"
        : "text-rose-700";

  return (
    <div className={cx("rounded-md border border-slate-200 bg-white p-4", className)}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
        {icon ? (
          <span className="text-slate-400" aria-hidden="true">
            {icon}
          </span>
        ) : null}
      </div>

      {loading ? (
        <div className="mt-2 h-7 w-2/3 animate-pulse rounded bg-slate-200 motion-reduce:animate-none" />
      ) : (
        <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight text-slate-900">
          {value}
        </p>
      )}

      <div className="mt-1 flex flex-wrap items-baseline gap-2">
        {delta !== null && delta !== undefined ? (
          <span className={cx("text-xs font-medium tabular-nums", deltaTone)}>
            {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(2)}
            {deltaSuffix ?? ""}
          </span>
        ) : null}
        {hint ? <span className="text-xs text-slate-500">{hint}</span> : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline coverage-measurement tag
// ---------------------------------------------------------------------------

/**
 * The label that must accompany aggregate language numbers. Rendered as a
 * small tag next to charts and stat groups.
 */
export function CoverageTag({ className }: { className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full border border-brand-300 bg-brand-50 px-2 py-0.5 text-[0.65rem] font-medium uppercase tracking-wide text-brand-800",
        className,
      )}
      title="These numbers measure language in published coverage. They are not investor sentiment."
    >
      <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path d="M4 3a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2H4Zm1 4h6v2H5V7Zm0 4h10v2H5v-2Z" />
      </svg>
      coverage measurement
    </span>
  );
}
