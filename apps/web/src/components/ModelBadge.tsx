import { cx } from "../lib/cx";
import { formatConfidence, sentimentStyle } from "../lib/format";
import type { ModelRef } from "../lib/schemas";
import { ProvenanceChip } from "./PredictionBadge";

// ---------------------------------------------------------------------------
// Model badge — name + version, always visible next to a prediction
// ---------------------------------------------------------------------------

interface ModelBadgeProps {
  model: ModelRef | null | undefined;
  /** Show the calibrated/uncalibrated state as a chip. Default true. */
  showCalibration?: boolean;
  className?: string;
}

/**
 * Every prediction view must show which model produced it. This component is
 * the single place that renders that fact, so it cannot be forgotten.
 */
export function ModelBadge({ model, showCalibration = true, className }: ModelBadgeProps) {
  if (!model) {
    return (
      <span
        className={cx(
          "inline-flex items-center rounded border border-dashed border-slate-300 px-2 py-0.5 text-[0.7rem] text-slate-500",
          className,
        )}
      >
        model unknown
      </span>
    );
  }

  return (
    <span className={cx("inline-flex flex-wrap items-center gap-1.5", className)}>
      <span
        className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2 py-0.5 font-mono text-[0.7rem] text-slate-700"
        title={`Produced by ${model.name} version ${model.version} (task: ${model.task})`}
      >
        <svg className="h-3 w-3 text-slate-400" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path d="M7 3a3 3 0 0 1 5.9-.7A3.5 3.5 0 0 1 15 9.3V15a2 2 0 0 1-2 2h-1a1 1 0 1 1 0-2h1v-2h-3v2a1 1 0 1 1-2 0v-2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h3V3Z" />
        </svg>
        {model.name}
        <span className="text-slate-400">@</span>
        {model.version}
      </span>
      <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.65rem] text-slate-600">
        task: {model.task}
      </span>
      {showCalibration ? <CalibrationChip calibrated={model.calibrated} /> : null}
    </span>
  );
}

interface CalibrationChipProps {
  calibrated: boolean;
  className?: string;
}

/**
 * Whether a confidence number is calibrated changes how it may be read.
 * We never present an uncalibrated score as if it were a probability.
 */
export function CalibrationChip({ calibrated, className }: CalibrationChipProps) {
  return calibrated ? (
    <span
      className={cx(
        "inline-flex items-center rounded bg-brand-50 px-1.5 py-0.5 text-[0.65rem] font-medium text-brand-800 ring-1 ring-inset ring-brand-300",
        className,
      )}
      title="Confidence was calibrated (e.g. isotonic/temperature scaling) on held-out data."
    >
      calibrated
    </span>
  ) : (
    <span
      className={cx(
        "inline-flex items-center rounded bg-amber-50 px-1.5 py-0.5 text-[0.65rem] font-medium text-amber-900 ring-1 ring-inset ring-amber-300",
        className,
      )}
      title="Confidence is a raw model score, not a calibrated probability."
    >
      uncalibrated score
    </span>
  );
}

// ---------------------------------------------------------------------------
// Confidence meter
// ---------------------------------------------------------------------------

interface ConfidenceMeterProps {
  value: number | null | undefined;
  calibrated?: boolean;
  label?: string;
  className?: string;
}

/**
 * Renders a confidence value as a bar plus an explicit number and calibration
 * state. The bar never stands alone — the number is always printed, because a
 * bar invites eyeballing a precision the model does not have.
 *
 * For multi-class predictions, an uncalibrated score of 1/n carries no
 * information; callers should pass `probabilities` through ProbabilityBars
 * instead when that matters.
 */
