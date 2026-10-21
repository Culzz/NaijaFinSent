import { Component, type ErrorInfo, type ReactNode } from "react";

import { ErrorState } from "../components/states";
import { DISCLAIMER_TEXT } from "../lib/constants";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Top-level error boundary.
 *
 * If a render crashes we still want the reviewer to see the disclaimer, so the
 * fallback re-states it rather than showing a bare stack trace.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Console only: this is a client-side research console, and we do not ship
    // an error-reporting endpoint by default.
    console.error("NaijaFinSent render error", error, info.componentStack);
  }

  private readonly reset = () => this.setState({ error: null });

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <main className="mx-auto max-w-3xl space-y-4 p-6">
        <h1 className="text-xl font-semibold text-slate-900">Something broke while rendering</h1>
        <p className="text-sm text-slate-600">{DISCLAIMER_TEXT}</p>
        <ErrorState
          error={error}
          title="This view failed to render"
          onRetry={this.reset}
        />
        <button
          type="button"
          onClick={() => {
            window.location.href = "/";
          }}
          className="rounded border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
        >
          Go to the overview
        </button>
      </main>
    );
  }
}
