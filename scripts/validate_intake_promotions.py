#!/usr/bin/env python3
"""Validate Canon Intake promotion instructions + receipts (CI-04).

Usage:
    python scripts/validate_intake_promotions.py <candidates-directory> <decision-directory> <material-directory> <collision-directory> <promotion-directory> [<promotion-directory> ...]

The first four directories are the CI-01 candidate batch, the CI-02 decision
set, the CI-02.1 material set and the CI-03 collision set (each validated by
its own contract first). Every following directory holds CI-04 promotion
records that together form ONE validated promotion set. A promotion set
contains both promotion instructions (identified by ``promotion_id``) and
promotion receipts (identified by ``receipt_id``); a receipt also carries the
``promotion_id`` it resolves.

CI-04 is a bridge, never a publisher. This validator owns:

- deterministic eligibility validation (a classified, explicitly human-
  approved candidate with an exact CI-03 ``clear`` result);
- deterministic explicit route/owner resolution from a fixed registry;
- promotion instruction construction/validation;
- promotion receipt schema/validation, including route-conditional
  authoritative read-back evidence;
- an adapter/interface boundary proving the bridge only hands work to an
  already-authoritative route, gated on FULL validation: an adapter is never
  handed a raw/unvalidated instruction, and the receipt it returns is
  validated before being exposed as success.

It does NOT duplicate RT01 SAVE logic, perform raw SQL DML, push to
``runtime-published``, invent a second generation counter or repository
mutation authority, silently edit arbitrary repository files, auto-resolve
CI-03 non-clear results, or promote a real RHC campaign candidate. The caller
(and, for real routes, the owners of the RT01 Save Gateway / repository-
authorized path) performs any write; CI-04 only prepares and validates the
instruction and receipt contract.
"""
import json
import re
import sys
import weakref
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_entities as shared  # noqa: E402
import validate_intake_candidates as candidates  # noqa: E402
import validate_intake_candidate_material as material  # noqa: E402
import validate_intake_collisions as collisions  # noqa: E402
import validate_intake_decisions as decisions  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INSTRUCTION_SCHEMA_PATH = ROOT / "schemas" / "intake_promotion.schema.json"
RECEIPT_SCHEMA_PATH = ROOT / "schemas" / "intake_promotion_receipt.schema.json"

READ_HOOKS = candidates.READ_HOOKS

ROUTE_VOCABULARY = ("runtime_save", "repository_canon")
OUTCOME_VOCABULARY = ("success", "failure")

# The explicit, fixed route registry. A route is a name for an existing
# authoritative owner; CI-04 never implements the owner itself and never
# guesses an owner from target prose. Unknown/unregistered routes fail closed.
ROUTE_AUTHORITIES = {
    "runtime_save": "RT01 Save Gateway",
    "repository_canon": "repository-authorized canon owner path",
}

_SHA_40 = re.compile(r"^[0-9a-f]{40}$")


class PromotionError(Exception):
    """A CI-04 bridge contract violation. Always fails closed."""


# --------------------------------------------------------------------------
# Schemas / records
# --------------------------------------------------------------------------

def load_schema(schema_path=INSTRUCTION_SCHEMA_PATH):
    """Return the parsed promotion-instruction JSON Schema."""
    return candidates.load_schema(schema_path)


def load_receipt_schema(schema_path=RECEIPT_SCHEMA_PATH):
    """Return the parsed promotion-receipt JSON Schema."""
    return candidates.load_schema(schema_path)


def validate_record(record, schema):
    """Return a list of human-readable error strings for one record (empty if valid)."""
    return candidates.validate_record(record, schema)


def read_record(path):
    """Read one JSON record through the shared fail-closed parse hooks."""
    return candidates.read_record(path)


def classify_promotion_record(record):
    """Return 'instruction', 'receipt', or None when the record is unclassifiable.

    A receipt is identified by its ``receipt_id`` and also carries the
    ``promotion_id`` it resolves (the instruction it references), so presence of
    ``promotion_id`` alone must not be mistaken for an instruction. A record
    with ``receipt_id`` is a receipt; otherwise a record with ``promotion_id``
    is an instruction; neither is unclassifiable and fails closed.
    """
    if not isinstance(record, dict):
        return None
    if "receipt_id" in record:
        return "receipt"
    if "promotion_id" in record:
        return "instruction"
    return None


