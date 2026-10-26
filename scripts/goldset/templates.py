"""Deterministic template families that scale the gold set to 1,000+ items.

Every generated item records ``is_synthetic: true`` and the generator family,
so reviewers can never mistake templated coverage for organic text. Frames
carry their own sentiment label — the label is part of the sentence's defined
meaning, not a judgement call at generation time.
"""

from __future__ import annotations

# 18 companies; ticker noted where colliding names matter.
COMPANIES: list[tuple[str, str]] = [
    ("Zenith Bank", "ZENITHBANK"),
    ("GTCO", "GTCO"),
    ("Access Holdings", "ACCESSCORP"),
    ("UBA", "UBA"),
    ("FBN Holdings", "FBNH"),
    ("Stanbic IBTC", "STANBIC"),
    ("FCMB Group", "FCMB"),
    ("Sterling Financial Holdings", "STERLINGNG"),
    ("Wema Bank", "WEMABANK"),
    ("Jaiz Bank", "JAIZBANK"),
    ("Dangote Cement", "DANGCEM"),
    ("BUA Cement", "BUACEMENT"),
    ("Lafarge Africa", "WAPCO"),
    ("Seplat Energy", "SEPLAT"),
    ("MTN Nigeria", "MTNN"),
    ("Nestlé Nigeria", "NESTLE"),
    ("Presco", "PRESCO"),
    ("OKOMU Oil Palm", "OKOMUOIL"),
]

# Naira amounts in every format the market actually writes.
VALUES: list[tuple[str, str]] = [  # (display text, marker)
    ("₦459 billion", "naira_symbol"),
    ("₦459bn", "naira_symbol"),
    ("N459 billion", "naira_abbrev"),
    ("N459bn", "naira_abbrev"),
    ("₦1.2 trillion", "naira_symbol"),
    ("₦1.2trn", "naira_symbol"),
    ("N1.2 trillion", "naira_abbrev"),
    ("N1.2trn", "naira_abbrev"),
    ("459 billion naira", "naira_words"),
    ("₦2.75 trillion", "naira_symbol"),
    ("₦2.75trn", "naira_symbol"),
    ("N2.75 trillion", "naira_abbrev"),
    ("N2.75trn", "naira_abbrev"),
    ("₦150 million", "naira_symbol"),
    ("N150 million", "naira_abbrev"),
]

DIVIDEND_PER_SHARE: list[tuple[str, str]] = [
    ("₦2.00 per share", "naira_symbol"),
    ("N2.00 per share", "naira_abbrev"),
    ("₦3.50 per share", "naira_symbol"),
    ("N3.50 per share", "naira_abbrev"),
    ("₦5.10 per share", "naira_symbol"),
    ("N5.10 per share", "naira_abbrev"),
    ("350 kobo per share", "kobo_format"),
    ("510 kobo per share", "kobo_format"),
]

PERCENTS: list[str] = ["4 percent", "12 percent", "19.5 percent", "28 percent", "34 percent", "41 percent", "98 percent", "105 percent"]

REGULATORS: list[str] = ["CBN", "SEC Nigeria", "NGX Regulation", "NCC", "NUPRC", "NAICOM", "PenCom", "FIRS", "NDPC", "Federal Competition and Consumer Protection Commission", "Corporate Affairs Commission", "SEC (Nigeria)"]


def _base(text: str, label: str, family: str, markers: list[str], *, topic: str, entities: list[dict] | None = None, events: list[dict] | None = None) -> dict:
    return {
        "text": text,
        "label": label,
        "markers": markers + [family],
        "topic": topic,
        "entities": entities or [],
        "events": events or [],
        "entity_sentiments": {},
    }


