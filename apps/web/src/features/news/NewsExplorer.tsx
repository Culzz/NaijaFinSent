import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { DataTable, type Column } from "../../components/DataTable";
import {
  ActiveFilters,
  ClearButton,
  FilterBar,
  FilterField,
  Select,
  TextInput,
} from "../../components/FilterBar";
import { Pagination } from "../../components/Pagination";
import { EventTypeBadge, PredictionBadge } from "../../components/PredictionBadge";
import { CoverageTag } from "../../components/StatCard";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "../../components/states";
import { useEntities } from "../../hooks/useEntities";
import { useNews } from "../../hooks/useNews";
import { useDebounced } from "../../hooks/useDebounced";
import { useHealth } from "../../hooks/useHealth";
import { isApiError } from "../../lib/api";
import { DEMO_PUBLISHERS } from "../../lib/fallbacks";
import {
  ENTITY_TYPES,
  EVENT_TYPES,
  SENTIMENT_LABELS,
  type EntityType,
  type EventType,
  type NewsFilters,
  type NewsListItem,
  type SentimentLabel,
} from "../../lib/schemas";
import { eventTypeLabel, entityStyle, formatDate, hostnameOf, truncate } from "../../lib/format";
import { statusStyle } from "../../lib/format";
import { ProvenanceChip } from "../../components/PredictionBadge";

const DEFAULT_PAGE_SIZE = 20;

/**
 * News explorer.
 *
 * Filters live in the URL so a view is shareable and the back button behaves.
 * Every row states where the language label came from via the model chip on the
 * detail page; here we keep the row compact but never drop the status.
 */