# --------------------------------------------------------------------------
# Explicit route / owner resolution (never inferred from prose)
# --------------------------------------------------------------------------

def route_authority(route):
    """Resolve an explicit route class to its already-authoritative owner.

    The route vocabulary is closed and fixed. An unknown, missing, or
    non-string route fails closed rather than being treated as safe or as a
    generic write path.
    """
    if not isinstance(route, str) or route not in ROUTE_AUTHORITIES:
        raise PromotionError(f"unknown or unresolved promotion route: {route!r}")
    return ROUTE_AUTHORITIES[route]


# --------------------------------------------------------------------------
# Semantic helpers
# --------------------------------------------------------------------------

def evidence_error(route, evidence):
    """Return a fail-closed error string when success evidence is insufficient.

    A success receipt must carry authoritative read-back evidence sufficient to
    identify the durable identity the authoritative owner produced for the
    route, and that evidence must be verifier-confirmed. A write attempt with
    no confirmed read-back is incomplete/failure, never success.
    """
    if not isinstance(evidence, dict):
        return (
            f"a successful {route} receipt requires authoritative read-back "
            f"evidence; none was provided"
        )
    if evidence.get("confirmed") is not True:
        return (
            "promotion success evidence must be verifier-confirmed "
            "(confirmed: true); an unconfirmed result is not success"
        )
    if route == "runtime_save":
        if evidence.get("kind") != "runtime_publication":
            return "runtime_save success requires runtime_publication evidence"
        generation = evidence.get("generation")
        if isinstance(generation, bool) or not isinstance(generation, int) \
                or generation < 1:
            return (
                "runtime_save success evidence requires a positive published "
                "generation"
            )
        git_ref = evidence.get("git_ref")
        if not isinstance(git_ref, str) or _SHA_40.match(git_ref) is None:
            return (
                "runtime_save success evidence requires an exact confirmed "
                "runtime-published git_ref (40-hex)"
            )
    elif route == "repository_canon":
        if evidence.get("kind") != "repository_commit":
            return "repository_canon success requires repository_commit evidence"
        commit = evidence.get("commit")
        if not isinstance(commit, str) or _SHA_40.match(commit) is None:
            return (
                "repository_canon success evidence requires an exact repository "
                "commit (40-hex)"
            )
    else:
        return f"unknown or unresolved promotion route: {route!r}"
    return None


def target_binding_error(instruction, material_record):
    """Return a fail-closed error when resolved_target is not the proposed target.

    The instruction's resolved_target must exactly equal the referenced CI-02.1
    material envelope's proposed_target (kind + reference). A mismatch is a
    silent reroute to a different owner than the candidate proposed.
    """
    proposed = material_record.get("proposed_target")
    resolved = instruction.get("resolved_target")
    if proposed is None:
        return (
            "candidate material envelope has no proposed_target; a promotion "
            "cannot resolve an explicit owner target"
        )
    if not isinstance(resolved, dict):
        return "promotion resolved_target must be an object"
    if (resolved.get("kind"), resolved.get("reference")) != (
        proposed.get("kind"), proposed.get("reference")
    ):
        return (
            f"resolved_target {resolved.get('kind')!r}:"
            f"{resolved.get('reference')!r} does not match the candidate's "
            f"proposed_target {proposed.get('kind')!r}:"
            f"{proposed.get('reference')!r}; promotion must not reroute the "
            f"proposed target"
        )
    return None


# --------------------------------------------------------------------------
# Validated upstream context (the dispatch gate's evidence)
# --------------------------------------------------------------------------