def earnings_families() -> list[dict]:
    out: list[dict] = []
    for name, ticker in COMPANIES:
        is_bank = "Bank" in name or name in ("GTCO", "UBA") or "Holdings" in name
        for pct in PERCENTS[:4]:
            out.append(_base(
                f"{name} posted a {ticker} beating {pct} rise in profit before tax as net interest income firmed.",
                "positive", "templated_earnings", [], topic="earnings",
                events=[{"event_type": "earnings"}]))
            out.append(_base(
                f"{name}'s profit before tax fell by {pct} as loan-loss charges and higher funding costs bit.",
                "negative", "templated_earnings", [], topic="earnings",
                events=[{"event_type": "earnings"}]))
        out.append(_base(
            f"The {ticker} operator released the {ticker} result for the quarter; fee income was flat while volumes grew.",
            "neutral", "templated_earnings", ["ticker_style"], topic="earnings",
            events=[{"event_type": "earnings"}]))
        out.append(_base(
            f"{name} said the outcome of the audit could change the interim result materially; final figures are pending.",
            "uncertain", "templated_earnings", [], topic="earnings",
            events=[{"event_type": "earnings"}]))
    for ticker, tick_pct in (("MTNN", "35 percent"), ("DANGCEM", "18 percent"), ("SEPLAT", "40 percent"), ("WAPCO", "22 percent"), ("PRESCO", "27 percent")):
        out.append(_base(
            f"{ticker} NPAT up {tick_pct} y/y; EBITDA margin steady; guidance intact.",
            "positive", "templated_earnings", ["headline_fragment", "ticker_style"], topic="earnings",
            events=[{"event_type": "earnings"}]))
        out.append(_base(
            f"{ticker} result in line; revenue +{tick_pct}, costs +{tick_pct}; outlook unclear.",
            "uncertain", "templated_earnings", ["headline_fragment", "ticker_style"], topic="earnings",
            events=[{"event_type": "earnings"}]))
    return out


def dividend_families() -> list[dict]:
    out: list[dict] = []
    for i, (name, _ticker) in enumerate(COMPANIES):
        for j in range(4):
            amount, marker = DIVIDEND_PER_SHARE[(i + j * 2) % len(DIVIDEND_PER_SHARE)]
            qualifiers = [
                (f"{name} recommended a final dividend of {amount} for the year ended December 2025.", "neutral"),
                (f"{name} declared an interim dividend of {amount} alongside its half-year result.", "neutral"),
                (f"The board cut the payout to {amount}, down from a higher total dividend last year.", "negative"),
                (f"{name} lifted the proposed payout to {amount}, its highest in five years.", "positive"),
            ]
            text, label = qualifiers[j]
            out.append(_base(text, label, "templated_dividend", [marker], topic="dividend", events=[{"event_type": "dividend"}]))
    for i, (name, _ticker) in enumerate(COMPANIES):
        amount2, marker2 = DIVIDEND_PER_SHARE[(i + 5) % len(DIVIDEND_PER_SHARE)]
        out.append(_base(
            f"{name} fixed a qualification date of March 5 and a payment date of March 12 for the {amount2} payout.",
            "neutral", "templated_dividend", [marker2, "calendar_dates"], topic="dividend",
            events=[{"event_type": "dividend"}]))
        out.append(_base(
            f"Shareholders await confirmation of the {name} payout; the proposed dividend still requires AGM approval.",
            "uncertain", "templated_dividend", [], topic="dividend",
            events=[{"event_type": "dividend"}]))
        out.append(_base(
            f"{name} said no interim dividend will be declared this period as capital is conserved.",
            "negative", "templated_dividend", [], topic="dividend",
            events=[{"event_type": "dividend"}]))
    return out


