import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { api } from "../lib/api";
import { queryKeys } from "./queryKeys";
import type {
  NarrativeSummary,
  Watchlist,
  WatchlistAlert,
  WatchlistCreateRequest,
} from "../lib/schemas";

export function useWatchlists(): UseQueryResult<Watchlist[], Error> {
  return useQuery({
    queryKey: queryKeys.narratives.watchlists(),
    queryFn: ({ signal }) => api.watchlists({ signal }),
  });
}

export function useNarratives(): UseQueryResult<NarrativeSummary[], Error> {
  return useQuery({
    queryKey: queryKeys.narratives.all(),
    queryFn: ({ signal }) => api.narratives({ signal }),
    placeholderData: (previous) => previous,
  });
}

export function useAlerts(): UseQueryResult<WatchlistAlert[], Error> {
  return useQuery({
    queryKey: queryKeys.narratives.alerts(),
    queryFn: ({ signal }) => api.alerts({ signal }),
    refetchInterval: 120_000,
  });
}

export function useCreateWatchlist(): UseMutationResult<
  Watchlist,
  Error,
  WatchlistCreateRequest
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: WatchlistCreateRequest) => api.createWatchlist(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.narratives.watchlists() });
    },
    retry: 0,
  });
}

/**
 * Evaluate a watchlist. Alerts returned here are merged into the alert list so
 * the user sees the newly-triggered rows immediately, each carrying the
 * threshold value that was actually applied.
 */
export function useEvaluateWatchlist(): UseMutationResult<WatchlistAlert[], Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (watchlistId: string) => api.evaluateWatchlist(watchlistId),
    onSuccess: (alerts) => {
      queryClient.setQueryData<WatchlistAlert[]>(queryKeys.narratives.alerts(), (previous) => {
        const seen = new Set((previous ?? []).map((alert) => alert.alert_id));
        const merged = [...alerts.filter((alert) => !seen.has(alert.alert_id)), ...(previous ?? [])];
        return merged;
      });
    },
    retry: 0,
  });
}
