"""EV2-12.1 generalized persistent item identity admission runtime proof.

Runs against real PostgreSQL 15 with the full RT01-A/B/C/D + RT02 + RT03 + RT04 +
HWB-02 + EV2-10 + EV2-11 spine plus the forward-only EV2-12.1 migration. All
durable mutation goes through the real save/publication/mirror-confirmation
spine; nothing is mocked. No real RHC item is admitted: every admitted identity
is synthetic.

Proof Matrix coverage:
  * happy path: one authorized already-defined synthetic unique item is admitted
    through the reusable action and publishes identity + first custody + a
    bounded receipt atomically on the RT01 spine;
  * duplicate same-instance admission fails closed (published and same-save);
  * conflicting replay/receipt-without-custody fails closed;
  * malformed item ID / request / provenance / controller / custody actor fails
    closed before any staging;
  * name collision across distinct item IDs remains legal (identity is the
    `item:` id, never a name/type);
  * Unknown owner/holder are accepted when not established and never invented;
  * known owner/holder are accepted only when structurally valid and explicitly
    supplied;
  * provenance source/event is preserved when established; optional day stays
    optional and is never synthesized;
  * malformed/duplicate existing custody or receipt truth fails closed before
    staging;
  * complete existing and resulting cross-collection receipt-to-custody integrity
    is enforced before staging: an orphan admission receipt (receipt without a
    matching custody record for the same item_id) fails closed even when a
    different item is being admitted, while the forward-only pre-EV2-12.1 legacy
    exception (item:vampire custody without a receipt) stays allowed;
  * complete resulting collections are validated before publish;
  * generic gameplay custody mutation remains non-minting;
  * generic SAVE/stage/delete cannot bypass the admission action;
  * admission does not silently mutate ordinary inventory or unrelated state;
  * same-save composition with an already-authorized inventory mutation publishes
    all-or-nothing without weakening existing authority guards;
  * admission is replay/crash-safe: an aborted admission leaves no durable
    identity or receipt and retry converges on exactly one;
  * controller law: Run-asserted admission, MAINRUN rejection of a Run-controlled
    actor, nonexistent/parked Run assertions all fail closed;
  * same-save Run-ownership changes and admission are mutually exclusive;
  * the action is service-role-only and the migration installs cleanly.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "rt04"))
import rt04_util as u  # noqa: E402


HERO = "character:test-hero"
FANIS = "character:test-fanis"
PARTY = "party:test-stash"
BLADE = "item:test-blade"
BLADE_COPY = "item:test-blade-copy"
SHIELD = "item:test-shield"
HELM = "item:test-helm"
UNKNOWN_ITEM = "item:test-unknown"


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


def _admit(db, token, request):
    def call(cur):
        cur.execute(
            "select public.admit_item_identity(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as_service(db, call)
    return json.loads(value) if isinstance(value, str) else value


def _admit_error(db, token, request):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.admit_item_identity(%s, %s::jsonb)",
            (token, json.dumps(request)),
        ),
    )


def _custody_mutate(db, token, request):
    def call(cur):
        cur.execute(
            "select public.mutate_item_custody(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as_service(db, call)
    return json.loads(value) if isinstance(value, str) else value


def _custody_mutate_error(db, token, request):
    return _error_as_service(
        db,
        lambda cur: cur.execute(
            "select public.mutate_item_custody(%s, %s::jsonb)",
            (token, json.dumps(request)),
        ),
    )


def _inventory_mutate(db, token, request):
    def call(cur):
        cur.execute(
            "select public.mutate_owner_inventory(%s, %s::jsonb)",
            (token, json.dumps(request)),
        )
        return cur.fetchone()[0]

    value = _run_as_service(db, call)
    return json.loads(value) if isinstance(value, str) else value


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
            "select public.delete_staged_campaign_state(%s, %s)",
            (token, key),
        ),
    )


# ---------------------------------------------------------------------------
# State / request builders
# ---------------------------------------------------------------------------

def _provenance(source="DM declaration", event="session 12", campaign_day=7):
    return {"source": source, "event": event, "campaign_day": campaign_day}


def _request(
    item=BLADE,
    controller=None,
    provenance=None,
    owner=HERO,
    holder=HERO,
    include_owner=True,
    include_holder=True,
):
    request = {
        "item_id": item,
        "controller": {"kind": "mainrun"} if controller is None else controller,
        "provenance": _provenance() if provenance is None else provenance,
    }
    if include_owner:
        request["owner_entity_id"] = owner
    if include_holder:
        request["holder_entity_id"] = holder
    return request


def _receipt(item=BLADE, controller=None, provenance=None, generation=1):
    return {
        "item_id": item,
        "controller": {"kind": "mainrun"} if controller is None else controller,
        "provenance": (
            {"source": None, "event": None, "campaign_day": None}
            if provenance is None
            else provenance
        ),
        "admitted_generation": generation,
        "admission_version": 1,
    }


def _published_state(db):
    return u.published_state(db)


def _published_custody(db):
    return _published_state(db).get("item_custody") or []


def _published_admissions(db):
    return _published_state(db).get("item_admissions") or []


def _published_generation(db):
    return u.scalar(
        db, "select published_generation from public.campaign_runtime where id = 1"
    )


def _seed_published(db, key, value):
    u.break_glass(
        db,
        "insert into public.campaign_state_generations "
        "(generation, key, value, created_at, updated_at) "
        "select cr.published_generation, %s, %s::jsonb, now(), now() "
        "from public.campaign_runtime cr where cr.id = 1 "
        "on conflict (generation, key) do update "
        "set value = excluded.value, updated_at = now()",
        (key, json.dumps(value)),
    )


def _seed_published_custody(db, records):
    _seed_published(db, "item_custody", records)


def _seed_published_admissions(db, records):
    _seed_published(db, "item_admissions", records)


def _seed_published_runs(db, runs):
    _seed_published(db, "runs", runs)


def _admit_and_publish(db, request):
    _published, _staging, token, _expires = u.begin_save(db)
    result = _admit(db, token, request)
    u.publish(db, token)
    u.confirm_mirror(db)
    return result


# ---------------------------------------------------------------------------
# Happy path / receipt
# ---------------------------------------------------------------------------

def test_happy_path_admits_identity_custody_and_bounded_receipt(db):
    result = _admit_and_publish(db, _request())

    assert _published_custody(db) == [
        {"item_id": BLADE, "owner_entity_id": HERO, "holder_entity_id": HERO}
    ]
    receipts = _published_admissions(db)
    assert receipts == [
        {
            "item_id": BLADE,
            "controller": {"kind": "mainrun"},
            "provenance": {
                "source": "DM declaration",
                "event": "session 12",
                "campaign_day": 7,
            },
            "admitted_generation": 1,
            "admission_version": 1,
        }
    ]
    assert result["admission"] == receipts[0]
    assert result["admitted_generation"] == 1
    assert result["custody"] == _published_custody(db)[0]


def test_identity_custody_and_receipt_publish_in_one_generation(db):
    _published, staging, token, _expires = u.begin_save(db)
    _admit(db, token, _request())
    u.publish(db, token)
    u.confirm_mirror(db)

    assert staging == 1
    assert _published_generation(db) == 1
    assert _published_custody(db)
    assert _published_admissions(db)
    assert _published_admissions(db)[0]["admitted_generation"] == 1


def test_admission_preserves_unknown_provenance_and_never_synthesizes(db):
    _admit_and_publish(db, _request(provenance={}))

    assert _published_admissions(db)[0]["provenance"] == {
        "source": None,
        "event": None,
        "campaign_day": None,
    }


def test_partial_provenance_preserves_only_established_facts(db):
    _admit_and_publish(
        db, _request(provenance={"source": "campaign ledger", "campaign_day": 0})
    )

    assert _published_admissions(db)[0]["provenance"] == {
        "source": "campaign ledger",
        "event": None,
        "campaign_day": 0,
    }


# ---------------------------------------------------------------------------
# Unknown / known custody facts
# ---------------------------------------------------------------------------

def test_unknown_owner_and_holder_are_accepted_and_not_invented(db):
    _admit_and_publish(
        db, _request(include_owner=False, include_holder=False)
    )

    assert _published_custody(db) == [
        {"item_id": BLADE, "owner_entity_id": None, "holder_entity_id": None}
    ]


def test_unknown_owner_with_known_holder_mirrors_ev212(db):
    _admit_and_publish(db, _request(owner=None, holder=HERO))

    assert _published_custody(db) == [
        {"item_id": BLADE, "owner_entity_id": None, "holder_entity_id": HERO}
    ]


def test_party_owner_and_holder_are_structurally_valid(db):
    _admit_and_publish(db, _request(owner=PARTY, holder=PARTY))

    assert _published_custody(db) == [
        {"item_id": BLADE, "owner_entity_id": PARTY, "holder_entity_id": PARTY}
    ]


# ---------------------------------------------------------------------------
# Duplicate / conflict / replay
# ---------------------------------------------------------------------------

def test_duplicate_same_instance_after_publish_fails_closed(db):
    _admit_and_publish(db, _request())

    _published, _staging, token, _expires = u.begin_save(db)
    error = _admit_error(db, token, _request())

    assert "already has an admitted custody record" in error
    assert _published_generation(db) == 1
    assert len(_published_custody(db)) == 1
    assert len(_published_admissions(db)) == 1


def test_duplicate_same_instance_in_same_save_fails_closed(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _admit(db, token, _request())

    error = _admit_error(db, token, _request(owner=FANIS, holder=FANIS))

    assert "already has an admitted custody record" in error


def test_receipt_without_custody_conflict_fails_closed(db):
    _seed_published_admissions(db, [_receipt()])

    _published, _staging, token, _expires = u.begin_save(db)
    error = _admit_error(db, token, _request())

    assert "already has an admission receipt" in error
    assert _published_generation(db) == 0


def test_name_collision_across_distinct_item_ids_is_legal(db):
    _seed_published(db, "item_custody", [])

    _published, _staging, token, _expires = u.begin_save(db)
    _admit(db, token, _request(item=BLADE))
    _admit(db, token, _request(item=BLADE_COPY, owner=FANIS, holder=FANIS))
    u.publish(db, token)
    u.confirm_mirror(db)

    assert [r["item_id"] for r in _published_custody(db)] == [BLADE, BLADE_COPY]
    assert [r["item_id"] for r in _published_admissions(db)] == [BLADE, BLADE_COPY]


# ---------------------------------------------------------------------------
# Malformed requests (fail closed before staging)
# ---------------------------------------------------------------------------

MALFORMED_REQUESTS = [
    {},
    {"item_id": BLADE},
    {"item_id": BLADE, "controller": {"kind": "mainrun"}},
    {"item_id": "item:Blade", "controller": {"kind": "mainrun"}, "provenance": {}},
    {"item_id": "character:test-hero", "controller": {"kind": "mainrun"}, "provenance": {}},
    {"item_id": 5, "controller": {"kind": "mainrun"}, "provenance": {}},
    {"item_id": BLADE, "controller": None, "provenance": {}},
    {"item_id": BLADE, "controller": {}, "provenance": {}},
    {"item_id": BLADE, "controller": {"kind": "MAINRUN"}, "provenance": {}},
    {"item_id": BLADE, "controller": {"kind": None}, "provenance": {}},
    {"item_id": BLADE, "controller": {"kind": "run"}, "provenance": {}},
    {"item_id": BLADE, "controller": {"kind": "run", "run_id": "1"}, "provenance": {}},
    {"item_id": BLADE, "controller": {"kind": "mainrun", "run_id": "R01"}, "provenance": {}},
    {"item_id": BLADE, "controller": {"kind": "run", "run_id": "R01", "x": 1}, "provenance": {}},
    {"item_id": BLADE, "controller": {"kind": "mainrun"}, "provenance": "x"},
    {"item_id": BLADE, "controller": {"kind": "mainrun"}, "provenance": {"source": 5}},
    {"item_id": BLADE, "controller": {"kind": "mainrun"}, "provenance": {"source": "   "}},
    {"item_id": BLADE, "controller": {"kind": "mainrun"}, "provenance": {"event": True}},
    {"item_id": BLADE, "controller": {"kind": "mainrun"}, "provenance": {"campaign_day": -1}},
    {"item_id": BLADE, "controller": {"kind": "mainrun"}, "provenance": {"campaign_day": 1.5}},
    {"item_id": BLADE, "controller": {"kind": "mainrun"}, "provenance": {"unexpected": 1}},
    {"item_id": BLADE, "controller": {"kind": "mainrun"}, "provenance": {}, "owner_entity_id": "faction:x"},
    {"item_id": BLADE, "controller": {"kind": "mainrun"}, "provenance": {}, "holder_entity_id": 123},
    {"item_id": BLADE, "controller": {"kind": "mainrun"}, "provenance": {}, "owner_entity_id": "character:Upper"},
    {"item_id": BLADE, "controller": {"kind": "mainrun"}, "provenance": {}, "extra": 1},
]


@pytest.mark.parametrize("payload", MALFORMED_REQUESTS)
def test_malformed_admission_requests_fail_closed(db, payload):
    _published, _staging, token, _expires = u.begin_save(db)

    error = _admit_error(db, token, payload)

    assert error
    assert _published_generation(db) == 0


# ---------------------------------------------------------------------------
# Malformed / duplicate existing truth
# ---------------------------------------------------------------------------

def test_malformed_existing_custody_fails_closed(db):
    malformed = {"item_id": SHIELD, "owner_entity_id": HERO}
    _seed_published_custody(db, [malformed])

    _published, _staging, token, _expires = u.begin_save(db)
    error = _admit_error(db, token, _request())

    assert error
    assert _published_generation(db) == 0


def test_duplicate_existing_custody_fails_closed(db):
    _seed_published_custody(
        db,
        [
            {"item_id": SHIELD, "owner_entity_id": HERO, "holder_entity_id": HERO},
            {"item_id": SHIELD, "owner_entity_id": FANIS, "holder_entity_id": FANIS},
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    error = _admit_error(db, token, _request())

    assert "duplicate" in error
    assert _published_generation(db) == 0


def test_malformed_existing_receipts_fail_closed(db):
    _seed_published_admissions(db, [{"item_id": SHIELD}])

    _published, _staging, token, _expires = u.begin_save(db)
    error = _admit_error(db, token, _request())

    assert error
    assert _published_generation(db) == 0


def test_duplicate_existing_receipts_fail_closed(db):
    _seed_published_admissions(db, [_receipt(item=SHIELD), _receipt(item=SHIELD)])

    _published, _staging, token, _expires = u.begin_save(db)
    error = _admit_error(db, token, _request())

    assert "duplicate admission receipts" in error
    assert _published_generation(db) == 0


# ---------------------------------------------------------------------------
# Cross-collection receipt-to-custody integrity (accepted P1 review scar)
# ---------------------------------------------------------------------------

def test_orphan_receipt_for_unrelated_item_blocks_admission(db):
    # P1 scar: validating item_custody and item_admissions independently lets a
    # structurally valid orphan receipt for one item survive while a DIFFERENT
    # item is admitted. The action must fail closed so it can never republish
    # admission truth that could not have been atomically created with custody.
    _seed_published_admissions(db, [_receipt(item=SHIELD)])

    _published, _staging, token, _expires = u.begin_save(db)
    error = _admit_error(db, token, _request(item=BLADE))

    assert "no matching item_custody record" in error
    assert _published_generation(db) == 0
    assert _published_admissions(db) == [_receipt(item=SHIELD)]
    assert _published_custody(db) == []


def test_orphan_receipt_blocks_admission_in_same_save_candidate(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _seed_published(db, "item_admissions", [_receipt(item=SHIELD)])

    error = _admit_error(db, token, _request(item=BLADE))

    assert "no matching item_custody record" in error


def test_legacy_vampire_custody_without_receipt_is_allowed(db):
    # Forward-only legacy exception: item:vampire was admitted before EV2-12.1,
    # so it has custody without an admission receipt. That asymmetry is
    # one-directional and must not be treated as an orphan; it also must not
    # block admitting a different item.
    _seed_published_custody(
        db,
        [
            {
                "item_id": "item:vampire",
                "owner_entity_id": None,
                "holder_entity_id": "character:gork",
            }
        ],
    )

    _admit_and_publish(db, _request(item=BLADE))

    state = _published_state(db)
    assert [r["item_id"] for r in state["item_custody"]] == ["item:vampire", BLADE]
    assert [r["item_id"] for r in state["item_admissions"]] == [BLADE]
    assert state["item_custody"][0] == {
        "item_id": "item:vampire",
        "owner_entity_id": None,
        "holder_entity_id": "character:gork",
    }


def test_any_custody_without_receipt_is_not_an_orphan(db):
    # The legacy exception is not hard-coded to item:vampire: the invariant is
    # one-directional by construction, so any pre-existing custody record
    # without a receipt is tolerated (legacy/forward-only), never rejected.
    _seed_published_custody(
        db,
        [{"item_id": HELM, "owner_entity_id": HERO, "holder_entity_id": HERO}],
    )

    _admit_and_publish(db, _request(item=BLADE))

    state = _published_state(db)
    assert [r["item_id"] for r in state["item_custody"]] == [HELM, BLADE]
    assert [r["item_id"] for r in state["item_admissions"]] == [BLADE]


# ---------------------------------------------------------------------------
# Separation / non-interference
# ---------------------------------------------------------------------------

def test_admission_does_not_touch_ordinary_inventory(db):
    inventory = [
        {
            "entity_id": HERO,
            "status": "known",
            "entries": [
                {"name": "Rope", "description": "Hemp rope", "quantity": 1}
            ],
            "currency": {"gp": 10},
        }
    ]
    _seed_published(db, "inventory", inventory)

    _admit_and_publish(db, _request())

    assert _published_state(db)["inventory"] == inventory


def test_gameplay_custody_remains_non_minting_after_admission(db):
    _admit_and_publish(db, _request())

    _published, _staging, token, _expires = u.begin_save(db)
    result = _custody_mutate(
        db,
        token,
        {
            "item_id": BLADE,
            "controller": {"kind": "mainrun"},
            "owner_entity_id": FANIS,
            "holder_entity_id": FANIS,
        },
    )
    assert result["custody"]["owner_entity_id"] == FANIS

    error = _custody_mutate_error(
        db,
        token,
        {
            "item_id": UNKNOWN_ITEM,
            "controller": {"kind": "mainrun"},
            "owner_entity_id": HERO,
            "holder_entity_id": HERO,
        },
    )
    assert "no admitted custody record" in error


def test_same_save_admission_and_inventory_compose_atomically(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _admit(db, token, _request())
    _inventory_mutate(
        db,
        token,
        {
            "owner_entity_id": HERO,
            "controller": {"kind": "mainrun"},
            "inventory": {
                "status": "known",
                "entries": [
                    {"name": "Torch", "description": "Pitch torch", "quantity": 3}
                ],
            },
        },
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    state = _published_state(db)
    assert state["item_custody"] == [
        {"item_id": BLADE, "owner_entity_id": HERO, "holder_entity_id": HERO}
    ]
    assert state["item_admissions"][0]["item_id"] == BLADE
    assert state["inventory"][0]["entries"][0]["name"] == "Torch"


# ---------------------------------------------------------------------------
# Bypass closure
# ---------------------------------------------------------------------------

def test_generic_stage_and_delete_cannot_write_engine_owned_keys(db):
    _published, _staging, token, _expires = u.begin_save(db)

    assert "item_custody" in _stage_error(db, token, "item_custody", [])
    assert "item_admissions" in _stage_error(db, token, "item_admissions", [])
    assert "item_custody" in _delete_error(db, token, "item_custody")
    assert "item_admissions" in _delete_error(db, token, "item_admissions")


def test_generic_save_cannot_mint_identity_or_receipt(db):
    _published, _staging, token, _expires = u.begin_save(db)

    error = _stage_error(
        db,
        token,
        "item_admissions",
        [_receipt()],
    )
    assert "engine-owned" in error
    assert _published_generation(db) == 0


def test_admission_action_is_service_role_only(db):
    assert u.scalar(
        db,
        "select has_function_privilege('service_role', "
        "'public.admit_item_identity(text,jsonb)', 'EXECUTE')",
    )
    assert not u.scalar(
        db,
        "select has_function_privilege('anon', "
        "'public.admit_item_identity(text,jsonb)', 'EXECUTE')",
    )
    assert not u.scalar(
        db,
        "select has_function_privilege('authenticated', "
        "'public.admit_item_identity(text,jsonb)', 'EXECUTE')",
    )


# ---------------------------------------------------------------------------
# Crash / retry
# ---------------------------------------------------------------------------

def test_aborted_admission_leaves_no_durable_identity_or_receipt(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _admit(db, token, _request())
    u.abort_save(db, token)

    assert _published_custody(db) == []
    assert _published_admissions(db) == []
    assert _published_generation(db) == 0


def test_retry_after_abort_converges_on_exactly_one_admission(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _admit(db, token, _request())
    u.abort_save(db, token)

    _admit_and_publish(db, _request())

    assert len(_published_custody(db)) == 1
    assert len(_published_admissions(db)) == 1
    assert _published_custody(db)[0]["item_id"] == BLADE


# ---------------------------------------------------------------------------
# Controller law
# ---------------------------------------------------------------------------

def test_admission_under_run_controller_for_controlled_actor(db):
    _seed_published_runs(
        db,
        [u.run(run_id="R01", mutable_owner_entity_ids=[HERO], participant_entity_ids=[HERO])],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    _admit(
        db,
        token,
        _request(controller={"kind": "run", "run_id": "R01"}, owner=HERO, holder=HERO),
    )
    u.publish(db, token)
    u.confirm_mirror(db)

    assert _published_admissions(db)[0]["controller"] == {
        "kind": "run",
        "run_id": "R01",
    }


def test_mainrun_cannot_establish_custody_for_run_controlled_actor(db):
    _seed_published_runs(
        db,
        [u.run(run_id="R01", mutable_owner_entity_ids=[HERO], participant_entity_ids=[HERO])],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    error = _admit_error(db, token, _request(owner=HERO, holder=HERO))

    assert "MAINRUN may not" in error
    assert _published_generation(db) == 0


def test_run_controller_without_existing_run_fails_closed(db):
    _published, _staging, token, _expires = u.begin_save(db)
    error = _admit_error(
        db,
        token,
        _request(
            controller={"kind": "run", "run_id": "R05"},
            include_owner=False,
            include_holder=False,
        ),
    )

    assert "does not exist" in error
    assert _published_generation(db) == 0


def test_parked_run_controller_without_actors_fails_closed(db):
    _seed_published_runs(
        db,
        [
            u.run(
                run_id="R01",
                execution_mode="played",
                control_state="parked",
                participant_entity_ids=[HERO],
                mutable_owner_entity_ids=[],
            )
        ],
    )

    _published, _staging, token, _expires = u.begin_save(db)
    error = _admit_error(
        db,
        token,
        _request(
            controller={"kind": "run", "run_id": "R01"},
            include_owner=False,
            include_holder=False,
        ),
    )

    assert "parked" in error
    assert _published_generation(db) == 0


# ---------------------------------------------------------------------------
# Same-save Run-ownership exclusion
# ---------------------------------------------------------------------------

def test_same_save_runs_change_blocks_admission(db):
    _published, _staging, token, _expires = u.begin_save(db)
    u.stage(db, token, "runs", [u.run()])

    error = _admit_error(db, token, _request())

    assert "staged a different runs batch" in error


def test_admission_closes_run_writing_doorways_in_same_save(db):
    _published, _staging, token, _expires = u.begin_save(db)
    _admit(db, token, _request())

    assert "already staged an item custody" in _stage_error(
        db, token, "runs", [u.run()]
    )
    assert "already staged an item custody" in _delete_error(db, token, "runs")


# ---------------------------------------------------------------------------
# Installation / shape
# ---------------------------------------------------------------------------

def test_admission_action_installs_on_the_full_migration_chain(db):
    assert u.scalar(
        db,
        "select count(*) from pg_proc p "
        "join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'public' and p.proname = 'admit_item_identity'",
    ) == 1
    assert u.scalar(
        db,
        "select count(*) from pg_proc p "
        "join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'public' and p.proname = '_rhc_validate_item_admissions_collection'",
    ) == 1
    assert u.scalar(
        db,
        "select count(*) from pg_proc p "
        "join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'public' and p.proname = '_rhc_validate_item_admission_custody_linkage'",
    ) == 1
