#!/usr/bin/env python3
"""Validate Canon Intake collision results against the CI series (CI-03).

Usage:
    python scripts/validate_intake_collisions.py <candidates-directory> <decision-directory> <material-directory> <collision-directory> [<collision-directory> ...]

The first directory holds CI-01 candidate records; the second holds CI-02
decision records; the third holds CI-02.1 candidate material envelopes (each
directory set validated by its own contract first). Every following directory
holds CI-03 collision results that together form ONE validated collision set.
Each collision result carries exactly one caller-supplied authoritative
current-target/publication observation; the caller (a CI-04/later adaptor,
never CI-03) is responsible for obtaining it from the correct
repository/runtime owner.

Classification is deterministic and exact-only (CI-03 contract law):

- invalid/ineligible input fails validation;
- a candidate whose CI-02 decision is not an explicit human `approved` is not
  eligible for collision clearance and fails closed;
- the record's observation is bound to the referenced candidate's
  proposed_target: observation.target must exactly match the CI-02.1 material
  envelope's proposed_target (kind + reference) when one is proposed, and must
  be absent when none is proposed, so one observation cannot clear multiple
  different targets;
- a known candidate base_publication pin that conflicts with the known current
  publication classifies `stale` before any content comparison;
- absent proposed_target classifies `unresolved` (nowhere to compare);
- unknown authoritative target state classifies `unresolved`;
- authoritative target known absent classifies `clear`;
- present target with unavailable current material classifies `unresolved`;
- present target whose current material exactly equals candidate material
  classifies `duplicate`;
- present target whose current material differs classifies `conflict`.

The observation shape embedded in each record is exactly:
    {"target": {"kind": ..., "reference": ...},   # bound to proposed_target
     "target_state": "absent" | "present" | "unknown",
     "target_identity": {"generation": <int >= 0> | "git_ref": <40-hex>},
     "current_material": <optional non-blank string, present target only>}

The declared `result` and `reason` must equal the deterministic classification
and reason computed from the evidence; a caller-authored mismatch fails closed.
No fuzzy/semantic equality, no normalization, no network access, no conflict
resolution, no promotion, no canon/runtime mutation, and no durable
import-history store exist here (CI-04 and later gates own those).
duplicate/stale/conflict/unresolved are NOT promotion-clear; only clear can
proceed toward CI-04.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_entities as shared  # noqa: E402
import validate_intake_candidates as candidates  # noqa: E402
import validate_intake_candidate_material as material  # noqa: E402
import validate_intake_decisions as decisions  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "intake_collision.schema.json"

READ_HOOKS = candidates.READ_HOOKS

RESULT_VOCABULARY = ("clear", "duplicate", "stale", "conflict", "unresolved")


def load_schema(schema_path=SCHEMA_PATH):
    """Return the parsed intake-collision JSON Schema."""
    return candidates.load_schema(schema_path)


def validate_record(record, schema):
    """Return a list of human-readable error strings for one record (empty if valid)."""
    return candidates.validate_record(record, schema)


def read_record(path):
    """Read one JSON record through the shared fail-closed parse hooks."""
    return candidates.read_record(path)


def approved_candidate_ids(candidate_paths, candidate_failures, decision_paths,
                           decision_failures):
    """Return {candidate_id: "approved"} for candidates eligible at all.

    Only candidates with no CI-01 validation failure may be considered. A
    candidate with no resolvable decision, a rejected decision, or a failed
    decision record is NOT approved and therefore not eligible for CI-03
    clearance (fail closed). Human-approved only: authority=human and
    outcome=approved are enforced by the CI-02 contract itself.
    """
    referenceable = material.referenceable_candidates(
        candidate_paths, candidate_failures
    )
    outcomes = {}
    for path in decision_paths:
        if path in decision_failures:
            continue
        record = read_record(path)
        candidate_id = record["candidate_id"]
        if candidate_id not in referenceable:
            continue
        if candidate_id in outcomes:
            # More than one valid decision for the same candidate cannot be
            # produced by one CI-02 set (it fails closed there); treat any
            # such input as not approved rather than picking one.
            outcomes[candidate_id] = None
        else:
            outcomes[candidate_id] = record["outcome"]
    return {
        candidate_id: outcome
        for candidate_id, outcome in outcomes.items()
        if outcome == "approved"
    }


def target_binding_error(material_record, observation):
    """Return a fail-closed error string when the observation is not bound to
    the referenced candidate's proposed_target, else None.

    The observation must identify exactly the target the referenced material
    envelope proposes (kind + reference). One observation therefore cannot be
    reused to clear a different target, and an observation for a candidate
    with no proposed target must not bind one.
    """
    proposed = material_record.get("proposed_target")
    observed = observation.get("target")
    if proposed is None:
        if observed is not None:
            return (
                "observation binds a target but the candidate material envelope "
                "has no proposed_target; an unproposed target cannot be observed"
            )
        return None
    if observed is None:
        return (
            "observation does not bind the candidate's proposed_target; every "
            "observation must identify the target it observed"
        )
    if (observed.get("kind"), observed.get("reference")) != (
        proposed.get("kind"), proposed.get("reference")
    ):
        return (
            f"observation target {observed.get('kind')!r}:"
            f"{observed.get('reference')!r} does not match the candidate's "
            f"proposed_target {proposed.get('kind')!r}:"
            f"{proposed.get('reference')!r}; one observation cannot clear "
            f"multiple different targets"
        )
    return None


def classify(material_record, observation):
    """Deterministically classify one candidate material against one observation.

    Implements the exact CI-03 precedence law. No fuzzy comparison, no
    normalization: string equality is exact and byte-faithful. Returns
    (result, reason), where reason is the authoritative evidence string the
    record must reproduce.
    """
    base_publication = material_record.get("base_publication")
    current_identity = observation.get("target_identity")

    # Precedence 3: known candidate base pin conflicting with known current
    # publication is stale, decided before any content comparison.
    if base_publication is not None and isinstance(current_identity, dict):
        base_generation = base_publication.get("generation")
        base_git_ref = base_publication.get("git_ref")
        current_generation = current_identity.get("generation")
        current_git_ref = current_identity.get("git_ref")
        if base_generation is not None and current_generation is not None \
                and base_generation != current_generation:
            return "stale", (
                f"base_publication.generation {base_generation} conflicts with "
                f"current published generation {current_generation}"
            )
        if base_git_ref is not None and current_git_ref is not None \
                and base_git_ref != current_git_ref:
            return "stale", (
                f"base_publication.git_ref {base_git_ref} conflicts with "
                f"current published git_ref {current_git_ref}"
            )

    # Precedence 4: no proposed target means there is nothing to compare.
    if "proposed_target" not in material_record:
        return "unresolved", (
            "candidate material envelope has no proposed_target; no comparison "
            "target exists"
        )

    # Precedence 5: authoritative target state unknown stays unknown.
    state = observation["target_state"]
    if state == "unknown":
        return "unresolved", "authoritative target state is unknown"

    # Precedence 6: target known absent from current truth.
    if state == "absent":
        return "clear", (
            "proposed target is known absent from current authoritative truth"
        )

    # Precedence 7: present target but current material unavailable.
    current_material = observation.get("current_material")
    if not isinstance(current_material, str) or not current_material.strip():
        return "unresolved", (
            "authoritative target is present but current material is unavailable"
        )

    # Precedence 8/9: exact deterministic comparison only.
    candidate_material = material_record["material"]
    if current_material == candidate_material:
        return "duplicate", (
            "current target material exactly equals candidate material "
            "(re-import/replay of identical material)"
        )
    return "conflict", "current target material differs from candidate material"


def validate_paths(candidate_paths, decision_paths, material_paths,
                   collision_paths, schema_path=SCHEMA_PATH):
    """Validate one collision set against candidate/decision/material inputs.

    Returns (candidate_failures, decision_failures, material_failures,
    collision_failures): dicts {path: [errors]} containing only paths with at
    least one error.
    """
    schema = load_schema(schema_path)

    candidate_failures, decision_failures = decisions.validate_paths(
        candidate_paths, decision_paths
    )
    material_failures = {}
    referenceable = material.referenceable_candidates(
        candidate_paths, candidate_failures
    )

    seen_material_candidate_ids = {}
    for path in material_paths:
        try:
            record = read_record(path)
        except UnicodeDecodeError as exc:
            material_failures[path] = [f"invalid UTF-8: {exc}"]
            continue
        except (json.JSONDecodeError, ValueError) as exc:
            material_failures[path] = [f"invalid JSON: {exc}"]
            continue

        errors = validate_record(
            record, candidates.load_schema(material.SCHEMA_PATH)
        )
        candidate_id = record.get("candidate_id") if isinstance(record, dict) else None
        if isinstance(candidate_id, str):
            if candidate_id in seen_material_candidate_ids:
                errors.append(
                    f"candidate_id '{candidate_id}' already has a material "
                    f"envelope in this material set "
                    f"({seen_material_candidate_ids[candidate_id].name})"
                )
            else:
                seen_material_candidate_ids[candidate_id] = path
            if candidate_id not in referenceable:
                errors.append(
                    f"candidate_id '{candidate_id}' does not resolve to a "
                    f"valid CI-01 candidate in the candidate batch"
                )
        if errors:
            material_failures[path] = errors

    approved = approved_candidate_ids(
        candidate_paths, candidate_failures, decision_paths, decision_failures
    )

    collision_failures = {}
    seen_collision_ids = {}
    seen_candidate_results = {}

    for path in collision_paths:
        try:
            record = read_record(path)
        except UnicodeDecodeError as exc:
            collision_failures[path] = [f"invalid UTF-8: {exc}"]
            continue
        except (json.JSONDecodeError, ValueError) as exc:
            collision_failures[path] = [f"invalid JSON: {exc}"]
            continue

        errors = validate_record(record, schema)
        # Semantic helpers (target binding and classification) rely on the
        # record/observation being structurally valid. When schema validation
        # has already failed, skip them entirely so a malformed observation
        # (missing target_state, scalar/non-object target, bad nested shape)
        # fails closed through validation errors instead of raising.
        schema_valid = not errors

        collision_id = record.get("collision_id") if isinstance(record, dict) else None
        candidate_id = record.get("candidate_id") if isinstance(record, dict) else None

        if isinstance(collision_id, str):
            if collision_id in seen_collision_ids:
                errors.append(
                    f"collision_id '{collision_id}' duplicates "
                    f"{seen_collision_ids[collision_id].name}; duplicate "
                    f"collision result records fail closed"
                )
            else:
                seen_collision_ids[collision_id] = path

        if isinstance(candidate_id, str):
            if candidate_id in seen_candidate_results:
                errors.append(
                    f"candidate_id '{candidate_id}' already has a collision "
                    f"result in this collision set "
                    f"({seen_candidate_results[candidate_id].name}); duplicate "
                    f"collision results fail closed"
                )
            else:
                seen_candidate_results[candidate_id] = path

            if candidate_id not in referenceable:
                errors.append(
                    f"candidate_id '{candidate_id}' does not resolve to a "
                    f"valid CI-01 candidate in the candidate batch"
                )
            elif candidate_id not in approved:
                errors.append(
                    f"candidate_id '{candidate_id}' has no valid explicit "
                    f"human-approved CI-02 decision; only approved candidates "
                    f"are eligible for CI-03 collision clearance"
                )
            else:
                envelope = _material_envelope(
                    material_paths, material_failures, candidate_id
                )
                if envelope is None:
                    errors.append(
                        f"candidate_id '{candidate_id}' has no valid CI-02.1 "
                        f"material envelope; collision classification requires "
                        f"candidate material"
                    )
                elif schema_valid:
                    observation = record["observation"]
                    binding_error = target_binding_error(envelope, observation)
                    if binding_error is not None:
                        errors.append(binding_error)
                    else:
                        result, reason = classify(envelope, observation)
                        declared = record.get("result")
                        declared_reason = record.get("reason")
                        if declared not in RESULT_VOCABULARY:
                            errors.append(
                                f"collision result {declared!r} is outside the "
                                f"legal CI-03 vocabulary"
                            )
                        elif declared != result:
                            errors.append(
                                f"declared collision result {declared!r} does "
                                f"not match the deterministic classification "
                                f"{result!r} ({reason})"
                            )
                        elif declared_reason != reason:
                            errors.append(
                                f"declared reason {declared_reason!r} does not "
                                f"match the deterministic reason {reason!r}"
                            )

        if errors:
            collision_failures[path] = errors

    return (candidate_failures, decision_failures, material_failures,
            collision_failures)


def _material_envelope(material_paths, material_failures, candidate_id):
    for path in material_paths:
        if path in material_failures:
            continue
        record = read_record(path)
        if record["candidate_id"] == candidate_id:
            return record
    return None


def main(argv):
    if len(argv) < 4:
        print(
            "usage: validate_intake_collisions.py "
            "<candidates-directory> <decision-directory> <material-directory> "
            "[<collision-directory> ...]",
            file=sys.stderr,
        )
        return 2

    try:
        candidate_paths = shared.load_records(argv[0])
        decision_paths = shared.load_records(argv[1])
        material_paths = shared.load_records(argv[2])
    except (NotADirectoryError, FileNotFoundError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    collision_paths = []
    for directory in argv[3:]:
        try:
            collision_paths.extend(shared.load_records(directory))
        except (NotADirectoryError, FileNotFoundError) as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2

    (candidate_failures, decision_failures, material_failures,
     collision_failures) = validate_paths(
        candidate_paths, decision_paths, material_paths, collision_paths,
    )

    for failures in (candidate_failures, decision_failures,
                     material_failures, collision_failures):
        for path, errors in failures.items():
            shown = shared._display_path(path)
            for error in errors:
                print(f"FAIL: {shown}: {error}", file=sys.stderr)

    if candidate_failures or decision_failures or material_failures \
            or collision_failures:
        total = (len(candidate_failures) + len(decision_failures)
                 + len(material_failures) + len(collision_failures))
        print(f"\n{total} record(s) failed validation.", file=sys.stderr)
        return 1

    print(
        f"OK: {len(candidate_paths)} candidate record(s), "
        f"{len(decision_paths)} decision record(s), "
        f"{len(material_paths)} material record(s), and "
        f"{len(collision_paths)} collision result record(s) valid as one "
        f"collision set."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
