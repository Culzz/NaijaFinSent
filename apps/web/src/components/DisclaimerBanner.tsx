import { DISCLAIMER_TEXT, EVIDENCE_SPAN_NOTE, USE_MOCKS_LABEL } from "../lib/constants";
import { cx } from "../lib/cx";

interface DisclaimerBannerProps {
  /** Compact variant is used inside dense panels; the full variant on page tops. */
  variant?: "full" | "compact";
  className?: string;
}

/**
 * Persistent product disclaimer. This is not decoration — it is the single
 * most important string in the app and must render on EVERY route.
 *
 * Do not paraphrase DISCLAIMER_TEXT. If it needs to change, change it in
 * src/lib/constants.ts so every surface updates together.
 */
export function DisclaimerBanner({ variant = "full", className }: DisclaimerBannerProps) {
  if (variant === "compact") {
    return (
      <p
        className={cx(
          "rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-900",
          className,
        )}
        role="note"
      >
        <span className="font-semibold">Not investment advice.</span> These are measurements of
        language in published news coverage, not investor sentiment, and no causal or predictive
        claim is made.
      </p>
    );
  }

  return (
    <div
      className={cx(
        "flex items-start gap-3 border-b border-amber-300 bg-amber-50 px-4 py-2.5 text-amber-950",
        className,
      )}
      role="note"
      aria-label="Product disclaimer"
    >
      <svg
        className="mt-0.5 h-4 w-4 shrink-0 text-amber-700"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495ZM10 6a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 10 6Zm0 9a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
          clipRule="evenodd"
        />
      </svg>
      <p className="text-xs leading-relaxed sm:text-[0.8rem]">
        <span className="font-semibold">{DISCLAIMER_TEXT}</span>
      </p>
    </div>
  );
}

/** Short note reminding readers what an evidence span is (and is not). */
export function EvidenceSpanNote({ className }: { className?: string }) {
  return (
    <p className={cx("text-xs text-slate-600", className)}>
      <span className="font-medium text-slate-700">Evidence spans are supporting text</span>, not
      causal attribution. {EVIDENCE_SPAN_NOTE.replace(/^Evidence spans are supporting text, not causal attribution\.\s*/, "")}
    </p>
  );
}

/** Banner shown only in mock mode so synthetic data can never be mistaken for real. */
export function MockDataBanner({ className }: { className?: string }) {
  return (
    <div
      className={cx(
        "flex items-start gap-3 border-b border-fuchsia-300 bg-fuchsia-50 px-4 py-2 text-fuchsia-950",
        className,
      )}
      role="status"
    >
      <svg className="mt-0.5 h-4 w-4 shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm1 11a1 1 0 1 1-2 0 1 1 0 0 1 2 0Zm-1-8a1 1 0 0 1 1 1v4a1 1 0 1 1-2 0V6a1 1 0 0 1 1-1Z" />
      </svg>
      <p className="text-xs">
        <span className="font-semibold">{USE_MOCKS_LABEL}.</span> The backend is not being
        queried; every value, article, and metric below is fabricated for interface review.
      </p>
    </div>
  );
}
