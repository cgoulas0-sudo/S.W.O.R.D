"""EV2-13.420 Temporal Core proof (Proof Matrix, all required cases).

The temporal core is a pure deterministic contract: exact mechanical-duration
conversion among second/round/minute/hour/day plus a narrow whole-minute RT02
bridge. These tests run the real forward migration chain on real PostgreSQL and
prove the declared invariants, fail-closed behavior and the absence of new
persistent state or mutation authority.
"""

import pytest
import psycopg2

from conftest import FORWARD_MIGRATIONS, TEMPORAL_MIGRATION, install_chain


def convert(db, amount, from_unit, to_unit):
    with db.cursor() as cur:
        cur.execute(
            "select public.convert_mechanical_duration(%s::numeric, %s, %s)",
            (amount, from_unit, to_unit),
        )
        return cur.fetchone()[0]


def bridge(db, amount, unit):
    with db.cursor() as cur:
        cur.execute(
            "select public.mechanical_duration_to_campaign_minutes(%s::numeric, %s)",
            (amount, unit),
        )
        return cur.fetchone()[0]


def scalar(db, sql, params=None):
    with db.cursor() as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Architecture pin: round != turn, one round == six elapsed seconds
# ---------------------------------------------------------------------------

def test_round_maps_to_six_elapsed_seconds(db):
    assert convert(db, 1, "round", "second") == 6
    assert convert(db, 2, "round", "second") == 12


def test_turn_is_rejected_as_elapsed_duration_unit(db):
    with pytest.raises(psycopg2.errors.RaiseException, match="not an elapsed-duration unit"):
        convert(db, 1, "turn", "second")
    with pytest.raises(psycopg2.errors.RaiseException, match="not an elapsed-duration unit"):
        convert(db, 6, "second", "turn")
    with pytest.raises(psycopg2.errors.RaiseException, match="not an elapsed-duration unit"):
        bridge(db, 1, "turn")


# ---------------------------------------------------------------------------
# Exact canonical conversions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "amount,from_unit,to_unit,expected",
    [
        (1, "round", "second", 6),
        (10, "round", "minute", 1),
        (1, "minute", "round", 10),
        (1, "minute", "second", 60),
        (6, "second", "round", 1),
        (1, "hour", "minute", 60),
        (1, "hour", "second", 3600),
        (1, "day", "hour", 24),
        (1, "day", "minute", 1440),
        (1, "day", "second", 86400),
        (24, "hour", "day", 1),
        (1440, "minute", "day", 1),
    ],
)
def test_exact_canonical_conversions(db, amount, from_unit, to_unit, expected):
    assert convert(db, amount, from_unit, to_unit) == expected


def test_zero_duration_is_explicit_and_deterministic(db):
    assert convert(db, 0, "round", "minute") == 0
    assert convert(db, 0, "day", "second") == 0
    assert convert(db, 0, "second", "day") == 0
    assert bridge(db, 0, "round") == 0


# ---------------------------------------------------------------------------
# Fail-closed untrusted input
# ---------------------------------------------------------------------------

def test_negative_amount_fails_closed(db):
    with pytest.raises(psycopg2.errors.RaiseException, match="non-negative"):
        convert(db, -1, "round", "second")
    with pytest.raises(psycopg2.errors.RaiseException, match="non-negative"):
        bridge(db, -6, "second")


def test_null_inputs_fail_closed(db):
    with pytest.raises(psycopg2.errors.RaiseException, match="amount is required"):
        convert(db, None, "round", "second")
    with pytest.raises(psycopg2.errors.RaiseException, match="unit is required"):
        convert(db, 1, None, "second")
    with pytest.raises(psycopg2.errors.RaiseException, match="unit is required"):
        convert(db, 1, "second", None)
    with pytest.raises(psycopg2.errors.RaiseException, match="unit is required"):
        bridge(db, 1, None)


def test_unknown_unit_fails_closed(db):
    with pytest.raises(psycopg2.errors.RaiseException, match="unknown mechanical duration unit"):
        convert(db, 1, "fortnight", "second")
    with pytest.raises(psycopg2.errors.RaiseException, match="unknown mechanical duration unit"):
        convert(db, 1, "second", "fortnight")