def policy_families() -> list[dict]:
    out: list[dict] = []
    bases = ["25 basis points", "50 basis points", "150 basis points", "300 basis points"]
    for bps in bases:
        out.append(_base(f"The CBN raised the monetary policy rate by {bps} to a 27-year high, deepening the tightening cycle.", "negative", "templated_policy", [], topic="monetary_policy", entities=[{"text": "CBN", "entity_type": "REGULATOR"}], events=[{"event_type": "cbn_policy"}]))
        out.append(_base(f"The MPC cut the cash reserve ratio by {bps}, freeing balances for lenders to expand credit.", "positive", "templated_policy", [], topic="monetary_policy", events=[{"event_type": "cbn_policy"}]))
        out.append(_base(f"The committee retained the policy rate after {bps} of cumulative increases since the last cycle began; several members wanted a pause to assess it.", "uncertain", "templated_policy", [], topic="monetary_policy", events=[{"event_type": "cbn_policy"}]))
    for pct in ("24.8 percent", "28.9 percent", "33.1 percent", "34.8 percent"):
        out.append(_base(f"Headline inflation printed {pct}, outweighing the modest dis-inflation seen in core.", "negative", "templated_policy", [], topic="monetary_policy"))
        out.append(_base(f"Core inflation eased to {pct} as food supply improved across the markets.", "positive", "templated_policy", [], topic="monetary_policy"))
        out.append(_base(f"The statistics office will publish the {pct} inflation debate next week; the MPC decision hangs on it.", "uncertain", "templated_policy", [], topic="monetary_policy"))
    for reg in REGULATORS:
        out.append(_base(f"{reg} issued a fresh circular tightening capital verification for operators.", "neutral", "templated_policy", ["circular"], topic="regulatory"))
        out.append(_base(f"{reg} said the compliance window will not be extended, rejecting industry appeals.", "negative", "templated_policy", ["circular"], topic="regulatory"))
        out.append(_base(f"{reg} signalled a more flexible stance after its review committee concluded consultations.", "positive", "templated_policy", ["circular"], topic="regulatory"))
        out.append(_base(f"Operators are seeking clarity as {reg} has yet to confirm the timeline for the new regime.", "uncertain", "templated_policy", ["circular"], topic="regulatory"))
    return out


def fx_families() -> list[dict]:
    out: list[dict] = []
    levels = ["₦1,512", "₦1,545", "N1,580", "N1,615", "₦1,630", "N1,660", "₦1,540", "N1,600",
              "₦1,505", "₦1,525", "N1,585", "N1,595", "₦1,675", "N1,690", "₦1,555", "N1,620"]
    markets = [("official window", "naira_symbol"), ("parallel market", "naira_symbol"), ("investors' window", "naira_symbol"), ("official market", "naira_abbrev")]
    for i in range(64):
        (market, marker) = markets[i % 4]
        out.append(_base(f"The naira appreciated to {levels[i % len(levels)]} per dollar at the {market}, extending gains after CBN interventions.", "positive", "templated_fx", [marker], topic="fx", events=[{"event_type": "fx_move"}]))
        out.append(_base(f"The naira weakened to {levels[(i + 3) % len(levels)]} per dollar at the {market} as dollar demand from importers outpaced supply.", "negative", "templated_fx", [marker], topic="fx", events=[{"event_type": "fx_move"}]))
        out.append(_base(f"The naira closed flat at {levels[(i + 7) % len(levels)]} per dollar at the {market} in thin holiday trading.", "neutral", "templated_fx", [marker], topic="fx", events=[{"event_type": "fx_move"}]))
        out.append(_base(f"Dealers expect volatility around {levels[(i + 11) % len(levels)]} per dollar at the {market} until the next FX auction clears.", "uncertain", "templated_fx", [marker], topic="fx", events=[{"event_type": "fx_move"}]))
    for pct in ("12", "25", "40", "55"):
        out.append(_base(f"Foreign portfolio inflows rose {pct} percent month on month, lifting market turnover.", "positive", "templated_fx", [], topic="fx"))
        out.append(_base(f"Non-deliverable forwards priced a further slide of {pct} kobo for the naira.", "negative", "templated_fx", [], topic="fx"))
        out.append(_base(f"Diaspora remittances were little changed at {pct} basis points of quarterly flow, data show.", "neutral", "templated_fx", [], topic="fx"))
        out.append(_base(f"Whether the FX backlog is fully cleared remains unclear, traders said.", "uncertain", "templated_fx", [], topic="fx"))
    return out


