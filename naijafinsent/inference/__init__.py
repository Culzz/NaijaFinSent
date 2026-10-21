"""Packaging metadata mirrors for the inference layer.

Keeping the Protocol names importable from one place means the API can depend
on ``naijafinsent.inference`` rather than reaching into submodules.
"""

from __future__ import annotations

from naijafinsent.inference.pipeline import (  # noqa: F401
    LIMITATIONS,
    AnalysisPipeline,
    PipelineContext,
    StageProvenance,
    StubPipeline,
)

__all__ = [
    "AnalysisPipeline",
    "StubPipeline",
    "PipelineContext",
    "StageProvenance",
    "LIMITATIONS",
]
