/**
 * SYNTHETIC FIXTURES — clearly fake, for UI review with the backend offline.
 *
 * Everything in this file is invented. Publisher names are "Example …" and all
 * URLs live under `example.ng`. Article ids are prefixed `mock-`. No number in
 * here describes any real market, company, or regulator action.
 *
 * These fixtures exist so a reviewer can see loading/empty/error/populated
 * states without running the API. They are NEVER presented as real corpus.
 */

import type {
  AnalysisResult,
  CopilotAnswer,
  EntityDetail,
  EntitySummary,
  EvaluationError,
  EvaluationSummary,
  EventCount,
  EventDetail,
  EventListItem,
  FreshnessReport,
  HealthStatus,
  LeaderboardRow,
  ModelComparison,
  ModelInfo,
  NarrativeSummary,
  NewsDetail,
  NewsListItem,
  SentimentTrendPoint,
  TimelineEntry,
  TopicCount,
  Watchlist,
  WatchlistAlert,
} from "../lib/schemas";

const ISO = (daysAgo: number, hour = 9, minute = 30): string => {
  const base = Date.UTC(2024, 2, 18, hour, minute, 0); // 2024-03-18
  return new Date(base - daysAgo * 86_400_000).toISOString();
};

const DATE = (daysAgo: number): string => ISO(daysAgo).slice(0, 10);

// ---------------------------------------------------------------------------
// Shared model refs — versions are fake
// ---------------------------------------------------------------------------

const SENTIMENT_MODEL = {
  name: "mock-sentiment-tfidf-lr",
  version: "0.4.0-mock",
  task: "sentiment",
  calibrated: true,
} as const;

const NER_MODEL = {
  name: "mock-ner-crf",
  version: "0.3.1-mock",
  task: "ner",
  calibrated: false,
} as const;

const EVENT_MODEL = {
  name: "mock-events-trigger",
  version: "0.2.0-mock",
  task: "events",
  calibrated: true,
} as const;

const ENTITY_SENTIMENT_MODEL = {
  name: "mock-entity-sentiment",
  version: "0.1.3-mock",
  task: "entity_sentiment",
  calibrated: false,
} as const;

const MOCK_LIMITATIONS: string[] = [
  "[synthetic fixture] These numbers are fabricated for UI review, not measured from a real corpus.",
  "Sentiment is a measurement of language in coverage, not investor sentiment or a price forecast.",
  "Evidence spans show supporting text only; they are not causal attribution.",
  "Uncertain and neutral are distinct labels and must not be merged.",
];

// ---------------------------------------------------------------------------
// Article bodies — invented text
// ---------------------------------------------------------------------------

const BODY_ACCESS = `Example Bank Plc said on Monday that it had completed a ₦120 billion rights issue, according to a filing published on the Example Exchange.

"We expect the proceeds to lift our capital adequacy ratio above the regulatory minimum," the bank's chief financial officer said in the filing. The statement did not give a completion date for the allotment.

The Central Bank of Nigeria had earlier signalled that systemically important banks would face a higher capital threshold. Analysts at Example Capital said the timing was "broadly in line with expectations", though they cautioned that the final ratio would depend on risk-weighted assets at year end.

A second report on the same filing was published by another outlet later in the day.`;

const BODY_RATE = `The Central Bank of Nigeria held its benchmark policy rate, saying the decision reflected "the balance of risks to the inflation outlook", in a communiqué read after the monetary policy meeting.

The regulator noted that liquidity conditions had tightened, and that it would continue to monitor the exchange rate. "The committee does not expect a sustained pass-through in the near term," the communiqué said.

Commentary published afterwards described the tone as cautious. One analyst wrote that the language left "room for a move either way" at the next meeting, which the analyst characterised as deliberately non-committal.`;

const BODY_FX = `The naira weakened against the dollar in the official window, according to data published by the Example Exchange, while the parallel market rate moved by a smaller margin.

Traders quoted by Example Wire attributed the move to seasonal demand. "We don't have enough visibility to say this is the start of a trend," one trader said.

The report noted that the regulator has not issued new guidance on the window, and that the previous circular remains in force.`;

const BODY_ENERGY = `Output from a major Example Delta field fell after an unplanned outage, the operator said, without giving a restart date.

The operator said the incident affected a processing train used for gas supply. "We are working to restore operations," a spokesperson said. The statement did not estimate the volume lost.

A trade publication reported that the outage could tighten domestic gas supply if it extends beyond a week, adding that no independent confirmation was available at the time of writing.`;

const BODY_SANCTION = `The Example Securities Commission fined an Example brokerage for reporting failures, ordering it to remediate its systems within 90 days.

The regulator said the failures related to late disclosure of a shareholding change. The brokerage said it "accepts the findings" and would comply.

Coverage of the penalty noted that the fine was smaller than the maximum available, which one commentator described as proportionate.`;

const BODY_DIVIDEND = `Example Cement Plc declared a final dividend of ₦2.50 per share, subject to shareholder approval at the annual general meeting, according to a notice published on the Example Exchange.

The notice stated that the register of members would close next month. It did not specify a payment date.

A syndicated version of the notice appeared on a second outlet's site with identical wording.`;

// ---------------------------------------------------------------------------
// Article records
// ---------------------------------------------------------------------------

interface ArticleSeed {
  id: string;
  title: string;
  publisher: string;
  sourceId: string;
  body: string;
  daysAgo: number;
  status: NewsListItem["status"];
  official: boolean;
  sentimentLabel: NewsListItem["sentiment"] extends infer _ ? "positive" | "negative" | "neutral" | "uncertain" : never;
  confidence: number;
  eventTypes: NewsListItem["event_types"];
  entityIds: string[];
  isDuplicate?: boolean;
  duplicateOf?: string | null;
  syndicatedFrom?: string | null;
}

