"""EV2-10 owner-local inventory ownership proof.

Runs against real PostgreSQL 15 with the full RT01-A/B/C/D + RT02 + RT03 + RT04 +
HWB-02 spine plus the forward-only EV2-10 migration. All durable mutation goes
through the real save/publication/mirror-confirmation spine; nothing is mocked.

Proof Matrix coverage:
  * ordinary entries require non-blank name/description + explicit quantity >= 1;
  * zero/negative/fractional/missing quantity fails closed;
  * currency is exactly cp/sp/ep/gp/pp, non-negative integers, structurally
    separate from ordinary entries; invented denominations/negative/fractional
    fail, zero balances are coherent;
  * known-empty inventory and owned assets are representable without taxonomy;
  * Party stash uses the same owner-local model;
  * ordinary inventory mints no persistent `item:` identity;
  * MAINRUN-or-one-RUN controller law against authoritative published Run truth;
  * stale/parked/historical Runs, two-Run claims and malformed published Run
    batches fail closed rather than falling through to MAINRUN;
  * same-save Run-ownership changes and inventory mutations are mutually
    exclusive across every Run-writing doorway — generic stage/delete and the
    dedicated RT04 reconciliation route — so a former controller cannot publish
    a stale inventory update, and closure keys on the explicit inventory-staging
    operation fact rather than on final value equality (a value-equal replay or a
    mutate-away-and-back still closes every doorway);
  * duplicate authoritative published Run identities fail closed before any
    inventory controller is authorized;
  * mathematical integer semantics match the owning schema, so quantity/currency
    `1` and `1.0` agree while non-integral values fail;
  * duplicate ordinary entries are rejected under JSON numeric equality, so
    `quantity: 1` and `quantity: 1.0` cannot both be stored;
  * an explicit `currency: null` fails closed while an omitted currency stays
    coherent;
  * an explicit structurally valid controller assertion is required before any
    authority branch: `controller.kind` must be a JSON string exactly `mainrun`
    or `run`, so null/missing/non-string/unknown kinds fail closed and can never
    fall through to MAINRUN;
  * duplicate ordinary entries and non-string entry text are rejected at runtime
    exactly as the owning schema requires;
  * generic SAVE stage/delete stays fail-closed for the engine-owned inventory
    key; all-or-nothing publication via the existing RT01 spine.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "rt04"))
import rt04_util as u  # noqa: E402


HERO = "character:test-hero"
PARTY = "party:test-stash"


# ---------------------------------------------------------------------------
# Harness helpers
# ---------------------------------------------------------------------------

def _run_as_service(db, fn):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            return fn(cur)
        finally:
            cur.execute("reset role")


def _error_as_service(db, fn):
    with db.cursor() as cur:
        cur.execute("set role service_role")
        try:
            fn(cur)
        except Exception as exc:  # noqa: BLE001 - fail-closed proof
            cur.execute("reset role")
            return str(exc)
        cur.execute("reset role")
    raise AssertionError("expected the statement to fail closed")


def _mutate(db, token, request):
    def call(cur):
        cur.execute(
            "select public.mutate_owner_inventory(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as_service(db, call)
    return json.loads(value) if isinstance(value, str) else value


def _mutate_error(db, token, request):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.mutate_owner_inventory(%s, %s::jsonb)",
            (token, json.dumps(request)),
        ),
    )


def _stage_error(db, token, key, value):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.stage_campaign_state(%s, %s, %s::jsonb)",
            (token, key, json.dumps(value)),
        ),
    )


def _delete_error(db, token, key):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.delete_staged_campaign_state(%s, %s)", (token, key)
        ),
    )


def _reconcile(db, token, request):
    def call(cur):
        cur.execute(
            "select public.reconcile_run_resolution(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as_service(db, call)
    return json.loads(value) if isinstance(value, str) else value


def _reconcile_error(db, token, request):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.reconcile_run_resolution(%s, %s::jsonb)",
            (token, json.dumps(request)),
        ),
    )


def _published_inventory(db):
    return u.published_state(db).get("inventory") or []


def _staged_inventory(db):
    value = u.scalar(
        db,
        "select csg.value from public.campaign_state_generations csg "
        "join public.campaign_runtime cr on cr.id = 1 "
        "and csg.generation = cr.staging_generation and csg.key = 'inventory'",
    )
    return value or []


def _known(entries=None, currency=None):
    inventory = {"status": "known", "entries": entries if entries is not None else []}
    if currency is not None:
        inventory["currency"] = currency
    return inventory


def _request(owner=HERO, controller=None, inventory=None):
    return {
        "owner_entity_id": owner,
        "controller": {"kind": "mainrun"} if controller is None else controller,
        "inventory": _known() if inventory is None else inventory,
    }


# ---------------------------------------------------------------------------
# Happy path + owner locality
# ---------------------------------------------------------------------------

def test_mainrun_mutation_publishes_owner_local_inventory(db):
    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(
        db,
        token,
        _request(
            inventory=_known(
                entries=[
                    {"name": "Rope", "description": "Fifty feet of hempen rope.", "quantity": 2},
                    {"name": "Draft horse", "description": "An owned mount.", "quantity": 1},
                ],
                currency={"cp": 12, "gp": 30},
            )
        ),
    )

    assert result["owner_entity_id"] == HERO
    assert result["inventory"]["entity_id"] == HERO
    # Staging is invisible until the existing publication handshake completes.
    assert _published_inventory(db) == []

    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_inventory(db)
    assert len(records) == 1
    assert records[0]["entity_id"] == HERO
    assert records[0]["currency"] == {"cp": 12, "gp": 30}
    assert {e["name"] for e in records[0]["entries"]} == {"Rope", "Draft horse"}


def test_party_stash_uses_the_same_owner_local_model(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _request(
            owner=PARTY,
            inventory=_known(
                entries=[
                    {"name": "Shared strongbox", "description": "A party-owned chest.", "quantity": 1}
                ],
                currency={"gp": 500},
            ),
        ),
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    records = _published_inventory(db)
    assert [r["entity_id"] for r in records] == [PARTY]
    assert records[0]["entries"][0]["name"] == "Shared strongbox"


def test_owned_asset_is_an_ordinary_entry_without_taxonomy(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _request(
            inventory=_known(
                entries=[
                    {"name": "Sailing ship", "description": "An owned vessel.", "quantity": 1},
                    {"name": "Cart", "description": "An owned cart.", "quantity": 3},
                ]
            )
        ),
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    names = {e["name"] for e in _published_inventory(db)[0]["entries"]}
    assert names == {"Sailing ship", "Cart"}


def test_ordinary_inventory_mints_no_item_identity(db):
    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(
        db,
        token,
        _request(
            inventory=_known(
                entries=[
                    {
                        "name": "Old map",
                        "description": "A hand-drawn map of the northern ridge.",
                        "quantity": 1,
                    }
                ]
            )
        ),
    )

    assert "item:" not in json.dumps(result)
    # An entry that tries to attach persistent identity is outside the contract.
    err = _mutate_error(
        db,
        token,
        _request(
            inventory=_known(
                entries=[
                    {
                        "name": "Old map",
                        "description": "A hand-drawn map.",
                        "quantity": 1,
                        "item_id": "item:northern-map",
                    }
                ]
            )
        ),
    )
    assert "outside the EV2-10 contract" in err


def test_known_empty_inventory_with_zero_currency_is_coherent(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _request(inventory=_known(entries=[], currency={"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0})),
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    record = _published_inventory(db)[0]
    assert record["entries"] == []
    assert record["currency"] == {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0}


# ---------------------------------------------------------------------------
# Controller law (authoritative published Run truth only)
# ---------------------------------------------------------------------------

def test_run_controller_accepted_when_published_run_claims_owner(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(
        db,
        token,
        _request(controller={"kind": "run", "run_id": "R01"}, inventory=_known(currency={"gp": 7})),
    )

    assert result["controller"] == {"kind": "run", "run_id": "R01"}


def test_mainrun_rejected_while_published_run_claims_owner(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))

    assert "MAINRUN" in err
    assert "R01" in err


def test_run_controller_rejected_without_any_published_claim(db):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": "R01"}))

    assert "no published Run" in err


def test_run_controller_rejected_when_a_different_run_owns_owner(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": "R02"}))

    assert "R01" in err and "R02" in err


def test_stale_parked_run_cannot_overwrite_after_ownership_moved(db):
    # R01 is now parked and no longer claims the owner: historical presence is
    # not mutation authority.
    u.publish_confirmed_runs(
        db,
        [u.run(run_id="R01", control_state="parked", mutable_owner_entity_ids=[])],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    assert "no published Run" in err

    # MAINRUN is now the controller and may author.
    _mutate(db, token, _request(controller={"kind": "mainrun"}, inventory=_known(currency={"gp": 1})))


def test_two_runs_claiming_one_owner_fail_closed(db):
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[HERO]),
            u.run(run_id="R02", mutable_owner_entity_ids=[HERO]),
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    for run_id in ("R01", "R02"):
        err = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": run_id}))
        assert "more than one published Run" in err


# ---------------------------------------------------------------------------
# Payload law
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "entry",
    [
        {"name": "Torch", "description": "A burning torch.", "quantity": 0},
        {"name": "Torch", "description": "A burning torch.", "quantity": -1},
        {"name": "Torch", "description": "A burning torch.", "quantity": 1.5},
        {"name": "Torch", "description": "A burning torch.", "quantity": "3"},
        {"name": "Torch", "description": "A burning torch."},
        {"name": "   ", "description": "A burning torch.", "quantity": 1},
        {"name": "Torch", "description": "   ", "quantity": 1},
    ],
)
def test_invalid_entry_payload_fails_closed(db, entry):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(inventory=_known(entries=[entry])))
    assert "inventory entry" in err


@pytest.mark.parametrize(
    "currency",
    [
        {"gp": -1},
        {"gp": 1.5},
        {"gp": "5"},
        {"silver": 5},
    ],
)
def test_invalid_currency_fails_closed(db, currency):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(inventory=_known(currency=currency)))
    assert "currency" in err


def test_known_inventory_requires_entries(db):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(inventory={"status": "known"}))
    assert "entries" in err


def test_non_known_status_forbids_entries_and_currency(db):
    _published, _staging, token, _expires = u.begin_save(db)

    err_entries = _mutate_error(
        db,
        token,
        _request(inventory={"status": "unknown", "entries": []}),
    )
    assert "forbidden" in err_entries

    err_currency = _mutate_error(
        db,
        token,
        _request(inventory={"status": "not_applicable", "currency": {"gp": 1}}),
    )
    assert "forbidden" in err_currency


# ---------------------------------------------------------------------------
# Request boundary
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "owner",
    ["creature:test-hero", "location:tavern", "character:Bad-Slug", "character:", "party:stash!"],
)
def test_owner_must_be_a_character_or_party_identity(db, owner):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(owner=owner))
    assert "owner_entity_id" in err


@pytest.mark.parametrize(
    "controller",
    [
        {"kind": "nonsense"},
        {"kind": "run"},
        {"kind": "run", "run_id": "R01", "extra": 1},
        {"kind": "run", "run_id": "R1"},
        {"kind": "mainrun", "run_id": "R01"},
        {"run_id": "R01"},
    ],
)
def test_controller_shape_is_bounded(db, controller):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller=controller))
    assert "controller" in err


@pytest.mark.parametrize(
    "controller",
    [
        {"kind": None},
        {"kind": True},
        {"kind": 1},
        {"kind": ["mainrun"]},
        {"kind": {"value": "mainrun"}},
        {"kind": "MainRun"},
        {"kind": "MAINRUN"},
        {},
    ],
)
def test_controller_kind_must_be_an_explicit_valid_string(db, controller):
    """`controller.kind` must be a JSON string exactly `mainrun` or `run`. A
    null/non-string/unknown kind must fail closed here rather than slip past a
    three-valued-logic `NOT IN` check and fall through to MAINRUN."""
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller=controller))
    assert "controller" in err


def test_null_controller_kind_cannot_fall_through_to_mainrun(db):
    """Regression for the round-5 P1: `{"kind": null}` previously evaluated
    `v_kind NOT IN (...)` to SQL NULL and could reach the MAINRUN branch. It must
    fail closed with nothing staged."""
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": None}))
    assert "controller" in err
    assert _staged_inventory(db) == []


def test_valid_mainrun_and_run_controller_kinds_still_authorize(db):
    """The strict kind validation must not reject the two valid assertions."""
    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(db, token, _request(controller={"kind": "mainrun"}))
    assert result["controller"] == {"kind": "mainrun"}

    u.publish(db, token)
    u.confirm_mirror(db)

    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])
    _published, _staging, token, _expires = u.begin_save(db)
    result = _mutate(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    assert result["controller"] == {"kind": "run", "run_id": "R01"}


def test_request_rejects_fields_outside_the_contract(db):
    _published, _staging, token, _expires = u.begin_save(db)
    request = _request()
    request["extra"] = True
    err = _mutate_error(db, token, request)
    assert "outside the EV2-10 contract" in err


def test_mutation_requires_an_active_campaign_save(db):
    err = _mutate_error(db, "not-a-real-token", _request())
    assert "lock" in err.lower()


# ---------------------------------------------------------------------------
# Existing SAVE-authority composition + all-or-nothing
# ---------------------------------------------------------------------------

def test_generic_save_cannot_write_or_delete_the_inventory_key(db):
    _published, _staging, token, _expires = u.begin_save(db)

    err_stage = _stage_error(db, token, "inventory", _known())
    assert "mutate_owner_inventory" in err_stage

    err_delete = _delete_error(db, token, "inventory")
    assert "inventory" in err_delete

    err_unknown = _stage_error(db, token, "totally_new_key", {"x": 1})
    assert "not allowed" in err_unknown


def test_existing_generic_allowed_keys_still_work_after_ev210(db):
    _published, _staging, token, _expires = u.begin_save(db)
    u.stage(db, token, "live_status", {"scene": "workshop"})
    u.stage(db, token, "runs", [u.run(run_id="R01")])
    u.publish(db, token)
    u.confirm_mirror(db)

    assert u.published_state(db).get("live_status") == {"scene": "workshop"}


def test_abort_discards_unpublished_inventory(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(inventory=_known(currency={"gp": 9})))
    u.abort_save(db, token)

    assert _published_inventory(db) == []


def test_mutation_is_absolute_and_replay_safe(db):
    _published, _staging, token, _expires = u.begin_save(db)
    request = _request(
        inventory=_known(
            entries=[{"name": "Rope", "description": "Hemp rope.", "quantity": 2}],
            currency={"gp": 5},
        )
    )
    _mutate(db, token, request)
    _mutate(db, token, request)
    u.publish(db, token)
    u.confirm_mirror(db)

    record = _published_inventory(db)[0]
    assert record["entries"] == [
        {"name": "Rope", "description": "Hemp rope.", "quantity": 2}
    ]
    assert record["currency"] == {"gp": 5}


# ---------------------------------------------------------------------------
# Codex round-1 repair: fail-closed controller integrity
# ---------------------------------------------------------------------------

def test_parked_run_claiming_owner_fails_closed_for_run_and_mainrun(db):
    """A parked played Run that still lists the owner is not a current
    controller. It must not be granted authority, and its claim means MAINRUN is
    not provably the controller either, so both assertions fail closed."""
    u.publish_confirmed_runs(
        db,
        [u.run(run_id="R01", control_state="parked", mutable_owner_entity_ids=[HERO])],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err_run = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    assert "parked" in err_run

    err_mainrun = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "parked" in err_mainrun


def test_malformed_published_run_entry_fails_closed_not_mainrun(db):
    """An authoritative `runs` entry carrying mutable ownership but no string
    run_id must not be skipped, because skipping the possible claim would return
    NULL and unsafely authorize MAINRUN."""
    malformed = {
        "execution_mode": "played",
        "control_state": "active",
        "scenario_id": "S01",
        "occurred_encounter_ids": [],
        "participant_entity_ids": [HERO],
        "mutable_owner_entity_ids": [HERO],
        "location_ids": [],
        "campaign_anchor": {
            "base_commit": u.RUN_ANCHOR,
            "campaign_time": "Day 1, evening",
        },
    }
    u.publish_confirmed_runs(db, [malformed])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "run_id" in err or "unreadable" in err


def test_non_object_published_run_entry_fails_closed(db):
    u.publish_confirmed_runs(db, ["not-a-run-record"])

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "non-object" in err


def test_same_save_runs_handoff_cannot_be_used_by_former_controller(db):
    """Inventory authority is proven against published Run truth. A same-save
    staged ownership handoff must make the mutation fail closed so a former
    controller cannot publish a stale inventory update."""
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    # Stage a same-save handoff that releases the hero from the claiming Run.
    u.stage(
        db,
        token,
        "runs",
        [u.run(run_id="R01", control_state="parked", mutable_owner_entity_ids=[])],
    )

    err_run = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    assert "runs" in err_run

    # MAINRUN is not provably the controller either once this save is changing
    # Run ownership, so the guard is asserted-kind-independent.
    err_mainrun = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "runs" in err_mainrun


def test_generic_runs_change_is_refused_once_inventory_is_staged(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, _request(inventory=_known(currency={"gp": 1})))

    err_stage = _stage_error(db, token, "runs", [u.run(run_id="R01")])
    assert "runs" in err_stage

    err_delete = _delete_error(db, token, "runs")
    assert "runs" in err_delete

    # Unrelated ordinary-save keys remain stageable in the same save.
    u.stage(db, token, "live_status", {"scene": "workshop"})


def test_reconcile_is_refused_once_inventory_is_staged_in_same_save(db):
    """The dedicated RT04 route writes `runs` with a direct INSERT, so it must
    enforce the same same-save inventory coupling as the generic closure."""
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _request(controller={"kind": "run", "run_id": "R01"}, inventory=_known(currency={"gp": 1})),
    )

    request = u.request(u.resolution(run_id="R01"), released=[HERO])
    err = _reconcile_error(db, token, request)
    assert "inventory" in err


def test_inventory_mutation_is_refused_after_reconcile_in_same_save(db):
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    request = u.request(u.resolution(run_id="R01"), released=[HERO])
    _reconcile(db, token, request)

    err = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    assert "runs" in err


def test_duplicate_ordinary_entries_fail_closed_at_runtime(db):
    _published, _staging, token, _expires = u.begin_save(db)
    entry = {"name": "Torch", "description": "A burning torch.", "quantity": 2}
    err = _mutate_error(db, token, _request(inventory=_known(entries=[entry, entry])))
    assert "unique" in err.lower()


def test_duplicate_entries_differing_only_by_integral_spelling_are_rejected(db):
    """Draft 2020-12 item equality is JSON numeric equality, so `quantity: 1` and
    `quantity: 1.0` are the SAME ordinary entry. Runtime duplicate detection must
    compare canonical JSONB values, not text serialization, or a numerically
    equal pair could double-count."""
    _published, _staging, token, _expires = u.begin_save(db)
    entries = [
        {"name": "Torch", "description": "A burning torch.", "quantity": 1},
        {"name": "Torch", "description": "A burning torch.", "quantity": 1.0},
    ]
    err = _mutate_error(db, token, _request(inventory=_known(entries=entries)))
    assert "unique" in err.lower()


def test_explicit_null_currency_fails_closed_but_omitted_currency_is_coherent(db):
    """An omitted `currency` is valid (the schema does not require it), but an
    explicit JSON `null` is not the same thing: when present, `currency` must be
    an object, so runtime must fail closed rather than silently dropping it."""
    _published, _staging, token, _expires = u.begin_save(db)

    inventory = _known()
    inventory["currency"] = None
    err = _mutate_error(db, token, _request(inventory=inventory))
    assert "currency" in err

    # Omitted currency still stages and publishes coherently.
    _mutate(db, token, _request(inventory=_known(entries=[], currency=None)))



@pytest.mark.parametrize("bad", [123, True, ["Torch"], {"value": "Torch"}])
@pytest.mark.parametrize("field", ["name", "description"])
def test_entry_text_must_be_a_json_string_at_runtime(db, field, bad):
    _published, _staging, token, _expires = u.begin_save(db)
    entry = {"name": "Torch", "description": "A burning torch.", "quantity": 1}
    entry[field] = bad
    err = _mutate_error(db, token, _request(inventory=_known(entries=[entry])))
    assert "inventory entry" in err


# ---------------------------------------------------------------------------
# Codex round-3 repair: operation-fact staging, duplicate Run identity, and
# schema-aligned integer semantics
# ---------------------------------------------------------------------------

def test_mathematically_integral_quantity_and_currency_are_accepted(db):
    """Draft 2020-12 `type: integer` accepts a mathematically integral number, so
    the runtime doorway must accept `1.0` exactly like `1` and not key on a
    digits-only spelling. Non-integral values (proved elsewhere) still fail."""
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _request(
            inventory=_known(
                entries=[
                    {"name": "Torch", "description": "A burning torch.", "quantity": 1.0}
                ],
                currency={"gp": 2.0, "cp": 0.0},
            )
        ),
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    record = _published_inventory(db)[0]
    assert record["entries"][0]["quantity"] == 1
    assert record["currency"] == {"gp": 2, "cp": 0}


@pytest.mark.parametrize("bad", [1.25, 2.5, 0.5])
def test_non_integral_quantity_still_fails_closed(db, bad):
    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(
        db,
        token,
        _request(
            inventory=_known(
                entries=[{"name": "Torch", "description": "A burning torch.", "quantity": bad}]
            )
        ),
    )
    assert "inventory entry" in err


def test_duplicate_published_run_identity_fails_closed_before_authority(db):
    """Two valid published records sharing one `run_id` make inventory authority
    ambiguous even when only one of them lists the requested owner. It must fail
    closed before any controller is authorized, matching the canonical RT03
    reader's refusal to resolve a duplicated identity."""
    u.publish_confirmed_runs(
        db,
        [
            u.run(run_id="R01", mutable_owner_entity_ids=[HERO]),
            u.run(
                run_id="R01",
                participant_entity_ids=["character:other-hero"],
                mutable_owner_entity_ids=["character:other-hero"],
            ),
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    err = _mutate_error(db, token, _request(controller={"kind": "mainrun"}))
    assert "duplicate authoritative Run identity" in err

    err_run = _mutate_error(db, token, _request(controller={"kind": "run", "run_id": "R01"}))
    assert "duplicate authoritative Run identity" in err_run


def test_value_equal_inventory_replay_still_closes_runs_doorways(db):
    """A successful inventory staging operation is an operation fact. Re-staging
    the exact published absolute target leaves the final value byte-equal to
    published reality, yet every Run-ownership-writing doorway must still fail
    closed for the rest of that save."""
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    request = _request(
        controller={"kind": "run", "run_id": "R01"},
        inventory=_known(currency={"gp": 5}),
    )
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, request)
    u.publish(db, token)
    u.confirm_mirror(db)

    # New save: stage the identical absolute target again, so final inventory is
    # value-equal to published. Final-value equality alone would look unchanged.
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, request)
    assert _staged_inventory(db) == _published_inventory(db)

    err_stage = _stage_error(
        db,
        token,
        "runs",
        [u.run(run_id="R01", control_state="parked", mutable_owner_entity_ids=[])],
    )
    assert "runs" in err_stage

    err_delete = _delete_error(db, token, "runs")
    assert "runs" in err_delete

    err_reconcile = _reconcile_error(
        db, token, u.request(u.resolution(run_id="R01"), released=[HERO])
    )
    assert "inventory" in err_reconcile


