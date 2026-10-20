# Stage 0 — Source audit

> **Status: DRAFT AUDIT — NOT YET VERIFIED AGAINST LIVE robots.txt / ToS.**
>
> This document describes the *audit process* and the *policy we adopt*. It is a
> record of our intent, not a legal opinion, and **not** a set of facts about any
> publisher's current robots.txt. Every entry marked **UNVERIFIED** must be
> re-checked against the live `robots.txt`, the site's Terms of Service, and (where
> relevant) an API/RSS licence before any crawl is enabled. We deliberately do **not**
> assert specific robots.txt directives here, because they change and quoting them
> from memory would be fabrication.
>
> **Do not enable a source in the crawler until `robots_checked_at` is set by a human
> who has actually looked at the live policy.**

## 0. Publishing policy (the one rule that matters)

This project is a **research and benchmarking** effort. It is not a content
aggregator and must never become one.

1. **We publish labels, article URLs, and rebuild scripts — never full article text.**
   The open artefacts we ship (NaijaFin-Bench splits, annotation exports, docs) carry
   an `article_id`, the source `url`, and the derived labels/spans. They do **not**
   carry the publisher's article body.
2. **Exception:** text is only redistributed for sources that are explicitly
   public-domain or official government/regulator releases (e.g. CBN, SEC Nigeria,
   NGX disclosures), where reuse of the published text is permitted. Even then we
   prefer to link, and we record the reuse basis in `license_note`.
3. **The corpus store is internal.** `Article.content` lives in the local corpus
   database (SQLite / JSONL) for processing only. It is never served by the public
   API and never committed to git (`data/` runtime artefacts are gitignored).
4. **No bypassing of controls.** We honour `robots.txt`, we identify honestly in the
   `User-Agent` (`NaijaFinSent-ResearchBot`), we rate-limit per host, and we stop if a
   publisher signals that they do not want crawling.
5. **Attribution and takedown.** Every derived record preserves the source URL and
   publisher. We will remove a source on request, and the manifest `enabled` flag is
   the single switch for doing so.

## 1. How to re-verify (the actual audit procedure)

For each source, a human completes the following and records the date in the
manifest's `robots_checked_at`:

1. Fetch `<base_url>/robots.txt` and read the rules for `User-agent: *`.
   Record: is our path class allowed? What is `Crawl-delay` (if any)?
2. Read the Terms of Service / legal page. Record whether bulk or automated access is
   prohibited, and whether an RSS feed or API is offered as the sanctioned route.
3. Prefer, in order: (a) an official API, (b) an official RSS/Atom feed, (c) an
   official sitemap, (d) plain HTML of article pages, subject to (1) and (2).
4. Record the resulting `license_note` — specifically: *may we store the text
   internally for processing? may we redistribute the text? must we link only?*
5. Set `enabled: true` only when steps 1–4 are satisfied; otherwise leave `false`.

## 2. Sources under audit

Trust tiers are from `naijafinsent.constants.TRUST_TIERS`:
`official` > `tier1` > `tier2` > `tier3` > `unknown`.

### 2.1 BusinessDay — `businessday`

| Field | Value |
|---|---|
| Base URL | `https://businessday.ng` |
| Access method (intended) | RSS feed, HTML fallback |
| Trust tier | `tier1` |
| Reuse rights | **UNVERIFIED.** Commercial news publisher. Assume all rights reserved until verified. |
| Storage policy | Store `content` internally for processing only; **publish URL + labels only**. |

**Audit notes:** A general feed is published (commonly at `/feed/`) plus section
feeds. Confirm the feed path and whether the feed licence differs from the site ToS.
BusinessDay is a commercial outlet with syndication partners, so text must be treated
as all-rights-reserved. Link-only redistribution for any derived benchmark.

### 2.2 Nairametrics — `nairametrics`

| Field | Value |
|---|---|
| Base URL | `https://nairametrics.com` |
| Access method (intended) | RSS feed, sitemap, HTML fallback |
| Trust tier | `tier1` |
| Reuse rights | **UNVERIFIED.** Commercial publisher; assume all rights reserved. |
| Storage policy | Store `content` internally; **publish URL + labels only**. |

**Audit notes:** Publishes market/finance coverage with heavy CBN and NGX content —
high value for our event taxonomy (`cbn_policy`, `fx_move`, `earnings`). Confirm feed
URL(s) and any stated `Crawl-delay`. Treat as all-rights-reserved.

### 2.3 Punch — `punch`

| Field | Value |
|---|---|
| Base URL | `https://punchng.com` |
| Access method (intended) | RSS feed, HTML fallback |
| Trust tier | `tier1` |
| Reuse rights | **UNVERIFIED.** Commercial newspaper; assume all rights reserved. |
| Storage policy | Store `content` internally; **publish URL + labels only**. |

