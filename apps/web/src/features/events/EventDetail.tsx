import { useParams } from "react-router-dom";

import { EvidenceList } from "../../components/EvidenceSpan";
import { ModelBadge } from "../../components/ModelBadge";
import { EventTypeBadge } from "../../components/PredictionBadge";
import { StatCard } from "../../components/StatCard";
import { Timeline } from "../../components/Timeline";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "../../components/states";
import { useEventItem } from "../../hooks/useEvents";
import { DEDUP_INFERRED_NOTE, WHATS_NEW_INFERRED_NOTE } from "../../lib/constants";
import { formatDate, formatNumber } from "../../lib/format";

/**
 * One event cluster: the full deduplicated coverage timeline.
 *
 * Publish date / event date / processing date are kept separate throughout —
 * collapsing them is the classic way event studies silently go wrong.
 */
export function EventDetailPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const event = useEventItem(eventId);

  if (event.isLoading) {
    return <LoadingSkeleton variant="cards" label="Loading event cluster" />;
  }
  if (event.isError || !event.data) {
    return (
      <ErrorState
        error={event.error}
        context="the event cluster"
        onRetry={() => void event.refetch()}
      />
    );
  }

  const detail = event.data;

  return (
    <div className="space-y-6">
      <SectionHeader
        as="h1"
        eyebrow="Event cluster"
        title={detail.title}
        subtitle="All coverage of one underlying event, deduplicated and ordered. Publish, event and processing dates are tracked separately."
      />

      <div className="flex flex-wrap gap-2">
        <EventTypeBadge type={detail.event_type} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Event date" value={formatDate(detail.event_date)} hint="when it happened" />
        <StatCard label="First publish" value={formatDate(detail.publish_date)} hint="first report seen" />
        <StatCard label="Articles" value={formatNumber(detail.article_count)} hint={`${formatNumber(detail.new_article_count)} new / ${formatNumber(detail.repeated_article_count)} repeats`} />
        <StatCard
          label="Mean confidence"
          value={detail.mean_confidence == null ? "—" : `${Math.round(detail.mean_confidence * 100)}%`}
          hint={detail.model ? <span><ModelBadge model={detail.model} /></span> : undefined}
        />
      </div>

      <section className="nfs-card" aria-labelledby="event-timeline">
        <SectionHeader
          id="event-timeline"
          title="Coverage timeline"
          subtitle={WHATS_NEW_INFERRED_NOTE}
          actions={detail.dedup_method ? <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700">{detail.dedup_method}</span> : undefined}
        />
        <div className="mt-4">
          {(detail.timeline ?? []).length === 0 ? (
            <EmptyState
              title="No timeline entries"
              description="This event has no linked articles in the snapshot."
            />
          ) : (
            <Timeline entries={detail.timeline ?? []} labelledBy="Coverage of this event" note={DEDUP_INFERRED_NOTE} />
          )}
        </div>
      </section>

      <section className="nfs-card" aria-labelledby="event-evidence">
        <SectionHeader
          id="event-evidence"
          title="Evidence"
          subtitle="Sentences the model read when it merged these articles into one cluster."
        />
        <div className="mt-4">
          <EvidenceList
            spans={detail.evidence ?? []}
            model={detail.model}
            emptyMessage="No evidence spans were stored for this cluster."
          />
        </div>
      </section>
    </div>
  );
}
