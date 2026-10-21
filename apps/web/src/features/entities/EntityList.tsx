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
import { EntityTypeBadge } from "../../components/PredictionBadge";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "../../components/states";
import { useEntities } from "../../hooks/useEntities";
import { useDebounced } from "../../hooks/useDebounced";
import {
  ENTITY_TYPES,
  type EntityFilters,
  type EntitySummary,
  type EntityType,
} from "../../lib/schemas";
import { ENTITY_TYPE_DESCRIPTIONS } from "../../lib/schemas";
import { ENTITY_STYLES, formatDate, formatNumber } from "../../lib/format";

const DEFAULT_PAGE_SIZE = 25;

/**
 * Entity directory.
 *
 * Ambiguous mentions are surfaced as their own column rather than folded into
 * the mention count — a resolver that could not decide is a different fact
 * from a resolution that succeeded.
 */
export function EntityList() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const page = Number.parseInt(searchParams.get("page") ?? "1", 10) || 1;
  const pageSize = Number.parseInt(searchParams.get("page_size") ?? String(DEFAULT_PAGE_SIZE), 10) || DEFAULT_PAGE_SIZE;

  const [searchInput, setSearchInput] = useState(searchParams.get("q") ?? "");
  const debouncedSearch = useDebounced(searchInput, 350);

  const filters = useMemo<EntityFilters>(
    () => ({
      entity_type: (searchParams.get("entity_type") as EntityType | null) ?? "",
      q: debouncedSearch || undefined,
      page,
      page_size: pageSize,
    }),
    [searchParams, debouncedSearch, page, pageSize],
  );

  const entities = useEntities(filters);

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
    const type = searchParams.get("entity_type");
    if (type) list.push({ label: "type", value: type });
    if (debouncedSearch) list.push({ label: "search", value: debouncedSearch });
    return list;
  }, [searchParams, debouncedSearch]);

  const columns: Column<EntitySummary>[] = [
    {
      key: "canonical_name",
      header: "Entity",
      sortValue: (row) => row.canonical_name,
      render: (row) => (
        <div className="min-w-0">
          <span className="font-medium text-brand-900">{row.canonical_name}</span>
          <p className="mt-0.5 font-mono text-[0.65rem] text-slate-500">{row.entity_id}</p>
        </div>
      ),
    },
    {
      key: "entity_type",
      header: "Type",
      sortValue: (row) => row.entity_type,
      description: "Primary type only. Regulators are typed REGULATOR, never ORG.",
      render: (row) => <EntityTypeBadge type={row.entity_type} />,
    },
    {
      key: "aliases",
      header: "Aliases",
      className: "hidden md:table-cell",
      sortValue: (row) => row.aliases.length,
      render: (row) =>
        row.aliases.length === 0 ? (
          <span className="text-xs text-slate-400">none recorded</span>
        ) : (
          <span className="space-x-1">
            {row.aliases.slice(0, 3).map((alias) => (
              <span
                key={alias}
                className="inline-block rounded bg-slate-100 px-1.5 py-0.5 text-[0.7rem] text-slate-700"
              >
                {alias}
              </span>
            ))}
            {row.aliases.length > 3 ? (
              <span className="text-[0.7rem] text-slate-500">+{row.aliases.length - 3}</span>
            ) : null}
          </span>
        ),
    },
    {
      key: "mention_count",
      header: "Mentions",
      align: "right",
      sortValue: (row) => row.mention_count,
      render: (row) => <span className="tabular-nums">{formatNumber(row.mention_count)}</span>,
    },
    {
      key: "ambiguous_mention_count",
      header: "Ambiguous",
      align: "right",
      sortValue: (row) => row.ambiguous_mention_count,
      description: "Mentions the resolver could not confidently attach to one entity. Counted separately, never folded into the total.",
      render: (row) =>
        row.ambiguous_mention_count === 0 ? (
          <span className="tabular-nums text-slate-400">0</span>
        ) : (
          <span
            className="tabular-nums font-medium text-amber-800"
            title="The resolver flagged these mentions as ambiguous."
          >
            {formatNumber(row.ambiguous_mention_count)}
          </span>
        ),
    },
    {
      key: "last_seen_at",
      header: "Last seen",
      className: "hidden lg:table-cell",
      sortValue: (row) => row.last_seen_at,
      render: (row) => <span className="whitespace-nowrap text-xs">{formatDate(row.last_seen_at)}</span>,
    },
  ];

  return (
    <div className="space-y-6">
      <SectionHeader
        as="h1"
        eyebrow="Entities"
        title="Entity directory"
        subtitle="Canonical entities the resolver has linked coverage to, with the aliases that map to each one. Ambiguous mentions are counted separately from resolved mentions."
      />

      <FilterBar
        description="Filter by primary type or by name/alias text."
        actions={
          activeFilters.length > 0 ? (
            <ClearButton
              onClick={() => {
                setSearchInput("");
                setSearchParams(new URLSearchParams(), { replace: true });
              }}
            />
          ) : (
            <span className="text-xs text-slate-500">No filters applied</span>
          )
        }
      >
        <FilterField label="Search" htmlFor="entity-q" className="min-w-[14rem] flex-1">
          <TextInput
            id="entity-q"
            value={searchInput}
            onChange={setSearchInput}
            placeholder="Canonical name or alias"
          />
        </FilterField>

        <FilterField label="Entity type" htmlFor="entity-type">
          <Select
            id="entity-type"
            value={searchParams.get("entity_type") ?? ""}
            onChange={(value) => updateParam("entity_type", value)}
            placeholder="All types"
            options={ENTITY_TYPES.map((type) => ({
              value: type,
              label: `${type} — ${ENTITY_TYPE_DESCRIPTIONS[type]}`,
            }))}
          />
        </FilterField>
      </FilterBar>

      <ActiveFilters
        filters={activeFilters}
        onClear={(label) => {
          if (label === "search") {
            setSearchInput("");
            updateParam("q", null);
            return;
          }
          updateParam("entity_type", null);
        }}
      />

      {entities.isLoading ? (
        <LoadingSkeleton variant="table" rows={8} label="Loading entities" />
      ) : entities.isError ? (
        <ErrorState error={entities.error} context="the entity directory" onRetry={() => void entities.refetch()} />
      ) : !entities.data || entities.data.items.length === 0 ? (
        <EmptyState
          title="No entities match these filters"
          description="The entity index returned an empty page."
          hint="Try a different entity type, or clear the search text."
        />
      ) : (
        <>
          <DataTable
            columns={columns}
            rows={entities.data.items}
            rowKey={(row) => row.entity_id}
            caption="Canonical entities with aliases, resolved mention counts, and ambiguous mention counts. Sortable by column header."
            initialSortKey="mention_count"
            initialSortDirection="desc"
            onRowClick={(row) => navigate(`/entities/${row.entity_id}`)}
          />
          <Pagination
            page={entities.data.page}
            pageSize={entities.data.page_size}
            total={entities.data.total}
            itemNoun="entities"
            onPageChange={(nextPage) => updateParam("page", String(nextPage))}
            onPageSizeChange={(size) => updateParam("page_size", String(size))}
          />
        </>
      )}

      {/* --- Type key ----------------------------------------------------- */}
      <section className="nfs-card" aria-labelledby="entity-types">
        <SectionHeader
          id="entity-types"
          title="Entity type key"
          subtitle="A span carries exactly one primary type. Regulators are REGULATOR rather than ORG, and money, tickers, and currencies are kept distinct from one another."
        />
        <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {ENTITY_TYPES.map((type) => (
            <li key={type} className="flex items-start gap-2">
              <span
                aria-hidden="true"
                className="mt-0.5 h-3 w-3 shrink-0 rounded-sm ring-1 ring-inset ring-black/10"
                style={{ backgroundColor: ENTITY_STYLES[type].hex }}
              />
              <div>
                <p className="font-mono text-xs font-medium text-slate-800">{type}</p>
                <p className="text-[0.7rem] text-slate-600">{ENTITY_TYPE_DESCRIPTIONS[type]}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
