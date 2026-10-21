import { NavLink, Outlet, useLocation } from "react-router-dom";

import { DisclaimerBanner, MockDataBanner } from "../components/DisclaimerBanner";
import { cx } from "../lib/cx";
import { APP_ENV, API_BASE_URL, USE_MOCKS } from "../lib/api";
import { useHealth } from "../hooks/useHealth";
import { formatRelative } from "../lib/format";

// ---------------------------------------------------------------------------
// Navigation model
// ---------------------------------------------------------------------------

interface NavItem {
  to: string;
  label: string;
  /** Shown in the sidebar group heading. */
  group: string;
  description: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Overview", group: "Monitor", description: "Recent coverage, events, freshness" },
  { to: "/news", label: "News explorer", group: "Monitor", description: "Filter and read articles with evidence spans" },
  { to: "/sentiment", label: "Coverage sentiment", group: "Monitor", description: "Language measurements over time" },
  { to: "/events", label: "Event explorer", group: "Monitor", description: "Event clusters and timelines" },
  { to: "/entities", label: "Entities", group: "Monitor", description: "Organisations, regulators, people" },
  { to: "/narratives", label: "Narratives", group: "Track", description: "Narrative intensity and watchlists" },
  { to: "/copilot", label: "Copilot", group: "Ask", description: "Ask questions over indexed coverage" },
  { to: "/playground", label: "Analyze playground", group: "Ask", description: "Paste text and inspect predictions" },
  { to: "/research", label: "Model lab", group: "Evaluate", description: "Versions, metrics with CIs, error browser" },
  { to: "/research/leaderboard", label: "Leaderboard", group: "Evaluate", description: "Ranked model runs" },
  { to: "/research/evaluation", label: "Evaluation", group: "Evaluate", description: "Dataset and split summary" },
];

const GROUP_ORDER = ["Monitor", "Track", "Ask", "Evaluate"] as const;

// ---------------------------------------------------------------------------
// Health indicator
// ---------------------------------------------------------------------------

function HealthIndicator() {
  const { data, isError, isLoading, refetch } = useHealth();

  if (USE_MOCKS) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-fuchsia-300 bg-fuchsia-50 px-2 py-0.5 text-[0.7rem] font-medium text-fuchsia-900">
        <span aria-hidden="true" className="h-2 w-2 rounded-full bg-fuchsia-500" />
        fixtures
      </span>
    );
  }

  if (isLoading) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white px-2 py-0.5 text-[0.7rem] text-slate-600">
        <span aria-hidden="true" className="h-2 w-2 animate-pulse rounded-full bg-slate-400" />
        checking API
      </span>
    );
  }

  if (isError || !data) {
    return (
      <button
        type="button"
        onClick={() => void refetch()}
        className="inline-flex items-center gap-1.5 rounded-full border border-rose-300 bg-rose-50 px-2 py-0.5 text-[0.7rem] font-medium text-rose-900 hover:bg-rose-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
        title={`API at ${API_BASE_URL} is not responding. Activate to retry.`}
      >
        <span aria-hidden="true" className="h-2 w-2 rounded-full bg-rose-500" />
        API offline · retry
      </button>
    );
  }

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-brand-300 bg-brand-50 px-2 py-0.5 text-[0.7rem] font-medium text-brand-900"
      title={`Last ingestion: ${formatRelative(data.last_ingestion_at)} · corpus size: ${data.corpus_size ?? "unknown"}`}
    >
      <span aria-hidden="true" className="h-2 w-2 rounded-full bg-brand-600" />
      API {data.status} · v{data.version}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Shell
// ---------------------------------------------------------------------------

export function AppShell() {
  const location = useLocation();

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <a href="#main-content" className="nfs-skip-link">
        Skip to main content
      </a>

      {/* The disclaimer is OUTSIDE <main> so it is present on every route. */}
      <DisclaimerBanner />
      {USE_MOCKS ? <MockDataBanner /> : null}

      <header className="nfs-no-print border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <NavLink
            to="/"
            className="flex items-center gap-2 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2"
          >
            <span
              aria-hidden="true"
              className="flex h-8 w-8 items-center justify-center rounded bg-brand-700 font-bold text-white"
            >
              NF
            </span>
            <span className="flex flex-col leading-tight">
              <span className="text-base font-semibold tracking-tight text-slate-900">
                NaijaFinSent
              </span>
              <span className="text-[0.7rem] text-slate-500">
                measurements of language in news coverage
              </span>
            </span>
          </NavLink>

          <div className="flex items-center gap-3">
            <HealthIndicator />
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-6 lg:flex-row">
        <Sidebar currentPath={location.pathname} />

        <main id="main-content" className="min-w-0 flex-1" tabIndex={-1}>
          <Outlet />
        </main>
      </div>

      <footer className="nfs-no-print border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-4 text-xs text-slate-500">
          <p>
            NaijaFinSent displays measurements of language in published news coverage. Evidence
            spans are supporting text, not causal attribution. Deduplication, clustering, and
            summaries are model-inferred.
          </p>
          <p>
            Environment: <span className="font-mono">{APP_ENV}</span> · API base:{" "}
            <span className="font-mono">{API_BASE_URL}</span>
            {USE_MOCKS ? " · MOCK MODE (synthetic fixtures)" : ""}
          </p>
        </div>
      </footer>
    </div>
  );
}

function Sidebar({ currentPath }: { currentPath: string }) {
  return (
    <nav
      className="nfs-no-print w-full shrink-0 lg:w-60"
      aria-label="Main navigation"
    >
      <div className="space-y-4 lg:sticky lg:top-4">
        {GROUP_ORDER.map((group) => {
          const items = NAV_ITEMS.filter((item) => item.group === group);
          if (items.length === 0) return null;
          return (
            <div key={group}>
              <h2 className="mb-1 px-2 text-[0.65rem] font-semibold uppercase tracking-wider text-slate-400">
                {group}
              </h2>
              <ul className="space-y-0.5">
                {items.map((item) => {
                  const isActive =
                    item.to === "/"
                      ? currentPath === "/"
                      : currentPath === item.to ||
                        (currentPath.startsWith(`${item.to}/`) && item.to !== "/research");
                  return (
                    <li key={item.to}>
                      <NavLink
                        to={item.to}
                        end={item.to === "/"}
                        title={item.description}
                        aria-current={isActive ? "page" : undefined}
                        className={({ isActive: routerActive }) => {
                          const active = routerActive || isActive;
                          return cx(
                            "block rounded px-2 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-1",
                            active
                              ? "bg-brand-50 font-medium text-brand-900 ring-1 ring-inset ring-brand-200"
                              : "text-slate-700 hover:bg-slate-100",
                          );
                        }}
                      >
                        {item.label}
                      </NavLink>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    </nav>
  );
}