**Audit notes:** Long-standing national newspaper; business desk covers banking and
energy. Confirm the business section feed path. Treat as all-rights-reserved. Note
that Punch historically syndicates from agencies (Reuters/AP) on some items — the
dedup layer's `syndicated_from` is directly relevant here.

### 2.4 Premium Times — `premium_times`

| Field | Value |
|---|---|
| Base URL | `https://www.premiumtimesng.com` |
| Access method (intended) | RSS feed, HTML fallback |
| Trust tier | `tier1` |
| Reuse rights | **UNVERIFIED.** Commercial publisher; assume all rights reserved. |
| Storage policy | Store `content` internally; **publish URL + labels only**. |

**Audit notes:** Known for investigations and policy reporting. Confirm feed path.
Treat as all-rights-reserved. Apply link-only redistribution.

### 2.5 Central Bank of Nigeria — `cbn`

| Field | Value |
|---|---|
| Base URL | `https://www.cbn.gov.ng` |
| Access method (intended) | HTML / sitemap (press releases, circulars, MPC communiqués) |
| Trust tier | `official` |
| Reuse rights | **UNVERIFIED but likely permissive.** Government/regulator material is generally published for public use, but we must confirm the site's stated terms before redistributing text. |
| Storage policy | Store `content` internally; text redistribution *may* be permissible — **publish `is_official_release` + URL + labels**, and only include text if the site's terms allow. |

**Audit notes:** Primary source for `cbn_policy` (MPR decisions, FX windows,
circulars) and the MPC communiqué series. These are the highest-precision labels in
the corpus. Verify whether there is a stable press-release index path rather than
scraping the homepage. Even where reuse is allowed, prefer linking.

### 2.6 Nigerian Exchange Group — `ngx`

| Field | Value |
|---|---|
| Base URL | `https://ngxgroup.com` (issuer disclosures also via the NGX portal) |
| Access method (intended) | HTML / sitemap (issuer disclosures, market notices) |
| Trust tier | `official` |
| Reuse rights | **UNVERIFIED.** Exchange-published market notices are public; confirm terms and any redistribution limits (issuer filings are issued by the issuers). |
| Storage policy | Store `content` internally; **publish URL + labels**; redistribute text only if terms allow. |

**Audit notes:** Source for `earnings`, `dividend`, `mna`, `capital_raise` via filings
and market notices. Note that some content is issuer-authored, so "official" here
means *exchange-published*, not necessarily *free to redistribute*. Verify terms.
May require a separate portal/API path — flag if the disclosure portal is JS-driven.

### 2.7 Securities and Exchange Commission, Nigeria — `sec_ng`

| Field | Value |
|---|---|
| Base URL | `https://sec.gov.ng` |
| Access method (intended) | HTML / sitemap (circulars, rules, enforcement notices) |
| Trust tier | `official` |
| Reuse rights | **UNVERIFIED but likely permissive.** Regulator publications are generally public; confirm the stated terms. |
| Storage policy | Store `content` internally; **publish URL + labels**; redistribute text only if terms allow. |

**Audit notes:** Source for `regulatory_sanction` and capital-market rules. Verify the
index of circulars/enforcement actions. Prefer linking.

## 3. Summary table

| source_id | name | tier | access (intended) | redistribute text? |
|---|---|---|---|---|
| `businessday` | BusinessDay | tier1 | rss | No (link only) |
| `nairametrics` | Nairametrics | tier1 | rss | No (link only) |
| `punch` | Punch | tier1 | rss | No (link only) |
| `premium_times` | Premium Times | tier1 | rss | No (link only) |
| `cbn` | Central Bank of Nigeria | official | html | Only if ToS permits; else link |
| `ngx` | Nigerian Exchange Group | official | html | Only if ToS permits; else link |
| `sec_ng` | SEC Nigeria | official | html | Only if ToS permits; else link |

## 4. What is NOT claimed here

- We do **not** claim to know any publisher's current robots.txt rules.
- We do **not** claim that any source is safe to crawl today.
- We do **not** claim that "official" implies free redistribution of third-party
  (issuer-authored) filings.
- `license_note` in `data/manifests/sources.json` is written to match the
  **conservative** policy in §0: internal storage for processing permitted in
  principle; redistribution of text **not** permitted unless explicitly verified.

## 5. Enforcement in code

- `naijafinsent.data.sources.load_manifests` loads `data/manifests/sources.json`.
- `naijafinsent.data.ingest.Ingestor` refuses to crawl a source whose
  `robots_checked_at is None` (i.e. audit unverified) **unless** the caller passes
  `allow_unverified=True`, and refuses any source with `enabled: false`.
- `naijafinsent.data.store.CorpusStore` is internal-only and never exposed by the API.
