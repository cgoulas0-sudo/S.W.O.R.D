"""RT01-B — real-PostgreSQL proof that the DATABASE owns publication identity.

WIN 9 (no caller-self-certified checkpoint identity), WIN 11 (RT01-C external-Git
boundary stays out of this gate), WIN 12 (one gateway family, no second
persistence model), and the primary PR #24 lessons.
"""

import psycopg2
import pytest

from gateway_util import begin_save, break_glass, exec_, rows, scalar


GATEWAY_PUBLIC_API = {
    "begin_campaign_save",
    "stage_campaign_state",
    "delete_staged_campaign_state",
    "abort_campaign_save",
    "publish_campaign_save",
}
GATEWAY_INTERNAL = {
    "_rhc_require_active_save",
    "_rhc_guard_runtime_owned_dml",
    "_rhc_guard_runtime_owned_truncate",
}


def _args(db, proname):
    return scalar(
        db,
        """
        select pg_get_function_arguments(p.oid)
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname = %s
        """,
        (proname,),
    )


# ---------------------------------------------------------------------------
# WIN 9 — caller cannot choose the generation
# ---------------------------------------------------------------------------
def test_caller_cannot_choose_generation(db):
    # BEGIN accepts only a TTL; there is no generation input anywhere.
    assert _args(db, "begin_campaign_save").strip() == "p_ttl_minutes integer DEFAULT 30"
    assert _args(db, "publish_campaign_save").strip() == "p_lock_token text"
    ctx = begin_save(db)
    assert ctx["staging"] == ctx["published"] + 1


# ---------------------------------------------------------------------------
# WIN 9 / PR #24 lesson 1 — caller cannot inject authoritative Git/hash identity
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("proname", sorted(GATEWAY_PUBLIC_API))
def test_no_gateway_function_accepts_git_or_hash_identity(db, proname):
    args = _args(db, proname).lower()
    for banned in ("git", "sha", "hash", "checkpoint", "ref"):
        assert banned not in args, f"{proname} must not accept caller '{banned}' identity"


def test_publish_does_not_retain_prior_generation_git_ref(db):
    # Break-glass a Git ref onto the published gen 0 (simulating a pinned floor).
    break_glass(
        db,
        "update public.campaign_runtime set published_git_ref = %s where id = 1",
        ("b127a513fade13d4f4bf5ec4df8069d48b88283c",),
    )
    assert scalar(db, "select published_git_ref from public.campaign_runtime") is not None

    # Publishing a new SQL generation must NOT carry the prior SHA forward and must
    # NOT fabricate a new one: RT01-B establishes no external Git proof.
    ctx = begin_save(db)
    exec_(db, "select public.stage_campaign_state(%s, 'k', '1'::jsonb)", (ctx["token"],))
    exec_(db, "select public.publish_campaign_save(%s)", (ctx["token"],))
    assert scalar(db, "select published_generation from public.campaign_runtime") == 1
    assert scalar(db, "select published_git_ref from public.campaign_runtime") is None


# ---------------------------------------------------------------------------
# WIN 9 / PR #24 lesson 2 — identity is derived inside the locked transaction
# ---------------------------------------------------------------------------
def test_publish_revalidates_next_generation_invariant(db):
    # The next-generation invariant is enforced in the publishing transaction
    # itself (not trusted from an earlier read). Corrupt the staging pointer via
    # break-glass so it is no longer published + 1, then prove publish refuses.
    ctx = begin_save(db)  # published 0, staging 1
    exec_(db, "select public.stage_campaign_state(%s, 'k', '1'::jsonb)", (ctx["token"],))
    # Jump staging to 5 (still > published, so RT01-A's floor check passes), which
    # is NOT published + 1.
    break_glass(db, "update public.campaign_runtime set staging_generation = 5 where id = 1")
    with pytest.raises(psycopg2.errors.RaiseException, match="not the next generation"):
        exec_(db, "select public.publish_campaign_save(%s)", (ctx["token"],))
    assert scalar(db, "select published_generation from public.campaign_runtime") == 0


# ---------------------------------------------------------------------------
# WIN 11 — RT01-C external-Git surface is genuinely absent
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "absent_fn",
    [
        "confirm_runtime_published_mirror",
        "dm_runtime_lookup",
        "engineering_release",
    ],
)
def test_no_rt01c_or_rt01d_function_surface(db, absent_fn):
    assert (
        scalar(
            db,
            "select exists(select 1 from pg_proc p join pg_namespace n"
            " on n.oid = p.pronamespace where n.nspname='public' and p.proname=%s)",
            (absent_fn,),
        )
        is False
    )


def test_no_mirror_confirmation_columns(db):
    cols = {
        c
        for (c,) in rows(
            db,
            "select column_name from information_schema.columns"
            " where table_schema='public' and table_name='campaign_runtime'",
        )
    }
    for absent in ("runtime_published_confirmed", "runtime_published_confirmed_at", "staging_branch"):
        assert absent not in cols, f"{absent} is RT01-C mirror state, not RT01-B"


# ---------------------------------------------------------------------------
# WIN 12 — exactly one gateway family; no second persistence model / no baggage
# ---------------------------------------------------------------------------
def test_public_schema_functions_are_exactly_the_gateway_family(db):
    present = {
        name
        for (name,) in rows(
            db,
            "select p.proname from pg_proc p join pg_namespace n"
            " on n.oid = p.pronamespace where n.nspname='public'",
        )
    }
    assert present == GATEWAY_PUBLIC_API | GATEWAY_INTERNAL


@pytest.mark.parametrize(
    "baggage",
    ["campaign_state", "entity_knowledge", "entity_registry", "entity_knowledge_runtime"],
)
def test_no_mission10_domain_baggage(db, baggage):
    assert scalar(db, "select to_regclass(%s)", (f"public.{baggage}",)) is None


def test_no_staging_procedure_allowlist_column(db):
    # Mission10's domain procedure allowlist must NOT be ported.
    assert (
        scalar(
            db,
            "select exists(select 1 from information_schema.columns"
            " where table_schema='public' and table_name='campaign_runtime'"
            " and column_name='staging_procedure')",
        )
        is False
    )
