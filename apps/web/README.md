# NaijaFinSent — Web Console

A React + TypeScript console for **measurements of language in published Nigerian
financial news coverage**.

> **Not investment advice.** These are measurements of language in published news
> coverage, not investor sentiment, and no causal or predictive claim is made.

This UI is deliberately built so a reviewer can never mistake model output for
market fact:

- The disclaimer banner is persistent on every route.
- Aggregates are labelled **"news coverage measurements"**, never "investor sentiment".
- Every prediction view shows the **source text**, the **evidence span**
  (highlighted), the **model name + version**, and the model's **limitations**.
- There is **no attention visualisation** anywhere. Growth in model attention is
  not evidence of influence; we show evidence spans and state plainly that they
  are *supporting text, not causal attribution*.
- **Reported facts** (quoted / attributed to a source) and **model
  interpretation** are visually and textually distinct.

---

## Stack

| Concern        | Choice                                  |
| -------------- | --------------------------------------- |
| Build          | Vite 5                                  |
| UI             | React 18                                |
| Types          | TypeScript 5 (strict, `noUncheckedIndexedAccess`) |
| Styling        | Tailwind CSS 3                          |
| Data           | TanStack Query v5                       |
| Routing        | React Router v6                         |
| Charts         | Recharts                                |
| Helpers        | local `cx` / `cn` (tailwind-merge-equivalent, no extra deps) |

## Getting started

```bash
npm install
cp .env.example .env          # then edit values
npm run dev                   # http://localhost:5173
```

The API is expected at `VITE_API_BASE_URL` (default `http://localhost:8000`).

### Reviewing with the backend offline

Set `VITE_USE_MOCKS=true` in `.env` and restart the dev server. Every query then
resolves from `src/mocks/fixtures.ts`, which is **clearly synthetic** — fixture
publishers, URLs under `example.ng`, and ids prefixed `mock-`. A prominent
"Synthetic fixtures" badge appears in the header and footer so mock data can
never be confused with real corpus output.

```bash
VITE_USE_MOCKS=true npm run dev
```

## Scripts

| Script              | What it does                          |
| ------------------- | ------------------------------------- |
| `npm run dev`       | Vite dev server with HMR              |
| `npm run build`     | `tsc -b` then production bundle       |
| `npm run preview`   | Serve the built bundle locally        |
| `npm run typecheck` | Type-check only                       |

## Route map

| Path | Feature | Notes |
| ---- | ------- | ----- |
| `/` | Overview | recent news, event counts, coverage-sentiment trend, freshness, health |
| `/news` | News explorer | publisher / date / entity / event / sentiment / free-text filters |
| `/news/:articleId` | Article detail | evidence spans highlighted, duplicate & syndication relations, source link |
| `/sentiment` | Coverage sentiment | trends, per-publisher breakdown, explicit "not investor sentiment" |
| `/entities` | Entity directory | aliases, ambiguity counts |
| `/entities/:entityId` | Entity page | aliases table, mentions, related events, coverage-sentiment trend |
| `/events` | Event explorer | filter by type / date / entity |
| `/events/:eventId` | Event detail | three dates, cluster timeline, new vs repeated, what's-new diff |
| `/narratives` | Narratives (Release 2) | coverage intensity, sentiment shift, watchlists + alerts |
| `/research` | Model Lab | version compare, metrics with CIs, per-slice charts, error browser |
| `/research/leaderboard` | Leaderboard | ranked runs |
| `/research/evaluation` | Evaluation summary | dataset + split summary |
| `/copilot` | Copilot | answer with inline numbered citations, abstention, quote framing |
| `/playground` | Analyze playground | paste text → entities, sentiment, events, evidence, limitations |
| `*` | Not found | |

## Environment variables

See `.env.example`. Only `VITE_*` variables are exposed to the bundle.

## Docker

```bash
docker build -t naijafinsent-web .
docker run --rm -p 8080:80 naijafinsent-web
```

`nginx.conf` serves the SPA with a history fallback and proxies `/api/` to an
`api:8000` upstream when running under docker-compose.

## Accessibility

- Semantic landmarks (`header`, `nav`, `main`, `footer`), one `h1` per page.
- Tables are real `<table>`s with `<caption>` and scoped headers; the sortable
  header is a real `<button>`, so the grid is keyboard navigable.
- Filter controls are labelled `<select>`/`<input>` elements, not divs.
- Icon-only buttons carry `aria-label`; decorative icons are `aria-hidden`.
- Visible focus rings everywhere (`focus-visible:ring-*`).
- `prefers-reduced-motion: reduce` disables the (already subtle) transitions.

## Data contract

`src/lib/schemas.ts` hand-mirrors `naijafinsent/schemas.py` field-for-field,
including enum spellings (`cbn_policy`, `regulatory_sanction`, `EVENT_TRIGGER`,
…). If the Pydantic models change, change the TS types in the same commit.
