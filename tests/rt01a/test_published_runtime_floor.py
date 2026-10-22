"""RT01-A — real-PostgreSQL proof of the published-runtime floor.

Each test maps to one or more RT01-A WIN conditions (see Issue #27). The proof
runs migrations against a real PostgreSQL instance and exercises actual Postgres
semantics: CHECK constraints, RLS, role privileges, and view generation scoping.

Run:
    python -m pytest tests/rt01a -v
"""

import psycopg2
import pytest

# 40-char lowercase hex commit SHAs used as exact-Git-ref fixtures.
FULL_SHA = "b127a513fade13d4f4bf5ec4df8069d48b88283c"
OTHER_SHA = "0123456789abcdef0123456789abcdef01234567"


def _scalar(db, sql, params=None):
    with db.cursor() as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return row[0] if row else None


def _rows(db, sql, params=None):
    with db.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def _exec(db, sql, params=None):
    with db.cursor() as cur:
        cur.execute(sql, params or ())


# ---------------------------------------------------------------------------
# WIN 1 & 2 — Unknown-safe bootstrap that invents no campaign facts
# ---------------------------------------------------------------------------
def test_bootstrap_invents_no_campaign_facts(db):
    row = _rows(
        db,
        """
        select published_generation, published_git_ref, published_day,
               save_in_progress, staging_generation
        from public.campaign_runtime
        """,
    )
    assert len(row) == 1, "runtime locator must be a single bootstrapped row"
    generation, git_ref, day, in_progress, staging = row[0]
    assert generation == 0
    assert git_ref is None, "bootstrap must not invent a pinned Git SHA"
    assert day is None, "bootstrap must not invent a current campaign day"
    assert in_progress is False
    assert staging is None
    # No seeded runtime/campaign state whatsoever.
    assert _scalar(db, "select count(*) from public.campaign_state_generations") == 0
    assert _scalar(db, "select count(*) from public.campaign_state_runtime") == 0


def test_singleton_locator_is_enforced(db):
    # id is fixed to 1; a second locator row is impossible.
    with pytest.raises(psycopg2.errors.CheckViolation):
        _exec(db, "insert into public.campaign_runtime (id) values (2)")
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _exec(db, "insert into public.campaign_runtime (id) values (1)")


# ---------------------------------------------------------------------------
# WIN 3 & 4 — published reads expose only the current generation; staged hidden
# ---------------------------------------------------------------------------
def test_published_read_exposes_only_current_generation(db):
    _exec(
        db,
        "insert into public.campaign_state_generations (generation, key, value)"
        " values (0, 'weather', '\"clear\"'::jsonb)",
    )
    published = _rows(
        db, "select key, value from public.campaign_state_runtime order by key"
    )
    assert published == [("weather", "clear")]


def test_staged_state_cannot_leak_through_published_surface(db):
    # Published (generation 0) row.
    _exec(
        db,
        "insert into public.campaign_state_generations (generation, key, value)"
        " values (0, 'weather', '\"clear\"'::jsonb)",
    )
    # Begin a (structural) staging generation ahead of the published one.
    _exec(
        db,
        "update public.campaign_runtime"
        " set save_in_progress = true, staging_generation = 1 where id = 1",
    )
    # Stage a mutation at the future generation.
    _exec(
        db,
        "insert into public.campaign_state_generations (generation, key, value)"
        " values (1, 'weather', '\"storm\"'::jsonb)",
    )
    # The published surface must still show ONLY the published generation.
    published = _rows(
        db, "select runtime_generation, key, value from public.campaign_state_runtime"
    )
    assert published == [(0, "weather", "clear")]
    # Sanity: the staged row does exist in the underlying store.
    assert (
        _scalar(
            db,
            "select value from public.campaign_state_generations"
            " where generation = 1 and key = 'weather'",
        )
        == "storm"
    )


# ---------------------------------------------------------------------------
# WIN 5 — published checkpoint binds to one EXACT full Git commit SHA
# ---------------------------------------------------------------------------
def test_exact_full_git_sha_accepted(db):
    _exec(
        db,
        "update public.campaign_runtime set published_git_ref = %s where id = 1",
        (FULL_SHA,),
    )
    assert _scalar(db, "select published_git_ref from public.campaign_runtime") == FULL_SHA


@pytest.mark.parametrize(
    "bad_ref",
    [
        "main",  # mutable branch name
        "b127a51",  # abbreviated revision
        "b127a513fade13d4f4bf5ec4df8069d48b88283",  # 39 chars (too short)
        "b127a513fade13d4f4bf5ec4df8069d48b88283cc",  # 41 chars (too long)
        "B127A513FADE13D4F4BF5EC4DF8069D48B88283C",  # uppercase, not exact form
        "b127a513fade13d4f4bf5ec4df8069d48b88283g",  # non-hex char
    ],
)
def test_non_exact_git_ref_is_rejected(db, bad_ref):
    with pytest.raises(psycopg2.errors.CheckViolation):
        _exec(
            db,
            "update public.campaign_runtime set published_git_ref = %s where id = 1",
            (bad_ref,),
        )


def test_null_git_ref_remains_valid_after_bootstrap(db):
    # Unknown is valid truth: a NULL pinned ref must stay acceptable.
    _exec(
        db,
        "update public.campaign_runtime set published_git_ref = null where id = 1",
    )
    assert _scalar(db, "select published_git_ref from public.campaign_runtime") is None


