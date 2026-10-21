import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CoverageTag, StatCard } from "../../components/StatCard";
import {
  EmptyState,
  ErrorState,
  LoadingSkeleton,
  OfflineNotice,
  SectionHeader,
} from "../../components/states";
import { EventTypeBadge, PredictionBadge } from "../../components/PredictionBadge";
import { useEventCounts, useFreshness, useSentimentTrend } from "../../hooks/useAnalytics";
import { useNews } from "../../hooks/useNews";
import { useHealth } from "../../hooks/useHealth";
import { SENTIMENT_STYLES, formatDate, formatMinutes, formatRelative, truncate } from "../../lib/format";
import { COVERAGE_MEASUREMENT_EXPLANATION } from "../../lib/constants";
import { isApiError } from "../../lib/api";
import { cx } from "../../lib/cx";

/**
 * Overview / dashboard.
 *
 * Every aggregate on this page is explicitly framed as a measurement of
 * language in coverage. The chart legend and the card hints carry that wording
 * so a screenshot of any single panel still reads correctly out of context.
 */
export function OverviewPage() {
  const health = useHealth();
  const trend = useSentimentTrend("day");
  const counts = useEventCounts();
  const freshness = useFreshness();
  const news = useNews({ page: 1, page_size: 5 });

  const apiDown =
    (isApiError(health.error) && health.error.kind === "network") ||
    (isApiError(trend.error) && trend.error.kind === "network");

  const totalArticles = news.data?.total ?? null;
  const latestPublished = news.data?.items[0]?.published_at ?? null;
  const topEvent = counts.data
    ? [...counts.data].sort((a, b) => b.count - a.count)[0]
    : undefined;

  return (
    <div className="space-y-8">
      <SectionHeader
        as="h1"
        eyebrow="Overview"
        title="News coverage monitor"
        subtitle={COVERAGE_MEASUREMENT_EXPLANATION}
        actions={<CoverageTag />}
      />

      {apiDown ? (
        <OfflineNotice onRetry={() => void health.refetch()} />
      ) : null}

      {/* --- Headline numbers -------------------------------------------- */}
      <section aria-labelledby="headline-numbers">
        <h2 id="headline-numbers" className="sr-only">
          Headline numbers
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Articles indexed"
            value={totalArticles === null ? "—" : totalArticles.toLocaleString("en-NG")}
            hint="in the corpus snapshot"
            loading={news.isLoading}
          />
          <StatCard
            label="Most frequent event type"
            value={topEvent ? topEvent.count : "—"}
            hint={topEvent ? `articles classified as ${topEvent.event_type}` : "event counts unavailable"}
            loading={counts.isLoading}
          />
          <StatCard
            label="Latest article published"
            value={latestPublished ? formatRelative(latestPublished) : "—"}
            hint={latestPublished ? formatDate(latestPublished) : "no articles returned"}
            loading={news.isLoading}
          />
          <StatCard
            label="Median ingestion lag"
            value={freshness.data ? formatMinutes(freshness.data.median_lag_minutes) : "—"}
            hint="publish → indexed"
            loading={freshness.isLoading}
          />
        </div>
      </section>

      {/* --- Coverage-language trend ------------------------------------- */}
      <section className="nfs-card" aria-labelledby="trend-heading">
        <SectionHeader
          id="trend-heading"
          title="Coverage sentiment over time"
          subtitle={
            <>
              Counts of articles by the sentiment label assigned to their language. This is a{" "}
              <strong>news coverage measurement</strong>, not investor sentiment and not a price
              signal.
            </>
          }
          actions={<CoverageTag />}
        />

        <div className="mt-4">
          {trend.isLoading ? (
            <LoadingSkeleton variant="chart" label="Loading sentiment trend" />
          ) : trend.isError ? (
            <ErrorState
              error={trend.error}
              context="the sentiment trend"
              onRetry={() => void trend.refetch()}
            />
          ) : !trend.data || trend.data.length === 0 ? (
            <EmptyState
              title="No sentiment measurements in this window"
              description="The corpus returned no labelled articles for the requested granularity."
              hint="Widen the date range, or confirm that sentiment labels have been produced for the current snapshot."
            />
          ) : (
            <>
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trend.data} margin={{ top: 8, right: 16, bottom: 8, left: -8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="period" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                    <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
                    <Tooltip
                      contentStyle={{ fontSize: 12 }}
                      formatter={(value: number, name: string) => [`${value} articles`, name]}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line
                      type="monotone"
                      dataKey="positive"
                      name="positive language"
                      stroke={SENTIMENT_STYLES.positive.hex}
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="negative"
                      name="negative language"
                      stroke={SENTIMENT_STYLES.negative.hex}
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="neutral"
                      name="neutral language"
                      stroke={SENTIMENT_STYLES.neutral.hex}
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="uncertain"
                      name="uncertain language"
                      stroke={SENTIMENT_STYLES.uncertain.hex}
                      strokeWidth={2}
                      strokeDasharray="4 3"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-xs text-slate-500">
                “Uncertain” is drawn dashed to keep it visually distinct from “neutral” — the two are
                different labels and are never merged.
              </p>
            </>
          )}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* --- Event counts ---------------------------------------------- */}
        <section className="nfs-card" aria-labelledby="events-heading">
          <SectionHeader
            id="events-heading"
            title="Event classifications"
            subtitle="How many articles carry each event-type classification. A classification is a model output, not a verified event record."
          />
          <div className="mt-4">
            {counts.isLoading ? (
              <LoadingSkeleton variant="chart" label="Loading event counts" />
            ) : counts.isError ? (
              <ErrorState error={counts.error} context="event counts" onRetry={() => void counts.refetch()} />
            ) : !counts.data || counts.data.length === 0 ? (
              <EmptyState
                title="No event classifications"
                description="No article in the current snapshot carries an event-type label."
              />
            ) : (
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    layout="vertical"
                    data={[...counts.data].sort((a, b) => a.count - b.count)}
                    margin={{ top: 4, right: 16, bottom: 4, left: 32 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
                    <YAxis
                      type="category"
                      dataKey="event_type"
                      tick={{ fontSize: 11 }}
                      stroke="#94a3b8"
                      width={110}
                    />
                    <Tooltip
                      contentStyle={{ fontSize: 12 }}
                      formatter={(value: number) => [`${value} articles`, "classified"]}
                    />
                    <Bar dataKey="count" fill="#1f6845" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </section>

        {/* --- Freshness ------------------------------------------------- */}
        <section className="nfs-card" aria-labelledby="freshness-heading">
          <SectionHeader
            id="freshness-heading"
            title="Ingestion freshness"
            subtitle="How recently coverage reached the index. Stale sources are listed explicitly rather than averaged away."
          />
          <div className="mt-4 space-y-4">
            {freshness.isLoading ? (
              <LoadingSkeleton rows={4} label="Loading freshness" />
            ) : freshness.isError ? (
              <ErrorState error={freshness.error} context="freshness" onRetry={() => void freshness.refetch()} />
            ) : !freshness.data ? (
              <EmptyState title="No freshness report" description="The API returned no freshness data." />
            ) : (
              <>
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-slate-500">Last ingestion</dt>
                    <dd className="text-slate-900">{formatRelative(freshness.data.last_ingestion_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-slate-500">Median lag</dt>
                    <dd className="text-slate-900">{formatMinutes(freshness.data.median_lag_minutes)}</dd>
                  </div>
                </dl>

                <ul className="space-y-2">
                  {freshness.data.buckets.map((bucket) => (
                    <li key={bucket.bucket}>
                      <div className="flex items-baseline justify-between text-xs">
                        <span className="text-slate-700">{bucket.bucket}</span>
                        <span className="tabular-nums text-slate-500">
                          {bucket.count} ({Math.round(bucket.share * 100)}%)
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
                        <div
                          className="h-full rounded-full bg-brand-600"
                          style={{ width: `${Math.min(100, bucket.share * 100)}%` }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>

                {freshness.data.stale_sources.length > 0 ? (
                  <div className="rounded border border-amber-300 bg-amber-50 p-2">
                    <p className="text-xs font-medium text-amber-900">
                      Sources behind their expected refresh
                    </p>
                    <ul className="mt-1 list-disc pl-4 text-xs text-amber-900">
                      {freshness.data.stale_sources.map((source) => (
                        <li key={source}>{source}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </>
            )}
          </div>
        </section>
      </div>

      {/* --- Recent news -------------------------------------------------- */}
      <section className="nfs-card" aria-labelledby="recent-heading">
        <SectionHeader
          id="recent-heading"
          title="Recent coverage"
          subtitle="The most recent articles in the snapshot, with the label assigned to each one's language."
          actions={
            <Link
              to="/news"
              className="rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
            >
              Open news explorer
            </Link>
          }
        />
        <div className="mt-4">
          {news.isLoading ? (
            <LoadingSkeleton variant="table" rows={5} label="Loading recent coverage" />
          ) : news.isError ? (
            <ErrorState error={news.error} context="recent coverage" onRetry={() => void news.refetch()} />
          ) : !news.data || news.data.items.length === 0 ? (
            <EmptyState
              title="No articles indexed yet"
              description="The corpus is empty for this snapshot."
              hint="Run an ingestion cycle, or switch to mock mode to review the interface."
            />
          ) : (
            <ul className="divide-y divide-slate-100">
              {news.data.items.map((article) => (
                <li key={article.article_id} className="py-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <Link
                        to={`/news/${article.article_id}`}
                        className="text-sm font-medium text-brand-800 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
                      >
                        {article.title}
                      </Link>
                      <p className="mt-0.5 text-xs text-slate-500">
                        {article.publisher} · {formatDate(article.published_at)}
                        {article.is_duplicate ? " · duplicate (model-inferred)" : ""}
                      </p>
                      {article.snippet ? (
                        <p className="mt-1 text-xs text-slate-600">{truncate(article.snippet, 180)}</p>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {article.event_types.slice(0, 2).map((type) => (
                        <EventTypeBadge key={type} type={type} />
                      ))}
                      <PredictionBadge
                        label={article.sentiment?.label ?? null}
                        confidence={article.sentiment?.confidence ?? null}
                        empty={article.status === "failed" || !article.sentiment}
                      />
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* --- Health ------------------------------------------------------- */}
      <section className="nfs-card" aria-labelledby="health-heading">
        <SectionHeader
          id="health-heading"
          title="Service health"
          subtitle="Whether the API and its dependencies are reachable, and which model versions are loaded."
        />
        <div className="mt-4">
          {health.isLoading ? (
            <LoadingSkeleton rows={3} label="Loading health" />
          ) : health.isError || !health.data ? (
            <ErrorState error={health.error} context="service health" onRetry={() => void health.refetch()} />
          ) : (
            <dl className={cx("grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4")}>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Status</dt>
                <dd className="font-medium text-slate-900">{health.data.status}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Version</dt>
                <dd className="font-mono text-slate-900">{health.data.version}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Database</dt>
                <dd className="text-slate-900">{health.data.database}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Corpus size</dt>
                <dd className="tabular-nums text-slate-900">
                  {health.data.corpus_size === null ? "unknown" : health.data.corpus_size.toLocaleString("en-NG")}
                </dd>
              </div>
              <div className="sm:col-span-2 lg:col-span-4">
                <dt className="text-xs uppercase tracking-wide text-slate-500">Models loaded</dt>
                <dd className="mt-1 flex flex-wrap gap-1.5">
                  {health.data.models_loaded.length === 0 ? (
                    <span className="text-slate-500">none reported</span>
                  ) : (
                    health.data.models_loaded.map((model) => (
                      <span
                        key={model}
                        className="rounded border border-slate-300 bg-slate-50 px-1.5 py-0.5 font-mono text-[0.7rem] text-slate-700"
                      >
                        {model}
                      </span>
                    ))
                  )}
                </dd>
              </div>
            </dl>
          )}
        </div>
      </section>
    </div>
  );
}
