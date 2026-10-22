#!/usr/bin/env python3
"""POST-EV2-14 disposable NON-CANON brainstorm-lab lifecycle kernel.

Engine-side, repository-independent kernel for a **disposable, explicitly
NON-CANON** Prequel / Sequel / What-If exploration lab. A lab is always rooted
at a caller-supplied **disposable scratch root** outside canonical campaign /
runtime authority; this module never reads or writes canonical RHC campaign
state, the reality registry, or any published runtime surface.

Lifecycle (one active lab per campaign / lab root, V1)::

    CLEAN -> ACTIVE -> CLOSED(completed|aborted) -> TOMBSTONED/RESETTING -> CLEAN

Guarantees encoded here:

* ``begin`` requires a clean baseline and a well-formed exact origin receipt
  (stable campaign identity + checkpoint/revision identity). Narrative mode and
  narrative anchor are recorded **separately** from origin provenance.
* ``NON-CANON`` is structural: the lab lock always declares ``non_canon: true``.
* exactly one active lab per lab root: the lock is the single active-lab owner.
* ``close`` freezes the lab (one-way). A closed lab stays inspectable/readable
  while every write through the lab guard is refused.
* ``reset`` is proven as **one recoverable transaction**. A single durable
  recovery record -- ``reset.pending.json`` -- is written *before* any
  destructive step, disposable ``active/`` state is atomically renamed to the
  single fixed tombstone **before** it is deleted, the small reset receipt
  ``last-reset.json`` is durably committed (never rewriting an already-committed
  one), and only then are the recovery records removed. The single invariant is:
  *until final reset completion is mechanically provable, at least one valid
  bounded recovery record exists and the lab cannot classify as CLEAN or
  writable.* The next ``reset`` therefore converges deterministically to a
  verified clean baseline after any interruption.
* the reset receipt is small lifecycle/provenance metadata only -- no
  story/campaign payload. The narrative anchor does not survive.
* clean proof is structural, not an enumerated checklist of current kinds: no
  active subtree, no tombstone, no pending journal, no kernel-owned metadata temp
  residue, no unexpected lab-owned state. Only the lock and the latest receipt
  may survive.
* filesystem artifact names are fixed kernel constants. No per-lab identity is
  ever interpolated into a path, so corrupted metadata can never gain
  path-shaping power; origin campaign/checkpoint ids stay data.
* there is deliberately **no** merge-back / canon-promotion / reconciliation
  surface: a good lab idea reaches canon only through a separate, later,
  DM-authorized intake path.

Trust boundary: the caller supplies an already-verified exact origin receipt.
This kernel validates shape/coherence only; independent provider/remote
verification belongs to the caller/platform. Origin/source material is never
mutated -- the kernel writes only inside the supplied scratch root.

Runtime metadata model (all inside the disposable scratch root, none of it a
repository file):

``lab.lock.json``
    active/closed authority for the one V1 lab.

``reset.pending.json``
    the single durable recovery journal for one in-progress reset.

``active/``
    disposable writable subtree while ACTIVE.

``active.tombstone``
    the single fixed kernel-owned tombstone an interrupted reset may leave.

``last-reset.json``
    the latest reset receipt (metadata only).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import uuid
from pathlib import Path

SCHEMA_VERSION = 1

LOCK_FILENAME = "lab.lock.json"
PENDING_FILENAME = "reset.pending.json"
RECEIPT_FILENAME = "last-reset.json"
ACTIVE_DIRNAME = "active"
TOMBSTONE_PATHNAME = "active.tombstone"

MODES = ("prequel", "sequel", "what_if")
OUTCOMES = ("completed", "aborted")

STATE_CLEAN = "clean"
STATE_ACTIVE = "active"
STATE_CLOSED = "closed"
STATE_RESETTING = "resetting"

ORIGIN_KEYS = ("campaign_id", "checkpoint_id")

# Origin campaign/checkpoint ids are *data*, never filesystem path components,
# so their identity format stays intentionally broad. The kernel-generated lab
# id and reset id are pinned to their exact generated form so a corrupted
# retained value can never masquerade as a real kernel identity.
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
_LAB_ID_RE = re.compile(r"^lab-[0-9a-f]{32}$")
_RESET_ID_RE = re.compile(r"^[0-9a-f]{32}$")

# Kernel-owned atomic-write temp artifacts: ``.<target name>.<32 hex>.tmp``,
# created adjacent to their target. Only temps bound to a known kernel metadata
# target are recognized as recoverable residue; an arbitrary unknown temp-like
# file is never silently deleted.
_TEMP_RE = re.compile(r"^\.(?P<base>[A-Za-z0-9._-]+)\.(?P<token>[0-9a-f]{32})\.tmp$")
_OWNED_TEMP_BASES = frozenset({LOCK_FILENAME, PENDING_FILENAME, RECEIPT_FILENAME})

LOCK_KEYS = frozenset(
    {
        "schema_version",
        "lab_id",
        "non_canon",
        "status",
        "mode",
        "narrative_anchor",
        "origin",
        "closed_outcome",
    }
)

PENDING_KIND = "disposable_brainstorm_lab_reset_pending"

PENDING_KEYS = frozenset(
    {
        "schema_version",
        "pending_kind",
        "reset_id",
        "non_canon",
        "provenance",
        "had_active",
    }
)

RECEIPT_KIND = "disposable_brainstorm_lab_reset"

RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "receipt_kind",
        "reset_id",
        "non_canon",
        "provenance",
        "verified_clean",
    }
)

# Bounded provenance is one nested value -- either null or one complete object --
# so a partial/mixed tuple cannot exist structurally.
PROVENANCE_KEYS = frozenset({"lab_id", "mode", "origin", "closed_outcome"})


class BrainstormLabError(Exception):
    """Any lifecycle/precondition/coherence failure. Always fails closed."""


def _fail(message: str) -> "BrainstormLabError":
    return BrainstormLabError("BRAINSTORM LAB REFUSED: " + message)


# --------------------------------------------------------------------------
# Disposable scratch root (never canonical campaign/runtime authority)
# --------------------------------------------------------------------------

def _scratch_root(lab_root) -> Path:
    """Resolve and prepare the disposable scratch root, or fail closed.

    The root must not be inside a Git working tree: a canonical repository is
    implementation/campaign truth, not a disposable lab root, so a lab rooted
    inside one is refused rather than silently risking canon contamination.
    The check walks the resolved root and its ancestors for a ``.git`` entry.
    """
    root = Path(lab_root).resolve()
    if root.exists() and not root.is_dir():
        raise _fail(f"lab root exists and is not a directory: {str(root)!r}")
    for candidate in (root, *root.parents):
        if (candidate / ".git").exists():
            raise _fail(
                "lab root must be a disposable scratch root outside any Git "
                f"working tree, got {str(root)!r} inside {str(candidate)!r}"
            )
    root.mkdir(parents=True, exist_ok=True)
    return root


# --------------------------------------------------------------------------
# Validation of caller-supplied inputs
# --------------------------------------------------------------------------

def _validate_identity(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(f"{field} must be a non-empty string")
    value = value.strip()
    if not _IDENTITY_RE.match(value):
        raise _fail(f"{field} has an invalid identity format: {value!r}")
    return value


def _validate_lab_id(value, field: str = "lab_id") -> str:
    if not isinstance(value, str) or not _LAB_ID_RE.match(value):
        raise _fail(
            f"{field} must be a kernel-generated lab id (lab-<32 hex>): {value!r}"
        )
    return value


def _validate_reset_id(value, field: str) -> str:
    if not isinstance(value, str) or not _RESET_ID_RE.match(value):
        raise _fail(f"{field} must be a kernel-generated reset id (32 hex): {value!r}")
    return value


def validate_origin(origin_receipt) -> dict:
    """Validate an exact trusted origin/checkpoint receipt (shape only).

    A trusted caller/platform has already verified this receipt against its
    provider. The kernel only proves it is coherent: a stable campaign identity
    and a checkpoint/revision identity, both present and well-formed. No
    remote/provider lookup, no branch/filesystem/name inference, and no
    "latest checkpoint" resolution happens here.
    """
    if not isinstance(origin_receipt, dict):
        raise _fail("origin receipt must be an object")
    origin = {}
    for key in ORIGIN_KEYS:
        if key not in origin_receipt:
            raise _fail(f"origin receipt missing required field: {key}")
        origin[key] = _validate_identity(origin_receipt[key], f"origin.{key}")
    return origin


def _validate_mode(mode) -> str:
    if mode not in MODES:
        raise _fail(f"mode must be one of {list(MODES)}, got {mode!r}")
    return mode


def _validate_anchor(anchor) -> str:
    if not isinstance(anchor, str) or not anchor.strip():
        raise _fail("narrative anchor must be a non-empty string")
    return anchor


def _validate_outcome(outcome) -> str:
    if outcome not in OUTCOMES:
        raise _fail(f"close outcome must be one of {list(OUTCOMES)}, got {outcome!r}")
    return outcome


def _is_schema_version(value) -> bool:
    """Exact integer type + exact supported value.

    JSON ``true``/``false`` and floats such as ``1.0`` compare equal to the
    integer ``1`` in Python, so value equality alone is not enough: a malformed
    metadata document must fail closed on type as well as value.
    """
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and value == SCHEMA_VERSION
    )


def _validate_provenance(provenance, name: str):
    """Validate one coherent bounded-provenance value, or ``None``.

    The kernel persists only two canonical provenance shapes as a single nested
    value -- never four independently-optional siblings -- so an impossible
    mixed tuple cannot exist structurally:

    * ``None`` -- a legitimate orphan cleanup where no committed lab identity
      survived; or
    * ``{lab_id, mode, origin, closed_outcome}`` -- an identified lab, with
      ``closed_outcome`` either ``None`` (reset from an active lab) or a valid
      close outcome.
    """
    if provenance is None:
        return None
    if not isinstance(provenance, dict) or frozenset(provenance) != PROVENANCE_KEYS:
        raise _fail(
            f"{name}.provenance must be null or carry exactly "
            "lab_id + mode + origin + closed_outcome"
        )
    _validate_lab_id(provenance["lab_id"], f"{name}.provenance.lab_id")
    _validate_mode(provenance["mode"])
    origin = provenance["origin"]
    if not isinstance(origin, dict) or frozenset(origin) != frozenset(ORIGIN_KEYS):
        raise _fail(
            f"{name}.provenance.origin must carry exactly campaign_id + checkpoint_id"
        )
    for key in ORIGIN_KEYS:
        _validate_identity(origin[key], f"{name}.provenance.origin.{key}")
    if provenance["closed_outcome"] is not None:
        _validate_outcome(provenance["closed_outcome"])
    return provenance


def _validate_lock(lock: dict) -> None:
    keys = frozenset(lock)
    if keys != LOCK_KEYS:
        raise _fail(
            f"lab lock has unexpected shape; missing={sorted(LOCK_KEYS - keys)} "
            f"unknown={sorted(keys - LOCK_KEYS)}"
        )
    if not _is_schema_version(lock["schema_version"]):
        raise _fail(f"unsupported lab lock schema_version: {lock['schema_version']!r}")
    if lock["non_canon"] is not True:
        raise _fail("lab lock must declare non_canon: true")
    if lock["status"] not in (STATE_ACTIVE, STATE_CLOSED):
        raise _fail(f"lab lock status must be active or closed, got {lock['status']!r}")
    _validate_lab_id(lock["lab_id"], "lab_id")
    _validate_mode(lock["mode"])
    _validate_anchor(lock["narrative_anchor"])
    origin = lock["origin"]
    if not isinstance(origin, dict) or frozenset(origin) != frozenset(ORIGIN_KEYS):
        raise _fail("lab lock origin must carry exactly campaign_id + checkpoint_id")
    for key in ORIGIN_KEYS:
        _validate_identity(origin[key], f"origin.{key}")
    if lock["status"] == STATE_ACTIVE and lock["closed_outcome"] is not None:
        raise _fail("an active lab must not carry a close outcome")
    if lock["status"] == STATE_CLOSED and lock["closed_outcome"] not in OUTCOMES:
        raise _fail("a closed lab must carry a valid close outcome")


def _validate_pending(pending: dict) -> None:
    keys = frozenset(pending)
    if keys != PENDING_KEYS:
        raise _fail(
            f"reset journal has unexpected shape; missing={sorted(PENDING_KEYS - keys)} "
            f"unknown={sorted(keys - PENDING_KEYS)}"
        )
    if not _is_schema_version(pending["schema_version"]):
        raise _fail("reset journal has an unsupported schema_version")
    if pending["pending_kind"] != PENDING_KIND:
        raise _fail("reset journal has an unexpected kind")
    if pending["non_canon"] is not True:
        raise _fail("reset journal must declare non_canon: true")
    _validate_reset_id(pending["reset_id"], "reset journal reset_id")
    _validate_provenance(pending["provenance"], "reset journal")
    if not isinstance(pending["had_active"], bool):
        raise _fail("reset journal had_active must be a boolean")


def _validate_receipt(receipt, name: str) -> None:
    """Validate a retained reset receipt against the bounded metadata contract.

    A surviving reset receipt is lifecycle/provenance metadata only. Any
    corrupt, malformed, unknown-field or narrative/story-bearing receipt is
    rejected so a false clean status can never be claimed over it.
    """
    if not isinstance(receipt, dict):
        raise _fail(f"retained reset receipt must be a JSON object: {name}")
    keys = frozenset(receipt)
    if keys != RECEIPT_KEYS:
        raise _fail(
            f"retained reset receipt has unexpected shape: {name}; "
            f"missing={sorted(RECEIPT_KEYS - keys)} unknown={sorted(keys - RECEIPT_KEYS)}"
        )
    if not _is_schema_version(receipt["schema_version"]):
        raise _fail(f"retained reset receipt has unsupported schema_version: {name}")
    if receipt["receipt_kind"] != RECEIPT_KIND:
        raise _fail(f"retained reset receipt has an unexpected kind: {name}")
    if receipt["non_canon"] is not True:
        raise _fail(f"retained reset receipt must declare non_canon: true: {name}")
    _validate_reset_id(receipt["reset_id"], f"retained reset receipt reset_id ({name})")
    _validate_provenance(receipt["provenance"], f"retained reset receipt ({name})")
    if receipt["verified_clean"] is not True:
        raise _fail(f"retained reset receipt must record a verified clean baseline: {name}")


# --------------------------------------------------------------------------
# Read / write kernel metadata
# --------------------------------------------------------------------------

def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically, cleaning the temp on any failure.

    An ordinary exception (for example a failed ``os.replace``) removes this
    call's own temp so it is not left as false residue. A process that is killed
    mid-write (no exception handler runs) may leave the temp behind; that is
    recognized as kernel-owned transaction residue and cleaned by ``reset``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, path)
    except BaseException:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass
        raise


def _atomic_write_json(path: Path, document: dict) -> None:
    _atomic_write_text(path, json.dumps(document, indent=2, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _fail(f"lab metadata is unreadable or malformed: {path.name}: {exc}") from None
    if not isinstance(document, dict):
        raise _fail(f"lab metadata must be a JSON object: {path.name}")
    return document


def _read_lock(root: Path):
    path = root / LOCK_FILENAME
    if not path.exists():
        return None
    lock = _read_json(path)
    _validate_lock(lock)
    return lock


def _read_pending(root: Path):
    path = root / PENDING_FILENAME
    if not path.exists():
        return None
    pending = _read_json(path)
    _validate_pending(pending)
    return pending


def _read_receipt(root: Path):
    path = root / RECEIPT_FILENAME
    if not path.exists():
        return None
    receipt = _read_json(path)
    _validate_receipt(receipt, RECEIPT_FILENAME)
    return receipt


def _copy_provenance(provenance):
    if provenance is None:
        return None
    return {
        "lab_id": provenance["lab_id"],
        "mode": provenance["mode"],
        "origin": dict(provenance["origin"]),
        "closed_outcome": provenance["closed_outcome"],
    }


def _lock_provenance(lock):
    if lock is None:
        return None
    return _copy_provenance(
        {
            "lab_id": lock["lab_id"],
            "mode": lock["mode"],
            "origin": lock["origin"],
            "closed_outcome": lock["closed_outcome"],
        }
    )


# --------------------------------------------------------------------------
# Kernel-owned temp residue
# --------------------------------------------------------------------------

def _is_owned_temp_name(name: str) -> bool:
    """True for a kernel-owned metadata temp bound to a known kernel target."""
    match = _TEMP_RE.match(name)
    return match is not None and match.group("base") in _OWNED_TEMP_BASES


def _list_owned_temps(root: Path) -> list:
    if not root.exists():
        return []
    return sorted(
        entry
        for entry in root.iterdir()
        if entry.is_file() and _is_owned_temp_name(entry.name)
    )


def _discard_owned_temps(root: Path) -> None:
    for temp in _list_owned_temps(root):
        temp.unlink()


# --------------------------------------------------------------------------
# Structural validation / classification
# --------------------------------------------------------------------------

def _check_owned_state(root: Path) -> None:
    """Fail closed on any lab-root entry this kernel does not own or expect."""
    if not root.exists():
        return
    unexpected = []
    for entry in sorted(root.iterdir()):
        name = entry.name
        if name == LOCK_FILENAME:
            if not entry.is_file():
                unexpected.append(name)
            else:
                _validate_lock(_read_json(entry))
        elif name == PENDING_FILENAME:
            if not entry.is_file():
                unexpected.append(name)
            else:
                _validate_pending(_read_json(entry))
        elif name == RECEIPT_FILENAME:
            if not entry.is_file():
                unexpected.append(name)
            else:
                _validate_receipt(_read_json(entry), RECEIPT_FILENAME)
        elif name == ACTIVE_DIRNAME:
            if not entry.is_dir():
                unexpected.append(name)
        elif name == TOMBSTONE_PATHNAME:
            if not entry.is_dir():
                unexpected.append(name)
        elif _is_owned_temp_name(name):
            if not entry.is_file():
                unexpected.append(name)
        else:
            unexpected.append(name)
    if unexpected:
        raise _fail("unexpected state owned by the lab root: " + ", ".join(unexpected))


def _load_validated(root: Path):
    """Read and cross-check every kernel metadata record, or fail closed.

    Structural/reference coherence the reset transaction can never generate
    fails closed here: a fixed tombstone without a committed journal, an
    active subtree that coexists with a tombstone, a lock and journal that
    disagree on bounded provenance, or a committed receipt and journal that
    share a reset id but disagree on provenance.
    """
    _check_owned_state(root)
    lock = _read_lock(root)
    pending = _read_pending(root)
    receipt = _read_receipt(root)
    active = (root / ACTIVE_DIRNAME).is_dir()
    tombstone = (root / TOMBSTONE_PATHNAME).exists()
    temps = _list_owned_temps(root)

    if tombstone and pending is None:
        raise _fail("a fixed tombstone without a committed reset journal fails closed")
    if active and tombstone:
        raise _fail("an active subtree and a tombstone must never coexist")
    if lock is not None and pending is not None:
        if _lock_provenance(lock) != pending["provenance"]:
            raise _fail("the lab lock and reset journal disagree on bounded provenance")
    if (
        receipt is not None
        and pending is not None
        and receipt["reset_id"] == pending["reset_id"]
        and receipt["provenance"] != pending["provenance"]
    ):
        raise _fail("the committed reset receipt and journal disagree on provenance")
    return lock, pending, receipt, active, tombstone, temps


def _residue_lab_id(lock, pending):
    if pending is not None and pending["provenance"] is not None:
        return pending["provenance"]["lab_id"]
    if lock is not None:
        return lock["lab_id"]
    return None


# --------------------------------------------------------------------------
# Inspection
# --------------------------------------------------------------------------

def lab_status(lab_root) -> dict:
    """Return the current lifecycle state of the lab root.

    Never mutates. ``resetting`` means a reset transaction is in progress: a
    pending journal, a fixed tombstone, kernel-owned metadata temp residue, or a
    lock without its active subtree remains. It is inspectable and is finished
    by the next ``reset``, but is never treated as a live/active lab and is never
    writable.
    """
    root = _scratch_root(lab_root)
    lock, pending, _receipt, active, tombstone, temps = _load_validated(root)

    if pending is not None or tombstone or temps or (lock is not None and not active):
        return {
            "state": STATE_RESETTING,
            "lab_id": _residue_lab_id(lock, pending),
            "non_canon": True if (lock is not None or pending is not None) else None,
        }
    if lock is None and not active:
        return {"state": STATE_CLEAN, "lab_id": None, "non_canon": None}
    if lock is None or not active:
        return {
            "state": STATE_RESETTING,
            "lab_id": lock["lab_id"] if lock is not None else None,
            "non_canon": True if lock is not None else None,
        }
    return {
        "state": lock["status"],
        "lab_id": lock["lab_id"],
        "non_canon": True,
        "mode": lock["mode"],
        "narrative_anchor": lock["narrative_anchor"],
        "origin": dict(lock["origin"]),
        "closed_outcome": lock["closed_outcome"],
    }


# --------------------------------------------------------------------------
# Lifecycle operations
# --------------------------------------------------------------------------

def begin(lab_root, origin_receipt, mode, narrative_anchor) -> dict:
    """Open one ACTIVE, explicitly NON-CANON lab from an exact origin receipt.

    Refuses unless the lab root is in a clean baseline (no active subtree, no
    tombstone, no journal, no lock). The recorded origin provenance is kept
    strictly separate from the narrative mode/anchor.
    """
    root = _scratch_root(lab_root)
    origin = validate_origin(origin_receipt)
    mode_value = _validate_mode(mode)
    anchor = _validate_anchor(narrative_anchor)

    state = lab_status(root)
    if state["state"] != STATE_CLEAN:
        raise _fail(
            f"cannot begin: lab root is not clean (state={state['state']}); "
            "one active lab per campaign/lab root"
        )

    (root / ACTIVE_DIRNAME).mkdir(parents=True, exist_ok=False)
    lock = {
        "schema_version": SCHEMA_VERSION,
        "lab_id": f"lab-{uuid.uuid4().hex}",
        "non_canon": True,
        "status": STATE_ACTIVE,
        "mode": mode_value,
        "narrative_anchor": anchor,
        "origin": origin,
        "closed_outcome": None,
    }
    _atomic_write_json(root / LOCK_FILENAME, lock)
    return lock


def close(lab_root, outcome) -> dict:
    """Freeze an ACTIVE lab as CLOSED(completed|aborted); one-way.

    A closed lab stays readable/inspectable, but every lab write is refused.
    Repeating the same close (same outcome) is idempotent; a conflicting
    outcome is refused.
    """
    root = _scratch_root(lab_root)
    outcome_value = _validate_outcome(outcome)
    state = lab_status(root)
    if state["state"] == STATE_CLOSED:
        if state["closed_outcome"] == outcome_value:
            return _read_lock(root)
        raise _fail(
            "lab is already closed with a different outcome "
            f"({state['closed_outcome']!r}); close is one-way"
        )
    if state["state"] != STATE_ACTIVE:
        raise _fail(f"cannot close: lab is not active (state={state['state']})")

    lock = _read_lock(root)
    lock["status"] = STATE_CLOSED
    lock["closed_outcome"] = outcome_value
    _atomic_write_json(root / LOCK_FILENAME, lock)
    return lock


def reset(lab_root) -> dict:
    """Return the lab root to a verified clean baseline.

    Reset is one explicit recoverable transaction:

    1. durably write (or resume) the single bounded recovery journal
       ``reset.pending.json`` before any destructive step, so every later
       interruption classifies as ``resetting`` -- never a false
       ACTIVE/CLOSED/CLEAN;
    2. tombstone-before-delete: atomically rename disposable ``active/`` state to
       the single fixed tombstone, then delete it;
    3. durably commit ``last-reset.json`` -- unless it already carries this
       transaction's ``reset_id``, in which case it is validated and **not**
       rewritten;
    4. only then remove the lock and journal (the recovery records);

    followed by a structural clean proof. An incomplete prior reset is detected
    and deterministically finished. Reset from an already-clean root is a safe,
    idempotent no-op that writes no new receipt. A surviving receipt carries only
    lifecycle/provenance metadata -- never campaign/story payload.
    """
    root = _scratch_root(lab_root)
    lock, pending, receipt, active, tombstone, _temps = _load_validated(root)
    # Owned temp residue is uncommitted by construction; the committed records
    # (lock/journal/receipt) remain authority, so it is safe to discard it.
    _discard_owned_temps(root)

    # A root with only the latest receipt (or nothing) is already clean.
    if lock is None and pending is None and not active and not tombstone:
        return {"state": STATE_CLEAN, "already_clean": True, "receipt": None}

    # The journal (if present) is the transaction authority; the lock is the
    # pre-transaction record. Recover the one bounded provenance.
    if pending is not None:
        provenance = _copy_provenance(pending["provenance"])
    else:
        provenance = _lock_provenance(lock)

    # Start the durable transaction before any destructive step.
    if pending is None:
        pending = {
            "schema_version": SCHEMA_VERSION,
            "pending_kind": PENDING_KIND,
            "reset_id": uuid.uuid4().hex,
            "non_canon": True,
            "provenance": _copy_provenance(provenance),
            "had_active": active,
        }
        _atomic_write_json(root / PENDING_FILENAME, pending)

    reset_id = pending["reset_id"]
    provenance = _copy_provenance(pending["provenance"])

    # Tombstone-before-delete.
    active_path = root / ACTIVE_DIRNAME
    tombstone_path = root / TOMBSTONE_PATHNAME
    if active:
        os.rename(active_path, tombstone_path)
    if tombstone_path.exists():
        shutil.rmtree(tombstone_path)

    # Commit the final receipt from the journal only. A receipt that already
    # carries this transaction's reset_id is committed evidence and is never
    # rewritten; an older receipt is replaced atomically.
    desired = {
        "schema_version": SCHEMA_VERSION,
        "receipt_kind": RECEIPT_KIND,
        "reset_id": reset_id,
        "non_canon": True,
        "provenance": provenance,
        "verified_clean": True,
    }
    if receipt is None or receipt["reset_id"] != reset_id:
        _atomic_write_json(root / RECEIPT_FILENAME, desired)
    committed = _read_receipt(root)

    # Remove the recovery records LAST: from here the transaction is complete.
    lock_path = root / LOCK_FILENAME
    pending_path = root / PENDING_FILENAME
    if lock_path.exists():
        lock_path.unlink()
    if pending_path.exists():
        pending_path.unlink()

    # Final structural clean proof: no active subtree, no tombstone, no lock, no
    # journal, no owned temp residue, no unexpected lab-owned state.
    _check_owned_state(root)
    if (
        active_path.exists()
        or tombstone_path.exists()
        or lock_path.exists()
        or pending_path.exists()
    ):
        raise _fail("reset failed to reach a clean baseline")

    return {"state": STATE_CLEAN, "already_clean": False, "receipt": committed}


# --------------------------------------------------------------------------
# Lab guard (writable only while ACTIVE; readable while ACTIVE or CLOSED)
# --------------------------------------------------------------------------

def _confined_path(root: Path, relative_path) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise _fail("lab state path must be a non-empty string")
    if "\\" in relative_path:
        raise _fail("lab state path must use repository-relative POSIX separators")
    relative = Path(relative_path)
    if relative.is_absolute():
        raise _fail("lab state path must be relative to the active subtree")
    if any(part in ("..", "") for part in relative.parts):
        raise _fail("lab state path must not escape the active subtree")
    active = root / ACTIVE_DIRNAME
    target = (active / relative).resolve()
    if os.path.commonpath([str(target), str(active.resolve())]) != str(active.resolve()):
        raise _fail("lab state path must not escape the active subtree")
    return target


def assert_writable(lab_root) -> Path:
    """Return the ACTIVE subtree or refuse; the lab writable guard."""
    root = _scratch_root(lab_root)
    state = lab_status(root)
    if state["state"] != STATE_ACTIVE:
        raise _fail(f"lab is not writable (state={state['state']}); writes are CLOSED")
    return root / ACTIVE_DIRNAME


def write_lab_state(lab_root, relative_path, data) -> Path:
    """Write a disposable lab state file through the writable guard."""
    active = assert_writable(lab_root)
    target = _confined_path(active.parent, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    target.write_bytes(payload)
    return target


def read_lab_state(lab_root, relative_path) -> bytes:
    """Read a lab state file while the lab is ACTIVE or CLOSED (inspectable)."""
    root = _scratch_root(lab_root)
    state = lab_status(root)
    if state["state"] not in (STATE_ACTIVE, STATE_CLOSED):
        raise _fail(f"lab state is not available (state={state['state']})")
    target = _confined_path(root, relative_path)
    if not target.is_file():
        raise _fail(f"no such lab state file: {relative_path!r}")
    return target.read_bytes()


def list_lab_state(lab_root) -> list:
    """List disposable lab state files (relative, sorted) for inspection."""
    root = _scratch_root(lab_root)
    active = root / ACTIVE_DIRNAME
    if not active.is_dir():
        return []
    return sorted(
        path.relative_to(active).as_posix()
        for path in active.rglob("*")
        if path.is_file()
    )


# --------------------------------------------------------------------------
# CLI (inspection/lifecycle convenience; not an authority surface)
# --------------------------------------------------------------------------

def _emit(document) -> None:
    print(json.dumps(document, indent=2, sort_keys=True))


def main(argv) -> int:
    parser = argparse.ArgumentParser(
        description="Disposable NON-CANON brainstorm-lab lifecycle kernel"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_begin = sub.add_parser("begin")
    p_begin.add_argument("lab_root")
    p_begin.add_argument("--origin", required=True, help="origin receipt JSON file")
    p_begin.add_argument("--mode", required=True, choices=list(MODES))
    p_begin.add_argument("--anchor", required=True)

    p_close = sub.add_parser("close")
    p_close.add_argument("lab_root")
    p_close.add_argument("--outcome", required=True, choices=list(OUTCOMES))

    p_reset = sub.add_parser("reset")
    p_reset.add_argument("lab_root")

    p_status = sub.add_parser("status")
    p_status.add_argument("lab_root")

    args = parser.parse_args(argv)
    try:
        if args.command == "begin":
            origin = json.loads(Path(args.origin).read_text(encoding="utf-8"))
            _emit(begin(args.lab_root, origin, args.mode, args.anchor))
        elif args.command == "close":
            _emit(close(args.lab_root, args.outcome))
        elif args.command == "reset":
            _emit(reset(args.lab_root))
        else:
            _emit(lab_status(args.lab_root))
    except BrainstormLabError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
