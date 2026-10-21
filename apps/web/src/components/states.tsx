import type { ReactNode } from "react";

import { cx } from "../lib/cx";
import { isApiError } from "../lib/api";

// ---------------------------------------------------------------------------
// SectionHeader
// ---------------------------------------------------------------------------

interface SectionHeaderProps {
  title: string;
  /** Second line, often the "coverage measurement" clarification. */
  subtitle?: ReactNode;
  /** Right-hand controls (filters, granularity toggle). */
  actions?: ReactNode;
  /** Overline label rendered above the title. */
  eyebrow?: string;
  as?: "h1" | "h2" | "h3";
  className?: string;
  id?: string;
}

export function SectionHeader({
  title,
  subtitle,
  actions,
  eyebrow,
  as: Heading = "h2",
  className,
  id,
}: SectionHeaderProps) {
  return (
    <div className={cx("flex flex-wrap items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        {eyebrow ? (
          <p className="text-[0.7rem] font-semibold uppercase tracking-wider text-brand-700">
            {eyebrow}
          </p>
        ) : null}
        <Heading id={id} className="text-lg font-semibold tracking-tight text-slate-900">
          {title}
        </Heading>
        {subtitle ? (
          <div className="mt-1 max-w-3xl text-sm text-slate-600">{subtitle}</div>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// LoadingSkeleton
// ---------------------------------------------------------------------------

interface LoadingSkeletonProps {
  /** Render this many rows/bars. */
  rows?: number;
  variant?: "table" | "cards" | "chart" | "text" | "stat";
  label?: string;
  className?: string;
}

/**
 * Skeletons rather than spinners, so the layout does not jump when data lands.
 * `aria-busy` + a status region means screen readers announce the load.
 */
export function LoadingSkeleton({
  rows = 4,
  variant = "text",
  label = "Loading",
  className,
}: LoadingSkeletonProps) {
  const bar = "animate-pulse rounded bg-slate-200 motion-reduce:animate-none";

  if (variant === "table") {
    return (
      <div
        className={cx("overflow-hidden rounded-md border border-slate-200", className)}
        role="status"
        aria-busy="true"
        aria-live="polite"
      >
        <div className="flex items-center gap-4 border-b border-slate-200 bg-slate-50 px-3 py-2">
          {[120, 90, 140, 70].map((width, index) => (
            <div key={index} className={bar} style={{ width, height: 12 }} />
          ))}
        </div>
        {Array.from({ length: rows }, (_, rowIndex) => (
          <div key={rowIndex} className="flex items-center gap-4 border-b border-slate-100 px-3 py-3">
            {[180, 110, 200, 60].map((width, index) => (
              <div key={index} className={bar} style={{ width, height: 12 }} />
            ))}
          </div>
        ))}
        <span className="sr-only">{label}</span>
      </div>
    );
  }

  if (variant === "cards") {
    return (
      <div className={cx("grid gap-3 sm:grid-cols-2 lg:grid-cols-3", className)} role="status" aria-busy="true">
        {Array.from({ length: rows }, (_, index) => (
          <div key={index} className="space-y-2 rounded-md border border-slate-200 p-4">
            <div className={cx(bar, "h-3 w-1/3")} />
            <div className={cx(bar, "h-5 w-4/5")} />
            <div className={cx(bar, "h-3 w-full")} />
            <div className={cx(bar, "h-3 w-2/3")} />
          </div>
        ))}
        <span className="sr-only">{label}</span>
      </div>
    );
  }

  if (variant === "chart") {
    return (
      <div
        className={cx("flex h-64 items-end gap-2 rounded-md border border-slate-200 p-4", className)}
        role="status"
        aria-busy="true"
      >
        {Array.from({ length: 12 }, (_, index) => (
          <div
            key={index}
            className={cx(bar, "flex-1")}
            style={{ height: `${30 + ((index * 37) % 60)}%` }}
          />
        ))}
        <span className="sr-only">{label}</span>
      </div>
    );
  }

  if (variant === "stat") {
    return (
      <div className={cx("grid gap-3 sm:grid-cols-2 lg:grid-cols-4", className)} role="status" aria-busy="true">
        {Array.from({ length: rows }, (_, index) => (
          <div key={index} className="space-y-2 rounded-md border border-slate-200 p-4">
            <div className={cx(bar, "h-3 w-1/2")} />
            <div className={cx(bar, "h-7 w-2/3")} />
          </div>
        ))}
        <span className="sr-only">{label}</span>
      </div>
    );
  }

  return (
    <div className={cx("space-y-2", className)} role="status" aria-busy="true">
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          className={cx(bar, "h-3")}
          style={{ width: `${100 - (index % 3) * 12}%` }}
        />
      ))}
      <span className="sr-only">{label}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// EmptyState
// ---------------------------------------------------------------------------

interface EmptyStateProps {
  title: string;
  description?: ReactNode;
  /** Suggest what to change — never leave the user with a dead end. */
  hint?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ title, description, hint, action, className }: EmptyStateProps) {
  return (
    <div
      className={cx(
        "flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center",
        className,
      )}
      role="status"
    >
      <svg className="h-8 w-8 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M3 7.5 12 3l9 4.5M3 7.5v9L12 21l9-4.5v-9M3 7.5 12 12m9-4.5L12 12m0 0v9" />
      </svg>
      <div>
        <p className="text-sm font-semibold text-slate-800">{title}</p>
        {description ? <p className="mt-1 max-w-md text-sm text-slate-600">{description}</p> : null}
      </div>
      {hint ? <p className="max-w-md text-xs text-slate-500">{hint}</p> : null}
      {action}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ErrorState
// ---------------------------------------------------------------------------

interface ErrorStateProps {
  error: unknown;
  /** Called by the retry button. Omit to hide the button. */
  onRetry?: () => void;
  title?: string;
  /** Extra context, e.g. "the news list". */
  context?: string;
  className?: string;
}

/**
 * Renders an error with a plain-language message, the machine detail behind a
 * disclosure, and a retry affordance when the failure is retryable.
 */
export function ErrorState({ error, onRetry, title, context, className }: ErrorStateProps) {
  const apiError = isApiError(error) ? error : null;
  const retryable = apiError ? apiError.isRetryable : true;
  const message = apiError
    ? apiError.userMessage
    : error instanceof Error
      ? error.message
      : "Something went wrong while loading this data.";

  const technical = apiError
    ? [apiError.kind, apiError.status, apiError.detail, apiError.url].filter(Boolean).join(" · ")
    : error instanceof Error
      ? `${error.name}: ${error.message}`
      : String(error);

  return (
    <div
      className={cx(
        "rounded-md border border-rose-300 bg-rose-50 p-4",
        className,
      )}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <svg className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fillRule="evenodd" d="M18 10A8 8 0 1 1 2 10a8 8 0 0 1 16 0Zm-8-4a1 1 0 0 1 1 1v3a1 1 0 1 1-2 0V7a1 1 0 0 1 1-1Zm0 7a1 1 0 1 0 0 2 1 1 0 0 0 0-2Z" clipRule="evenodd" />
        </svg>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-rose-900">
            {title ?? `Could not load ${context ?? "this data"}`}
          </p>
          <p className="mt-1 text-sm text-rose-800">{message}</p>

          {apiError?.status === 404 ? (
            <p className="mt-1 text-xs text-rose-700">
              The item may have been removed, or the id may be from a different corpus snapshot.
            </p>
          ) : null}

          {!retryable ? (
            <p className="mt-1 text-xs text-rose-700">
              Retrying will not help — this request was rejected rather than failing transiently.
            </p>
          ) : null}

          <details className="mt-2">
            <summary className="cursor-pointer text-xs font-medium text-rose-800 underline-offset-2 hover:underline">
              Technical detail
            </summary>
            <p className="mt-1 break-words font-mono text-[0.7rem] text-rose-900/80">{technical}</p>
          </details>

          {onRetry && retryable ? (
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 inline-flex items-center gap-1.5 rounded border border-rose-400 bg-white px-2.5 py-1.5 text-xs font-medium text-rose-800 hover:bg-rose-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 focus-visible:ring-offset-1"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M4.755 5.755A.75.75 0 0 1 5.286 5.5h3.5a.75.75 0 0 1 0 1.5H6.884l1.056 1.056a4 4 0 1 1-1.06 4.243.75.75 0 0 1 1.415-.5 2.5 2.5 0 1 0 .53-2.65L7.75 10.22v2.53a.75.75 0 0 1-1.5 0V6.25a.75.75 0 0 1 .22-.53Z" clipRule="evenodd" />
              </svg>
              Retry
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// OfflineNotice — special-case for the "backend not running" story
// ---------------------------------------------------------------------------

export function OfflineNotice({ onRetry, className }: { onRetry?: () => void; className?: string }) {
  return (
    <div className={cx("rounded-md border border-slate-300 bg-white p-4", className)} role="status">
      <p className="text-sm font-semibold text-slate-900">The NaijaFinSent API is not reachable</p>
      <p className="mt-1 text-sm text-slate-600">
        Start the FastAPI service on <code className="font-mono text-xs">http://localhost:8000</code>,
        or set <code className="font-mono text-xs">VITE_USE_MOCKS=true</code> in{" "}
        <code className="font-mono text-xs">.env</code> to review the interface against clearly
        synthetic fixtures.
      </p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded border border-slate-400 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
        >
          Check again
        </button>
      ) : null}
    </div>
  );
}