const ARTICLE_SEEDS: ArticleSeed[] = [
  {
    id: "mock-art-0001",
    title: "Example Bank completes ₦120bn rights issue",
    publisher: "Example Business Daily",
    sourceId: "example-businessdaily",
    body: BODY_ACCESS,
    daysAgo: 0,
    status: "complete",
    official: false,
    sentimentLabel: "positive",
    confidence: 0.78,
    eventTypes: ["capital_raise"],
    entityIds: ["mock-ent-exbank", "mock-ent-cbn", "mock-ent-exch"],
  },
  {
    id: "mock-art-0002",
    title: "Example Bank rights issue: what the filing said",
    publisher: "Example Wire",
    sourceId: "example-wire",
    body: BODY_ACCESS,
    daysAgo: 0,
    status: "complete",
    official: false,
    sentimentLabel: "positive",
    confidence: 0.64,
    eventTypes: ["capital_raise"],
    entityIds: ["mock-ent-exbank"],
    isDuplicate: true,
    duplicateOf: "mock-art-0001",
  },
  {
    id: "mock-art-0003",
    title: "CBN holds benchmark rate, cites balance of risks",
    publisher: "Example Business Daily",
    sourceId: "example-businessdaily",
    body: BODY_RATE,
    daysAgo: 1,
    status: "complete",
    official: false,
    sentimentLabel: "neutral",
    confidence: 0.71,
    eventTypes: ["cbn_policy"],
    entityIds: ["mock-ent-cbn"],
  },
  {
    id: "mock-art-0004",
    title: "CBN communiqué: rate unchanged",
    publisher: "Example Official Gazette",
    sourceId: "example-official",
    body: BODY_RATE,
    daysAgo: 1,
    status: "complete",
    official: true,
    sentimentLabel: "neutral",
    confidence: 0.83,
    eventTypes: ["cbn_policy"],
    entityIds: ["mock-ent-cbn"],
    syndicatedFrom: null,
  },
  {
    id: "mock-art-0005",
    title: "Naira slips in official window as seasonal demand builds",
    publisher: "Example Wire",
    sourceId: "example-wire",
    body: BODY_FX,
    daysAgo: 2,
    status: "partial",
    official: false,
    sentimentLabel: "uncertain",
    confidence: 0.52,
    eventTypes: ["fx_move"],
    entityIds: ["mock-ent-naira"],
  },
  {
    id: "mock-art-0006",
    title: "Example Delta outage hits gas supply train",
    publisher: "Example Energy Review",
    sourceId: "example-energy",
    body: BODY_ENERGY,
    daysAgo: 3,
    status: "complete",
    official: false,
    sentimentLabel: "negative",
    confidence: 0.74,
    eventTypes: ["oil_energy"],
    entityIds: ["mock-ent-delta"],
  },
  {
    id: "mock-art-0007",
    title: "Commission fines Example brokerage over disclosure failures",
    publisher: "Example Business Daily",
    sourceId: "example-businessdaily",
    body: BODY_SANCTION,
    daysAgo: 5,
    status: "complete",
    official: false,
    sentimentLabel: "negative",
    confidence: 0.81,
    eventTypes: ["regulatory_sanction"],
    entityIds: ["mock-ent-esc", "mock-ent-broker"],
  },
  {
    id: "mock-art-0008",
    title: "Example Cement declares ₦2.50 final dividend",
    publisher: "Example Exchange Notices",
    sourceId: "example-exchange",
    body: BODY_DIVIDEND,
    daysAgo: 7,
    status: "complete",
    official: true,
    sentimentLabel: "positive",
    confidence: 0.8,
    eventTypes: ["dividend"],
    entityIds: ["mock-ent-cement", "mock-ent-exch"],
  },
  {
    id: "mock-art-0009",
    title: "Example Cement dividend notice syndicated",
    publisher: "Example Wire",
    sourceId: "example-wire",
    body: BODY_DIVIDEND,
    daysAgo: 7,
    status: "complete",
    official: false,
    sentimentLabel: "positive",
    confidence: 0.69,
    eventTypes: ["dividend"],
    entityIds: ["mock-ent-cement"],
    isDuplicate: true,
    duplicateOf: "mock-art-0008",
    syndicatedFrom: "mock-art-0008",
  },
  {
    id: "mock-art-0010",
    title: "Pipeline stage failed on an Example Wire file",
    publisher: "Example Wire",
    sourceId: "example-wire",
    body: BODY_FX,
    daysAgo: 9,
    status: "failed",
    official: false,
    sentimentLabel: "neutral",
    confidence: 0,
    eventTypes: [],
    entityIds: [],
  },
  {
    id: "mock-art-0011",
    title: "Example Bank AGM date set as capital plan advances",
    publisher: "Example Business Daily",
    sourceId: "example-businessdaily",
    body: BODY_ACCESS,
    daysAgo: 11,
    status: "complete",
    official: false,
    sentimentLabel: "positive",
    confidence: 0.61,
    eventTypes: ["capital_raise", "earnings"],
    entityIds: ["mock-ent-exbank"],
  },
  {
    id: "mock-art-0012",
    title: "Analysts split on naira path after window adjustment",
    publisher: "Example Capital Notes",
    sourceId: "example-capital",
    body: BODY_FX,
    daysAgo: 13,
    status: "complete",
    official: false,
    sentimentLabel: "uncertain",
    confidence: 0.48,
    eventTypes: ["fx_move"],
    entityIds: ["mock-ent-naira"],
  },
];

function snippetOf(body: string): string {
  const first = body.split("\n\n")[0] ?? body;
  return first.length > 220 ? `${first.slice(0, 219)}…` : first;
}

function evidenceFor(body: string, phrase: string) {
  const start = body.indexOf(phrase);
  if (start < 0) return [];
  return [{ text: phrase, start, end: start + phrase.length }];
}

// ---------------------------------------------------------------------------
// Derived builders
// ---------------------------------------------------------------------------

export const mockNewsList: NewsListItem[] = ARTICLE_SEEDS.map((seed) => ({
  article_id: seed.id,
  title: seed.title,
  publisher: seed.publisher,
  source_id: seed.sourceId,
  url: `https://${seed.sourceId}.example.ng/${seed.id}`,
  canonical_url: `https://${seed.sourceId}.example.ng/${seed.id}`,
  published_at: ISO(seed.daysAgo),
  fetched_at: ISO(seed.daysAgo, 10, 5),
  is_official_release: seed.official,
  is_duplicate: seed.isDuplicate ?? false,
  duplicate_of: seed.duplicateOf ?? null,
  syndicated_from: seed.syndicatedFrom ?? null,
  status: seed.status,
  sentiment:
    seed.status === "failed"
      ? null
      : {
          label: seed.sentimentLabel,
          confidence: seed.confidence,
          probabilities: {
            positive: seed.sentimentLabel === "positive" ? seed.confidence : 0.08,
            negative: seed.sentimentLabel === "negative" ? seed.confidence : 0.08,
            neutral: seed.sentimentLabel === "neutral" ? seed.confidence : 0.1,
            uncertain: seed.sentimentLabel === "uncertain" ? seed.confidence : 0.06,
          },
          evidence: evidenceFor(seed.body, seed.body.split("\n\n")[0]?.slice(0, 60) ?? ""),
          model: { ...SENTIMENT_MODEL },
        },
  event_types: seed.eventTypes,
  entity_ids: seed.entityIds,
  snippet: snippetOf(seed.body),
}));

