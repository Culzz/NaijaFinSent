/**
 * Shared query key factory.
 *
 * Centralising keys keeps invalidation honest: the Analyze playground can
 * invalidate exactly the news it affects, and nothing else.
 */

import type {
  EntityFilters,
  EventFilters,
  Granularity,
  NewsFilters,
} from "../lib/schemas";

function normalise(filters: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!filters) return {};
  const entries = Object.entries(filters)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .sort(([a], [b]) => a.localeCompare(b));
  return Object.fromEntries(entries);
}

export const queryKeys = {
  health: () => ["health"] as const,

  news: {
    all: () => ["news"] as const,
    list: (filters: NewsFilters) => ["news", "list", normalise({ ...filters })] as const,
    detail: (articleId: string) => ["news", "detail", articleId] as const,
  },

  events: {
    all: () => ["events"] as const,
    list: (filters: EventFilters) => ["events", "list", normalise({ ...filters })] as const,
    detail: (eventId: string) => ["events", "detail", eventId] as const,
    timeline: (eventId: string) => ["events", "timeline", eventId] as const,
    counts: () => ["events", "counts"] as const,
  },

  entities: {
    all: () => ["entities"] as const,
    list: (filters: EntityFilters) => ["entities", "list", normalise({ ...filters })] as const,
    detail: (entityId: string) => ["entities", "detail", entityId] as const,
    timeline: (entityId: string) => ["entities", "timeline", entityId] as const,
  },

  analytics: {
    sentiment: (granularity: Granularity) => ["analytics", "sentiment", granularity] as const,
    topics: () => ["analytics", "topics"] as const,
    freshness: () => ["analytics", "freshness"] as const,
  },

  models: {
    all: () => ["models"] as const,
    comparison: () => ["models", "comparison"] as const,
    leaderboard: () => ["models", "leaderboard"] as const,
    evaluation: () => ["models", "evaluation"] as const,
    errors: () => ["models", "evaluation", "errors"] as const,
  },

  narratives: {
    all: () => ["narratives"] as const,
    alerts: () => ["narratives", "alerts"] as const,
    watchlists: () => ["narratives", "watchlists"] as const,
  },

  analyze: (hash: string) => ["analyze", hash] as const,
  copilot: (question: string) => ["copilot", question] as const,
};
