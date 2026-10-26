import { useLeaderboard } from "../../hooks/useModels";

import { CalibrationChip } from "../../components/ModelBadge";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "../../components/states";
import { formatMetricWithCi } from "../../lib/format";

/**
 * Public leaderboard on NaijaFin-Bench. Baselines are marked as such so a
 * submission is never silently compared against a weak baseline only.
 */
export function LeaderboardPage() {
  const leaderboard = useLeaderboard();

  return (
    <div className="space-y-6">
      <SectionHeader
        as="h1"
        eyebrow="Research"
        title="NaijaFin-Bench leaderboard"
        subtitle="Metrics with bootstrap confidence intervals on the locked test split. Baselines are labelled."
      />

      <section className="nfs-card" aria-labelledby="leaderboard-table">
        <SectionHeader
          id="leaderboard-table"
          title="Ranked entries"
          subtitle="Ties within overlapping CIs are genuine ties — we do not crown a single winner."
        />
        <div className="mt-4">
          {leaderboard.isLoading ? (
            <LoadingSkeleton variant="table" label="Loading leaderboard" />
          ) : leaderboard.isError ? (
            <ErrorState error={leaderboard.error} context="the leaderboard" onRetry={() => void leaderboard.refetch()} />
          ) : (leaderboard.data ?? []).length === 0 ? (
            <EmptyState title="No entries yet" description="Run an evaluation to populate this leaderboard." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                    <th className="py-2 pr-3">Rank</th>
                    <th className="py-2 pr-3">Model</th>
                    <th className="py-2 pr-3">Task</th>
                    <th className="py-2 pr-3">Metric</th>
                    <th className="py-2 pr-3">Value (95% CI)</th>
                    <th className="py-2">Type</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(leaderboard.data ?? []).map((row) => (
                    <tr key={`${row.model}-${row.version}-${row.rank}`}>
                      <td className="py-2 pr-3 tabular-nums">{row.rank}</td>
                      <td className="py-2 pr-3">
                        <div className="font-medium text-slate-900">
                          {row.model} <span className="text-slate-500">v{row.version}</span>
                        </div>
                        <div className="text-[11px] text-slate-500">
                          {row.framework}
                          {row.notes ? ` · ${row.notes}` : ""}
                        </div>
                      </td>
                      <td className="py-2 pr-3 text-slate-700">{row.task}</td>
                      <td className="py-2 pr-3 text-slate-700">{row.primary_metric}</td>
                      <td className="py-2 pr-3 tabular-nums text-slate-900">
                        {formatMetricWithCi(row.primary_value, row.metrics[`${row.primary_metric}_ci_low`] ?? row.primary_value, row.metrics[`${row.primary_metric}_ci_high`] ?? row.primary_value, 0.95)}
                      </td>
                      <td className="py-2">
                        {row.is_baseline ? (
                          <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700">baseline</span>
                        ) : (
                          <span className="rounded bg-brand-50 px-2 py-0.5 text-xs text-brand-900">entry</span>
                        )}
                        <span className="ml-1"><CalibrationChip calibrated={row.calibrated} /></span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
