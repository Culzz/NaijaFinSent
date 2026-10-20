import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api } from "../lib/api";
import { queryKeys } from "./queryKeys";
import type { HealthStatus } from "../lib/schemas";

/** Health probe. Retries a little more eagerly than data queries. */
export function useHealth(): UseQueryResult<HealthStatus, Error> {
  return useQuery({
    queryKey: queryKeys.health(),
    queryFn: ({ signal }) => api.health({ signal }),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 1,
  });
}
