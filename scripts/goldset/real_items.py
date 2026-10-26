"""Curated, hand-authored gold items (model-assisted labels — see gold README).

Each item is a dict with:

* ``text``            — the sentence / headline fragment
* ``label``           — one of the four sentiment labels
* ``markers``         — coverage markers (pidgin, naira variants, …)
* ``topic``           — coarse topical group
* ``entities``        — optional [{text, entity_type}] entity mentions
* ``events``          — optional [{event_type}] event mentions
* ``entity_sentiments`` — optional {entity: label} for entity-targeted items

Every label here was produced by an LLM-assisted pass (declared in each
record as ``annotator`` with ``model_prelabel: true``). No label here has
been confirmed by a second human annotator yet; the gold README documents
the review protocol. Treat the numbers as model-assisted measurement, not a
human gold standard.
"""

from __future__ import annotations


def item(text: str, label: str, markers: list[str], topic: str, *, entities: list[dict] | None = None, events: list[dict] | None = None, entity_sentiments: dict[str, str] | None = None) -> dict:
    return {
        "text": text,
        "label": label,
        "markers": markers,
        "topic": topic,
        "entities": entities or [],
        "events": events or [],
        "entity_sentiments": entity_sentiments or {},
    }


REAL_ITEMS: list[dict] = [
    # ------------------------------------------------------------- earnings
    item("Zenith Bank posted a 98 percent jump in half-year profit to ₦459 billion, riding higher interest income.", "positive", ["naira_symbol", "earnings", "body_style"], "earnings", entities=[{"text": "Zenith Bank", "entity_type": "ORG"}], events=[{"event_type": "earnings"}]),
    item("Access Holdings reported profit before tax of ₦142.1 billion for nine months, up 11.2 percent year on year.", "positive", ["naira_symbol", "earnings", "body_style"], "earnings", entities=[{"text": "Access Holdings", "entity_type": "ORG"}], events=[{"event_type": "earnings"}]),
    item("MTN Nigeria returned to profit after tax in the first half, its first since listing.", "positive", ["earnings", "body_style"], "earnings", entities=[{"text": "MTN Nigeria", "entity_type": "ORG"}], events=[{"event_type": "earnings"}]),
    item("Dangote Cement's revenue climbed to 1.6trn while pan-African volumes improved.", "positive", ["trn_bn_abbrev", "earnings", "body_style"], "earnings", entities=[{"text": "Dangote Cement", "entity_type": "ORG"}], events=[{"event_type": "earnings"}]),
    item("FBN Holdings delivered its best quarterly result since recapitalisation, with net interest margin steady at 6.1 percent.", "positive", ["earnings", "body_style"], "earnings", entities=[{"text": "FBN Holdings", "entity_type": "ORG"}], events=[{"event_type": "earnings"}]),
    item("GTCO's return on equity rose to 41.5 percent, keeping it among the most profitable Nigerian banks.", "positive", ["earnings", "body_style"], "earnings", entities=[{"text": "GTCO", "entity_type": "ORG"}], events=[{"event_type": "earnings"}]),
    item("Cost of funds jumped across tier-one lenders as treasury yields bit into margins.", "negative", ["earnings", "body_style"], "earnings"),
    item("Lenders' non-performing loan ratio inched up to 4.2 percent as the mid-tier segment deteriorated.", "negative", ["earnings", "body_style"], "earnings"),
    item("Seplat Energy lifted crude production to 68,000 barrels per day after completing the ANOH gas plant.", "positive", ["earnings", "energy", "body_style"], "energy", entities=[{"text": "Seplat Energy", "entity_type": "ORG"}], events=[{"event_type": "earnings"}]),
    item("Julius Berger won a ₦210 billion contract for the Lagos-Calabar coastal highway section.", "positive", ["naira_symbol", "body_style"], "industrials", entities=[{"text": "Julius Berger", "entity_type": "ORG"}]),
    item("BUA Cement announced a price reduction to ₦3,500 per bag, the third cut this year.", "negative", ["naira_symbol", "body_style"], "industrials", entities=[{"text": "BUA Cement", "entity_type": "ORG"}]),
    item("Nestlé Nigeria's operating margin compressed as input costs outpaced pricing actions.", "negative", ["earnings", "body_style"], "earnings", entities=[{"text": "Nestlé Nigeria", "entity_type": "ORG"}]),
    item("Transcorp Group reported profit in line with the prior-year period even as power revenue slowed.", "neutral", ["earnings", "body_style"], "earnings"),
    item("United Capital posted record fees as dealing operations doubled turnover.", "positive", ["earnings", "body_style"], "financials", entities=[{"text": "United Capital", "entity_type": "ORG"}]),
    item("Stanbic IBTC's pension and asset management income grew in step with rising AUM.", "positive", ["earnings", "body_style"], "financials", entities=[{"text": "Stanbic IBTC", "entity_type": "ORG"}]),
    item("The fintech's audited accounts showed revenue doubling while fraud losses tripled.", "negative", ["earnings", "body_style"], "financials"),
    item("Bank fee income rose 19 percent, driven by digital channels and card spend.", "positive", ["earnings", "body_style"], "financials"),
    # ------------------------------------------------------------------- fx
    item("The naira appreciated to ₦1,512 per dollar at the official window after CBN dollar sales.", "positive", ["naira_symbol", "fx", "body_style"], "fx", events=[{"event_type": "fx_move"}]),
    item("The naira depreciated further at the parallel market, closing at ₦1,630 per dollar.", "negative", ["naira_symbol", "fx", "body_style"], "fx", events=[{"event_type": "fx_move"}]),
    item("Foreign portfolio inflows rose 40 percent month on month as the FX market deepened.", "positive", ["fx", "body_style"], "fx"),
    item("N1.6 billion in invisibles slipped out of the official window last month.", "neutral", ["naira_abbrev", "fx", "body_style"], "fx"),
    item("Importers struggled to source dollars as the FX backlog grew to $2.2 billion.", "negative", ["fx", "body_style"], "fx"),
    item("The naira fell to a fresh low against the pound at the investors' window.", "negative", ["fx", "body_style"], "fx", events=[{"event_type": "fx_move"}]),
    item("Remittances held steady near $2 billion a month despite FX spread worries.", "neutral", ["fx", "body_style"], "fx"),
    # ---------------------------------------------------- monetary policy
    item("The MPC raised the monetary policy rate by 25 basis points to 27.75 percent.", "neutral", ["monetary_policy", "body_style"], "monetary_policy", entities=[{"text": "MPC", "entity_type": "REGULATOR"}], events=[{"event_type": "cbn_policy"}]),
    item("The CBN held the policy rate at 27.50 percent for the fourth consecutive meeting, leaving borrowers disappointed.", "negative", ["monetary_policy", "body_style"], "monetary_policy", entities=[{"text": "CBN", "entity_type": "REGULATOR"}], events=[{"event_type": "cbn_policy"}]),
    item("MPC members voted 9 to 3 to tighten as headline inflation quickened to 34.8 percent.", "negative", ["monetary_policy", "body_style"], "monetary_policy", events=[{"event_type": "cbn_policy"}]),
    item("The CBN cut the cash reserve ratio by 300 basis points, releasing liquidity to lenders.", "positive", ["monetary_policy", "body_style"], "monetary_policy", entities=[{"text": "CBN", "entity_type": "REGULATOR"}], events=[{"event_type": "cbn_policy"}]),
    item("Analysts are divided on whether the next MPC meeting brings a hold or another hike.", "uncertain", ["monetary_policy", "body_style"], "monetary_policy"),
    item("The central bank retained the asymmetric corridor at plus 50 basis points.", "neutral", ["monetary_policy", "body_style"], "monetary_policy", events=[{"event_type": "cbn_policy"}]),
    item("Policy rate at 27.50%; CRR 45%; corridor asymmetric +50bps.", "neutral", ["monetary_policy", "headline_fragment"], "monetary_policy", events=[{"event_type": "cbn_policy"}]),
    # ------------------------------------------------------------ dividends
    item("Zenith Bank declared a final dividend of N2.00 per share, payable to shareholders on the register by March 12.", "neutral", ["naira_abbrev", "dividend", "body_style"], "dividend", entities=[{"text": "Zenith Bank", "entity_type": "ORG"}], events=[{"event_type": "dividend"}]),
    item("GTCO recommended a final dividend of ₦3.50 for the year ended December 2025.", "neutral", ["naira_symbol", "dividend", "body_style"], "dividend", entities=[{"text": "GTCO", "entity_type": "ORG"}], events=[{"event_type": "dividend"}]),
    item("Presco proposes a special dividend of N46.00 per share from its 2025 net profit.", "neutral", ["naira_abbrev", "dividend", "body_style"], "dividend", entities=[{"text": "Presco", "entity_type": "ORG"}], events=[{"event_type": "dividend"}]),
    item("MTN Nigeria said no dividend will be paid as it rebuilds capital after losses.", "negative", ["dividend", "body_style"], "dividend", entities=[{"text": "MTN Nigeria", "entity_type": "ORG"}], events=[{"event_type": "dividend"}]),
    item("Shareholders will vote on the proposed dividend at the AGM; approval is not guaranteed.", "uncertain", ["dividend", "body_style"], "dividend", events=[{"event_type": "dividend"}]),
    item("The board advised shareholders to await further guidance on the payout before the AGM.", "uncertain", ["dividend", "body_style"], "dividend"),
    item("Final div ₦3.10; qualification date Mar 5; payment Mar 12.", "neutral", ["naira_symbol", "dividend", "headline_fragment"], "dividend", events=[{"event_type": "dividend"}]),
    item("Mutual Benefits declared an interim dividend of 5 kobo per share despite flat earnings.", "neutral", ["dividend", "body_style"], "dividend", events=[{"event_type": "dividend"}]),
    # ------------------------------------------------------- capital raise
    item("Zenith Bank launched a ₦290 billion rights issue of 5.4 billion ordinary shares at ₦36.00.", "neutral", ["naira_symbol", "capital_raise", "body_style"], "capital_raise", entities=[{"text": "Zenith Bank", "entity_type": "ORG"}], events=[{"event_type": "capital_raise"}]),
    item("Access Holdings completed its ₦351 billion capital raise, exceeding the regulator's minimum.", "positive", ["naira_symbol", "capital_raise", "body_style"], "capital_raise", entities=[{"text": "Access Holdings", "entity_type": "ORG"}], events=[{"event_type": "capital_raise"}]),
    item("Sterling Bank's ₦100 billion recapitalisation received overwhelming shareholder approval.", "positive", ["naira_symbol", "capital_raise", "body_style"], "capital_raise", entities=[{"text": "Sterling Bank", "entity_type": "ORG"}], events=[{"event_type": "capital_raise"}]),
    item("The bank's planned capital raise may be delayed to next quarter, the CFO said.", "uncertain", ["capital_raise", "body_style"], "capital_raise"),
    item("FCMB Group priced its commercial paper at yields near 24 percent amid tight liquidity.", "neutral", ["capital_raise", "body_style"], "capital_raise"),
    item("The wider consequences of the recapitalisation exercise remain unclear for mid-tier lenders.", "uncertain", ["capital_raise", "body_style"], "capital_raise"),
    # ----------------------------------------------------------------- mna
    item("Seplat acquired a 40 percent stake in a willing-seller field operator for $128 million.", "positive", ["mna", "energy", "body_style"], "energy", entities=[{"text": "Seplat", "entity_type": "ORG"}], events=[{"event_type": "mna"}]),
    item("Flutterwave's planned acquisition of a pan-African payments rival collapsed over valuation.", "negative", ["mna", "body_style"], "financials", entities=[{"text": "Flutterwave", "entity_type": "ORG"}], events=[{"event_type": "mna"}]),
    item("MTN is in talks that may lead to acquiring additional fibre assets, terms undisclosed.", "uncertain", ["mna", "body_style"], "telecoms"),
    item("Airtel Africa completed the sale of its tower portfolio to a regional operator.", "neutral", ["mna", "body_style"], "telecoms", entities=[{"text": "Airtel Africa", "entity_type": "ORG"}], events=[{"event_type": "mna"}]),
    # ----------------------------------------------------------- sanctions
    item("CBN fined the lender ₦50 million for late submission of prudential returns.", "negative", ["naira_symbol", "sanction", "body_style"], "regulatory", events=[{"event_type": "regulatory_sanction"}]),
    item("SEC suspended the stockbroker for unauthorised trading on client accounts.", "negative", ["sanction", "body_style"], "regulatory", events=[{"event_type": "regulatory_sanction"}]),
    item("NGX Regulation fined two dealers for market abuse, citing surveillance data.", "negative", ["sanction", "body_style"], "regulatory", events=[{"event_type": "regulatory_sanction"}]),
    item("The tribunal dismissed the case against the lender, clearing it of the alleged breaches.", "positive", ["sanction", "body_style"], "regulatory"),
    item("The NCC threatened sanctions against network operators over quality of service breaches.", "uncertain", ["sanction", "body_style"], "regulatory"),
    # ---------------------------------------------------------------- oil
    item("Oil production fell to 1.38 million barrels per day as shut-ins persisted at Forcados.", "negative", ["energy", "body_style"], "energy"),
    item("NUPRC awarded new deepwater blocks in the latest mini-bid round.", "neutral", ["energy", "body_style"], "energy"),
    item("Bonny Light rose to $88 per barrel on supply concerns.", "positive", ["energy", "body_style"], "energy"),
    item("Dangote refinery's crude supply deal with NNPC remains under negotiation.", "uncertain", ["energy", "body_style"], "energy", entities=[{"text": "NNPC", "entity_type": "ORG"}]),
    # -------------------------------------------------------------- market
    item("NGX All-Share Index added 1.2 percent led by banking names.", "positive", ["body_style"], "market"),
    item("The All-Share Index slipped 0.8 percent as profit-taking hit cement majors.", "negative", ["body_style"], "market"),
    item("Traded value fell to ₦4.1 billion in a muted session with volume spread thin.", "neutral", ["naira_symbol", "body_style"], "market"),
    item("Breadth favours sellers; bond desks report no clear direction ahead of the MPC.", "uncertain", ["body_style"], "market"),
    # --------------------------------------------------------------- pidgin
    item("Bank don declare dividend, shareholders dey happy well well.", "positive", ["pidgin"], "dividend", events=[{"event_type": "dividend"}]),
    item("Naira don fall again for parallel market, dollar cost ₦1,700 today.", "negative", ["pidgin", "naira_symbol", "fx"], "fx", events=[{"event_type": "fx_move"}]),
    item("CBN don hold rate again, nothing change for borrowers side.", "neutral", ["pidgin", "monetary_policy"], "monetary_policy", events=[{"event_type": "cbn_policy"}]),
    item("Oil price don go up, country money dey come small small.", "positive", ["pidgin", "energy"], "energy"),
    item("Investors still dey wait to know how the recap go end.", "uncertain", ["pidgin", "capital_raise"], "capital_raise"),
    item("Market no dey move today, everybody just dey look.", "neutral", ["pidgin"], "market"),
    item("The bank say profit don drop because loan no dey repay.", "negative", ["pidgin", "earnings"], "earnings"),
    item("FG don talk say fuel subsidy money dey go infrastructure now.", "positive", ["pidgin"], "policy"),
    # -------------------------------------------------------- headline style
    item("NPAT +34% y/y; final div ₦3.10; qual date Mar 5.", "neutral", ["headline_fragment", "naira_symbol", "dividend"], "dividend", events=[{"event_type": "dividend"}]),
    item("CBN keeps rate at 27.50% for 4th straight MPC.", "neutral", ["headline_fragment", "monetary_policy"], "monetary_policy", events=[{"event_type": "cbn_policy"}]),
    item("Naira slips to ₦1,615/$ at official window.", "negative", ["headline_fragment", "naira_symbol", "fx"], "fx", events=[{"event_type": "fx_move"}]),
    item("UBA, Zenith lead gainers as NGX index adds 1.2%.", "positive", ["headline_fragment"], "market"),
    item("FCMB rights issue oversubscribed — details pending.", "uncertain", ["headline_fragment", "capital_raise"], "capital_raise", events=[{"event_type": "capital_raise"}]),
    item("Forex reserves hit 40-month high as inflows return.", "positive", ["headline_fragment", "fx"], "fx"),
    item("SEC freezes broker accounts over client asset shortfalls.", "negative", ["headline_fragment", "sanction"], "regulatory", events=[{"event_type": "regulatory_sanction"}]),
    item("Cement price war widens as BUA trims ex-factory rate again.", "negative", ["headline_fragment"], "industrials"),
    item("Seplat nears $128m field acquisition — board approval said imminent.", "uncertain", ["headline_fragment", "mna"], "energy", events=[{"event_type": "mna"}]),
    item("NGX: turnover ₦4.1bn; 18 gainers, 24 losers.", "neutral", ["headline_fragment", "trn_bn_abbrev"], "market"),
    # ------------------------------------------------- entity-targeted pairs
    item("Zenith Bank's profit fell 12 percent even as GTCO posted record earnings.", "neutral", ["entity_paired", "earnings", "body_style"], "earnings", entities=[{"text": "Zenith Bank", "entity_type": "ORG"}, {"text": "GTCO", "entity_type": "ORG"}], events=[{"event_type": "earnings"}], entity_sentiments={"Zenith Bank": "negative", "GTCO": "positive"}),
    item("FBN Holdings' cost of risk worsened while Stanbic IBTC tightened pricing.", "neutral", ["entity_paired", "earnings", "body_style"], "earnings", entities=[{"text": "FBN Holdings", "entity_type": "ORG"}, {"text": "Stanbic IBTC", "entity_type": "ORG"}], entity_sentiments={"FBN Holdings": "negative", "Stanbic IBTC": "positive"}),
    item("MTN Group cut full-year guidance, though MTN Nigeria kept its own outlook unchanged.", "neutral", ["entity_paired", "ticker_collision", "body_style"], "telecoms", entities=[{"text": "MTN Group", "entity_type": "ORG"}, {"text": "MTN Nigeria", "entity_type": "ORG"}], entity_sentiments={"MTN Group": "negative", "MTN Nigeria": "neutral"}),
    item("Seplat shares rose after the operator declared an interim dividend and lifted output.", "positive", ["entity_paired", "dividend", "body_style"], "energy", entities=[{"text": "Seplat", "entity_type": "ORG"}], events=[{"event_type": "dividend"}], entity_sentiments={"Seplat": "positive"}),
    item("Unity Bank stayed positive on margins even as unity eluded the broader market.", "neutral", ["entity_paired", "ticker_collision", "body_style"], "financials", entities=[{"text": "Unity Bank", "entity_type": "ORG"}]),
    item("Access Holdings grew Access Corp fee income across the group.", "positive", ["ticker_collision", "body_style"], "financials", entities=[{"text": "Access Holdings", "entity_type": "ORG"}]),
    item("The Access Bank brand outperformed the Access sector index in the review window.", "neutral", ["ticker_collision", "body_style"], "financials", entities=[{"text": "Access Bank", "entity_type": "ORG"}]),
    # ------------------------------------------------------ naira variants
    item("The lender raised N1.2 billion in fresh CBN bills at the auction.", "neutral", ["naira_abbrev", "body_style"], "financials", events=[{"event_type": "capital_raise"}]),
    item("FGN sold 1.2trn of treasury bills in the quarter, absorbing system liquidity.", "neutral", ["trn_bn_abbrev", "monetary_policy", "body_style"], "monetary_policy", events=[{"event_type": "cbn_policy"}]),
    item("Subsidy savings hit N2.5 trillion year to date under the unbundling.", "positive", ["trn_bn_abbrev", "body_style"], "policy"),
    item("The standby facility is worth ₦120bn at the concessional window.", "neutral", ["naira_symbol", "trn_bn_abbrev", "body_style"], "financials"),
    item("Remittance inflows hit N6.7 trillion, the highest since the reset of the window.", "positive", ["trn_bn_abbrev", "fx", "body_style"], "fx"),
    item("Federal allocation to states topped N1.9 trillion as ARRA improved.", "neutral", ["trn_bn_abbrev", "body_style"], "policy"),
]
