import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api } from "../lib/api";
import { queryKeys } from "./queryKeys";
import { mockEvaluationErrorRows } from "../mocks/transport";
import { USE_MOCKS } from "../lib/api";
import type {
  EvaluationError,
  EvaluationSummary,
  LeaderboardRow,
  ModelComparison,
  ModelInfo,
} from "../lib/schemas";

export function useModels(): UseQueryResult<ModelInfo[], Error> {
  return useQuery({
    queryKey: queryKeys.models.all(),
    queryFn: ({ signal }) => api.models({ signal }),
    staleTime: 5 * 60_000,
  });
}

export function useModelComparison(): UseQueryResult<ModelComparison[], Error> {
  return useQuery({
    queryKey: queryKeys.models.comparison(),
    queryFn: ({ signal }) => api.modelComparison({ signal }),
    staleTime: 5 * 60_000,
  });
}

export function useLeaderboard(): UseQueryResult<LeaderboardRow[], Error> {
  return useQuery({
    queryKey: queryKeys.models.leaderboard(),
    queryFn: ({ signal }) => api.leaderboard({ signal }),
    staleTime: 5 * 60_000,
  });
}

export function useEvaluation(): UseQueryResult<EvaluationSummary, Error> {
  return useQuery({
    queryKey: queryKeys.models.evaluation(),
    queryFn: ({ signal }) => api.evaluation({ signal }),
    staleTime: 5 * 60_000,
  });
}

/**
 * Evaluation error rows.
 *
 * The mock transport embeds these under `errors` on the evaluation payload, so
 * the shape is the same whether the rows came from the wire or a fixture. If a
 * deployment exposes them on a dedicated route later, only this function
 * changes.
 */
export function useEvaluationErrors(): UseQueryResult<EvaluationError[], Error> {
  return useQuery({
    queryKey: queryKeys.models.errors(),
    queryFn: async ({ signal }): Promise<EvaluationError[]> => {
      if (USE_MOCKS) return mockEvaluationErrorRows;
      const summary = await api.evaluation({ signal });
      const embedded = (summary as unknown as { errors?: EvaluationError[] }).errors;
      return Array.isArray(embedded) ? embedded : [];
    },
    staleTime: 5 * 60_000,
  });
}
