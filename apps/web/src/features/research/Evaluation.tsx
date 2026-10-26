import { useState } from "react";

import { useEvaluation, useEvaluationErrors } from "../../hooks/useModels";

import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "../../components/states";
import type { EvaluationError } from "../../lib/schemas";

/**
 * Evaluation summary: headline metrics with CIs, per-slice breakdown, and a
 * browsable error list. The error browser exists so people can see *what kind
 * of mistakes the model makes* rather than only the aggregate score.
 */
export function EvaluationPage() {
  const evaluation = useEvaluation();
  const errorRows = useEvaluationErrors();
  const [category, setCategory] = useState<string>("all");

  if (evaluation.isLoading) {
    return <LoadingSkeleton variant="cards" label="Loading evaluation" />;
  }
  if (evaluation.isError) {
    return (
      <ErrorState error={evaluation.error} context="the evaluation summary" onRetry={() => void evaluation.refetch()} />
    );
  }
  const summary = evaluation.data;
  if (!summary) {
    return <EmptyState title="No evaluation run" description="Run an evaluation to populate this report." />;
  }

  const rows: EvaluationError[] = errorRows.data ?? [];
  const categories = Array.from(new Set(rows.map((r) => r.error_category))).sort();
  const visible = category === "all" ? rows : rows.filter((r) => r.error_category === category);

  return (
    <div className="space-y-6">
      <SectionHeader
        as="h1"
        eyebrow="Research"
        title="Evaluation summary"
        subtitle={`${summary.dataset} · ${summary.split} split · ${summary.n_items} items · ${summary.dataset_version}`}
      />

      <section className="nfs-card" aria-labelledby="eval-metrics">
        <SectionHeader id="eval-metrics" title="Headline metrics" subtitle="Bootstrap 95% CIs; n is the resample count." />
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {summary.metrics.map((metric) => (
            <div key={metric.metric} className="rounded-md border border-slate-200 bg-white p-3">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{metric.metric}</p>
              <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">{metric.value.toFixed(3)}</p>
              <p className="text-xs tabular-nums text-slate-600">
                CI {metric.ci_level * 100}%: [{metric.ci_low.toFixed(3)}, {metric.ci_high.toFixed(3)}]
              </p>
              <p className="text-[11px] text-slate-400">n={metric.n}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="nfs-card" aria-labelledby="eval-slices">
        <SectionHeader id="eval-slices" title="Slice metrics" subtitle="Same metric computed on defined sub-populations; small slices have wider CIs." />
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-4">Slice</th>
                <th className="py-2 pr-4">Kind</th>
                <th className="py-2 pr-4">n</th>
                <th className="py-2">Metrics</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {summary.slices.map((slice) => (
                <tr key={slice.slice}>
                  <td className="py-2 pr-4 font-medium text-slate-900">{slice.slice}</td>
                  <td className="py-2 pr-4 text-slate-700">{slice.slice_kind}</td>
                  <td className="py-2 pr-4 tabular-nums text-slate-700">{slice.n}</td>
                  <td className="py-2">
                    <ul className="space-y-0.5">
                      {slice.metrics.map((metric) => (
                        <li key={metric.metric} className="tabular-nums">
                          {metric.metric}: {metric.value.toFixed(3)}{" "}
                          <span className="text-slate-500">CI [{metric.ci_low.toFixed(3)}, {metric.ci_high.toFixed(3)}]</span>
                        </li>
                      ))}
                    </ul>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="nfs-card" aria-labelledby="eval-errors">
        <SectionHeader
          id="eval-errors"
          title="Error browser"
          subtitle="Predicted vs gold on sampled errors. Text shown is the eval item's own text, stored with labels and URLs only."
          actions={
            <select
              aria-label="Filter errors by category"
              className="rounded border border-slate-300 px-2 py-1 text-sm"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="all">All categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          }
        />
        <div className="mt-4">
          {errorRows.isLoading ? (
            <LoadingSkeleton variant="table" label="Loading errors" />
          ) : errorRows.isError ? (
            <ErrorState error={errorRows.error} context="the error browser" onRetry={() => void errorRows.refetch()} />
          ) : visible.length === 0 ? (
            <EmptyState title="No sampled errors" description="No errors recorded for this filter." />
          ) : (
            <ul className="divide-y divide-slate-200">
              {visible.slice(0, 50).map((error) => (
                <li key={error.item_id} className="py-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="rounded bg-slate-100 px-2 py-0.5 font-medium text-slate-700">{error.error_category}</span>
                    <span className="text-slate-700">gold: <strong>{error.gold}</strong></span>
                    <span className="text-slate-700">predicted: <strong>{error.predicted}</strong></span>
                    <span className="text-slate-500">{error.split} · {error.task}</span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-slate-800">{error.text}</p>
                  {error.url ? (
                    <a href={error.url} target="_blank" rel="noopener noreferrer" className="text-xs text-brand-800 underline-offset-2 hover:underline">
                      source article
                    </a>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {summary.notes.length > 0 ? (
        <section className="nfs-card">
          <SectionHeader title="Run notes" />
          <ul className="mt-2 list-disc pl-5 text-xs text-slate-700">
            {summary.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