def test_mutate_away_and_back_still_closes_runs_doorways(db):
    """Mutating inventory away and then back to the published value still counts
    as a staging operation, so Run-ownership writes remain closed."""
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    canonical = _request(
        controller={"kind": "run", "run_id": "R01"},
        inventory=_known(currency={"gp": 5}),
    )
    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(db, token, canonical)
    u.publish(db, token)
    u.confirm_mirror(db)

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _request(controller={"kind": "run", "run_id": "R01"}, inventory=_known(currency={"gp": 0})),
    )
    _mutate(db, token, canonical)
    assert _staged_inventory(db) == _published_inventory(db)

    err_stage = _stage_error(db, token, "runs", [u.run(run_id="R01")])
    assert "runs" in err_stage


def test_inventory_staging_marker_does_not_leak_into_a_later_save(db):
    """The staging operation fact is bound to the save's own database-minted
    lock_token, so a prior save's inventory mutation must not block a later
    save's legitimate Run reconciliation."""
    u.publish_confirmed_runs(db, [u.run(run_id="R01", mutable_owner_entity_ids=[HERO])])

    _published, _staging, token, _expires = u.begin_save(db)
    _mutate(
        db,
        token,
        _request(controller={"kind": "run", "run_id": "R01"}, inventory=_known(currency={"gp": 1})),
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    _published, _staging, token, _expires = u.begin_save(db)
    result = _reconcile(db, token, u.request(u.resolution(run_id="R01"), released=[HERO]))
    assert result["run_id"] == "R01"
