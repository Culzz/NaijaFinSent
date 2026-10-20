/**
 * Hand-written TypeScript mirror of `naijafinsent/schemas.py` and the API
 * response shapes.
 *
 * Everything here is a measurement of language in published news coverage.
 * Nothing here is investment advice, investor sentiment, or a prediction.
 *
 * Field names and enum spellings must match the Pydantic models EXACTLY.
 * If the Python schemas change, change this file in the same commit.
 */

// ---------------------------------------------------------------------------
// Label spaces (must equal naijafinsent/constants.py tuples)
// ---------------------------------------------------------------------------

export const SENTIMENT_LABELS = ["positive", "negative", "neutral", "uncertain"] as const;
export type SentimentLabel = (typeof SENTIMENT_LABELS)[number];

export const ENTITY_TYPES = [
  "ORG",
  "PER",
  "REGULATOR",
  "MONEY",
  "TICKER",
  "CURRENCY",
  "SECTOR",
  "EVENT_TRIGGER",
] as const;
export type EntityType = (typeof ENTITY_TYPES)[number];

export const EVENT_TYPES = [
  "cbn_policy",
  "earnings",
  "dividend",
  "mna",
  "regulatory_sanction",
  "capital_raise",
  "fx_move",
  "oil_energy",
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

export const PROCESSING_STATUSES = [
  "pending",
  "processing",
  "complete",
  "partial",
  "failed",
] as const;
export type ProcessingStatus = (typeof PROCESSING_STATUSES)[number];

export const TRUST_TIERS = ["official", "tier1", "tier2", "tier3", "unknown"] as const;
export type TrustTier = (typeof TRUST_TIERS)[number];

/** Human labels for event types — mirrors EVENT_TYPE_DESCRIPTIONS in constants.py. */
export const EVENT_TYPE_LABELS: Record<EventType, string> = {
  cbn_policy: "CBN policy",
  earnings: "Earnings",
  dividend: "Dividend",
  mna: "M&A",
  regulatory_sanction: "Regulatory sanction",
  capital_raise: "Capital raise",
  fx_move: "FX move",
  oil_energy: "Oil & energy",
};

export const EVENT_TYPE_DESCRIPTIONS: Record<EventType, string> = {
  cbn_policy: "Central Bank of Nigeria policy decision, circular, or rate change",
  earnings: "Company earnings, interim or final results",
  dividend: "Dividend declaration, closure of registers, or payment",
  mna: "Merger, acquisition, takeover, or divestment",
  regulatory_sanction: "Regulatory fine, sanction, ban, or penalty",
  capital_raise: "Capital raise, recapitalisation, rights issue, or public offer",
  fx_move: "Foreign-exchange or naira valuation move / FX market policy",
  oil_energy: "Oil output, gas supply, or energy-sector disruption",
};

export const ENTITY_TYPE_DESCRIPTIONS: Record<EntityType, string> = {
  ORG: "Company, bank, or firm",
  PER: "Person",
  REGULATOR: "Regulator (CBN, SEC, NDIC, NERC, FCCPC, PenCom …)",
  MONEY: "Monetary amount (value + currency normalised separately)",
  TICKER: "NGX ticker symbol",
  CURRENCY: "Currency mention",
  SECTOR: "Sector",
  EVENT_TRIGGER: "Verb or noun that triggers an event frame",
};

// ---------------------------------------------------------------------------
// Corpus / provenance
// ---------------------------------------------------------------------------

export interface SourceManifestEntry {
  source_id: string;
  name: string;
  base_url: string;
  url_pattern: string;
  access_method: string;
  license_note: string;
  trust_tier: TrustTier | string;
  robots_checked_at: string | null;
  enabled: boolean;
  notes: string | null;
}

export interface Article {
  article_id: string;
  url: string;
  canonical_url: string | null;
  title: string;
  publisher: string;
  source_id: string | null;
  published_at: string | null;
  fetched_at: string;
  language: string;
  content: string;
  content_hash: string;
  is_official_release: boolean;
  syndicated_from: string | null;
  is_duplicate: boolean;
  duplicate_of: string | null;
  minhash_signature: number[] | null;
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Annotation (gold)
// ---------------------------------------------------------------------------

export interface EntitySpan {
  start: number;
  end: number;
  text: string;
  entity_type: EntityType;
}

export interface MoneyAnnotation {
  span: EntitySpan;
  value: number | null;
  currency: string | null;
  unit: string | null;
}

export interface SentimentAnnotation {
  task: string;
  label: SentimentLabel;
  target_entity: string | null;
  rationale_span: EntitySpan | null;
  annotator: string;
  model_prelabel: boolean;
}

export interface EventAnnotation {
  event_type: EventType;
  event_date: string | null;
  entities: EntitySpan[];
  evidence_span: EntitySpan | null;
  annotator: string;
  model_prelabel: boolean;
}

export interface AnnotationRecord {
  item_id: string;
  article_id: string;
  split: string;
  text: string;
  sentiment: SentimentAnnotation | null;
  spans: EntitySpan[];
  money: MoneyAnnotation[];
  events: EventAnnotation[];
}

// ---------------------------------------------------------------------------
// Predictions — every one carries evidence + a model reference
// ---------------------------------------------------------------------------

export interface EvidenceSpan {
  text: string;
  start: number;
  end: number;
}

export interface ModelRef {
  name: string;
  version: string;
  task: string;
  calibrated: boolean;
}

export interface SentimentPrediction {
  label: SentimentLabel;
  /** Calibrated when model.calibrated is true. Always rendered with that caveat. */
  confidence: number;
  probabilities: Record<string, number>;
  evidence: EvidenceSpan[];
  model: ModelRef;
}

export interface EntityPrediction {
  span: EntitySpan;
  entity_id: string | null;
  canonical_name: string | null;
  resolution_method: "alias" | "fuzzy" | "embedding" | "ambiguous" | string | null;
  confidence: number;
}

export interface EntitySentimentPrediction {
  entity_id: string | null;
  canonical_name: string | null;
  label: SentimentLabel;
  confidence: number;
  evidence: EvidenceSpan[];
  model: ModelRef;
}

export interface EventPrediction {
  event_type: EventType;
  confidence: number;
  event_date: string | null;
  entities: EntityPrediction[];
  evidence: EvidenceSpan[];
  attributes: Record<string, unknown>;
  model: ModelRef;
}

export interface AnalysisResult {
  text_sha256: string;
  language: string;
  status: ProcessingStatus;
  sentiment: SentimentPrediction | null;
  entities: EntityPrediction[];
  entity_sentiments: EntitySentimentPrediction[];
  events: EventPrediction[];
  /** Honest caveats the UI must display alongside predictions. */
  limitations: string[];
  processed_at: string;
  latency_ms: number | null;
}

// ---------------------------------------------------------------------------
// Analytics shapes
// ---------------------------------------------------------------------------

export type Granularity = "day" | "week" | "month";

export interface SentimentTrendPoint {
  period: string;
  positive: number;
  negative: number;
  neutral: number;
  uncertain: number;
  mean_score: number | null;
}

export interface EventCount {
  event_type: string;
  count: number;
}

export interface ModelInfo {
  name: string;
  version: string;
  task: string;
  framework: string;
  metrics: Record<string, number>;
  trained_at: string | null;
  description: string | null;
}

export interface HealthStatus {
  status: string;
  version: string;
  database: string;
  models_loaded: string[];
  corpus_size: number | null;
  last_ingestion_at: string | null;
}

// ---------------------------------------------------------------------------
// Paged envelope — {items, total, page, page_size}
// ---------------------------------------------------------------------------

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// API-only response shapes (list rows, timelines, analytics, copilot, watchlists)
// ---------------------------------------------------------------------------

/** A row in GET /news. Content is the full extracted text; it is never published. */
export interface NewsListItem {
  article_id: string;
  title: string;
  publisher: string;
  source_id: string | null;
  url: string;
  canonical_url: string | null;
  published_at: string | null;
  fetched_at: string;
  is_official_release: boolean;
  is_duplicate: boolean;
  duplicate_of: string | null;
  syndicated_from: string | null;
  status: ProcessingStatus;
  sentiment: SentimentPrediction | null;
  event_types: EventType[];
  entity_ids: string[];
  /** Short preview only; the explorer must not imply it is the full text. */
  snippet: string | null;
}

export interface NewsDetail extends NewsListItem {
  content: string;
  language: string;
  content_hash: string;
  entities: EntityPrediction[];
  entity_sentiments: EntitySentimentPrediction[];
  events: EventPrediction[];
  limitations: string[];
  /** Other articles judged to be the same story (model-inferred). */
  duplicates: NewsRelation[];
  /** Articles this one was syndicated from / to (provenance). */
  syndications: NewsRelation[];
}

export interface NewsRelation {
  article_id: string;
  title: string;
  publisher: string;
  url: string;
  published_at: string | null;
  /** Model-inferred relation. Always labelled as such in the UI. */
  method: string | null;
  score: number | null;
  reason: string | null;
}

export interface EntitySummary {
  entity_id: string;
  canonical_name: string;
  entity_type: EntityType;
  aliases: string[];
  mention_count: number;
  /** Mentions the resolver could not confidently attach to one entity. */
  ambiguous_mention_count: number;
  first_seen_at: string | null;
  last_seen_at: string | null;
  description: string | null;
}

export interface EntityMention {
  article_id: string;
  article_title: string;
  publisher: string;
  url: string;
  published_at: string | null;
  span: EntitySpan;
  sentiment: SentimentLabel | null;
  confidence: number;
  resolution_method: string | null;
}

export interface EntityDetail extends EntitySummary {
  aliases_table: EntityAlias[];
  mentions: EntityMention[];
  related_events: EventListItem[];
  sentiment_trend: SentimentTrendPoint[];
  /** Mentions where the resolver flagged ambiguity, counted separately. */
  ambiguous_mentions: EntityMention[];
  limitations: string[];
}

export interface EntityAlias {
  alias: string;
  source: string;
  confidence: number | null;
  first_seen_at: string | null;
}

export interface TimelineEntry {
  /** Which clock this entry sits on — these are never conflated. */
  published_at: string | null;
  event_date: string | null;
  processed_at: string | null;
  article_id: string;
  title: string;
  publisher: string;
  url: string;
  event_type: EventType | null;
  sentiment: SentimentLabel | null;
  /** True when this article is judged to be new coverage, not a repeat. */
  is_new_coverage: boolean;
  is_duplicate: boolean;
  evidence: EvidenceSpan[];
}

export interface EventListItem {
  event_id: string;
  event_type: EventType;
  title: string;
  /** The three dates are stored and rendered separately, never merged. */
  event_date: string | null;
  publish_date: string | null;
  processing_date: string | null;
  article_count: number;
  new_article_count: number;
  repeated_article_count: number;
  entity_ids: string[];
  mean_confidence: number | null;
  model: ModelRef | null;
}

export interface EventDetail extends EventListItem {
  entities: EntityPrediction[];
  /** Ordered cluster timeline. */
  timeline: TimelineEntry[];
  /** Coverage judged to be the first report of this event. */
  new_coverage: TimelineEntry[];
  /** Coverage judged to repeat an earlier report. Model-inferred, not fact. */
  repeated_coverage: TimelineEntry[];
  /** What changed since the earliest article — model-generated diff. */
  whats_new: WhatsNewItem[];
  dedup_method: string | null;
  limitations: string[];
  evidence: EvidenceSpan[];
}

export interface WhatsNewItem {
  label: string;
  detail: string;
  article_id: string | null;
  evidence: EvidenceSpan[];
  /** Always "model_inferred" — the diff is not a verified fact. */
  source: string;
}

export interface TopicCount {
  topic: string;
  count: number;
  delta: number | null;
}

export interface FreshnessBucket {
  bucket: string;
  count: number;
  share: number;
}

export interface FreshnessReport {
  generated_at: string;
  last_ingestion_at: string | null;
  median_lag_minutes: number | null;
  buckets: FreshnessBucket[];
  stale_sources: string[];
}

export interface NarrativeSummary {
  narrative_id: string;
  title: string;
  description: string;
  started_at: string;
  last_activity_at: string;
  intensity: number;
  intensity_change: number;
  sentiment_shift: number | null;
  dominant_sentiment: SentimentLabel;
  top_entity_ids: string[];
  article_count: number;
  severity: "low" | "medium" | "high";
}

export interface Watchlist {
  watchlist_id: string;
  name: string;
  description: string | null;
  entity_ids: string[];
  keywords: string[];
  event_types: EventType[];
  /** The threshold actually in force. The UI must show this number. */
  intensity_threshold: number;
  sentiment_shift_threshold: number;
  created_at: string;
  enabled: boolean;
}

export interface WatchlistAlert {
  alert_id: string;
  watchlist_id: string;
  watchlist_name: string;
  narrative_id: string;
  title: string;
  /** Why this fired — includes the threshold value used. */
  reason: string;
  triggered_at: string;
  observed_intensity: number;
  threshold_used: number;
  severity: "low" | "medium" | "high";
  article_ids: string[];
}

export interface Citation {
  article_id: string;
  url: string;
  quote: string;
  score: number;
}

export interface CopilotAnswer {
  answer: string;
  citations: Citation[];
  /** True when the model declined to answer for lack of indexed evidence. */
  abstained: boolean;
  model: ModelRef | null;
  limitations: string[];
  latency_ms: number | null;
}

export interface LeaderboardRow {
  rank: number;
  model: string;
  version: string;
  task: string;
  framework: string;
  primary_metric: string;
  primary_value: number;
  metrics: Record<string, number>;
  calibrated: boolean;
  is_baseline: boolean;
  notes: string | null;
}

export interface MetricEstimate {
  metric: string;
  value: number;
  /** Confidence interval is rendered as a range, never as a bare point. */
  ci_low: number;
  ci_high: number;
  ci_level: number;
  n: number;
}

export interface SliceMetric {
  slice: string;
  slice_kind: string;
  metrics: MetricEstimate[];
  n: number;
}

export interface EvaluationError {
  item_id: string;
  article_id: string;
  url: string | null;
  task: string;
  text: string;
  gold: string;
  predicted: string;
  error_category: string;
  split: string;
  model: ModelRef | null;
}

export interface EvaluationSummary {
  run_id: string;
  generated_at: string;
  dataset: string;
  dataset_version: string;
  split: string;
  n_items: number;
  metrics: MetricEstimate[];
  slices: SliceMetric[];
  abstention_rate: number | null;
  notes: string[];
}

export interface ModelComparison {
  task: string;
  metric: string;
  versions: Array<{
    name: string;
    version: string;
    value: number;
    ci_low: number;
    ci_high: number;
    n: number;
    calibrated: boolean;
  }>;
}

// ---------------------------------------------------------------------------
// Request payloads
// ---------------------------------------------------------------------------

export interface AnalyzeRequest {
  text: string;
  language?: string;
}

export interface CopilotAskRequest {
  question: string;
  /** Optional scope narrowing; all fields map to /news filters. */
  publisher?: string;
  date_from?: string;
  date_to?: string;
  entity?: string;
  event_type?: EventType;
  top_k?: number;
}

export interface WatchlistCreateRequest {
  name: string;
  description?: string;
  entity_ids?: string[];
  keywords?: string[];
  event_types?: EventType[];
  intensity_threshold?: number;
  sentiment_shift_threshold?: number;
}

// ---------------------------------------------------------------------------
// API error envelope
// ---------------------------------------------------------------------------

export interface ApiErrorBody {
  detail?: string | { msg?: string; loc?: Array<string | number>; type?: string }[];
  error?: string;
  message?: string;
  status_code?: number;
}

// ---------------------------------------------------------------------------
// Query filter shapes
// ---------------------------------------------------------------------------

export interface NewsFilters {
  publisher?: string;
  date_from?: string;
  date_to?: string;
  entity?: string;
  event_type?: EventType | "";
  sentiment?: SentimentLabel | "";
  q?: string;
  page?: number;
  page_size?: number;
}

export interface EventFilters {
  event_type?: EventType | "";
  entity?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}

export interface EntityFilters {
  entity_type?: EntityType | "";
  q?: string;
  page?: number;
  page_size?: number;
}

// ---------------------------------------------------------------------------
// Runtime narrowing helpers (the API is external; do not trust it blindly)
// ---------------------------------------------------------------------------

export function isSentimentLabel(value: unknown): value is SentimentLabel {
  return typeof value === "string" && (SENTIMENT_LABELS as readonly string[]).includes(value);
}

export function isEntityType(value: unknown): value is EntityType {
  return typeof value === "string" && (ENTITY_TYPES as readonly string[]).includes(value);
}

export function isEventType(value: unknown): value is EventType {
  return typeof value === "string" && (EVENT_TYPES as readonly string[]).includes(value);
}

export function isProcessingStatus(value: unknown): value is ProcessingStatus {
  return typeof value === "string" && (PROCESSING_STATUSES as readonly string[]).includes(value);
}

/** Narrows an array of unknown strings to EventType[], dropping unrecognised values. */
export function toEventTypes(values: readonly unknown[] | null | undefined): EventType[] {
  if (!values) return [];
  return values.filter(isEventType);
}

/**
 * Product wording lives in ./constants.ts. Re-exported here for convenience so
 * existing imports from "@/lib/schemas" keep working.
 */
export {
  ABSTENTION_TEXT,
  COVERAGE_MEASUREMENT_LABEL,
  DEDUP_INFERRED_NOTE as DEDUP_NOTE,
  DISCLAIMER_TEXT,
  EVIDENCE_SPAN_NOTE,
} from "./constants";
