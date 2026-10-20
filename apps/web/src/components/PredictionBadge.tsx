import { cx } from "../lib/cx";
import { ENTITY_STYLES, SENTIMENT_STYLES, entityStyle, sentimentStyle } from "../lib/format";
import type { EntityType, SentimentLabel } from "../lib/schemas";

// ---------------------------------------------------------------------------
// Prediction badge — the label chip for a sentiment prediction
// ---------------------------------------------------------------------------

interface PredictionBadgeProps {
  label: SentimentLabel | null | undefined;
  /** Appended after the label, e.g. "72%". */
  confidence?: number | null;
  size?: "sm" | "md";
  /** When true, render a muted "no prediction" chip instead of a colour. */
  empty?: boolean;
  title?: string;
  className?: string;
}

/**
 * Sentiment label chip. Colours are fixed by the product contract:
 * positive=emerald, negative=rose, neutral=slate, uncertain=amber.
 *
 * This renders a *label*, never a verdict: it is always the label assigned to
 * the language of the text.
 */
export function PredictionBadge({
  label,
  confidence,
  size = "sm",
  empty = false,
  title,
  className,
}: PredictionBadgeProps) {
  if (empty || !label) {
    return (
      <span
        className={cx(
          "inline-flex items-center rounded-full bg-slate-100 font-medium text-slate-500 ring-1 ring-inset ring-slate-200",
          size === "sm" ? "px-2 py-0.5 text-[0.7rem]" : "px-2.5 py-1 text-xs",
          className,
        )}
        title={title ?? "No prediction available for this item"}
      >
        no prediction
      </span>
    );
  }

  const style = sentimentStyle(label);
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full font-medium capitalize",
        style.badge,
        size === "sm" ? "px-2 py-0.5 text-[0.7rem]" : "px-2.5 py-1 text-xs",
        className,
      )}
      title={title ?? `Model sentiment label: ${label}`}
    >
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: style.hex }} />
      {style.label}
      {confidence !== null && confidence !== undefined ? (
        <span className="font-normal opacity-80 tabular-nums">
          {Math.round(confidence * 100)}%
        </span>
      ) : null}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Entity type badge
// ---------------------------------------------------------------------------

interface EntityTypeBadgeProps {
  type: EntityType | null | undefined;
  size?: "sm" | "md";
  className?: string;
}

export function EntityTypeBadge({ type, size = "sm", className }: EntityTypeBadgeProps) {
  const style = type ? ENTITY_STYLES[type] : undefined;
  if (!type || !style) {
    return (
      <span
        className={cx(
          "inline-flex items-center rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.65rem] text-slate-600",
          className,
        )}
      >
        UNKNOWN
      </span>
    );
  }
  return (
    <span
      className={cx(
        "inline-flex items-center rounded font-mono font-medium tracking-tight",
        style.badge,
        size === "sm" ? "px-1.5 py-0.5 text-[0.65rem]" : "px-2 py-1 text-xs",
        className,
      )}
      title={style.label}
    >
      {type}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Legibility chip: reported fact vs model interpretation
// ---------------------------------------------------------------------------

interface ProvenanceChipProps {
  kind: "reported" | "model";
  className?: string;
}

/**
 * Distinguishes text that appears in the published article from text a model
 * produced. The styling is deliberately different in *shape* as well as
 * colour, so the distinction survives greyscale/colour-blind viewing.
 */
export function ProvenanceChip({ kind, className }: ProvenanceChipProps) {
  if (kind === "reported") {
    return (
      <span
        className={cx(
          "inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-1.5 py-0.5 text-[0.65rem] font-medium text-slate-700",
          className,
        )}
        title="Quoted or attributed in the published article text."
      >
        <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path d="M6 2a1 1 0 0 0-1 1v1H4.5A1.5 1.5 0 0 0 3 5.5v11A1.5 1.5 0 0 0 4.5 18h11a1.5 1.5 0 0 0 1.5-1.5v-11A1.5 1.5 0 0 0 15.5 4H14V3a1 1 0 1 0-2 0v1H8V3a1 1 0 0 0-1-1Zm7.7 6.7-4.5 4.6a1 1 0 0 1-1.4 0L5.3 11a1 1 0 1 1 1.4-1.4l1.8 1.8 3.8-3.8a1 1 0 0 1 1.4 1.4Z" />
        </svg>
        reported in source
      </span>
    );
  }
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded border border-dashed border-violet-400 bg-violet-50 px-1.5 py-0.5 text-[0.65rem] font-medium text-violet-800",
        className,
      )}
      title="Produced by a model from the article text. May be wrong."
    >
      <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm0 4a1 1 0 1 1 0 2 1 1 0 0 1 0-2Zm0 3.5c.55 0 1 .45 1 1V14a1 1 0 1 1-2 0v-3.5c0-.55.45-1 1-1Z" />
      </svg>
      model interpretation
    </span>
  );
}

// ---------------------------------------------------------------------------
// Event type badge
// ---------------------------------------------------------------------------

interface EventTypeBadgeProps {
  type: string | null | undefined;
  label?: string;
  className?: string;
}

export function EventTypeBadge({ type, label, className }: EventTypeBadgeProps) {
  const { eventTypeLabel, eventTypeStyle } = stylesForEvents();
  return (
    <span
      className={cx(
        "inline-flex items-center rounded px-1.5 py-0.5 text-[0.7rem] font-medium",
        eventTypeStyle(type),
        className,
      )}
    >
      {label ?? eventTypeLabel(type)}
    </span>
  );
}

// Imported lazily to keep this file's imports flat and avoid a cycle.
function stylesForEvents() {
  return {
    eventTypeLabel,
    eventTypeStyle,
  };
}

// Re-import at the bottom so the module stays a single unit for readers.
import { eventTypeLabel, eventTypeStyle } from "../lib/format";

export { SentimentLabel as _SentimentLabelType };
