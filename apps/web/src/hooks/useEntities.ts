import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api } from "../lib/api";
import { queryKeys } from "./queryKeys";
import type {
  EntityDetail,
  EntityFilters,
  EntitySummary,
  Page,
  SentimentTrendPoint,
} from "../lib/schemas";

export function useEntities(
  filters: EntityFilters,
): UseQueryResult<Page<EntitySummary>, Error> {
  return useQuery({
    queryKey: queryKeys.entities.list(filters),
    queryFn: ({ signal }) => api.entityList(filters, { signal }),
    placeholderData: (previous) => previous,
  });
}

export function useEntity(entityId: string | undefined): UseQueryResult<EntityDetail, Error> {
  return useQuery({
    queryKey: queryKeys.entities.detail(entityId ?? "none"),
    queryFn: ({ signal }) => api.entityItem(entityId as string, { signal }),
    enabled: Boolean(entityId),
  });
}

export function useEntityTimeline(
  entityId: string | undefined,
): UseQueryResult<SentimentTrendPoint[], Error> {
  return useQuery({
    queryKey: queryKeys.entities.timeline(entityId ?? "none"),
    queryFn: ({ signal }) => api.entityTimeline(entityId as string, { signal }),
    enabled: Boolean(entityId),
  });
}
