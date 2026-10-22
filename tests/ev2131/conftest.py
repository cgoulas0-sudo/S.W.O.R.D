"""EV2-13.1 timed applied-status proof conftest.

This directory's real-PostgreSQL fixtures and migration-chain installer are
defined once in :mod:`ev2131_util` and re-exported here so pytest discovers them
for the suite. The proof only runs against a live PostgreSQL server; when none is
reachable the whole module set is skipped rather than mocked. No Supabase project
or live database is ever contacted.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ev2131_util import (  # noqa: E402,F401
    EV2131_MIGRATION,
    FORWARD_MIGRATIONS,
    database_server,
    database_server_pg17,
    db,
    db_pg17,
    install_chain,
)