function seedById(id: string): ArticleSeed | undefined {
  return ARTICLE_SEEDS.find((seed) => seed.id === id);
}

function toNewsDetail(seed: ArticleSeed): NewsDetail {
  const listItem = mockNewsList.find((item) => item.article_id === seed.id);
  if (!listItem) throw new Error(`mock fixture missing list item ${seed.id}`);

  const duplicateSeeds = ARTICLE_SEEDS.filter(
    (other) => other.id !== seed.id && (other.duplicateOf === seed.id || seed.duplicateOf === other.id),
  );

  return {
    ...listItem,
    content: seed.body,
    language: "en",
    content_hash: `mock-sha256-${seed.id}`,
    entities: buildEntities(seed),
    entity_sentiments: (seed.entityIds.length > 0
      ? seed.entityIds.slice(0, 2)
      : []
    ).map((entityId) => ({
      entity_id: entityId,
      canonical_name: entityName(entityId),
      label: seed.sentimentLabel,
      confidence: Math.max(0.3, seed.confidence - 0.12),
      evidence: evidenceFor(seed.body, seed.body.split("\n\n")[0]?.slice(0, 40) ?? ""),
      model: { ...ENTITY_SENTIMENT_MODEL },
    })),
    events: seed.eventTypes.map((eventType) => ({
      event_type: eventType,
      confidence: Math.max(0.35, seed.confidence - 0.05),
      event_date: DATE(seed.daysAgo + 1),
      entities: buildEntities(seed).slice(0, 3),
      evidence: evidenceFor(seed.body, seed.body.split("\n\n")[0]?.slice(0, 50) ?? ""),
      attributes: {
        "[synthetic]": true,
        note: "attributes are invented for fixture review",
      },
      model: { ...EVENT_MODEL },
    })),
    limitations: MOCK_LIMITATIONS,
    duplicates: duplicateSeeds.map((other) => ({
      article_id: other.id,
      title: other.title,
      publisher: other.publisher,
      url: `https://${other.sourceId}.example.ng/${other.id}`,
      published_at: ISO(other.daysAgo),
      method: "minhash+lsh (mock)",
      score: 0.93,
      reason: "[synthetic] near-identical opening paragraph and shared filing reference",
    })),
    syndications: ARTICLE_SEEDS.filter((other) => other.syndicatedFrom === seed.id).map((other) => ({
      article_id: other.id,
      title: other.title,
      publisher: other.publisher,
      url: `https://${other.sourceId}.example.ng/${other.id}`,
      published_at: ISO(other.daysAgo),
      method: "syndication feed (mock)",
      score: null,
      reason: "[synthetic] republished notice with unchanged wording",
    })),
  };
}

function entityName(entityId: string): string {
  const map: Record<string, string> = {
    "mock-ent-exbank": "Example Bank Plc",
    "mock-ent-cbn": "Central Bank of Nigeria",
    "mock-ent-exch": "Example Exchange",
    "mock-ent-naira": "naira",
    "mock-ent-delta": "Example Delta",
    "mock-ent-esc": "Example Securities Commission",
    "mock-ent-broker": "Example Brokerage",
    "mock-ent-cement": "Example Cement Plc",
  };
  return map[entityId] ?? "Example Entity";
}

function entityType(entityId: string): EntitySummary["entity_type"] {
  const map: Record<string, EntitySummary["entity_type"]> = {
    "mock-ent-exbank": "ORG",
    "mock-ent-cbn": "REGULATOR",
    "mock-ent-exch": "ORG",
    "mock-ent-naira": "CURRENCY",
    "mock-ent-delta": "ORG",
    "mock-ent-esc": "REGULATOR",
    "mock-ent-broker": "ORG",
    "mock-ent-cement": "TICKER",
  };
  return map[entityId] ?? "ORG";
}

function buildEntities(seed: ArticleSeed) {
  return seed.entityIds.map((entityId, index) => {
    const name = entityName(entityId);
    const start = seed.body.indexOf(name);
    const safeStart = start >= 0 ? start : 0;
    return {
      span: {
        start: safeStart,
        end: safeStart + (start >= 0 ? name.length : 3),
        text: start >= 0 ? name : seed.body.slice(0, 3),
        entity_type: entityType(entityId),
      },
      entity_id: entityId,
      canonical_name: name,
      resolution_method: index === 0 ? "alias" : index === 1 ? "fuzzy" : "embedding",
      confidence: Math.max(0.4, 0.9 - index * 0.12),
    };
  });
}

export const mockNewsDetails: Record<string, NewsDetail> = Object.fromEntries(
  ARTICLE_SEEDS.map((seed) => [seed.id, toNewsDetail(seed)]),
);

// ---------------------------------------------------------------------------
// Entities
// ---------------------------------------------------------------------------

export const mockEntities: EntitySummary[] = [
  {
    entity_id: "mock-ent-exbank",
    canonical_name: "Example Bank Plc",
    entity_type: "ORG",
    aliases: ["Example Bank", "EXBANK", "the bank"],
    mention_count: 34,
    ambiguous_mention_count: 2,
    first_seen_at: ISO(40),
    last_seen_at: ISO(0),
    description: "[synthetic] A fictional deposit money bank used for fixture review.",
  },
  {
    entity_id: "mock-ent-cbn",
    canonical_name: "Central Bank of Nigeria",
    entity_type: "REGULATOR",
    aliases: ["CBN", "the central bank", "the committee"],
    mention_count: 51,
    ambiguous_mention_count: 1,
    first_seen_at: ISO(60),
    last_seen_at: ISO(1),
    description: "[synthetic] Regulator mentions are labelled REGULATOR, never ORG.",
  },
  {
    entity_id: "mock-ent-exch",
    canonical_name: "Example Exchange",
    entity_type: "ORG",
    aliases: ["the exchange", "NGX (mock)"],
    mention_count: 19,
    ambiguous_mention_count: 4,
    first_seen_at: ISO(55),
    last_seen_at: ISO(0),
    description: "[synthetic] Fictional bourse. Ambiguous mentions are counted separately.",
  },
  {
    entity_id: "mock-ent-naira",
    canonical_name: "naira",
    entity_type: "CURRENCY",
    aliases: ["₦", "NGN"],
    mention_count: 27,
    ambiguous_mention_count: 0,
    first_seen_at: ISO(58),
    last_seen_at: ISO(2),
    description: "[synthetic] Currency mentions are typed CURRENCY, not MONEY.",
  },
  {
    entity_id: "mock-ent-cement",
    canonical_name: "Example Cement Plc",
    entity_type: "TICKER",
    aliases: ["EXCEM", "the cement maker"],
    mention_count: 12,
    ambiguous_mention_count: 1,
    first_seen_at: ISO(30),
    last_seen_at: ISO(7),
    description: "[synthetic] Fictional listed issuer.",
  },
  {
    entity_id: "mock-ent-esc",
    canonical_name: "Example Securities Commission",
    entity_type: "REGULATOR",
    aliases: ["the commission", "ESC (mock)"],
    mention_count: 9,
    ambiguous_mention_count: 2,
    first_seen_at: ISO(45),
    last_seen_at: ISO(5),
    description: "[synthetic] Fictional capital-markets regulator.",
  },
  {
    entity_id: "mock-ent-delta",
    canonical_name: "Example Delta",
    entity_type: "SECTOR",
    aliases: ["the delta", "the field"],
    mention_count: 7,
    ambiguous_mention_count: 3,
    first_seen_at: ISO(33),
    last_seen_at: ISO(3),
    description: "[synthetic] Fictional energy producing area.",
  },
  {
    entity_id: "mock-ent-broker",
    canonical_name: "Example Brokerage",
    entity_type: "ORG",
    aliases: ["the brokerage"],
    mention_count: 5,
    ambiguous_mention_count: 0,
    first_seen_at: ISO(44),
    last_seen_at: ISO(5),
    description: "[synthetic] Fictional brokerage firm.",
  },
];

