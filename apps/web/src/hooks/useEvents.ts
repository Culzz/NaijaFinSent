import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api } from "../lib/api";
import { queryKeys } from "./queryKeys";
import type { EventCount, EventDetail, EventFilters, EventListItem, Page, TimelineEntry } from "../lib/schemas";

export function useEvents(filters: EventFilters): UseQueryResult<Page<EventListItem>, Error> {
  return useQuery({
    queryKey: queryKeys.events.list(filters),
    queryFn: ({ signal }) => api.events(filters, { signal }),
    placeholderData: (previous) => previous,
  });
}

export function useEventItem(eventId: string | undefined): UseQueryResult<EventDetail, Error> {
  return useQuery({
    queryKey: queryKeys.events.detail(eventId ?? "none"),
    queryFn: ({ signal }) => api.eventItem(eventId as string, { signal }),
    enabled: Boolean(eventId),
  });
}

export function useEventTimeline(
  eventId: string | undefined,
): UseQueryResult<TimelineEntry[], Error> {
  return useQuery({
    queryKey: queryKeys.events.timeline(eventId ?? "none"),
    queryFn: ({ signal }) => api.eventTimeline(eventId as string, { signal }),
    enabled: Boolean(eventId),
  });
}

export function useEventCounts(): UseQueryResult<EventCount[], Error> {
  return useQuery({
    queryKey: queryKeys.events.counts(),
    queryFn: ({ signal }) => api.eventCounts({ signal }),
  });
}
