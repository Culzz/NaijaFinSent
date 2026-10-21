import { Link } from "react-router-dom";

import { EmptyState } from "../components/states";

/** 404 for the research console. */
export function NotFound() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold tracking-tight text-slate-900">Page not found</h1>
      <EmptyState
        title="That route does not exist"
        description="The link may be stale, or the feature may live under a different path."
        hint="Use the navigation on the left, or start from the overview."
        action={
          <Link
            to="/"
            className="rounded border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
          >
            Go to the overview
          </Link>
        }
      />
    </div>
  );
}
