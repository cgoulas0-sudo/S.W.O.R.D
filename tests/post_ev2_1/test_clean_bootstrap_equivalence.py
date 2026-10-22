"""POST-EV2-1 Patch 1D proof — clean bootstrap / baseline equivalence.

The clean bootstrap is deliberately a pinned flattened replay of the exact
18-file historical migration frontier at main
d3292fd53cbb162a9e13c9e6148f88cfc474fa75. Historical migrations remain the
upgrade/audit authority. This suite proves the baseline stays source-identical to
that frontier and converges to the same effective PostgreSQL state on real
PostgreSQL 15 and 17.

No live Supabase is touched.
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import uuid

import pytest

psycopg2 = pytest.importorskip(
    "psycopg2", reason="POST-EV2-1 Patch 1D needs real PostgreSQL servers"
)
from psycopg2 import sql
from psycopg2.extensions import parse_dsn


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
BASELINE = ROOT / "supabase" / "baselines" / "20260924_post_ev2_1_clean_bootstrap.sql"
BASELINE_ROLES = ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"

CUT_POINT_SHA = "d3292fd53cbb162a9e13c9e6148f88cfc474fa75"
MIGRATION_NAMES = (
    "20260908000001_rt01a_published_runtime_floor.sql",
    "20260908000002_rt01a_bootstrap_unknown_runtime.sql",
    "20260908000003_rt01b_save_gateway_mutation_boundary.sql",
    "20260908000004_rt01c_runtime_published_git_handshake.sql",
    "20260908000005_rt01c_bind_runtime_mirror_base.sql",
    "20260908000006_rt01d_dm_read_engineering_release.sql",
    "20260911000001_rt02_campaign_clock.sql",
    "20260911000002_rt03_canonical_run_runtime_read.sql",
    "20260912000001_rt04_safe_run_reconciliation.sql",
    "20260914000001_hwb02_save_runtime_authority.sql",
    "20260915000001_ev210_inventory_ownership.sql",
    "20260917000001_ev211_item_custody.sql",
    "20260919000001_ev2121_item_identity_admission.sql",
    "20260919000002_ev213_mutable_entity_state.sql",
    "20260920000001_ev213420_temporal_core.sql",
    "20260920000002_ev2131_timed_status_continuity.sql",
    "20260923000001_post_ev2_1_save_domain_policy_registry.sql",
    "20260923000002_post_ev2_1_same_save_compatibility_dispatcher.sql",
)
MIGRATIONS = tuple(MIGRATIONS_DIR / name for name in MIGRATION_NAMES)

BASELINE_HEADER = """-- POST-EV2-1 Patch 1D — clean bootstrap baseline
-- Rolling High Club runtime, clean-environment bootstrap only.
--
-- PINNED FRONTIER:
--   repository: Nollie-gif/Rolling-High-Club
--   base/main cut point: d3292fd53cbb162a9e13c9e6148f88cfc474fa75
--   final historical migration:
--     20260923000002_post_ev2_1_same_save_compatibility_dispatcher.sql
--   migration count: 18
--
-- CONTRACT:
--   * This file is NOT a migration and MUST NOT be placed under supabase/migrations/.
--   * It is valid only for a fresh/empty environment that already has the
--     Supabase baseline roles anon/authenticated/service_role.
--   * Existing databases continue to upgrade through the preserved historical
--     migration chain. Never apply this file on top of an existing RHC runtime.
--   * The body below is a deterministic flattened replay of the exact 18-file
--     historical chain at the pinned cut point. Patch 1D tests prove this file
--     remains source-identical to that chain and behaviorally equivalent on
--     PostgreSQL 15 and 17.
--   * It contains no production campaign data and preserves Unknown-safe
--     bootstrap state.
--
-- WHY THIS SHAPE:
--   Patch 1D deliberately does not attempt a semantic SQL rewrite or pg_dump
--   canonicalization. The safest first clean baseline is a single pinned
--   clean-install artifact assembled verbatim from already-reviewed migrations.
--   Historical migration files remain the upgrade/audit authority.
"""

PG15_ENV = "RHC_POST_EV21_PG_DSN"
PG17_ENV = "RHC_POST_EV21_PG17_DSN"
PG15_FALLBACK = "postgresql://postgres:rhc@localhost:55432/rhc"
PG17_FALLBACK = "postgresql://postgres:rhc@localhost:55433/rhc"

POLICY_KEYS = (
    "daily_recap",
    "runs",
    "campaign_clock",
    "run_reconciliations",
    "inventory",
    "item_custody",
    "item_admissions",
    "entity_state",
    "applied_statuses",
    "__unknown_patch_1d_key__",
)
COMPATIBILITY_OPERATIONS = (
    "stage_runs",
    "delete_runs",
    "reconcile_runs",
    "mutate_inventory",
    "mutate_item_custody",
    "admit_item_identity",
    "mutate_entity_state",
    "mutate_applied_status",
    "stage_campaign_clock",
)


def _flattened_body():
    parts = []
    for migration in MIGRATIONS:
        object_path = f"supabase/migrations/{migration.name}"
        pinned = subprocess.run(
            ["git", "show", f"{CUT_POINT_SHA}:{object_path}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        assert migration.read_bytes() == pinned, f"Historical migration drift: {object_path}"
        parts.append(
            "\n-- ============================================================================\n"
            f"-- SOURCE MIGRATION: {migration.name}\n"
            "-- ============================================================================\n\n"
            f"{pinned.decode('utf-8').rstrip()}\n"
        )
    return "".join(parts)


def test_baseline_is_exactly_the_pinned_18_migration_frontier():
    discovered = tuple(path.name for path in sorted(MIGRATIONS_DIR.glob("*.sql")))
    frontier_index = discovered.index(MIGRATION_NAMES[-1])
    assert discovered[: frontier_index + 1] == MIGRATION_NAMES
    assert len(MIGRATION_NAMES) == 18
    assert BASELINE.parent.name == "baselines"
    assert BASELINE.parent != MIGRATIONS_DIR
    expected = BASELINE_HEADER + _flattened_body()
    assert BASELINE.read_text(encoding="utf-8") == expected


def _dsn(env_name, fallback):
    return os.environ.get(env_name, fallback)


def _db_params(dsn, dbname):
    params = parse_dsn(dsn)
    params["dbname"] = dbname
    return params


@contextmanager
def _temporary_database(dsn, label):
    name = f"rhc_1d_{label}_{uuid.uuid4().hex[:12]}"
    admin = None
    db = None
    try:
        admin = psycopg2.connect(**_db_params(dsn, "postgres"))
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(sql.SQL("create database {} template template0").format(sql.Identifier(name)))
        db = psycopg2.connect(**_db_params(dsn, name))
        db.autocommit = False
        yield db
    finally:
        if db is not None:
            db.close()
        if admin is not None:
            with admin.cursor() as cur:
                cur.execute(
                    "select pg_terminate_backend(pid) from pg_stat_activity "
                    "where datname = %s and pid <> pg_backend_pid()",
                    (name,),
                )
                cur.execute(sql.SQL("drop database if exists {}").format(sql.Identifier(name)))
            admin.close()


def _install_roles(db):
    with db.cursor() as cur:
        cur.execute(BASELINE_ROLES.read_text(encoding="utf-8"))
    db.commit()


def _install_full_replay(db):
    _install_roles(db)
    with db.cursor() as cur:
        for migration in MIGRATIONS:
            cur.execute(migration.read_text(encoding="utf-8"))
    db.commit()


def _install_clean_baseline(db):
    _install_roles(db)
    with db.cursor() as cur:
        cur.execute(BASELINE.read_text(encoding="utf-8"))
    db.commit()


def _rows(db, query, params=()):
    with db.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def _catalog_snapshot(db):
    """Capture authority-relevant effective state, excluding unstable OIDs/timestamps."""
    return {
        "relations": _rows(
            db,
            """
            select c.relkind, c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   coalesce(c.relacl::text, '')
              from pg_class c
              join pg_namespace n on n.oid = c.relnamespace
             where n.nspname = 'public'
               and c.relkind in ('r','p','v','m','S')
             order by c.relkind, c.relname
            """,
        ),
        "columns": _rows(
            db,
            """
            select table_name, ordinal_position, column_name, data_type, udt_name,
                   is_nullable, coalesce(column_default, ''), is_identity
              from information_schema.columns
             where table_schema = 'public'
             order by table_name, ordinal_position
            """,
        ),
        "constraints": _rows(
            db,
            """
            select c.conrelid::regclass::text, c.conname, c.contype,
                   pg_get_constraintdef(c.oid, true)
              from pg_constraint c
             where c.connamespace = 'public'::regnamespace
             order by 1, 2
            """,
        ),
        "indexes": _rows(
            db,
            """
            select tablename, indexname, indexdef
              from pg_indexes
             where schemaname = 'public'
             order by tablename, indexname
            """,
        ),
        "triggers": _rows(
            db,
            """
            select c.relname, t.tgname, pg_get_triggerdef(t.oid, true)
              from pg_trigger t
              join pg_class c on c.oid = t.tgrelid
              join pg_namespace n on n.oid = c.relnamespace
             where n.nspname = 'public' and not t.tgisinternal
             order by c.relname, t.tgname
            """,
        ),
        "policies": _rows(
            db,
            """
            select tablename, policyname, permissive, roles::text, cmd,
                   coalesce(qual, ''), coalesce(with_check, '')
              from pg_policies
             where schemaname = 'public'
             order by tablename, policyname
            """,
        ),
        "routines": _rows(
            db,
            """
            select p.proname,
                   pg_get_function_identity_arguments(p.oid),
                   pg_get_function_result(p.oid),
                   p.prokind, p.prosecdef, p.provolatile, p.proparallel,
                   coalesce(p.proacl::text, ''),
                   pg_get_functiondef(p.oid)
              from pg_proc p
              join pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'public'
             order by p.proname, pg_get_function_identity_arguments(p.oid)
            """,
        ),
        "views": _rows(
            db,
            """
            select c.relname, pg_get_viewdef(c.oid, true)
              from pg_class c
              join pg_namespace n on n.oid = c.relnamespace
             where n.nspname = 'public' and c.relkind in ('v','m')
             order by c.relname
            """,
        ),
        "runtime_seed": _rows(
            db,
            """
            select (
              to_jsonb(cr)
              - 'bootstrapped_at'
              - 'updated_at'
              - 'save_started_at'
              - 'lock_expires_at'
            )::text
              from public.campaign_runtime cr
             order by id
            """,
        ),
        "generation_state": _rows(
            db,
            """
            select generation, key, value::text
              from public.campaign_state_generations
             order by generation, key
            """,
        ),
        "table_privileges": _rows(
            db,
            """
            select grantee, table_name, privilege_type, is_grantable
              from information_schema.table_privileges
             where table_schema = 'public'
               and grantee in ('anon','authenticated','service_role','rhc_mirror_verifier')
             order by grantee, table_name, privilege_type, is_grantable
            """,
        ),
        "routine_privileges": _rows(
            db,
            """
            select grantee, routine_name, privilege_type, is_grantable
              from information_schema.routine_privileges
             where routine_schema = 'public'
               and grantee in ('anon','authenticated','service_role','rhc_mirror_verifier')
             order by grantee, routine_name, privilege_type, is_grantable
            """,
        ),
    }


def _role_snapshot(db):
    role = _rows(
        db,
        """
        select rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
               rolreplication, rolbypassrls
          from pg_roles
         where rolname = 'rhc_mirror_verifier'
        """,
    )
    memberships = _rows(
        db,
        """
        select member_role.rolname, granted_role.rolname, m.admin_option
          from pg_auth_members m
          join pg_roles member_role on member_role.oid = m.member
          join pg_roles granted_role on granted_role.oid = m.roleid
         where member_role.rolname = 'rhc_mirror_verifier'
            or granted_role.rolname = 'rhc_mirror_verifier'
         order by member_role.rolname, granted_role.rolname
        """,
    )
    return role, memberships


def _policy_snapshot(db):
    domain = {}
    compatibility = {}
    with db.cursor() as cur:
        for key in POLICY_KEYS:
            cur.execute("select public._rhc_save_domain_policy(%s)", (key,))
            domain[key] = cur.fetchone()[0]
        for operation in COMPATIBILITY_OPERATIONS:
            cur.execute("select public._rhc_same_save_compatibility_policy(%s)", (operation,))
            compatibility[operation] = cur.fetchone()[0]
    return domain, compatibility


def _behavior_snapshot(db):
    """Representative allowed + fail-closed behavior without publishing anything."""
    result = {}
    with db.cursor() as cur:
        cur.execute("select * from public.begin_campaign_save(30)")
        published, staging, token, _expires = cur.fetchone()
        result["begin_delta"] = staging - published
        cur.execute(
            "select (public.stage_campaign_state(%s, 'daily_recap', %s::jsonb)).key",
            (token, json.dumps({"probe": "patch-1d"})),
        )
        result["generic_allowed_key"] = cur.fetchone()[0]
        cur.execute("select public.abort_campaign_save(%s)", (token,))
        result["abort"] = cur.fetchone()[0]
    db.commit()

    with db.cursor() as cur:
        cur.execute("select * from public.begin_campaign_save(30)")
        _published, _staging, token, _expires = cur.fetchone()
        try:
            cur.execute(
                "select public.stage_campaign_state(%s, 'campaign_clock', '{}'::jsonb)",
                (token,),
            )
        except psycopg2.Error as exc:
            result["dedicated_bypass_sqlstate"] = exc.pgcode
            result["dedicated_bypass_rejected"] = True
            db.rollback()
        else:  # pragma: no cover - this is the safety failure the test guards
            result["dedicated_bypass_rejected"] = False
            db.rollback()

    with db.cursor() as cur:
        cur.execute(
            "select published_generation, published_git_ref, published_day, save_in_progress "
            "from public.campaign_runtime where id = 1"
        )
        result["post_probe_runtime"] = cur.fetchone()
    db.commit()
    return result


def _prove_for_server(dsn, label):
    try:
        with _temporary_database(dsn, f"{label}_history") as history_db:
            _install_full_replay(history_db)
            history = {
                "catalog": _catalog_snapshot(history_db),
                "roles": _role_snapshot(history_db),
                "policies": _policy_snapshot(history_db),
                "behavior": _behavior_snapshot(history_db),
            }
        with _temporary_database(dsn, f"{label}_baseline") as baseline_db:
            _install_clean_baseline(baseline_db)
            baseline = {
                "catalog": _catalog_snapshot(baseline_db),
                "roles": _role_snapshot(baseline_db),
                "policies": _policy_snapshot(baseline_db),
                "behavior": _behavior_snapshot(baseline_db),
            }
    except psycopg2.OperationalError as exc:
        pytest.skip(f"{label} PostgreSQL is not reachable: {exc}")

    assert baseline == history
    assert baseline["catalog"]["generation_state"] == []
    runtime_seed = json.loads(baseline["catalog"]["runtime_seed"][0][0])
    assert runtime_seed["published_generation"] == 0
    assert runtime_seed["published_git_ref"] is None
    assert runtime_seed["published_day"] is None
    assert runtime_seed["save_in_progress"] is False
    assert baseline["behavior"]["begin_delta"] == 1
    assert baseline["behavior"]["generic_allowed_key"] == "daily_recap"
    assert baseline["behavior"]["dedicated_bypass_rejected"] is True
    assert baseline["behavior"]["dedicated_bypass_sqlstate"] is not None


def test_clean_bootstrap_equivalent_to_full_replay_on_postgresql15():
    _prove_for_server(_dsn(PG15_ENV, PG15_FALLBACK), "pg15")


def test_clean_bootstrap_equivalent_to_full_replay_on_postgresql17():
    _prove_for_server(_dsn(PG17_ENV, PG17_FALLBACK), "pg17")