export function NewsExplorer() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const page = Number.parseInt(searchParams.get("page") ?? "1", 10) || 1;
  const pageSize = Number.parseInt(searchParams.get("page_size") ?? String(DEFAULT_PAGE_SIZE), 10) || DEFAULT_PAGE_SIZE;

  const [searchInput, setSearchInput] = useState(searchParams.get("q") ?? "");
  const debouncedSearch = useDebounced(searchInput, 350);

  const publishers = usePublisherOptions();
  const entities = useEntities({ page: 1, page_size: 100 });

  const filters = useMemo<NewsFilters>(
    () => ({
      publisher: searchParams.get("publisher") ?? undefined,
      date_from: searchParams.get("date_from") ?? undefined,
      date_to: searchParams.get("date_to") ?? undefined,
      entity: searchParams.get("entity") ?? undefined,
      event_type: (searchParams.get("event_type") as EventType | null) ?? "",
      sentiment: (searchParams.get("sentiment") as SentimentLabel | null) ?? "",
      q: debouncedSearch || undefined,
      page,
      page_size: pageSize,
    }),
    [searchParams, debouncedSearch, page, pageSize],
  );

  const news = useNews(filters);

  function updateParam(key: string, value: string | null) {
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (value === null || value === "") next.delete(key);
        else next.set(key, value);
        // Any filter change resets to page 1 so the user never lands on an
        // out-of-range page after narrowing.
        if (key !== "page" && key !== "page_size") next.delete("page");
        return next;
      },
      { replace: true },
    );
  }

  function clearFilters() {
    setSearchInput("");
    setSearchParams(new URLSearchParams(), { replace: true });
  }

  const activeFilters = useMemo(() => {
    const list: Array<{ label: string; value: string }> = [];
    const publisher = searchParams.get("publisher");
    if (publisher) list.push({ label: "publisher", value: publisher });
    const entity = searchParams.get("entity");
    if (entity) list.push({ label: "entity", value: entity });
    const eventType = searchParams.get("event_type");
    if (eventType) list.push({ label: "event", value: eventType });
    const sentiment = searchParams.get("sentiment");
    if (sentiment) list.push({ label: "sentiment", value: sentiment });
    const from = searchParams.get("date_from");
    if (from) list.push({ label: "from", value: from });
    const to = searchParams.get("date_to");
    if (to) list.push({ label: "to", value: to });
    if (debouncedSearch) list.push({ label: "search", value: debouncedSearch });
    return list;
  }, [searchParams, debouncedSearch]);

  const columns: Column<NewsListItem>[] = [
    {
      key: "title",
      header: "Article",
      sortValue: (row) => row.title,
      render: (row) => (
        <div className="min-w-0 max-w-md">
          <span className="font-medium text-brand-900">{row.title}</span>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[0.7rem] text-slate-500">
            <a
              href={row.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(event) => event.stopPropagation()}
              className="underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
            >
              {hostnameOf(row.url)} ↗
            </a>
            {row.is_official_release ? (
              <span className="rounded bg-brand-50 px-1.5 py-0.5 font-medium text-brand-800 ring-1 ring-inset ring-brand-300">
                official release
              </span>
            ) : null}
          </div>
          {row.snippet ? (
            <p className="mt-1 text-xs text-slate-600">{truncate(row.snippet, 140)}</p>
          ) : null}
        </div>
      ),
    },
    {
      key: "publisher",
      header: "Publisher",
      sortValue: (row) => row.publisher,
      render: (row) => <span className="text-xs text-slate-700">{row.publisher}</span>,
    },
    {
      key: "published_at",
      header: "Published",
      sortValue: (row) => row.published_at,
      render: (row) => (
        <span className="whitespace-nowrap text-xs text-slate-700">{formatDate(row.published_at)}</span>
      ),
    },
    {
      key: "sentiment",
      header: "Language label",
      sortValue: (row) => row.sentiment?.label ?? null,
      description: "The sentiment label assigned to the article's language.",
      render: (row) =>
        row.status === "failed" ? (
          <span className="rounded-full bg-rose-50 px-2 py-0.5 text-[0.7rem] font-medium text-rose-800 ring-1 ring-inset ring-rose-300">
            pipeline failed
          </span>
        ) : (
          <PredictionBadge
            label={row.sentiment?.label ?? null}
            confidence={row.sentiment?.confidence ?? null}
            empty={!row.sentiment}
          />
        ),
    },
    {
      key: "event_types",
      header: "Events",
      className: "hidden md:table-cell",
      render: (row) =>
        row.event_types.length === 0 ? (
          <span className="text-xs text-slate-400">none</span>
        ) : (
          <span className="flex flex-wrap gap-1">
            {row.event_types.map((type) => (
              <EventTypeBadge key={type} type={type} />
            ))}
          </span>
        ),
    },
    {
      key: "status",
      header: "Pipeline",
      sortValue: (row) => row.status,
      className: "hidden lg:table-cell",
      description: "Processing status. 'partial' means some pipeline stages failed.",
      render: (row) => {
        const style = statusStyle(row.status);
        return (
          <span className={`inline-flex rounded px-1.5 py-0.5 text-[0.7rem] font-medium ${style.badge}`} title={style.description}>
            {style.label}
          </span>
        );
      },
    },
    {
      key: "relations",
      header: "Relations",
      className: "hidden xl:table-cell",
      description: "Duplicate and syndication relations are model-inferred.",
      render: (row) =>
        row.is_duplicate || row.syndicated_from ? (
          <span className="space-x-1">
            {row.is_duplicate ? (
              <span
                className="rounded bg-amber-50 px-1.5 py-0.5 text-[0.65rem] text-amber-900 ring-1 ring-inset ring-amber-300"
                title="A model judged this to be a duplicate of another article."
              >
                duplicate
              </span>
            ) : null}
            {row.syndicated_from ? (
              <span
                className="rounded bg-slate-100 px-1.5 py-0.5 text-[0.65rem] text-slate-700 ring-1 ring-inset ring-slate-300"
                title="Provenance: this article was republished from another source."
              >
                syndicated
              </span>
            ) : null}
          </span>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <SectionHeader
        as="h1"
        eyebrow="News"
        title="News explorer"
        subtitle="Articles in the corpus with the language labels, event classifications, and duplicate relations attached to them. Duplicates and syndication are model-inferred, never verified."
        actions={<CoverageTag />}
      />

      <FilterBar
        description="Filters apply to article metadata and the labels attached to each article."
        actions={
          activeFilters.length > 0 ? (
            <ClearButton onClick={clearFilters} />
          ) : (
            <span className="text-xs text-slate-500">No filters applied</span>
          )
        }
      >
        <FilterField label="Search" htmlFor="filter-q" className="min-w-[14rem] flex-1">
          <TextInput
            id="filter-q"
            value={searchInput}
            onChange={setSearchInput}
            placeholder="Title, publisher, or preview text"
          />
        </FilterField>

        <FilterField label="Publisher" htmlFor="filter-publisher">
          <Select
            id="filter-publisher"
            value={searchParams.get("publisher") ?? ""}
            onChange={(value) => updateParam("publisher", value)}
            placeholder="All publishers"
            options={publishers.map((name) => ({ value: name, label: name }))}
          />
        </FilterField>

        <FilterField label="Entity" htmlFor="filter-entity">
          <Select
            id="filter-entity"
            value={searchParams.get("entity") ?? ""}
            onChange={(value) => updateParam("entity", value)}
            placeholder="All entities"
            disabled={entities.isLoading}
            options={(entities.data?.items ?? []).map((entity) => ({
              value: entity.entity_id,
              label: `${entity.canonical_name} (${entity.entity_type})`,
            }))}
          />
        </FilterField>

        <FilterField label="Event type" htmlFor="filter-event">
          <Select
            id="filter-event"
            value={searchParams.get("event_type") ?? ""}
            onChange={(value) => updateParam("event_type", value)}
            placeholder="All event types"
            options={EVENT_TYPES.map((type) => ({ value: type, label: eventTypeLabel(type) }))}
          />
        </FilterField>

        <FilterField label="Language label" htmlFor="filter-sentiment">
          <Select
            id="filter-sentiment"
            value={searchParams.get("sentiment") ?? ""}
            onChange={(value) => updateParam("sentiment", value)}
            placeholder="All labels"
            options={SENTIMENT_LABELS.map((label) => ({ value: label, label }))}
          />
        </FilterField>

        <FilterField label="Published from" htmlFor="filter-from">
          <TextInput
            id="filter-from"
            type="date"
            value={searchParams.get("date_from") ?? ""}
            onChange={(value) => updateParam("date_from", value)}
          />
        </FilterField>

        <FilterField label="Published to" htmlFor="filter-to">
          <TextInput
            id="filter-to"
            type="date"
            value={searchParams.get("date_to") ?? ""}
            onChange={(value) => updateParam("date_to", value)}
          />
        </FilterField>
      </FilterBar>

      <ActiveFilters
        filters={activeFilters}
        onClear={(label) => {
          const map: Record<string, string> = {
            publisher: "publisher",
            entity: "entity",
            event: "event_type",
            sentiment: "sentiment",
            from: "date_from",
            to: "date_to",
          };
          if (label === "search") {
            setSearchInput("");
            updateParam("q", null);
            return;
          }
          const key = map[label];
          if (key) updateParam(key, null);
        }}
      />

      {news.isLoading ? (
        <LoadingSkeleton variant="table" rows={8} label="Loading articles" />
      ) : news.isError ? (
        <ErrorState error={news.error} context="the news list" onRetry={() => void news.refetch()} />
      ) : !news.data || news.data.items.length === 0 ? (
        <EmptyState
          title="No articles match these filters"
          description="The corpus returned an empty page for the current filter combination."
          hint="Try removing the entity or event filter, widening the date range, or clearing the search text."
          action={activeFilters.length > 0 ? <ClearButton onClick={clearFilters} /> : undefined}
        />
      ) : (
        <>
          <DataTable
            columns={columns}
            rows={news.data.items}
            rowKey={(row) => row.article_id}
            caption="Articles with their language labels, event classifications, pipeline status, and duplicate relations. Sortable by clicking a column header."
            onRowClick={(row) => {
              navigate(`/news/${row.article_id}`);
            }}
          />

          <Pagination
            page={news.data.page}
            pageSize={news.data.page_size}
            total={news.data.total}
            itemNoun="articles"
            onPageChange={(nextPage) => updateParam("page", String(nextPage))}
            onPageSizeChange={(size) => updateParam("page_size", String(size))}
          />
        </>
      )}

      <section className="rounded-md border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-900">Reading these columns</h2>
        <dl className="mt-2 grid gap-3 text-xs sm:grid-cols-2">
          <div>
            <dt className="font-medium text-slate-700">Language label</dt>
            <dd className="text-slate-600">
              The sentiment label assigned to the article's language. It is a measurement of wording,
              not a statement about the company or the market.
            </dd>
          </div>
          <div className="space-y-1">
            <dt className="font-medium text-slate-700">Duplicate / syndicated</dt>
            <dd className="flex flex-wrap items-center gap-1 text-slate-600">
              <ProvenanceChip kind="model" /> Duplicates are judged by a model. Syndication is
              provenance metadata from the source.
            </dd>
          </div>
          <div>
            <dt className="font-medium text-slate-700">Pipeline status</dt>
            <dd className="text-slate-600">
              <span className="font-medium">partial</span> means some stages failed; the labels shown
              cover only the stages that succeeded.
            </dd>
          </div>
          <div>
            <dt className="font-medium text-slate-700">Entity types</dt>
            <dd className="flex flex-wrap items-center gap-1.5 text-slate-600">
              {ENTITY_TYPES.slice(0, 4).map((type: EntityType) => (
                <span
                  key={type}
                  className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[0.65rem]"
                  style={{ backgroundColor: `${entityStyle(type).hex}1a`, color: entityStyle(type).hex }}
                >
                  {type}
                </span>
              ))}
              <span>…and four more, listed on entity pages.</span>
            </dd>
          </div>
        </dl>
      </section>
    </div>
  );
}

/** Publisher options: from the API when possible, otherwise the demo list. */
function usePublisherOptions(): string[] {
  const health = useHealth();
  const news = useNews({ page: 1, page_size: 100 });
  return useMemo(() => {
    const fromData = Array.from(new Set((news.data?.items ?? []).map((item) => item.publisher)));
    if (fromData.length > 0) return fromData.sort();
    if (isApiError(health.error)) return DEMO_PUBLISHERS;
    return [];
  }, [news.data, health.error]);
}
