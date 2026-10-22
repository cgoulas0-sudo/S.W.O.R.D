import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "realities"

sys.path.insert(0, str(ROOT / "scripts"))

from validate_realities import (  # noqa: E402
    load_schema,
    validate_paths,
    validate_record,
)
from validate_entities import load_records  # noqa: E402

# RHC's current canonical primary reality. It remains the RHC root, but the
# engine no longer privileges this literal id: the root is now a structural role.
RHC_PRIMARY = "reality:rhc-primary"
# A campaign-neutral root id a clean/new campaign may use instead.
NEUTRAL_ROOT = "reality:campaign-root"
REGISTRY = ROOT / "realities" / "registry" / "rhc-primary.json"


def _write(path, record):
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _alternate(reality_id, parent, name="Alternate"):
    return {
        "reality_id": reality_id,
        "display_name": name,
        "parent_reality_id": parent,
    }


def _root(reality_id, name="Root"):
    return {"reality_id": reality_id, "display_name": name}


# -- schema shape ----------------------------------------------------------

def test_schema_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(load_schema())


def test_reality_id_grammar_is_strict():
    schema = load_schema()
    invalid_ids = [
        "",
        "reality:",
        "reality:-leading",
        "reality:trailing-",
        "reality:UPPER",
        "reality:has space",
        "reality:has_underscore",
        "Reality:lower",
        "character:hero",
        "reality:one\n",
        "reality:one two",
    ]
    for reality_id in invalid_ids:
        errors = validate_record(
            {"reality_id": reality_id, "display_name": "X"}, schema
        )
        assert errors, f"reality_id {reality_id!r} should fail schema validation"


def test_schema_forbids_extra_properties():
    schema = load_schema()
    record = {
        "reality_id": "reality:test-alt",
        "display_name": "Alt",
        "parent_reality_id": RHC_PRIMARY,
        "subjects": ["character:hero"],
    }
    assert validate_record(record, schema)


def test_schema_does_not_privilege_a_fixed_root_identity():
    # The schema must not hard-code any single reality id as the privileged root.
    schema_text = json.dumps(load_schema())
    assert RHC_PRIMARY not in schema_text
    assert NEUTRAL_ROOT not in schema_text


# -- per-record shape -------------------------------------------------------

def test_root_record_without_parent_is_schema_valid():
    schema = load_schema()
    assert validate_record(_root(RHC_PRIMARY), schema) == []


def test_non_root_record_with_parent_is_schema_valid():
    schema = load_schema()
    assert validate_record(_alternate("reality:test-alt", RHC_PRIMARY), schema) == []


# -- RHC continuity ---------------------------------------------------------

def test_rhc_primary_remains_the_unique_root(tmp_path):
    # RHC's canonical primary record still validates and is the unique root.
    record = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert record["reality_id"] == RHC_PRIMARY
    assert "parent_reality_id" not in record
    assert validate_paths([REGISTRY]) == {}


def test_registry_primary_record_is_the_root():
    record = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert record["reality_id"] == RHC_PRIMARY
    assert "parent_reality_id" not in record
    assert validate_paths([REGISTRY]) == {}


# -- generic root semantics -------------------------------------------------

def test_synthetic_root_with_different_id_validates(tmp_path):
    root = _write(tmp_path / "root.json", _root(NEUTRAL_ROOT))
    assert validate_paths([root]) == {}


def test_valid_fixtures_pass_as_a_batch():
    paths = load_records(FIXTURES / "valid")
    assert len(paths) == 2
    assert validate_paths(paths) == {}


def test_minimal_inherited_record_needs_no_subject_availability_map(tmp_path):
    primary = _write(tmp_path / "primary.json", _root(RHC_PRIMARY))
    alt = _write(tmp_path / "alt.json", _alternate("reality:test-alt", RHC_PRIMARY))
    assert validate_paths([primary, alt]) == {}


# -- batch lineage law ------------------------------------------------------

def test_exactly_one_root_is_required_zero_roots_fail(tmp_path):
    # A non-root child whose parent is absent leaves the set with no root.
    alt = _write(tmp_path / "alt.json", _alternate("reality:test-alt", "reality:missing"))
    errors_by_path = validate_paths([alt])
    assert alt in errors_by_path
    assert any("no root reality" in e for e in errors_by_path[alt])


