"""Read-only proof for the canonical root campaign JSON validator.

Proves the bounded owner contracts are enforced (strict JSON, root object,
META/NON_META and NPC owner vocabularies), that malformed input fails closed,
that Entity V2 per-entity schemas are NOT applied to root documents, that the
public CLI is bound to the six exact repository-relative paths (and rejects a
same-basename noncanonical path), and that validating the real committed root
files is source-immutable.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_canonical_root_json.py"
sys.path.insert(0, str(ROOT / "scripts"))


def _load_validator():
    spec = importlib.util.spec_from_file_location("vcrj", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vcrj = _load_validator()


@pytest.fixture(scope="module")
def vocabulary():
    return vcrj.load_npc_vocabulary(ROOT)


def _validate(relative, content, vocabulary):
    return vcrj.validate_text(relative, content, vocabulary)


def test_real_canonical_root_files_are_valid(vocabulary):
    for relative in vcrj.CANONICAL_ROOT_FILES:
        errors = vcrj.validate_repository_file(relative, vocabulary)
        assert errors == [], f"{relative}: {errors}"


def test_malformed_json_fails_closed(vocabulary):
    errors = _validate("state/live_status.json", "{ not json", vocabulary)
    assert errors and "invalid JSON" in errors[0]


def test_duplicate_key_fails_closed(vocabulary):
    errors = _validate("state/live_status.json", '{"a": 1, "a": 2}', vocabulary)
    assert errors and "duplicate key" in errors[0]


def test_bare_nonfinite_constant_fails_closed(vocabulary):
    errors = _validate("state/live_status.json", '{"a": NaN}', vocabulary)
    assert errors and "not valid JSON" in errors[0]


def test_numeric_overflow_fails_closed(vocabulary):
    errors = _validate("state/live_status.json", '{"a": 1e400}', vocabulary)
    assert errors and "non-finite" in errors[0]


@pytest.mark.parametrize(
    "relative, content",
    [
        ("state/live_status.json", "[1, 2, 3]"),
        ("state/live_status.json", '"just a string"'),
        ("state/live_status.json", "42"),
        ("knowledge/facts.json", "[]"),
        ("npc/npc_state.json", "null"),
    ],
)
def test_non_object_root_fails_closed(vocabulary, relative, content):
    errors = _validate(relative, content, vocabulary)
    assert errors and "must be a JSON object" in errors[0]


def _facts_document(**overrides):
    document = {
        "schema_version": 2,
        "default_visibility": "meta",
        "facts": [],
        "fact_schema": {
            "visibility": "meta | non_meta",
            "source_status": "rhc_canon | explicit_dm_canon | official_dnd_rules",
        },
    }
    document.update(overrides)
    return document


def test_facts_default_visibility_vocabulary(vocabulary):
    errors = _validate(
        "knowledge/facts.json",
        json.dumps(_facts_document(default_visibility="public")),
        vocabulary,
    )
    assert errors and "default_visibility" in errors[0]


def test_facts_entry_visibility_vocabulary(vocabulary):
    document = _facts_document(facts=[{"fact_id": "F001", "visibility": "secret"}])
    errors = _validate("knowledge/facts.json", json.dumps(document), vocabulary)
    assert errors and "facts[0].visibility" in errors[0]


def test_facts_entry_source_status_vocabulary(vocabulary):
    document = _facts_document(facts=[{"fact_id": "F001", "source_status": "made_up"}])
    errors = _validate("knowledge/facts.json", json.dumps(document), vocabulary)
    assert errors and "source_status" in errors[0]


def test_facts_valid_entry_passes(vocabulary):
    document = _facts_document(
        facts=[
            {
                "fact_id": "F001",
                "visibility": "non_meta",
                "source_status": "rhc_canon",
            }
        ]
    )
    errors = _validate("knowledge/facts.json", json.dumps(document), vocabulary)
    assert errors == []


def _npc_document(**entry_overrides):
    entry = {
        "display_name": "Fixture NPC",
        "live_state": {"status": "Unknown", "current_combat_state": "battle_ready"},
        "relationships": {"fixture": {"trend": "stable"}},
        "continuity": {"last_update_source": "quicksave"},
    }
    entry.update(entry_overrides)
    return {"template_version": 7, "npcs": {"fixture": entry}}


def test_npc_combat_state_vocabulary(vocabulary):
    document = _npc_document(
        live_state={"status": "Unknown", "current_combat_state": "flying"}
    )
    errors = _validate("npc/npc_state.json", json.dumps(document), vocabulary)
    assert errors and "current_combat_state" in errors[0]


def test_npc_relationship_trend_vocabulary(vocabulary):
    document = _npc_document(relationships={"fixture": {"trend": "growing"}})
    errors = _validate("npc/npc_state.json", json.dumps(document), vocabulary)
    assert errors and "trend" in errors[0]


def test_npc_update_source_vocabulary(vocabulary):
    document = _npc_document(continuity={"last_update_source": "chat"})
    errors = _validate("npc/npc_state.json", json.dumps(document), vocabulary)
    assert errors and "last_update_source" in errors[0]


def test_npc_valid_entry_passes(vocabulary):
    errors = _validate("npc/npc_state.json", json.dumps(_npc_document()), vocabulary)
    assert errors == []


def test_dm_meta_visibility_must_be_meta(vocabulary):
    errors = _validate("state/dm_meta.json", '{"visibility": "non_meta"}', vocabulary)
    assert errors and "must be 'meta'" in errors[0]


@pytest.mark.parametrize(
    "relative, content",
    [
        ("state/daily_recap.json", '{"status": "uninitialized", "current_day": null}'),
        ("state/day_resolution.json", '{"status": "uninitialized", "rng_rolls": []}'),
        ("state/live_status.json", '{"businesses": {}, "party_state": {}}'),
    ],
)
def test_state_root_documents_only_require_object(vocabulary, relative, content):
    assert _validate(relative, content, vocabulary) == []


def test_unknown_relative_document_is_rejected(vocabulary):
    errors = vcrj.validate_document("random.json", {}, vocabulary)
    assert errors and "not a recognized canonical root document" in errors[0]


def test_canonical_relative_path_binds_by_location(vocabulary):
    assert (
        vcrj.canonical_relative_path(ROOT / "state" / "live_status.json", ROOT)
        == "state/live_status.json"
    )
    assert (
        vcrj.canonical_relative_path("state/live_status.json", ROOT)
        == "state/live_status.json"
    )


def test_same_basename_noncanonical_path_gets_no_contract(tmp_path):
    intel = tmp_path / "live_status.json"
    intel.write_text('{"businesses": {}}', encoding="utf-8")
    assert vcrj.canonical_relative_path(intel, ROOT) is None


def test_relative_canonical_path_resolves_from_root_not_cwd():
    assert (
        vcrj.canonical_relative_path("state/live_status.json", ROOT)
        == "state/live_status.json"
    )
    assert vcrj.canonical_relative_path("live_status.json", ROOT) is None


def test_public_cli_rejects_same_basename_noncanonical_path(tmp_path, capsys):
    intel = tmp_path / "live_status.json"
    intel.write_text('{"businesses": {}}', encoding="utf-8")

    assert vcrj.main([str(intel)]) == 1
    captured = capsys.readouterr()
    assert "not one of the canonical root paths" in captured.err


def test_public_cli_accepts_a_canonical_absolute_path(capsys):
    assert vcrj.main([str(ROOT / "state" / "live_status.json")]) == 0
    captured = capsys.readouterr()
    assert "OK: 1 canonical root JSON document(s) valid." in captured.out


def test_public_cli_relative_path_succeeds_from_outside_checkout(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    assert vcrj.main(["state/live_status.json"]) == 0
    captured = capsys.readouterr()
    assert "OK: 1 canonical root JSON document(s) valid." in captured.out


def test_public_cli_rejects_relative_same_basename_from_outside_checkout(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "live_status.json").write_text('{"businesses": {}}', encoding="utf-8")
    assert vcrj.main(["live_status.json"]) == 1
    captured = capsys.readouterr()
    assert "not one of the canonical root paths" in captured.err


def test_validation_does_not_mutate_sources(vocabulary, capsys):
    snapshots = {
        relative: (ROOT / relative).read_bytes()
        for relative in vcrj.CANONICAL_ROOT_FILES
    }
    template_snapshot = (ROOT / vcrj.NPC_STATE_TEMPLATE).read_bytes()

    assert vcrj.main([]) == 0
    capsys.readouterr()

    for relative, before in snapshots.items():
        assert (ROOT / relative).read_bytes() == before, relative
    assert (ROOT / vcrj.NPC_STATE_TEMPLATE).read_bytes() == template_snapshot
