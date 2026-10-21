"""Transformer-based sentiment classifiers (DistilBERT / DeBERTa-v3 / FinBERT /
AfroXLM-R).

Everything heavy (``torch``, ``transformers``, ``datasets``) is imported *inside*
methods, so importing this module with only the base dependencies installed is
cheap and side-effect free. Training and inference raise a clear, actionable
error when the optional ``ml`` extra is missing.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Sequence

from naijafinsent.schemas import EvidenceSpan
from naijafinsent.sentiment.base import LABELS, BaseSentimentModel

__all__ = ["TransformerSentimentModel", "PRESETS", "MISSING_ML_MSG"]

MISSING_ML_MSG = (
    "TransformerSentimentModel requires the optional 'ml' dependencies. "
    "Install with: pip install 'naijafinsent[ml]' (this pulls torch + transformers). "
    "Then re-import; torch/transformers are imported lazily and are not needed "
    "by the base package."
)

#: Convenient named checkpoints. All are encoder classifiers available on the
#: HuggingFace Hub; nothing is downloaded until you actually build the model.
PRESETS: dict[str, str] = {
    "distilbert": "distilbert-base-uncased",
    "deberta-v3": "microsoft/deberta-v3-base",
    "finbert": "ProsusAI/finbert",
    "afroxlmr": "Davlan/afro-xlmr-base",
    "xlmr": "xlm-roberta-base",
    "roberta": "roberta-base",
}


def _require_transformers():
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on env
        raise ImportError(MISSING_ML_MSG) from exc
    import torch
    import transformers

    return torch, transformers


class TransformerSentimentModel(BaseSentimentModel):
    """Fine-tunable transformer classifier with a HF ``Trainer`` backend.

    Usage::

        model = TransformerSentimentModel(model_name="distilbert-base-uncased")
        model.fit(texts, labels, epochs=3, class_weight=True)
        pred = model.predict("MTN Nigeria profit rises 12%")
    """

    name = "transformer-sentiment"
    version = "0.1.0"

    def __init__(
        self,
        *,
        model_name: str = "distilbert-base-uncased",
        num_labels: int | None = None,
        max_length: int = 256,
        seed: int = 42,
        calibrated: bool = False,
        temperature: float | None = None,
        device: str | None = None,
    ) -> None:
        # Resolve a preset name to its hub id.
        self.model_name = PRESETS.get(model_name, model_name)
        self.num_labels = num_labels or len(LABELS)
        self.max_length = max_length
        self.seed = seed
        # Honest default: a freshly fine-tuned model is NOT calibrated unless a
        # temperature is fitted on held-out data and applied.
        self.calibrated = calibrated
        self.temperature = temperature
        self.device = device
        self.labels = LABELS
        self._model = None
        self._tokenizer = None
        self._label2id: dict[str, int] = {lab: i for i, lab in enumerate(self.labels)}
        self._id2label: dict[int, str] = {i: lab for lab, i in self._label2id.items()}

    # -- internals ------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        torch, transformers = _require_transformers()
        self._tokenizer = transformers.AutoTokenizer.from_pretrained(self.model_name)
        self._model = transformers.AutoModelForSequenceClassification.from_pretrained(
            self.model_name,
            num_labels=len(self.labels),
            id2label=self._id2label,
            label2id=self._label2id,
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

    # -- training -------------------------------------------------------
    def fit(
        self,
        texts: Sequence[str],
        labels: Sequence[str],
        *,
        val_texts: Sequence[str] | None = None,
        val_labels: Sequence[str] | None = None,
        epochs: int = 3,
        batch_size: int = 16,
        lr: float = 2e-5,
        weight_decay: float = 0.01,
        class_weight: bool = True,
        warmup_ratio: float = 0.06,
        output_dir: str | Path | None = None,
        **kwargs,
    ) -> TransformerSentimentModel:
        """Fine-tune with HuggingFace ``Trainer``.

        ``class_weight=True`` computes inverse-frequency class weights and passes
        a weighted cross-entropy loss (implemented by subclassing ``Trainer`` so
        we do not silently ignore imbalance). Seeding is applied for
        reproducibility; note full determinism also depends on the CUDA backend.
        """
        torch, transformers = _require_transformers()
        self._set_seed()
        self._ensure_loaded()

        texts = list(texts)
        labels = list(labels)
        if not texts:
            raise ValueError("fit() requires at least one training example")
        unknown = set(labels) - set(self.labels)
        if unknown:
            raise ValueError(f"labels not in {self.labels}: {sorted(unknown)}")

        tokenizer = self._tokenizer

        def encode(batch_texts):
            return tokenizer(
                list(batch_texts),
                truncation=True,
                padding="max_length",
                max_length=self.max_length,
                return_tensors="pt",
            )

        train_enc = encode(texts)
        train_y = torch.tensor([self._label2id[l] for l in labels], dtype=torch.long)

        # --- weighted loss --------------------------------------------
        class_weights = None
        if class_weight:
            counts = torch.zeros(len(self.labels), dtype=torch.float)
            for l in labels:
                counts[self._label2id[l]] += 1
            counts = torch.clamp(counts, min=1.0)
            class_weights = counts.sum() / (counts * len(self.labels))

        class _Dataset(torch.utils.data.Dataset):
            def __init__(self, enc, ys):
                self.enc = enc
                self.ys = ys

            def __len__(self):
                return len(self.ys)

            def __getitem__(self, i):
                item = {k: v[i] for k, v in self.enc.items()}
                item["labels"] = self.ys[i]
                return item

        train_ds = _Dataset(train_enc, train_y)
        eval_ds = None
        if val_texts:
            val_enc = encode(val_texts)
            val_y = torch.tensor([self._label2id[l] for l in val_labels or []], dtype=torch.long)
            eval_ds = _Dataset(val_enc, val_y)

        trainer_cls = transformers.Trainer
        if class_weights is not None:

            class _WeightedTrainer(transformers.Trainer):
                def compute_loss(self, model, inputs, return_outputs=False, **kw):
                    lbl = inputs.pop("labels")
                    outputs = model(**inputs)
                    loss_fn = torch.nn.CrossEntropyLoss(weight=class_weights.to(outputs.logits.device))
                    loss = loss_fn(outputs.logits, lbl)
                    return (loss, outputs) if return_outputs else loss

            trainer_cls = _WeightedTrainer

        args = transformers.TrainingArguments(
            output_dir=str(output_dir or "data/models/_hf_tmp"),
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            per_device_eval_batch_size=batch_size,
            learning_rate=lr,
            weight_decay=weight_decay,
            warmup_ratio=warmup_ratio,
            seed=self.seed,
            logging_steps=max(1, len(train_ds) // max(1, batch_size)),
            save_strategy="no",
            report_to=[],
            **{k: v for k, v in kwargs.items() if k in _TRAINING_ARG_KEYS},
        )
        trainer = trainer_cls(
            model=self._model,
            args=args,
            train_dataset=train_ds,
            eval_dataset=eval_ds,
        )
        trainer.train()
        self._model = trainer.model
        self._model.eval()
        return self

    # -- inference ------------------------------------------------------
    def predict_proba(self, text: str) -> dict[str, float]:
        self._ensure_loaded()
        torch, _ = _require_transformers()
        enc = self._tokenizer(
            text,
            truncation=True,
            padding=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        if self.device:
            enc = {k: v.to(self.device) for k, v in enc.items()}
        with torch.no_grad():
            logits = self._model(**enc).logits[0]
        temp = self.temperature or 1.0
        probs = torch.softmax(logits / temp, dim=-1).cpu().numpy()
        return {lab: float(probs[i]) for i, lab in enumerate(self.labels)}

    def explain(self, text: str, label: str, k: int = 1) -> list[EvidenceSpan]:
        """Sentence-level evidence.

        Honest limitation: this model has no built-in attribution here, so we
        return the highest-salience sentence(s) by a cheap heuristic (sentence
        length as a proxy for information content), not a gradient attribution.
        Use a dedicated explainer (e.g. integrated gradients) if you need
        faithful attribution.
        """
        from naijafinsent.preprocessing.text import split_sentences

        sents = split_sentences(text)
        if not sents:
            return self._fallback_evidence(text)
        ranked = sorted(sents, key=len, reverse=True)[:k]
        spans: list[EvidenceSpan] = []
        cursor = 0
        for s in ranked:
            idx = text.find(s, cursor)
            if idx < 0:
                idx = text.find(s)
            spans.append(EvidenceSpan(text=s, start=idx, end=idx + len(s)))
            cursor = idx + len(s)
        return spans

    # -- persistence ----------------------------------------------------
    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        config = {
            "model_name": self.model_name,
            "num_labels": self.num_labels,
            "max_length": self.max_length,
            "seed": self.seed,
            "calibrated": self.calibrated,
            "temperature": self.temperature,
            "labels": list(self.labels),
        }
        (path / "naijafinsent_sentiment_config.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8"
        )
        if self._model is not None and self._tokenizer is not None:
            self._model.save_pretrained(path)
            self._tokenizer.save_pretrained(path)

    @classmethod
    def load(cls, path: str | Path) -> TransformerSentimentModel:
        path = Path(path)
        cfg_path = path / "naijafinsent_sentiment_config.json"
        config = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        model = cls(
            model_name=config.get("model_name", str(path)),
            num_labels=config.get("num_labels"),
            max_length=config.get("max_length", 256),
            seed=config.get("seed", 42),
            calibrated=config.get("calibrated", False),
            temperature=config.get("temperature"),
        )
        if (path / "config.json").exists():
            model._ensure_loaded()
        return model


#: Whitelist of TrainingArguments kwargs we accept from callers.
_TRAINING_ARG_KEYS: frozenset[str] = frozenset(
    {
        "gradient_accumulation_steps",
        "fp16",
        "bf16",
        "lr_scheduler_type",
        "eval_strategy",
        "evaluation_strategy",
        "save_total_limit",
        "dataloader_num_workers",
    }
)