class _ValidationLookups:
    """Internal per-set lookups; not a dispatch credential."""

    def __init__(self, referenceable, candidate_status, approved,
                 decisions_by_id, materials_by_candidate, collisions_by_id):
        self.referenceable = referenceable
        self.candidate_status = candidate_status
        self.approved = approved
        self.decisions_by_id = decisions_by_id
        self.materials_by_candidate = materials_by_candidate
        self.collisions_by_id = collisions_by_id

    def instruction_errors(self, instruction):
        """Full eligibility/lineage/target/route errors for one instruction.

        Includes schema validation and every CI-04 eligibility rule, so an
        empty result means the instruction is fully validated and safe to hand
        to an authoritative adapter.
        """
        errors = validate_record(instruction, load_schema())
        if errors:
            return errors
        return instruction_semantic_errors(instruction, self)

    def receipt_errors(self, receipt, instruction):
        """Binding + authoritative-evidence errors for one receipt.

        The receipt must bind to the exact instruction it claims (candidate and
        route), and a success must carry route-sufficient confirmed read-back
        evidence. A failure must not carry success evidence. An empty result
        means the receipt is safe to expose as the route outcome.
        """
        errors = validate_record(receipt, load_receipt_schema())
        if errors:
            return errors
        if receipt["promotion_id"] != instruction["promotion_id"]:
            errors.append(
                f"receipt promotion_id '{receipt['promotion_id']}' does not "
                f"match promotion instruction '{instruction['promotion_id']}'"
            )
        if receipt["candidate_id"] != instruction["candidate_id"]:
            errors.append(
                f"receipt candidate_id '{receipt['candidate_id']}' does not "
                f"match promotion instruction candidate "
                f"'{instruction['candidate_id']}'"
            )
        if receipt["route"] != instruction["route"]:
            errors.append(
                f"receipt route '{receipt['route']}' does not match the "
                f"promotion instruction route '{instruction['route']}'; a "
                f"receipt must record the route actually used"
            )
        if receipt["outcome"] == "success":
            problem = evidence_error(receipt["route"], receipt.get("evidence"))
            if problem is not None:
                errors.append(problem)
        elif receipt.get("evidence") is not None:
            errors.append(
                "a failure receipt must not carry success evidence; failure "
                "must never masquerade as success"
            )
        return errors


class PromotionContext:
    """Opaque, factory-issued handle for one validated upstream/instruction snapshot.

    No caller-supplied maps or writable attributes are trusted for dispatch.
    The immutable proof bytes live only in the module's weak registry.
    """

    __slots__ = ("__weakref__",)

    def __new__(cls, *args, **kwargs):
        raise PromotionError("PromotionContext must be issued by build_context")

    def __setattr__(self, name, value):
        raise PromotionError("PromotionContext is immutable")


_CONTEXT_PROOFS = weakref.WeakKeyDictionary()