function mentionsForEntity(entityId: string): EntityDetail["mentions"] {
  const seeds = ARTICLE_SEEDS.filter((seed) => seed.entityIds.includes(entityId));
  const name = entityName(entityId);
  return seeds.map((seed) => {
    const start = seed.body.indexOf(name);
    const safeStart = start >= 0 ? start : 0;
    return {
      article_id: seed.id,
      article_title: seed.title,
      publisher: seed.publisher,
      url: `https://${seed.sourceId}.example.ng/${seed.id}`,
      published_at: ISO(seed.daysAgo),
      span: {
        start: safeStart,
        end: safeStart + (start >= 0 ? name.length : 3),
        text: start >= 0 ? name : seed.body.slice(0, 3),
        entity_type: entityType(entityId),
      },
      sentiment: seed.status === "failed" ? null : seed.sentimentLabel,
      confidence: Math.max(0.4, seed.confidence - 0.05),
      resolution_method: "alias",
    };
  });
}

function trendFor(days: number, bias: number): SentimentTrendPoint[] {
  return Array.from({ length: 12 }, (_, i) => {
    const positive = Math.max(0, Math.round(6 + bias + Math.sin(i / 2) * 3));
    const negative = Math.max(0, Math.round(5 - bias + Math.cos(i / 2) * 2));
    const neutral = Math.max(0, Math.round(7 + Math.sin(i / 3) * 2));
    const uncertain = Math.max(0, Math.round(3 + Math.cos(i / 4) * 1.5));
    return {
      period: DATE((11 - i) * days),
      positive,
      negative,
      neutral,
      uncertain,
      mean_score: Number(((positive - negative) / (positive + negative + neutral + uncertain || 1)).toFixed(3)),
    };
  });
}

export const mockEntityDetails: Record<string, EntityDetail> = Object.fromEntries(
  mockEntities.map((entity) => {
    const mentions = mentionsForEntity(entity.entity_id);
    const ambiguous = mentions.filter((m) => m.confidence < 0.6);
    return [
      entity.entity_id,
      {
        ...entity,
        aliases_table: entity.aliases.map((alias, index) => ({
          alias,
          source: index === 0 ? "manual seed (mock)" : "model candidate (mock)",
          confidence: index === 0 ? 1 : Number((0.9 - index * 0.12).toFixed(2)),
          first_seen_at: ISO(40 - index * 3),
        })),
        mentions,
        related_events: mockEvents.filter((event) => event.entity_ids.includes(entity.entity_id)),
        sentiment_trend: trendFor(3, entity.entity_type === "ORG" ? 1 : 0),
        ambiguous_mentions: ambiguous,
        limitations: MOCK_LIMITATIONS,
      } satisfies EntityDetail,
    ];
  }),
);

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

function timelineFor(daysAgo: number, title: string, publisher: string, sourceId: string, eventType: EventDetail["event_type"], body: string): TimelineEntry {
  return [
    {
      published_at: ISO(daysAgo + 2, 8, 0),
      event_date: DATE(daysAgo + 2),
      processed_at: ISO(daysAgo + 2, 8, 4),
      article_id: `mock-art-orig-${daysAgo}`,
      title: `[first report] ${title}`,
      publisher,
      url: `https://${sourceId}.example.ng/orig-${daysAgo}`,
      event_type: eventType,
      sentiment: "neutral",
      is_new_coverage: true,
      is_duplicate: false,
      evidence: evidenceFor(body, body.split("\n\n")[0]?.slice(0, 60) ?? ""),
    },
    {
      published_at: ISO(daysAgo, 9, 15),
      event_date: DATE(daysAgo + 2),
      processed_at: ISO(daysAgo, 9, 22),
      article_id: `mock-art-follow-${daysAgo}`,
      title: `[follow-up] ${title}`,
      publisher: "Example Wire",
      url: `https://example-wire.example.ng/follow-${daysAgo}`,
      event_type: eventType,
      sentiment: "neutral",
      is_new_coverage: true,
      is_duplicate: false,
      evidence: evidenceFor(body, body.split("\n\n")[1]?.slice(0, 60) ?? ""),
    },
    {
      published_at: ISO(daysAgo, 14, 30),
      event_date: DATE(daysAgo + 2),
      processed_at: ISO(daysAgo, 14, 31),
      article_id: `mock-art-repeat-${daysAgo}`,
      title: `[repeat] ${title}`,
      publisher: "Example Capital Notes",
      url: `https://example-capital.example.ng/repeat-${daysAgo}`,
      event_type: eventType,
      sentiment: "neutral",
      is_new_coverage: false,
      is_duplicate: true,
      evidence: evidenceFor(body, body.split("\n\n")[2]?.slice(0, 60) ?? ""),
    },
  ];
}

