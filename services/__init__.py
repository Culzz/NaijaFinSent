"""NaijaFinSent services.

Two deployables live here, both of which import *from* the framework-free
``naijafinsent`` core package and never the reverse:

* ``services.api``    - the FastAPI inference + analytics service.
* ``services.worker`` - the scheduled ingestion / inference / alert loop.

Marking this a regular package (rather than relying on implicit namespace
packages) keeps imports deterministic on Windows and inside slim containers,
and gives ``ruff`` and ``mypy`` a stable root to anchor to.
"""

from __future__ import annotations
