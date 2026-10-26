import { useState } from "react";

import { CoverageTag } from "../../components/StatCard";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "../../components/states";
import {
  useAlerts,
  useCreateWatchlist,
  useNarratives,
  useWatchlists,
} from "../../hooks/useWatchlists";
import { COVERAGE_MEASUREMENT_EXPLANATION, WHATS_NEW_INFERRED_NOTE } from "../../lib/constants";
import { formatNumber, formatPercent } from "../../lib/format";
import type { NarrativeSummary } from "../../lib/schemas";

const SEVERITY_STYLES: Record<NarrativeSummary["severity"], string> = {
  low: "bg-slate-100 text-slate-700 border-slate-300",
  medium: "bg-amber-50 text-amber-900 border-amber-300",
  high: "bg-rose-50 text-rose-900 border-rose-300",
};

/** Narratives + watchlists. Coverage measurement framing throughout. */
export function NarrativesPage() {
  const narratives = useNarratives();
  const watchlists = useWatchlists();
  const alerts = useAlerts();
  const createWatchlist = useCreateWatchlist();
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState("");

  return (
    <div className="space-y-6">
      <SectionHeader
        as="h1"
        eyebrow="Narratives"
        title="Coverage narratives and watchlists"
        subtitle={COVERAGE_MEASUREMENT_EXPLANATION}
        actions={<CoverageTag />}
      />

      <section className="nfs-card" aria-labelledby="narratives-list">
        <SectionHeader
          id="narratives-list"
          title="Active narratives"
          subtitle="Intensity is a share of articles in the window — a coverage measure, not a market signal."
        />
        <div className="mt-4">
          {narratives.isLoading ? (
            <LoadingSkeleton variant="table" label="Loading narratives" />
          ) : narratives.isError ? (
            <ErrorState error={narratives.error} context="narratives" onRetry={() => void narratives.refetch()} />
          ) : (narratives.data ?? []).length === 0 ? (
            <EmptyState title="No narratives detected" description="The snapshot contains no grouped coverage threads." />
          ) : (
            <ul className="divide-y divide-slate-200">
              {(narratives.data ?? []).map((n) => (
                <li key={n.narrative_id} className="py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{n.title}</p>
                      <p className="text-xs text-slate-600">{n.description}</p>
                    </div>
                    <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${SEVERITY_STYLES[n.severity]}`}>
                      {n.severity}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-4 text-xs text-slate-600">
                    <span>Intensity: {formatPercent(n.intensity)}</span>
                    <span>Change: {formatPercent(n.intensity_change)}</span>
                    <span>Dominant label: {n.dominant_sentiment}</span>
                    <span>Articles: {formatNumber(n.article_count)}</span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-500">{WHATS_NEW_INFERRED_NOTE}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="nfs-card" aria-labelledby="watchlists-panel">
        <SectionHeader
          id="watchlists-panel"
          title="Watchlists"
          subtitle="A watchlist is a saved filter whose thresholds are visible; alerts say exactly which threshold fired."
        />
        <div className="mt-4 space-y-4">
          {watchlists.isLoading ? (
            <LoadingSkeleton variant="table" label="Loading watchlists" />
          ) : watchlists.isError ? (
            <ErrorState error={watchlists.error} context="watchlists" onRetry={() => void watchlists.refetch()} />
          ) : (watchlists.data?.length ?? 0) === 0 ? (
            <EmptyState
              title="No watchlists yet"
              description="Create one below — or through the API — to get alerted when a narrative crosses your thresholds."
            />
          ) : (
            <ul className="divide-y divide-slate-200">
              {(watchlists.data ?? []).map((w) => (
                <li key={w.watchlist_id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">{w.name}</p>
                    <p className="text-xs text-slate-600">
                      Intensity ≥ {formatPercent(w.intensity_threshold)} · sentiment shift ≥{" "}
                      {w.sentiment_shift_threshold} · {w.enabled ? "enabled" : "paused"}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-1 text-xs text-slate-600">
                    {w.keywords.slice(0, 4).map((k) => (
                      <span key={k} className="rounded bg-slate-100 px-2 py-0.5">{k}</span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}

          <form
            className="flex flex-wrap items-end gap-3 border-t border-slate-200 pt-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!name.trim()) return;
              createWatchlist.mutate(
                {
                  name: name.trim(),
                  keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean),
                  intensity_threshold: 0.5,
                  sentiment_shift_threshold: 0.1,
                },
                {
                  onSuccess: () => {
                    setName("");
                    setKeywords("");
                    void watchlists.refetch();
                    void alerts.refetch();
                  },
                },
              );
            }}
          >
            <label className="text-xs font-medium text-slate-700">
              Name
              <input
                className="mt-1 block w-56 rounded border border-slate-300 px-2 py-1.5 text-sm"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="[mock] MPR watch"
                required
              />
            </label>
            <label className="text-xs font-medium text-slate-700">
              Keywords (comma-separated)
              <input
                className="mt-1 block w-72 rounded border border-slate-300 px-2 py-1.5 text-sm"
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                placeholder="monetary policy, naira"
              />
            </label>
            <button
              type="submit"
              disabled={createWatchlist.isPending}
              className="rounded bg-brand-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-900 disabled:opacity-60"
            >
              Create watchlist
            </button>
          </form>
        </div>
      </section>

      <section className="nfs-card" aria-labelledby="alerts-panel">
        <SectionHeader
          id="alerts-panel"
          title="Alerts"
          subtitle="Each alert records the observed value and the exact threshold used, so it is auditable."
        />
        <div className="mt-4">
          {alerts.isLoading ? (
            <LoadingSkeleton variant="table" label="Loading alerts" />
          ) : alerts.isError ? (
            <ErrorState error={alerts.error} context="alerts" onRetry={() => void alerts.refetch()} />
          ) : (alerts.data ?? []).length === 0 ? (
            <EmptyState title="No alerts" description="No watchlist thresholds have fired in this snapshot." />
          ) : (
            <ul className="divide-y divide-slate-200">
              {(alerts.data ?? []).map((a) => (
                <li key={a.alert_id} className="py-3">
                  <p className="text-sm font-semibold text-slate-900">{a.title}</p>
                  <p className="text-xs text-slate-700">{a.reason}</p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Observed {formatPercent(a.observed_intensity)} · threshold {formatPercent(a.threshold_used)} ·{" "}
                    {a.severity}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
