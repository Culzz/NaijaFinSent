/**
 * Typed fetch client for the NaijaFinSent API.
 *
 * Responsibilities:
 *  - base URL from VITE_API_BASE_URL (trailing slash normalised)
 *  - per-request timeout via AbortController
 *  - consistent error envelope parsing into `ApiError`
 *  - `useQuery`-friendly errors: `ApiError` carries `status` and `isRetryable`
 *  - optional mock transport behind VITE_USE_MOCKS (default OFF)
 *
 * Nothing in this module interprets data. It only moves bytes.
 */

import type {
  AnalysisResult,
  AnalyzeRequest,
  ApiErrorBody,
  CopilotAnswer,
  CopilotAskRequest,
  EntityDetail,
  EntityFilters,
  EntitySummary,
  EvaluationSummary,
  EventCount,
  EventDetail,
  EventFilters,
  EventListItem,
  FreshnessReport,
  Granularity,
  HealthStatus,
  LeaderboardRow,
  ModelComparison,
  ModelInfo,
  NarrativeSummary,
  NewsDetail,
  NewsFilters,
  NewsListItem,
  Page,
  SentimentTrendPoint,
  TopicCount,
  Watchlist,
  WatchlistAlert,
  WatchlistCreateRequest,
} from "./schemas";
import { mockTransport } from "../mocks/transport";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

function readEnv(key: keyof ImportMetaEnv, fallback: string): string {
  const value = import.meta.env[key];
  return typeof value === "string" && value.length > 0 ? value : fallback;
}

function normaliseBaseUrl(raw: string): string {
  return raw.replace(/\/+$/, "");
}

export const API_BASE_URL = normaliseBaseUrl(
  readEnv("VITE_API_BASE_URL", "http://localhost:8000"),
);

/** Default false: reviewers see the real API unless they opt in. */
export const USE_MOCKS = readEnv("VITE_USE_MOCKS", "false").toLowerCase() === "true";

const DEFAULT_TIMEOUT_MS = Number.parseInt(readEnv("VITE_API_TIMEOUT_MS", "15000"), 10);

export const APP_ENV = readEnv("VITE_APP_ENV", "development");

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

export type ApiErrorKind = "network" | "timeout" | "http" | "parse" | "aborted";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly detail: string | null;
  readonly url: string | null;
  /** True for 408/429/5xx and transient network failures — safe to retry. */
  readonly isRetryable: boolean;

  constructor(init: {
    message: string;
    kind: ApiErrorKind;
    status?: number | null;
    detail?: string | null;
    url?: string | null;
    isRetryable?: boolean;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.kind = init.kind;
    this.status = init.status ?? null;
    this.detail = init.detail ?? null;
    this.url = init.url ?? null;
    this.isRetryable =
      init.isRetryable ??
      (init.kind === "network" ||
        init.kind === "timeout" ||
        (init.status != null && (init.status >= 500 || init.status === 408 || init.status === 429)));
  }

  /** Short, non-technical line suitable for an ErrorState panel. */
  get userMessage(): string {
    switch (this.kind) {
      case "timeout":
        return "The request took too long and was cancelled.";
      case "network":
        return "Could not reach the NaijaFinSent API.";
      case "aborted":
        return "The request was cancelled.";
      case "parse":
        return "The API returned a response we could not read.";
      case "http":
        if (this.status === 404) return "That item was not found in the corpus.";
        if (this.status === 422) return "The API rejected the request parameters.";
        if (this.status === 503) return "The API is up but a dependency is unavailable.";
        return this.detail ?? `The API returned HTTP ${this.status ?? "error"}.`;
      default:
        return this.message;
    }
  }
}

/** True when a thrown value is an ApiError (used by the query retry policy). */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

// ---------------------------------------------------------------------------
// Envelope parsing
// ---------------------------------------------------------------------------