export const mockEvents: EventListItem[] = [
  {
    event_id: "mock-evt-0001",
    event_type: "capital_raise",
    title: "Example Bank ₦120bn rights issue (synthetic cluster)",
    event_date: DATE(1),
    publish_date: DATE(0),
    processing_date: DATE(0),
    article_count: 3,
    new_article_count: 2,
    repeated_article_count: 1,
    entity_ids: ["mock-ent-exbank"],
    mean_confidence: 0.74,
    model: { ...EVENT_MODEL },
  },
  {
    event_id: "mock-evt-0002",
    event_type: "cbn_policy",
    title: "CBN holds policy rate (synthetic cluster)",
    event_date: DATE(2),
    publish_date: DATE(1),
    processing_date: DATE(1),
    article_count: 4,
    new_article_count: 1,
    repeated_article_count: 3,
    entity_ids: ["mock-ent-cbn"],
    mean_confidence: 0.79,
    model: { ...EVENT_MODEL },
  },
  {
    event_id: "mock-evt-0003",
    event_type: "fx_move",
    title: "Naira move in the official window (synthetic cluster)",
    event_date: DATE(2),
    publish_date: DATE(2),
    processing_date: DATE(2),
    article_count: 2,
    new_article_count: 2,
    repeated_article_count: 0,
    entity_ids: ["mock-ent-naira"],
    mean_confidence: 0.55,
    model: { ...EVENT_MODEL },
  },
  {
    event_id: "mock-evt-0004",
    event_type: "oil_energy",
    title: "Example Delta outage (synthetic cluster)",
    event_date: DATE(3),
    publish_date: DATE(3),
    processing_date: DATE(3),
    article_count: 2,
    new_article_count: 1,
    repeated_article_count: 1,
    entity_ids: ["mock-ent-delta"],
    mean_confidence: 0.68,
    model: { ...EVENT_MODEL },
  },
  {
    event_id: "mock-evt-0005",
    event_type: "regulatory_sanction",
    title: "Example brokerage fined (synthetic cluster)",
    event_date: DATE(6),
    publish_date: DATE(5),
    processing_date: DATE(5),
    article_count: 1,
    new_article_count: 1,
    repeated_article_count: 0,
    entity_ids: ["mock-ent-esc", "mock-ent-broker"],
    mean_confidence: 0.77,
    model: { ...EVENT_MODEL },
  },
  {
    event_id: "mock-evt-0006",
    event_type: "dividend",
    title: "Example Cement final dividend (synthetic cluster)",
    event_date: DATE(8),
    publish_date: DATE(7),
    processing_date: DATE(7),
    article_count: 2,
    new_article_count: 1,
    repeated_article_count: 1,
    entity_ids: ["mock-ent-cement"],
    mean_confidence: 0.72,
    model: { ...EVENT_MODEL },
  },
];

export const mockEventDetails: Record<string, EventDetail> = Object.fromEntries(
  mockEvents.map((event) => {
    const seed = ARTICLE_SEEDS.find((s) => s.eventTypes.includes(event.event_type));
    const body = seed?.body ?? BODY_RATE;
    const daysAgo = seed?.daysAgo ?? 1;
    const timeline = timelineFor(
      daysAgo,
      event.title,
      seed?.publisher ?? "Example Business Daily",
      seed?.sourceId ?? "example-businessdaily",
      event.event_type,
      body,
    );
    return [
      event.event_id,
      {
        ...event,
        entities: (seed ? buildEntities(seed) : []).slice(0, 4),
        timeline,
        new_coverage: timeline.filter((entry) => entry.is_new_coverage),
        repeated_coverage: timeline.filter((entry) => !entry.is_new_coverage),
        whats_new: [
          {
            label: "New detail",
            detail: "[synthetic] A follow-up added an expected completion window that the first report did not carry.",
            article_id: timeline[1]?.article_id ?? null,
            evidence: timeline[1]?.evidence ?? [],
            source: "model_inferred",
          },
          {
            label: "Attribution change",
            detail: "[synthetic] The repeat article attributes the same figures to the earlier report rather than to the primary filing.",
            article_id: timeline[2]?.article_id ?? null,
            evidence: timeline[2]?.evidence ?? [],
            source: "model_inferred",
          },
          {
            label: "No new detail",
            detail: "[synthetic] Otherwise the wording is materially unchanged across the cluster.",
            article_id: null,
            evidence: [],
            source: "model_inferred",
          },
        ],
        dedup_method: "minhash + embedding similarity (mock, model-inferred)",
        limitations: MOCK_LIMITATIONS,
        evidence: timeline[0]?.evidence ?? [],
      } satisfies EventDetail,
    ];
  }),
);

export const mockEventCounts: EventCount[] = [
  { event_type: "cbn_policy", count: 12 },
  { event_type: "earnings", count: 9 },
  { event_type: "dividend", count: 6 },
  { event_type: "mna", count: 3 },
  { event_type: "regulatory_sanction", count: 5 },
  { event_type: "capital_raise", count: 8 },
  { event_type: "fx_move", count: 14 },
  { event_type: "oil_energy", count: 7 },
];

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export const mockSentimentTrend: SentimentTrendPoint[] = trendFor(2, 0);

export const mockTopics: TopicCount[] = [
  { topic: "[synthetic] capital adequacy", count: 21, delta: 4 },
  { topic: "[synthetic] policy rate", count: 18, delta: -2 },
  { topic: "[synthetic] exchange-rate window", count: 15, delta: 6 },
  { topic: "[synthetic] gas supply", count: 9, delta: 1 },
  { topic: "[synthetic] disclosure rules", count: 7, delta: 0 },
];

export const mockFreshness: FreshnessReport = {
  generated_at: ISO(0, 10, 0),
  last_ingestion_at: ISO(0, 6, 0),
  median_lag_minutes: 94,
  buckets: [
    { bucket: "< 1 h", count: 38, share: 0.21 },
    { bucket: "1–6 h", count: 74, share: 0.41 },
    { bucket: "6–24 h", count: 43, share: 0.24 },
    { bucket: "> 24 h", count: 25, share: 0.14 },
  ],
  stale_sources: ["example-energy (mock)", "example-capital (mock)"],
};

// ---------------------------------------------------------------------------
// Models / research
// ---------------------------------------------------------------------------

