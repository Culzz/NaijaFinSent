import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api } from "../lib/api";
import { queryKeys } from "./queryKeys";
import type {
  EventCount,
  FreshnessReport,
  Granularity,
  SentimentTrendPoint,
  TopicCount,
} from "../lib/schemas";

/** Aggregate language-measurement trend. Never labelled "investor sentiment". */
export function useSentimentTrend(
  granularity: Granularity,
): UseQueryResult<SentimentTrendPoint[], Error> {
  return useQuery({
    queryKey: queryKeys.analytics.sentiment(granularity),
    queryFn: ({ signal }) => api.sentimentTrend(granularity, { signal }),
    placeholderData: (previous) => previous,
  });
}

export function useTopics(): UseQueryResult<TopicCount[], Error> {
  return useQuery({
    queryKey: queryKeys.analytics.topics(),
    queryFn: ({ signal }) => api.topics({ signal }),
  });
}

export function useFreshness(): UseQueryResult<FreshnessReport, Error> {
  return useQuery({
    queryKey: queryKeys.analytics.freshness(),
    queryFn: ({ signal }) => api.freshness({ signal }),
    staleTime: 60_000,
  });
}

export function useEventCounts(): UseQueryResult<EventCount[], Error> {
  return useQuery({
    queryKey: queryKeys.events.counts(),
    queryFn: ({ signal }) => api.eventCounts({ signal }),
  });
}