export function ConfidenceMeter({
  value,
  calibrated = false,
  label = "Confidence",
  className,
}: ConfidenceMeterProps) {
  const hasValue = value !== null && value !== undefined && !Number.isNaN(value);
  const pct = hasValue ? Math.max(0, Math.min(1, value)) * 100 : 0;

  return (
    <div className={cx("space-y-1", className)}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-slate-600">{label}</span>
        <span className="font-mono text-xs tabular-nums text-slate-800">
          {hasValue ? formatConfidence(value) : "—"}
          <span className="ml-1 text-slate-400">
            {calibrated ? "(calibrated)" : "(uncalibrated score)"}
          </span>
        </span>
      </div>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-slate-200"
        role="meter"
        aria-valuenow={hasValue ? Math.round(pct) : undefined}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label}${calibrated ? " (calibrated)" : " (uncalibrated score)"}`}
      >
        <div
          className={cx(
            "h-full rounded-full motion-safe:transition-[width] motion-safe:duration-300",
            calibrated ? "bg-brand-600" : "bg-amber-500",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      {!hasValue ? (
        <p className="text-[0.7rem] text-slate-500">No confidence value was returned.</p>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Probability bars (all classes, so a flat distribution is visible)
// ---------------------------------------------------------------------------

interface ProbabilityBarsProps {
  probabilities: Record<string, number> | null | undefined;
  calibrated?: boolean;
  className?: string;
}

/**
 * Shows the full class distribution. This exists so a near-uniform
 * distribution is *visible* rather than hidden behind one confidence number.
 */
export function ProbabilityBars({
  probabilities,
  calibrated = false,
  className,
}: ProbabilityBarsProps) {
  const entries = Object.entries(probabilities ?? {});
  if (entries.length === 0) {
    return (
      <p className={cx("text-xs text-slate-500", className)}>
        The model returned no per-class distribution for this prediction.
      </p>
    );
  }

  const ordered = entries.sort(([, a], [, b]) => b - a);

  return (
    <div className={cx("space-y-1.5", className)}>
      {ordered.map(([name, value]) => {
        const known = name === "positive" || name === "negative" || name === "neutral" || name === "uncertain";
        const colour = known ? sentimentStyle(name as "positive").hex : "#94a3b8";
        return (
          <div key={name} className="flex items-center gap-2">
            <span className="w-20 shrink-0 text-[0.7rem] capitalize text-slate-600">{name}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200">
              <div
                className="h-full rounded-full"
                style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%`, backgroundColor: colour }}
              />
            </div>
            <span className="w-12 shrink-0 text-right font-mono text-[0.7rem] tabular-nums text-slate-700">
              {Math.round(value * 100)}%
            </span>
          </div>
        );
      })}
      <p className="text-[0.7rem] text-slate-500">
        {calibrated
          ? "Distribution calibrated on held-out data."
          : "Distribution is a raw model score, not a calibrated probability."}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Limitations panel
// ---------------------------------------------------------------------------

interface LimitationsPanelProps {
  limitations: string[];
  className?: string;
  /** Short heading; defaults to "Limitations". */
  title?: string;
  /** Hide the "model interpretation" chip when limitations come from a non-model source. */
  showProvenance?: boolean;
}

/**
 * The limitations list is mandatory next to every prediction. When the API
 * returns none we still render the panel and state that none were supplied —
 * an empty list must never look like "no limitations apply".
 */
export function LimitationsPanel({
  limitations,
  className,
  title = "Limitations",
  showProvenance = true,
}: LimitationsPanelProps) {
  return (
    <section
      className={cx("rounded-md border border-amber-300 bg-amber-50/60 p-3", className)}
      aria-label={title}
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-amber-900">{title}</h4>
        {showProvenance ? <ProvenanceChip kind="model" /> : null}
      </div>
      {limitations.length === 0 ? (
        <p className="text-xs text-amber-900">
          The API returned no limitations for this item. That is not the same as there being none —
          treat every number here as a measurement with error.
        </p>
      ) : (
        <ul className="list-disc space-y-1 pl-4 text-xs leading-relaxed text-amber-950">
          {limitations.map((limitation, index) => (
            <li key={index}>{limitation}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
