"""HWB-02 forward-only install safety proof (real PostgreSQL 15 + 17).

The HWB-02 migration must:
  * install cleanly on the current RT01+RT02+RT03+RT04 spine when no save is
    active (JOHNNY #69 proof 10);
  * refuse to install while a save is active (proof 11);
  * acquire the authoritative singleton lock (the same advisory xact lock and
    `FOR UPDATE` row lock `begin_campaign_save` takes) BEFORE testing
    `save_in_progress`, so a concurrent `begin_campaign_save` can never race the
    check and start staging under the pre-HWB-02 generic function definitions
    (proof 12).

The race proof holds an uncommitted `begin_campaign_save` on one connection and
installs on another under a short `statement_timeout`: the install must BLOCK on
the lock and be cancelled. An unlocked `exists (select ... where save_in_progress)`
check reads the uncommitted save as false under READ COMMITTED and would install
immediately — the exact defect.

Proved on real PostgreSQL 15 and 17. No live Supabase is touched.
"""

import psycopg2
import psycopg2.errors
import pytest

from conftest import HWB02, MIGRATIONS

pytest.importorskip("psycopg2")


def _migration_sql():
    return (MIGRATIONS / HWB02).read_text(encoding="utf-8")


def _begin_save(conn):
    with conn.cursor() as cur:
        cur.execute("select * from public.begin_campaign_save(30)")
        return cur.fetchone()


def _abort_save(conn, token):
    with conn.cursor() as cur:
        cur.execute("select public.abort_campaign_save(%s)", (token,))


@pytest.mark.parametrize("db_name", ("db_pre_hwb02", "db17_pre_hwb02"))
def test_migration_installs_when_no_save_active(request, db_name):
    db = request.getfixturevalue(db_name)
    with db.cursor() as cur:
        cur.execute(_migration_sql())
    # Post-install enforcement is live and fails closed on an undeclared key.
    token = _begin_save(db)[2]
    with pytest.raises(psycopg2.errors.RaiseException, match="not allowed for campaign_save"):
        with db.cursor() as cur:
            cur.execute(
                "select public.stage_campaign_state(%s, 'invented_domain', '{}'::jsonb)",
                (token,),
            )
    # RT02/RT04 dedicated closures compose after the install too.
    with pytest.raises(psycopg2.errors.RaiseException, match="campaign_clock is engine-owned"):
        with db.cursor() as cur:
            cur.execute(
                "select public.delete_staged_campaign_state(%s, 'campaign_clock')",
                (token,),
            )
    _abort_save(db, token)


@pytest.mark.parametrize("db_name", ("db_pre_hwb02", "db17_pre_hwb02"))
def test_migration_refuses_install_while_save_active(request, db_name):
    db = request.getfixturevalue(db_name)
    token = _begin_save(db)[2]
    with pytest.raises(psycopg2.errors.RaiseException, match="migration refused"):
        with db.cursor() as cur:
            cur.execute(_migration_sql())
    _abort_save(db, token)
    # After the active save resolves, the same forward-only install succeeds.
    with db.cursor() as cur:
        cur.execute(_migration_sql())
    token = _begin_save(db)[2]
    with pytest.raises(psycopg2.errors.RaiseException, match="not allowed for campaign_save"):
        with db.cursor() as cur:
            cur.execute(
                "select public.stage_campaign_state(%s, 'invented_domain', '{}'::jsonb)",
                (token,),
            )
    _abort_save(db, token)


@pytest.mark.parametrize(
    "dsn_name, db_name",
    (
        ("pg15_dsn", "db_pre_hwb02"),
        ("pg17_dsn", "db17_pre_hwb02"),
    ),
)
def test_migration_install_locks_singleton_and_blocks_inflight_begin(
    request, dsn_name, db_name
):
    """The install check locks the authoritative singleton; it cannot race BEGIN.

    Connection A holds an uncommitted `campaign_save` (advisory + row lock,
    `save_in_progress = true`, no COMMIT). Connection B attempts the install with
    a short `statement_timeout`: the install BLOCKS on the lock and raises
    `QueryCanceled`.
    """
    dsn = request.getfixturevalue(dsn_name)
    db = request.getfixturevalue(db_name)

    conn_a = psycopg2.connect(dsn)
    conn_a.autocommit = False
    try:
        with conn_a.cursor() as cur:
            cur.execute("select * from public.begin_campaign_save(30)")
        conn_b = psycopg2.connect(dsn)
        conn_b.autocommit = True
        try:
            with conn_b.cursor() as cur:
                cur.execute("set statement_timeout = 800")
                with pytest.raises(psycopg2.errors.QueryCanceled):
                    cur.execute(_migration_sql())
        finally:
            conn_b.close()
    finally:
        conn_a.rollback()
        conn_a.close()

    # After the in-flight save resolves, the install succeeds and enforcement is
    # live on this engine.
    with db.cursor() as cur:
        cur.execute(_migration_sql())
    token = _begin_save(db)[2]
    with pytest.raises(psycopg2.errors.RaiseException, match="not allowed for campaign_save"):
        with db.cursor() as cur:
            cur.execute(
                "select public.stage_campaign_state(%s, 'invented_domain', '{}'::jsonb)",
                (token,),
            )
    _abort_save(db, token)