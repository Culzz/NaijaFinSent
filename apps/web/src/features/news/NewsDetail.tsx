import { Link, useParams } from "react-router-dom";

import { AnnotatedText, EvidenceList, entityAnnotations } from "../../components/EvidenceSpan";
import {
  ConfidenceMeter,
  LimitationsPanel,
  ModelBadge,
  ProbabilityBars,
} from "../../components/ModelBadge";
import {
  EntityTypeBadge,
  EventTypeBadge,
  PredictionBadge,
  ProvenanceChip,
} from "../../components/PredictionBadge";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "../../components/states";
import { useNewsItem } from "../../hooks/useNews";
import { DEDUP_INFERRED_NOTE, EVIDENCE_SPAN_NOTE } from "../../lib/constants";
import {
  ENTITY_TYPES,
  SENTIMENT_LABELS,
  type EntityType,
} from "../../lib/schemas";
import {
  SENTIMENT_GLOSS,
  entityStyle,
  formatDateTime,
  hostnameOf,
  sentimentStyle,
  statusStyle,
} from "../../lib/format";
import { EntitySwatch } from "../../components/PredictionBadge";

/**
 * Article detail.
 *
 * Shows, in this order: provenance and source link, duplicate/syndication
 * relations, the annotated source text with entity and evidence spans, the
 * sentiment prediction with its model and limitations, and the event frames.
 *
 * There is no attention visualisation anywhere on this page by design.
 */
