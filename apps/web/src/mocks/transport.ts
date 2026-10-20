/**
 * Mock transport — serves the synthetic fixtures through the SAME code path as
 * the real API client, including paged envelopes, filters, and real `ApiError`
 * throws. This means loading/empty/error states in the UI are all exercisable
 * with no backend.
 *
 * Activated only when VITE_USE_MOCKS=true (default false).
 */

import { ApiError, type QueryParams } from "../lib/api";
import {
  mockAlerts,
  mockAnalyzeResult,
  mockCopilotAnswer,
  mockEntities,
  mockEntityDetails,
  mockEvaluation,
  mockEvaluationErrors,
  mockEventCounts,
  mockEvents,
  mockEventDetails,
  mockFreshness,
  mockHealth,
  mockLeaderboard,
  mockModelComparison,
  mockModels,
  mockNarratives,
  mockNewsDetails,
  mockNewsList,
  mockSentimentTrend,
  mockTopics,
  mockWatchlists,
} from "./fixtures";
import type {
  AnalysisResult,
  CopilotAnswer,
  EventType,
  NewsListItem,
  Page,
  SentimentLabel,
  Watchlist,
} from "../lib/schemas";
import { EVENT_TYPES } from "../lib/schemas";

interface MockOptions {
  method: string;
  body?: unknown;
  params?: QueryParams;
}

const SIMULATED_LATENCY_MS = 180;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function param(params: QueryParams | undefined, key: string): string | null {
  const value = params?.[key];
  if (value === undefined || value === null || value === "") return null;
  if (Array.isArray(value)) return value.length > 0 ? String(value[0]) : null;
  return String(value);
}

function paginate<T>(items: T[], params: QueryParams | undefined): Page<T> {
  const page = Math.max(1, Number.parseInt(param(params, "page") ?? "1", 10) || 1);
  const pageSize = Math.min(
    100,
    Math.max(1, Number.parseInt(param(params, "page_size") ?? "20", 10) || 20),
  );
  const start = (page - 1) * pageSize;
  return {
    items: items.slice(start, start + pageSize),
    total: items.length,
    page,
    page_size: pageSize,
  };
}

function notFound(path: string): ApiError {
  return new ApiError({
    message: `No mock fixture for ${path}`,
    kind: "http",
    status: 404,
    detail: "This fixture does not exist in the synthetic mock set.",
    url: path,
  });
}

// --- News filtering ---------------------------------------------------------

