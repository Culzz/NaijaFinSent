import { useState } from "react";

import { EvidenceList } from "../../components/EvidenceSpan";
import { ModelBadge, ProbabilityBars } from "../../components/ModelBadge";
import { PredictionBadge, EntityTypeBadge, EventTypeBadge } from "../../components/PredictionBadge";
import { CoverageTag, StatCard } from "../../components/StatCard";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "../../components/states";

import { useAnalyze } from "../../hooks/useAnalyze";
import type { AnalysisResult } from "../../lib/schemas";
import { SAMPLE_TEXTS } from "./samples";

/**
 * Live playground: paste text, run the pipeline, inspect every stage with its
 * evidence spans and model badge. Uses the same api client as production.
 */
export function AnalyzePlayground() {
  const [text, setText] = useState(SAMPLE_TEXTS[0] ?? "");
  const analyze = useAnalyze();
  const result = analyze.data as AnalysisResult | undefined;

  return (
    <div className="space-y-6">
      <SectionHeader
        as="h1"
        eyebrow="Playground"
        title="Analyze your own text"
        subtitle="Runs the live pipeline on text you paste. Predictions describe language in the text — not advice."
        actions={<CoverageTag />}
      />

      <section className="nfs-card">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!text.trim()) return;
            analyze.mutate({ text });
          }}
        >
          <label htmlFor="playground-text" className="block text-sm font-medium text-slate-800">
            Article text
          </label>
          <textarea
            id="playground-text"
            className="min-h-40 w-full rounded border border-slate-300 px-3 py-2 text-sm"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            {SAMPLE_TEXTS.map((sample, index) => (
              <button
                key={index}
                type="button"
                onClick={() => setText(sample)}
                className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
              >
                Example {index + 1}
              </button>
            ))}
          </div>
          <button
            type="submit"
            disabled={analyze.isPending}
            className="rounded bg-brand-800 px-4 py-2 text-sm font-medium text-white hover:bg-brand-900 disabled:opacity-60"
          >
            {analyze.isPending ? "Analyzing…" : "Run analysis"}
          </button>
        </form>
      </section>

      <div aria-live="polite">
        {analyze.isPending ? (
          <LoadingSkeleton variant="cards" label="Running the pipeline" />
        ) : analyze.isError ? (
          <ErrorState error={analyze.error} context="the analysis playground" onRetry={() => void analyze.reset()} />
        ) : result ? (
          <ResultGrid result={result} />
        ) : (
          <EmptyState
            title="No result yet"
            description="Paste text above and run the pipeline: sentiment, entities, and events will show with their evidence spans."
          />
        )}
      </div>
    </div>
  );
}

function ResultGrid({ result }: { result: AnalysisResult }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Pipeline status" value={result.status} hint={result.limitations?.[0]} />
        <StatCard label="Sentiment" value={result.sentiment?.label ?? "—"} hint={result.sentiment?.model?.name} />
        <StatCard label="Entities" value={result.entities.length} hint="model-tagged spans" />
        <StatCard label="Events" value={result.events.length} hint="typed triggers with evidence" />
      </div>

      <section className="nfs-card">
        <SectionHeader
          title="Document sentiment"
          subtitle="Probabilities show the full distribution so a near-uniform run is visible, not hidden."
          actions={result.sentiment?.model ? <ModelBadge model={result.sentiment.model} /> : undefined}
        />
        <div className="mt-3">
          <PredictionBadge label={result.sentiment?.label ?? null} confidence={result.sentiment?.confidence} size="md" />
          <div className="mt-2">
            <ProbabilityBars probabilities={result.sentiment?.probabilities} />
          </div>
          <div className="mt-3">
            <EvidenceList
              spans={result.sentiment?.evidence ?? []}
              model={result.sentiment?.model}
              emptyMessage="No evidence stored for this run."
            />
          </div>
        </div>
      </section>

      <section className="nfs-card">
        <SectionHeader
          title="Entities"
          subtitle="Resolved mentions: canonical name, type, and model confidence."
        />
        <div className="mt-3 space-y-2">
          {result.entities.length === 0 ? (
            <p className="text-sm text-slate-600">No entities found in this text.</p>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {result.entities.map((entity, index) => (
                <li key={`${entity.span.start}-${index}`} className="flex items-center gap-1.5 rounded border border-slate-200 bg-white px-2 py-1">
                  <EntityTypeBadge type={entity.span.entity_type} size="sm" />
                  <span className="text-sm text-slate-800">{entity.span.text}</span>
                  {entity.canonical_name && entity.canonical_name !== entity.span.text ? (
                    <span className="text-xs text-slate-500">→ {entity.canonical_name}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="nfs-card">
        <SectionHeader
          title="Events"
          subtitle="Typed event mentions with the exact sentences that triggered them."
        />
        <div className="mt-3 space-y-3">
          {result.events.length === 0 ? (
            <p className="text-sm text-slate-600">No events detected in this text.</p>
          ) : (
            result.events.map((event, index) => (
              <div key={`${event.event_type}-${index}`} className="rounded-md border border-slate-200 bg-white p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <EventTypeBadge type={event.event_type} />
                  <span className="text-xs text-slate-600">
                    confidence {event.confidence ? `${Math.round(event.confidence * 100)}%` : "—"}
                  </span>
                  <ModelBadge model={event.model} />
                </div>
                <div className="mt-2">
                  <EvidenceList spans={event.evidence} model={event.model} />
                </div>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