export function NewsDetailPage() {
  const { articleId } = useParams<{ articleId: string }>();
  const query = useNewsItem(articleId);

  if (query.isLoading) {
    return (
      <div className="space-y-4">
        <LoadingSkeleton rows={2} label="Loading article" />
        <LoadingSkeleton variant="chart" label="Loading article text" />
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="space-y-4">
        <SectionHeader as="h1" title="Article" subtitle="This article could not be loaded." />
        <ErrorState error={query.error} context="this article" onRetry={() => void query.refetch()} />
        <Link
          to="/news"
          className="inline-block rounded border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
        >
          Back to the news explorer
        </Link>
      </div>
    );
  }

  const article = query.data;
  if (!article) {
    return (
      <EmptyState
        title="Article not returned"
        description="The API returned no body for this id."
        action={
          <Link to="/news" className="text-sm font-medium text-brand-800 underline">
            Back to the news explorer
          </Link>
        }
      />
    );
  }

  const status = statusStyle(article.status);
  const annotations = [
    ...entityAnnotations(article.entities),
    ...(article.sentiment?.evidence ?? []).map((span) => ({
      start: span.start,
      end: span.end,
      text: span.text,
      tone: "sentiment" as const,
      sentiment: article.sentiment?.label ?? null,
      label: "Sentiment evidence span. Supporting text, not causal attribution.",
    })),
  ];

  return (
    <div className="space-y-6">
      {/* --- Header ------------------------------------------------------- */}
      <div className="space-y-2">
        <nav aria-label="Breadcrumb" className="text-xs text-slate-500">
          <Link to="/news" className="underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600">
            News
          </Link>
          <span aria-hidden="true" className="mx-1">
            /
          </span>
          <span>Article</span>
        </nav>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">{article.title}</h1>
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
          <span className="font-medium">{article.publisher}</span>
          <span aria-hidden="true">·</span>
          <span>
            published {formatDateTime(article.published_at)}
            <span className="ml-1 text-slate-400">(publish date)</span>
          </span>
          <span aria-hidden="true">·</span>
          <span>
            indexed {formatDateTime(article.fetched_at)}
            <span className="ml-1 text-slate-400">(processing date)</span>
          </span>
          {article.is_official_release ? (
            <span className="rounded bg-brand-50 px-1.5 py-0.5 font-medium text-brand-800 ring-1 ring-inset ring-brand-300">
              official release
            </span>
          ) : null}
          <span className={`rounded px-1.5 py-0.5 font-medium ${status.badge}`} title={status.description}>
            {status.label}
          </span>
        </div>
        <p className="text-xs">
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-brand-800 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
          >
            Read the source article at {hostnameOf(article.url)} ↗
          </a>
          <span className="ml-2 text-slate-500">
            The text below is what the pipeline extracted; always prefer the source.
          </span>
        </p>
      </div>

      {/* --- Partial / failed handling ------------------------------------ */}
      {article.status === "partial" || article.status === "failed" ? (
        <div
          className={`rounded-md border p-3 ${
            article.status === "failed"
              ? "border-rose-300 bg-rose-50 text-rose-900"
              : "border-amber-300 bg-amber-50 text-amber-900"
          }`}
          role="alert"
        >
          <p className="text-sm font-semibold">
            {article.status === "failed"
              ? "The pipeline failed for this article"
              : "The pipeline only partially completed for this article"}
          </p>
          <p className="mt-1 text-xs">{status.description}</p>
        </div>
      ) : null}

      {/* --- Relations ---------------------------------------------------- */}
      <section className="nfs-card" aria-labelledby="relations-heading">
        <SectionHeader
          id="relations-heading"
          title="Duplicate and syndication relations"
          subtitle={DEDUP_INFERRED_NOTE}
          actions={<ProvenanceChip kind="model" />}
        />
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          <RelationList
            title="Judged duplicates"
            emptyText="No article was judged a duplicate of this one."
            rows={article.duplicates}
          />
          <RelationList
            title="Syndicated copies"
            emptyText="No syndicated copies recorded for this article."
            rows={article.syndications}
          />
        </div>
      </section>

      {/* --- Annotated text ---------------------------------------------- */}
      <section className="nfs-card" aria-labelledby="text-heading">
        <SectionHeader
          id="text-heading"
          title="Source text with evidence spans"
          subtitle={EVIDENCE_SPAN_NOTE}
          actions={<EntityLegend />}
        />
        <div className="mt-4">
          <AnnotatedText
            text={article.content}
            annotations={annotations}
            className="max-h-[32rem] overflow-y-auto rounded border border-slate-200 bg-slate-50 p-4"
          />
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Highlighted spans are the text the models keyed on. Shading is used only to locate spans —
          there is no attention or influence visualisation, because attention is not evidence of
          anything.
        </p>
      </section>

      {/* --- Sentiment ----------------------------------------------------- */}
      <section className="nfs-card" aria-labelledby="sentiment-heading">
        <SectionHeader
          id="sentiment-heading"
          title="Language label"
          subtitle="The sentiment label assigned to this article's language, with the evidence that produced it."
        />

        {!article.sentiment ? (
          <div className="mt-3">
            <EmptyState
              title="No sentiment prediction"
              description="Either the pipeline did not reach the sentiment stage, or it failed."
              hint="Check the pipeline status above and the limitations panel below."
            />
          </div>
        ) : (
          <div className="mt-3 grid gap-4 lg:grid-cols-2">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <PredictionBadge
                  label={article.sentiment.label}
                  confidence={article.sentiment.confidence}
                  size="md"
                />
                <span className="text-xs text-slate-600">
                  {SENTIMENT_GLOSS[article.sentiment.label]}
                </span>
              </div>

              <ConfidenceMeter
                value={article.sentiment.confidence}
                calibrated={article.sentiment.model.calibrated}
                label="Model confidence"
              />

              <ProbabilityBars
                probabilities={article.sentiment.probabilities}
                calibrated={article.sentiment.model.calibrated}
              />

              <ModelBadge model={article.sentiment.model} />
            </div>

            <div className="space-y-3">
              <div>
                <div className="mb-1 flex items-center gap-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                    Evidence spans
                  </h3>
                  <ProvenanceChip kind="model" />
                </div>
                <p className="mb-2 text-xs text-slate-500">{EVIDENCE_SPAN_NOTE}</p>
                <EvidenceList spans={article.sentiment.evidence} model={article.sentiment.model} />
              </div>
            </div>
          </div>
        )}
      </section>

      {/* --- Entity sentiments -------------------------------------------- */}
      {article.entity_sentiments.length > 0 ? (
        <section className="nfs-card" aria-labelledby="entity-sentiment-heading">
          <SectionHeader
            id="entity-sentiment-heading"
            title="Per-entity language labels"
            subtitle="Which entity the language is directed at. This is a separate task from the article-level label and uses its own model."
          />
          <ul className="mt-3 space-y-3">
            {article.entity_sentiments.map((entitySentiment, index) => (
              <li key={`${entitySentiment.entity_id ?? "unknown"}-${index}`} className="rounded border border-slate-200 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-slate-900">
                    {entitySentiment.canonical_name ?? entitySentiment.entity_id ?? "unresolved entity"}
                  </span>
                  <PredictionBadge
                    label={entitySentiment.label}
                    confidence={entitySentiment.confidence}
                  />
                  <ModelBadge model={entitySentiment.model} />
                </div>
                <EvidenceList
                  className="mt-2"
                  spans={entitySentiment.evidence}
                  emptyMessage="No evidence span returned for this entity label."
                />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* --- Events -------------------------------------------------------- */}
      <section className="nfs-card" aria-labelledby="events-heading">
        <SectionHeader
          id="events-heading"
          title="Event frames"
          subtitle="Event classifications extracted from this article. Each carries its own evidence and model version."
        />
        <div className="mt-3">
          {article.events.length === 0 ? (
            <EmptyState
              title="No event frame extracted"
              description="No event type reached the model's decision threshold for this article."
            />
          ) : (
            <ul className="space-y-4">
              {article.events.map((event, index) => (
                <li key={`${event.event_type}-${index}`} className="rounded border border-slate-200 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <EventTypeBadge type={event.event_type} />
                    <span className="text-xs text-slate-600">
                      confidence {Math.round(event.confidence * 100)}%
                    </span>
                    <ModelBadge model={event.model} />
                    <span className="text-xs text-slate-500">
                      event date:{" "}
                      {event.event_date ? (
                        event.event_date
                      ) : (
                        <span className="text-slate-400" title="The article did not state when the event happened.">
                          not stated in the text
                        </span>
                      )}
                    </span>
                  </div>

                  {event.entities.length > 0 ? (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">
                        participating entities
                      </span>
                      {event.entities.map((entity, entityIndex) => (
                        <span key={entityIndex} className="inline-flex items-center gap-1">
                          <EntityTypeBadge type={entity.span.entity_type} />
                          <span className="text-xs text-slate-700">
                            {entity.canonical_name ?? entity.span.text}
                          </span>
                        </span>
                      ))}
                    </div>
                  ) : null}

                  <div className="mt-2">
                    <div className="mb-1 flex items-center gap-2">
                      <span className="text-[0.65rem] font-semibold uppercase tracking-wide text-slate-600">
                        evidence
                      </span>
                      <ProvenanceChip kind="model" />
                    </div>
                    <EvidenceList
                      spans={event.evidence}
                      model={event.model}
                      emptyMessage="No evidence span was returned for this event frame. Treat the classification as unsupported."
                    />
                  </div>

                  {Object.keys(event.attributes).length > 0 ? (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs font-medium text-slate-600">
                        Extracted attributes
                      </summary>
                      <dl className="mt-1 grid gap-1 text-xs sm:grid-cols-2">
                        {Object.entries(event.attributes).map(([key, value]) => (
                          <div key={key} className="flex gap-2">
                            <dt className="font-mono text-slate-500">{key}</dt>
                            <dd className="text-slate-800">{String(value)}</dd>
                          </div>
                        ))}
                      </dl>
                    </details>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* --- Entities ------------------------------------------------------ */}
      <section className="nfs-card" aria-labelledby="entities-heading">
        <SectionHeader
          id="entities-heading"
          title="Extracted entities"
          subtitle="Spans the model tagged in this article, with how each was resolved to a canonical entity."
        />
        <div className="mt-3">
          {article.entities.length === 0 ? (
            <EmptyState title="No entities extracted" description="The NER stage found no spans in this article." />
          ) : (
            <ul className="divide-y divide-slate-100">
              {article.entities.map((entity, index) => (
                <li key={index} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <EntityTypeBadge type={entity.span.entity_type} />
                    <span className="text-sm font-medium text-slate-900">{entity.span.text}</span>
                    {entity.canonical_name ? (
                      <>
                        <span className="text-xs text-slate-400">→</span>
                        {entity.entity_id ? (
                          <Link
                            to={`/entities/${entity.entity_id}`}
                            className="text-xs font-medium text-brand-800 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
                          >
                            {entity.canonical_name}
                          </Link>
                        ) : (
                          <span className="text-xs text-slate-700">{entity.canonical_name}</span>
                        )}
                      </>
                    ) : (
                      <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[0.65rem] text-amber-900 ring-1 ring-inset ring-amber-300">
                        unresolved
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    {entity.resolution_method ? (
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.65rem]">
                        {entity.resolution_method}
                      </span>
                    ) : null}
                    <span className="tabular-nums">{Math.round(entity.confidence * 100)}%</span>
                    <span className="font-mono text-[0.65rem]">
                      chars {entity.span.start}–{entity.span.end}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* --- Limitations --------------------------------------------------- */}
      <LimitationsPanel limitations={article.limitations} />

      <LimitationsFootnote />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RelationList({
  title,
  rows,
  emptyText,
}: {
  title: string;
  rows: Array<{
    article_id: string;
    title: string;
    publisher: string;
    url: string;
    published_at: string | null;
    method: string | null;
    score: number | null;
    reason: string | null;
  }>;
  emptyText: string;
}) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">{title}</h3>
      {rows.length === 0 ? (
        <p className="mt-1 rounded border border-dashed border-slate-300 bg-slate-50 px-3 py-2 text-xs text-slate-600">
          {emptyText}
        </p>
      ) : (
        <ul className="mt-1 space-y-2">
          {rows.map((row) => (
            <li key={row.article_id} className="rounded border border-slate-200 p-2">
              <Link
                to={`/news/${row.article_id}`}
                className="text-sm font-medium text-brand-800 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
              >
                {row.title}
              </Link>
              <p className="mt-0.5 text-xs text-slate-500">
                {row.publisher} · {formatDateTime(row.published_at)}
              </p>
              <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[0.7rem] text-slate-600">
                <ProvenanceChip kind="model" />
                {row.method ? <span className="font-mono">{row.method}</span> : null}
                {row.score !== null ? <span className="tabular-nums">score {row.score.toFixed(2)}</span> : null}
              </p>
              {row.reason ? <p className="mt-1 text-[0.7rem] text-slate-600">{row.reason}</p> : null}
              <a
                href={row.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-block text-[0.7rem] text-slate-500 underline-offset-2 hover:underline"
              >
                {hostnameOf(row.url)} ↗
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Legend for the entity span colours. Answers "what do the highlights mean?". */
function EntityLegend() {
  return (
    <ul className="flex flex-wrap items-center gap-2" aria-label="Highlight legend">
      {ENTITY_TYPES.map((type: EntityType) => (
        <li key={type} className="inline-flex items-center gap-1 text-[0.65rem] text-slate-600">
          <EntitySwatch type={type} />
          <span className="font-mono">{type}</span>
        </li>
      ))}
      <li className="inline-flex items-center gap-1 text-[0.65rem] text-slate-600">
        <span
          aria-hidden="true"
          className="inline-block h-3 w-3 rounded-sm ring-1 ring-inset ring-black/10"
          style={{ backgroundColor: `${sentimentStyle("positive").hex}33` }}
        />
        <span>sentiment evidence</span>
      </li>
    </ul>
  );
}

/** Closes the page with the label-space and evidence reminders. */
function LimitationsFootnote() {
  return (
    <section className="rounded-md border border-slate-200 bg-white p-4 text-xs text-slate-600">
      <h2 className="text-sm font-semibold text-slate-900">What the labels mean here</h2>
      <dl className="mt-2 grid gap-2 sm:grid-cols-2">
        {SENTIMENT_LABELS.map((label) => (
          <div key={label} className="flex gap-2">
            <dt className="shrink-0">
              <PredictionBadge label={label} />
            </dt>
            <dd className="text-slate-600">{SENTIMENT_GLOSS[label]}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3">
        Entity types follow the annotation contract; <span className="font-mono">REGULATOR</span> is
        used instead of <span className="font-mono">ORG</span> for regulators, and a span is never
        double-labelled. Span colours only mark which words were tagged.
      </p>
      <ul className="mt-2 flex flex-wrap gap-2">
        {ENTITY_TYPES.map((type: EntityType) => (
          <li key={type} className="inline-flex items-center gap-1">
            <EntitySwatch type={type} />
            <span className="font-mono text-[0.7rem]">{type}</span>
            <span className="text-[0.7rem] text-slate-500" style={{ color: entityStyle(type).hex }}>
              {/* colour label mirrors the swatch */}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
