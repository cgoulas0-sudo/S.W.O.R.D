"""RT01-A proof for coherent staging locator states."""

import psycopg2
import pytest


def _exec(db, sql):
    with db.cursor() as cur:
        cur.execute(sql)


def test_save_in_progress_requires_staging_generation(db):
    with pytest.raises(psycopg2.errors.CheckViolation):
        _exec(
            db,
            "update public.campaign_runtime "
            "set save_in_progress = true, staging_generation = null where id = 1",
        )


def test_staging_generation_requires_save_in_progress(db):
    with pytest.raises(psycopg2.errors.CheckViolation):
        _exec(
            db,
            "update public.campaign_runtime "
            "set save_in_progress = false, staging_generation = 1 where id = 1",
        )
