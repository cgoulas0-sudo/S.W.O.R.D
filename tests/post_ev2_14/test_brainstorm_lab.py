"""POST-EV2-14 disposable NON-CANON brainstorm-lab lifecycle proof.

Proves the reusable engine-side lab kernel defined by JOHNNY CHECKPOINT
``POST_EV2_14_DISPOSABLE_BRAINSTORM_LAB_V1`` at base
``ee3b089473d56a2992e10510816a0e8806dcff14``. Synthetic generic identities
only; no real RHC character/NPC/location/item names or campaign content appear
in this proof or in the kernel it proves.

This suite proves the simplified (Option C) reset internals: one durable
recovery journal ``reset.pending.json``, one fixed tombstone ``active.tombstone``,
and one latest receipt ``last-reset.json``. It covers the original Mission Proof
Matrix plus the required simplification proofs -- active/closed/orphan happy
paths, receipt replacement on a later reset, every materially distinct reset
interruption boundary, fail-closed metadata states, and the preserved
no-merge-back / synthetic-corpus guarantees.

This suite is COPY-shipped into every clean campaign canvas, so it is a
portable bounded-lifecycle proof only: every assertion below runs unchanged in
the source repository and inside an exported canvas. The primary reality it
must not mutate is resolved by its structural role -- the unique parentless
root record in the shipped registry -- never by one RHC-only source path.
Assertions that police the source factory machinery (the source CI workflow
that runs this suite, the export-policy classification of these surfaces, and
their presence in a fresh export) belong to the EXCLUDE-owned factory proof
``tests/post_ev2_z/test_clean_campaign_export.py`` and are deliberately absent
here, so no source-vs-canvas context discriminator exists at all.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KERNEL_PATH = ROOT / "scripts" / "brainstorm_lab.py"
DOC_PATH = ROOT / "docs" / "POST-EV2-14-DISPOSABLE-BRAINSTORM-LAB.md"
TEST_PATH = ROOT / "tests" / "post_ev2_14" / "test_brainstorm_lab.py"

sys.path.insert(0, str(ROOT / "scripts"))

import brainstorm_lab as lab  # noqa: E402

ORIGIN = {"campaign_id": "campaign-alpha", "checkpoint_id": "checkpoint-0001"}

# Reusable corpus must carry only synthetic generic identities. These are the
# real RHC instance names that must never leak into shipped code/fixtures/
# tests/examples/acceptance assertions. The literals are split so this denylist
# does not itself trip the corpus scan it powers once this module ships in the
# clean canvas.
RHC_NAME_TOKENS = (
    "ma" "dma",
    "go" "rk",
    "mu" "gen",
    "saa" "rpa",
    "iou" "laum",
    "lar" "loch",
    "bor-" "family",
    "bor" "_",
)


def _git(*args):
    return subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _snapshot(root: Path):
    snapshot = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snapshot[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return snapshot


def _primary_registry_path():
    # The primary reality is a structural role -- the unique parentless root
    # record -- not one fixed campaign identity (POST-EV2-Z3). Source RHC ships
    # its canonical root record while a clean canvas genesis emits a
    # campaign-neutral root at a remapped path, so this COPY-shipped suite
    # resolves the record this tree actually ships instead of hard-coding one
    # RHC-only source path that the Z exporter remaps away.
    records = sorted((ROOT / "realities" / "registry").glob("*.json"))
    parentless = [
        path
        for path in records
        if "parent_reality_id"
        not in json.loads(path.read_text(encoding="utf-8"))
    ]
    assert len(parentless) == 1, (
        "expected exactly one parentless root reality record in "
        f"realities/registry, got {len(parentless)}"
    )
    return parentless[0]


def _lock_provenance(lock: dict) -> dict:
    return {
        "lab_id": lock["lab_id"],
        "mode": lock["mode"],
        "origin": dict(lock["origin"]),
        "closed_outcome": lock["closed_outcome"],
    }


def _pending_doc(lock: dict = None, **overrides) -> dict:
    provenance = None
    if lock is not None:
        provenance = _lock_provenance(lock)
    document = {
        "schema_version": lab.SCHEMA_VERSION,
        "pending_kind": lab.PENDING_KIND,
        "reset_id": "0" * 32,
        "non_canon": True,
        "provenance": provenance,
        "had_active": True,
    }
    document.update(overrides)
    return document


def _receipt_document(root: Path) -> dict:
    return json.loads((root / lab.RECEIPT_FILENAME).read_text(encoding="utf-8"))


def _write_receipt_document(root: Path, document: dict) -> None:
    (root / lab.RECEIPT_FILENAME).write_text(json.dumps(document), encoding="utf-8")


def _lab_with_committed_receipt(tmp_path):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    lab.reset(root)
    return root


# --------------------------------------------------------------------------
# begin / active identity
# --------------------------------------------------------------------------

def test_begin_from_origin_creates_active_non_canon_lab(tmp_path):
    lock = lab.begin(tmp_path / "lab", ORIGIN, "prequel", "anchor-alpha")
    assert lock["non_canon"] is True
    assert lock["status"] == lab.STATE_ACTIVE
    assert lock["origin"] == ORIGIN
    assert lock["lab_id"]
    status = lab.lab_status(tmp_path / "lab")
    assert status["state"] == lab.STATE_ACTIVE
    assert status["non_canon"] is True


def test_begin_refuses_when_a_lab_already_exists(tmp_path):
    lab.begin(tmp_path / "lab", ORIGIN, "sequel", "anchor-alpha")
    with pytest.raises(lab.BrainstormLabError):
        lab.begin(tmp_path / "lab", ORIGIN, "what_if", "anchor-beta")


def test_begin_refuses_on_closed_unreset_state(tmp_path):
    lab.begin(tmp_path / "lab", ORIGIN, "sequel", "anchor-alpha")
    lab.close(tmp_path / "lab", "completed")
    with pytest.raises(lab.BrainstormLabError):
        lab.begin(tmp_path / "lab", ORIGIN, "prequel", "anchor-beta")


def test_begin_refuses_when_already_resetting(tmp_path):
    root = tmp_path / "lab"
    lock = lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    (root / lab.PENDING_FILENAME).write_text(
        json.dumps(_pending_doc(lock, reset_id="a" * 32)), encoding="utf-8"
    )
    assert lab.lab_status(root)["state"] == lab.STATE_RESETTING
    with pytest.raises(lab.BrainstormLabError):
        lab.begin(root, ORIGIN, "prequel", "anchor-beta")


def test_fresh_root_is_clean(tmp_path):
    assert lab.lab_status(tmp_path / "fresh")["state"] == lab.STATE_CLEAN


@pytest.mark.parametrize("mode", lab.MODES)
def test_modes_supported_without_canon_authority(tmp_path, mode):
    lock = lab.begin(tmp_path / mode, ORIGIN, mode, f"anchor-{mode}")
    assert lock["mode"] == mode
    assert lock["non_canon"] is True
    # No reality registry or canon artifact is created anywhere.
    assert not (tmp_path / mode / "realities").exists()
    assert not (tmp_path / mode / "canon").exists()


def test_origin_provenance_is_stored_separately_from_anchor(tmp_path):
    lock = lab.begin(tmp_path / "lab", ORIGIN, "what_if", "anchor-alpha")
    assert lock["origin"] == ORIGIN
    assert lock["narrative_anchor"] == "anchor-alpha"
    assert "narrative_anchor" not in lock["origin"]
    assert "campaign_id" not in lock["narrative_anchor"]


# --------------------------------------------------------------------------
# origin receipt validation
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad",
    [
        None,
        "a string",
        [],
        {},
        {"campaign_id": "campaign-alpha"},
        {"checkpoint_id": "checkpoint-0001"},
        {"campaign_id": "", "checkpoint_id": "checkpoint-0001"},
        {"campaign_id": "campaign-alpha", "checkpoint_id": "   "},
        {"campaign_id": 5, "checkpoint_id": "checkpoint-0001"},
        {"campaign_id": "bad identity!", "checkpoint_id": "checkpoint-0001"},
        {"campaign_id": "campaign-alpha", "checkpoint_id": "checkpoint\n0001"},
    ],
)
def test_origin_receipt_shape_is_strict(tmp_path, bad):
    with pytest.raises(lab.BrainstormLabError):
        lab.begin(tmp_path / "lab", bad, "prequel", "anchor-alpha")


# --------------------------------------------------------------------------
# source immutability / write confinement
# --------------------------------------------------------------------------

def test_source_and_origin_material_unchanged_by_lifecycle(tmp_path):
    scratch = tmp_path / "scratch"
    source = scratch / "source"
    source.mkdir(parents=True)
    (source / "campaign-page.json").write_text(
        json.dumps({"page": "synthetic"}), encoding="utf-8"
    )
    origin_file = scratch / "origin.json"
    origin_file.write_text(json.dumps(ORIGIN), encoding="utf-8")
    # Source/origin material lives outside the disposable lab root.
    before = {**{f"source/{p}": h for p, h in _snapshot(source).items()},
              "origin.json": hashlib.sha256(origin_file.read_bytes()).hexdigest()}

    root = scratch / "lab"
    lab.begin(root, ORIGIN, "sequel", "anchor-alpha")
    lab.write_lab_state(root, "scene/one.json", "{}")
    lab.close(root, "completed")
    lab.reset(root)

    after = {**{f"source/{p}": h for p, h in _snapshot(source).items()},
             "origin.json": hashlib.sha256(origin_file.read_bytes()).hexdigest()}
    assert after == before


def test_lifecycle_writes_only_inside_lab_root(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    root = scratch / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    lab.write_lab_state(root, "notes.txt", "synthetic")
    outside = {p.name for p in scratch.iterdir() if p.name != "lab"}
    assert outside == set()


def test_lab_root_inside_git_worktree_is_refused(tmp_path):
    # The repository itself is a Git working tree; a lab rooted inside it must
    # be refused rather than risking canon contamination.
    with pytest.raises(lab.BrainstormLabError):
        lab.begin(ROOT / "__forbidden_lab__", ORIGIN, "prequel", "anchor-alpha")
    assert not (ROOT / "__forbidden_lab__").exists()


def test_write_guard_confines_paths_to_active_subtree(tmp_path):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    for escape in ("../escape.txt", "..\\escape.txt", "/abs.txt", ""):
        with pytest.raises(lab.BrainstormLabError):
            lab.write_lab_state(root, escape, "x")
    assert not (tmp_path / "escape.txt").exists()


# --------------------------------------------------------------------------
# close / freeze
# --------------------------------------------------------------------------

def test_close_is_one_way_and_idempotent(tmp_path):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "sequel", "anchor-alpha")
    first = lab.close(root, "completed")
    assert first["status"] == lab.STATE_CLOSED
    assert first["closed_outcome"] == "completed"
    # Same close is idempotent.
    again = lab.close(root, "completed")
    assert again == first
    # A conflicting outcome is refused; close is one-way.
    with pytest.raises(lab.BrainstormLabError):
        lab.close(root, "aborted")


def test_close_refused_when_not_active(tmp_path):
    root = tmp_path / "lab"
    with pytest.raises(lab.BrainstormLabError):
        lab.close(root, "completed")
    lab.begin(root, ORIGIN, "what_if", "anchor-alpha")
    lab.close(root, "aborted")
    # Repeated same close is idempotent; a conflicting outcome is refused.
    assert lab.close(root, "aborted")["closed_outcome"] == "aborted"
    with pytest.raises(lab.BrainstormLabError):
        lab.close(root, "completed")


def test_writable_guard_refuses_closed_but_read_remains(tmp_path):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    lab.write_lab_state(root, "scene/one.json", '{"synthetic": true}')
    lab.close(root, "completed")

    with pytest.raises(lab.BrainstormLabError):
        lab.assert_writable(root)
    with pytest.raises(lab.BrainstormLabError):
        lab.write_lab_state(root, "scene/two.json", "{}")

    # Read/inspection remains available.
    assert lab.lab_status(root)["state"] == lab.STATE_CLOSED
    assert b"synthetic" in lab.read_lab_state(root, "scene/one.json")
    assert lab.list_lab_state(root) == ["scene/one.json"]


# --------------------------------------------------------------------------
# reset happy paths / receipt model
# --------------------------------------------------------------------------

def test_active_reset_reaches_clean_with_latest_receipt(tmp_path):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    lab.write_lab_state(root, "scene/one.json", "{}")
    result = lab.reset(root)

    assert result["state"] == lab.STATE_CLEAN
    assert result["already_clean"] is False
    receipt = result["receipt"]
    assert receipt["verified_clean"] is True
    assert receipt["non_canon"] is True
    assert receipt["reset_id"]
    assert receipt["provenance"]["mode"] == "prequel"
    assert receipt["provenance"]["origin"] == ORIGIN
    assert receipt["provenance"]["closed_outcome"] is None
    assert lab.lab_status(root)["state"] == lab.STATE_CLEAN
    assert not (root / lab.ACTIVE_DIRNAME).exists()
    assert not (root / lab.LOCK_FILENAME).exists()
    assert not (root / lab.PENDING_FILENAME).exists()
    assert not (root / lab.TOMBSTONE_PATHNAME).exists()
    # The latest receipt survives as metadata only.
    assert (root / lab.RECEIPT_FILENAME).is_file()


def test_closed_reset_reaches_clean_with_latest_receipt(tmp_path):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "sequel", "anchor-alpha")
    lab.write_lab_state(root, "scene/one.json", "{}")
    lab.close(root, "aborted")
    result = lab.reset(root)
    assert result["state"] == lab.STATE_CLEAN
    assert result["receipt"]["provenance"]["closed_outcome"] == "aborted"
    assert lab.lab_status(root)["state"] == lab.STATE_CLEAN


def test_orphan_active_without_lock_reset_has_null_provenance(tmp_path):
    root = tmp_path / "lab"
    (root / lab.ACTIVE_DIRNAME).mkdir(parents=True)
    (root / lab.ACTIVE_DIRNAME / "scene.json").write_text("{}", encoding="utf-8")

    result = lab.reset(root)
    assert result["state"] == lab.STATE_CLEAN
    receipt = result["receipt"]
    assert receipt["provenance"] is None
    assert receipt["verified_clean"] is True
    assert lab.lab_status(root)["state"] == lab.STATE_CLEAN


def test_second_orphan_reset_replaces_receipt_with_new_reset_id(tmp_path):
    root = tmp_path / "lab"

    (root / lab.ACTIVE_DIRNAME).mkdir(parents=True)
    first = lab.reset(root)["receipt"]
    first_id = first["reset_id"]

    (root / lab.ACTIVE_DIRNAME).mkdir(parents=True)
    second = lab.reset(root)["receipt"]

    assert second["reset_id"] != first_id
    assert second["provenance"] is None
    assert _receipt_document(root)["reset_id"] == second["reset_id"]


def test_old_receipt_does_not_block_a_new_reset_transaction(tmp_path):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    first = lab.reset(root)["receipt"]

    lab.begin(root, ORIGIN, "sequel", "anchor-beta")
    second = lab.reset(root)["receipt"]

    assert second["reset_id"] != first["reset_id"]
    assert _receipt_document(root) == second
    assert lab.lab_status(root)["state"] == lab.STATE_CLEAN


def test_repeated_reset_from_clean_is_idempotent(tmp_path):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "sequel", "anchor-alpha")
    first = lab.reset(root)
    assert first["already_clean"] is False

    before = _snapshot(root)
    second = lab.reset(root)
    assert second["already_clean"] is True
    assert second["receipt"] is None
    assert _snapshot(root) == before


def test_reset_after_clean_allows_a_new_lab(tmp_path):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    lab.reset(root)
    lock = lab.begin(root, ORIGIN, "sequel", "anchor-beta")
    assert lock["status"] == lab.STATE_ACTIVE


def test_reset_recovers_lock_without_active_subtree(tmp_path):
    # Simulate residue where the exclusive lock survives but its active subtree
    # is already gone; the next reset must finish deterministically.
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    (root / lab.ACTIVE_DIRNAME).rmdir()

    assert lab.lab_status(root)["state"] == lab.STATE_RESETTING
    result = lab.reset(root)
    assert result["state"] == lab.STATE_CLEAN
    assert result["receipt"]["provenance"]["lab_id"]
    assert not (root / lab.LOCK_FILENAME).exists()


# --------------------------------------------------------------------------
# simplification interruption matrix
# --------------------------------------------------------------------------

def test_crash_before_journal_replace_retry_succeeds(tmp_path, monkeypatch):
    # Boundary: the very first durable journal write fails before any destructive
    # step. Nothing changed, so the lab is still genuinely ACTIVE and a retry
    # begins the transaction cleanly.
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "sequel", "anchor-secret")

    real_write = lab._atomic_write_json

    def boom(path, document):
        if Path(path).name == lab.PENDING_FILENAME:
            raise OSError("simulated interruption before journal commit")
        real_write(path, document)

    monkeypatch.setattr(lab, "_atomic_write_json", boom)
    with pytest.raises(OSError):
        lab.reset(root)
    monkeypatch.setattr(lab, "_atomic_write_json", real_write)

    assert lab.lab_status(root)["state"] == lab.STATE_ACTIVE
    assert lab._list_owned_temps(root) == []

    result = lab.reset(root)
    assert result["state"] == lab.STATE_CLEAN
    assert result["receipt"]["provenance"]["mode"] == "sequel"
    assert "anchor-secret" not in json.dumps(result["receipt"])


def test_journal_temp_residue_is_resetting_and_discarded(tmp_path):
    # Boundary: a process killed after the journal temp was written but before
    # its atomic replace leaves kernel-owned residue. It forces RESETTING and a
    # retry discards only that owned temp and finishes.
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-secret")
    temp = root / f".{lab.PENDING_FILENAME}.{'ab' * 16}.tmp"
    temp.write_text("{ interrupted", encoding="utf-8")

    assert lab.lab_status(root)["state"] == lab.STATE_RESETTING
    with pytest.raises(lab.BrainstormLabError):
        lab.begin(root, ORIGIN, "prequel", "anchor-other")

    result = lab.reset(root)
    assert result["state"] == lab.STATE_CLEAN
    assert not temp.exists()
    assert lab._list_owned_temps(root) == []
    assert "anchor-secret" not in json.dumps(result["receipt"])


def test_crash_after_journal_commit_before_rename(tmp_path, monkeypatch):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "sequel", "anchor-secret")
    lab.write_lab_state(root, "scene/one.json", "{}")
    lab.close(root, "completed")

    real_rename = lab.os.rename

    def boom(*_args, **_kwargs):
        raise OSError("simulated interruption before rename")

    monkeypatch.setattr(lab.os, "rename", boom)
    with pytest.raises(OSError):
        lab.reset(root)
    monkeypatch.setattr(lab.os, "rename", real_rename)

    assert (root / lab.ACTIVE_DIRNAME).is_dir()
    assert (root / lab.PENDING_FILENAME).exists()
    pending = json.loads((root / lab.PENDING_FILENAME).read_text(encoding="utf-8"))
    assert pending["had_active"] is True
    assert pending["provenance"]["closed_outcome"] == "completed"
    assert lab.lab_status(root)["state"] == lab.STATE_RESETTING
    with pytest.raises(lab.BrainstormLabError):
        lab.begin(root, ORIGIN, "prequel", "anchor-other")
    with pytest.raises(lab.BrainstormLabError):
        lab.write_lab_state(root, "scene/two.json", "{}")

    result = lab.reset(root)
    assert result["state"] == lab.STATE_CLEAN
    assert result["receipt"]["provenance"]["mode"] == "sequel"
    assert result["receipt"]["provenance"]["closed_outcome"] == "completed"
    assert "anchor-secret" not in json.dumps(result["receipt"])


def test_crash_after_rename_before_delete(tmp_path, monkeypatch):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "what_if", "anchor-secret")
    lab.write_lab_state(root, "scene/one.json", "{}")

    real_rmtree = lab.shutil.rmtree

    def boom(*_args, **_kwargs):
        raise OSError("simulated interruption before delete")

    monkeypatch.setattr(lab.shutil, "rmtree", boom)
    with pytest.raises(OSError):
        lab.reset(root)
    monkeypatch.setattr(lab.shutil, "rmtree", real_rmtree)

    assert not (root / lab.ACTIVE_DIRNAME).exists()
    assert (root / lab.TOMBSTONE_PATHNAME).exists()
    assert (root / lab.PENDING_FILENAME).exists()
    assert lab.lab_status(root)["state"] == lab.STATE_RESETTING

    result = lab.reset(root)
    assert result["state"] == lab.STATE_CLEAN
    assert not (root / lab.TOMBSTONE_PATHNAME).exists()
    assert result["receipt"]["provenance"]["mode"] == "what_if"
    assert lab.lab_status(root)["state"] == lab.STATE_CLEAN


def test_interruption_during_tombstone_delete(tmp_path, monkeypatch):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-secret")
    lab.write_lab_state(root, "scene/one.json", "{}")

    real_rmtree = lab.shutil.rmtree
    calls = {"n": 0}

    def partial(path, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated interruption during delete")
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(lab.shutil, "rmtree", partial)
    with pytest.raises(OSError):
        lab.reset(root)
    monkeypatch.setattr(lab.shutil, "rmtree", real_rmtree)

    assert lab.lab_status(root)["state"] == lab.STATE_RESETTING
    result = lab.reset(root)
    assert result["state"] == lab.STATE_CLEAN
    assert not (root / lab.TOMBSTONE_PATHNAME).exists()
    assert lab.lab_status(root)["state"] == lab.STATE_CLEAN


def test_crash_during_last_reset_write(tmp_path, monkeypatch):
    # Boundary: tombstone deletion already succeeded but the final receipt write
    # fails. The journal must survive so the root can never read as CLEAN.
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "sequel", "anchor-secret")
    lab.write_lab_state(root, "scene/one.json", "{}")

    real_write = lab._atomic_write_json

    def boom(path, document):
        if Path(path).name == lab.RECEIPT_FILENAME:
            raise OSError("simulated interruption during receipt write")
        real_write(path, document)

    monkeypatch.setattr(lab, "_atomic_write_json", boom)
    with pytest.raises(OSError):
        lab.reset(root)
    monkeypatch.setattr(lab, "_atomic_write_json", real_write)

    assert not (root / lab.ACTIVE_DIRNAME).exists()
    assert not (root / lab.TOMBSTONE_PATHNAME).exists()
    assert (root / lab.PENDING_FILENAME).exists()
    assert not (root / lab.RECEIPT_FILENAME).exists()
    assert lab.lab_status(root)["state"] == lab.STATE_RESETTING

    result = lab.reset(root)
    assert result["state"] == lab.STATE_CLEAN
    assert result["receipt"]["provenance"]["mode"] == "sequel"
    assert "anchor-secret" not in json.dumps(result["receipt"])


def test_committed_receipt_is_not_rewritten_on_recovery(tmp_path, monkeypatch):
    # Boundary: the final receipt is durably committed but the recovery records
    # have not been cleaned. Retry must finish cleanup without rewriting the
    # committed receipt.
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "sequel", "anchor-secret")
    lab.write_lab_state(root, "scene/one.json", "{}")
    lab.close(root, "completed")

    real_write = lab._atomic_write_json

    def write_then_crash(path, document):
        real_write(path, document)
        if Path(path).name == lab.RECEIPT_FILENAME:
            raise OSError("simulated crash after receipt commit")

    monkeypatch.setattr(lab, "_atomic_write_json", write_then_crash)
    with pytest.raises(OSError):
        lab.reset(root)
    monkeypatch.setattr(lab, "_atomic_write_json", real_write)

    before = (root / lab.RECEIPT_FILENAME).read_bytes()
    assert (root / lab.LOCK_FILENAME).exists()
    assert (root / lab.PENDING_FILENAME).exists()
    assert lab.lab_status(root)["state"] == lab.STATE_RESETTING

    result = lab.reset(root)
    assert result["state"] == lab.STATE_CLEAN
    assert (root / lab.RECEIPT_FILENAME).read_bytes() == before
    assert result["receipt"] == json.loads(before)
    assert not (root / lab.LOCK_FILENAME).exists()
    assert not (root / lab.PENDING_FILENAME).exists()
    assert lab.lab_status(root)["state"] == lab.STATE_CLEAN


def test_after_journal_cleanup_root_is_legitimately_clean(tmp_path):
    # Boundary: after the recovery records are removed the transaction is
    # complete; no residue survives and a further reset is a safe no-op.
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-a")
    lab.write_lab_state(root, "scene/one.json", "{}")
    lab.reset(root)

    assert lab.lab_status(root)["state"] == lab.STATE_CLEAN
    assert not lab._list_owned_temps(root)
    assert not (root / lab.LOCK_FILENAME).exists()
    assert not (root / lab.PENDING_FILENAME).exists()
    assert not (root / lab.TOMBSTONE_PATHNAME).exists()
    assert lab.reset(root)["already_clean"] is True


# --------------------------------------------------------------------------
# fail-closed state
# --------------------------------------------------------------------------

def test_unexpected_lab_root_entry_fails_closed(tmp_path):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    (root / "surprise.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(lab.BrainstormLabError):
        lab.lab_status(root)
    with pytest.raises(lab.BrainstormLabError):
        lab.reset(root)


def test_corrupt_lock_fails_closed_without_false_clean_receipt(tmp_path):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    (root / lab.LOCK_FILENAME).write_text("{not json", encoding="utf-8")
    with pytest.raises(lab.BrainstormLabError):
        lab.lab_status(root)
    with pytest.raises(lab.BrainstormLabError):
        lab.reset(root)
    assert not (root / lab.RECEIPT_FILENAME).exists()


def test_fixed_tombstone_without_journal_fails_closed(tmp_path):
    # The simplified transaction can only ever leave the fixed tombstone while a
    # committed journal exists; a bare tombstone is an impossible state.
    root = tmp_path / "lab"
    (root / lab.TOMBSTONE_PATHNAME).mkdir(parents=True)
    (root / lab.TOMBSTONE_PATHNAME / "scene.json").write_text("{}", encoding="utf-8")

    with pytest.raises(lab.BrainstormLabError):
        lab.lab_status(root)
    with pytest.raises(lab.BrainstormLabError):
        lab.reset(root)
    assert (root / lab.TOMBSTONE_PATHNAME).exists()


def test_active_and_tombstone_coexist_fails_closed(tmp_path):
    root = tmp_path / "lab"
    lock = lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    (root / lab.TOMBSTONE_PATHNAME).mkdir()
    (root / lab.PENDING_FILENAME).write_text(
        json.dumps(_pending_doc(lock, reset_id="b" * 32)), encoding="utf-8"
    )

    with pytest.raises(lab.BrainstormLabError):
        lab.lab_status(root)
    with pytest.raises(lab.BrainstormLabError):
        lab.reset(root)


def test_unknown_temp_like_file_fails_closed_and_is_not_deleted(tmp_path):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-a")
    rogue = root / f".evil.json.{'ab' * 16}.tmp"
    rogue.write_text("rogue", encoding="utf-8")

    with pytest.raises(lab.BrainstormLabError):
        lab.lab_status(root)
    with pytest.raises(lab.BrainstormLabError):
        lab.reset(root)
    assert rogue.exists()


def test_atomic_write_cleans_its_own_temp_on_failure(tmp_path, monkeypatch):
    target = tmp_path / "meta.json"

    def boom(*_args, **_kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(lab.os, "replace", boom)
    with pytest.raises(OSError):
        lab._atomic_write_json(target, {"k": 1})

    assert not target.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


# --------------------------------------------------------------------------
# metadata coherence / malformed provenance
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "overrides",
    [
        None,
        {"lab_id": None},
        {"mode": None},
        {"origin": None},
        {"closed_outcome": "not-an-outcome"},
        {"lab_id": "../../escaped"},
    ],
)
def test_malformed_pending_provenance_fails_closed(tmp_path, overrides):
    root = tmp_path / "lab"
    lock = lab.begin(root, ORIGIN, "sequel", "anchor-alpha")
    document = _pending_doc(lock, reset_id="c" * 32)
    if overrides is None:
        del document["provenance"]["mode"]
    else:
        document["provenance"].update(overrides)
    (root / lab.PENDING_FILENAME).write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(lab.BrainstormLabError):
        lab.lab_status(root)
    with pytest.raises(lab.BrainstormLabError):
        lab.reset(root)
    with pytest.raises(lab.BrainstormLabError):
        lab.begin(root, ORIGIN, "prequel", "anchor-beta")


@pytest.mark.parametrize(
    "overrides",
    [
        None,
        {"lab_id": None},
        {"mode": None},
        {"origin": None},
        {"closed_outcome": "not-an-outcome"},
    ],
)
def test_malformed_retained_receipt_provenance_fails_clean_proof(tmp_path, overrides):
    root = _lab_with_committed_receipt(tmp_path)
    document = _receipt_document(root)
    if overrides is None:
        del document["provenance"]["origin"]
    else:
        document["provenance"].update(overrides)
    _write_receipt_document(root, document)

    with pytest.raises(lab.BrainstormLabError):
        lab.lab_status(root)
    with pytest.raises(lab.BrainstormLabError):
        lab.reset(root)
    with pytest.raises(lab.BrainstormLabError):
        lab.begin(root, ORIGIN, "sequel", "anchor-beta")


def test_receipt_provenance_null_is_accepted_and_blocks_nothing(tmp_path):
    # An all-null orphan provenance is the valid orphan shape and a legitimate
    # clean state; a subsequent begin is allowed.
    root = tmp_path / "lab"
    (root / lab.ACTIVE_DIRNAME).mkdir(parents=True)
    lab.reset(root)
    assert _receipt_document(root)["provenance"] is None

    assert lab.lab_status(root)["state"] == lab.STATE_CLEAN
    lock = lab.begin(root, ORIGIN, "sequel", "anchor-beta")
    assert lock["status"] == lab.STATE_ACTIVE


def test_journal_and_receipt_same_reset_id_different_provenance_fails_closed(tmp_path):
    root = tmp_path / "lab"
    lock = lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    reset_id = "d" * 32

    (root / lab.PENDING_FILENAME).write_text(
        json.dumps(_pending_doc(lock, reset_id=reset_id)), encoding="utf-8"
    )
    receipt = {
        "schema_version": lab.SCHEMA_VERSION,
        "receipt_kind": lab.RECEIPT_KIND,
        "reset_id": reset_id,
        "non_canon": True,
        "provenance": {
            "lab_id": "lab-" + "0" * 32,
            "mode": "prequel",
            "origin": dict(ORIGIN),
            "closed_outcome": None,
        },
        "verified_clean": True,
    }
    _write_receipt_document(root, receipt)

    with pytest.raises(lab.BrainstormLabError):
        lab.lab_status(root)
    with pytest.raises(lab.BrainstormLabError):
        lab.reset(root)


def test_lock_and_journal_disagreeing_provenance_fails_closed(tmp_path):
    root = tmp_path / "lab"
    lock = lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    document = _pending_doc(lock, reset_id="e" * 32)
    document["provenance"]["mode"] = "sequel"
    (root / lab.PENDING_FILENAME).write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(lab.BrainstormLabError):
        lab.lab_status(root)
    with pytest.raises(lab.BrainstormLabError):
        lab.reset(root)


def test_non_integer_retained_receipt_schema_version_fails_clean_proof(
    tmp_path
):
    root = _lab_with_committed_receipt(tmp_path)
    document = _receipt_document(root)
    document["schema_version"] = True
    _write_receipt_document(root, document)

    with pytest.raises(lab.BrainstormLabError):
        lab.lab_status(root)
    with pytest.raises(lab.BrainstormLabError):
        lab.begin(root, ORIGIN, "sequel", "anchor-beta")


@pytest.mark.parametrize("bad", [True, 1.0])
def test_non_integer_metadata_schema_versions_fail_closed(tmp_path, bad):
    # JSON true/1.0 compare equal to integer 1 in Python; the lock and journal
    # schema_version fields must require an exact int type.
    lock_root = tmp_path / "locklab"
    lab.begin(lock_root, ORIGIN, "prequel", "anchor-a")
    lock_file = lock_root / lab.LOCK_FILENAME
    lock_doc = json.loads(lock_file.read_text(encoding="utf-8"))
    lock_doc["schema_version"] = bad
    lock_file.write_text(json.dumps(lock_doc), encoding="utf-8")
    with pytest.raises(lab.BrainstormLabError):
        lab.lab_status(lock_root)

    journal_root = tmp_path / "journallab"
    lock = lab.begin(journal_root, ORIGIN, "prequel", "anchor-a")
    journal_doc = _pending_doc(lock, reset_id="f" * 32, schema_version=bad)
    (journal_root / lab.PENDING_FILENAME).write_text(
        json.dumps(journal_doc), encoding="utf-8"
    )
    with pytest.raises(lab.BrainstormLabError):
        lab.lab_status(journal_root)


def test_integer_lock_schema_version_is_accepted(tmp_path):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-a")
    lock_file = root / lab.LOCK_FILENAME
    document = json.loads(lock_file.read_text(encoding="utf-8"))
    document["schema_version"] = 1
    lock_file.write_text(json.dumps(document), encoding="utf-8")

    assert lab.lab_status(root)["state"] == lab.STATE_ACTIVE


def test_path_shaped_lab_id_fails_closed_without_touching_paths(tmp_path):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-a")
    lock_file = root / lab.LOCK_FILENAME
    document = json.loads(lock_file.read_text(encoding="utf-8"))
    document["lab_id"] = "../../escaped"
    lock_file.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(lab.BrainstormLabError):
        lab.lab_status(root)
    with pytest.raises(lab.BrainstormLabError):
        lab.reset(root)
    assert not (tmp_path / "escaped").exists()
    assert not (tmp_path.parent / "escaped").exists()


# --------------------------------------------------------------------------
# receipt is metadata only / no merge-back
# --------------------------------------------------------------------------

def test_narrative_anchor_never_enters_pending_or_receipt(tmp_path, monkeypatch):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "what_if", "anchor-with-story-secret")
    lab.write_lab_state(root, "scene/one.json", '{"secret": "STORY-PAYLOAD-MARKER"}')

    written = []
    real_write = lab._atomic_write_json

    def capture(path, document):
        written.append((Path(path).name, json.dumps(document)))
        real_write(path, document)

    monkeypatch.setattr(lab, "_atomic_write_json", capture)
    result = lab.reset(root)
    monkeypatch.setattr(lab, "_atomic_write_json", real_write)

    for name, text in written:
        assert name in (lab.PENDING_FILENAME, lab.RECEIPT_FILENAME)
        assert "anchor-with-story-secret" not in text
        assert "narrative_anchor" not in text
        assert "STORY-PAYLOAD-MARKER" not in text
    assert "anchor-with-story-secret" not in json.dumps(result["receipt"])
    assert "narrative_anchor" not in result["receipt"]
    assert "STORY-PAYLOAD-MARKER" not in (root / lab.RECEIPT_FILENAME).read_text(
        encoding="utf-8"
    )


def test_interrupted_pending_journal_has_no_story_payload(tmp_path, monkeypatch):
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-with-story-secret")
    lab.write_lab_state(root, "scene/one.json", '{"secret": "STORY-PAYLOAD-MARKER"}')

    real_rename = lab.os.rename

    def boom(*_args, **_kwargs):
        raise OSError("simulated interruption before rename")

    monkeypatch.setattr(lab.os, "rename", boom)
    with pytest.raises(OSError):
        lab.reset(root)
    monkeypatch.setattr(lab.os, "rename", real_rename)

    pending_text = (root / lab.PENDING_FILENAME).read_text(encoding="utf-8")
    assert "anchor-with-story-secret" not in pending_text
    assert "narrative_anchor" not in pending_text
    assert "STORY-PAYLOAD-MARKER" not in pending_text


def test_no_merge_back_or_canon_promotion_surface_exists():
    source = KERNEL_PATH.read_text(encoding="utf-8")
    for forbidden in ("merge_back", "mergeback", "promote", "canon_promote", "reconcile"):
        assert forbidden not in source
    names = {name for name in dir(lab) if not name.startswith("__")}
    assert not any("merge" in name or "promote" in name for name in names)


def test_kernel_has_no_runtime_or_sql_dependency():
    source = KERNEL_PATH.read_text(encoding="utf-8")
    for forbidden in ("supabase", "psycopg", "import sqlite3", "requests", "urllib"):
        assert forbidden not in source


# --------------------------------------------------------------------------
# no canonical surface is mutated
# --------------------------------------------------------------------------

def test_reality_registry_is_not_modified_by_lifecycle(tmp_path):
    registry_path = _primary_registry_path()
    before = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    root = tmp_path / "lab"
    lab.begin(root, ORIGIN, "prequel", "anchor-alpha")
    lab.close(root, "completed")
    lab.reset(root)
    after = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    assert before == after
    assert not (root / "registry").exists()


# --------------------------------------------------------------------------
# corpus is synthetic
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path", [KERNEL_PATH, DOC_PATH, TEST_PATH], ids=lambda p: p.name
)
def test_corpus_contains_only_synthetic_identities(path):
    text = path.read_text(encoding="utf-8").lower()
    for token in RHC_NAME_TOKENS:
        assert token not in text, f"{path.name} leaks RHC name {token!r}"


# --------------------------------------------------------------------------
# repository hygiene
# --------------------------------------------------------------------------

def test_git_diff_check_is_clean():
    assert _git("diff", "--check").returncode == 0
    assert _git("diff", "--cached", "--check").returncode == 0
