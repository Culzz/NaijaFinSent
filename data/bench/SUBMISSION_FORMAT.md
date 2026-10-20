# NaijaFin-Bench submission format

Submit one JSONL file per task. Each line is an object keyed by `item_id`.

## Sentiment (`sentiment.jsonl`)
```json
{"item_id": "nfs-000123", "label": "negative", "confidence": 0.81}
```
`label` must be one of: positive, negative, neutral, uncertain.

## NER (`ner.jsonl`)
```json
{"item_id": "nfs-000123", "entities": [{"start": 4, "end": 7, "text": "CBN", "entity_type": "REGULATOR"}]}
```
`entity_type` must be one of: ORG, PER, REGULATOR, MONEY, TICKER, CURRENCY, SECTOR, EVENT_TRIGGER.
Offsets are character offsets into the benchmark text (inclusive start, exclusive end).

## Events (`events.jsonl`)
```json
{"item_id": "nfs-000123", "events": [{"event_type": "cbn_policy", "event_date": "2026-02-19", "evidence_start": 0, "evidence_end": 62}]}
```
`event_type` must be one of: cbn_policy, earnings, dividend, mna, regulatory_sanction,
capital_raise, fx_move, oil_energy.

## Rules
* One prediction per `item_id`; extra or missing ids are scored as errors.
* Never train on items whose `split` is `test*`.
* Report seeds and variance. A single-seed number without variance is not accepted
  onto the leaderboard.
* Submissions must include a model card and a reproducibility statement.
* This benchmark measures language in news coverage. It is **not investment advice**.
