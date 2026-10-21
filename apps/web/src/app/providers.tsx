import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { QueryClient, QueryClientProvider, type QueryClientConfig } from "@tanstack/react-query";

import { ApiError, isApiError } from "../lib/api";
import { cx } from "../lib/cx";

// ---------------------------------------------------------------------------
// Toast context — a tiny global error surface
// ---------------------------------------------------------------------------

export interface Toast {
  id: number;
  title: string;
  description?: string;
  tone: "error" | "info";
}

interface ToastContextValue {
  toasts: Toast[];
  pushToast: (toast: Omit<Toast, "id">) => void;
  dismissToast: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside <AppProviders>.");
  return context;
}

function ToastRegion() {
  const { toasts, dismissToast } = useToast();

  if (toasts.length === 0) return null;

  return (
    <div
      className="nfs-no-print pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2"
      role="region"
      aria-label="Notifications"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role="alert"
          className={cx(
            "pointer-events-auto flex items-start gap-3 rounded-md border p-3 shadow-sm",
            toast.tone === "error" ? "border-rose-300 bg-rose-50" : "border-slate-300 bg-white",
          )}
        >
          <div className="min-w-0 flex-1">
            <p
              className={cx(
                "text-sm font-semibold",
                toast.tone === "error" ? "text-rose-900" : "text-slate-900",
              )}
            >
              {toast.title}
            </p>
            {toast.description ? (
              <p
                className={cx(
                  "mt-0.5 text-xs",
                  toast.tone === "error" ? "text-rose-800" : "text-slate-600",
                )}
              >
                {toast.description}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={() => dismissToast(toast.id)}
            aria-label="Dismiss notification"
            className={cx(
              "shrink-0 rounded p-0.5 focus-visible:outline-none focus-visible:ring-2",
              toast.tone === "error"
                ? "text-rose-700 hover:bg-rose-100 focus-visible:ring-rose-500"
                : "text-slate-500 hover:bg-slate-100 focus-visible:ring-brand-600",
            )}
          >
            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
          </button>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Retry policy
// ---------------------------------------------------------------------------

/**
 * Retry only transient failures, and never retry a request the API actively
 * rejected (4xx). Retrying a 422 forever is worse than showing the error.
 */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 2) return false;
  if (isApiError(error)) return error.isRetryable;
  if (error instanceof DOMException && error.name === "AbortError") return false;
  return true;
}

function retryDelay(attemptIndex: number): number {
  // Exponential backoff with jitter, capped so the UI stays responsive.
  const base = Math.min(1000 * 2 ** attemptIndex, 8000);
  return base + Math.random() * 250;
}

function createQueryClient(onError: (error: unknown) => void): QueryClient {
  const config: QueryClientConfig = {
    defaultOptions: {
      queries: {
        // Corpus data changes on an ingestion schedule, not per second.
        staleTime: 60_000,
        gcTime: 5 * 60_000,
        retry: shouldRetry,
        retryDelay,
        refetchOnWindowFocus: false,
        refetchOnReconnect: true,
        // Errors are surfaced per-view AND globally; see onError below.
        throwOnError: false,
      },
      mutations: {
        retry: false,
      },
    },
  };

  const client = new QueryClient(config);

  // The QueryClient constructor cannot take a global onError, so we attach a
  // cache-level subscription. Errors are still rendered inline by each view;
  // the toast is a secondary signal for failures the user did not trigger.
  client.getQueryCache().config.onError = (error) => onError(error);

  return client;
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AppProviders({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismissToast = useCallback((id: number) => {
    setToasts((previous) => previous.filter((toast) => toast.id !== id));
  }, []);

  const pushToast = useCallback(
    (toast: Omit<Toast, "id">) => {
      const id = Date.now() + Math.floor(Math.random() * 1000);
      setToasts((previous) => [...previous.slice(-2), { ...toast, id }]);
      window.setTimeout(() => dismissToast(id), 8000);
    },
    [dismissToast],
  );

  const [queryClient] = useState(() =>
    createQueryClient((error) => {
      // Aborted requests are user-initiated navigation, not failures.
      if (isApiError(error) && error.kind === "aborted") return;
      const message = isApiError(error)
        ? error.userMessage
        : error instanceof Error
          ? error.message
          : "An unexpected error occurred.";
      pushToast({
        title: "Request failed",
        description: message,
        tone: "error",
      });
    }),
  );

  // Clear toasts on unmount so a hot reload never leaves stale ones behind.
  useEffect(() => () => setToasts([]), []);

  const value = useMemo<ToastContextValue>(
    () => ({ toasts, pushToast, dismissToast }),
    [toasts, pushToast, dismissToast],
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ToastContext.Provider value={value}>
        {children}
        <ToastRegion />
      </ToastContext.Provider>
    </QueryClientProvider>
  );
}

export { ApiError };