# ---------------------------------------------------------------------------
# WIN 6 — generation-scoped storage; pointer advances without rewriting history
# ---------------------------------------------------------------------------
def test_pointer_advances_without_rewriting_history(db):
    _exec(
        db,
        "insert into public.campaign_state_generations (generation, key, value)"
        " values (0, 'weather', '\"clear\"'::jsonb)",
    )
    _exec(
        db,
        "update public.campaign_runtime"
        " set save_in_progress = true, staging_generation = 1 where id = 1",
    )
    _exec(
        db,
        "insert into public.campaign_state_generations (generation, key, value)"
        " values (1, 'weather', '\"storm\"'::jsonb)",
    )
    # Publish: advance the pointer only. Historical rows are not touched.
    _exec(
        db,
        "update public.campaign_runtime"
        " set published_generation = 1, staging_generation = null,"
        "     save_in_progress = false, updated_at = now() where id = 1",
    )
    # New published view reflects generation 1.
    assert _rows(
        db, "select runtime_generation, value from public.campaign_state_runtime"
    ) == [(1, "storm")]
    # Generation 0 history is still intact in the store (not rewritten in place).
    assert (
        _scalar(
            db,
            "select value from public.campaign_state_generations"
            " where generation = 0 and key = 'weather'",
        )
        == "clear"
    )


def test_staging_generation_must_advance_beyond_published(db):
    # A staging generation at or below the published one violates the floor.
    with pytest.raises(psycopg2.errors.CheckViolation):
        _exec(
            db,
            "update public.campaign_runtime set staging_generation = 0 where id = 1",
        )
    with pytest.raises(psycopg2.errors.CheckViolation):
        _exec(
            db,
            "update public.campaign_runtime"
            " set published_generation = 5, staging_generation = 5 where id = 1",
        )


# ---------------------------------------------------------------------------
# WIN 7 — clean RHC schema: no legacy Mission10 mirror / domain machinery
# ---------------------------------------------------------------------------
def test_no_legacy_campaign_state_mirror(db):
    assert (
        _scalar(
            db,
            "select to_regclass('public.campaign_state')",
        )
        is None
    ), "clean RHC floor must not carry Mission10's legacy campaign_state mirror"


@pytest.mark.parametrize(
    "unwanted",
    [
        "entity_registry",
        "entity_knowledge",
        "entity_knowledge_runtime",
    ],
)
def test_no_mission10_domain_machinery(db, unwanted):
    assert _scalar(db, "select to_regclass(%s)", (f"public.{unwanted}",)) is None


# ---------------------------------------------------------------------------
# WIN 8 — inert floor: no gateway / mutation / read-facade behavior was built
# ---------------------------------------------------------------------------
def test_floor_defines_no_functions(db):
    # A structural floor must ship no routines (no Save Gateway, no dm_runtime
    # facade, no publication procedures).
    count = _scalar(
        db,
        """
        select count(*) from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
        """,
    )
    assert count == 0


@pytest.mark.parametrize(
    "gateway_fn",
    [
        "begin_campaign_save",
        "stage_campaign_state",
        "delete_staged_campaign_state",
        "publish_campaign_save",
        "abort_campaign_save",
        "dm_runtime_lookup",
    ],
)
def test_no_save_gateway_or_read_facade(db, gateway_fn):
    exists = _scalar(
        db,
        """
        select exists(
          select 1 from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
          where n.nspname = 'public' and p.proname = %s
        )
        """,
        (gateway_fn,),
    )
    assert exists is False, f"{gateway_fn} belongs to a later gate, not RT01-A"


def test_floor_defines_only_expected_relations(db):
    relations = {
        (name, kind)
        for name, kind in _rows(
            db,
            """
            select c.relname, c.relkind
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind in ('r', 'v')
            """,
        )
    }
    assert relations == {
        ("campaign_runtime", "r"),
        ("campaign_state_generations", "r"),
        ("campaign_state_runtime", "v"),
    }


# ---------------------------------------------------------------------------
# Real Postgres RLS / privilege proof (defense-in-depth for the floor)
# ---------------------------------------------------------------------------
def test_rls_is_enabled_on_floor_tables(db):
    for table in ("campaign_runtime", "campaign_state_generations"):
        assert (
            _scalar(
                db,
                "select relrowsecurity from pg_class where oid = %s::regclass",
                (f"public.{table}",),
            )
            is True
        ), f"RLS must be enabled on {table}"


def test_published_view_is_security_invoker(db):
    opts = _scalar(
        db,
        "select reloptions from pg_class where oid = 'public.campaign_state_runtime'::regclass",
    )
    assert opts is not None and "security_invoker=true" in opts


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_anon_and_authenticated_cannot_read_runtime_state(db, role):
    with db.cursor() as cur:
        cur.execute(f"set role {role}")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("select * from public.campaign_state_generations")
        finally:
            cur.execute("reset role")


def test_service_role_can_read_runtime_state(db):
    _exec(
        db,
        "insert into public.campaign_state_generations (generation, key, value)"
        " values (0, 'weather', '\"clear\"'::jsonb)",
    )
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            cur.execute("select count(*) from public.campaign_state_runtime")
            assert cur.fetchone()[0] == 1
        finally:
            cur.execute("reset role")