export const mockModels: ModelInfo[] = [
  {
    name: "mock-sentiment-tfidf-lr",
    version: "0.4.0-mock",
    task: "sentiment",
    framework: "sklearn",
    metrics: { macro_f1: 0.71, accuracy: 0.74, ece: 0.06 },
    trained_at: ISO(20),
    description: "[synthetic] Lexical baseline with isotonic calibration.",
  },
  {
    name: "mock-sentiment-transformer",
    version: "0.5.0-mock",
    task: "sentiment",
    framework: "pytorch",
    metrics: { macro_f1: 0.76, accuracy: 0.78, ece: 0.04 },
    trained_at: ISO(12),
    description: "[synthetic] Fine-tuned encoder, temperature-scaled.",
  },
  {
    name: "mock-ner-crf",
    version: "0.3.1-mock",
    task: "ner",
    framework: "sklearn",
    metrics: { span_f1: 0.68, span_precision: 0.72, span_recall: 0.65 },
    trained_at: ISO(26),
    description: "[synthetic] Sequence labeller over the 8-type span space.",
  },
  {
    name: "mock-events-trigger",
    version: "0.2.0-mock",
    task: "events",
    framework: "sklearn",
    metrics: { macro_f1: 0.61, coverage: 0.55 },
    trained_at: ISO(18),
    description: "[synthetic] Trigger-based event frame classifier.",
  },
];

export const mockLeaderboard: LeaderboardRow[] = [
  {
    rank: 1,
    model: "mock-sentiment-transformer",
    version: "0.5.0-mock",
    task: "sentiment",
    framework: "pytorch",
    primary_metric: "macro_f1",
    primary_value: 0.76,
    metrics: { macro_f1: 0.76, accuracy: 0.78, ece: 0.04 },
    calibrated: true,
    is_baseline: false,
    notes: "[synthetic] best on the time-split test set",
  },
  {
    rank: 2,
    model: "mock-sentiment-tfidf-lr",
    version: "0.4.0-mock",
    task: "sentiment",
    framework: "sklearn",
    primary_metric: "macro_f1",
    primary_value: 0.71,
    metrics: { macro_f1: 0.71, accuracy: 0.74, ece: 0.06 },
    calibrated: true,
    is_baseline: true,
    notes: "[synthetic] lexical baseline",
  },
  {
    rank: 3,
    model: "mock-ner-crf",
    version: "0.3.1-mock",
    task: "ner",
    framework: "sklearn",
    primary_metric: "span_f1",
    primary_value: 0.68,
    metrics: { span_f1: 0.68, span_precision: 0.72, span_recall: 0.65 },
    calibrated: false,
    is_baseline: false,
    notes: "[synthetic] different task; shown for context",
  },
  {
    rank: 4,
    model: "mock-events-trigger",
    version: "0.2.0-mock",
    task: "events",
    framework: "sklearn",
    primary_metric: "macro_f1",
    primary_value: 0.61,
    metrics: { macro_f1: 0.61, coverage: 0.55 },
    calibrated: true,
    is_baseline: false,
    notes: "[synthetic] low coverage; treat slices with care",
  },
];

export const mockModelComparison: ModelComparison[] = [
  {
    task: "sentiment",
    metric: "macro_f1",
    versions: [
      { name: "mock-sentiment-tfidf-lr", version: "0.3.0-mock", value: 0.66, ci_low: 0.62, ci_high: 0.7, n: 402, calibrated: false },
      { name: "mock-sentiment-tfidf-lr", version: "0.4.0-mock", value: 0.71, ci_low: 0.67, ci_high: 0.75, n: 402, calibrated: true },
      { name: "mock-sentiment-transformer", version: "0.5.0-mock", value: 0.76, ci_low: 0.72, ci_high: 0.8, n: 402, calibrated: true },
    ],
  },
  {
    task: "ner",
    metric: "span_f1",
    versions: [
      { name: "mock-ner-crf", version: "0.2.0-mock", value: 0.6, ci_low: 0.56, ci_high: 0.64, n: 318, calibrated: false },
      { name: "mock-ner-crf", version: "0.3.1-mock", value: 0.68, ci_low: 0.64, ci_high: 0.72, n: 318, calibrated: false },
    ],
  },
];

export const mockEvaluation: EvaluationSummary = {
  run_id: "mock-eval-run-001",
  generated_at: ISO(1),
  dataset: "[synthetic] Example Nigerian financial news gold set",
  dataset_version: "mock-2024.03",
  split: "test_time",
  n_items: 402,
  metrics: [
    { metric: "macro_f1", value: 0.71, ci_low: 0.67, ci_high: 0.75, ci_level: 0.95, n: 402 },
    { metric: "accuracy", value: 0.74, ci_low: 0.7, ci_high: 0.78, ci_level: 0.95, n: 402 },
    { metric: "macro_precision", value: 0.72, ci_low: 0.68, ci_high: 0.76, ci_level: 0.95, n: 402 },
    { metric: "macro_recall", value: 0.7, ci_low: 0.66, ci_high: 0.74, ci_level: 0.95, n: 402 },
    { metric: "ece", value: 0.06, ci_low: 0.04, ci_high: 0.09, ci_level: 0.95, n: 402 },
  ],
  slices: [
    {
      slice: "publisher=example-businessdaily",
      slice_kind: "publisher",
      n: 140,
      metrics: [
        { metric: "macro_f1", value: 0.73, ci_low: 0.66, ci_high: 0.8, ci_level: 0.95, n: 140 },
        { metric: "accuracy", value: 0.76, ci_low: 0.69, ci_high: 0.82, ci_level: 0.95, n: 140 },
      ],
    },
    {
      slice: "publisher=example-wire",
      slice_kind: "publisher",
      n: 96,
      metrics: [
        { metric: "macro_f1", value: 0.64, ci_low: 0.55, ci_high: 0.73, ci_level: 0.95, n: 96 },
        { metric: "accuracy", value: 0.68, ci_low: 0.59, ci_high: 0.77, ci_level: 0.95, n: 96 },
      ],
    },
    {
      slice: "length=short (<120 tokens)",
      slice_kind: "length",
      n: 58,
      metrics: [
        { metric: "macro_f1", value: 0.55, ci_low: 0.44, ci_high: 0.66, ci_level: 0.95, n: 58 },
      ],
    },
    {
      slice: "label=uncertain",
      slice_kind: "label",
      n: 61,
      metrics: [
        { metric: "macro_f1", value: 0.42, ci_low: 0.31, ci_high: 0.53, ci_level: 0.95, n: 61 },
      ],
    },
    {
      slice: "event=oil_energy",
      slice_kind: "event_type",
      n: 34,
      metrics: [
        { metric: "macro_f1", value: 0.68, ci_low: 0.54, ci_high: 0.81, ci_level: 0.95, n: 34 },
      ],
    },
  ],
  abstention_rate: 0.07,
  notes: [
    "[synthetic] Confidence intervals are bootstrap estimates over the fixture set.",
    "Slices with n < 40 are reported but should not be over-read.",
  ],
};