def test_fractional_amount_fails_closed(db):
    with pytest.raises(psycopg2.errors.RaiseException, match="whole number of units"):
        convert(db, "1.5", "minute", "second")
    with pytest.raises(psycopg2.errors.RaiseException, match="whole number of units"):
        bridge(db, "2.5", "hour")


def test_non_whole_result_fails_closed(db):
    # 1 round is six seconds and cannot become a whole minute.
    with pytest.raises(psycopg2.errors.RaiseException, match="whole number of minute"):
        convert(db, 1, "round", "minute")
    with pytest.raises(psycopg2.errors.RaiseException, match="whole number of round"):
        convert(db, 7, "second", "round")


# ---------------------------------------------------------------------------
# RT02 whole-minute bridge
# ---------------------------------------------------------------------------

def test_bridge_accepts_exact_whole_minutes(db):
    assert bridge(db, 10, "round") == 1
    assert bridge(db, 1, "minute") == 1
    assert bridge(db, 60, "second") == 1
    assert bridge(db, 1, "hour") == 60
    assert bridge(db, 1, "day") == 1440


def test_bridge_rejects_sub_minute_duration(db):
    # One round (six seconds) must fail closed, never truncate to zero minutes.
    with pytest.raises(psycopg2.errors.RaiseException, match="whole number of minute"):
        bridge(db, 1, "round")
    with pytest.raises(psycopg2.errors.RaiseException, match="whole number of minute"):
        bridge(db, 7, "second")


# RT02 normalizes `elapsed_campaign_minutes` to a PostgreSQL integer (int4), so
# the bridge must accept exactly through 2147483647 and reject one above it.
RT02_MINUTES_MAX = 2147483647


def test_bridge_accepts_rt02_maximum_minutes(db):
    assert bridge(db, RT02_MINUTES_MAX, "minute") == RT02_MINUTES_MAX
    # The same boundary expressed as an exact whole-minute seconds duration.
    assert bridge(db, RT02_MINUTES_MAX * 60, "second") == RT02_MINUTES_MAX


def test_bridge_rejects_first_value_above_rt02_range(db):
    with pytest.raises(
        psycopg2.errors.RaiseException, match="RT02 elapsed_campaign_minutes range"
    ):
        bridge(db, RT02_MINUTES_MAX + 1, "minute")
    with pytest.raises(
        psycopg2.errors.RaiseException, match="RT02 elapsed_campaign_minutes range"
    ):
        bridge(db, (RT02_MINUTES_MAX + 1) * 60, "second")


def test_canonical_converter_is_not_rt02_bounded(db):
    # The canonical converter is the general primitive; only the RT02 bridge is
    # bounded. A whole-minute value above the RT02 integer ceiling is still a
    # valid exact conversion.
    assert convert(db, RT02_MINUTES_MAX + 1, "minute", "minute") == RT02_MINUTES_MAX + 1


# ---------------------------------------------------------------------------
# Wide arithmetic: wide intermediates must not reject representable final
# results; only the final result is range-checked
# ---------------------------------------------------------------------------

BIGINT_MAX = 9223372036854775807


def test_wide_valid_conversions_do_not_overflow(db):
    # Each result exceeds the 32-bit integer range but is a valid bigint result.
    assert convert(db, 1000000, "day", "second") == 86400000000
    assert convert(db, 1000000, "day", "minute") == 1440000000
    assert convert(db, 4000000000, "second", "second") == 4000000000
    assert convert(db, 4000000000, "minute", "minute") == 4000000000


def test_wide_intermediate_does_not_reject_representable_final(db):
    # Same-unit at the bigint ceiling: the seconds intermediate (bigint-max days
    # times 86400) is far larger than bigint, yet the requested result is exactly
    # representable and must succeed.
    assert convert(db, BIGINT_MAX, "day", "day") == BIGINT_MAX
    assert convert(db, BIGINT_MAX, "second", "second") == BIGINT_MAX
    assert convert(db, BIGINT_MAX, "minute", "minute") == BIGINT_MAX
    # Cross-unit: days -> minutes whose seconds intermediate (~5.5e20) is above
    # bigint but whose final minute result is representable.
    days = BIGINT_MAX // 1440
    assert convert(db, days, "day", "minute") == days * 1440


