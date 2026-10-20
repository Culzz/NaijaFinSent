"""NaijaFinSent: Nigeria-focused financial NLP and event-intelligence platform.

Framework-free core package. The API service and worker import from here,
but this package must never import FastAPI, SQLAlchemy, or any web framework.
This is enforced by tests/test_architecture.py.
"""

__version__ = "0.1.0"