export const mockEvaluationErrors: EvaluationError[] = [
  {
    item_id: "mock-item-001",
    article_id: "mock-art-0005",
    url: "https://example-wire.example.ng/mock-art-0005",
    task: "sentiment",
    text: "The naira weakened in the official window. \"We don't have enough visibility to say this is the start of a trend,\" one trader said.",
    gold: "uncertain",
    predicted: "negative",
    error_category: "uncertain → negative",
    split: "test_time",
    model: { ...SENTIMENT_MODEL },
  },
  {
    item_id: "mock-item-002",
    article_id: "mock-art-0003",
    url: "https://example-businessdaily.example.ng/mock-art-0003",
    task: "sentiment",
    text: "The Central Bank of Nigeria held its benchmark policy rate, saying the decision reflected the balance of risks.",
    gold: "neutral",
    predicted: "positive",
    error_category: "neutral → positive",
    split: "test_time",
    model: { ...SENTIMENT_MODEL },
  },
  {
    item_id: "mock-item-003",
    article_id: "mock-art-0008",
    url: "https://example-exchange.example.ng/mock-art-0008",
    task: "ner",
    text: "Example Cement Plc declared a final dividend of ₦2.50 per share, subject to shareholder approval.",
    gold: "ORG:Example Cement Plc, MONEY:₦2.50",
    predicted: "TICKER:Example Cement Plc, MONEY:₦2.50",
    error_category: "boundary",
    split: "test_source",
    model: { ...NER_MODEL },
  },
  {
    item_id: "mock-item-004",
    article_id: "mock-art-0006",
    url: "https://example-energy.example.ng/mock-art-0006",
    task: "events",
    text: "Output from a major Example Delta field fell after an unplanned outage, the operator said.",
    gold: "oil_energy",
    predicted: "none",
    error_category: "false negative",
    split: "test_time",
    model: { ...EVENT_MODEL },
  },
  {
    item_id: "mock-item-005",
    article_id: "mock-art-0001",
    url: "https://example-businessdaily.example.ng/mock-art-0001",
    task: "events",
    text: "Example Bank Plc said it had completed a ₦120 billion rights issue, according to a filing.",
    gold: "capital_raise",
    predicted: "capital_raise, earnings",
    error_category: "false positive",
    split: "test_random",
    model: { ...EVENT_MODEL },
  },
  {
    item_id: "mock-item-006",
    article_id: "mock-art-0007",
    url: "https://example-businessdaily.example.ng/mock-art-0007",
    task: "entity_sentiment",
    text: "The Example Securities Commission fined an Example brokerage for reporting failures.",
    gold: "entity=Example Brokerage: negative",
    predicted: "entity=Example Securities Commission: negative",
    error_category: "wrong target",
    split: "test_source",
    model: { ...ENTITY_SENTIMENT_MODEL },
  },
];

// ---------------------------------------------------------------------------
// Narratives, watchlists, alerts
// ---------------------------------------------------------------------------

export const mockNarratives: NarrativeSummary[] = [
  {
    narrative_id: "mock-nar-0001",
    title: "[synthetic] Bank capitalisation race",
    description: "[synthetic] Coverage cluster around capital raises and higher thresholds.",
    started_at: ISO(21),
    last_activity_at: ISO(0),
    intensity: 0.72,
    intensity_change: 0.18,
    sentiment_shift: 0.09,
    dominant_sentiment: "positive",
    top_entity_ids: ["mock-ent-exbank"],
    article_count: 11,
    severity: "high",
  },
  {
    narrative_id: "mock-nar-0002",
    title: "[synthetic] Policy-rate pause debate",
    description: "[synthetic] Coverage cluster around whether the benchmark rate will move.",
    started_at: ISO(14),
    last_activity_at: ISO(1),
    intensity: 0.55,
    intensity_change: -0.07,
    sentiment_shift: -0.03,
    dominant_sentiment: "neutral",
    top_entity_ids: ["mock-ent-cbn"],
    article_count: 8,
    severity: "medium",
  },
  {
    narrative_id: "mock-nar-0003",
    title: "[synthetic] Exchange-rate window chatter",
    description: "[synthetic] Coverage cluster around the official FX window.",
    started_at: ISO(9),
    last_activity_at: ISO(2),
    intensity: 0.41,
    intensity_change: 0.22,
    sentiment_shift: -0.11,
    dominant_sentiment: "uncertain",
    top_entity_ids: ["mock-ent-naira"],
    article_count: 6,
    severity: "medium",
  },
  {
    narrative_id: "mock-nar-0004",
    title: "[synthetic] Gas supply reliability",
    description: "[synthetic] Coverage cluster around outage and supply language.",
    started_at: ISO(6),
    last_activity_at: ISO(3),
    intensity: 0.28,
    intensity_change: 0.05,
    sentiment_shift: -0.04,
    dominant_sentiment: "negative",
    top_entity_ids: ["mock-ent-delta"],
    article_count: 3,
    severity: "low",
  },
];

export const mockWatchlists: Watchlist[] = [
  {
    watchlist_id: "mock-wl-0001",
    name: "[synthetic] Banks & capital",
    description: "[synthetic] Fixture watchlist.",
    entity_ids: ["mock-ent-exbank"],
    keywords: ["rights issue", "capital adequacy"],
    event_types: ["capital_raise"],
    intensity_threshold: 0.6,
    sentiment_shift_threshold: 0.15,
    created_at: ISO(12),
    enabled: true,
  },
  {
    watchlist_id: "mock-wl-0002",
    name: "[synthetic] FX window",
    description: "[synthetic] Fixture watchlist.",
    entity_ids: ["mock-ent-naira"],
    keywords: ["naira", "official window"],
    event_types: ["fx_move"],
    intensity_threshold: 0.5,
    sentiment_shift_threshold: 0.1,
    created_at: ISO(6),
    enabled: true,
  },
];

