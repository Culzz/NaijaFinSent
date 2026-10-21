import { cx } from "../lib/cx";
import { formatDate, formatDateTime, sentimentStyle } from "../lib/format";
import type { TimelineEntry } from "../lib/schemas";
import { EventTypeBadge, PredictionBadge, ProvenanceChip } from "./PredictionBadge";

interface TimelineProps {
  entries: TimelineEntry[];
  /** Heading id for aria-labelledby. */
  labelledBy?: string;
  className?: string;
  /** Shown under the heading; defaults to the three-clocks note. */
  note?: string;
}

/**
 * Vertical cluster timeline.
 *
 * Each entry shows THREE distinct clocks — event date, publish date, and
 * processing date — separately. They are never merged into one "date", because
 * conflating them would misrepresent when a fact became knowable.
 */
export function Timeline({ entries, labelledBy, className, note }: TimelineProps) {
  if (entries.length === 0) {
    return (
      <p className={cx("rounded border border-dashed border-slate-300 bg-slate-50 px-3 py-4 text-sm text-slate-600", className)}>
        No timeline entries were returned for this cluster.
      </p>
    );
  }

  return (
    <div className={className}>
      <p className="mb-3 text-xs text-slate-600">
        {note ??
          "Each entry lists three separate clocks: the event date, the publish date, and the processing date. They are shown separately and are not interchangeable."}
      </p>
      <ol className="relative space-y-4 border-l border-slate-200 pl-6" aria-labelledby={labelledBy}>
        {entries.map((entry, index) => (
          <li key={`${entry.article_id}-${index}`} className="relative">
            <span
              aria-hidden="true"
              className={cx(
                "absolute -left-[1.72rem] top-1.5 h-3 w-3 rounded-full border-2 border-white",
                entry.is_new_coverage ? "bg-brand-600" : "bg-slate-400",
              )}
            />
            <div className="rounded-md border border-slate-200 bg-white p-3">
              <div className="flex flex-wrap items-center gap-2">
                <a
                  href={entry.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium text-brand-800 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
                >
                  {entry.title}
                </a>
                <span className="text-xs text-slate-500">{entry.publisher}</span>
                {entry.is_new_coverage ? (
                  <span className="rounded bg-brand-50 px-1.5 py-0.5 text-[0.65rem] font-medium text-brand-800 ring-1 ring-inset ring-brand-300">
                    new coverage
                  </span>
                ) : (
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[0.65rem] font-medium text-slate-600 ring-1 ring-inset ring-slate-300">
                    repeated coverage
                  </span>
                )}
                {entry.is_duplicate ? (
                  <span
                    className="rounded bg-amber-50 px-1.5 py-0.5 text-[0.65rem] font-medium text-amber-900 ring-1 ring-inset ring-amber-300"
                    title="A model judged this to be a duplicate of another article. Model-inferred."
                  >
                    duplicate (model-inferred)
                  </span>
                ) : null}
                {entry.event_type ? <EventTypeBadge type={entry.event_type} /> : null}
                <PredictionBadge label={entry.sentiment} />
              </div>

              <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
                <DateCell term="event date" value={entry.event_date} format="date" />
                <DateCell term="publish date" value={entry.published_at} format="datetime" />
                <DateCell term="processing date" value={entry.processed_at} format="datetime" />
              </dl>

              {entry.evidence.length > 0 ? (
                <div className="mt-2 space-y-1 border-t border-slate-100 pt-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[0.65rem] font-medium uppercase tracking-wide text-slate-500">
                      evidence
                    </span>
                    <ProvenanceChip kind="model" />
                  </div>
                  {entry.evidence.map((span, spanIndex) => (
                    <blockquote
                      key={spanIndex}
                      className="border-l-2 pl-2 text-xs italic text-slate-600"
                      style={{ borderColor: entry.sentiment ? sentimentStyle(entry.sentiment).hex : "#cbd5e1" }}
                      title="Supporting text, not causal attribution."
                    >
                      “{span.text}”
                    </blockquote>
                  ))}
                </div>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function DateCell({
  term,
  value,
  format,
}: {
  term: string;
  value: string | null;
  format: "date" | "datetime";
}) {
  const formatted =
    value === null ? (
      <span className="text-slate-400" title="The source did not state this date.">
        not stated
      </span>
    ) : format === "date" ? (
      formatDate(value)
    ) : (
      formatDateTime(value)
    );

  return (
    <div className="flex flex-col">
      <dt className="text-[0.65rem] uppercase tracking-wide text-slate-500">{term}</dt>
      <dd className="text-slate-800">{formatted}</dd>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Compact timeline used on entity pages
// ---------------------------------------------------------------------------

interface MiniTimelineProps {
  entries: Array<{
    id: string;
    date: string | null;
    title: string;
    url: string;
    publisher: string;
    kind?: string;
  }>;
  className?: string;
}

export function MiniTimeline({ entries, className }: MiniTimelineProps) {
  if (entries.length === 0) {
    return <p className={cx("text-sm text-slate-500", className)}>No dated mentions.</p>;
  }
  return (
    <ol className={cx("space-y-2", className)}>
      {entries.map((entry) => (
        <li key={entry.id} className="flex gap-3 text-sm">
          <time className="w-24 shrink-0 font-mono text-xs text-slate-500" dateTime={entry.date ?? undefined}>
            {entry.date ? formatDate(entry.date) : "date not stated"}
          </time>
          <div className="min-w-0">
            <a
              href={entry.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand-800 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
            >
              {entry.title}
            </a>
            <span className="ml-2 text-xs text-slate-500">{entry.publisher}</span>
            {entry.kind ? (
              <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-[0.65rem] text-slate-600">
                {entry.kind}
              </span>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