def test_empty_registry_batch_fails_closed():
    # An empty validated registry/batch (zero records) is a zero-root state and
    # must fail closed instead of silently validating as an empty batch.
    with pytest.raises(ValueError) as excinfo:
        validate_paths([])
    message = str(excinfo.value)
    assert "no root reality" in message
    assert "zero-root" in message


def test_empty_registry_directory_fails_closed(tmp_path):
    # An existing registry directory containing zero JSON records must fail
    # closed; a zero-record registry is never reported as a valid registry.
    empty = tmp_path / "registry"
    empty.mkdir()
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_realities.py"), str(empty)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "OK:" not in proc.stdout
    assert proc.stderr.strip()


def test_two_parentless_roots_fail(tmp_path):
    a = _write(tmp_path / "a.json", _root("reality:a"))
    b = _write(tmp_path / "b.json", _root("reality:b"))
    errors_by_path = validate_paths([a, b])
    assert a in errors_by_path and b in errors_by_path
    assert any("more than one parentless root" in e for e in errors_by_path[a])


def test_non_root_child_without_parent_fails(tmp_path):
    # An intended child that declares no parent is a second parentless root and
    # therefore fails the exactly-one-root structural rule.
    root = _write(tmp_path / "root.json", _root(RHC_PRIMARY))
    orphan = _write(tmp_path / "orphan.json", {"reality_id": "reality:orphan", "display_name": "Orphan"})
    errors_by_path = validate_paths([root, orphan])
    assert orphan in errors_by_path
    assert any(
        "more than one parentless root" in e or "must declare exactly one parent" in e
        for e in errors_by_path[orphan]
    )


def test_non_root_child_with_non_string_parent_fails(tmp_path):
    root = _write(tmp_path / "root.json", _root(RHC_PRIMARY))
    bad = _write(
        tmp_path / "bad.json",
        {"reality_id": "reality:bad", "display_name": "Bad", "parent_reality_id": None},
    )
    errors_by_path = validate_paths([root, bad])
    assert bad in errors_by_path
    assert any("must declare exactly one parent" in e for e in errors_by_path[bad])


def test_unresolved_parent_fails(tmp_path):
    primary = _write(tmp_path / "primary.json", _root(RHC_PRIMARY))
    alt = _write(tmp_path / "alt.json", _alternate("reality:test-alt", "reality:missing"))
    errors_by_path = validate_paths([primary, alt])
    assert alt in errors_by_path
    assert any("does not resolve" in e for e in errors_by_path[alt])


def test_parent_cycle_fails(tmp_path):
    primary = _write(tmp_path / "primary.json", _root(RHC_PRIMARY))
    a = _write(tmp_path / "a.json", _alternate("reality:cycle-a", "reality:cycle-b"))
    b = _write(tmp_path / "b.json", _alternate("reality:cycle-b", "reality:cycle-a"))
    errors_by_path = validate_paths([primary, a, b])
    assert a in errors_by_path and b in errors_by_path
    assert any("cycle" in e for e in errors_by_path[a])
    assert any("cycle" in e for e in errors_by_path[b])


def test_self_parent_cycle_fails(tmp_path):
    primary = _write(tmp_path / "primary.json", _root(RHC_PRIMARY))
    selfy = _write(tmp_path / "self.json", _alternate("reality:self", "reality:self"))
    errors_by_path = validate_paths([primary, selfy])
    assert selfy in errors_by_path
    assert any("cycle" in e for e in errors_by_path[selfy])


def test_duplicate_reality_ids_fail(tmp_path):
    primary = _write(tmp_path / "primary.json", _root(RHC_PRIMARY))
    a = _write(tmp_path / "a.json", _alternate("reality:dup", RHC_PRIMARY))
    b = _write(tmp_path / "b.json", _alternate("reality:dup", RHC_PRIMARY))
    errors_by_path = validate_paths([primary, a, b])
    assert len(errors_by_path) == 1
    (only_path, errors), = errors_by_path.items()
    assert only_path in (a, b)
    assert any("duplicates" in e for e in errors)