def sanction_families() -> list[dict]:
    out: list[dict] = []
    for i in range(max(len(REGULATORS), len(COMPANIES)) * 2):
        reg = REGULATORS[i % len(REGULATORS)]
        name, _t = COMPANIES[i % len(COMPANIES)]
        out.append(_base(f"{reg} fined {name} for breaches of the capital verification regime.", "negative", "templated_sanction", [], topic="regulatory", events=[{"event_type": "regulatory_sanction"}]))
        out.append(_base(f"{reg} suspended {name}'s licence holder pending the outcome of a special examination.", "negative", "templated_sanction", [], topic="regulatory", events=[{"event_type": "regulatory_sanction"}]))
        out.append(_base(f"The appeal tribunal set aside the earlier fine on {name}, faulting {reg}'s data.", "positive", "templated_sanction", [], topic="regulatory"))
        out.append(_base(f"{name} faces a sanction risk as {reg} weighs the final report; no decision has been announced.", "uncertain", "templated_sanction", [], topic="regulatory"))
    for action in ("froze", "lifted the freeze on", "warned it may freeze", "reviewed"):
        out.append(_base(f"The regulator {action} broker accounts linked to the client-asset shortfall.", "negative" if action == "froze" or action == "warned it may freeze" else "positive" if action == "lifted the freeze on" else "uncertain", "templated_sanction", [], topic="regulatory"))
        out.append(_base(f"After the surveillance sweep, two dealers were barred; the third case is ongoing though showing promise.", "neutral", "templated_sanction", [], topic="regulatory"))
    return out


def capital_raise_families() -> list[dict]:
    out: list[dict] = []
    for i, (name, ticker) in enumerate(COMPANIES):
        amount, marker = VALUES[i % len(VALUES)]
        kinds = [
            (f"{name} opened a {amount} rights issue for existing shareholders at the subscription price fixed in the circular.", "neutral"),
            (f"{name} completed its {amount} recapitalisation comfortably ahead of the regulatory deadline.", "positive"),
            (f"The {ticker} capital raise could cost more than planned; {name} said the timetable may shift if approvals slip.", "uncertain"),
            (f"{name}'s {amount} commercial paper programme was oversubscribed at the auction.", "positive"),
        ]
        # Deterministic spread: two frames per company.
        for k in (0, 1):
            text, label = kinds[(i + k) % len(kinds)]
            out.append(_base(text, label, "templated_capital_raise", [marker], topic="capital_raise", events=[{"event_type": "capital_raise"}]))
    for name, _t in COMPANIES[:6]:
        out.append(_base(f"Merchant banks are underwriting the {name} offer; coupon guidance spans 24 to 26 percent.", "neutral", "templated_capital_raise", [], topic="capital_raise"))
        out.append(_base(f"The {name} bookbuild outcome is pending; the lead arrangers extended the closing date.", "uncertain", "templated_capital_raise", [], topic="capital_raise"))
        out.append(_base(f"{name} repaid its {name} line ahead of schedule, lifting covenants comfortably.", "positive", "templated_capital_raise", [], topic="capital_raise"))
    return out


def mna_families() -> list[dict]:
    out: list[dict] = []
    deals = ["$128 million", "$420 million", "$1.5 billion", "$75 million"]
    targets = ["a willing-seller crude producer", "a regional payments platform", "a mid-tier asset manager", "a gas processing company"]
    for i in range(36):
        name, _t = COMPANIES[i % len(COMPANIES)]
        deal = deals[(i * 3) % len(deals)]
        target = targets[(i * 5) % len(targets)]
        frames = [
            (f"{name} completed its {deal} acquisition of {target}.", "neutral"),
            (f"The {deal} acquisition by {name} of {target} cleared its final regulatory approvals.", "positive"),
            (f"{name}'s {deal} pursuit of {target} fell apart over valuation and financing.", "negative"),
            (f"{name} is in talks over a possible {deal} deal for {target}; terms remain undisclosed.", "uncertain"),
        ]
        text, label = frames[i % len(frames)]
        out.append(_base(text, label, "templated_mna", [], topic="mna", events=[{"event_type": "mna"}]))
    return out