def _json_bytes(value):
    """Freeze JSON data without retaining any caller-owned mutable references."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _snapshot_lookups(snapshot):
    """Derive private lookups solely from the validated immutable record bytes."""
    candidate_records, decision_records, material_records, collision_records = (
        [json.loads(raw, **READ_HOOKS) for raw in records]
        for records in snapshot
    )
    referenceable = {record["candidate_id"] for record in candidate_records}
    status = {record["candidate_id"]: record["status"]
              for record in candidate_records}
    decisions_by_id = {record["decision_id"]: record
                       for record in decision_records}
    approved = {record["candidate_id"]: record["outcome"]
                for record in decision_records
                if record["authority"] == "human" and record["outcome"] == "approved"}
    materials_by_candidate = {record["candidate_id"]: record
                              for record in material_records}
    collisions_by_id = {record["collision_id"]: record
                        for record in collision_records}
    return _ValidationLookups(referenceable, status, approved, decisions_by_id,
                              materials_by_candidate, collisions_by_id)


def instruction_semantic_errors(instruction, context):
    """The CI-04 eligibility/lineage/target/route rules for one instruction.

    Caller must already have confirmed the instruction is schema-valid, so the
    required keys are present and typed.
    """
    errors = []
    candidate_id = instruction["candidate_id"]

    if candidate_id not in context.referenceable:
        errors.append(
            f"candidate_id '{candidate_id}' does not resolve to a valid "
            f"CI-01 candidate in the candidate batch"
        )
    elif context.candidate_status.get(candidate_id) != "classified":
        errors.append(
            f"candidate_id '{candidate_id}' is "
            f"'{context.candidate_status.get(candidate_id)}'; only classified "
            f"candidates are promotion-eligible"
        )
    elif candidate_id not in context.approved:
        errors.append(
            f"candidate_id '{candidate_id}' has no valid explicit "
            f"human-approved CI-02 decision; only approved candidates "
            f"are promotion-eligible"
        )

    decision = context.decisions_by_id.get(instruction["decision_id"])
    if decision is None:
        errors.append(
            f"decision_id '{instruction['decision_id']}' does not resolve to "
            f"a valid CI-02 decision in the decision set"
        )
    elif decision["candidate_id"] != candidate_id:
        errors.append(
            f"decision_id '{instruction['decision_id']}' belongs to candidate "
            f"'{decision['candidate_id']}', not '{candidate_id}'; "
            f"promotion lineage must bind one candidate"
        )
    elif decision["outcome"] != "approved":
        errors.append(
            f"decision_id '{instruction['decision_id']}' is "
            f"'{decision['outcome']}'; promotion requires an explicit "
            f"human approval"
        )

    collision = context.collisions_by_id.get(instruction["collision_id"])
    if collision is None:
        errors.append(
            f"collision_id '{instruction['collision_id']}' does not resolve "
            f"to a valid CI-03 collision result in the collision set"
        )
    elif collision["candidate_id"] != candidate_id:
        errors.append(
            f"collision_id '{instruction['collision_id']}' belongs to "
            f"candidate '{collision['candidate_id']}', not "
            f"'{candidate_id}'; promotion lineage must bind one candidate"
        )
    elif collision["result"] != "clear":
        errors.append(
            f"collision_id '{instruction['collision_id']}' result is "
            f"'{collision['result']}'; only a clear collision result is "
            f"promotion-eligible"
        )

    envelope = context.materials_by_candidate.get(candidate_id)
    if envelope is None:
        errors.append(
            f"candidate_id '{candidate_id}' has no valid CI-02.1 "
            f"material envelope; promotion requires candidate material"
        )
    else:
        if instruction["material_type"] != envelope["material_type"]:
            errors.append(
                f"material_type '{instruction['material_type']}' does not "
                f"match the candidate material envelope's "
                f"'{envelope['material_type']}'"
            )
        binding = target_binding_error(instruction, envelope)
        if binding is not None:
            errors.append(binding)

    try:
        route_authority(instruction["route"])
    except PromotionError as exc:
        errors.append(str(exc))

    return errors


def _upstream_maps(candidate_paths, decision_paths, material_paths,
                   collision_paths, candidate_failures, decision_failures,
                   material_failures, collision_failures):
    """Build read-only lookups from the valid upstream CI records."""
    referenceable = material.referenceable_candidates(
        candidate_paths, candidate_failures
    )
    candidate_status = {}
    for path in candidate_paths:
        if path in candidate_failures:
            continue
        record = read_record(path)
        candidate_status[record["candidate_id"]] = record["status"]

    decisions_by_id = {}
    for path in decision_paths:
        if path in decision_failures:
            continue
        record = read_record(path)
        decisions_by_id[record["decision_id"]] = record

    materials_by_candidate = {}
    for path in material_paths:
        if path in material_failures:
            continue
        record = read_record(path)
        materials_by_candidate[record["candidate_id"]] = record

    collisions_by_id = {}
    for path in collision_paths:
        if path in collision_failures:
            continue
        record = read_record(path)
        collisions_by_id[record["collision_id"]] = record

    return (referenceable, candidate_status, decisions_by_id,
            materials_by_candidate, collisions_by_id)


def build_context(candidate_paths, decision_paths, material_paths,
                  collision_paths, instruction):
    """Issue an opaque context for exactly one validated instruction and input set.

    Byte snapshots bracket upstream validation: a changed input cannot be
    silently substituted between validation and dispatch. Only the frozen
    snapshot is used thereafter, including for the instruction handed off.
    """
    path_sets = tuple(tuple(paths) for paths in (
        candidate_paths, decision_paths, material_paths, collision_paths))
    candidate_paths, decision_paths, material_paths, collision_paths = path_sets
    before = tuple(tuple(Path(path).read_bytes() for path in paths)
                   for paths in path_sets)
    (candidate_failures, decision_failures, material_failures,
     collision_failures) = collisions.validate_paths(
        candidate_paths, decision_paths, material_paths, collision_paths,
        schema_path=collisions.SCHEMA_PATH,
    )
    if candidate_failures or decision_failures or material_failures \
            or collision_failures:
        raise PromotionError(
            "cannot build a CI-04 promotion context from an invalid upstream "
            "CI-01/02/02.1/03 set"
        )
    if before != tuple(tuple(Path(path).read_bytes() for path in paths)
                       for paths in path_sets):
        raise PromotionError("upstream records changed during validation")
    snapshot = tuple(tuple(_json_bytes(json.loads(raw.decode("utf-8"),
                                                  **READ_HOOKS)) for raw in records)
                     for records in before)
    try:
        instruction_bytes = _json_bytes(instruction)
    except (TypeError, ValueError) as exc:
        raise PromotionError(f"invalid promotion instruction JSON: {exc}") from None
    lookups = _snapshot_lookups(snapshot)
    errors = lookups.instruction_errors(json.loads(instruction_bytes, **READ_HOOKS))
    if errors:
        raise PromotionError("cannot seal an invalid promotion instruction: "
                             + "; ".join(errors))
    context = object.__new__(PromotionContext)
    _CONTEXT_PROOFS[context] = (snapshot, instruction_bytes)
    return context


# --------------------------------------------------------------------------
# Adapter / interface boundary (the bridge hands work to an existing owner)
# --------------------------------------------------------------------------

class PromotionRouteAdapter:
    """Boundary the bridge hands a validated promotion instruction to.

    A route adapter stands in front of an already-authoritative owner (the
    RT01 Save Gateway for ``runtime_save``, the repository-authorized canon
    owner path for ``repository_canon``). CI-04 never implements persistence:
    it only dispatches a fully validated instruction to a registered adapter
    and consumes the receipt that adapter returns, after validating it. Real
    adapters belong to their authoritative lane; tests supply synthetic
    adapters that emulate success/failure/read-back.
    """

    route = None

    def execute(self, instruction):  # pragma: no cover - interface only
        raise NotImplementedError


def dispatch_promotion(instruction, adapters, context):
    """Hand one fully validated promotion instruction to its authoritative adapter.

    Gating is the whole point: the bridge owns no write mechanism and must
    never execute an adapter from a raw/unvalidated instruction. Before any
    adapter runs it proves, against a validated :class:`PromotionContext`, that
    the instruction has a classified candidate, an explicit human approval, an
    exact CI-03 ``clear`` result, correctly bound candidate/material/decision/
    collision lineage, a resolved target matching the proposed target, and a
    legal explicit route. After the adapter returns, the receipt is validated
    (binding + route + authoritative read-back evidence) before it is exposed;
    a malformed, incomplete, or forged success fails closed.
    """
    if type(context) is not PromotionContext or context not in _CONTEXT_PROOFS:
        raise PromotionError(
            "dispatch requires a fully validated CI-04 promotion context; a "
            "raw or unvalidated instruction is never dispatched"
        )
    if not isinstance(instruction, dict):
        raise PromotionError("promotion instruction must be an object")

    snapshot, instruction_bytes = _CONTEXT_PROOFS[context]
    try:
        current_bytes = _json_bytes(instruction)
    except (TypeError, ValueError) as exc:
        raise PromotionError(f"invalid promotion instruction JSON: {exc}") from None
    if current_bytes != instruction_bytes:
        raise PromotionError("instruction differs from its validated snapshot")
    checked_instruction = json.loads(instruction_bytes, **READ_HOOKS)
    lookups = _snapshot_lookups(snapshot)
    validation_errors = lookups.instruction_errors(checked_instruction)
    if validation_errors:
        raise PromotionError(
            "refusing to dispatch an invalid promotion instruction: "
            + "; ".join(validation_errors)
        )

    route = checked_instruction["route"]
    route_authority(route)
    if not isinstance(adapters, dict):
        raise PromotionError("adapters must be a mapping of route -> adapter")
    adapter = adapters.get(route)
    if adapter is None:
        raise PromotionError(
            f"no authoritative adapter registered for route {route!r}"
        )
    if getattr(adapter, "route", None) != route:
        raise PromotionError(
            f"adapter for route {route!r} declares route "
            f"{getattr(adapter, 'route', None)!r}"
        )

    receipt = adapter.execute(json.loads(instruction_bytes, **READ_HOOKS))

    # Freeze the adapter's result immediately, BEFORE validating it. The
    # adapter still owns the object it returned, so snapshot to canonical JSON
    # bytes first: a later mutation of that live object can then never change
    # what CI-04 validates or exposes. Validate and return this exact frozen
    # snapshot -- never validate the adapter-owned mutable object and then read
    # or copy it again.
    try:
        frozen_receipt = _json_bytes(receipt)
    except (TypeError, ValueError) as exc:
        raise PromotionError(
            f"invalid promotion receipt returned by the adapter: {exc}"
        ) from None
    checked_receipt = json.loads(frozen_receipt, **READ_HOOKS)

    receipt_errors = lookups.receipt_errors(checked_receipt, checked_instruction)
    if receipt_errors:
        raise PromotionError(
            "refusing to expose an invalid promotion receipt as success: "
            + "; ".join(receipt_errors)
        )
    return checked_receipt


# --------------------------------------------------------------------------
# Set validation
# --------------------------------------------------------------------------

def validate_paths(candidate_paths, decision_paths, material_paths,
                   collision_paths, promotion_paths,
                   instruction_schema_path=INSTRUCTION_SCHEMA_PATH,
                   receipt_schema_path=RECEIPT_SCHEMA_PATH):
    """Validate one promotion set against the CI-01/02/02.1/03 inputs.

    Returns (candidate_failures, decision_failures, material_failures,
    collision_failures, promotion_failures): dicts {path: [errors]} containing
    only paths with at least one error.
    """
    instruction_schema = load_schema(instruction_schema_path)
    receipt_schema = load_schema(receipt_schema_path)

    (candidate_failures, decision_failures, material_failures,
     collision_failures) = collisions.validate_paths(
        candidate_paths, decision_paths, material_paths, collision_paths,
        schema_path=collisions.SCHEMA_PATH,
    )

    (referenceable, candidate_status, decisions_by_id,
     materials_by_candidate, collisions_by_id) = _upstream_maps(
        candidate_paths, decision_paths, material_paths, collision_paths,
        candidate_failures, decision_failures, material_failures,
        collision_failures,
    )

    approved = collisions.approved_candidate_ids(
        candidate_paths, candidate_failures, decision_paths, decision_failures
    )
    context = _ValidationLookups(referenceable, candidate_status, approved,
                                 decisions_by_id, materials_by_candidate,
                                 collisions_by_id)

    # Pass 1: read + classify + validate every promotion record.
    parsed = []
    promotion_failures = {}
    for path in promotion_paths:
        try:
            record = read_record(path)
        except UnicodeDecodeError as exc:
            promotion_failures[path] = [f"invalid UTF-8: {exc}"]
            continue
        except (json.JSONDecodeError, ValueError) as exc:
            promotion_failures[path] = [f"invalid JSON: {exc}"]
            continue

        kind = classify_promotion_record(record)
        if kind == "instruction":
            errors = validate_record(record, instruction_schema)
            if not errors:
                errors.extend(instruction_semantic_errors(record, context))
        elif kind == "receipt":
            errors = validate_record(record, receipt_schema)
        else:
            errors = [
                "promotion record must be exactly one of a promotion "
                "instruction (promotion_id) or a promotion receipt (receipt_id); "
                "a record with both or neither fails closed"
            ]
        parsed.append((path, kind, record, errors))

    # Build the map of valid instructions so receipts can resolve them.
    instructions_by_id = {}
    for _path, kind, record, errors in parsed:
        if kind == "instruction" and not errors:
            instructions_by_id.setdefault(record["promotion_id"], record)

    # Pass 2a: instruction set-level replay law.
    seen_promotion_ids = {}
    seen_instruction_candidates = {}
    for path, kind, record, errors in parsed:
        if kind != "instruction":
            continue
        if not errors:
            promotion_id = record["promotion_id"]
            candidate_id = record["candidate_id"]

            if promotion_id in seen_promotion_ids:
                errors.append(
                    f"promotion_id '{promotion_id}' duplicates "
                    f"{seen_promotion_ids[promotion_id].name}; duplicate "
                    f"promotion instructions fail closed"
                )
            else:
                seen_promotion_ids[promotion_id] = path

            if candidate_id in seen_instruction_candidates:
                errors.append(
                    f"candidate_id '{candidate_id}' already has a promotion "
                    f"instruction in this set "
                    f"({seen_instruction_candidates[candidate_id].name}); "
                    f"duplicate promotions for one candidate fail closed"
                )
            else:
                seen_instruction_candidates[candidate_id] = path

        if errors:
            promotion_failures[path] = errors

    # Pass 2b: receipt set-level replay law + validated binding/evidence.
    seen_receipt_ids = {}
    seen_success_promotions = {}
    for path, kind, record, errors in parsed:
        if kind != "receipt":
            continue
        if not errors:
            receipt_id = record["receipt_id"]
            promotion_id = record["promotion_id"]

            if receipt_id in seen_receipt_ids:
                errors.append(
                    f"receipt_id '{receipt_id}' duplicates "
                    f"{seen_receipt_ids[receipt_id].name}; duplicate promotion "
                    f"receipts fail closed"
                )
            else:
                seen_receipt_ids[receipt_id] = path

            instruction = instructions_by_id.get(promotion_id)
            if instruction is None:
                errors.append(
                    f"promotion_id '{promotion_id}' does not resolve to a valid "
                    f"promotion instruction in this promotion set"
                )
            else:
                errors.extend(context.receipt_errors(record, instruction))

            if record["outcome"] == "success":
                if promotion_id in seen_success_promotions:
                    errors.append(
                        f"more than one success receipt for promotion "
                        f"'{promotion_id}' in this set "
                        f"({seen_success_promotions[promotion_id].name}); "
                        f"replay/idempotency fails closed"
                    )
                else:
                    seen_success_promotions[promotion_id] = path

        if errors:
            promotion_failures[path] = errors

    # Pass 2c: records that were neither a valid instruction nor receipt.
    for path, kind, _record, errors in parsed:
        if kind is None and path not in promotion_failures:
            promotion_failures[path] = errors

    return (candidate_failures, decision_failures, material_failures,
            collision_failures, promotion_failures)


def main(argv):
    if len(argv) < 5:
        print(
            "usage: validate_intake_promotions.py "
            "<candidates-directory> <decision-directory> <material-directory> "
            "<collision-directory> <promotion-directory> "
            "[<promotion-directory> ...]",
            file=sys.stderr,
        )
        return 2

    try:
        candidate_paths = shared.load_records(argv[0])
        decision_paths = shared.load_records(argv[1])
        material_paths = shared.load_records(argv[2])
        collision_paths = shared.load_records(argv[3])
    except (NotADirectoryError, FileNotFoundError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    promotion_paths = []
    for directory in argv[4:]:
        try:
            promotion_paths.extend(shared.load_records(directory))
        except (NotADirectoryError, FileNotFoundError) as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2

    (candidate_failures, decision_failures, material_failures,
     collision_failures, promotion_failures) = validate_paths(
        candidate_paths, decision_paths, material_paths, collision_paths,
        promotion_paths,
    )

    for failures in (candidate_failures, decision_failures, material_failures,
                     collision_failures, promotion_failures):
        for path, errors in failures.items():
            shown = shared._display_path(path)
            for error in errors:
                print(f"FAIL: {shown}: {error}", file=sys.stderr)

    if candidate_failures or decision_failures or material_failures \
            or collision_failures or promotion_failures:
        total = (len(candidate_failures) + len(decision_failures)
                 + len(material_failures) + len(collision_failures)
                 + len(promotion_failures))
        print(f"\n{total} record(s) failed validation.", file=sys.stderr)
        return 1

    instructions = sum(
        1 for path in promotion_paths
        if classify_promotion_record(read_record(path)) == "instruction"
    )
    print(
        f"OK: {len(candidate_paths)} candidate record(s), "
        f"{len(decision_paths)} decision record(s), "
        f"{len(material_paths)} material record(s), "
        f"{len(collision_paths)} collision result record(s), and "
        f"{len(promotion_paths)} promotion record(s) "
        f"({instructions} instruction(s)) valid as one promotion set."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
