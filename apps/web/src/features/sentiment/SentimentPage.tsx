import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ToggleGroup } from "../../components/FilterBar";
import { PredictionBadge } from "../../components/PredictionBadge";
import { CoverageTag, StatCard } from "../../components/StatCard";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "../../components/states";
import { useSentimentTrend } from "../../hooks/useAnalytics";
import { useNews } from "../../hooks/useNews";
import { COVERAGE_MEASUREMENT_EXPLANATION } from "../../lib/constants";
import { SENTIMENT_LABELS, type Granularity, type SentimentLabel } from "../../lib/schemas";
import { SENTIMENT_GLOSS, SENTIMENT_STYLES, formatNumber, formatPercent } from "../../lib/format";

/**
 * Coverage sentiment.
 *
 * This page is deliberately NOT called "market sentiment" or "investor
 * sentiment". Every panel carries the coverage-measurement framing, and the
 * per-publisher split is shown as a *breakdown of counts*, never as a
 * confusion matrix or an accuracy claim (the corpus has no ground truth here).
 */
export function SentimentPage() {
  const [granularity, setGranularity] = useState<Granularity>("week");
  const trend = useSentimentTrend(granularity);
  const news = useNews({ page: 1, page_size: 100 });

  const totals = useMemo(() => {
    const base: Record<SentimentLabel, number> = { positive: 0, negative: 0, neutral: 0, uncertain: 0 };
    for (const point of trend.data ?? []) {
      base.positive += point.positive;
      base.negative += point.negative;
      base.neutral += point.neutral;
      base.uncertain += point.uncertain;
    }
    const total = base.positive + base.negative + base.neutral + base.uncertain;
    return { counts: base, total };
  }, [trend.data]);

  /** Per-publisher counts come from the news page we already fetched. */
  const byPublisher = useMemo(() => {
    const map = new Map<
      string,
      { publisher: string; positive: number; negative: number; neutral: number; uncertain: number; total: number }
    >();
    for (const article of news.data?.items ?? []) {
      const entry = map.get(article.publisher) ?? {
        publisher: article.publisher,
        positive: 0,
        negative: 0,
        neutral: 0,
        uncertain: 0,
        total: 0,
      };
      const label = article.sentiment?.label;
      if (label) entry[label] += 1;
      entry.total += 1;
      map.set(article.publisher, entry);
    }
    return Array.from(map.values()).sort((a, b) => b.total - a.total);
  }, [news.data]);

  const chartData = useMemo(
    () =>
      (trend.data ?? []).map((point) => ({
        period: point.period,
        positive: point.positive,
        negative: point.negative,
        neutral: point.neutral,
        uncertain: point.uncertain,
        mean_score: point.mean_score,
      })),
    [trend.data],
  );

  return (
    <div className="space-y-6">
      <SectionHeader
        as="h1"
        eyebrow="Sentiment"
        title="Coverage sentiment measurements"
        subtitle={COVERAGE_MEASUREMENT_EXPLANATION}
        actions={
          <ToggleGroup
            ariaLabel="Trend granularity"
            value={granularity}
            onChange={setGranularity}
            options={[
              { value: "day", label: "Daily" },
              { value: "week", label: "Weekly" },
              { value: "month", label: "Monthly" },
            ]}
          />
        }
      />

      {/* --- Summary numbers --------------------------------------------- */}
      <section aria-labelledby="sentiment-summary">
        <h2 id="sentiment-summary" className="sr-only">
          Summary
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <StatCard
            label="Labelled articles"
            value={formatNumber(totals.total)}
            hint="in the shown window"
            loading={trend.isLoading}
          />
          {SENTIMENT_LABELS.map((label) => (
            <StatCard
              key={label}
              label={SENTIMENT_STYLES[label].label}
              value={formatNumber(totals.counts[label])}
              hint={totals.total > 0 ? formatPercent(totals.counts[label] / totals.total) : "—"}
              loading={trend.isLoading}
            />
          ))}
        </div>
      </section>

      {/* --- Trend -------------------------------------------------------- */}
      <section className="nfs-card" aria-labelledby="sentiment-trend">
        <SectionHeader
          id="sentiment-trend"
          title={`Articles by label (${granularity === "day" ? "daily" : granularity === "week" ? "weekly" : "monthly"})`}
          subtitle="Stack-free comparison: each line is the count of articles whose language carries that label."
          actions={<CoverageTag />}
        />
        <div className="mt-4">
          {trend.isLoading ? (
            <LoadingSkeleton variant="chart" label="Loading coverage sentiment trend" />
          ) : trend.isError ? (
            <ErrorState
              error={trend.error}
              context="the coverage sentiment trend"
              onRetry={() => void trend.refetch()}
            />
          ) : chartData.length === 0 ? (
            <EmptyState
              title="No labelled articles in this window"
              description="The corpus returned no sentiment measurements for the selected granularity."
              hint="Try a coarser granularity, or confirm sentiment labels exist for this snapshot."
            />
          ) : (
            <div className="h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: -8 }}>
                  <defs>
                    {SENTIMENT_LABELS.map((label) => (
                      <linearGradient key={label} id={`fill-${label}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={SENTIMENT_STYLES[label].hex} stopOpacity={0.35} />
                        <stop offset="95%" stopColor={SENTIMENT_STYLES[label].hex} stopOpacity={0.03} />
                      </linearGradient>
                    ))}
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="period" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                  <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ fontSize: 12 }}
                    formatter={(value: number, name: string) => [`${value} articles`, name]}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {SENTIMENT_LABELS.map((label) => (
                    <Area
                      key={label}
                      type="monotone"
                      dataKey={label}
                      name={`${label} language`}
                      stroke={SENTIMENT_STYLES[label].hex}
                      fill={`url(#fill-${label})`}
                      strokeWidth={2}
                      strokeDasharray={label === "uncertain" ? "4 3" : undefined}
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
        <p className="mt-2 text-xs text-slate-500">
          These are counts of language labels, not a net sentiment score. We do not publish a single
          blended "sentiment index", because collapsing four labels into one number would hide the
          uncertain/neutral distinction that the annotation contract requires us to keep.
        </p>
      </section>

      {/* --- Per-publisher ------------------------------------------------- */}
      <section className="nfs-card" aria-labelledby="sentiment-publishers">
        <SectionHeader
          id="sentiment-publishers"
          title="Label distribution by publisher"
          subtitle="How each publisher's articles are labelled. This is a composition breakdown, not an accuracy measurement — there is no ground truth for corpus articles."
        />
        <div className="mt-4">
          {news.isLoading ? (
            <LoadingSkeleton variant="chart" label="Loading publisher breakdown" />
          ) : news.isError ? (
            <ErrorState error={news.error} context="the publisher breakdown" onRetry={() => void news.refetch()} />
          ) : byPublisher.length === 0 ? (
            <EmptyState
              title="No publisher breakdown available"
              description="No labelled articles were returned for the current snapshot."
            />
          ) : (
            <div className="h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={byPublisher} margin={{ top: 8, right: 16, bottom: 8, left: -8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="publisher"
                    tick={{ fontSize: 10 }}
                    stroke="#94a3b8"
                    interval={0}
                    angle={-20}
                    textAnchor="end"
                    height={70}
                  />
                  <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
                  <Tooltip contentStyle={{ fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {SENTIMENT_LABELS.map((label) => (
                    <Bar key={label} dataKey={label} name={`${label} language`} stackId="labels" fill={SENTIMENT_STYLES[label].hex} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Stacked bars show composition only. A taller bar means more articles, not stronger language.
        </p>
      </section>

      {/* --- Label glossary ------------------------------------------------ */}
      <section className="nfs-card" aria-labelledby="sentiment-glossary">
        <SectionHeader
          id="sentiment-glossary"
          title="Label definitions"
          subtitle="The four labels are mutually exclusive. 'Uncertain' is separate from 'neutral' and must not be merged with it."
        />
        <ul className="mt-3 grid gap-3 sm:grid-cols-2">
          {SENTIMENT_LABELS.map((label) => (
            <li key={label} className="rounded border border-slate-200 p-3">
              <div className="flex items-center gap-2">
                <PredictionBadge label={label} size="md" />
                <span
                  aria-hidden="true"
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: SENTIMENT_STYLES[label].hex }}
                />
              </div>
              <p className="mt-2 text-xs text-slate-600">{SENTIMENT_GLOSS[label]}</p>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-slate-500">
          Colour encoding: <span className="font-medium text-emerald-700">positive=emerald</span>,{" "}
          <span className="font-medium text-rose-700">negative=rose</span>,{" "}
          <span className="font-medium text-slate-600">neutral=slate</span>,{" "}
          <span className="font-medium text-amber-700">uncertain=amber</span>. These colours are used
          for nothing else in the app.
        </p>
      </section>

      <p className="text-xs text-slate-500">
        Looking for the per-article labels behind these counts?{" "}
        <Link to="/news" className="font-medium text-brand-800 underline-offset-2 hover:underline">
          Open the news explorer
        </Link>{" "}
        and filter by sentiment.
      </p>
    </div>
  );
}