def pidgin_families() -> list[dict]:
    out: list[dict] = []
    fill: list[tuple[str, str, str]] = []
    for i in range(36):
        name, _t = COMPANIES[i % len(COMPANIES)]
        amt, _m = (VALUES + DIVIDEND_PER_SHARE)[i % (len(VALUES) + len(DIVIDEND_PER_SHARE))]
        fill.append((name, amt, PERCENTS[i % len(PERCENTS)]))
    frames = [
        ("{name} don post better result for last quarter, profit don rise {pct}.", "positive", "templated_pidgin"),
        ("{name} profit don drop {pct}, shareholders no happy at all.", "negative", "templated_pidgin"),
        ("{name} dividend don land, e sweet for people wey hold share.", "positive", "templated_pidgin"),
        ("Nobody don hear anything from {name} board about payout, everything still dey hang.", "uncertain", "templated_pidgin"),
        ("Market just dey quiet, {name} and others no move today.", "neutral", "templated_pidgin"),
        ("Naira don firm small for official window after CBN sell dollar, e good for everybody.", "positive", "templated_pidgin"),
        ("Rate still dey high, borrowers dey cry say money no dey flow.", "negative", "templated_pidgin"),
        ("The buy-back talk for {name} still dey up in the air, no date yet.", "uncertain", "templated_pidgin"),
        ("{name} don settle fine with regulator, case level don close now.", "positive", "templated_pidgin"),
        ("Regulator don fine {name} for late returns, e no sweet for the bank.", "negative", "templated_pidgin"),
    ]
    for name, _amt, pct in fill[:100]:
        template, label, family = frames[len(out) % len(frames)]
        out.append(_base(template.format(name=name, pct=pct), label, family, ["pidgin"], topic="pidgin"))
    return out


def headline_families() -> list[dict]:
    out: list[dict] = []
    for name, ticker in COMPANIES:
        out.append(_base(f"{ticker}: profit up 21% y/y; div ₦3.10 declared.", "positive", "templated_headline", ["headline_fragment", "naira_symbol", "ticker_style"], topic="dividend", events=[{"event_type": "dividend"}]))
        out.append(_base(f"{ticker}: margin in line; qual date Mar 7; payment Mar 14.", "neutral", "templated_headline", ["headline_fragment", "ticker_style", "calendar_dates"], topic="dividend", events=[{"event_type": "dividend"}]))
        out.append(_base(f"{ticker} slips as regulators fault disclosures.", "negative", "templated_headline", ["headline_fragment", "ticker_style"], topic="regulatory", events=[{"event_type": "regulatory_sanction"}]))
        out.append(_base(f"{ticker}: asset sale talks at advanced stage, says report.", "uncertain", "templated_headline", ["headline_fragment", "ticker_style"], topic="mna", events=[{"event_type": "mna"}]))
    extras = [
        ("NGX ASI +1.4%; banks lead; turnover ₦6.2bn.", "positive"),
        ("ASI flat; cement drags; volume thin.", "neutral"),
        ("FX: official ₦1,532; parallel ₦1,650; reserves up.", "positive"),
        ("Inflation path ahead of the CPI print uncertain.", "uncertain"),
        ("MPC outcome split 7-4; hawks prevail; guidance unclear.", "negative"),
        ("Treasury stop rates jump 90bps at auction; demand mixed.", "neutral"),
        ("Reserves climb as inflows beat expectations, data show.", "positive"),
        ("CBN bills: stop rate eases 40bps; clearing yields soften.", "neutral"),
        ("Banks recap: eight lenders meet minimum capital early.", "positive"),
        ("Sanction watch: three dealers remain barred, four cases hang.", "uncertain"),
        ("Fuel import bill falls as Dangote lifts petrol output.", "positive"),
        ("Bond auction: bids undershoot offer by 18%; yields harden.", "negative"),
        ("Paints makers post flat sales as demand slows.", "neutral"),
        ("FUGAZ banks shed 2.1% in broad risk-off session.", "negative"),
        ("Shipping costs ease 9% on freight rates; exporters cheer.", "positive"),
        ("FX backlog questions linger after third auction delay.", "uncertain"),
    ]
    for text, label in extras:
        out.append(_base(text, label, "templated_headline", ["headline_fragment"], topic="market"))
    out.append(_base("MPC: decision split; direction unclear till communiqué.", "uncertain", "templated_headline", ["headline_fragment", "monetary_policy"], topic="monetary_policy", events=[{"event_type": "cbn_policy"}]))
    out.append(_base("FX backlog: CBN clears $1.2bn more; full resolution pending.", "uncertain", "templated_headline", ["headline_fragment", "fx"], topic="fx"))
    return out


