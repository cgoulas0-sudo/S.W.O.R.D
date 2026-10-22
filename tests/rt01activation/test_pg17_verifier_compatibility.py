"""Managed PostgreSQL 17 verifier-role compatibility proof."""

import os
from pathlib import Path

import psycopg2
import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
BASELINE_ROLES_SQL = ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"
DEFAULT_DSN = "postgresql://postgres:rhc@localhost:55433/rhc"
PRE_RT01C = (
    "20260908000001_rt01a_published_runtime_floor.sql",
    "20260908000002_rt01a_bootstrap_unknown_runtime.sql",
    "20260908000003_rt01b_save_gateway_mutation_boundary.sql",
)
RT01C = "20260908000004_rt01c_runtime_published_git_handshake.sql"
POST_RT01C = (
    "20260908000005_rt01c_bind_runtime_mirror_base.sql",
    "20260908000006_rt01d_dm_read_engineering_release.sql",
)
EXECUTOR = "rhc_migration_executor"
EXECUTOR_PASSWORD = "rhc-test-executor"


def _dsn():
    return os.environ.get("RHC_RT01_ACTIVATION_PG_DSN", DEFAULT_DSN)


def _sql(path):
    return path.read_text(encoding="utf-8")


def _apply(cur, name):
    cur.execute(_sql(MIGRATIONS / name))


@pytest.fixture(scope="session")
def pg17_connections():
    try:
        admin = psycopg2.connect(_dsn())
    except psycopg2.OperationalError as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"RT01 activation proof needs PostgreSQL 17 at {_dsn()!r}: {exc}")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute("show server_version_num")
        if int(cur.fetchone()[0]) < 170000:
            admin.close()
            pytest.skip("RT01 activation compatibility proof requires PostgreSQL 17+")
    yield admin
    admin.close()


@pytest.fixture()
def pg17_db(pg17_connections):
    admin = pg17_connections
    with admin.cursor() as cur:
        cur.execute("drop schema if exists public cascade")
        cur.execute("drop role if exists rhc_mirror_verifier")
        cur.execute("drop role if exists rhc_unrelated_role")
        cur.execute(f"drop role if exists {EXECUTOR}")
        cur.execute(_sql(BASELINE_ROLES_SQL))
        cur.execute(
            f"create role {EXECUTOR} login password %s createrole",
            (EXECUTOR_PASSWORD,),
        )
        cur.execute(f"create schema public authorization {EXECUTOR}")
        cur.execute("grant usage on schema public to anon, authenticated, service_role")
    executor = psycopg2.connect(
        _dsn(), user=EXECUTOR, password=EXECUTOR_PASSWORD
    )
    executor.autocommit = True
    with executor.cursor() as cur:
        for name in PRE_RT01C:
            _apply(cur, name)
    try:
        yield admin, executor
    finally:
        executor.close()
        with admin.cursor() as cur:
            cur.execute("drop schema if exists public cascade")
            cur.execute("drop role if exists rhc_mirror_verifier")
            cur.execute("drop role if exists rhc_unrelated_role")
            cur.execute(f"drop role if exists {EXECUTOR}")


def test_pg17_creator_relationship_installs_full_chain_and_verifier_executes(pg17_db):
    admin, executor = pg17_db
    with executor.cursor() as cur:
        cur.execute("begin")
        cur.execute("create role rhc_mirror_verifier nologin")
        cur.execute(
            "select admin_option, inherit_option, set_option "
            "from pg_auth_members "
            "where roleid = 'rhc_mirror_verifier'::regrole "
            "and member = current_user::regrole"
        )
        assert cur.fetchall() == [(True, False, False)]
        cur.execute("rollback")

        cur.execute("begin")
        _apply(cur, RT01C)
        cur.execute("rollback")
        cur.execute(
            "select count(*) from pg_roles where rolname = 'rhc_mirror_verifier'"
        )
        assert cur.fetchone()[0] == 0

        _apply(cur, RT01C)
        for name in POST_RT01C:
            _apply(cur, name)

        cur.execute("select lock_token from public.begin_campaign_save(30)")
        token = cur.fetchone()[0]
        cur.execute("select public.stage_campaign_state(%s, 'k', '1'::jsonb)", (token,))
        cur.execute("select public.publish_campaign_save(%s)", (token,))
        cur.execute("select public.get_pending_runtime_mirror()")
        candidate = cur.fetchone()[0]
        cur.execute("set role rhc_mirror_verifier")
        cur.execute(
            "select public.bind_runtime_mirror_base(%s, %s::uuid, %s)",
            (
                candidate["generation"],
                candidate["mirror_token"],
                "a" * 40,
            ),
        )
        cur.execute("reset role")

    with admin.cursor() as cur:
        cur.execute(
            "select rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, "
            "rolreplication, rolbypassrls from pg_roles "
            "where rolname = 'rhc_mirror_verifier'"
        )
        assert cur.fetchone() == (False, False, False, False, False, False)
        cur.execute(
            "select m.rolname, bool_or(am.admin_option), "
            "bool_or(am.set_option), bool_or(am.inherit_option) "
            "from pg_auth_members am "
            "join pg_roles m on m.oid = am.member "
            "where am.roleid = 'rhc_mirror_verifier'::regrole "
            "group by m.rolname"
        )
        assert cur.fetchall() == [(EXECUTOR, True, True, False)]
        cur.execute("set role service_role")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(
                    "select public.bind_runtime_mirror_base(%s, %s::uuid, %s)",
                    (
                        candidate["generation"],
                        candidate["mirror_token"],
                        "a" * 40,
                    ),
                )
        finally:
            cur.execute("reset role")


def test_pg17_refuses_unsafe_preexisting_verifier_attributes(pg17_db):
    _admin, executor = pg17_db
    with executor.cursor() as cur:
        cur.execute("create role rhc_mirror_verifier login")
        with pytest.raises(psycopg2.errors.RaiseException, match="unsafe role attributes"):
            _apply(cur, RT01C)


def test_pg17_refuses_unrelated_verifier_member(pg17_db):
    _admin, executor = pg17_db
    with executor.cursor() as cur:
        cur.execute("create role rhc_mirror_verifier nologin")
        cur.execute("grant rhc_mirror_verifier to service_role")
        with pytest.raises(psycopg2.errors.RaiseException, match="unsafe role membership"):
            _apply(cur, RT01C)


def test_pg17_refuses_verifier_membership_in_another_role(pg17_db):
    admin, executor = pg17_db
    with admin.cursor() as cur:
        cur.execute("create role rhc_mirror_verifier nologin")
        cur.execute("create role rhc_unrelated_role nologin")
        cur.execute("grant rhc_unrelated_role to rhc_mirror_verifier")
    with executor.cursor() as cur:
        with pytest.raises(psycopg2.errors.RaiseException, match="unsafe role membership"):
            _apply(cur, RT01C)
