/**
 * Formatting helpers: naira, dates, confidence, and label/type colour maps.
 *
 * Colour choices are part of the product contract:
 *   positive = emerald, negative = rose, neutral = slate, uncertain = amber.
 * Entity-type colours are distinct and stable across every view.
 */

import type { EventType, EntityType, SentimentLabel, TrustTier } from "./schemas";
import { EVENT_TYPE_LABELS } from "./schemas";

// ---------------------------------------------------------------------------
// Naira / money
// ---------------------------------------------------------------------------

/**
 * Format a monetary value. The currency is only rendered when the source
 * actually stated one — we never infer a missing unit.
 */
export function formatMoney(
  value: number | null | undefined,
  currency: string | null | undefined,
  unit: string | null | undefined,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";

  const code = (currency ?? "").toUpperCase();
  const symbol = code === "NGN" ? "₦" : code ? `${code} ` : "";
  const magnitude = unit ? ` ${unit}` : "";

  const abs = Math.abs(value);
  const digits = abs >= 1000 || Number.isInteger(value) ? 0 : 2;

  const formatted = value.toLocaleString("en-NG", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

  return `${symbol}${formatted}${magnitude}`.trim();
}

/** Compact naira display for stat cards, e.g. ₦1.2bn. Never applied silently to spans. */
export function formatNairaCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${sign}₦${(abs / 1e12).toFixed(1)}tn`;
  if (abs >= 1e9) return `${sign}₦${(abs / 1e9).toFixed(1)}bn`;
  if (abs >= 1e6) return `${sign}₦${(abs / 1e6).toFixed(1)}m`;
  if (abs >= 1e3) return `${sign}₦${(abs / 1e3).toFixed(1)}k`;
  return `${sign}₦${abs.toFixed(0)}`;
}

// ---------------------------------------------------------------------------
// Dates — we keep three clocks strictly separate
// ---------------------------------------------------------------------------

function parse(value: string | null | undefined): Date | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** e.g. "12 Mar 2024, 14:05" in the viewer's locale/timezone. */
export function formatDateTime(value: string | null | undefined): string {
  const d = parse(value);
  if (!d) return "unknown";
  return d.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** e.g. "12 Mar 2024". Use for publish date and event date. */
export function formatDate(value: string | null | undefined): string {
  const d = parse(value);
  if (!d) return "unknown";
  return d.toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/** e.g. "2024-03". Used for analytics period keys. */
export function formatPeriod(value: string): string {
  const dayMatch = /^\d{4}-\d{2}-\d{2}$/.test(value);
  if (dayMatch) return formatDate(value);
  const monthMatch = /^(\d{4})-(\d{2})$/.exec(value);
  if (monthMatch) {
    const d = new Date(Number(monthMatch[1]), Number(monthMatch[2]) - 1, 1);
    return d.toLocaleDateString(undefined, { month: "short", year: "numeric" });
  }
  return value;
}

/** Relative age, e.g. "3h ago". Used for freshness, not for event dating. */
export function formatRelative(value: string | null | undefined): string {
  const d = parse(value);
  if (!d) return "unknown";
  const diffMs = Date.now() - d.getTime();
  const past = diffMs >= 0;
  const mins = Math.round(Math.abs(diffMs) / 60000);
  if (mins < 1) return "just now";
  const text =
    mins < 60
      ? `${mins}m`
      : mins < 60 * 24
        ? `${Math.round(mins / 60)}h`
        : mins < 60 * 24 * 30
          ? `${Math.round(mins / (60 * 24))}d`
          : `${Math.round(mins / (60 * 24 * 30))}mo`;
  return past ? `${text} ago` : `in ${text}`;
}

/** Minutes → human lag string used by the freshness panel. */
export function formatMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || Number.isNaN(minutes)) return "unknown";
  if (minutes < 60) return `${Math.round(minutes)} min`;
  if (minutes < 60 * 24) return `${(minutes / 60).toFixed(1)} h`;
  return `${(minutes / (60 * 24)).toFixed(1)} d`;
}

// ---------------------------------------------------------------------------
// Confidence
// ---------------------------------------------------------------------------

/**
 * Confidence as a percentage. The caller is responsible for stating whether
 * the number is calibrated (see ModelBadge / ConfidenceMeter).
 */
export function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

/** Bucketed confidence wording, matched to the ConfidenceMeter bands. */
export function confidenceBand(value: number | null | undefined): {
  key: "low" | "medium" | "high";
  label: string;
  tone: string;
} {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return { key: "low", label: "No score", tone: "text-slate-500" };
  }
  if (value >= 0.75) return { key: "high", label: "High", tone: "text-emerald-700" };
  if (value >= 0.5) return { key: "medium", label: "Moderate", tone: "text-amber-700" };
  return { key: "low", label: "Low", tone: "text-rose-700" };
}

/** Format a metric's confidence interval as a range. NEVER render a bare point. */
export function formatCi(low: number, high: number, level = 0.95, digits = 3): string {
  const pct = Math.round(level * 100);
  return `${pct}% CI [${low.toFixed(digits)}, ${high.toFixed(digits)}]`;
}

/** Format a metric value with its interval attached. */
export function formatMetricWithCi(
  value: number,
  low: number,
  high: number,
  level = 0.95,
  digits = 3,
): string {
  return `${value.toFixed(digits)} (${formatCi(low, high, level, digits)})`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-NG");
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/** Signed delta, used for narrative intensity change and sentiment shift. */
export function formatDelta(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}`;
}

