import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Column, DataTable } from "../../components/DataTable";
import {
  ActiveFilters,
  ClearButton,
  FilterBar,
  FilterField,
  Select,
  TextInput,
} from "../../components/FilterBar";
import { Pagination } from "../../components/Pagination";
import { EventTypeBadge } from "../../components/PredictionBadge";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "../../components/states";
import { useEntities } from "../../hooks/useEntities";
import { useEvents } from "../../hooks/useEvents";
import { useDebounced } from "../../hooks/useDebounced";
import {
  EVENT_TYPES,
  EVENT_TYPE_LABELS,
  type EventFilters,
  type EventListItem,
  type EventType,
} from "../../lib/schemas";
import { DEDUP_INFERRED_NOTE } from "../../lib/constants";
import { formatDate, formatNumber } from "../../lib/format";

const DEFAULT_PAGE_SIZE = 20;

/**
 * Event explorer.
 *
 * The list shows the three dates in three separate columns. Collapsing them
 * into one "date" would hide the difference between when something happened,
 * when it was reported, and when we processed it.
 */
export function EventExplorer() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const page = Number.parseInt(searchParams.get("page") ?? "1", 10) || 1;
  const pageSize = Number.parseInt(searchParams.get("page_size") ?? String(DEFAULT_PAGE_SIZE), 10) || DEFAULT_PAGE_SIZE;

  const [entityInput, setEntityInput] = useState("");
  const debouncedEntity = useDebounced(entityInput, 350);
  const entities = useEntities({ page: 1, page_size: 100 });

  const filters = useMemo<EventFilters>(
    () => ({
      event_type: (searchParams.get("event_type") as EventType | null) ?? "",
      entity: searchParams.get("entity") ?? undefined,
      date_from: searchParams.get("date_from") ?? undefined,
      date_to: searchParams.get("date_to") ?? undefined,
      page,
      page_size: pageSize,
    }),
    [searchParams, page, pageSize],
  );

  const events = useEvents(filters);

  function updateParam(key: string, value: string | null) {
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (value === null || value === "") next.delete(key);
        else next.set(key, value);
        if (key !== "page" && key !== "page_size") next.delete("page");
        return next;
      },
      { replace: true },
    );
  }

  const activeFilters = useMemo(() => {
    const list: Array<{ label: string; value: string }> = [];
    const type = searchParams.get("event_type");
    if (type) list.push({ label: "event type", value: type });
    const entity = searchParams.get("entity");
    if (entity) list.push({ label: "entity", value: entity });
    const from = searchParams.get("date_from");
    if (from) list.push({ label: "from", value: from });
    const to = searchParams.get("date_to");
    if (to) list.push({ label: "to", value: to });
    return list;
  }, [searchParams]);

  const columns: Column<EventListItem>[] = [
    {
      key: "title",
      header: "Event cluster",
      sortValue: (row) => row.title,
      render: (row) => (
        <div className="min-w-0 max-w-md">
          <span className="font-medium text-brand-900">{row.title}</span>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
            <EventTypeBadge type={row.event_type} />
            {row.model ? (
              <span className="font-mono text-[0.65rem] text-slate-500">
                {row.model.name}@{row.model.version}
              </span>
            ) : null}
          </div>
        </div>
      ),
    },
    {
      key: "article_count",
      header: "Articles",
      align: "right",
      sortValue: (row) => row.article_count,
      render: (row) => (
        <div className="text-right">
          <span className="tabular-nums">{formatNumber(row.article_count)}</span>
          <p className="text-[0.65rem] text-slate-500">
            {row.new_article_count} new · {row.repeated_article_count} repeated
          </p>
        </div>
      ),
    },
    {
      key: "event_date",
      header: "Event date",
      className: "hidden md:table-cell",
      sortValue: (row) => row.event_date,
      description: "When the event happened, as stated in the coverage. Distinct from the publish date.",
      render: (row) => (
        <span className="whitespace-nowrap text-xs" title="Date the event happened, not the publish date.">
          {row.event_date ? formatDate(row.event_date) : <span className="text-slate-400">not stated</span>}
        </span>
      ),
    },
    {
      key: "publish_date",
      header: "Publish date",
      className: "hidden md:table-cell",
      sortValue: (row) => row.publish_date,
      description: "When the earliest article in the cluster was published.",
      render: (row) => (
        <span className="whitespace-nowrap text-xs">{formatDate(row.publish_date)}</span>
      ),
    },
    {
      key: "processing_date",
      header: "Processing date",
      className: "hidden lg:table-cell",
      sortValue: (row) => row.processing_date,
      description: "When the pipeline processed the cluster.",
      render: (row) => (
        <span className="whitespace-nowrap text-xs text-slate-600">{formatDate(row.processing_date)}</span>
      ),
    },
    {
      key: "mean_confidence",
      header: "Mean conf.",
      align: "right",
      className: "hidden lg:table-cell",
      sortValue: (row) => row.mean_confidence,
      render: (row) =>
        row.mean_confidence === null ? (
          <span className="text-slate-400">—</span>
        ) : (
          <span className="tabular-nums text-xs">{Math.round(row.mean_confidence * 100)}%</span>
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <SectionHeader
        as="h1"
        eyebrow="Events"
        title="Event explorer"
        subtitle={DEDUP_INFERRED_NOTE}
      />

      <FilterBar
        description="Filter clusters by type, participating entity, and publish-date range."
        actions={
          activeFilters.length > 0 ? (
            <ClearButton
              onClick={() => {
                setEntityInput("");
                setSearchParams(new URLSearchParams(), { replace: true });
              }}
            />
          ) : (
            <span className="text-xs text-slate-500">No filters applied</span>
          )
        }
      >
        <FilterField label="Event type" htmlFor="event-type">
          <Select
            id="event-type"
            value={searchParams.get("event_type") ?? ""}
            onChange={(value) => updateParam("event_type", value)}
            placeholder="All event types"
            options={EVENT_TYPES.map((type) => ({ value: type, label: EVENT_TYPE_LABELS[type] }))}
          />
        </FilterField>

        <FilterField label="Entity" htmlFor="event-entity" hint={debouncedEntity ? `matching “${debouncedEntity}”` : undefined}>
          <TextInput
            id="event-entity"
            value={entityInput}
            onChange={setEntityInput}
            placeholder="Entity name or id"
          />
        </FilterField>

        <FilterField label="Publish date from" htmlFor="event-from">
          <TextInput
            id="event-from"
            type="date"
            value={searchParams.get("date_from") ?? ""}
            onChange={(value) => updateParam("date_from", value)}
          />
        </FilterField>

        <FilterField label="Publish date to" htmlFor="event-to">
          <TextInput
            id="event-to"
            type="date"
            value={searchParams.get("date_to") ?? ""}
            onChange={(value) => updateParam("date_to", value)}
          />
        </FilterField>

        {entities.data && entities.data.items.length > 0 ? (
          <FilterField label="Pick entity" htmlFor="event-entity-select">
            <Select
              id="event-entity-select"
              value={searchParams.get("entity") ?? ""}
              onChange={(value) => updateParam("entity", value)}
              placeholder="Any entity"
              options={entities.data.items.map((entity) => ({
                value: entity.entity_id,
                label: entity.canonical_name,
              }))}
            />
          </FilterField>
        ) : null}
      </FilterBar>

      <ActiveFilters
        filters={activeFilters}
        onClear={(label) => {
          const map: Record<string, string> = {
            "event type": "event_type",
            entity: "entity",
            from: "date_from",
            to: "date_to",
          };
          const key = map[label];
          if (key) updateParam(key, null);
        }}
      />

      {events.isLoading ? (
        <LoadingSkeleton variant="table" rows={8} label="Loading event clusters" />
      ) : events.isError ? (
        <ErrorState error={events.error} context="the event list" onRetry={() => void events.refetch()} />
      ) : !events.data || events.data.items.length === 0 ? (
        <EmptyState
          title="No event clusters match these filters"
          description="The corpus returned an empty page for the current filters."
          hint="Clusters are produced by a model over article text; a quiet window may genuinely contain none."
        />
      ) : (
        <>
          <DataTable
            columns={columns}
            rows={events.data.items}
            rowKey={(row) => row.event_id}
            caption="Event clusters with article counts, the three separate dates, and mean classification confidence. Sortable by column header."
            initialSortKey="publish_date"
            initialSortDirection="desc"
            onRowClick={(row) => navigate(`/events/${row.event_id}`)}
          />
          <Pagination
            page={events.data.page}
            pageSize={events.data.page_size}
            total={events.data.total}
            itemNoun="clusters"
            onPageChange={(nextPage) => updateParam("page", String(nextPage))}
            onPageSizeChange={(size) => updateParam("page_size", String(size))}
          />
        </>
      )}

      <section className="rounded-md border border-slate-200 bg-white p-4 text-xs text-slate-600">
        <h2 className="text-sm font-semibold text-slate-900">Why three dates</h2>
        <ul className="mt-2 list-disc space-y-1 pl-4">
          <li>
            <span className="font-medium text-slate-800">Event date</span> — when the thing described
            happened, as stated in the coverage.
          </li>
          <li>
            <span className="font-medium text-slate-800">Publish date</span> — when the earliest
            article in the cluster was published.
          </li>
          <li>
            <span className="font-medium text-slate-800">Processing date</span> — when our pipeline
            read the cluster.
          </li>
        </ul>
        <p className="mt-2">
          They differ, and the difference matters: a cluster processed today may describe something
          that happened a week ago and was reported yesterday.
        </p>
      </section>
    </div>
  );
}
