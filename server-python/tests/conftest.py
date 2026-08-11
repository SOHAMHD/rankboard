"""Test setup.

app.config raises at import time without JWT_SECRET, and app.db without
DATABASE_URL — both deliberately, so a misconfigured server fails at boot rather
than at the first request. Those have to exist before any app module is
imported, which is what this file is for. No test here opens a database
connection.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://tests/tests")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-for-anything-real")
os.environ.setdefault("SKIP_DB_INIT", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
