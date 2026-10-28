# Legal & monetisation pack

> **Status: UNVERIFIED throughout.** Nothing in this file is a legal opinion and
> nothing here has been checked by a Nigerian-qualified lawyer or against the
> live text of any platform's terms. Items marked **[VERIFY]** are open
> external checks that must be completed (by a human, with receipts — dates
> and screenshots in the repo) before the related feature or spend is enabled.
> The engineering rule stands regardless of the words below:
> **labels/links/URLs out, no publisher article text out** (see `SOURCES.md`
> §0), and **no investment advice / no causal claims** in every UI surface and
> every API response (`LIMITATIONS.md`).

## 1. Per-source ToS / redistribution verdicts — all UNVERIFIED

The audit *procedure* lives in `SOURCES.md` §1 (robots.txt → ToS → sanctioned
route → license_note). Verdicts recorded there are honest *placeholders* until
a human sets `robots_checked_at`. Summary of the current stance, none of which
is verified:

| Source class | Access route (preferred order) | Store text internally? | Redistribute text? | Status |
|---|---|---|---|---|
| CBN, SEC Nigeria, NGX disclosures, NCC/other regulators | official releases / APIs | Yes (official releases, reuse basis recorded in `license_note`) | Yes, with basis noted | **UNVERIFIED** per exact page |
| BusinessDay, Nairametrics, Punch, Premium-subscription dailies | RSS/Atom feeds or sitemaps, per robots + ToS | Internal processing only if ToS allows; **never redistributed** | **No** — link + labels only | **UNVERIFIED** |
| Aggregators/newsletters that republish others' content | Avoid — provenance unclear | No | No | **UNVERIFIED** |
| Social commentary / forums (X posts, Nairaland) | Platform APIs with their own ToS | Per platform terms | No | **UNVERIFIED** |

**[VERIFY] list (ASCII receipt trail required before enabling a crawler):**
1. Live `robots.txt` for each enabled host, with fetch date and the rule line
   for `User-agent: *` / our UA.
2. The ToS/legal page URL, date checked, and one sentence: bulk/automated
   access permitted? RSS/API offered as sanctioned route?
3. `license_note` filled for every source: store? redistribute? link-only?
4. Rate limits + honest User-Agent recorded in the crawler config (already
   enforced in code: `NaijaFinSent-ResearchBot`, per-host limits).

## 2. Nigeria Data Protection Act (NDPA 2023) notes — engineering stance

Not advice; the engineering impact of the Act as publicly understood **[VERIFY
with counsel before personal-data processing or paid subscribers]**:

- **We do not need personal data to do the core job.** The pipeline processes
  *published financial text*. Article ingestion stores publisher + URL +
  content — no reader personal data. Keep it that way: no reader accounts
  without a lawful basis, no third-party analytics with personal data, no
  contact-scraping.
- If/when B2B users have accounts (name, work email, card details), that is
  personal data → privacy notice, lawful basis (contract), data-subject
  request (DSR) path, breach-notification runbook, and a register of
  processing. `services/api` stores minimal account fields by design; billing
  identifiers should stay at the PSP (Paystack/Flutterwave) so card data never
  touches this codebase. **[VERIFY] PSP-hosted checkout keeps us out of PCI
  scope in practice.**
- Web/Telegram briefings: `email` and `chat_id` are personal data → consented
  opt-in, export + delete buttons, suppression list. The briefing module ships
  with an explicit consent field wired end-to-end before any live send.
- NDPC is the regulator; registration obligations depend on scale/kind of
  processing — **[VERIFY]** registration duty, DPIA duty for profiling at
  scale.

## 3. SEC-Nigeria framing rules (how we may talk about the product)

The product **classifies the tone of published coverage** and surfaces
calendar data. Public framing rules so marketing never walks into securities-
advice territory — **[VERIFY] exact SEC-Nigeria investment-adviser scope and
whether our earning/monetisation triggers registration thresholds:**

1. **Never** publish "buy/sell/hold" language derived from sentiment labels.
   Labels are **coverage tone**, labelled that way in every surface
   (`docs/EVALUATION.md` §"Sentiment target").
2. **Never** present percentages/confidence as predictive: no "stock will
   rise", no target prices, no implied faith in the numbers we extract.
3. Every output surface ships the standing disclaimer tuple (already in
   `pipeline.LIMITATIONS`): *not investment advice; text-only; no causal or
   predictive claim; confidence may be miscalibrated*.
4. The B2B API response schema carries the same disclaimers machine-readably
   (`limitations[]`), so customers cannot strip them without forking the
   contract.
5. Monetisation of *data feeds* (extracted structured events with source
   links) is factual-data provision; monetisation of *advice* is not the
   product. Any future feature that ranks/recommends instruments needs a
   separate legal **[VERIFY]** before build.

## 4. WhatsApp / Telegram / Email delivery — verification items

| Channel | Status | [VERIFY] items |
|---|---|---|
| Email (transactional provider e.g. Resend/SES/Brevo) | planned in briefings module; no live send in tests | SPF/DKIM/DMARC on the sending domain; unsubscribe (one-click headers); NDPA consent capture; monthly send-cap cost |
| Telegram Bot API | planned (free, simple) | bot token in secrets; chat opt-in registry; "stop" command honoured; ToS: automated bulk messages [VERIFY] |
| WhatsApp Business API / BSP | **later, gated** | BSP choice + per-message pricing class (utility vs marketing) [VERIFY]; Meta business verification [VERIFY]; template approval for digest template [VERIFY]; opt-in registry required by Meta policy [VERIFY]; budget gate: no activation below a confirmed cost/user/month |

Engineering guardrails already decided (no live sends from tests; senders are
config-gated `BRIEFING_ENABLED=false` by default; every send logs recipient +
template + result for audit).

## 5. Paystack / Flutterwave — payment coverage

| Item | Status | Notes |
|---|---|---|
| Chip: B2B subscriptions priced per tier (API key seats) | planned | PSP-hosted checkout + webhooks → entitlement switch in `services/api` |
| Card data | never stored by us | PSP-hosted fields only **[VERIFY] current PCI-DSS SAQ-A scope** |
| [VERIFY] | current Paystack/Flutterwave availability for our entity type; KYC documents; settlement timing; FX for USD pricing; webhook replay behaviour |  |
| Disputes/refunds | refund-first policy for outages | runbook item, not code |

## 6. Cost model template (fill per month, in ₦ and $)

| Line | Unit assumption | Qty/mo | Unit cost | Monthly | Notes / [VERIFY] |
|---|---|---|---|---|---|
| Crawl/bandwidth (respecting robots + delays) | requests × avg KB | 0 (not enabled) | band | — | enable only after §1 checks |
| Compute (API) | CPU-hrs / Dyno-hrs | | | | |
| Postgres | GB-mo | | | | |
| Email delivery | emails | | | | free tier first |
| Telegram | fixed | 0 | 0 | 0 | free API |
| WhatsApp (BSP) | msgs × class | 0 (gated) | | | economics decide go/no-go |
| PSP fees | % + fixed | | | | Paystack NGA card: [VERIFY] rates |
| Compliance (counsel, one-off review) | hours | | | | before paid tiers |

Decision rule for any paid channel: activation requires (a) §1–§5 [VERIFY]
items closed for that channel, (b) a filled row above, (c) measured unit
economics ≥ break-even at the projected tier sizes.