def test_out_of_range_final_results_fail_cleanly(db):
    with pytest.raises(psycopg2.errors.RaiseException, match="out of representable range"):
        convert(db, "1000000000000000", "day", "second")
    with pytest.raises(psycopg2.errors.RaiseException, match="out of representable range"):
        convert(db, "9223372036854775808", "second", "second")
    # A representable amount can still have an unrepresentable final result.
    with pytest.raises(psycopg2.errors.RaiseException, match="out of representable range"):
        convert(db, BIGINT_MAX, "day", "second")


# ---------------------------------------------------------------------------
# No new persistence / mutation authority
# ---------------------------------------------------------------------------

def _public_shape(db):
    with db.cursor() as cur:
        cur.execute(
            "select table_name from information_schema.tables "
            "where table_schema = 'public' order by table_name"
        )
        tables = [row[0] for row in cur.fetchall()]
        cur.execute(
            "select table_name, column_name from information_schema.columns "
            "where table_schema = 'public' order by table_name, column_name"
        )
        columns = [tuple(row) for row in cur.fetchall()]
        cur.execute(
            "select count(*) from pg_proc p "
            "join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'public'"
        )
        functions = cur.fetchone()[0]
    return tables, columns, functions


def test_temporal_migration_adds_no_persistent_state(db):
    pre_temporal = [m for m in FORWARD_MIGRATIONS if m != TEMPORAL_MIGRATION]
    install_chain(db, pre_temporal)
    tables_before, columns_before, functions_before = _public_shape(db)
    install_chain(db, FORWARD_MIGRATIONS)
    tables_after, columns_after, functions_after = _public_shape(db)

    assert tables_after == tables_before
    assert columns_after == columns_before
    # Exactly the three pure temporal-core functions are added.
    assert functions_after == functions_before + 3


def test_conversion_functions_are_pure_immutable(db):
    for name in (
        "_rhc_mechanical_unit_seconds",
        "convert_mechanical_duration",
        "mechanical_duration_to_campaign_minutes",
    ):
        assert scalar(
            db, "select provolatile from pg_proc where proname = %s", (name,)
        ) == "i"


def test_conversions_mutate_no_campaign_state(db):
    generation_before = scalar(
        db, "select count(*) from public.campaign_state_generations"
    )
    runtime_before = scalar(
        db,
        "select published_generation || ':' || save_in_progress "
        "from public.campaign_runtime where id = 1",
    )
    convert(db, 1, "round", "second")
    convert(db, 10, "round", "minute")
    bridge(db, 1, "day")
    generation_after = scalar(
        db, "select count(*) from public.campaign_state_generations"
    )
    runtime_after = scalar(
        db,
        "select published_generation || ':' || save_in_progress "
        "from public.campaign_runtime where id = 1",
    )
    assert generation_after == generation_before
    assert runtime_after == runtime_before


def test_temporal_functions_are_service_role_only(db):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            cur.execute(
                "select public.convert_mechanical_duration(1, 'round', 'second')"
            )
            assert cur.fetchone()[0] == 6
        finally:
            cur.execute("reset role")
    with db.cursor() as cur:
        cur.execute("set role authenticated")
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(
                    "select public.convert_mechanical_duration(1, 'round', 'second')"
                )
        finally:
            cur.execute("reset role")


# ---------------------------------------------------------------------------
# PostgreSQL 15 and PostgreSQL 17 both install and behave identically
# ---------------------------------------------------------------------------

def test_migration_installs_and_behaves_on_postgres_17(db_pg17):
    assert scalar(db_pg17, "select current_setting('server_version_num')::int") >= 170000
    assert scalar(
        db_pg17, "select public.convert_mechanical_duration(1, 'round', 'second')"
    ) == 6
    assert scalar(
        db_pg17,
        "select public.mechanical_duration_to_campaign_minutes(10, 'round')",
    ) == 1
    with pytest.raises(psycopg2.errors.RaiseException, match="whole number of minute"):
        bridge(db_pg17, 1, "round")