import { cx } from "../lib/cx";
import {
  ENTITY_STYLES,
  entityStyle,
  eventTypeLabel,
  eventTypeStyle,
  sentimentStyle,
} from "../lib/format";
import type { EntityType, SentimentLabel } from "../lib/schemas";

// ---------------------------------------------------------------------------
// Prediction badge — the sentiment label chip
// ---------------------------------------------------------------------------

interface PredictionBadgeProps {
  label: SentimentLabel | null | undefined;
  /** Rendered after the label, e.g. "72%". Only pass calibrated numbers as such. */
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
 * This renders the label *assigned to the language of the text* — never a
 * verdict about a company or a market.
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
        "inline-flex items-center gap-1 rounded-full font-medium",
        style.badge,
        size === "sm" ? "px-2 py-0.5 text-[0.7rem]" : "px-2.5 py-1 text-xs",
        className,
      )}
      title={title ?? `Model sentiment label: ${style.label}`}
    >
      <span
        aria-hidden="true"
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: style.hex }}
      />
      {style.label}
      {confidence !== null && confidence !== undefined ? (
        <span className="font-normal tabular-nums opacity-80">
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

/** Small colour swatch used by the entity legend. */
export function EntitySwatch({ type }: { type: EntityType }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-3 w-3 shrink-0 rounded-sm ring-1 ring-inset ring-black/10"
      style={{ backgroundColor: entityStyle(type).hex }}
    />
  );
}

// ---------------------------------------------------------------------------
// Provenance chip: reported fact vs model interpretation
// ---------------------------------------------------------------------------

interface ProvenanceChipProps {
  kind: "reported" | "model";
  className?: string;
}

/**
 * Distinguishes text that appears in the published article from text a model
 * produced. The styling differs in *shape* as well as colour (solid rule vs
 * dashed rule, different icon), so the distinction survives greyscale printing
 * and colour-blind viewing.
 */
export function ProvenanceChip({ kind, className }: ProvenanceChipProps) {
  if (kind === "reported") {
    return (
      <span
        className={cx(
          "inline-flex items-center gap-1 rounded border border-solid border-slate-400 bg-white px-1.5 py-0.5 text-[0.65rem] font-medium text-slate-700",
          className,
        )}
        title="Quoted or attributed in the published article text."
      >
        <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path d="M4 3a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2H4Zm10.7 5.7-4.5 4.6a1 1 0 0 1-1.4 0L6.3 10.8a1 1 0 1 1 1.4-1.4l1.8 1.8 3.8-3.9a1 1 0 0 1 1.4 1.4Z" />
        </svg>
        reported in source
      </span>
    );
  }
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded border border-dashed border-violet-500 bg-violet-50 px-1.5 py-0.5 text-[0.65rem] font-medium text-violet-800",
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
  /** Override the rendered text; the colour still comes from `type`. */
  label?: string;
  className?: string;
}

export function EventTypeBadge({ type, label, className }: EventTypeBadgeProps) {
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
