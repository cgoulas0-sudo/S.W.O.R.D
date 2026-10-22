"""RT01-B — real-PostgreSQL proof of the mechanical mutation boundary.

WIN 4 (raw DML blocked) and WIN 5 (internal guard helpers are not a public
bypass), plus the history-attack surface: normal staging cannot mutate a
published/historical generation, and unpublished candidates never surface
through the published-only RT01-A projection.
"""

import psycopg2
import pytest

from gateway_util import begin_save, break_glass, exec_, scalar


RUNTIME_TABLES = ("campaign_runtime", "campaign_state_generations")


def _as_role(db, role, sql, params=None):
    with db.cursor() as cur:
        cur.execute(f"set role {role}")
        try:
            cur.execute(sql, params or ())
        finally:
            cur.execute("reset role")


# ---------------------------------------------------------------------------
# WIN 4 — layer 1: service_role holds no direct DML privilege
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("table", RUNTIME_TABLES)
def test_service_role_cannot_directly_insert(db, table):
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        _as_role(
            db,
            "service_role",
            f"insert into public.{table} (id) values (1)"
            if table == "campaign_runtime"
            else f"insert into public.{table} (generation, key, value)"
            " values (0, 'x', '1'::jsonb)",
        )


@pytest.mark.parametrize("table", RUNTIME_TABLES)
def test_service_role_cannot_directly_update_or_delete(db, table):
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        _as_role(db, "service_role", f"update public.{table} set id = id" if table == "campaign_runtime"
                 else f"update public.{table} set value = value")
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        _as_role(db, "service_role", f"delete from public.{table}")


def test_service_role_keeps_select(db):
    # The runtime role must still be able to READ published state.
    _as_role(db, "service_role", "select count(*) from public.campaign_state_runtime")


# ---------------------------------------------------------------------------
# WIN 4 — layer 2: ungated owner/superuser raw DML trips the guard trigger
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("table", RUNTIME_TABLES)
def test_ungated_owner_raw_insert_is_rejected_by_guard(db, table):
    # The proof connection is the table owner/superuser. Without passing through a
    # gateway function, even the owner's raw write must trip the guard.
    sql = (
        "insert into public.campaign_state_generations (generation, key, value)"
        " values (0, 'x', '1'::jsonb)"
        if table == "campaign_state_generations"
        else "update public.campaign_runtime set published_day = 5 where id = 1"
    )
    with pytest.raises(psycopg2.errors.InsufficientPrivilege) as exc:
        exec_(db, sql)
    assert "guarded RHC save gateway" in str(exc.value)


def test_ungated_owner_raw_delete_is_rejected_by_guard(db):
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        exec_(db, "delete from public.campaign_runtime where id = 1")


# ---------------------------------------------------------------------------
# WIN 4 — TRUNCATE cannot bypass the mutation boundary (P1 repair)
# ---------------------------------------------------------------------------
# Row-level triggers never fire for TRUNCATE, so without a statement-level guard an
# owner/raw TRUNCATE could erase the runtime locator or every published/historical
# generation outside the gateway. Both layers must cover TRUNCATE too.
@pytest.mark.parametrize("table", RUNTIME_TABLES)
def test_service_role_cannot_truncate(db, table):
    # Layer 1: service_role holds no TRUNCATE privilege on runtime-owned tables.
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        _as_role(db, "service_role", f"truncate table public.{table}")


@pytest.mark.parametrize("table", RUNTIME_TABLES)
def test_ungated_owner_truncate_is_rejected_by_guard(db, table):
    # Layer 2: even the table owner's ungated raw TRUNCATE trips the guard trigger.
    with pytest.raises(psycopg2.errors.InsufficientPrivilege) as exc:
        exec_(db, f"truncate table public.{table}")
    assert "truncation requires the guarded RHC save gateway" in str(exc.value)


def test_break_glass_truncate_works_only_when_guard_asserted(db):
    # Seed a published generation so the runtime table is non-empty.
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'k', '1'::jsonb)", (ctx["token"],))
    exec_(db, "select public.publish_campaign_save(%s)", (ctx["token"],))
    assert scalar(db, "select count(*) from public.campaign_state_generations") > 0

    # An intentional administrative TRUNCATE succeeds ONLY inside a guard-asserted
    # transaction (break-glass) — not as normal gameplay authority.
    break_glass(db, "truncate table public.campaign_state_generations")
    assert scalar(db, "select count(*) from public.campaign_state_generations") == 0

    # The guard is transaction-local: it did not leak past the break-glass
    # transaction, so a subsequent ungated TRUNCATE is rejected again.
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        exec_(db, "truncate table public.campaign_state_generations")


def test_break_glass_superuser_can_still_administer(db):
    # Superuser break-glass is an intentional administrative path, not normal
    # gameplay authority: it works only by explicitly asserting the guard inside
    # the writing transaction.
    break_glass(db, "update public.campaign_runtime set published_day = 7 where id = 1")
    assert scalar(db, "select published_day from public.campaign_runtime") == 7
    # A subsequent ungated raw write is rejected again — the guard is transaction
    # -local and did not persist beyond the break-glass transaction.
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        exec_(db, "update public.campaign_runtime set published_day = 8 where id = 1")


# ---------------------------------------------------------------------------
# WIN 5 — internal guard helpers cannot be invoked as a public bypass
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "call",
    [
        "select public._rhc_require_active_save('anything')",
        "select public._rhc_guard_runtime_owned_dml()",
    ],
)
def test_internal_helpers_are_not_executable_by_service_role(db, call):
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        _as_role(db, "service_role", call)


def test_asserting_guard_alone_does_not_enable_service_role_dml(db):
    # Even if a caller could set the guard, the privilege layer still blocks DML.
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        with db.cursor() as cur:
            cur.execute("set role service_role")
            try:
                cur.execute(
                    "insert into public.campaign_state_generations (generation, key, value)"
                    " values (0, 'x', '1'::jsonb)"
                )
            finally:
                cur.execute("reset role")


# ---------------------------------------------------------------------------
# History attacks — staging cannot touch a published/historical generation
# ---------------------------------------------------------------------------
def test_gateway_cannot_stage_into_published_generation(db):
    # Publish gen 1, begin gen 2. The active staging generation is 2; there is no
    # gateway path that targets generation <= published_generation.
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'weather', '\"clear\"'::jsonb)", (ctx["token"],))
    exec_(db, "select public.publish_campaign_save(%s)", (ctx["token"],))

    ctx2 = begin_save(db)  # staging generation 2
    exec_(db, "select public.stage_campaign_state(%s, 'weather', '\"storm\"'::jsonb)", (ctx2["token"],))
    # The published generation-1 row is untouched by staging at generation 2.
    assert (
        scalar(
            db,
            "select value from public.campaign_state_generations"
            " where generation = 1 and key = 'weather'",
        )
        == "clear"
    )


def test_unpublished_candidate_is_invisible_through_published_view(db):
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'secret', '\"staged\"'::jsonb)", (ctx["token"],))
    # RT01-A published-only projection must never expose the staged candidate.
    assert scalar(db, "select count(*) from public.campaign_state_runtime") == 0
