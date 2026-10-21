import { Link, useParams } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { EntityTypeBadge, PredictionBadge } from "../../components/PredictionBadge";
import { LimitationsPanel } from "../../components/ModelBadge";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "../../components/states";
import { CoverageTag, StatCard } from "../../components/StatCard";
import { useEntity } from "../../hooks/useEntities";
import { COVERAGE_MEASUREMENT_EXPLANATION } from "../../lib/constants";
import { ENTITY_TYPE_DESCRIPTIONS, SENTIMENT_LABELS } from "../../lib/schemas";
import {
  SENTIMENT_STYLES,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPeriod,
} from "../../lib/format";

/**
 * Entity page.
 *
 * Shows the alias table, every mention with its span, related events, and the
 * coverage-language trend for this entity. Ambiguous mentions get their own
 * section so a reader can see exactly which occurrences the resolver doubted.
 */
export function EntityPage() {
  const { entityId } = useParams<{ entityId: string }>();
  const query = useEntity(entityId);

  if (query.isLoading) {
    return (
      <div className="space-y-4">
        <LoadingSkeleton rows={2} label="Loading entity" />
        <LoadingSkeleton variant="stat" rows={4} label="Loading entity statistics" />
        <LoadingSkeleton variant="chart" label="Loading entity trend" />
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="space-y-4">
        <SectionHeader as="h1" title="Entity" subtitle="This entity could not be loaded." />
        <ErrorState error={query.error} context="this entity" onRetry={() => void query.refetch()} />
        <Link
          to="/entities"
          className="inline-block rounded border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
        >
          Back to the entity directory
        </Link>
      </div>
    );
  }

  const entity = query.data;
  if (!entity) {
    return <EmptyState title="Entity not returned" description="The API returned no body for this id." />;
  }

  const trendData = entity.sentiment_trend.map((point) => ({
    period: formatPeriod(point.period),
    positive: point.positive,
    negative: point.negative,
    neutral: point.neutral,
    uncertain: point.uncertain,
  }));

  return (
    <div className="space-y-6">
      {/* --- Header ------------------------------------------------------- */}
      <div className="space-y-2">
        <nav aria-label="Breadcrumb" className="text-xs text-slate-500">
          <Link to="/entities" className="underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600">
            Entities
          </Link>
          <span aria-hidden="true" className="mx-1">
            /
          </span>
          <span>{entity.canonical_name}</span>
        </nav>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">{entity.canonical_name}</h1>
          <EntityTypeBadge type={entity.entity_type} size="md" />
        </div>
        <p className="text-xs text-slate-500">
          {ENTITY_TYPE_DESCRIPTIONS[entity.entity_type]} · id{" "}
          <span className="font-mono">{entity.entity_id}</span>
        </p>
        {entity.description ? <p className="text-sm text-slate-700">{entity.description}</p> : null}
      </div>

      {/* --- Numbers ------------------------------------------------------- */}
      <section aria-labelledby="entity-stats">
        <h2 id="entity-stats" className="sr-only">
          Entity statistics
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Resolved mentions" value={formatNumber(entity.mention_count)} hint="across the corpus" />
          <StatCard
            label="Ambiguous mentions"
            value={formatNumber(entity.ambiguous_mention_count)}
            hint="resolver could not decide"
          />
          <StatCard label="Aliases" value={formatNumber(entity.aliases.length)} hint="mapped to this entity" />
          <StatCard
            label="Last seen"
            value={entity.last_seen_at ? formatDate(entity.last_seen_at) : "—"}
            hint={entity.last_seen_at ? formatDateTime(entity.last_seen_at) : "no mentions recorded"}
          />
        </div>
      </section>

      {/* --- Ambiguity section (only when there is ambiguity) -------------- */}
      {entity.ambiguous_mentions.length > 0 ? (
        <section className="rounded-md border border-amber-300 bg-amber-50 p-4" aria-labelledby="entity-ambiguity">
          <SectionHeader
            id="entity-ambiguity"
            title="Ambiguous mentions"
            subtitle={`${entity.ambiguous_mentions.length} occurrence${entity.ambiguous_mentions.length === 1 ? "" : "s"} that the resolver attached to this entity with low confidence. They are counted separately from the resolved total above, because "likely this entity" is not the same as "this entity".`}
          />
          <ul className="mt-3 space-y-2">
            {entity.ambiguous_mentions.map((mention) => (
              <li key={`${mention.article_id}-${mention.span.start}`} className="rounded border border-amber-200 bg-white p-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    to={`/news/${mention.article_id}`}
                    className="text-sm font-medium text-brand-800 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
                  >
                    {mention.article_title}
                  </Link>
                  <span className="text-xs text-slate-500">{mention.publisher}</span>
                  <span className="font-mono text-[0.65rem] text-amber-800">
                    confidence {Math.round(mention.confidence * 100)}%
                    {mention.resolution_method ? ` · ${mention.resolution_method}` : ""}
                  </span>
                </div>
                <blockquote className="mt-1 border-l-2 border-amber-400 pl-2 text-xs italic text-slate-700">
                  …{mention.span.text}…
                </blockquote>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <p className="rounded border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
          No mentions were flagged ambiguous for this entity.
        </p>
      )}

      {/* --- Aliases -------------------------------------------------------- */}
      <section className="nfs-card" aria-labelledby="entity-aliases">
        <SectionHeader
          id="entity-aliases"
          title="Aliases"
          subtitle="Strings that map to this canonical entity, with how each alias was established."
        />
        <div className="mt-3 overflow-x-auto">
          {entity.aliases_table.length === 0 ? (
            <EmptyState
              title="No aliases recorded"
              description="Only the canonical name appears to be in use."
            />
          ) : (
            <table className="min-w-full border-collapse text-sm">
              <caption className="sr-only">Aliases for {entity.canonical_name}</caption>
              <thead className="bg-slate-50">
                <tr>
                  <th scope="col" className="border-b border-slate-200 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                    Alias
                  </th>
                  <th scope="col" className="border-b border-slate-200 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                    Established by
                  </th>
                  <th scope="col" className="border-b border-slate-200 px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-600">
                    Confidence
                  </th>
                  <th scope="col" className="border-b border-slate-200 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                    First seen
                  </th>
                </tr>
              </thead>
              <tbody>
                {entity.aliases_table.map((alias) => (
                  <tr key={alias.alias} className="border-b border-slate-100 last:border-b-0">
                    <td className="px-3 py-2 font-medium text-slate-800">{alias.alias}</td>
                    <td className="px-3 py-2 text-xs text-slate-600">
                      <span
                        className={`rounded px-1.5 py-0.5 ${
                          alias.source.toLowerCase().includes("manual")
                            ? "bg-brand-50 text-brand-800 ring-1 ring-inset ring-brand-300"
                            : "bg-violet-50 text-violet-800 ring-1 ring-inset ring-violet-300"
                        }`}
                        title={
                          alias.source.toLowerCase().includes("manual")
                            ? "Curated by a human."
                            : "Proposed by a model. Model-inferred."
                        }
                      >
                        {alias.source}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-slate-700">
                      {alias.confidence === null ? "—" : `${Math.round(alias.confidence * 100)}%`}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-600">{formatDate(alias.first_seen_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* --- Trend ---------------------------------------------------------- */}
      <section className="nfs-card" aria-labelledby="entity-trend">
        <SectionHeader
          id="entity-trend"
          title="Coverage sentiment for this entity"
          subtitle={COVERAGE_MEASUREMENT_EXPLANATION}
          actions={<CoverageTag />}
        />
        <div className="mt-4">
          {trendData.length === 0 ? (
            <EmptyState
              title="No trend available"
              description="There are not enough dated mentions of this entity to build a trend."
            />
          ) : (
            <>
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendData} margin={{ top: 8, right: 16, bottom: 8, left: -8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="period" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                    <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
                    <Tooltip contentStyle={{ fontSize: 12 }} />
                    {SENTIMENT_LABELS.map((label) => (
                      <Line
                        key={label}
                        type="monotone"
                        dataKey={label}
                        name={`${label} language`}
                        stroke={SENTIMENT_STYLES[label].hex}
                        strokeWidth={2}
                        strokeDasharray={label === "uncertain" ? "4 3" : undefined}
                        dot={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Counts of articles mentioning this entity, split by the label assigned to each
                article's language. This measures how the entity is written about, not how the entity
                is performing.
              </p>
            </>
          )}
        </div>
      </section>

      {/* --- Mentions ------------------------------------------------------- */}
      <section className="nfs-card" aria-labelledby="entity-mentions">
        <SectionHeader
          id="entity-mentions"
          title="Mentions"
          subtitle="Each row is one span the model tagged in one article. The quoted text is the span itself, not a summary."
        />
        <div className="mt-3">
          {entity.mentions.length === 0 ? (
            <EmptyState
              title="No mentions returned"
              description="The API returned no mentions for this entity, even though a count was reported."
            />
          ) : (
            <ul className="divide-y divide-slate-100">
              {entity.mentions.map((mention) => (
                <li key={`${mention.article_id}-${mention.span.start}`} className="py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      to={`/news/${mention.article_id}`}
                      className="text-sm font-medium text-brand-800 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
                    >
                      {mention.article_title}
                    </Link>
                    <PredictionBadge label={mention.sentiment} />
                    <span className="text-xs text-slate-500">{mention.publisher}</span>
                    <span className="text-xs text-slate-500">{formatDate(mention.published_at)}</span>
                  </div>
                  <blockquote className="mt-1 border-l-2 border-slate-300 pl-2 text-xs italic text-slate-700">
                    …{mention.span.text}…
                  </blockquote>
                  <p className="mt-1 font-mono text-[0.65rem] text-slate-500">
                    span chars {mention.span.start}–{mention.span.end} ·{" "}
                    {mention.resolution_method ?? "resolution method unrecorded"} · confidence{" "}
                    {Math.round(mention.confidence * 100)}%
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* --- Related events -------------------------------------------------- */}
      <section className="nfs-card" aria-labelledby="entity-events">
        <SectionHeader
          id="entity-events"
          title="Related event clusters"
          subtitle="Event clusters this entity participates in. Cluster membership is model-inferred."
        />
        <div className="mt-3">
          {entity.related_events.length === 0 ? (
            <EmptyState
              title="No related events"
              description="No event cluster currently links to this entity."
            />
          ) : (
            <ul className="space-y-2">
              {entity.related_events.map((event) => (
                <li key={event.event_id} className="rounded border border-slate-200 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      to={`/events/${event.event_id}`}
                      className="text-sm font-medium text-brand-800 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
                    >
                      {event.title}
                    </Link>
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[0.7rem] text-slate-700">
                      {event.event_type}
                    </span>
                    <span className="text-xs text-slate-500">
                      {event.article_count} articles · {event.new_article_count} new ·{" "}
                      {event.repeated_article_count} repeated
                    </span>
                  </div>
                  <p className="mt-1 flex flex-wrap gap-3 text-[0.7rem] text-slate-500">
                    <span>event date: {formatDate(event.event_date)}</span>
                    <span>publish date: {formatDate(event.publish_date)}</span>
                    <span>processing date: {formatDate(event.processing_date)}</span>
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <LimitationsPanel limitations={entity.limitations} />
    </div>
  );
}