// ---------------------------------------------------------------------------
// Text
// ---------------------------------------------------------------------------

export function truncate(text: string, max = 160): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1).trimEnd()}…`;
}

/** Domain-only host for source links, so the link label stays honest about origin. */
export function hostnameOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// ---------------------------------------------------------------------------
// Sentiment label styling (positive=emerald, negative=rose, neutral=slate,
// uncertain=amber). These are the ONLY colours used for labels anywhere.
// ---------------------------------------------------------------------------

export interface LabelStyle {
  /** Badge classes: soft background, readable text, subtle ring. */
  badge: string;
  /** Inline evidence/highlight classes. */
  highlight: string;
  /** Solid colour for charts (must match the hex below). */
  hex: string;
  text: string;
  border: string;
  bg: string;
  label: string;
}

export const SENTIMENT_STYLES: Record<SentimentLabel, LabelStyle> = {
  positive: {
    badge: "bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-300",
    highlight: "bg-emerald-100 decoration-emerald-400",
    hex: "#059669",
    text: "text-emerald-700",
    border: "border-emerald-300",
    bg: "bg-emerald-50",
    label: "Positive",
  },
  negative: {
    badge: "bg-rose-50 text-rose-800 ring-1 ring-inset ring-rose-300",
    highlight: "bg-rose-100 decoration-rose-400",
    hex: "#e11d48",
    text: "text-rose-700",
    border: "border-rose-300",
    bg: "bg-rose-50",
    label: "Negative",
  },
  neutral: {
    badge: "bg-slate-100 text-slate-800 ring-1 ring-inset ring-slate-300",
    highlight: "bg-slate-100 decoration-slate-400",
    hex: "#64748b",
    text: "text-slate-600",
    border: "border-slate-300",
    bg: "bg-slate-50",
    label: "Neutral",
  },
  uncertain: {
    badge: "bg-amber-50 text-amber-900 ring-1 ring-inset ring-amber-300",
    highlight: "bg-amber-100 decoration-amber-400",
    hex: "#d97706",
    text: "text-amber-700",
    border: "border-amber-300",
    bg: "bg-amber-50",
    label: "Uncertain",
  },
};

export function sentimentStyle(label: SentimentLabel | null | undefined): LabelStyle {
  return SENTIMENT_STYLES[label ?? "neutral"];
}

/** Plain-language gloss of what "uncertain" means — it is NOT "neutral". */
export const SENTIMENT_GLOSS: Record<SentimentLabel, string> = {
  positive: "Text uses favourable language toward its subject.",
  negative: "Text uses unfavourable language toward its subject.",
  neutral: "Text takes no position — factual or balanced reporting.",
  uncertain: "Text signals doubt or a conditional outcome. Distinct from neutral.",
};

// ---------------------------------------------------------------------------
// Entity type colours — distinct, stable, colour-blind-considerate
// ---------------------------------------------------------------------------

export interface EntityStyle {
  hex: string;
  badge: string;
  highlight: string;
  label: string;
}

export const ENTITY_STYLES: Record<EntityType, EntityStyle> = {
  ORG: {
    hex: "#1d4ed8",
    badge: "bg-blue-50 text-blue-800 ring-1 ring-inset ring-blue-300",
    highlight: "bg-blue-100 text-blue-900",
    label: "Organisation",
  },
  PER: {
    hex: "#7c3aed",
    badge: "bg-violet-50 text-violet-800 ring-1 ring-inset ring-violet-300",
    highlight: "bg-violet-100 text-violet-900",
    label: "Person",
  },
  REGULATOR: {
    hex: "#b91c1c",
    badge: "bg-red-50 text-red-800 ring-1 ring-inset ring-red-300",
    highlight: "bg-red-100 text-red-900",
    label: "Regulator",
  },
  MONEY: {
    hex: "#0f766e",
    badge: "bg-teal-50 text-teal-800 ring-1 ring-inset ring-teal-300",
    highlight: "bg-teal-100 text-teal-900",
    label: "Money",
  },
  TICKER: {
    hex: "#4338ca",
    badge: "bg-indigo-50 text-indigo-800 ring-1 ring-inset ring-indigo-300",
    highlight: "bg-indigo-100 text-indigo-900",
    label: "Ticker",
  },
  CURRENCY: {
    hex: "#a16207",
    badge: "bg-yellow-50 text-yellow-900 ring-1 ring-inset ring-yellow-300",
    highlight: "bg-yellow-100 text-yellow-900",
    label: "Currency",
  },
  SECTOR: {
    hex: "#15803d",
    badge: "bg-green-50 text-green-800 ring-1 ring-inset ring-green-300",
    highlight: "bg-green-100 text-green-900",
    label: "Sector",
  },
  EVENT_TRIGGER: {
    hex: "#be185d",
    badge: "bg-pink-50 text-pink-800 ring-1 ring-inset ring-pink-300",
    highlight: "bg-pink-100 text-pink-900",
    label: "Event trigger",
  },
};

export function entityStyle(type: EntityType | null | undefined): EntityStyle {
  return type ? ENTITY_STYLES[type] : ENTITY_STYLES.ORG;
}

// ---------------------------------------------------------------------------
// Processing status
// ---------------------------------------------------------------------------

export const STATUS_STYLES: Record<
  string,
  { badge: string; label: string; description: string }
> = {
  pending: {
    badge: "bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-300",
    label: "Pending",
    description: "Queued; no predictions available yet.",
  },
  processing: {
    badge: "bg-sky-50 text-sky-800 ring-1 ring-inset ring-sky-300",
    label: "Processing",
    description: "Pipeline still running; results may be incomplete.",
  },
  complete: {
    badge: "bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-300",
    label: "Complete",
    description: "All pipeline stages finished.",
  },
  partial: {
    badge: "bg-amber-50 text-amber-900 ring-1 ring-inset ring-amber-300",
    label: "Partial",
    description:
      "Some pipeline stages failed. The predictions below cover only the stages that succeeded.",
  },
  failed: {
    badge: "bg-rose-50 text-rose-800 ring-1 ring-inset ring-rose-300",
    label: "Failed",
    description: "The pipeline failed for this item. No predictions are shown.",
  },
};

export function statusStyle(status: string | null | undefined) {
  return (
    STATUS_STYLES[status ?? "pending"] ?? {
      badge: "bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-300",
      label: status ?? "Unknown",
      description: "Unrecognised processing status.",
    }
  );
}

// ---------------------------------------------------------------------------
// Event type + trust tier presentation
// ---------------------------------------------------------------------------

export const EVENT_TYPE_STYLES: Record<string, string> = {
  cbn_policy: "bg-sky-50 text-sky-800 ring-1 ring-inset ring-sky-300",
  earnings: "bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-300",
  dividend: "bg-teal-50 text-teal-800 ring-1 ring-inset ring-teal-300",
  mna: "bg-violet-50 text-violet-800 ring-1 ring-inset ring-violet-300",
  regulatory_sanction: "bg-rose-50 text-rose-800 ring-1 ring-inset ring-rose-300",
  capital_raise: "bg-amber-50 text-amber-900 ring-1 ring-inset ring-amber-300",
  fx_move: "bg-indigo-50 text-indigo-800 ring-1 ring-inset ring-indigo-300",
  oil_energy: "bg-orange-50 text-orange-900 ring-1 ring-inset ring-orange-300",
};

export function eventTypeStyle(type: EventType | string | null | undefined): string {
  if (!type) return "bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-300";
  return (
    EVENT_TYPE_STYLES[type] ?? "bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-300"
  );
}

export function eventTypeLabel(type: EventType | string | null | undefined): string {
  if (!type) return "Unknown event";
  return EVENT_TYPE_LABELS[type as EventType] ?? String(type);
}

export const TRUST_TIER_STYLES: Record<TrustTier | string, string> = {
  official: "bg-brand-50 text-brand-800 ring-1 ring-inset ring-brand-300",
  tier1: "bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-200",
  tier2: "bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-300",
  tier3: "bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-200",
  unknown: "bg-amber-50 text-amber-900 ring-1 ring-inset ring-amber-300",
};

export function trustTierStyle(tier: TrustTier | string | null | undefined): string {
  if (!tier) return TRUST_TIER_STYLES["unknown"] as string;
  return TRUST_TIER_STYLES[tier] ?? (TRUST_TIER_STYLES["unknown"] as string);
}
