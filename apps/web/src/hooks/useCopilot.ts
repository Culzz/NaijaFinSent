import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { api } from "../lib/api";
import type { CopilotAnswer, CopilotAskRequest } from "../lib/schemas";

/**
 * Copilot questions are asked only on demand — never auto-fired — so the user
 * always knows a model generated the framing they are reading.
 */
export function useCopilot(): UseMutationResult<CopilotAnswer, Error, CopilotAskRequest> {
  return useMutation({
    mutationFn: (payload: CopilotAskRequest) => api.copilotAsk(payload),
    retry: 0,
  });
}