function extractDetail(body: ApiErrorBody | null, fallbackText: string): string {
  if (!body) return fallbackText;
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) {
    // FastAPI validation errors: [{loc, msg, type}]
    const parts = body.detail
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        const loc = Array.isArray(item.loc) ? item.loc.join(".") : "";
        const msg = item.msg ?? "";
        return loc ? `${loc}: ${msg}` : msg;
      })
      .filter((part): part is string => Boolean(part));
    if (parts.length > 0) return parts.join("; ");
  }
  if (typeof body.error === "string") return body.error;
  if (typeof body.message === "string") return body.message;
  return fallbackText;
}

async function parseErrorBody(response: Response): Promise<{ detail: string; body: ApiErrorBody | null }> {
  const text = await response.text().catch(() => "");
  if (!text) return { detail: `${response.status} ${response.statusText}`.trim(), body: null };
  try {
    const parsed = JSON.parse(text) as ApiErrorBody;
    return { detail: extractDetail(parsed, text.slice(0, 500)), body: parsed };
  } catch {
    return { detail: text.slice(0, 500), body: null };
  }
}

// ---------------------------------------------------------------------------
// Query string builder
// ---------------------------------------------------------------------------

export type QueryParams = Record<
  string,
  string | number | boolean | null | undefined | Array<string | number>
>;

export function buildQuery(params: QueryParams | undefined): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) search.append(key, String(item));
    } else {
      search.append(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

// ---------------------------------------------------------------------------
// Core request
// ---------------------------------------------------------------------------

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  params?: QueryParams;
  timeoutMs?: number;
  signal?: AbortSignal;
  /** Overrides VITE_USE_MOCKS for a single call (tests, fixtures). */
  useMocks?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, params, timeoutMs = DEFAULT_TIMEOUT_MS, signal } = options;
  const shouldMock = options.useMocks ?? USE_MOCKS;

  if (shouldMock) {
    // The mock transport mirrors the real surface (including paged envelopes)
    // and throws real ApiErrors, so error states are exercisable offline.
    return mockTransport<T>(path, { method, body, params });
  }

  const url = `${API_BASE_URL}${path}${buildQuery(params)}`;

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(new DOMException("timeout", "TimeoutError")), timeoutMs);

  // Bridge a caller-supplied signal into our controller.
  const onExternalAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onExternalAbort, { once: true });
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (error) {
    if (controller.signal.aborted) {
      const reason = controller.signal.reason;
      const timedOut = reason instanceof DOMException && reason.name === "TimeoutError";
      throw new ApiError({
        message: timedOut ? `Request to ${path} timed out` : `Request to ${path} was cancelled`,
        kind: timedOut ? "timeout" : "aborted",
        url,
        isRetryable: timedOut,
      });
    }
    throw new ApiError({
      message: error instanceof Error ? error.message : "Network request failed",
      kind: "network",
      url,
    });
  } finally {
    window.clearTimeout(timeoutId);
    if (signal) signal.removeEventListener("abort", onExternalAbort);
  }

  if (!response.ok) {
    const { detail } = await parseErrorBody(response);
    throw new ApiError({
      message: `HTTP ${response.status} for ${path}`,
      kind: "http",
      status: response.status,
      detail,
      url,
    });
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  if (!text) return undefined as T;

  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError({
      message: `Response from ${path} was not valid JSON`,
      kind: "parse",
      status: response.status,
      url,
    });
  }
}

// ---------------------------------------------------------------------------
// Typed endpoint surface
// ---------------------------------------------------------------------------

