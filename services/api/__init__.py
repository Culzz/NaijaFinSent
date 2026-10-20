"""NaijaFinSent API service package.

The importable surface is intentionally tiny: ``services.api.app.main.create_app``
is the only thing a process (uvicorn, gunicorn, a test) needs. Everything else is
an implementation detail.
"""

from __future__ import annotations
