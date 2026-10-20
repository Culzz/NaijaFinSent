import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { api } from "../lib/api";
import type { AnalysisResult, AnalyzeRequest } from "../lib/schemas";

/**
 * /analyze is a POST with a body, so it is a mutation rather than a query —
 * but we key it by the text hash so repeat submissions can be cached by the
 * caller if desired. The playground owns the request lifecycle.
 */
export function useAnalyze(): UseMutationResult<AnalysisResult, Error, AnalyzeRequest> {
  return useMutation({
    mutationFn: (payload: AnalyzeRequest) => api.analyze(payload),
    retry: 0,
  });
}