def test_multi_level_lineage_resolves(tmp_path):
    primary = _write(tmp_path / "primary.json", _root(RHC_PRIMARY))
    child = _write(tmp_path / "child.json", _alternate("reality:child", RHC_PRIMARY))
    grandchild = _write(tmp_path / "grand.json", _alternate("reality:grand", "reality:child"))
    assert validate_paths([primary, child, grandchild]) == {}


# -- forbidden surfaces -----------------------------------------------------

def test_no_subject_availability_schema_introduced():
    assert not (ROOT / "schemas" / "reality_scope.schema.json").exists()
    schema = load_schema()
    assert set(schema["properties"]) == {
        "reality_id",
        "display_name",
        "parent_reality_id",
    }
    property_names = set(schema["properties"])
    assert "subjects" not in property_names
    assert "availability" not in property_names


def test_no_generic_override_or_state_copy_payload_introduced():
    assert not list((ROOT / "schemas").glob("reality_override*"))
    assert not list((ROOT / "schemas").glob("reality_state*"))
    property_names = set(load_schema()["properties"])
    for forbidden in ("override", "overrides", "divergence", "divergences", "state"):
        assert forbidden not in property_names


def test_existing_owner_schemas_remain_reality_free():
    for name in (
        "entity.schema.json",
        "hook.schema.json",
        "scenario.schema.json",
        "encounter.schema.json",
        "run.schema.json",
    ):
        path = ROOT / "schemas" / name
        if not path.exists():
            continue
        assert "reality" not in path.read_text(encoding="utf-8").lower(), (
            f"{name} must not be reality-scoped by POST-EV2-4B"
        )


def test_no_runtime_or_temporal_surface_was_added():
    assert not list((ROOT / "supabase").rglob("*reality*"))
    assert not list((ROOT / "supabase").rglob("*reality*.sql"))


# -- pinned durable meaning ------------------------------------------------

def test_docs_pin_inheritance_by_default_and_rejected_scar():
    text = (ROOT / "docs" / "POST-EV2-4B-REALITY-INHERITANCE.md").read_text(
        encoding="utf-8"
    )
    lowered = text.lower()
    assert "inherit" in lowered
    assert "unchanged" in lowered
    assert "availability" in lowered
    assert "reality_scope.schema.json" in text
    assert "mutate the parent/source reality" in lowered
    assert "one engine; many histories" in lowered


def test_readme_pins_inheritance_by_default():
    text = (ROOT / "realities" / "README.md").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "inherit" in lowered
    assert "unchanged" in lowered
    assert RHC_PRIMARY in text


def test_traveler_carry_out_is_deferred_not_implemented():
    text = (ROOT / "docs" / "POST-EV2-4B-REALITY-INHERITANCE.md").read_text(
        encoding="utf-8"
    )
    assert "carry-out" in text.lower()
    assert "No carry-out happens" in text
    schema_text = json.dumps(load_schema())
    assert "carry" not in schema_text


def test_external_continuity_remains_non_canon():
    text = (ROOT / "docs" / "POST-EV2-4B-REALITY-INHERITANCE.md").read_text(
        encoding="utf-8"
    )
    assert "PREQUEL" in text and "SEQUEL" in text
    assert "non-canon" in text


def test_disposable_labs_remain_non_canon_and_unregistered():
    # POST-EV2-14 durable boundary: disposable brainstorm labs are NOT canonical
    # realities and are never registered in the reality registry.
    lab_doc = (ROOT / "docs" / "POST-EV2-14-DISPOSABLE-BRAINSTORM-LAB.md").read_text(
        encoding="utf-8"
    )
    lowered = lab_doc.lower()
    assert "non-canon" in lowered
    assert "reality" in lowered
    assert not list((ROOT / "realities" / "registry").rglob("*lab*"))


# -- CI wiring -------------------------------------------------------------

def test_entity_v2_workflow_runs_bounded_reality_proof():
    workflow = (ROOT / ".github" / "workflows" / "entity-v2-identity.yml").read_text(
        encoding="utf-8"
    )
    assert "scripts/validate_realities.py" in workflow
    assert "tests/test_reality_inheritance.py" in workflow


def test_missing_directory_is_rejected(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises((FileNotFoundError, NotADirectoryError)):
        load_records(missing)
