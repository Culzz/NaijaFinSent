"""Token-classification NER via HuggingFace ``transformers``.

Fine-tunes an encoder (DistilBERT / DeBERTa-v3 / AfroXLM-R) for token
classification on BIO tags, preserving label alignment across subwords. At
inference we request ``return_offsets_mapping=True`` so decoded subword spans map
back to *exact* character offsets in the original text -- this is what makes the
produced ``EntitySpan`` objects consistent with the gold annotations.

All heavy imports are lazy; importing this module needs only base deps.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Sequence

from naijafinsent.schemas import EntityPrediction, EntitySpan, EntityType
from naijafinsent.ner.base import BIO, ENTITY_TYPES, BaseNerModel
from naijafinsent.ner.bio import spans_to_bio_subwords

__all__ = ["TransformerNer", "PRESETS", "MISSING_ML_MSG"]

MISSING_ML_MSG = (
    "TransformerNer requires the optional 'ml' dependencies (torch + "
    "transformers). Install with: pip install 'naijafinsent[ml]'. They are "
    "imported lazily so the base package stays light."
)

PRESETS: dict[str, str] = {
    "distilbert": "distilbert-base-uncased",
    "deberta-v3": "microsoft/deberta-v3-base",
    "afroxlmr": "Davlan/afro-xlmr-base",
    "xlmr": "xlm-roberta-base",
    "bert": "bert-base-uncased",
}


def _require_transformers():
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as exc:  # pragma: no cover - env dependent
        raise ImportError(MISSING_ML_MSG) from exc
    import torch
    import transformers

    return torch, transformers


class TransformerNer(BaseNerModel):
    """Fine-tunable token-classification NER."""

    name = "transformer-ner"
    version = "0.1.0"
    calibrated = False

    def __init__(
        self,
        *,
        model_name: str = "distilbert-base-uncased",
        max_length: int = 256,
        seed: int = 42,
        device: str | None = None,
        label_all_subwords: bool = True,
    ) -> None:
        self.model_name = PRESETS.get(model_name, model_name)
        self.max_length = max_length
        self.seed = seed
        self.device = device
        self.label_all_subwords = label_all_subwords
        self.entity_types = ENTITY_TYPES
        self._tags = BIO.all_tags()
        self._tag2id = {t: i for i, t in enumerate(self._tags)}
        self._id2tag = {i: t for t, i in self._tag2id.items()}
        self._model = None
        self._tokenizer = None

    # -- internals ------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        _torch, transformers = _require_transformers()
        self._tokenizer = transformers.AutoTokenizer.from_pretrained(self.model_name)
        self._model = transformers.AutoModelForTokenClassification.from_pretrained(
            self.model_name,
            num_labels=len(self._tags),
            id2label=self._id2tag,
            label2id=self._tag2id,
            ignore_mismatched_sizes=True,
        )
        if self.device:
            self._model.to(self.device)
        self._model.eval()

    def _set_seed(self) -> None:
        torch, _ = _require_transformers()
        random.seed(self.seed)
        torch.manual_seed(self.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(self.seed)

    def _encode_example(self, text: str, spans: list[EntitySpan]) -> dict:
        """Tokenize with offsets and produce aligned label ids."""
        enc = self._tokenizer(
            text,
            truncation=True,
            max_length=self.max_length,
            return_offsets_mapping=True,
        )
        offsets = enc["offset_mapping"]
        special_mask = [
            (s == 0 and e == 0) for (s, e) in offsets
        ]
        tags = spans_to_bio_subwords(offsets, spans, special_mask=special_mask)
        enc["labels"] = [self._tag2id[t] for t in tags]
        return enc

    # -- training -------------------------------------------------------
    def fit(
        self,
        texts: Sequence[str],
        spans: Sequence[list[EntitySpan]],
        *,
        epochs: int = 3,
        batch_size: int = 16,
        lr: float = 3e-5,
        weight_decay: float = 0.01,
        output_dir: str | Path | None = None,
        **kwargs,
    ) -> TransformerNer:
        torch, transformers = _require_transformers()
        self._set_seed()
        self._ensure_loaded()

        encoded = [self._encode_example(t, s) for t, s in zip(texts, spans)]

        class _Dataset(torch.utils.data.Dataset):
            def __init__(self, items):
                self.items = items

            def __len__(self):
                return len(self.items)

            def __getitem__(self, i):
                item = dict(self.items[i])
                item.pop("offset_mapping", None)
                return {
                    k: torch.tensor(v) if isinstance(v, list) else v
                    for k, v in item.items()
                }

        ds = _Dataset(encoded)
        data_collator = transformers.DataCollatorForTokenClassification(self._tokenizer)
        args = transformers.TrainingArguments(
            output_dir=str(output_dir or "data/models/_hf_ner_tmp"),
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            learning_rate=lr,
            weight_decay=weight_decay,
            seed=self.seed,
            save_strategy="no",
            logging_steps=max(1, len(ds) // max(1, batch_size)),
            report_to=[],
        )
        trainer = transformers.Trainer(
            model=self._model,
            args=args,
            train_dataset=ds,
            data_collator=data_collator,
        )
        trainer.train()
        self._model = trainer.model
        self._model.eval()
        return self

    # -- inference ------------------------------------------------------
    def predict(self, text: str) -> list[EntityPrediction]:
        self._ensure_loaded()
        torch, _ = _require_transformers()
        enc = self._tokenizer(
            text,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
            return_offsets_mapping=True,
        )
        offsets = enc.pop("offset_mapping")[0].tolist()
        if self.device:
            enc = {k: v.to(self.device) for k, v in enc.items()}
        with torch.no_grad():
            logits = self._model(**enc).logits[0]
        probs = torch.softmax(logits, dim=-1).cpu().numpy()
        pred_ids = probs.argmax(axis=-1)
        tags = [self._id2tag[int(i)] for i in pred_ids]
        confs = probs.max(axis=-1)

        # Decode subword BIO -> char spans.
        spans: list[EntityPrediction] = []
        cur_type: str | None = None
        cur_start: int | None = None
        cur_end: int | None = None
        cur_conf: list[float] = []

        def flush() -> None:
            nonlocal cur_type, cur_start, cur_end, cur_conf
            if cur_type is not None and cur_start is not None and cur_end is not None:
                spans.append(
                    EntityPrediction(
                        span=EntitySpan(
                            start=cur_start,
                            end=cur_end,
                            text=text[cur_start:cur_end],
                            entity_type=EntityType(cur_type),
                        ),
                        confidence=float(sum(cur_conf) / max(1, len(cur_conf))),
                        resolution_method=None,
                    )
                )
            cur_type, cur_start, cur_end, cur_conf = None, None, None, []

        for i, tag in enumerate(tags):
            ts, te = offsets[i]
            if ts == te:  # special token
                continue
            prefix, et = BIO.parse(tag)
            if prefix == "B" and et is not None:
                flush()
                cur_type, cur_start, cur_end, cur_conf = et, ts, te, [float(confs[i])]
            elif prefix == "I" and et is not None and cur_type == et:
                cur_end = te
                cur_conf.append(float(confs[i]))
            elif prefix == "I" and et is not None and cur_type is None:
                # Stray I: open a span defensively.
                cur_type, cur_start, cur_end, cur_conf = et, ts, te, [float(confs[i])]
            else:
                flush()
        flush()
        return spans

    # -- persistence ----------------------------------------------------
    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        config = {
            "model_name": self.model_name,
            "max_length": self.max_length,
            "seed": self.seed,
            "entity_types": list(self.entity_types),
            "tags": self._tags,
        }
        (path / "naijafinsent_ner_config.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8"
        )
        if self._model is not None and self._tokenizer is not None:
            self._model.save_pretrained(path)
            self._tokenizer.save_pretrained(path)

    @classmethod
    def load(cls, path: str | Path) -> TransformerNer:
        path = Path(path)
        cfg_path = path / "naijafinsent_ner_config.json"
        config = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        model = cls(
            model_name=config.get("model_name", str(path)),
            max_length=config.get("max_length", 256),
            seed=config.get("seed", 42),
        )
        if (path / "config.json").exists():
            model._ensure_loaded()
        return model
