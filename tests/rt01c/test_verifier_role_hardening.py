"""Regression proof for the RT01-C verifier role trust boundary."""

import os
from pathlib import Path

import psycopg2
import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
BASELINE_ROLES_SQL = ROOT / "tests" / "rt01a" / "supabase_baseline_roles.sql"
DEFAULT_DSN = "postgresql://postgres:rhc@localhost:55432/rhc"

PRE_RT01C = (
    "20260908000001_rt01a_published_runtime_floor.sql",
    "20260908000002_rt01a_bootstrap_unknown_runtime.sql",
    "20260908000003_rt01b_save_gateway_mutation_boundary.sql",
)
RT01C = "20260908000004_rt01c_runtime_published_git_handshake.sql"


def _dsn():
    return (
        os.environ.get("RHC_RT01C_PG_DSN")
        or os.environ.get("RHC_RT01B_PG_DSN")
        or os.environ.get("RHC_RT01A_PG_DSN")
        or DEFAULT_DSN
    )


def _apply(cur, name):
    cur.execute((MIGRATIONS / name).read_text(encoding="utf-8"))


def _prepare_conn():
    conn = psycopg2.connect(_dsn())
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("drop schema if exists public cascade")
        cur.execute("drop role if exists rhc_mirror_verifier")
        cur.execute(BASELINE_ROLES_SQL.read_text(encoding="utf-8"))
        cur.execute("create schema public")
        cur.execute("grant usage on schema public to anon, authenticated, service_role")
        for name in PRE_RT01C:
            _apply(cur, name)
    return conn


def test_rt01c_refuses_preexisting_login_enabled_verifier_role():
    try:
        conn = _prepare_conn()
    except psycopg2.OperationalError as exc:  # pragma: no cover
        pytest.skip(f"real PostgreSQL required: {exc}")
    try:
        with conn.cursor() as cur:
            cur.execute("create role rhc_mirror_verifier login")
            with pytest.raises(psycopg2.errors.RaiseException, match="unsafe role attributes"):
                _apply(cur, RT01C)
    finally:
        with conn.cursor() as cur:
            cur.execute("drop schema if exists public cascade")
            cur.execute("drop role if exists rhc_mirror_verifier")
        conn.close()


def test_rt01c_refuses_preexisting_service_role_membership():
    try:
        conn = _prepare_conn()
    except psycopg2.OperationalError as exc:  # pragma: no cover
        pytest.skip(f"real PostgreSQL required: {exc}")
    try:
        with conn.cursor() as cur:
            cur.execute("create role rhc_mirror_verifier nologin")
            cur.execute("grant rhc_mirror_verifier to service_role")
            with pytest.raises(psycopg2.errors.RaiseException, match="unsafe role membership"):
                _apply(cur, RT01C)
    finally:
        with conn.cursor() as cur:
            cur.execute("drop schema if exists public cascade")
            cur.execute("revoke rhc_mirror_verifier from service_role")
            cur.execute("drop role if exists rhc_mirror_verifier")
        conn.close()
