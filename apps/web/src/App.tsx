import { BrowserRouter } from "react-router-dom";

import { AppRouter } from "./app/AppRouter";
import { ErrorBoundary } from "./app/ErrorBoundary";
import { AppProviders } from "./app/providers";

/**
 * Application root.
 *
 * Order matters: the ErrorBoundary wraps the providers so a failure in the
 * query layer still renders the disclaimer-bearing fallback, and the providers
 * wrap the router so every route can use queries and toasts.
 */
export default function App() {
  return (
    <ErrorBoundary>
      <AppProviders>
        <BrowserRouter>
          <AppRouter />
        </BrowserRouter>
      </AppProviders>
    </ErrorBoundary>
  );
}
