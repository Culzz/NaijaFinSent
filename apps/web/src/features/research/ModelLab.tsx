import { useModelComparison, useModels } from "../../hooks/useModels";

import { ModelBadge } from "../../components/ModelBadge";
import { CoverageTag } from "../../components/StatCard";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "../../components/states";
import { formatMetricWithCi } from "../../lib/format";

/**
 * Model lab: which models are registered, and how versions compare side by
 * side. Every metric carries its bootstrap CI — a bare point estimate is
 * never shown alone (docs/MODEL_CARD.md).
 */
export function ModelLab() {
  const models = useModels();
  const comparison = useModelComparison();

  return (
    <div className="space-y-6">
      <SectionHeader
        as="h1"
        eyebrow="Research"
        title="Model lab"
        subtitle="Registered models and version comparisons. CIs are bootstrap resamples on the locked eval split."
        actions={<CoverageTag />}
      />

      <section className="nfs-card" aria-labelledby="lab-registry">
        <SectionHeader id="lab-registry" title="Registered models" subtitle="Serving registry — model cards live in docs/MODEL_CARD.md." />
        <div className="mt-4">
          {models.isLoading ? (
            <LoadingSkeleton variant="table" label="Loading models" />
          ) : models.isError ? (
            <ErrorState error={models.error} context="the model registry" onRetry={() => void models.refetch()} />
          ) : (models.data ?? []).length === 0 ? (
            <EmptyState title="No models registered" description="Train and register models to see them here." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                    <th className="py-2 pr-4">Model</th>
                    <th className="py-2 pr-4">Task</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2">Calibration</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(models.data ?? []).map((m) => (
                    <tr key={`${m.name}-${m.version}`}>
                      <td className="py-2 pr-4">
                        <div className="font-medium text-slate-900">
                          {m.name} <span className="text-slate-500">v{m.version}</span>
                        </div>
                      </td>
                      <td className="py-2 pr-4 text-slate-700">{m.task}</td>
                      <td className="py-2 pr-4 text-slate-700">
                        {m.metrics && Object.keys(m.metrics).length > 0
                          ? Object.entries(m.metrics).slice(0, 2).map(([metric, value]) => `${metric}=${value.toFixed(3)}`).join(" · ")
                          : "—"}
                      </td>
                      <td className="py-2">
                        <ModelBadge model={{ name: m.name, version: m.version, task: m.task, calibrated: false }} showCalibration={false} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      <section className="nfs-card" aria-labelledby="lab-compare">
        <SectionHeader
          id="lab-compare"
          title="Version comparison"
          subtitle="Per-task metric comparison across versions. Differences within the CI overlap should be treated as ties."
        />
        <div className="mt-4 space-y-5">
          {comparison.isLoading ? (
            <LoadingSkeleton variant="chart" label="Loading comparisons" />
          ) : comparison.isError ? (
            <ErrorState error={comparison.error} context="model comparisons" onRetry={() => void comparison.refetch()} />
          ) : (comparison.data ?? []).length === 0 ? (
            <EmptyState title="No comparisons" description="No evaluation comparisons recorded yet." />
          ) : (
            (comparison.data ?? []).map((row) => (
              <div key={`${row.task}-${row.metric}`}>
                <p className="text-sm font-semibold text-slate-900">
                  {row.task} · {row.metric}
                </p>
                <ul className="mt-2 space-y-1">
                  {row.versions.map((v) => (
                    <li key={`${v.name}-${v.version}`} className="flex flex-wrap items-center gap-3 text-sm">
                      <span className="w-64 font-medium text-slate-800">
                        {v.name} <span className="text-slate-500">v{v.version}</span>
                      </span>
                      <span className="tabular-nums text-slate-900">
                        {formatMetricWithCi(v.value, v.ci_low, v.ci_high, 0.95, v.n)}
                      </span>
                      {v.calibrated ? (
                        <span className="rounded bg-emerald-50 px-2 py-0.5 text-xs text-emerald-800">calibrated</span>
                      ) : (
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">uncalibrated</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