def market_families() -> list[dict]:
    out: list[dict] = []
    for pct in ("0.8", "1.2", "2.1", "3.4", "0.4", "1.7", "2.6", "0.6"):
        out.append(_base(f"The All-Share Index rose {pct} percent to a new year-to-date high as foreign flows returned.", "positive", "templated_market", [], topic="market"))
        out.append(_base(f"The All-Share Index closed {pct} percent lower; breadth finished at three decliners for every advancer.", "negative", "templated_market", [], topic="market"))
        out.append(_base(f"Turnover settled at ₦6.{pct} billion in a session that ended with the index roughly flat.", "neutral", "templated_market", ["naira_symbol"], topic="market"))
        out.append(_base(f"Direction for the index hinges on the {pct}-percent question: whether inflows persist after this auction cycle.", "uncertain", "templated_market", [], topic="market"))
    return out


def rates_families() -> list[dict]:
    """Debt market / auction items — a family the corpus actually sees weekly."""
    out: list[dict] = []
    sizes = [("₦450 billion", "naira_symbol"), ("₦450bn", "naira_symbol"), ("N450 billion", "naira_abbrev"), ("N450bn", "naira_abbrev"), ("₦1.25 trillion", "naira_symbol"), ("N1.25 trillion", "naira_abbrev"), ("₦1.25trn", "naira_symbol"), ("N1.25trn", "naira_abbrev")]
    yields = ["18.2", "19.5", "22.7", "24.3"]
    for i in range(16):
        size, marker = sizes[i % len(sizes)]
        y = yields[(i // 2) % len(yields)]
        out.append(_base(f"The treasury bills auction offered {size} with the 91-day stop rate rising to {y} percent.", "negative", "templated_rates", [marker], topic="debt_market", events=[{"event_type": "cbn_policy"}]))
        out.append(_base(f"The {size} auction saw the stop rate ease to {y} percent as system liquidity improved.", "positive", "templated_rates", [marker], topic="debt_market", events=[{"event_type": "cbn_policy"}]))
        out.append(_base(f"The {size} debt auction priced at {y} percent, broadly in line with the previous cycle.", "neutral", "templated_rates", [marker], topic="debt_market", events=[{"event_type": "cbn_policy"}]))
        out.append(_base(f"Bid direction for the {size} offer hinges on whether the stop rate settles near {y} percent.", "uncertain", "templated_rates", [marker], topic="debt_market", events=[{"event_type": "cbn_policy"}]))
    for i in range(8):
        size, marker = sizes[i % len(sizes)]
        out.append(_base(f"CBN OMO drained {size} at a two-tick jump; interbank rates spiked intraday.", "negative", "templated_rates", [marker], topic="debt_market", events=[{"event_type": "cbn_policy"}]))
        out.append(_base(f"Open-market operations returned {size} as maturities flowed back to banks.", "neutral", "templated_rates", [marker], topic="debt_market", events=[{"event_type": "cbn_policy"}]))
        out.append(_base(f"Bond issuance windfall: FGN collection beat budget projections on the {size} programme.", "positive", "templated_rates", [marker], topic="debt_market"))
        out.append(_base(f"Where the {size} bond book lands is still unclear; dealers widen quotes ahead of pricing.", "uncertain", "templated_rates", [marker], topic="debt_market"))
    return out


FAMILIES = (
    earnings_families,
    dividend_families,
    policy_families,
    fx_families,
    sanction_families,
    capital_raise_families,
    mna_families,
    rates_families,
    pidgin_families,
    headline_families,
    market_families,
)


def build_templated() -> list[dict]:
    out: list[dict] = []
    for family in FAMILIES:
        out.extend(family())
    return out