/** Health check — used by the shell to show an online/offline indicator. */
export const api = {
  health: (options?: RequestOptions) =>
    request<HealthStatus>("/health", options),

  // --- Analysis -----------------------------------------------------------
  analyze: (payload: AnalyzeRequest, options?: RequestOptions) =>
    request<AnalysisResult>("/analyze", { ...options, method: "POST", body: payload }),

  sentiment: (payload: AnalyzeRequest, options?: RequestOptions) =>
    request<AnalysisResult["sentiment"]>("/sentiment", { ...options, method: "POST", body: payload }),

  entities: (payload: AnalyzeRequest, options?: RequestOptions) =>
    request<AnalysisResult["entities"]>("/entities", { ...options, method: "POST", body: payload }),

  // --- News ---------------------------------------------------------------
  news: (filters: NewsFilters, options?: RequestOptions) =>
    request<Page<NewsListItem>>("/news", { ...options, params: { ...filters } }),

  newsItem: (articleId: string, options?: RequestOptions) =>
    request<NewsDetail>(`/news/${encodeURIComponent(articleId)}`, options),

  // --- Events -------------------------------------------------------------
  events: (filters: EventFilters, options?: RequestOptions) =>
    request<Page<EventListItem>>("/events", { ...options, params: { ...filters } }),

  eventItem: (eventId: string, options?: RequestOptions) =>
    request<EventDetail>(`/events/${encodeURIComponent(eventId)}`, options),

  eventTimeline: (eventId: string, options?: RequestOptions) =>
    request<EventDetail["timeline"]>(`/events/${encodeURIComponent(eventId)}/timeline`, options),

  // --- Entities -----------------------------------------------------------
  entityList: (filters: EntityFilters, options?: RequestOptions) =>
    request<Page<EntitySummary>>("/entities", { ...options, params: { ...filters } }),

  entityItem: (entityId: string, options?: RequestOptions) =>
    request<EntityDetail>(`/entities/${encodeURIComponent(entityId)}`, options),

  entityTimeline: (entityId: string, options?: RequestOptions) =>
    request<SentimentTrendPoint[]>(`/entities/${encodeURIComponent(entityId)}/timeline`, options),

  // --- Analytics ----------------------------------------------------------
  sentimentTrend: (granularity: Granularity, options?: RequestOptions) =>
    request<SentimentTrendPoint[]>("/analytics/sentiment", {
      ...options,
      params: { granularity },
    }),

  topics: (options?: RequestOptions) => request<TopicCount[]>("/analytics/topics", options),

  freshness: (options?: RequestOptions) => request<FreshnessReport>("/analytics/freshness", options),

  eventCounts: (options?: RequestOptions) => request<EventCount[]>("/events/counts", options),

  // --- Models / research --------------------------------------------------
  models: (options?: RequestOptions) => request<ModelInfo[]>("/models", options),

  leaderboard: (options?: RequestOptions) => request<LeaderboardRow[]>("/leaderboard", options),

  evaluation: (options?: RequestOptions) => request<EvaluationSummary>("/evaluation", options),

  modelComparison: (options?: RequestOptions) =>
    request<ModelComparison[]>("/models/compare", options),

  // --- Copilot ------------------------------------------------------------
  copilotAsk: (payload: CopilotAskRequest, options?: RequestOptions) =>
    request<CopilotAnswer>("/copilot/ask", { ...options, method: "POST", body: payload }),

  // --- Watchlists ---------------------------------------------------------
  watchlists: (options?: RequestOptions) => request<Watchlist[]>("/watchlists", options),

  createWatchlist: (payload: WatchlistCreateRequest, options?: RequestOptions) =>
    request<Watchlist>("/watchlists", { ...options, method: "POST", body: payload }),

  evaluateWatchlist: (watchlistId: string, options?: RequestOptions) =>
    request<WatchlistAlert[]>(`/watchlists/${encodeURIComponent(watchlistId)}/evaluate`, {
      ...options,
      method: "POST",
    }),

  // --- Narratives (Release 2) --------------------------------------------
  narratives: (options?: RequestOptions) =>
    request<NarrativeSummary[]>("/narratives", options),

  alerts: (options?: RequestOptions) => request<WatchlistAlert[]>("/alerts", options),
};

export type Api = typeof api;