export const mockAlerts: WatchlistAlert[] = [
  {
    alert_id: "mock-alert-0001",
    watchlist_id: "mock-wl-0001",
    watchlist_name: "[synthetic] Banks & capital",
    narrative_id: "mock-nar-0001",
    title: "[synthetic] Coverage intensity crossed the watchlist threshold",
    reason:
      "[synthetic] Observed intensity 0.72 over the last 24h, against the watchlist threshold of 0.60. Sentiment shift +0.09 is below the 0.15 threshold, so no sentiment alert fired.",
    triggered_at: ISO(0, 8, 0),
    observed_intensity: 0.72,
    threshold_used: 0.6,
    severity: "high",
    article_ids: ["mock-art-0001", "mock-art-0002"],
  },
  {
    alert_id: "mock-alert-0002",
    watchlist_id: "mock-wl-0002",
    watchlist_name: "[synthetic] FX window",
    narrative_id: "mock-nar-0003",
    title: "[synthetic] Sentiment shift crossed the watchlist threshold",
    reason:
      "[synthetic] Observed sentiment shift -0.11, against the watchlist threshold of 0.10 in absolute terms. Intensity 0.41 is below the 0.50 threshold.",
    triggered_at: ISO(2, 17, 30),
    observed_intensity: 0.41,
    threshold_used: 0.1,
    severity: "medium",
    article_ids: ["mock-art-0005", "mock-art-0012"],
  },
  {
    alert_id: "mock-alert-0003",
    watchlist_id: "mock-wl-0001",
    watchlist_name: "[synthetic] Banks & capital",
    narrative_id: "mock-nar-0001",
    title: "[synthetic] Intensity eased below the watchlist threshold",
    reason:
      "[synthetic] Observed intensity 0.44 against the watchlist threshold of 0.60; recorded for completeness rather than as an active alert.",
    triggered_at: ISO(7, 9, 0),
    observed_intensity: 0.44,
    threshold_used: 0.6,
    severity: "low",
    article_ids: ["mock-art-0011"],
  },
];

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export const mockHealth: HealthStatus = {
  status: "ok (mock)",
  version: "0.1.0+mock",
  database: "synthetic-fixtures",
  models_loaded: [
    "mock-sentiment-transformer@0.5.0-mock",
    "mock-ner-crf@0.3.1-mock",
    "mock-events-trigger@0.2.0-mock",
  ],
  corpus_size: 180,
  last_ingestion_at: ISO(0, 6, 0),
};

// ---------------------------------------------------------------------------
// Analyze (+ copilot)
// ---------------------------------------------------------------------------

export const MOCK_ANALYZE_SAMPLE = `The Central Bank of Nigeria said on Tuesday that it had approved a new capital framework for Example Bank Plc, according to a circular published on its website.

Under the framework the bank would need to hold additional capital of ₦85 billion by the end of the year. "The transition period reflects the current operating environment," the circular said, without specifying penalties for non-compliance.

Analysts at Example Capital wrote that the move was expected but that the timeline remained unclear.`;

export function mockAnalyzeResult(text: string): AnalysisResult {
  const safeText = text || MOCK_ANALYZE_SAMPLE;
  const spans: Array<{ needle: string; type: AnalysisResult["entities"][number]["span"]["entity_type"] }> = [
    { needle: "Central Bank of Nigeria", type: "REGULATOR" },
    { needle: "Example Bank Plc", type: "ORG" },
    { needle: "₦85 billion", type: "MONEY" },
    { needle: "Example Capital", type: "ORG" },
  ];

  const entities = spans
    .map(({ needle, type }) => {
      const start = safeText.indexOf(needle);
      if (start < 0) return null;
      return {
        span: { start, end: start + needle.length, text: needle, entity_type: type },
        entity_id: `mock-ent-inline-${type.toLowerCase()}`,
        canonical_name: needle,
        resolution_method: "alias",
        confidence: 0.82,
      };
    })
    .filter((value): value is NonNullable<typeof value> => value !== null);

  const firstSentence = safeText.split("\n\n")[0]?.slice(0, 80) ?? safeText.slice(0, 80);

  return {
    text_sha256: "mock-text-sha256",
    language: "en",
    status: "complete",
    sentiment: {
      label: "uncertain",
      confidence: 0.58,
      probabilities: { positive: 0.2, negative: 0.14, neutral: 0.08, uncertain: 0.58 },
      evidence: safeText.toLowerCase().includes("transition period")
        ? evidenceFor(safeText, '"The transition period reflects the current operating environment,"')
        : evidenceFor(safeText, firstSentence),
      model: { ...SENTIMENT_MODEL },
    },
    entities,
    entity_sentiments: entities.slice(0, 2).map((entity) => ({
      entity_id: entity.entity_id,
      canonical_name: entity.canonical_name,
      label: "uncertain" as const,
      confidence: 0.49,
      evidence: evidenceFor(safeText, firstSentence),
      model: { ...ENTITY_SENTIMENT_MODEL },
    })),
    events: [
      {
        event_type: "cbn_policy" as const,
        confidence: 0.66,
        event_date: null,
        entities: entities.slice(0, 2),
        evidence: evidenceFor(safeText, firstSentence),
        attributes: { "[synthetic]": true },
        model: { ...EVENT_MODEL },
      },
      {
        event_type: "capital_raise" as const,
        confidence: 0.54,
        event_date: null,
        entities: entities.slice(0, 2),
        evidence: safeText.toLowerCase().includes("capital")
          ? evidenceFor(safeText, "additional capital of ₦85 billion")
          : [],
        attributes: { "[synthetic]": true },
        model: { ...EVENT_MODEL },
      },
    ],
    limitations: MOCK_LIMITATIONS,
    processed_at: new Date().toISOString(),
    latency_ms: 42.7,
  };
}

export const mockCopilotAnswer = (question: string): CopilotAnswer => {
  const abstain = /weather|price target|should i buy|forecast/i.test(question);
  if (abstain) {
    return {
      answer:
        "I don't have enough evidence in the indexed coverage to answer that. [synthetic fixture]",
      citations: [],
      abstained: true,
      model: { name: "mock-copilot-rag", version: "0.1.0-mock", task: "copilot", calibrated: false },
      limitations: MOCK_LIMITATIONS,
      latency_ms: 12.4,
    };
  }
  return {
    answer:
      "[synthetic fixture — model-generated framing, not a source quote] Coverage in the fixture corpus discusses a capital framework with an unclear transition timeline. The wording is hedged, which is why the sentiment label in this fixture is uncertain rather than neutral. Evidence from the cited article is quoted below.",
    citations: [
      {
        article_id: "mock-art-0001",
        url: "https://example-businessdaily.example.ng/mock-art-0001",
        quote: "We expect the proceeds to lift our capital adequacy ratio above the regulatory minimum.",
        score: 0.81,
      },
      {
        article_id: "mock-art-0003",
        url: "https://example-businessdaily.example.ng/mock-art-0003",
        quote: "The committee does not expect a sustained pass-through in the near term.",
        score: 0.66,
      },
    ],
    abstained: false,
    model: { name: "mock-copilot-rag", version: "0.1.0-mock", task: "copilot", calibrated: false },
    limitations: MOCK_LIMITATIONS,
    latency_ms: 128.9,
  };
};