function filterNews(params: QueryParams | undefined): NewsListItem[] {
  const publisher = param(params, "publisher");
  const dateFrom = param(params, "date_from");
  const dateTo = param(params, "date_to");
  const entity = param(params, "entity");
  const eventType = param(params, "event_type");
  const sentiment = param(params, "sentiment");
  const q = param(params, "q")?.toLowerCase() ?? null;

  return mockNewsList.filter((item) => {
    if (publisher && item.publisher !== publisher) return false;
    if (entity && !item.entity_ids.includes(entity)) return false;
    if (eventType && !item.event_types.includes(eventType as EventType)) return false;
    if (sentiment && item.sentiment?.label !== (sentiment as SentimentLabel)) return false;
    const publishedDate = item.published_at?.slice(0, 10) ?? "";
    if (dateFrom && publishedDate < dateFrom) return false;
    if (dateTo && publishedDate > dateTo) return false;
    if (q) {
      const haystack = `${item.title} ${item.publisher} ${item.snippet ?? ""}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });
}

function filterEvents(params: QueryParams | undefined) {
  const eventType = param(params, "event_type");
  const entity = param(params, "entity");
  const dateFrom = param(params, "date_from");
  const dateTo = param(params, "date_to");

  return mockEvents.filter((event) => {
    if (eventType && event.event_type !== eventType) return false;
    if (entity && !event.entity_ids.includes(entity)) return false;
    const publishedDate = event.publish_date ?? "";
    if (dateFrom && publishedDate < dateFrom) return false;
    if (dateTo && publishedDate > dateTo) return false;
    return true;
  });
}

// --- Dispatch ---------------------------------------------------------------

export async function mockTransport<T>(path: string, options: MockOptions): Promise<T> {
  await delay(SIMULATED_LATENCY_MS + Math.random() * 120);

  const { method, body, params } = options;
  const cleanPath = path.split("?")[0] ?? path;
  const segments = cleanPath.split("/").filter(Boolean);

  // /health
  if (cleanPath === "/health" && method === "GET") return mockHealth as T;

  // /analyze, /sentiment, /entities (POST)
  if (cleanPath === "/analyze") {
    const payload = (body ?? {}) as { text?: string };
    return mockAnalyzeResult(payload.text ?? "") as T;
  }
  if (cleanPath === "/sentiment" && method === "POST") {
    const result = mockAnalyzeResult(((body ?? {}) as { text?: string }).text ?? "");
    return result.sentiment as T;
  }
  if (cleanPath === "/entities" && method === "POST") {
    const result = mockAnalyzeResult(((body ?? {}) as { text?: string }).text ?? "");
    return result.entities as T;
  }

  // /news, /news/counts, /news/{id}
  if (segments[0] === "news") {
    if (segments.length === 1) return paginate(filterNews(params), params) as T;
    if (segments[1] === "counts") {
      return mockEventCounts.map((entry) => ({ event_type: entry.event_type, count: entry.count })) as T;
    }
    const id = segments[1] as string;
    const detail = mockNewsDetails[id];
    if (!detail) throw notFound(cleanPath);
    return detail as T;
  }

  // /events, /events/counts, /events/{id}, /events/{id}/timeline
  if (segments[0] === "events") {
    if (segments.length === 1) return paginate(filterEvents(params), params) as T;
    if (segments[1] === "counts") return mockEventCounts as T;
    const id = segments[1] as string;
    if (segments[2] === "timeline") {
      const detail = mockEventDetails[id];
      if (!detail) throw notFound(cleanPath);
      return detail.timeline as T;
    }
    const detail = mockEventDetails[id];
    if (!detail) throw notFound(cleanPath);
    return detail as T;
  }

  // /entities
  if (segments[0] === "entities" && method === "GET") {
    if (segments.length === 1) {
      const typeFilter = param(params, "entity_type");
      const q = param(params, "q")?.toLowerCase() ?? null;
      const filtered = mockEntities.filter((entity) => {
        if (typeFilter && entity.entity_type !== typeFilter) return false;
        if (q) {
          const haystack = `${entity.canonical_name} ${entity.aliases.join(" ")}`.toLowerCase();
          if (!haystack.includes(q)) return false;
        }
        return true;
      });
      return paginate(filtered, params) as T;
    }
    const id = segments[1] as string;
    if (segments[2] === "timeline") {
      const detail = mockEntityDetails[id];
      if (!detail) throw notFound(cleanPath);
      return detail.sentiment_trend as T;
    }
    const detail = mockEntityDetails[id];
    if (!detail) throw notFound(cleanPath);
    return detail as T;
  }

  // /analytics/*
  if (segments[0] === "analytics") {
    if (segments[1] === "sentiment") {
      const granularity = param(params, "granularity") ?? "day";
      // Period keys are regenerated to match the requested granularity so the
      // chart axis labels stay coherent.
      return mockSentimentTrend.map((point, index) => ({
        ...point,
        period:
          granularity === "month"
            ? point.period.slice(0, 7)
            : granularity === "week"
              ? `W${String(index + 1).padStart(2, "0")} ${point.period.slice(0, 4)}`
              : point.period,
      })) as T;
    }
    if (segments[1] === "topics") return mockTopics as T;
    if (segments[1] === "freshness") return mockFreshness as T;
  }

  // /models, /models/compare (registered before /models/{id} would be)
  if (segments[0] === "models") {
    if (segments[1] === "compare") return mockModelComparison as T;
    return mockModels as T;
  }

  if (cleanPath === "/leaderboard") return mockLeaderboard as T;
  if (cleanPath === "/evaluation") {
    // Expose the error browser rows in a well-known slot so the UI can fetch
    // both without an extra endpoint contract.
    const withErrors = { ...mockEvaluation, errors: mockEvaluationErrors } as unknown as T;
    return withErrors;
  }

  // /copilot/ask
  if (cleanPath === "/copilot/ask" && method === "POST") {
    const question = ((body ?? {}) as { question?: string }).question ?? "";
    return mockCopilotAnswer(question) as T;
  }

  // /watchlists, /watchlists/{id}/evaluate
  if (segments[0] === "watchlists") {
    if (segments.length === 1 && method === "GET") return mockWatchlists as T;
    if (segments.length === 1 && method === "POST") {
      const payload = (body ?? {}) as Partial<Watchlist>;
      const created: Watchlist = {
        watchlist_id: `mock-wl-${Math.floor(Math.random() * 9000 + 1000)}`,
        name: payload.name ?? "[synthetic] New watchlist",
        description: payload.description ?? "[synthetic] Created from fixtures.",
        entity_ids: payload.entity_ids ?? [],
        keywords: payload.keywords ?? [],
        event_types: payload.event_types ?? [],
        intensity_threshold: payload.intensity_threshold ?? 0.5,
        sentiment_shift_threshold: payload.sentiment_shift_threshold ?? 0.1,
        created_at: new Date().toISOString(),
        enabled: true,
      };
      mockWatchlists.push(created);
      return created as T;
    }
    if (segments[2] === "evaluate") {
      const id = segments[1] as string;
      const alerts = mockAlerts.filter((alert) => alert.watchlist_id === id);
      return alerts as T;
    }
  }

  if (cleanPath === "/narratives") return mockNarratives as T;
  if (cleanPath === "/alerts") return mockAlerts as T;

  // Unknown route: exercise the real error UI instead of pretending to work.
  throw notFound(cleanPath);
}

/** Exported so the Model Lab error browser can render fixture errors offline. */
export const mockEvaluationErrorRows = mockEvaluationErrors;

/** Exported so the sentiment filter can offer exactly the mock publishers. */
export const mockPublisherNames: string[] = Array.from(
  new Set(mockNewsList.map((item) => item.publisher)),
).sort();

/** Exported for the free-text filter hint in mock mode. */
export const mockEventTypeOptions: EventType[] = [...EVENT_TYPES];

export type { AnalysisResult, CopilotAnswer };
