"""Ingest + analysis worker.

Runs a loop (or one-shot): load the source manifest, fetch new article URLs,
extract text, dedup, run the analysis pipeline (deterministic stub by default),
and persist results into the corpus DB.

Usage
-----
    python -m app.worker --once          # single cycle (CI / cron)
    python -m app.worker --limit 20      # cap articles per cycle
    python -m app.worker --loop 900      # loop every 15 minutes

Run from ``services/api`` so ``app`` resolves. The worker never imports
FastAPI; it shares the package but runs as its own process.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("worker")


def run_cycle(*, limit: int, max_urls_per_source: int = 25) -> dict:
    """One ingest+analyze pass. Returns a summary (never raises)."""
    summary: dict = {"fetched": 0, "new": 0, "duplicates": 0, "analyzed": 0, "errors": 0}

    try:
        from naijafinsent.data.ingest import Ingestor
        from naijafinsent.data.sources import load_manifests
    except Exception as exc:  # noqa: BLE001
        logger.error("cannot import ingestor: %r", exc)
        summary["errors"] += 1
        return summary

    try:
        ingestor = Ingestor()
        for entry in load_manifests():
            if not entry.enabled:
                continue
            try:
                report = ingestor.ingest_source(entry.source_id, limit=limit)
                summary["fetched"] += report.fetched if hasattr(report, "fetched") else 0
                summary["new"] += report.created if hasattr(report, "created") else 0
                logger.info("source %s: %s", entry.source_id, report)
            except Exception as exc:  # noqa: BLE001 - per-source isolation
                logger.warning("source %s failed: %r", entry.source_id, exc)
                summary["errors"] += 1
    except Exception as exc:  # noqa: BLE001 - worker must survive bad sources
        logger.warning("ingest cycle failed: %r", exc)
        summary["errors"] += 1
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NaijaFinSent ingest+analyze worker")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument("--loop", type=int, default=0, help="sleep N seconds between cycles")
    parser.add_argument("--limit", type=int, default=100, help="max new articles per cycle")
    parser.add_argument("--max-urls-per-source", type=int, default=25)
    args = parser.parse_args(argv)

    logger.info("worker starting (mode=%s)", "once" if args.once else "loop")
    while True:
        started = datetime.now(timezone.utc)
        summary = run_cycle(limit=args.limit, max_urls_per_source=args.max_urls_per_source)
        logger.info("cycle summary=%s elapsed=%.1fs",
                    summary, (datetime.now(timezone.utc) - started).total_seconds())
        if args.once or not args.loop:
            break
        time.sleep(args.loop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
