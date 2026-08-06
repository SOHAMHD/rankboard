"""Test setup.

app.db raises at import time if DATABASE_URL is missing, and app.config does the
same for JWT_SECRET — both deliberately, so a misconfigured server fails loudly
at boot instead of at the first request. Tests need those variables present
before any app module is imported, which is what this file is for. Nothing here
connects to a database: the units under test take a connection as an argument,
so the tests hand them a fake (see fake_db.py).
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://tests/tests")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-for-anything-real")
os.environ.setdefault("SKIP_DB_INIT", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
