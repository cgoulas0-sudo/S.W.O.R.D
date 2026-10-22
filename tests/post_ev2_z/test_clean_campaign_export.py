"""POST-EV2-Z Clean Campaign Canvas exporter proof (extended by POST-EV2-Z.1).

Proves the deterministic clean-canvas exporter defined by JOHNNY CHECKPOINT
``POST_EV2_Z_CLEAN_CAMPAIGN_CANVAS_V3`` at base
``64260bc53575016a848283196c4b1bdd947cb5d4`` and extended by JOHNNY CHECKPOINT
``POST_EV2_Z1_ENGINE_VERSION_STAMP`` at base
``80cf8aa4a4cd3e10922dc0e3b92d4e8ab3cdf489``:

* branch/base exact and the cumulative Mission diff stays inside the Surface
  Budget (create ``ENGINE_VERSION``; modify the policy, exporter, proof, doc,
  and workflow);
* every tracked source path has exactly one structural disposition;
* an unclassified or ambiguous path fails closed;
* classification is path-only (no content-derived classification/sanitization);
* COPY bytes and modes match the exact Git blobs;
* EXCLUDE surfaces and factory-only POST-EV2-Z machinery are absent;
* generated mutable roots are EMPTY / UNKNOWN and contract-valid;
* the receipt carries a comparable ``engine_version`` read from the single
  ``ENGINE_VERSION`` source of truth at the exact commit, and a missing or
  malformed version source fails the export closed;
* every retained control/document route resolves (no dangling route into an
  excluded source path); an executable workflow route is satisfied only by a
  real exported file (never by an empty preserved skeleton directory), a
  route naming a path that exists nowhere fails closed, and every skeleton
  false positive is caught -- each with a synthetic negative;
* shipped (COPY or generated) executable/structured surfaces carry no
  RHC-only primary-reality identity (a synthetic stale copied reference fails
  the guard closed);
* repeated export from the same HEAD is byte/path/mode/receipt deterministic;
* the source tree is unchanged;
* destructive overwrite and source/output overlap are refused;
* the export initializes as an independent repository context;
* the exported representative test suite is free of RHC character/NPC fixture
  names;
* no COPY-shipped executable/structured surface carries the remapped RHC-only
  primary-reality identity (a synthetic stale copied reference fails the guard
  closed) and the COPY-shipped POST-EV2-14 suite executes from inside the
  exported canvas: that suite is a portable bounded-lifecycle proof carrying no
  source/factory-only assertion and no context discriminator, and this
  EXCLUDE-owned factory proof owns the equivalent source wiring assertions --
  the source Entity V2 workflow runs the POST-EV2-14 suite, the export policy
  classifies the POST-EV2-14 surfaces as COPY, and a fresh export contains
  them;
* the dedicated Z workflow is Mission-local and checks out the exact PR head;
* the dedicated Z workflow never derives the canvas path from a ``runner``
  context at job-level ``env`` (where GitHub Actions does not make it available,
  which fails workflow startup before any job runs);
* existing global CI is unchanged; ``git diff --check`` is clean.

The three mission-bound provenance assertions (the cumulative Surface-Budget
diff, the branch/base JOHNNY binding, and the global-workflow immutability
check) proved the original POST-EV2-Z / Z.1 Mission only; they are gated behind
``_on_original_z_mission_branch`` so they run on that Mission's branch -- both
locally and in its detached exact-head CI checkout, where the branch is
recovered from the GitHub event context -- and skip elsewhere, rather than
acting as permanent repository law that false-fails later authorized Missions.
The durable exporter/clean-canvas proofs above stay active unconditionally.
POST-EV2-Z7 adds the durable product-identity-acceptance proof: the ACTUAL
post-materialization emitted tree carries no declared source campaign identity
(paths or declared content surfaces) and matches the authorized output
path/kind inventory, the receipt records machine-readable acceptance evidence
for that completed tree, and positive/negative fixtures -- including
identity-bearing files/directories, a mutated root README, a token-free unlisted
extra path, an expected regular file substituted by a symlink to a neutral
external file, and a token-free but altered materialized regular file, all
injected *during* materialization -- fail the export closed with no accepted
receipt written. The post-materialization inspector reads every entry's
no-follow filesystem species with ``os.lstat`` (a regular file and a symlink
that share a relative path are never collapsed onto the same bare string; a
legitimate Git ``120000`` COPY symlink must remain an actual symlink) and
attests each emitted regular file's real bytes -- or an authorized symlink's
real ``readlink`` target -- against the exact intended digest. Its traversal is a
strict no-follow ``os.scandir`` walk that fails closed on any unscannable
directory or unreadable entry (never a silently partial inventory), and it
verifies each emitted regular file's real POSIX mode against its authorized Git
``100755``/``100644`` mode -- a platform-bounded guarantee asserted where the
host exposes permission bits (Ubuntu CI) and never silently claimed on Windows.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import inspect
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXPORTER_PATH = ROOT / "scripts" / "export_clean_campaign.py"
POLICY_PATH = ROOT / "bootstrap" / "CLEAN_CAMPAIGN_EXPORT_POLICY.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "post-ev2-z-clean-canvas.yml"

BASE_SHA = "80cf8aa4a4cd3e10922dc0e3b92d4e8ab3cdf489"
BRANCH = "post-ev2-z1/engine-version-stamp"

ENGINE_VERSION_PATH = ROOT / "ENGINE_VERSION"

# The POST-EV2-Z factory-only machinery this Mission extends: the exporter, its
# policy, its doc, its proof, and its Mission-local workflow are all EXCLUDE
# surfaces that must never appear in the exported customer tree.
Z_FILES = frozenset(
    {
        "bootstrap/CLEAN_CAMPAIGN_EXPORT_POLICY.json",
        "scripts/export_clean_campaign.py",
        "docs/POST-EV2-Z-CLEAN-CAMPAIGN-EXPORT.md",
        "tests/post_ev2_z/test_clean_campaign_export.py",
        ".github/workflows/post-ev2-z-clean-canvas.yml",
    }
)

# The one new factory/control-plane input this Mission adds: the single
# root-level engine-version source of truth. The exporter reads it and records
# it in the receipt; it is not a shipped customer-tree surface.
ENGINE_VERSION_FILES = frozenset({"ENGINE_VERSION"})

# EXCLUDE surfaces that must be absent from the exported canvas: the POST-EV2-Z
# factory machinery plus the engine-version source.
FACTORY_ABSENT_FILES = Z_FILES | ENGINE_VERSION_FILES

# Exactly the paths this Mission's branch-bound JOHNNY Surface Budget authorizes
# this run to create or modify: create ENGINE_VERSION; modify the policy, the
# exporter, the proof, the doc, and (for trigger coverage) the workflow.
SURFACE_BUDGET_FILES = Z_FILES | ENGINE_VERSION_FILES

# The Z3 reality surfaces this Mission admits into the dedicated Z proof path:
# the generic-primary-reality schema, validator, proof, and their durable docs.
# A change to any of these must schedule the Z proof on both PR and main push so
# it cannot silently bypass the engine's reality-law admission.
REALITY_SURFACES = frozenset({
    "schemas/reality.schema.json",
    "scripts/validate_realities.py",
    "tests/test_reality_inheritance.py",
    "realities/README.md",
    "docs/POST-EV2-4B-REALITY-INHERITANCE.md",
})

# Path-filter patterns that admit every shipped surface the copied-executable
# portability guard scans (COPY plus GENERATE_EMPTY, minus prose *.md -- including
# the COPY-shipped POST-EV2-14 test surface under ``tests/**`` and the
# policy-generated RT01 runtime workflow under ``.github/**``) into this proof: a
# change to any scanned surface must schedule the Z proof, or a stale copied or
# stale generated reference could merge without the guard ever running.
# Directory prefixes use the GitHub Actions ``dir/**`` form; the coverage proof
# below matches every scanned surface against these declared patterns, and a
# shipped surface landing outside every pattern fails the proof closed.
COPY_SCAN_COVERAGE_PATTERNS = (
    ".gitignore",
    ".githooks/**",
    ".github/**",
    "characters/**",
    "config/**",
    "knowledge/**",
    "locations/**",
    "npc/**",
    "quests/**",
    "realities/**",
    "requirements.txt",
    "schemas/**",
    "scripts/**",
    "state/**",
    "supabase/**",
    "tests/**",
)

# The POST-EV2-Z Mission-local workflow trigger set: every POST-EV2-Z surface,
# the engine-version source (so a version-only bump still runs this proof), the
# authorized requirements.txt PyYAML line, the Z3 reality surfaces this
# Mission admits into the Z proof path, and the path-filter patterns that admit
# every COPY surface the copied-executable guard scans.
Z_WORKFLOW_TRIGGER_PATHS = (
    Z_FILES
    | ENGINE_VERSION_FILES
    | REALITY_SURFACES
    | frozenset(COPY_SCAN_COVERAGE_PATTERNS)
)

EXCLUDED_SAMPLE = (
    "canon/timeline.md",  # generated blank, not the RHC timeline body
    "characters/madma/NARRATIVE_DIRECTION.md",  # Z7: named path removed entirely
    "canon/bor_vestige_bell_spellplague.md",
    "characters/mugen.md",
    "npc/profiles/bor.md",
    "npc/battle/bor.md",
    "villain/gork.md",
    "inventory/weapons/vampire.md",
    "entities/items/vampire.json",
    "entities/README.md",
    "supabase/README.md",
    "supabase/canaries/ev212_vampire_admission.sql",
    "schemas/README.md",
    "docs/EV2-12-FIRST-REAL-CANARY.md",
    "docs/EV2-12.1-GENERALIZED-ITEM-ADMISSION.md",
    "docs/HB-01-PROVENANCE.md",
    "docs/POST-EV2-3-RUN-IMPACT-WIRING.md",
    "tests/ev212/test_first_real_item_canary.py",
    "tests/ev2121/test_generalized_item_identity_admission.py",
    "tests/post_ev2_6/test_story_retrieval.py",
    "tests/rt03/test_run_record_validation.py",
    "tests/rt03/test_run_resolution.py",
    # Source-repository provenance: this proof's historical frontier assertion
    # reads a pinned RHC commit object and is meaningless in an independent
    # repository with no RHC ancestry, so it stays in source RHC (EXCLUDE).
    "tests/post_ev2_1/test_clean_bootstrap_equivalence.py",
    "tests/post_ev2_2/test_hot_run_registry.py",
    "tests/post_ev2_9/test_character_vitals_resources.py",
    "tests/post_ev2_10/test_character_rest.py",
    "CHANGELOG.md",  # generated blank
    "ENGINE_CHANGELOG.md",  # generated blank
    # Workflow/automation surfaces whose run: steps invoke excluded paths; they
    # are reclassified EXCLUDE rather than shipped with a dead route.
    ".github/workflows/entity-v2-identity.yml",
    ".github/workflows/flight-control.yml",
    ".github/workflows/story-retrieval.yml",
)
# The EXCLUDE disposition leaves the RHC logbook body out; the blank logbook is
# generated at the same path, so only its campaign body must be absent.
EXCLUDED_BODY_MARKERS = {
    "CHANGELOG.md": "Rolling High Club",
    "ENGINE_CHANGELOG.md": "Rolling High Club",
    "canon/timeline.md": "Rolling High Club",
}

# The shipped RT01 runtime workflow is the one explicit, proven portability
# adaptation of this Mission: the policy classifies it GENERATE_EMPTY and
# generates the exported bytes from a fixed policy constant equal to the source
# workflow minus its source-only pytest arguments. The four source-only test
# trees below stay EXCLUDE (ownership audit: each is a live source-RHC runtime
# proof whose test code carries RHC campaign-identity strings -- item:vampire /
# character:gork in tests/ev2121 and tests/post_ev2_2, character:mugen in
# tests/post_ev2_9 and tests/post_ev2_10 -- so shipping them would violate the
# durable no-RHC-fixture-names invariant, while stripping them from the source
# workflow would strip live source proof). The generated workflow drops exactly
# these arguments and nothing else; the source workflow keeps invoking them.
RUNTIME_WORKFLOW_PATH = ".github/workflows/rt01-runtime.yml"
SOURCE_ONLY_RUNTIME_TEST_TREES = frozenset({
    "tests/ev2121",
    "tests/post_ev2_2",
    "tests/post_ev2_9",
    "tests/post_ev2_10",
})

GENERATED_ROOTS = (
    "state/daily_recap.json",
    "state/day_resolution.json",
    "state/dm_meta.json",
    "state/live_status.json",
    "knowledge/facts.json",
    "npc/npc_state.json",
    "quests/narrative_hooks.json",
    "realities/registry/campaign-root.json",
    "canon/timeline.md",
    "CHANGELOG.md",
    "ENGINE_CHANGELOG.md",
)

REPRESENTATIVE_SURFACES = (
    "supabase/migrations/20260911000001_rt02_campaign_clock.sql",
    "supabase/migrations/20260908000001_rt01a_published_runtime_floor.sql",
    "scripts/validate_entities.py",
    "scripts/validate_canonical_root_json.py",
    "tests/test_entity_validation.py",
    "tests/test_canonical_root_json.py",
    "tests/rt02/conftest.py",
    "tests/rt01b/conftest.py",
    "tests/ev213420/conftest.py",
    "tests/rt01a/supabase_baseline_roles.sql",
    "schemas/entity.schema.json",
    "requirements.txt",
    "tests/post_ev2_14/test_brainstorm_lab.py",
)

RHC_NAME_TOKENS = (
    "madma",
    "gork",
    "mugen",
    "saarpa",
    "ioulaum",
    "vampire",
    "bor-family",
    "larloch",
)


def _load_exporter():
    spec = importlib.util.spec_from_file_location("clean_campaign_export", EXPORTER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exporter = _load_exporter()


def _git(*args, check=True):
    proc = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def _on_original_z_mission_branch():
    """Whether the checkout is the original POST-EV2-Z / Z.1 Mission branch.

    Three assertions below (the cumulative Surface-Budget diff, the branch/base
    JOHNNY binding, and the global-workflow immutability check) were written to
    prove the original POST-EV2-Z / Z.1 Mission. They encode that Mission's
    historical assumptions -- a fixed original Z Surface Budget, a frozen
    original Z.1 branch/base, and a frozen set of global workflows -- so they
    are historical mission/provenance assertions, not durable exporter
    invariants. On any later branch they would falsely fail a legitimate
    authorized change (PR #245 / BTH-01 is the concrete example), so they run
    only on the original Mission branch they were authored to prove.

    GitHub Actions checks out the exact commit SHA, so in its detached CI
    checkout ``rev-parse --abbrev-ref HEAD`` is ``HEAD`` and the branch name is
    not available locally. The original Mission is therefore also recovered from
    the event branch GitHub supplies -- ``GITHUB_HEAD_REF`` on pull_request runs
    and ``GITHUB_REF_NAME`` on push runs -- so the historical assertions still
    run when CI is proving the original Z.1 branch itself instead of being
    skipped by the detached checkout. Exact-head binding is separately enforced
    by the workflow. An unrelated later branch matches neither source and still
    skips.
    """
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch == BRANCH:
        return True
    if branch != "HEAD":
        return False
    return BRANCH in (
        os.environ.get("GITHUB_HEAD_REF"),
        os.environ.get("GITHUB_REF_NAME"),
    )


def _policy():
    return exporter.parse_policy(POLICY_PATH.read_text(encoding="utf-8"))


def _sample_export(tmp_path, name="canvas"):
    output = tmp_path / name
    receipt = tmp_path / f"{name}.receipt.json"
    receipt_object = exporter.export(ROOT, "HEAD", output, receipt)
    return output, receipt, receipt_object


def _tree_snapshot(root: Path):
    snapshot = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snapshot[path.relative_to(root).as_posix()] = path.read_bytes()
    return snapshot


def _git_run(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def _workflow_event_paths(text):
    """Return ``{event: set(paths)}`` from a workflow's top-level ``on`` block.

    The workflow is parsed with a real YAML parser and each event's ``paths``
    list is read independently, so a trigger missing from one event cannot be
    masked by the surviving copy under another event (which is exactly what
    flattening every quoted list item into one combined/deduplicated set does).
    The YAML 1.1 loader decodes the ``on`` key to the boolean ``True``, so both
    spellings are accepted.
    """
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        return {}
    triggers = document.get("on", document.get(True))
    if not isinstance(triggers, dict):
        return {}
    events = {}
    for event, config in triggers.items():
        if isinstance(config, dict) and isinstance(config.get("paths"), list):
            events[str(event)] = set(config["paths"])
    return events


def _runner_derived_job_env(document):
    """Return ``[(job_id, key)]`` for ``runner.`` used at job-level ``env``.

    GitHub Actions does not make the ``runner`` context available at
    ``jobs.<job_id>.env`` -- only once a runner exists (step level). A
    runner-derived value declared there fails workflow planning/startup before
    any job runs, so the workflow never appears as a check-run. This checker
    parses the workflow with a real YAML parser and inspects only the declared
    ``jobs.*.env`` maps, which is the exact startup-failure class this repair
    closes.
    """
    jobs = document.get("jobs") if isinstance(document, dict) else None
    if not isinstance(jobs, dict):
        return []
    offenders = []
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        env = job.get("env")
        if not isinstance(env, dict):
            continue
        for key, value in env.items():
            if "runner." in str(value):
                offenders.append((str(job_id), str(key)))
    return offenders


# --------------------------------------------------------------------------
# Surface budget / provenance
# --------------------------------------------------------------------------

def test_cumulative_diff_is_exactly_the_surface_budget():
    # Historical POST-EV2-Z / Z.1 mission-bound provenance assertion: it proved
    # the original Mission's cumulative diff equalled that Mission's Surface
    # Budget. It must not become permanent repository law for later Missions.
    if not _on_original_z_mission_branch():
        pytest.skip("historical POST-EV2-Z / Z.1 mission-bound assertion")
    changed = _git("diff", "--name-only", BASE_SHA).stdout.split()
    untracked = _git("ls-files", "--others", "--exclude-standard").stdout.split()
    assert set(changed) | set(untracked) == set(SURFACE_BUDGET_FILES)


def test_branch_and_base_are_bound_to_the_johnny():
    # Historical POST-EV2-Z / Z.1 mission-bound provenance assertion: it proved
    # the branch/base binding of the original Mission's JOHNNY. It must not
    # become permanent repository law for later Missions.
    if not _on_original_z_mission_branch():
        pytest.skip("historical POST-EV2-Z / Z.1 mission-bound assertion")
    assert _git("merge-base", "--is-ancestor", BASE_SHA, "HEAD", check=False).returncode == 0
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    event_head = os.environ.get("GITHUB_EVENT_HEAD_SHA")
    if branch == "HEAD":
        # Detached exact-head checkout (CI): when the workflow supplies the
        # event PR head, prove we are on that exact immutable commit.
        if event_head:
            assert _git("rev-parse", "HEAD").stdout.strip() == event_head
    else:
        assert branch == BRANCH


class _FakeProcess:
    """Minimal stand-in for a ``git`` subprocess result (``.stdout`` only)."""

    def __init__(self, stdout):
        self.stdout = stdout


def _stub_local_branch(monkeypatch, branch):
    """Force only the local branch read used by ``_on_original_z_mission_branch``."""
    monkeypatch.setattr(
        sys.modules[__name__],
        "_git",
        lambda *args, **kwargs: _FakeProcess(f"{branch}\n"),
    )


def test_original_mission_is_detected_on_its_own_local_branch(monkeypatch):
    # Local original-Z.1 execution must still run the historical assertions.
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    _stub_local_branch(monkeypatch, BRANCH)
    assert _on_original_z_mission_branch() is True


def test_original_mission_is_detected_in_detached_ci_head_ref(monkeypatch):
    # GitHub Actions checks out the exact commit SHA, so the local branch name
    # is ``HEAD``; the original Mission is recovered from the PR source branch
    # GitHub supplies in ``GITHUB_HEAD_REF`` rather than being skipped.
    monkeypatch.setenv("GITHUB_HEAD_REF", BRANCH)
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    _stub_local_branch(monkeypatch, "HEAD")
    assert _on_original_z_mission_branch() is True


def test_original_mission_is_detected_in_detached_ci_ref_name(monkeypatch):
    # A push run to the original Mission branch supplies the branch in
    # ``GITHUB_REF_NAME`` (``GITHUB_HEAD_REF`` is pull_request-only).
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.setenv("GITHUB_REF_NAME", BRANCH)
    _stub_local_branch(monkeypatch, "HEAD")
    assert _on_original_z_mission_branch() is True


def test_unrelated_local_branch_skips_historical_assertions(monkeypatch):
    # A later legitimate Mission's local branch must not run the original
    # Mission's historical provenance assertions.
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    _stub_local_branch(monkeypatch, "post-ev2/z2-clean-canvas-ci-mission-local")
    assert _on_original_z_mission_branch() is False


def test_unrelated_detached_ci_branch_skips_historical_assertions(monkeypatch):
    # A later Mission's detached CI run matches neither the local branch
    # (``HEAD``) nor the GitHub event branch, so it must still skip.
    monkeypatch.setenv("GITHUB_HEAD_REF", "post-ev2/z2-clean-canvas-ci-mission-local")
    monkeypatch.setenv("GITHUB_REF_NAME", "246/merge")
    _stub_local_branch(monkeypatch, "HEAD")
    assert _on_original_z_mission_branch() is False


# --------------------------------------------------------------------------
# Structural classification
# --------------------------------------------------------------------------

def test_every_tracked_path_has_exactly_one_disposition():
    policy = _policy()
    counts = {disposition: 0 for disposition in exporter.ALLOWED_DISPOSITIONS}
    for _mode, obj_type, _sha, path in exporter.tracked_entries("HEAD", ROOT):
        assert obj_type == "blob"
        disposition = exporter.disposition_for_path(policy, path)
        assert disposition in exporter.ALLOWED_DISPOSITIONS
        counts[disposition] += 1
    assert all(count > 0 for count in counts.values())


def test_unclassified_path_fails_closed():
    with pytest.raises(exporter.ExportError):
        exporter.disposition_for_path(_policy(), "no/such/tracked/path.txt")


def test_ambiguous_path_fails_closed():
    ambiguous = {
        "rules": [
            {"disposition": "COPY", "match": "a/b"},
            {"disposition": "EXCLUDE", "match": "a/b"},
        ]
    }
    with pytest.raises(exporter.ExportError):
        exporter.disposition_for_path(ambiguous, "a/b")


def test_copy_rule_may_not_be_a_directory_prefix():
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(json.dumps({
            **json.loads(POLICY_PATH.read_text(encoding="utf-8")),
            "rules": [{"disposition": "COPY", "match": "docs/"}],
        }))


def test_duplicate_policy_rule_is_rejected():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["rules"] = policy["rules"] + [dict(policy["rules"][0])]
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(json.dumps(policy))


def test_classification_is_path_only():
    signature = inspect.signature(exporter.disposition_for_path)
    assert list(signature.parameters) == ["policy", "path"]
    assert "content" not in signature.parameters
    assert "text" not in signature.parameters
    for forbidden in ("unicodedata", "codecs", "base64"):
        assert forbidden not in EXPORTER_PATH.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# COPY / EXCLUDE / GENERATE_EMPTY fidelity
# --------------------------------------------------------------------------

def test_copy_bytes_and_modes_match_exact_git_blobs(tmp_path):
    output, _receipt, receipt_object = _sample_export(tmp_path)
    policy = _policy()
    by_path = {entry["path"]: entry for entry in receipt_object["entries"]}
    for mode, _obj_type, sha, path in exporter.tracked_entries("HEAD", ROOT):
        disposition = exporter.disposition_for_path(policy, path)
        out_path = (
            exporter.generate_output_path(policy, path)
            if disposition == exporter.GENERATE_EMPTY
            else path
        )
        target = output / out_path
        if disposition == exporter.EXCLUDE:
            assert path not in by_path
            assert not target.exists(), path
            continue
        assert target.read_bytes() == (
            exporter._git_bytes(["cat-file", "blob", sha], ROOT)
            if disposition == exporter.COPY
            else exporter.generated_bytes(policy, out_path)
        ), path
        assert by_path[out_path]["disposition"] == disposition
        assert by_path[out_path]["mode"] == (
            mode if disposition == exporter.COPY else exporter.GENERATED_FILE_MODE
        )
        if disposition == exporter.COPY and mode == "100755" and os.name != "nt":
            assert os.access(target, os.X_OK), path
        if disposition == exporter.GENERATE_EMPTY and out_path != path:
            # A remapped generated root is materialized only at its neutral
            # output path; the campaign-specific source path stays absent.
            assert not (output / path).exists(), path


def test_excluded_surfaces_and_factory_machinery_are_absent(tmp_path):
    output, _receipt, _ = _sample_export(tmp_path)
    for relative in EXCLUDED_SAMPLE:
        target = output / relative
        if relative in EXCLUDED_BODY_MARKERS:
            assert target.is_file(), relative
            assert EXCLUDED_BODY_MARKERS[relative] not in target.read_text(encoding="utf-8")
        else:
            assert not target.exists(), relative
    for relative in FACTORY_ABSENT_FILES:
        assert not (output / relative).exists(), relative
    assert not (output / "bootstrap").exists()


def test_generated_mutable_roots_are_empty_contract_valid(tmp_path):
    output, _receipt, receipt_object = _sample_export(tmp_path)
    exported = {entry["path"] for entry in receipt_object["entries"]}
    for relative in GENERATED_ROOTS:
        assert relative in exported

    facts = json.loads((output / "knowledge" / "facts.json").read_text(encoding="utf-8"))
    assert facts["default_visibility"] in ("meta", "non_meta")
    assert facts["facts"] == []

    npc_state = json.loads((output / "npc" / "npc_state.json").read_text(encoding="utf-8"))
    assert npc_state["npcs"] == {}

    dm_meta = json.loads((output / "state" / "dm_meta.json").read_text(encoding="utf-8"))
    assert dm_meta["visibility"] == "meta"
    assert dm_meta["status"] == "uninitialized"

    for relative in (
        "state/daily_recap.json",
        "state/day_resolution.json",
        "state/live_status.json",
    ):
        document = json.loads((output / relative).read_text(encoding="utf-8"))
        assert document["status"] == "uninitialized"
        assert document["current_day"] is None

    hooks = json.loads(
        (output / "quests" / "narrative_hooks.json").read_text(encoding="utf-8")
    )
    assert hooks["day_status"] == "uninitialized"
    assert hooks["current_day"] is None

    reality = json.loads(
        (output / "realities" / "registry" / "campaign-root.json").read_text(encoding="utf-8")
    )
    # The clean genesis emits a campaign-neutral root identity at a
    # campaign-neutral path, not RHC-specific reality:rhc-primary at the
    # RHC-specific rhc-primary.json path; it is the unique parentless root of
    # the clean canvas.
    assert reality["reality_id"] == "reality:campaign-root"
    assert "parent_reality_id" not in reality
    assert not (output / "realities" / "registry" / "rhc-primary.json").exists()

    validator = output / "scripts" / "validate_canonical_root_json.py"
    assert validator.is_file()
    proc = subprocess.run(
        [sys.executable, str(validator)],
        cwd=str(output),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK:" in proc.stdout


def test_exported_neutral_reality_registry_passes_validator(tmp_path):
    # Proof 18: the exported neutral reality registry passes the same reality
    # validator without engine edits (the engine no longer privileges any fixed
    # root id, so a campaign-neutral root validates), and it is emitted at the
    # campaign-neutral path, never the RHC-specific rhc-primary.json path.
    output, _receipt, _ = _sample_export(tmp_path)
    registry = output / "realities" / "registry"
    reality_file = registry / "campaign-root.json"
    assert reality_file.is_file()
    assert not (registry / "rhc-primary.json").exists()
    record = json.loads(reality_file.read_text(encoding="utf-8"))
    assert record["reality_id"] == "reality:campaign-root"
    assert "parent_reality_id" not in record
    validator = output / "scripts" / "validate_realities.py"
    assert validator.is_file()
    proc = subprocess.run(
        [sys.executable, str(validator), str(registry)],
        cwd=str(output),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK:" in proc.stdout


def test_rhc_source_registry_remains_untouched():
    # Proof 19: the existing RHC source registry is unchanged by this Mission.
    source = ROOT / "realities" / "registry" / "rhc-primary.json"
    record = json.loads(source.read_text(encoding="utf-8"))
    assert record["reality_id"] == "reality:rhc-primary"
    assert "parent_reality_id" not in record
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_realities.py"),
         str(ROOT / "realities" / "registry")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK:" in proc.stdout


# --------------------------------------------------------------------------
# Copied executable portability
# --------------------------------------------------------------------------

# The RHC-only primary-reality identity token. The Z remap moves clean genesis
# to the campaign-neutral root, so a COPY-shipped executable/test surface that
# carries this token hard-codes an RHC-only source dependency that breaks
# inside the exported canvas even though the source repository stays green.
STALE_PRIMARY_IDENTITY_TOKEN = "rhc-primary"


def _shipped_executable_primary_identity_offenders(policy, tracked):
    """Return shipped surfaces whose non-prose bytes carry the RHC-only identity.

    Prose documents (``*.md``) may legitimately keep the reference as RHC
    source material; every shipped executable/structured surface -- COPY blobs
    and policy-generated content alike -- must resolve the primary reality by
    its structural role (the unique parentless root record) or by the
    campaign-neutral exported path instead, so the shipped surface keeps
    working after the Z remap.
    """
    offenders = []
    for mode, _obj_type, sha, path in tracked:
        disposition = exporter.disposition_for_path(policy, path)
        if disposition not in (exporter.COPY, exporter.GENERATE_EMPTY):
            continue
        if path.endswith(".md"):
            continue
        if disposition == exporter.COPY:
            blob = exporter._git_bytes(["cat-file", "blob", sha], ROOT)
        else:
            output_path = exporter.generate_output_path(policy, path)
            blob = exporter.generated_bytes(policy, output_path)
        if STALE_PRIMARY_IDENTITY_TOKEN in blob.decode("utf-8", errors="replace"):
            offenders.append(path)
    return offenders


def test_shipped_executable_surfaces_carry_no_rhc_only_primary_identity():
    # No shipped executable/structured surface (COPY or policy-generated) may
    # hard-code the RHC-only primary-reality identity that the Z remap replaces
    # in a clean canvas; prose documents keep the legitimate RHC-source
    # references.
    policy = _policy()
    tracked = exporter.tracked_entries("HEAD", ROOT)
    assert _shipped_executable_primary_identity_offenders(policy, tracked) == []


def test_shipped_executable_guard_catches_a_stale_copied_reference(monkeypatch):
    # Negative proof: the guard actually catches the exact regression class --
    # a COPY-shipped executable/test that hard-codes the remapped RHC-only
    # primary-reality path -- instead of passing vacuously.
    stale_path = "tests/stale_copied_test.py"
    stale_sha = "2" * 40
    clean_sha = "3" * 40
    blobs = {
        stale_sha: b'PATH = ROOT / "realities" / "registry" / "rhc-primary.json"\n',
        clean_sha: b'PATH = ROOT / "realities" / "registry" / "campaign-root.json"\n',
    }
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] in blobs:
            return blobs[args[2]]
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    tracked = [
        ("100644", "blob", stale_sha, stale_path),
        ("100644", "blob", clean_sha, "tests/clean_copied_test.py"),
    ]
    policy = {
        "rules": [
            {"disposition": exporter.COPY, "match": stale_path},
            {"disposition": exporter.COPY, "match": "tests/clean_copied_test.py"},
        ]
    }
    assert _shipped_executable_primary_identity_offenders(policy, tracked) == [stale_path]


def test_shipped_generated_workflow_cannot_carry_the_stale_identity():
    # The generated RT01 workflow is shipped executable content produced from
    # the policy's generation constant; the guard must scan it too, so a stale
    # RHC-only identity could never ship through the generated surface.
    policy = _policy()
    assert (
        policy["generate"][RUNTIME_WORKFLOW_PATH].count(STALE_PRIMARY_IDENTITY_TOKEN)
        == 0
    )


def _path_filter_matches(pattern, path):
    """Whether a GitHub Actions path-filter pattern selects ``path``.

    Supports the two pattern species the Z workflow declares: an exact
    repository-relative path, and a directory prefix of the form ``dir/**``
    (every file under ``dir`` at any depth).
    """
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-2])
    return path == pattern


def test_path_filter_matcher_catches_an_uncovered_surface():
    # Non-vacuity proof for the trigger-coverage matcher: the two declared
    # pattern species match what GitHub Actions matches, and a surface outside
    # every pattern is detected rather than silently admitted.
    assert _path_filter_matches(
        "tests/**", "tests/post_ev2_14/test_brainstorm_lab.py"
    )
    assert _path_filter_matches("requirements.txt", "requirements.txt")
    assert not _path_filter_matches("schemas/**", "tests/some_test.py")
    assert not _path_filter_matches("requirements.txt", "other.txt")


def test_z_workflow_triggers_cover_the_guard_scan_surface():
    # The copied-executable guard scans every shipped surface except prose
    # *.md (COPY blobs and policy-generated content alike), so a change to any
    # scanned surface must schedule this proof in BOTH events. A scanned
    # surface landing outside every declared path-filter pattern fails closed,
    # forcing the workflow admission to be extended.
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    events = _workflow_event_paths(text)
    policy = _policy()
    scanned = [
        path
        for _mode, _obj_type, _sha, path in exporter.tracked_entries("HEAD", ROOT)
        if exporter.disposition_for_path(policy, path)
        in (exporter.COPY, exporter.GENERATE_EMPTY)
        and not path.endswith(".md")
    ]
    assert scanned
    uncovered = {
        path
        for path in scanned
        if not any(
            _path_filter_matches(pattern, path) for pattern in events["pull_request"]
        )
    } | {
        path
        for path in scanned
        if not any(
            _path_filter_matches(pattern, path) for pattern in events["push"]
        )
    }
    assert uncovered == set(), sorted(uncovered)


# The COPY-shipped POST-EV2-14 suite is a portable bounded-lifecycle proof: it
# carries no source/factory-only assertion and no context discriminator, so it
# runs unchanged in the source repository and inside an exported canvas. The
# equivalent source wiring assertions -- which may only police RHC factory
# machinery from source RHC -- are owned HERE, in this EXCLUDE-owned factory
# proof that never ships in the exported tree.
POST_EV2_14_SURFACES = (
    "docs/POST-EV2-14-DISPOSABLE-BRAINSTORM-LAB.md",
    "scripts/brainstorm_lab.py",
    "tests/post_ev2_14/test_brainstorm_lab.py",
)
ENTITY_V2_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "entity-v2-identity.yml"


def test_source_entity_v2_workflow_runs_post_ev2_14_proof():
    # Re-homed from the copied POST-EV2-14 suite: the source Entity V2 workflow
    # still schedules the POST-EV2-14 brainstorm-lab proof, so the portable
    # suite stays exercised by source CI.
    workflow = ENTITY_V2_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "tests/post_ev2_14/test_brainstorm_lab.py" in workflow


def test_export_policy_classifies_post_ev2_14_surfaces_as_copy():
    # Re-homed from the copied POST-EV2-14 suite: the export policy still
    # classifies every POST-EV2-14 surface COPY, so the portable suite ships
    # into every clean canvas.
    rules = {rule["match"]: rule["disposition"] for rule in _policy()["rules"]}
    for relative in POST_EV2_14_SURFACES:
        assert rules.get(relative) == "COPY", relative


def test_fresh_export_contains_post_ev2_14_surfaces(tmp_path):
    # Re-homed from the copied POST-EV2-14 suite: a fresh export of exact HEAD
    # still contains every POST-EV2-14 surface.
    output, _receipt, _ = _sample_export(tmp_path)
    for relative in POST_EV2_14_SURFACES:
        assert (output / relative).is_file(), relative

# --------------------------------------------------------------------------
# GENERATE_EMPTY output-path remap
# --------------------------------------------------------------------------

def test_generate_output_path_remaps_to_neutral_path():
    # The clean genesis root reality is materialized at the campaign-neutral
    # output path declared by its GENERATE_EMPTY rule.
    policy = _policy()
    assert (
        exporter.generate_output_path(policy, "realities/registry/rhc-primary.json")
        == "realities/registry/campaign-root.json"
    )


def test_generate_output_path_defaults_to_the_source_path():
    policy = _policy()
    assert (
        exporter.generate_output_path(policy, "state/daily_recap.json")
        == "state/daily_recap.json"
    )


def test_generate_output_path_requires_a_generate_rule():
    with pytest.raises(exporter.ExportError):
        exporter.generate_output_path(_policy(), "no/such/generate/rule.json")


def test_output_path_equal_to_its_source_match_is_rejected():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["rules"][0]["output_path"] = policy["rules"][0]["match"]
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(json.dumps(policy))


def test_output_path_colliding_with_another_output_path_is_rejected():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["rules"] = policy["rules"] + [
        {
            "disposition": "GENERATE_EMPTY",
            "match": "synthetic/generated-source.json",
            "output_path": "realities/registry/campaign-root.json",
        },
    ]
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(json.dumps(policy))


def test_rule_match_colliding_with_a_generated_output_path_is_rejected():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["rules"] = policy["rules"] + [
        {"disposition": "COPY", "match": "realities/registry/campaign-root.json"},
    ]
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(json.dumps(policy))


def test_copy_rule_with_an_output_path_is_rejected():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["rules"] = policy["rules"] + [
        {
            "disposition": "COPY",
            "match": "synthetic/copy-source.txt",
            "output_path": "synthetic/copy-remapped.txt",
        },
    ]
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(json.dumps(policy))


def test_generate_empty_directory_prefix_rule_is_rejected():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["rules"] = policy["rules"] + [
        {"disposition": "GENERATE_EMPTY", "match": "realities/registry/"},
    ]
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(json.dumps(policy))


def _policy_with_neutral_output_path(output_path):
    """Return the tracked policy with the neutral genesis rule remapped elsewhere."""
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    for rule in policy["rules"]:
        if rule["disposition"] == "GENERATE_EMPTY" and (
            rule["match"] == "realities/registry/rhc-primary.json"
        ):
            rule["output_path"] = output_path
            break
    else:
        raise AssertionError("neutral remap rule not found in the tracked policy")
    return policy


@pytest.mark.parametrize(
    "aliased",
    [
        "./README.md",  # normalizes onto the COPY destination README.md
        "docs/./guide.md",  # interior self-component alias
        "realities/registry/./campaign-root.json",
        "realities/registry/campaign-root.json/.",
        "docs/../README.md",
        ".",
        "..",
    ],
)
def test_output_path_dot_component_alias_is_rejected(aliased):
    # A dot path component lets a remap target normalize away into a different
    # output destination than its raw string (e.g. ``./README.md`` materializes
    # ``README.md``), which raw-string collision comparison cannot see; the
    # target must fail closed as an alias instead of being compared raw.
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(
            json.dumps(_policy_with_neutral_output_path(aliased))
        )


def test_output_path_landing_inside_an_exclude_prefix_is_rejected():
    # The normalized remap target must respect every EXCLUDE-owned namespace,
    # not only exact path equality: a generated file under an EXCLUDE prefix
    # would smuggle generated content into an excluded namespace.
    for inside_excluded in (
        "supabase/canaries/generated.json",
        "bootstrap/generated.json",
        "tests/post_ev2_z/generated.py",
    ):
        with pytest.raises(exporter.ExportError):
            exporter.parse_policy(
                json.dumps(_policy_with_neutral_output_path(inside_excluded))
            )


def test_output_path_colliding_with_an_exact_exclude_match_is_rejected():
    # A remap target equal to an EXCLUDE rule match is refused even when that
    # EXCLUDE rule appears *after* the remapping rule in the policy list.
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(
            json.dumps(_policy_with_neutral_output_path("supabase/README.md"))
        )


def test_output_path_nests_inside_an_existing_output_destination():
    # A remap target nested beneath an existing generated output path would
    # require that output to be a directory; it must fail closed.
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["rules"] = policy["rules"] + [
        {
            "disposition": "GENERATE_EMPTY",
            "match": "synthetic/nested-source.json",
            "output_path": "realities/registry/campaign-root.json/nested.json",
        },
    ]
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(json.dumps(policy))


def test_existing_output_destination_nests_inside_the_remapped_target():
    # The mirror direction: a remap target whose path is a directory prefix of
    # an existing generated output (or of an exact policy source path) would
    # require the target itself to be a directory; it must fail closed.
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["rules"] = policy["rules"] + [
        {
            "disposition": "GENERATE_EMPTY",
            "match": "synthetic/plain-source.json",
            "output_path": "realities/registry",
        },
    ]
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(json.dumps(policy))

    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(
            json.dumps(_policy_with_neutral_output_path("realities"))
        )


def test_output_path_colliding_with_an_existing_copy_destination_is_rejected():
    # A remap target equal to a retained COPY destination (the motivating
    # collision the raw-string comparison missed through its ``./`` alias) is
    # refused; the existing COPY file at that path is the output authority.
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(
            json.dumps(_policy_with_neutral_output_path("README.md"))
        )


def test_output_path_nests_inside_an_exact_copy_rule_match():
    # The single exported canvas cannot materialize a file beneath another
    # retained COPY file, so a remap target nested under an exact rule match
    # fails closed even though it is not a raw-string equality collision.
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(
            json.dumps(
                _policy_with_neutral_output_path(
                    "scripts/validate_entities.py/smuggled.json"
                )
            )
        )


# --------------------------------------------------------------------------
# Engine version stamp (receipt metadata, single source of truth)
# --------------------------------------------------------------------------

def test_engine_version_source_is_present_and_semver():
    # The source is the single authority; the proof must not pin a release
    # literal as a second source of truth. It only asserts the source exists and
    # is a valid semver, and the receipt proof compares against this value.
    text = ENGINE_VERSION_PATH.read_text(encoding="utf-8")
    version = text.strip()
    assert exporter.SEMVER_RE.match(version)


def test_receipt_records_engine_version_field(tmp_path):
    output, receipt, receipt_object = _sample_export(tmp_path)
    expected = ENGINE_VERSION_PATH.read_text(encoding="utf-8").strip()
    # The in-memory receipt object and the on-disk receipt both carry the field.
    assert receipt_object["engine_version"] == expected
    on_disk = json.loads(receipt.read_text(encoding="utf-8"))
    assert on_disk["engine_version"] == expected
    # The version source is control-plane metadata; it is not shipped into the
    # exported customer tree.
    assert not (output / "ENGINE_VERSION").exists()


def test_engine_version_is_sourced_from_the_exact_commit(tmp_path, monkeypatch):
    # Rewrite the version source as it is seen *at the exact commit* and prove
    # the receipt binds to that commit value, not to the working tree.
    real = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:1] == ["show"] and args[1].endswith(":ENGINE_VERSION"):
            return b"2.3.4\n"
        return real(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    _output, _receipt, receipt_object = _sample_export(tmp_path)
    assert receipt_object["engine_version"] == "2.3.4"


def test_missing_engine_version_source_fails_closed(tmp_path, monkeypatch):
    real = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:1] == ["show"] and args[1].endswith(":ENGINE_VERSION"):
            raise exporter.ExportError("no such path in commit")
        return real(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    with pytest.raises(exporter.ExportError):
        exporter.export(
            ROOT, "HEAD", tmp_path / "canvas", tmp_path / "canvas.receipt.json"
        )
    assert not (tmp_path / "canvas").exists()


def test_malformed_engine_version_source_fails_closed(tmp_path, monkeypatch):
    real = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:1] == ["show"] and args[1].endswith(":ENGINE_VERSION"):
            return b"not-a-version\n"
        return real(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    with pytest.raises(exporter.ExportError):
        exporter.export(
            ROOT, "HEAD", tmp_path / "canvas", tmp_path / "canvas.receipt.json"
        )


@pytest.mark.parametrize(
    "good",
    [
        "1.0.0",
        "1.0.0\n",
        "0.0.0",
        "10.20.30",
        "1.2.3-rc.1",
        "1.2.3+build.5",
        "1.2.3-rc.1+build.5",
    ],
)
def test_parse_engine_version_accepts_semver(good):
    assert exporter.parse_engine_version(good) == good.strip()


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "\n", "1.0", "1.0.0.0", "v1.0.0", "01.0.0", "abc", "1.0.0\n2.0.0"],
)
def test_parse_engine_version_rejects_malformed(bad):
    with pytest.raises(exporter.ExportError):
        exporter.parse_engine_version(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "1\u0661.0.0",       # Arabic-Indic one in MINOR
        "\u0661.0.0",         # Arabic-Indic one in MAJOR
        "1.0.\u0661",         # Arabic-Indic one in PATCH
        "1.0.0-\u0661",       # Arabic-Indic numeric prerelease identifier
        "1.\uff11.0",         # fullwidth one in MINOR
    ],
)
def test_parse_engine_version_rejects_unicode_decimal_digits(bad):
    # SemVer numeric identifiers permit ASCII ``0-9`` only. Python's ``\d`` also
    # matches Unicode decimal digits, so a malformed source such as "1\u0661.0.0"
    # must still be rejected fail-closed rather than accepted as a valid version.
    with pytest.raises(exporter.ExportError):
        exporter.parse_engine_version(bad)


def test_unicode_digit_engine_version_source_fails_closed(tmp_path, monkeypatch):
    # The same malformed value reaching the exporter through the real
    # ENGINE_VERSION read path (the exact commit source) must fail the export
    # closed, writing no canvas and no receipt.
    real = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:1] == ["show"] and args[1].endswith(":ENGINE_VERSION"):
            return "1\u0661.0.0\n".encode("utf-8")
        return real(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    with pytest.raises(exporter.ExportError):
        exporter.export(
            ROOT, "HEAD", tmp_path / "canvas", tmp_path / "canvas.receipt.json"
        )
    assert not (tmp_path / "canvas").exists()


# --------------------------------------------------------------------------
# Reference integrity
# --------------------------------------------------------------------------

def test_retained_routes_resolve(tmp_path):
    # A clean export runs the reference check as part of export() and succeeds.
    output, _receipt, _ = _sample_export(tmp_path)
    assert (output / "AGENT_HANDOFF.md").is_file()
    assert (output / "docs" / "DM_CONTROL_ROOM.md").is_file()
    assert (output / "docs" / "RHC_WORKSYSTEM.md").is_file()


def test_dangling_route_fails_closed():
    policy = _policy()
    # Remove the COPY rule for a real link target and force it EXCLUDE.
    policy["rules"] = [
        rule for rule in policy["rules"]
        if not (rule["disposition"] == "COPY" and rule["match"] == "PROJECT_PRIMER.md")
    ] + [{"disposition": "EXCLUDE", "match": "PROJECT_PRIMER.md"}]
    tracked = exporter.tracked_entries("HEAD", ROOT)
    export_files = [
        path for _mode, _otype, _sha, path in tracked
        if exporter.disposition_for_path(policy, path) != exporter.EXCLUDE
    ]
    skeleton = exporter._skeleton_dirs("HEAD", ROOT)
    dangling, _dynamic = exporter.check_reference_integrity(
        policy, tracked, export_files, skeleton, ROOT, report=True
    )
    assert any(resolved == "PROJECT_PRIMER.md" for _ref, _cand, resolved in dangling)


def test_workflow_run_routes_are_extracted():
    sample = (
        "on:\n"
        "  push:\n"
        "    paths:\n"
        "      - \"supabase/**\"\n"
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: python scripts/validate_entities.py tests/fixtures/entities/valid\n"
        "      - name: folded\n"
        "        run: |\n"
        "          pytest tests/rt02 -q\n"
        "          pytest tests/test_runtime_published_mirror.py\n"
        "        env:\n"
        "          DSN: postgresql://u:p@localhost:5432/db\n"
    )
    routes = {route for route, _dynamic in exporter._workflow_routes(sample)}
    assert "scripts/validate_entities.py" in routes
    assert "tests/fixtures/entities/valid" in routes
    assert "tests/rt02" in routes
    assert "tests/test_runtime_published_mirror.py" in routes
    assert not any(route.startswith("supabase") for route in routes)
    assert not any("postgresql" in route for route in routes)


def test_dynamic_workflow_route_fragment_is_yielded_as_dynamic():
    # A run: argument that directly abuts an Actions expression is a fragment
    # of a dynamically computed string (GitHub interpolates it at runtime), not
    # a statically resolvable repository path. The extractor yields it flagged
    # dynamic so the integrity check can classify it honestly instead of
    # treating it as either a satisfied or an excluded dependency.
    sample = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: git fetch --no-tags origin \"refs/pull/${{ github.event.pull_request.number }}/head\"\n"
        "      - run: pytest tests/real_dir -q\n"
    )
    routes = dict(exporter._workflow_routes(sample))
    assert routes.get("refs/pull/") is True
    assert routes.get("tests/real_dir") is False


def test_workflow_run_route_dangle_fails_closed():
    # A shipped workflow must not invoke a test file the policy excludes. The
    # shipped RT01 workflow is the policy-GENERATED portability adaptation, so
    # this check exercises the generated surface's routes: the generated bytes
    # still invoke this file (the constant is derived from the source
    # workflow), the file is excluded, so the route dangles and must be
    # reported by the same check that covers Markdown and COPY surfaces.
    policy = _policy()
    # Exclude a real file that a retained workflow invokes; the workflow route
    # must then be reported as dangling by the same check that covers Markdown.
    policy["rules"] = [
        rule for rule in policy["rules"]
        if not (rule["disposition"] == "COPY"
                and rule["match"] == "tests/test_runtime_published_mirror.py")
    ] + [{"disposition": "EXCLUDE",
          "match": "tests/test_runtime_published_mirror.py"}]
    tracked = exporter.tracked_entries("HEAD", ROOT)
    export_files = [
        path for _mode, _otype, _sha, path in tracked
        if exporter.disposition_for_path(policy, path) != exporter.EXCLUDE
    ]
    skeleton = exporter._skeleton_dirs("HEAD", ROOT)
    dangling, _dynamic = exporter.check_reference_integrity(
        policy, tracked, export_files, skeleton, ROOT, report=True
    )
    assert any(
        referrer == ".github/workflows/rt01-runtime.yml"
        and resolved == "tests/test_runtime_published_mirror.py"
        for referrer, _candidate, resolved in dangling
    )


def test_skeleton_only_workflow_route_fails_closed():
    # THE Z6 false positive: a preserved (empty) skeleton directory must never
    # satisfy an executable workflow dependency. Forcing the shipped RT01
    # workflow back to its source bytes re-introduces the four source-only
    # pytest arguments; every one of them resolves only to an empty preserved
    # skeleton in the export (zero exported test modules), so the check must
    # report all four as failures instead of blessing them as present.
    policy = _policy()
    policy["rules"] = [
        rule for rule in policy["rules"]
        if not (rule["disposition"] == "GENERATE_EMPTY"
                and rule["match"] == ".github/workflows/rt01-runtime.yml")
    ] + [{"disposition": "COPY",
          "match": ".github/workflows/rt01-runtime.yml"}]
    tracked = exporter.tracked_entries("HEAD", ROOT)
    export_files = [
        exporter.generate_output_path(policy, path)
        if exporter.disposition_for_path(policy, path) == exporter.GENERATE_EMPTY
        else path
        for _mode, _otype, _sha, path in tracked
        if exporter.disposition_for_path(policy, path) != exporter.EXCLUDE
    ]
    skeleton = exporter._skeleton_dirs("HEAD", ROOT)
    dangling, _dynamic = exporter.check_reference_integrity(
        policy, tracked, export_files, skeleton, ROOT, report=True
    )
    resolved_dirs = {resolved for _ref, _cand, resolved in dangling}
    for source_only in SOURCE_ONLY_RUNTIME_TEST_TREES:
        assert source_only in resolved_dirs, (source_only, sorted(resolved_dirs))
    with pytest.raises(exporter.ExportError):
        exporter.check_reference_integrity(
            policy, tracked, export_files, skeleton, ROOT, report=False
        )


def test_never_existing_workflow_route_fails_closed(monkeypatch):
    # A statically written run: argument naming a path that exists nowhere in
    # the source tree cannot resolve in any exported tree either. It must fail
    # the export closed instead of being silently ignored as a non-route.
    workflow_path = ".github/workflows/synthetic-never-existing.yml"
    blob_sha = "0" * 40
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest tests/never_existed_dir -q\n"
    )
    tracked = [("100644", "blob", blob_sha, workflow_path)]
    policy = {"rules": [{"disposition": exporter.COPY, "match": workflow_path}]}
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] == blob_sha:
            return workflow_text.encode("utf-8")
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    dangling, dynamic = exporter.check_reference_integrity(
        policy, tracked, [workflow_path], [], ROOT, report=True
    )
    assert dynamic == []
    assert any(
        referrer == workflow_path and candidate == "tests/never_existed_dir"
        and resolved is None
        for referrer, candidate, resolved in dangling
    )
    with pytest.raises(exporter.ExportError):
        exporter.check_reference_integrity(
            policy, tracked, [workflow_path], [], ROOT, report=False
        )


def test_dynamic_workflow_route_is_classified_never_proved(monkeypatch):
    # A dynamically computed route fragment is neither accepted nor failed: it
    # is returned for explicit honest classification (recorded in the receipt)
    # so the export never claims a dependency class it did not prove.
    workflow_path = ".github/workflows/synthetic-dynamic-route.yml"
    blob_sha = "0" * 40
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: git fetch --no-tags origin "
        "\"refs/pull/${{ github.event.pull_request.number }}/head\"\n"
        "      - run: python scripts/validate_write_boundary.py -h\n"
    )
    tracked = [
        ("100644", "blob", blob_sha, workflow_path),
        ("100644", "blob", "1" * 40, "scripts/validate_write_boundary.py"),
    ]
    policy = {
        "rules": [
            {"disposition": exporter.COPY, "match": workflow_path},
            {"disposition": exporter.COPY,
             "match": "scripts/validate_write_boundary.py"},
        ]
    }
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] == blob_sha:
            return workflow_text.encode("utf-8")
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    dangling, dynamic = exporter.check_reference_integrity(
        policy, tracked, [p for _m, _o, _s, p in tracked], [], ROOT, report=True
    )
    assert dangling == []
    assert dynamic == [(workflow_path, "refs/pull/")]


def _run_synthetic_integrity(monkeypatch, workflow_path, workflow_text,
                             extra_tracked=(), report=True):
    """Run ``check_reference_integrity`` over one synthetic COPY workflow.

    ``workflow_text`` is served as the workflow blob; ``extra_tracked`` entries
    are further ``(mode, type, sha, path)`` tracked files the policy COPYs (their
    bytes are never read -- only a Markdown/workflow control-plane surface is
    read -- so they stand in for other exported files). ``report=True`` returns
    the failure list; ``report=False`` raises as the real export does.
    """
    blob_sha = "0" * 40
    tracked = [("100644", "blob", blob_sha, workflow_path), *extra_tracked]
    policy = {
        "rules": [
            {"disposition": exporter.COPY, "match": workflow_path},
            *({"disposition": exporter.COPY, "match": path}
              for _mode, _otype, _sha, path in extra_tracked),
        ]
    }
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] == blob_sha:
            return workflow_text.encode("utf-8")
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    return exporter.check_reference_integrity(
        policy, tracked, [p for _m, _o, _s, p in tracked], [], ROOT,
        report=report,
    )


def test_workflow_routes_keep_dynamic_and_static_same_route():
    # The same normalized route can occur both as a dynamic fragment and as a
    # static argument. Deduplicating by route alone would drop one of them, so
    # the extractor must classify and deduplicate independently: both
    # occurrences survive in either order.
    dynamic_first = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest tests/shared${{ matrix.suffix }}\n"
        "      - run: pytest tests/shared -q\n"
    )
    static_first = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest tests/shared -q\n"
        "      - run: pytest tests/shared${{ matrix.suffix }}\n"
    )
    for sample in (dynamic_first, static_first):
        routes = list(exporter._workflow_routes(sample))
        assert ("tests/shared", True) in routes
        assert ("tests/shared", False) in routes


def test_workflow_route_dynamic_before_static_missing_fails_closed(monkeypatch):
    # Codex P2, ordering one: a dynamic occurrence of a route must not suppress
    # the later static occurrence. When only the dynamic fragment is retained,
    # the missing static executable dependency is never checked. The static
    # occurrence must fail the export closed while the dynamic fragment remains
    # explicitly represented (it feeds the receipt's unresolved evidence).
    workflow_path = ".github/workflows/synthetic-dynamic-before-static.yml"
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest tests/missing${{ matrix.suffix }}\n"
        "      - run: pytest tests/missing -q\n"
    )
    dangling, dynamic = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text
    )
    assert (workflow_path, "tests/missing", None) in dangling
    assert (workflow_path, "tests/missing") in dynamic
    with pytest.raises(exporter.ExportError):
        _run_synthetic_integrity(
            monkeypatch, workflow_path, workflow_text, report=False
        )


def test_workflow_route_static_before_dynamic_missing_fails_closed(monkeypatch):
    # Codex P2, ordering two: the reverse ordering must not silently omit the
    # dynamic receipt entry. The static missing path fails closed and the
    # dynamic occurrence is still recorded as consciously unproven.
    workflow_path = ".github/workflows/synthetic-static-before-dynamic.yml"
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest tests/missing -q\n"
        "      - run: pytest tests/missing${{ matrix.suffix }}\n"
    )
    dangling, dynamic = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text
    )
    assert (workflow_path, "tests/missing", None) in dangling
    assert (workflow_path, "tests/missing") in dynamic
    with pytest.raises(exporter.ExportError):
        _run_synthetic_integrity(
            monkeypatch, workflow_path, workflow_text, report=False
        )


def test_workflow_route_static_present_and_dynamic_coexist(monkeypatch):
    # A present static route and a dynamic occurrence of the same route coexist
    # without a false failure: the dynamic fragment is recorded unproven, the
    # static occurrence resolves, and nothing dangles.
    workflow_path = ".github/workflows/synthetic-present-and-dynamic.yml"
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest tests/real_dir${{ matrix.suffix }}\n"
        "      - run: pytest tests/real_dir -q\n"
    )
    present = (("100644", "blob", "1" * 40, "tests/real_dir/test_present.py"),)
    dangling, dynamic = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text, extra_tracked=present
    )
    assert dangling == []
    assert (workflow_path, "tests/real_dir") in dynamic


def test_workflow_route_same_class_duplicates_still_dedup(monkeypatch):
    # Ordinary same-class deduplication is preserved: two identical static
    # occurrences of one missing route yield a single failure and no dynamic
    # receipt entry.
    workflow_path = ".github/workflows/synthetic-same-class.yml"
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest tests/missing -q\n"
        "      - run: pytest tests/missing\n"
    )
    dangling, dynamic = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text
    )
    assert [entry for entry in dangling if entry[1] == "tests/missing"] == [
        (workflow_path, "tests/missing", None)
    ]
    assert dynamic == []


def test_workflow_routes_dynamic_working_directory_marks_operands_unresolved():
    # Codex P2 (fresh at 9e328c8): an effective working directory that cannot be
    # statically resolved (an Actions expression) means the command's real run
    # location is unknown. Its repo-relative operands must be classified
    # unresolved (is_dynamic=True) instead of being silently re-rooted at the
    # repository root, where a root-level path could falsely satisfy a
    # dependency the referencing step never actually reaches. Precedence is
    # preserved: a static step-level override still wins over a dynamic default.
    sample = (
        "defaults:\n"
        "  run:\n"
        "    working-directory: ${{ vars.CANVAS }}\n"
        "jobs:\n"
        "  workflow-default:\n"
        "    steps:\n"
        "      - run: pytest tests/unit\n"
        "  job-default:\n"
        "    defaults:\n"
        "      run:\n"
        "        working-directory: ${{ matrix.dir }}\n"
        "    steps:\n"
        "      - run: pytest tests/job_unit\n"
        "  step-dynamic:\n"
        "    steps:\n"
        "      - working-directory: ${{ matrix.dir }}\n"
        "        run: pytest tests/step_unit\n"
        "  step-override-static:\n"
        "    steps:\n"
        "      - working-directory: tests/steps\n"
        "        run: pytest step_override_only.py\n"
        "      - run: pytest tests/defaulted_operand\n"
    )
    routes = dict(exporter._workflow_routes(sample))
    # Dynamic workflow-level default and dynamic job-level default each mark
    # their step's operand unresolved rather than repo-root static.
    assert routes.get("tests/unit") is True
    assert routes.get("tests/job_unit") is True
    # A step-level dynamic working directory overrides the (dynamic) default and
    # still marks its operand unresolved.
    assert routes.get("tests/step_unit") is True
    # A static step-level working directory overrides the dynamic default, so
    # that step's operand stays statically rooted and provable.
    assert routes.get("tests/steps/step_override_only.py") is False
    # A step with no override inherits the dynamic workflow default, so its
    # operand is unresolved too.
    assert routes.get("tests/defaulted_operand") is True


def test_dynamic_working_directory_route_is_recorded_not_falsely_proved(monkeypatch):
    # The adversarial P2 case: a real shipped root-level ``tests/unit`` exists,
    # so the pre-repair classifier -- which re-rooted a dynamic working
    # directory at the repository root -- blessed the dependency as proved even
    # though the matrix directory may not contain it. With the fix the operand
    # cannot be located, so it is recorded as unresolved dynamic (and the
    # unresolvable working directory with it); nothing is falsely proved.
    workflow_path = ".github/workflows/synthetic-dynamic-workdir.yml"
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - working-directory: ${{ matrix.dir }}\n"
        "        run: pytest tests/unit\n"
    )
    present = (("100644", "blob", "1" * 40, "tests/unit/test_present.py"),)
    dangling, dynamic = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text, extra_tracked=present
    )
    assert dangling == []
    assert (workflow_path, "tests/unit") in dynamic
    assert (workflow_path, "working-directory '${{ matrix.dir }}'") in dynamic


def test_dynamic_working_directory_operand_without_root_path_is_unresolved(monkeypatch):
    # A run argument that exists nowhere in the source tree fails the export
    # closed when it is statically written (see the never-existing-route proof).
    # Under an unresolvable working directory it may legitimately exist inside
    # that unknown directory, so the honest classification is "unresolved", not
    # "missing": the export does not fail and the operand is recorded unproven.
    workflow_path = ".github/workflows/synthetic-dynamic-workdir-missing.yml"
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - working-directory: ${{ matrix.dir }}\n"
        "        run: pytest tests/nowhere\n"
    )
    dangling, dynamic = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text
    )
    assert dangling == []
    assert (workflow_path, "tests/nowhere") in dynamic


def test_dynamic_working_directory_and_static_occurrence_coexist():
    # A dynamic-working-directory occurrence and a static repo-root occurrence
    # of the same route are separate classifications: the static occurrence is
    # still checked (a missing static dependency still fails closed) and the
    # dynamic occurrence is still recorded unproven, in either order.
    dynamic_first = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - working-directory: ${{ matrix.dir }}\n"
        "        run: pytest tests/shared\n"
        "      - run: pytest tests/shared -q\n"
    )
    static_first = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest tests/shared -q\n"
        "      - working-directory: ${{ matrix.dir }}\n"
        "        run: pytest tests/shared\n"
    )
    for sample in (dynamic_first, static_first):
        routes = list(exporter._workflow_routes(sample))
        assert ("tests/shared", True) in routes
        assert ("tests/shared", False) in routes


def test_dynamic_working_directory_static_occurrence_still_fails_closed(monkeypatch):
    # Non-vacuity end to end: the dynamic occurrence must not suppress the
    # static occurrence's missing dependency. The static repo-root reference to
    # tests/absent exists nowhere, so the export fails closed while the dynamic
    # occurrence is still recorded as consciously unproven.
    workflow_path = ".github/workflows/synthetic-dynamic-and-static.yml"
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - working-directory: ${{ matrix.dir }}\n"
        "        run: pytest tests/absent\n"
        "      - run: pytest tests/absent -q\n"
    )
    dangling, dynamic = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text
    )
    assert (workflow_path, "tests/absent", None) in dangling
    assert (workflow_path, "tests/absent") in dynamic
    with pytest.raises(exporter.ExportError):
        _run_synthetic_integrity(
            monkeypatch, workflow_path, workflow_text, report=False
        )


# ---------------------------------------------------------------------------
# Path-operand expression provenance (C1-C7): an Actions expression inside one
# shell argument is one dynamic path operand even when separated from a path
# fragment by a slash, so no token inside it may be claimed a proved static
# dependency. Expression-internal whitespace (`${{ matrix.dir }}`) is exercised
# throughout; C5/C6 are the must-preserve controls.
# ---------------------------------------------------------------------------


def test_expression_prefix_operand_is_recorded_unresolved_not_proved(monkeypatch):
    # C1: `${{ matrix.dir }}/tests/unit` is ONE operand; `_TOKEN_RE` sees only
    # the trailing `tests/unit`. The pre-repair classifier treated it as a
    # provable repo-root static dependency, so a shipped root-level
    # `tests/unit` falsely satisfied it and the operand never reached the
    # receipt. It must instead be classified dynamic and recorded unproven.
    workflow_path = ".github/workflows/synthetic-expression-prefix.yml"
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest ${{ matrix.dir }}/tests/unit\n"
    )
    present = (("100644", "blob", "1" * 40, "tests/unit/test_present.py"),)
    dangling, dynamic = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text, extra_tracked=present
    )
    assert dangling == []
    assert dynamic == [(workflow_path, "tests/unit")]


def test_expression_prefix_operand_without_root_path_is_unresolved(monkeypatch):
    # C1/C3: with no root-level path the pre-repair classifier raised a FALSE
    # static failure ("names a path that does not exist in the source tree").
    # The operand is dynamic, so it is recorded unproven and does not fail.
    workflow_path = ".github/workflows/synthetic-expression-prefix-absent.yml"
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest ${{ matrix.dir }}/tests/absent\n"
    )
    dangling, dynamic = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text
    )
    assert dangling == []
    assert dynamic == [(workflow_path, "tests/absent")]


def test_expression_prefix_filename_fragment_is_dynamic(monkeypatch):
    # C3: a bare filename fragment after a prefix expression is part of the same
    # dynamic operand, not a standalone static `unit.py` at the repo root.
    workflow_path = ".github/workflows/synthetic-expression-prefix-file.yml"
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest ${{ matrix.dir }}/unit.py\n"
    )
    dangling, dynamic = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text
    )
    assert dangling == []
    assert dynamic == [(workflow_path, "unit.py")]


def test_expression_infix_operand_fragments_are_all_dynamic(monkeypatch):
    # C2: `tests/${{ matrix.dir }}/unit.py` is one operand split by `_TOKEN_RE`
    # into `tests/` and `unit.py`. Pre-repair, `tests/` was dynamic but
    # `unit.py` was independently (and wrongly) static. Both fragments must be
    # dynamic; neither may become a standalone proved or failed dependency.
    workflow_path = ".github/workflows/synthetic-expression-infix.yml"
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest tests/${{ matrix.dir }}/unit.py\n"
    )
    dangling, dynamic = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text
    )
    assert dangling == []
    assert dynamic == [
        (workflow_path, "tests/"),
        (workflow_path, "unit.py"),
    ]


def test_quoted_expression_operand_is_dynamic(monkeypatch):
    # C4: quoting an operand does not change that it is one dynamically
    # computed path, so the trailing fragment is still unproven, never proved.
    workflow_path = ".github/workflows/synthetic-expression-quoted.yml"
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest '${{ matrix.dir }}/tests/unit'\n"
    )
    present = (("100644", "blob", "1" * 40, "tests/unit/test_present.py"),)
    dangling, dynamic = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text, extra_tracked=present
    )
    assert dangling == []
    assert dynamic == [(workflow_path, "tests/unit")]


def test_expression_operand_and_static_same_route_both_orders(monkeypatch):
    # C7: the same normalized route occurring once inside a dynamic operand and
    # once as a genuinely static argument (either order) keeps BOTH
    # classifications -- the missing static dependency still fails closed and
    # the dynamic operand is still recorded unproven.
    dynamic_first = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest ${{ matrix.dir }}/tests/shared\n"
        "      - run: pytest tests/shared -q\n"
    )
    static_first = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest tests/shared -q\n"
        "      - run: pytest ${{ matrix.dir }}/tests/shared\n"
    )
    for index, sample in enumerate((dynamic_first, static_first)):
        workflow_path = f".github/workflows/synthetic-expression-mixed-{index}.yml"
        dangling, dynamic = _run_synthetic_integrity(
            monkeypatch, workflow_path, sample
        )
        assert (workflow_path, "tests/shared") in dynamic
        assert (workflow_path, "tests/shared", None) in dangling
        with pytest.raises(exporter.ExportError):
            _run_synthetic_integrity(
                monkeypatch, workflow_path, sample, report=False
            )


def test_expression_direct_suffix_operand_stays_dynamic():
    # C5 (must-preserve control): an expression directly suffixed on the path
    # (no separator) was already dynamic; it stays dynamic.
    sample = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest tests/unit${{ matrix.suffix }}\n"
    )
    assert ("tests/unit", True) in list(exporter._workflow_routes(sample))


def test_expression_separate_argument_stays_static(monkeypatch):
    # C6 (must-preserve control): whitespace separates shell arguments, so
    # `${{ matrix.dir }}` and `unit.py` are TWO operands. `unit.py` stays a
    # statically checked argument: it is not dynamic, it resolves when shipped,
    # and it still fails closed when missing.
    workflow_path = ".github/workflows/synthetic-expression-separate-arg.yml"
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest ${{ matrix.dir }} unit.py\n"
    )
    present = (("100644", "blob", "1" * 40, "unit.py"),)
    dangling, dynamic = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text, extra_tracked=present
    )
    assert dynamic == []
    assert dangling == []
    dangling_missing, dynamic_missing = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text
    )
    assert (workflow_path, "unit.py", None) in dangling_missing
    assert dynamic_missing == []


def test_local_action_uses_missing_directory_fails_closed(monkeypatch):
    # A ``uses: ./...`` step names a repo-local action; if no real exported
    # file exists under that directory the step cannot run and must fail the
    # export closed.
    workflow_path = ".github/workflows/synthetic-local-action.yml"
    blob_sha = "0" * 40
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - uses: ./.github/actions/missing_action\n"
        "      - run: pytest tests/real_dir -q\n"
    )
    tracked = [
        ("100644", "blob", blob_sha, workflow_path),
        ("100644", "blob", "1" * 40, "tests/real_dir/test_present.py"),
    ]
    policy = {
        "rules": [
            {"disposition": exporter.COPY, "match": workflow_path},
            {"disposition": exporter.COPY, "match": "tests/real_dir/test_present.py"},
        ]
    }
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] == blob_sha:
            return workflow_text.encode("utf-8")
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    dangling, _dynamic = exporter.check_reference_integrity(
        policy, tracked, [p for _m, _o, _s, p in tracked], [], ROOT, report=True
    )
    assert any(
        referrer == workflow_path and "missing_action" in candidate
        for referrer, candidate, _resolved in dangling
    )
    with pytest.raises(exporter.ExportError):
        exporter.check_reference_integrity(
            policy, tracked, [p for _m, _o, _s, p in tracked], [], ROOT,
            report=False,
        )


def test_local_action_uses_present_resolves(monkeypatch):
    # The positive: a local action directory that ships real files (including
    # its action metadata) satisfies a ``uses: ./...`` step.
    workflow_path = ".github/workflows/synthetic-local-action-present.yml"
    blob_sha = "0" * 40
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - uses: ./.github/actions/real_action\n"
        "      - run: pytest tests/real_dir -q\n"
    )
    tracked = [
        ("100644", "blob", blob_sha, workflow_path),
        ("100644", "blob", "1" * 40, ".github/actions/real_action/action.yml"),
        ("100644", "blob", "2" * 40, "tests/real_dir/test_present.py"),
    ]
    policy = {
        "rules": [
            {"disposition": exporter.COPY, "match": workflow_path},
            {"disposition": exporter.COPY,
             "match": ".github/actions/real_action/action.yml"},
            {"disposition": exporter.COPY, "match": "tests/real_dir/test_present.py"},
        ]
    }
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] == blob_sha:
            return workflow_text.encode("utf-8")
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    dangling, _dynamic = exporter.check_reference_integrity(
        policy, tracked, [p for _m, _o, _s, p in tracked], [], ROOT, report=True
    )
    assert dangling == []


def test_local_action_uses_without_action_metadata_fails_closed(monkeypatch):
    # F2: a local action directory must ship its ``action.yml``/``action.yaml``
    # metadata to load. A folder that exists and holds unrelated files but no
    # action metadata cannot run as an action, so the export must fail closed
    # instead of accepting the weaker "some exported file is present" rule.
    workflow_path = ".github/workflows/synthetic-local-action-no-metadata.yml"
    blob_sha = "0" * 40
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - uses: ./.github/actions/not_an_action\n"
        "      - run: pytest tests/real_dir -q\n"
    )
    tracked = [
        ("100644", "blob", blob_sha, workflow_path),
        ("100644", "blob", "1" * 40, ".github/actions/not_an_action/run.sh"),
        ("100644", "blob", "2" * 40, ".github/actions/not_an_action/index.js"),
        ("100644", "blob", "3" * 40, "tests/real_dir/test_present.py"),
    ]
    policy = {
        "rules": [
            {"disposition": exporter.COPY, "match": workflow_path},
            {"disposition": exporter.COPY,
             "match": ".github/actions/not_an_action/run.sh"},
            {"disposition": exporter.COPY,
             "match": ".github/actions/not_an_action/index.js"},
            {"disposition": exporter.COPY, "match": "tests/real_dir/test_present.py"},
        ]
    }
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] == blob_sha:
            return workflow_text.encode("utf-8")
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    export_files = [p for _m, _o, _s, p in tracked]
    dangling, _dynamic = exporter.check_reference_integrity(
        policy, tracked, export_files, [], ROOT, report=True
    )
    assert any(
        referrer == workflow_path and "not_an_action" in candidate
        and resolved == ".github/actions/not_an_action"
        for referrer, candidate, resolved in dangling
    )
    with pytest.raises(exporter.ExportError):
        exporter.check_reference_integrity(
            policy, tracked, export_files, [], ROOT, report=False
        )


def _root_local_action_workflow(uses: str) -> str:
    return (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        f"      - uses: {uses}\n"
    )


def test_root_local_action_uses_with_action_metadata_resolves(monkeypatch):
    # P2 A positive: ``uses: ./`` (and the equivalent ``uses: .//``) names the
    # repository root as a root-local action. It must be a visible, checkable
    # dependency -- never the empty string silently discarded by the pre-repair
    # ``if not candidate`` guard -- and it resolves when the exported root
    # ships its ``action.yml``/``action.yaml`` metadata.
    for uses in ("./", ".//"):
        for metadata in ("action.yml", "action.yaml"):
            workflow_path = ".github/workflows/synthetic-root-action-ok.yml"
            present = (("100644", "blob", "1" * 40, metadata),)
            dangling, dynamic = _run_synthetic_integrity(
                monkeypatch, workflow_path,
                _root_local_action_workflow(uses), extra_tracked=present,
            )
            assert dangling == [], (uses, metadata)
            assert dynamic == [], (uses, metadata)


def test_root_local_action_uses_without_action_metadata_fails_closed(monkeypatch):
    # P2 A negative: the root local action must fail closed when the exported
    # root ships no action metadata, or only unrelated files. The pre-repair
    # exporter stripped ``uses: ./`` to the empty string and silently discarded
    # it, so a root action was never verified at all.
    for uses in ("./", ".//"):
        for unrelated in (
            (),
            (("100644", "blob", "1" * 40, "NOTES.txt"),),
            (("100644", "blob", "1" * 40, "scripts/helper.py"),),
        ):
            workflow_path = ".github/workflows/synthetic-root-action-missing.yml"
            dangling, _dynamic = _run_synthetic_integrity(
                monkeypatch, workflow_path,
                _root_local_action_workflow(uses), extra_tracked=unrelated,
            )
            assert any(
                referrer == workflow_path and "local action" in candidate
                for referrer, candidate, _resolved in dangling
            ), (uses, unrelated)
            with pytest.raises(exporter.ExportError):
                _run_synthetic_integrity(
                    monkeypatch, workflow_path,
                    _root_local_action_workflow(uses), extra_tracked=unrelated,
                    report=False,
                )


def test_root_local_action_uses_excluded_metadata_fails_closed(monkeypatch):
    # P2 A negative: root action metadata that is policy-EXCLUDE never ships
    # into the exported tree, so the exported root cannot load the action even
    # though the source tree has the file; the export must fail closed.
    workflow_path = ".github/workflows/synthetic-root-action-excluded.yml"
    blob_sha = "0" * 40
    tracked = [
        ("100644", "blob", blob_sha, workflow_path),
        ("100644", "blob", "1" * 40, "action.yml"),
    ]
    policy = {
        "rules": [
            {"disposition": exporter.COPY, "match": workflow_path},
            {"disposition": exporter.EXCLUDE, "match": "action.yml"},
        ]
    }
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] == blob_sha:
            return _root_local_action_workflow("./").encode("utf-8")
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    export_files = [workflow_path]
    dangling, _dynamic = exporter.check_reference_integrity(
        policy, tracked, export_files, [], ROOT, report=True
    )
    assert any(
        referrer == workflow_path and "local action" in candidate
        for referrer, candidate, _resolved in dangling
    )
    with pytest.raises(exporter.ExportError):
        exporter.check_reference_integrity(
            policy, tracked, export_files, [], ROOT, report=False
        )


def test_working_directory_pointing_nowhere_fails_closed(monkeypatch):
    # A statically declared step ``working-directory`` that exists nowhere in
    # the source tree makes the step unrunnable in any exported tree; it must
    # fail the export closed.
    workflow_path = ".github/workflows/synthetic-working-directory-nowhere.yml"
    blob_sha = "0" * 40
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - working-directory: tests/nowhere\n"
        "        run: pytest -q\n"
    )
    tracked = [("100644", "blob", blob_sha, workflow_path)]
    policy = {"rules": [{"disposition": exporter.COPY, "match": workflow_path}]}
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] == blob_sha:
            return workflow_text.encode("utf-8")
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    dangling, _dynamic = exporter.check_reference_integrity(
        policy, tracked, [workflow_path], [], ROOT, report=True
    )
    assert any(
        referrer == workflow_path and "working-directory" in candidate
        and resolved is None
        for referrer, candidate, resolved in dangling
    )
    with pytest.raises(exporter.ExportError):
        exporter.check_reference_integrity(
            policy, tracked, [workflow_path], [], ROOT, report=False
        )


def test_stale_generated_remap_route_fails_closed(monkeypatch):
    # A shipped workflow that still names a GENERATE_EMPTY rule's source path
    # (remapped away by the policy's output_path) resolves to an excluded
    # source path: the exported tree materializes the neutral output path and
    # never the RHC-specific source path, so the route must fail closed.
    workflow_path = ".github/workflows/synthetic-stale-remap.yml"
    blob_sha = "0" * 40
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: cat realities/registry/rhc-primary.json\n"
    )
    generate_source_sha = "2" * 40
    tracked = [
        ("100644", "blob", blob_sha, workflow_path),
        ("100644", "blob", generate_source_sha, "realities/registry/rhc-primary.json"),
    ]
    policy = {
        "rules": [
            {"disposition": exporter.COPY, "match": workflow_path},
            {"disposition": exporter.GENERATE_EMPTY,
             "match": "realities/registry/rhc-primary.json",
             "output_path": "realities/registry/campaign-root.json"},
        ],
        "generate": {
            "realities/registry/campaign-root.json": {
                "reality_id": "reality:campaign-root",
            },
        },
    }
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] == blob_sha:
            return workflow_text.encode("utf-8")
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    export_files = ["realities/registry/campaign-root.json", workflow_path]
    dangling, _dynamic = exporter.check_reference_integrity(
        policy, tracked, export_files, [], ROOT, report=True
    )
    assert any(
        referrer == workflow_path and candidate == "realities/registry/rhc-primary.json"
        and resolved == "realities/registry/rhc-primary.json"
        for referrer, candidate, resolved in dangling
    )
    with pytest.raises(exporter.ExportError):
        exporter.check_reference_integrity(
            policy, tracked, export_files, [], ROOT, report=False
        )


def test_quoted_run_key_spellings_are_extracted():
    # GitHub Actions accepts the same ``run:`` step key written bare,
    # single-quoted, or double-quoted, optionally with whitespace before the
    # colon. Every equivalent spelling must yield its route, or a step written
    # in one of them would smuggle an excluded path past the fail-closed check.
    sample = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - \"run\": pytest tests/double_quoted.py\n"
        "      - 'run': pytest tests/single_quoted.py\n"
        "      - name: spaced\n"
        "        run : pytest tests/space_before_colon.py\n"
    )
    routes = {
        route for route, _dynamic in exporter._workflow_routes(sample)
    }
    assert "tests/double_quoted.py" in routes
    assert "tests/single_quoted.py" in routes
    assert "tests/space_before_colon.py" in routes


def test_quoted_run_key_route_dangle_fails_closed(monkeypatch):
    # A retained workflow whose step uses the quoted-key spelling and invokes an
    # excluded path must be reported as dangling and must fail the export
    # closed -- the exact round-2 finding this repair closes.
    workflow_path = ".github/workflows/synthetic-quoted-run.yml"
    excluded_path = "tests/excluded_by_quoted_run.py"
    blob_sha = "0" * 40
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - \"run\": pytest tests/excluded_by_quoted_run.py\n"
    )
    tracked = [
        ("100644", "blob", blob_sha, workflow_path),
        ("100644", "blob", "1" * 40, excluded_path),
    ]
    policy = {
        "rules": [
            {"disposition": exporter.COPY, "match": workflow_path},
            {"disposition": exporter.EXCLUDE, "match": excluded_path},
        ]
    }
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] == blob_sha:
            return workflow_text.encode("utf-8")
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    export_files = [workflow_path]
    dangling, _dynamic = exporter.check_reference_integrity(
        policy, tracked, export_files, [], ROOT, report=True
    )
    assert any(
        referrer == workflow_path and resolved == excluded_path
        for referrer, _candidate, resolved in dangling
    )
    with pytest.raises(exporter.ExportError):
        exporter.check_reference_integrity(
            policy, tracked, export_files, [], ROOT, report=False
        )


def test_escaped_run_key_route_dangle_fails_closed(monkeypatch):
    # The round-3 finding: a YAML double-quoted key using an escape sequence
    # ("\u0072un":) decodes to the key ``run`` and GitHub executes the step, but
    # no literal-text regex can enumerate every escaped spelling. The structural
    # PyYAML parse decodes the key, so the route is extracted and the dangling
    # route into an excluded path fails the export closed.
    workflow_path = ".github/workflows/synthetic-escaped-run.yml"
    excluded_path = "tests/excluded_by_escaped_run.py"
    blob_sha = "0" * 40
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        '      - "\\u0072un": pytest tests/excluded_by_escaped_run.py\n'
    )
    tracked = [
        ("100644", "blob", blob_sha, workflow_path),
        ("100644", "blob", "1" * 40, excluded_path),
    ]
    policy = {
        "rules": [
            {"disposition": exporter.COPY, "match": workflow_path},
            {"disposition": exporter.EXCLUDE, "match": excluded_path},
        ]
    }
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] == blob_sha:
            return workflow_text.encode("utf-8")
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    # The escaped key decodes to ``run`` and its route is extracted...
    assert "tests/excluded_by_escaped_run.py" in {
        route for route, _dynamic in exporter._workflow_routes(workflow_text)
    }
    # ...so the dangling route into the excluded path is caught, failing closed.
    export_files = [workflow_path]
    dangling, _dynamic = exporter.check_reference_integrity(
        policy, tracked, export_files, [], ROOT, report=True
    )
    assert any(
        referrer == workflow_path and resolved == excluded_path
        for referrer, _candidate, resolved in dangling
    )
    with pytest.raises(exporter.ExportError):
        exporter.check_reference_integrity(
            policy, tracked, export_files, [], ROOT, report=False
        )


def test_workflow_routes_resolve_against_effective_working_directory():
    # The round-4 finding: GitHub Actions runs a step's command relative to its
    # effective working directory -- a step-level ``working-directory`` if set,
    # else the job's ``defaults.run.working-directory``, else the workflow-level
    # ``defaults.run.working-directory``, else the repository root. A run:
    # argument must be resolved against that directory, not always the repo root.
    sample = (
        "defaults:\n"
        "  run:\n"
        "    working-directory: scripts\n"
        "jobs:\n"
        "  workflow-default:\n"
        "    steps:\n"
        "      - run: pytest workflow_default_only.py\n"
        "  job-default:\n"
        "    defaults:\n"
        "      run:\n"
        "        working-directory: tests/jobs\n"
        "    steps:\n"
        "      - run: pytest job_default_only.py\n"
        "  step-override:\n"
        "    steps:\n"
        "      - working-directory: tests/steps\n"
        "        run: pytest step_override_only.py\n"
        "  dynamic:\n"
        "    steps:\n"
        "      - working-directory: ${{ env.CANVAS }}\n"
        "        run: pytest dynamic_only.py\n"
    )
    routes = {
        route for route, _dynamic in exporter._workflow_routes(sample)
    }
    classified = dict(exporter._workflow_routes(sample))
    # Workflow-level default applies to a job that does not override it.
    assert "scripts/workflow_default_only.py" in routes
    # A job-level default overrides the workflow-level default.
    assert "tests/jobs/job_default_only.py" in routes
    # A step-level working-directory overrides every default.
    assert "tests/steps/step_override_only.py" in routes
    # A dynamic working-directory cannot be resolved structurally, so its
    # operand is not re-rooted at the repository root: it is yielded unresolved
    # (is_dynamic) and recorded as consciously unproven, never proved as though
    # the file lived at the repo root.
    assert classified["dynamic_only.py"] is True
    assert not any(route.startswith("${{") for route in routes)


def test_working_directory_relative_route_dangle_fails_closed(monkeypatch):
    # The round-4 finding, end to end: a retained workflow whose step runs
    # relative to a working directory and invokes an excluded path must be
    # caught -- resolved against that directory, not the repo root (where the
    # file does not exist), and must fail the export closed.
    workflow_path = ".github/workflows/synthetic-working-directory.yml"
    excluded_path = "tests/excluded_by_working_directory.py"
    blob_sha = "0" * 40
    workflow_text = (
        "defaults:\n"
        "  run:\n"
        "    working-directory: tests\n"
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - run: pytest excluded_by_working_directory.py\n"
    )
    tracked = [
        ("100644", "blob", blob_sha, workflow_path),
        ("100644", "blob", "1" * 40, excluded_path),
    ]
    policy = {
        "rules": [
            {"disposition": exporter.COPY, "match": workflow_path},
            {"disposition": exporter.EXCLUDE, "match": excluded_path},
        ]
    }
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] == blob_sha:
            return workflow_text.encode("utf-8")
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    # The working-directory-relative route is resolved to the excluded source
    # path, not left as a nonexistent repo-root path.
    assert excluded_path in {
        route for route, _dynamic in exporter._workflow_routes(workflow_text)
    }
    export_files = [workflow_path]
    dangling, _dynamic = exporter.check_reference_integrity(
        policy, tracked, export_files, [], ROOT, report=True
    )
    assert any(
        referrer == workflow_path and resolved == excluded_path
        for referrer, _candidate, resolved in dangling
    )
    with pytest.raises(exporter.ExportError):
        exporter.check_reference_integrity(
            policy, tracked, export_files, [], ROOT, report=False
        )


def test_static_working_directory_with_exported_descendant_resolves(monkeypatch):
    # Fourth exact-head Codex P2: a static step ``working-directory`` was
    # validated by exact membership in the exported file/dir sets, so a real
    # exported directory -- whose path is itself never an exported file -- was
    # falsely rejected, even though the same species-aware descendant-file rule
    # already satisfies a ``run:`` route. A static working directory holding a
    # real exported descendant file must resolve, at every effective level.
    workflow_path = ".github/workflows/synthetic-working-directory-present.yml"
    blob_sha = "0" * 40
    workflow_text = (
        "defaults:\n"
        "  run:\n"
        "    working-directory: tests/wf_default\n"
        "jobs:\n"
        "  wf:\n"
        "    steps:\n"
        "      - run: pytest wf_only.py -q\n"
        "  override:\n"
        "    defaults:\n"
        "      run:\n"
        "        working-directory: tests/job_default\n"
        "    steps:\n"
        "      - run: pytest inherited.py -q\n"
        "      - working-directory: tests/step_override\n"
        "        run: pytest overridden.py -q\n"
    )
    tracked = [
        ("100644", "blob", blob_sha, workflow_path),
        ("100644", "blob", "1" * 40, "tests/wf_default/wf_only.py"),
        ("100644", "blob", "2" * 40, "tests/job_default/inherited.py"),
        ("100644", "blob", "3" * 40, "tests/step_override/overridden.py"),
    ]
    policy = {
        "rules": [
            {"disposition": exporter.COPY, "match": workflow_path},
            {"disposition": exporter.COPY, "match": "tests/wf_default/wf_only.py"},
            {"disposition": exporter.COPY, "match": "tests/job_default/inherited.py"},
            {"disposition": exporter.COPY,
             "match": "tests/step_override/overridden.py"},
        ]
    }
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] == blob_sha:
            return workflow_text.encode("utf-8")
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    # Each step's route resolves against its effective working directory:
    # step override, then job default, then workflow default.
    routes = {route for route, _dynamic in exporter._workflow_routes(workflow_text)}
    assert "tests/step_override/overridden.py" in routes
    assert "tests/job_default/inherited.py" in routes
    assert "tests/wf_default/wf_only.py" in routes
    # The working directories themselves are not exported files, only the
    # directories holding real exported descendants: the check must pass.
    export_files = [p for _m, _o, _s, p in tracked]
    assert "tests/step_override" not in export_files
    dangling, dynamic = exporter.check_reference_integrity(
        policy, tracked, export_files, [], ROOT, report=True
    )
    assert dangling == []
    assert dynamic == []


def test_static_working_directory_without_exported_descendant_fails_closed(
    monkeypatch,
):
    # The complement of the positive above: a static working directory whose
    # every source file is EXCLUDE ships as an empty preserved skeleton with
    # zero exported executable files. Enlarging the exact-membership check into
    # a descendant-file check must not be relaxed into accepting an empty
    # folder, so this must still fail closed.
    workflow_path = ".github/workflows/synthetic-working-directory-skeleton.yml"
    excluded_path = "tests/skeleton/test_excluded.py"
    blob_sha = "0" * 40
    workflow_text = (
        "jobs:\n"
        "  x:\n"
        "    steps:\n"
        "      - working-directory: tests/skeleton\n"
        "        run: pytest -q\n"
    )
    tracked = [
        ("100644", "blob", blob_sha, workflow_path),
        ("100644", "blob", "1" * 40, excluded_path),
    ]
    policy = {
        "rules": [
            {"disposition": exporter.COPY, "match": workflow_path},
            {"disposition": exporter.EXCLUDE, "match": excluded_path},
        ]
    }
    real_git_bytes = exporter._git_bytes

    def fake_git_bytes(args, cwd):
        if args[:2] == ["cat-file", "blob"] and args[2] == blob_sha:
            return workflow_text.encode("utf-8")
        return real_git_bytes(args, cwd)

    monkeypatch.setattr(exporter, "_git_bytes", fake_git_bytes)
    # The excluded file is absent from the exported tree, so the directory is a
    # skeleton only.
    export_files = [workflow_path]
    dangling, _dynamic = exporter.check_reference_integrity(
        policy, tracked, export_files, [], ROOT, report=True
    )
    assert any(
        referrer == workflow_path and "working-directory" in candidate
        and resolved == "tests/skeleton"
        for referrer, candidate, resolved in dangling
    )
    with pytest.raises(exporter.ExportError):
        exporter.check_reference_integrity(
            policy, tracked, export_files, [], ROOT, report=False
        )


def test_static_working_directory_pointing_at_a_file_fails_closed(monkeypatch):
    # P2 B: a static ``working-directory`` names a DIRECTORY the runner changes
    # into. The pre-repair exporter validated it with ``_route_satisfied``,
    # which accepts an exported *file* at the exact path -- a false pass, since
    # changing directory into a file is impossible. Cover workflow-, job- and
    # step-level static directories, each with no route operand, so only the
    # path-kind (directory-ness) check can fail the export closed.
    workflow_path = ".github/workflows/synthetic-working-directory-file.yml"
    workflow_text = (
        "defaults:\n"
        "  run:\n"
        "    working-directory: tests/wf_file.py\n"
        "jobs:\n"
        "  wf:\n"
        "    steps:\n"
        "      - run: pytest -q\n"
        "  job:\n"
        "    defaults:\n"
        "      run:\n"
        "        working-directory: tests/job_file.py\n"
        "    steps:\n"
        "      - run: pytest -q\n"
        "  step:\n"
        "    steps:\n"
        "      - working-directory: tests/step_file.py\n"
        "        run: pytest -q\n"
    )
    present = (
        ("100644", "blob", "1" * 40, "tests/wf_file.py"),
        ("100644", "blob", "2" * 40, "tests/job_file.py"),
        ("100644", "blob", "3" * 40, "tests/step_file.py"),
    )
    dangling, dynamic = _run_synthetic_integrity(
        monkeypatch, workflow_path, workflow_text, extra_tracked=present
    )
    for name in ("tests/wf_file.py", "tests/job_file.py", "tests/step_file.py"):
        assert (workflow_path, f"working-directory {name!r}", name) in dangling, name
    assert dynamic == []
    with pytest.raises(exporter.ExportError):
        _run_synthetic_integrity(
            monkeypatch, workflow_path, workflow_text,
            extra_tracked=present, report=False,
        )


# --------------------------------------------------------------------------
# Determinism / source immutability / safety
# --------------------------------------------------------------------------

def test_repeated_export_is_deterministic(tmp_path):
    out1, rec1, obj1 = _sample_export(tmp_path, "one")
    out2, rec2, obj2 = _sample_export(tmp_path, "two")
    assert obj1 == obj2
    assert rec1.read_bytes() == rec2.read_bytes()
    assert _tree_snapshot(out1) == _tree_snapshot(out2)


def test_source_tree_is_unchanged(tmp_path):
    before_status = _git("status", "--porcelain").stdout
    before_head = _git("rev-parse", "HEAD").stdout.strip()
    _sample_export(tmp_path)
    assert _git("status", "--porcelain").stdout == before_status
    assert _git("rev-parse", "HEAD").stdout.strip() == before_head


def test_destructive_overwrite_and_source_output_overlap_are_refused(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "keep.txt").write_bytes(b"keep")
    with pytest.raises(exporter.ExportError):
        exporter.export(ROOT, "HEAD", existing, tmp_path / "existing.receipt.json")

    with pytest.raises(exporter.ExportError):
        exporter.export(ROOT, "HEAD", ROOT / "__rhc_z_overlap__", tmp_path / "r.json")

    with pytest.raises(exporter.ExportError):
        exporter.export(ROOT, "HEAD", ROOT, tmp_path / "r.json")

    assert not (ROOT / "__rhc_z_overlap__").exists()


def test_repo_root_must_be_the_true_git_toplevel(tmp_path):
    with pytest.raises(exporter.ExportError):
        exporter.guard_paths(
            ROOT / "scripts", tmp_path / "canvas", tmp_path / "canvas.receipt.json"
        )
    exporter.guard_paths(
        ROOT, tmp_path / "canvas", tmp_path / "canvas.receipt.json"
    )


def test_ref_must_resolve_to_a_commit_object():
    tree = _git("rev-parse", "HEAD^{tree}").stdout.strip()
    with pytest.raises(exporter.ExportError):
        exporter.rev_parse(tree, ROOT)
    assert exporter.rev_parse("HEAD", ROOT) == _git("rev-parse", "HEAD").stdout.strip()


def test_report_references_prints_diagnostic(tmp_path, monkeypatch, capsys):
    sentinel = [(".github/workflows/x.yml", "excluded/file.py", "excluded/file.py")]
    monkeypatch.setattr(
        exporter, "check_reference_integrity",
        lambda *args, **kwargs: (list(sentinel), []),
    )
    exporter.export(
        ROOT, "HEAD", tmp_path / "canvas", tmp_path / "canvas.receipt.json",
        report_references=True,
    )
    captured = capsys.readouterr()
    assert "DANGLING ROUTE:" in captured.out
    assert "excluded/file.py" in captured.out


def test_export_initializes_as_independent_repository(tmp_path):
    output, _receipt, _ = _sample_export(tmp_path)
    assert not (output / ".git").exists()
    assert _git_run(output, "init", "-q").returncode == 0
    assert _git_run(output, "add", "-A").returncode == 0
    commit = _git_run(
        output,
        "-c", "user.email=z@example.invalid",
        "-c", "user.name=POST-EV2-Z",
        "commit", "-q", "-m", "clean canvas",
    )
    assert commit.returncode == 0, commit.stderr


# --------------------------------------------------------------------------
# Representative proofs / genericization / CI boundary
# --------------------------------------------------------------------------

def test_representative_proof_surfaces_are_present(tmp_path):
    output, _receipt, _ = _sample_export(tmp_path)
    for relative in REPRESENTATIVE_SURFACES:
        assert (output / relative).is_file(), relative


def test_exported_test_suite_is_free_of_rhc_fixture_names(tmp_path):
    output, _receipt, _ = _sample_export(tmp_path)
    tests_dir = output / "tests"
    assert tests_dir.is_dir()
    offenders = []
    for path in tests_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lowered = text.lower()
        for token in RHC_NAME_TOKENS:
            if token in lowered:
                offenders.append((path.relative_to(output).as_posix(), token))
    assert offenders == []


def test_z_workflow_is_mission_local_and_pins_exact_head():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    events = _workflow_event_paths(text)
    # Each event's path filter is asserted independently: a regression that
    # drops a trigger from only pull_request or only push must fail the proof,
    # so one event cannot hide a missing trigger in the other.
    assert "pull_request" in events
    assert "push" in events
    assert events["pull_request"] == Z_WORKFLOW_TRIGGER_PATHS
    assert events["push"] == Z_WORKFLOW_TRIGGER_PATHS
    for event in ("pull_request", "push"):
        # The engine-version source must trigger this event, so a version-only
        # change still schedules the proof that validates the version source and
        # receipt; the authorized requirements.txt PyYAML line must too.
        assert "ENGINE_VERSION" in events[event]
        assert "requirements.txt" in events[event]
        # Every surface this Mission is allowed to change is a workflow trigger,
        # so this Mission's own changes exercise the proof.
        assert SURFACE_BUDGET_FILES <= events[event]
    # The Mission-local workflow never delegates to the global RT01 workflow
    # (no reusable-workflow invocation and no workflow-run dispatch): any
    # rt01-runtime reference is the EXPORTED copy read for execution inside the
    # exported canvas, whose inside-canvas binding is proven separately.
    assert "gh workflow run" not in text
    assert "workflow_call" not in text
    # Exact-head checkout for pull_request runs (do not grade the synthetic
    # merge commit).
    assert "github.event.pull_request.head.sha" in text


def test_z_workflow_avoids_runner_context_in_job_level_env():
    # Startup-failure regression proof: ``runner`` is not available at
    # ``jobs.<job_id>.env``, so a runner-derived canvas path declared there makes
    # the workflow fail planning before any job runs (zero check-runs). The
    # clean-canvas path must be derived from a step-level/runtime context.
    document = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert _runner_derived_job_env(document) == []


def test_z_workflow_defines_canvas_path_at_step_level():
    # The repair must keep deriving the temporary canvas path (it is not simply
    # dropped); it must live where GitHub Actions makes ``runner`` available --
    # a step-level ``env`` or ``working-directory``, never job-level ``env``.
    document = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = document["jobs"]["clean-canvas"]["steps"]
    assert any(
        isinstance(step, dict)
        and (
            "runner." in str(step.get("working-directory", ""))
            or any(
                "runner." in str(value)
                for value in (step.get("env") or {}).values()
            )
        )
        for step in steps
    )


def test_z_workflow_runs_the_copied_post_ev2_14_suite_inside_the_canvas():
    # The COPY-shipped POST-EV2-14 suite must actually execute from inside the
    # exported canvas, not merely exist there: a shipped test surface that
    # carries a stale remapped reference must fail in RHC CI (this proof) and
    # not first be discovered downstream by PORT-01.
    document = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = document["jobs"]["clean-canvas"]["steps"]
    commands = [
        str(step.get("run", "")) for step in steps if isinstance(step, dict)
    ]
    assert any(
        "tests/post_ev2_14/test_brainstorm_lab.py" in command for command in commands
    )


# The ownership boundary this Mission establishes: reusable Git-anchor behavior
# proofs stay exported and self-contained (they build their own synthetic Git
# history), while genuine RHC source-history/provenance proofs stay in source
# RHC and are reclassified EXCLUDE so they never ship into an independent
# repository that has no RHC ancestor objects.
PORTABLE_ANCHORED_TESTS = (
    "tests/test_offscreen_anchor_context.py",
    "tests/test_offscreen_run_resolution.py",
    "tests/test_run_validation.py",
    "tests/test_run_anchor_git_validation.py",
)
RHC_SOURCE_PROVENANCE_TESTS = (
    "tests/post_ev2_1/test_clean_bootstrap_equivalence.py",
)


def test_export_policy_ships_portable_anchored_tests_and_excludes_rhc_provenance():
    # The reusable Git-anchor proofs are shipped COPY (so an independent
    # repository still exercises anchor semantics), and the RHC source-history
    # frontier proof is EXCLUDE (it reads a pinned RHC commit that a clean
    # repository cannot contain).
    rules = {rule["match"]: rule["disposition"] for rule in _policy()["rules"]}
    for relative in PORTABLE_ANCHORED_TESTS:
        assert rules.get(relative) == "COPY", relative
    for relative in RHC_SOURCE_PROVENANCE_TESTS:
        assert rules.get(relative) == "EXCLUDE", relative


def _portable_suite_step(document):
    """Return the single ``portable-suite`` step that runs the full test suite."""
    steps = document["jobs"]["portable-suite"]["steps"]
    matches = [
        step
        for step in steps
        if isinstance(step, dict)
        and str(step.get("run", "")).strip() == "pytest tests -q"
    ]
    assert len(matches) == 1
    return matches[0]


def _exported_canvas(document):
    """Return the canvas path the ``portable-suite`` job exports into."""
    steps = document["jobs"]["portable-suite"]["steps"]
    export = next(
        step
        for step in steps
        if isinstance(step, dict)
        and "export_clean_campaign.py" in str(step.get("run", ""))
    )
    return (export.get("env") or {}).get("CANVAS")


def test_z_workflow_runs_the_full_portable_suite_in_a_fresh_repository():
    # PROOF MATRIX 6/10: the Mission-local CI must prove the intended portable
    # exported suite itself, not only a representative source subset. The
    # ``portable-suite`` job exports exact HEAD, initializes a brand-new
    # independent Git repository on ``main`` with no RHC ancestry or remotes,
    # and runs the full exported test suite there.
    document = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = document["jobs"]["portable-suite"]["steps"]
    commands = [
        str(step.get("run", "")) for step in steps if isinstance(step, dict)
    ]
    assert any("export_clean_campaign.py" in command for command in commands)
    assert any("init -q -b main" in command for command in commands)
    canvas = _exported_canvas(document)
    assert canvas and "runner.temp" in str(canvas)
    # The full suite must run FROM INSIDE the exported canvas the job just
    # created -- not merely exist as a command somewhere in the job -- so it
    # cannot accidentally grade the source checkout or another directory.
    suite_step = _portable_suite_step(document)
    assert str(suite_step.get("working-directory")) == str(canvas)


def test_portable_suite_canvas_binding_catches_a_step_outside_the_canvas():
    # Non-vacuity: the inside-canvas binding check above must fail when the
    # full-suite step runs outside the exported canvas (here: the source root,
    # with no ``working-directory``), rather than passing blindly.
    document = yaml.safe_load(
        "jobs:\n"
        "  portable-suite:\n"
        "    steps:\n"
        "      - env:\n"
        "          CANVAS: ${{ runner.temp }}/portable-campaign-canvas\n"
        "        run: |\n"
        "          python scripts/export_clean_campaign.py "
        "--repo-root . --ref HEAD --output \"$CANVAS\"\n"
        "      - run: pytest tests -q\n"
    )
    canvas = _exported_canvas(document)
    assert canvas
    assert str(_portable_suite_step(document).get("working-directory")) != str(canvas)


def test_workflow_contract_detects_runner_context_in_job_level_env():
    # Focused negative proof: the checker above actually catches the exact
    # startup-failure class the repaired workflow avoids, so the regression
    # proof cannot pass vacuously.
    invalid = yaml.safe_load(
        "jobs:\n"
        "  clean-canvas:\n"
        "    runs-on: ubuntu-latest\n"
        "    env:\n"
        "      CANVAS: ${{ runner.temp }}/clean-campaign-canvas\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    assert _runner_derived_job_env(invalid) == [("clean-canvas", "CANVAS")]


def test_existing_global_workflows_are_unmodified():
    # Historical POST-EV2-Z / Z.1 mission-bound provenance assertion: it proved
    # every global workflow present at the original Z base was byte-unchanged by
    # that Mission. Later authorized Missions may legitimately change workflows,
    # so this must not become permanent repository law.
    if not _on_original_z_mission_branch():
        pytest.skip("historical POST-EV2-Z / Z.1 mission-bound assertion")
    existing = _git(
        "ls-tree", "--name-only", BASE_SHA, ".github/workflows/"
    ).stdout.split()
    assert existing
    # The Mission-local POST-EV2-Z workflow is a Surface Budget file this
    # Mission may repair (ENGINE_VERSION trigger coverage); it is proven by the
    # surface-budget, trigger-set and exact-head tests instead. Every OTHER
    # workflow must be untouched.
    global_workflows = [path for path in existing if path not in Z_FILES]
    assert global_workflows
    for path in global_workflows:
        proc = _git("diff", "--quiet", BASE_SHA, "--", path, check=False)
        assert proc.returncode == 0, path


def test_git_diff_check_is_clean():
    assert _git("diff", "--check", check=False).returncode == 0
    assert _git("diff", "--cached", "--check", check=False).returncode == 0


# --------------------------------------------------------------------------
# POST-EV2-Z6: exported product acceptance
# --------------------------------------------------------------------------

def _runtime_workflow_documents():
    source = yaml.safe_load(
        (ROOT / RUNTIME_WORKFLOW_PATH).read_text(encoding="utf-8")
    )
    policy = _policy()
    rule = next(
        rule for rule in policy["rules"] if rule["match"] == RUNTIME_WORKFLOW_PATH
    )
    assert rule["disposition"] == exporter.GENERATE_EMPTY, rule
    generated_text = policy["generate"][RUNTIME_WORKFLOW_PATH]
    return source, yaml.safe_load(generated_text), generated_text


def _runtime_workflow_top_level_divergences(source, generated):
    """Return sorted top-level keys whose parsed values differ between two workflows.

    The portable RT01 workflow is the source workflow minus exactly the four
    audited source-only pytest arguments, so the whole top-level contract --
    ``name`` and the applicable ``on`` / ``env`` / ``defaults`` / ``permissions``
    keys -- must stay semantically identical too. The comparison is structural,
    over parsed YAML values, not byte-equality: a comment or whitespace
    difference is not a semantic divergence, while an unintended trigger, DSN,
    default or permission change is. ``jobs`` is excluded because it is guarded
    step-by-step in the test below. The YAML 1.1 loader decodes the ``on`` key to
    the boolean ``True``, so the returned keys are sorted by their string form to
    keep the mixed-type key set orderable.
    """
    keys = (set(source) | set(generated)) - {"jobs"}
    return sorted(
        (key for key in keys if source.get(key) != generated.get(key)),
        key=str,
    )


def test_export_policy_generates_the_portable_runtime_workflow():
    # The one explicit, proven portability adaptation of this Mission: the
    # exported RT01 runtime workflow is generated from a fixed policy constant
    # equal to the source workflow minus exactly the four audited source-only
    # pytest arguments. Every other semantic byte must be identical, so the
    # source workflow and the shipped adaptation cannot drift apart silently;
    # the exporter's route-integrity check independently proves the generated
    # bytes reference only shipped executable surfaces.
    source, generated, _generated_text = _runtime_workflow_documents()
    assert list(source["jobs"]) == list(generated["jobs"])
    # The whole top-level workflow contract must match too: the declared
    # portability adaptation removes only the four source-only pytest
    # arguments, so ``name`` and the applicable ``on`` / ``env`` / ``defaults`` /
    # ``permissions`` keys cannot silently drift.
    assert _runtime_workflow_top_level_divergences(source, generated) == []
    for job_id, source_job in source["jobs"].items():
        generated_job = generated["jobs"][job_id]
        assert {
            key: value for key, value in source_job.items() if key != "steps"
        } == {key: value for key, value in generated_job.items() if key != "steps"}, (
            job_id,
        )
        assert len(source_job["steps"]) == len(generated_job["steps"]), job_id
        for index, (source_step, generated_step) in enumerate(
            zip(source_job["steps"], generated_job["steps"])
        ):
            source_run = source_step.get("run")
            if isinstance(source_run, str):
                assert isinstance(generated_step.get("run"), str), (job_id, index)
                assert (
                    generated_step["run"].split()
                    == [
                        token for token in source_run.split()
                        if token not in SOURCE_ONLY_RUNTIME_TEST_TREES
                    ]
                ), (job_id, index)
                source_step = {
                    key: value for key, value in source_step.items()
                    if key != "run"
                }
                generated_step = {
                    key: value for key, value in generated_step.items()
                    if key != "run"
                }
            assert source_step == generated_step, (job_id, index)
    # The adaptation removes each audited source-only argument exactly once
    # from the source shard commands, so the guard cannot pass vacuously.
    removed = []
    for job in source["jobs"].values():
        for step in job["steps"]:
            run = step.get("run")
            if isinstance(run, str):
                removed += [
                    token for token in run.split()
                    if token in SOURCE_ONLY_RUNTIME_TEST_TREES
                ]
    assert sorted(removed) == sorted(SOURCE_ONLY_RUNTIME_TEST_TREES)


def test_runtime_workflow_contract_detects_a_top_level_divergence():
    # Non-vacuity: the contract guard compares the whole top-level workflow, not
    # just the job bodies. An unintended divergence in any top-level key --
    # ``name``, the ``on`` triggers, ``env`` DSNs, ``defaults`` or added
    # ``permissions`` -- must be caught, so a drifted generated constant cannot
    # ship a portable workflow with a dropped trigger or DSN while its jobs still
    # match the source.
    source, generated, _generated_text = _runtime_workflow_documents()
    assert _runtime_workflow_top_level_divergences(source, generated) == []

    def diverged(mutate):
        candidate = copy.deepcopy(generated)
        mutate(candidate)
        return _runtime_workflow_top_level_divergences(source, candidate)

    assert diverged(
        lambda workflow: workflow.__setitem__(
            "name", "RT01 runtime foundation (portable)"
        )
    ) == ["name"]

    def _drop_dsn(workflow):
        workflow["env"].pop("RHC_RT01A_PG_DSN")

    assert diverged(_drop_dsn) == ["env"]

    def _drop_push(workflow):
        # The YAML 1.1 loader decodes ``on`` to the boolean ``True``.
        del workflow[True]["push"]

    assert diverged(_drop_push) == [True]

    assert diverged(
        lambda workflow: workflow.__setitem__(
            "permissions", {"contents": "read"}
        )
    ) == ["permissions"]

    assert diverged(
        lambda workflow: workflow.__setitem__(
            "defaults", {"run": {"working-directory": "."}}
        )
    ) == ["defaults"]

    def _drop_name(workflow):
        del workflow["name"]

    assert diverged(_drop_name) == ["name"]


def test_source_only_runtime_test_trees_stay_excluded():
    # Ownership audit, encoded: every test file under the four audited
    # source-only trees is policy-EXCLUDE. Each tree's test code carries RHC
    # campaign-identity strings (item:vampire / character:gork /
    # character:mugen), so the suites are live source-RHC runtime proof --
    # shipping them would violate the durable no-RHC-fixture-names invariant
    # and copying them would be copying source-only tests merely to silence
    # empty-directory pytest arguments. Their proof stays live in source CI,
    # where the source workflow keeps invoking them.
    policy = _policy()
    members = [
        path
        for _mode, _obj_type, _sha, path in exporter.tracked_entries("HEAD", ROOT)
        if any(path.startswith(tree + "/") for tree in SOURCE_ONLY_RUNTIME_TEST_TREES)
    ]
    assert len(members) == 5, sorted(members)
    for path in members:
        assert exporter.disposition_for_path(policy, path) == exporter.EXCLUDE, path


def test_receipt_records_unresolved_dynamic_routes(tmp_path):
    # Dynamically computed workflow route fragments are consciously unproven:
    # the receipt classifies them explicitly instead of silently accepting them
    # as satisfied or claiming they were proved. The shipped surfaces carry
    # exactly one such fragment today.
    _output, _receipt, receipt_object = _sample_export(tmp_path)
    assert receipt_object["unresolved_dynamic_routes"] == [
        {"path": ".github/workflows/hard-write-boundary.yml", "route": "refs/pull/"},
    ]


# Proof D: exported Python entrypoints and their local imports must resolve
# against the exported tree. A repo-local module is resolved by the export's
# own import conventions (importer's own directory, scripts/, and the tests/
# suite directories on sys.path); everything else must be the standard library
# or a module the shipped requirements.txt declares. Relative imports are
# resolved by Python's package machinery at collection time and are outside
# this static guard's honest reach (documented residual limit).
IMPORT_DECLARED_EXTERNAL_MODULES = frozenset(
    {"jsonschema", "pytest", "yaml", "psycopg2"}
)


def _resolves_in_export(name: str, importer: str, exported: frozenset | set):
    importer_dir = importer.rsplit("/", 1)[0] if "/" in importer else ""
    parts = name.split(".")
    for depth in range(len(parts), 0, -1):
        prefix = "/".join(parts[:depth])
        mod_file = prefix.replace(".", "/") + ".py"
        pkg_file = prefix.replace(".", "/") + "/__init__.py"
        for base in ("", importer_dir, "scripts"):
            joined = (base + "/" if base else "") + mod_file
            if joined in exported:
                return joined
            joined = (base + "/" if base else "") + pkg_file
            if joined in exported:
                return joined
        leaf = parts[0] + ".py"
        for candidate in sorted(exported):
            if candidate.startswith(("scripts/", "tests/")) and candidate.endswith(
                "/" + leaf
            ):
                return candidate
    return None


def _export_local_import_offenders(output: Path):
    offenders = []
    exported = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    }
    for relative in sorted(p for p in exported if p.endswith(".py")):
        text = (output / relative).read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            offenders.append((relative, "syntax", str(exc)))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [(alias.name, 0) for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [(node.module, node.level)]
            else:
                continue
            for name, level in names:
                if level:
                    continue
                if _resolves_in_export(name, relative, exported):
                    continue
                top = name.split(".")[0]
                if top in sys.stdlib_module_names:
                    continue
                if top in IMPORT_DECLARED_EXTERNAL_MODULES:
                    continue
                offenders.append((relative, "import", name))
    return offenders


def test_export_import_closure_resolves(tmp_path):
    output, _receipt, _ = _sample_export(tmp_path)
    assert _export_local_import_offenders(output) == []


def test_export_import_closure_guard_catches_a_broken_local_import(
    tmp_path, monkeypatch
):
    # Non-vacuity: excluding a locally-imported helper module from the export
    # must make the import-closure guard flag its importers, so the guard
    # cannot pass vacuously.
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["rules"] = [
        rule for rule in policy["rules"]
        if not (rule["disposition"] == "COPY"
                and rule["match"] == "tests/ev2131/ev2131_util.py")
    ] + [{"disposition": "EXCLUDE", "match": "tests/ev2131/ev2131_util.py"}]
    monkeypatch.setattr(
        exporter, "load_policy",
        lambda ref, repo_root: exporter.parse_policy(json.dumps(policy)),
    )
    output = tmp_path / "canvas"
    exporter.export(ROOT, "HEAD", output, tmp_path / "canvas.receipt.json")
    offenders = _export_local_import_offenders(output)
    assert any(
        path.startswith("tests/ev2131/") and name == "ev2131_util"
        for path, kind, name in offenders
        if kind == "import"
    )


def _clean_canvas_export_step(document):
    steps = document["jobs"]["clean-canvas"]["steps"]
    return next(
        step for step in steps
        if isinstance(step, dict)
        and "export_clean_campaign.py" in str(step.get("run", ""))
    )


def _clean_canvas_shard_execution_step(document):
    steps = document["jobs"]["clean-canvas"]["steps"]
    matches = [
        step for step in steps
        if isinstance(step, dict)
        and RUNTIME_WORKFLOW_PATH in str(step.get("run", ""))
        and "pytest" in str(step.get("run", ""))
    ]
    assert len(matches) == 1
    return matches[0]


def _shard_step_canvas_binding(document):
    """Return (shard_step, canvas, inside_canvas?) for the clean-canvas job."""
    shard_step = _clean_canvas_shard_execution_step(document)
    canvas = str(_clean_canvas_export_step(document).get("env", {}).get("CANVAS"))
    assert canvas and "runner.temp" in canvas
    return shard_step, canvas, str(shard_step.get("working-directory")) == canvas


def test_z_workflow_executes_exported_runtime_shard_commands_inside_canvas():
    # Proof F: the Mission-local workflow must actually execute every shipped
    # RT01 shard command inside the exported canvas with the PostgreSQL
    # services the shipped workflow itself declares -- the proof of the
    # exported product's CI, not a source-side lookalike. The step must run
    # from the canvas the job exported into and require real passes, so
    # DB-gated proofs execute instead of silently skipping.
    document = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    shard_step, _canvas, inside_canvas = _shard_step_canvas_binding(document)
    assert inside_canvas
    command = str(shard_step.get("run", ""))
    assert RUNTIME_WORKFLOW_PATH in command
    assert "pytest" in command
    # DB-gated proofs must actually execute: a shard command that proves
    # nothing (no tests passed) must fail the job closed.
    assert "passed" in command
    services = document["jobs"]["clean-canvas"]["services"]
    assert services["postgres"]["image"].startswith("postgres:15")
    assert services["postgres17"]["image"].startswith("postgres:17")


def test_shard_execution_binding_catches_a_step_outside_the_canvas():
    # Non-vacuity: the inside-canvas binding check above must fail when the
    # shard-execution step runs somewhere other than the exported canvas (here:
    # the source checkout, with no ``working-directory``), rather than passing
    # blindly.
    document = yaml.safe_load(
        "jobs:\n"
        "  clean-canvas:\n"
        "    services:\n"
        "      postgres:\n"
        "        image: postgres:15\n"
        "      postgres17:\n"
        "        image: postgres:17\n"
        "    steps:\n"
        "      - env:\n"
        "          CANVAS: ${{ runner.temp }}/clean-campaign-canvas\n"
        "        run: |\n"
        "          python scripts/export_clean_campaign.py "
        "--repo-root . --ref HEAD --output \"$CANVAS\"\n"
        "      - run: pytest .github/workflows/rt01-runtime.yml\n"
    )
    _shard_step, _canvas, inside_canvas = _shard_step_canvas_binding(document)
    assert not inside_canvas


ACTIONLINT_VERSION = "1.7.12"
ACTIONLINT_SHA256 = (
    "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"
)


def _actionlint_step(document):
    steps = document["jobs"]["clean-canvas"]["steps"]
    matches = [
        step for step in steps
        if isinstance(step, dict) and "actionlint" in str(step.get("run", ""))
    ]
    assert len(matches) == 1
    return matches[0]


def test_z_workflow_lints_the_emitted_workflows_with_pinned_actionlint():
    # Layer A of the Z6 product-acceptance architecture: actionlint owns GitHub
    # Actions workflow syntax, expression and schema checking of the ACTUAL
    # emitted workflow bytes. It must be an immutably pinned release with a
    # verified archive digest, must lint only the two emitted workflows inside
    # the canvas, must keep the binary/temp outside the emitted product, must
    # disable unrelated shellcheck/pyflakes, and must not broadly suppress
    # diagnostics.
    document = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    canvas = str(_clean_canvas_export_step(document).get("env", {}).get("CANVAS"))
    assert canvas and "runner.temp" in canvas
    step = _actionlint_step(document)
    command = str(step.get("run", ""))
    # Exact immutable version + verified SHA-256 archive digest, checked before
    # extraction/execution (no mutable "latest", no unverified download).
    assert ACTIONLINT_VERSION in command
    assert ACTIONLINT_SHA256 in command
    assert "actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz" in command
    assert "sha256sum -c -" in command
    # Only the two emitted product workflows are linted, from the canvas.
    assert ".github/workflows/rt01-runtime.yml" in command
    assert ".github/workflows/hard-write-boundary.yml" in command
    assert "$CANVAS" in command
    # The tool/binary and fixtures live outside the emitted product.
    assert "RUNNER_TEMP" in command
    assert "clean-campaign-canvas" not in command
    # Scope is Actions syntax only: optional shellcheck/pyflakes disabled, and
    # no broad suppression of actionlint diagnostics.
    assert "-shellcheck= -pyflakes=" in command
    assert "-ignore" not in command


def test_z_workflow_actionlint_gate_is_non_vacuous():
    # Non-vacuity: the actionlint step must run a deliberately invalid workflow
    # fixture and fail the job when actionlint accepts it, so the gate proves a
    # real non-zero result rather than merely invoking the tool name.
    document = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    command = str(_actionlint_step(document).get("run", ""))
    assert "actionlint-negative" in command
    assert "vacuous" in command
    assert "exit 1" in command


# The Z6 Mission-bound provenance assertion: on this Mission's own branch the
# cumulative diff against the approved base must stay exactly inside the Z6
# machine Surface Budget. Because the budget contains only export/CI/proof
# surfaces, this single subset check is also the explicit gameplay-domain
# non-regression diff: no gameplay, schema, migration, save, or reality
# implementation file can change without leaving the budget.
Z6_BASE_SHA = "2a1eae0be2a9e9374f5a7fa5d233b900cd21cbc4"
Z6_BRANCH = "post-ev2-z6/export-product-acceptance"
Z6_SURFACE_BUDGET = frozenset({
    "scripts/export_clean_campaign.py",
    "bootstrap/CLEAN_CAMPAIGN_EXPORT_POLICY.json",
    "tests/post_ev2_z/test_clean_campaign_export.py",
    ".github/workflows/post-ev2-z-clean-canvas.yml",
    ".github/workflows/rt01-runtime.yml",
    "docs/POST-EV2-Z-CLEAN-CAMPAIGN-EXPORT.md",
    "CHANGELOG.md",
    "ENGINE_CHANGELOG.md",
})


def _on_z6_mission_branch():
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch == Z6_BRANCH:
        return True
    if branch != "HEAD":
        return False
    return Z6_BRANCH in (
        os.environ.get("GITHUB_HEAD_REF"),
        os.environ.get("GITHUB_REF_NAME"),
    )


def test_z6_cumulative_diff_stays_inside_the_mission_budget():
    if not _on_z6_mission_branch():
        pytest.skip("POST-EV2-Z6 mission-bound assertion")
    changed = _git("diff", "--name-only", Z6_BASE_SHA).stdout.split()
    untracked = _git("ls-files", "--others", "--exclude-standard").stdout.split()
    assert set(changed) | set(untracked) <= set(Z6_SURFACE_BUDGET)


# --------------------------------------------------------------------------
# POST-EV2-Z7: product identity acceptance
# --------------------------------------------------------------------------

# The source-owned campaign identity tokens the exported artifact must not
# carry, and the one user-facing surface whose actual emitted bytes must be
# campaign-neutral. These mirror the tracked policy's ``identity`` block; the
# durable guard reads the policy, and this proof additionally pins the expected
# values so a silent widening of the accepted identity fails closed.
IDENTITY_PATH_TOKENS = (
    "madma",
    "gork",
    "mugen",
    "saarpa",
    "ioulaum",
    "vampire",
    "larloch",
    "spellplague",
    "bor-family",
)
IDENTITY_CONTENT_SURFACES = {"README.md": ["Rolling High Club", "rhc-primary"]}
IDENTITY_OMITTED_SKELETON_PREFIXES = [
    "characters/madma/",
    "npc/profiles/bor-family/",
]


def _emitted_relative_paths(output: Path):
    """Every emitted relative path in the canvas: files AND directories."""
    emitted = set()
    for path in output.rglob("*"):
        relative = path.relative_to(output).as_posix()
        emitted.add(relative + "/" if path.is_dir() else relative)
    return emitted


def _wrap_writes(monkeypatch, action):
    """Run ``action`` after every real ``_write_file`` materializes a file.

    This is the Z7 contamination seam. ``action`` runs *during* materialization
    -- after the pre-materialization identity precheck has already passed and
    before the post-materialization inspection -- so a test can inject output
    the precheck never saw. That is exactly the false-green window the Z7 repair
    closes: the old exporter certified its PREDICTED pre-write path set/bytes.
    """
    real_write = exporter._write_file

    def wrapper(full, data, mode):
        real_write(full, data, mode)
        action(full, data, mode)

    monkeypatch.setattr(exporter, "_write_file", wrapper)


def _require_symlinks(tmp_path):
    """Skip when the host filesystem cannot create a symlink.

    The path-kind proof needs a real symlink: on an unprivileged Windows host
    ``os.symlink`` raises WinError 1314, so the symlink-specific negatives and
    the legitimate-``120000`` positive skip there and run in the Linux CI
    environment, where symlinks are always available. The kind/byte guards
    themselves stay proven on every host by the symlink-free negatives below.
    """
    probe_target = tmp_path / "symlink-probe-target"
    probe_link = tmp_path / "symlink-probe-link"
    probe_target.write_text("probe\n", encoding="utf-8")
    try:
        os.symlink(probe_target, probe_link)
    except (OSError, NotImplementedError):
        pytest.skip("host filesystem cannot create symlinks (privilege/OS)")
    else:
        probe_link.unlink()
    finally:
        probe_target.unlink()


def _require_posix_modes(tmp_path):
    """Skip when the host does not expose POSIX permission semantics.

    The executable-mode fidelity proof needs an observable POSIX mode: on
    Windows ``os.chmod`` only toggles the read-only attribute, so a Git
    ``100755`` bit is not representable and the mode negatives skip there and run
    in the Ubuntu CI environment, where POSIX modes are always observable. The
    probe also skips on a POSIX host whose filesystem still refuses to reflect
    the bits, so the tests never assert a platform guarantee they cannot prove.
    """
    if os.name != "posix":
        pytest.skip("host does not expose POSIX permission semantics")
    probe = tmp_path / "mode-probe"
    probe.write_bytes(b"probe\n")
    os.chmod(probe, 0o755)
    try:
        if stat.S_IMODE(os.lstat(probe).st_mode) != 0o755:
            pytest.skip("host filesystem does not reflect POSIX permission bits")
    finally:
        probe.unlink()


def test_exported_tree_carries_no_campaign_identity(tmp_path):
    # Positive: the ACTUAL emitted artifact carries no declared campaign
    # identity path token -- files OR preserved directory skeletons. The named
    # source-owned Madma directory (file and folder) is gone, and the root
    # README is the policy-generated campaign-neutral genesis.
    output, _receipt, _ = _sample_export(tmp_path)
    emitted = _emitted_relative_paths(output)
    leaks = sorted(
        path
        for path in emitted
        for token in IDENTITY_PATH_TOKENS
        if token in path.lower()
    )
    assert leaks == []
    assert not (output / "characters" / "madma").exists()
    assert not (output / "characters" / "madma" / "NARRATIVE_DIRECTION.md").exists()
    assert not (output / "npc" / "profiles" / "bor-family").exists()

    neutral = exporter.generated_bytes(_policy(), "README.md")
    assert (output / "README.md").read_bytes() == neutral
    lowered = neutral.decode("utf-8").lower()
    for token in ("rolling high club", "rhc-primary", *IDENTITY_PATH_TOKENS):
        assert token not in lowered, token


def test_receipt_records_machine_readable_identity_acceptance(tmp_path):
    # Evidence: the receipt carries explicit, machine-readable identity
    # acceptance for the exact emitted artifact.
    output, receipt, receipt_object = _sample_export(tmp_path)
    evidence = receipt_object["identity_acceptance"]
    assert evidence["accepted"] is True
    assert evidence["violations"] == []
    assert evidence["path_tokens"] == sorted(IDENTITY_PATH_TOKENS)
    assert evidence["content_surfaces"] == {
        surface: sorted(tokens)
        for surface, tokens in sorted(IDENTITY_CONTENT_SURFACES.items())
    }
    assert evidence["omitted_skeleton_prefixes"] == IDENTITY_OMITTED_SKELETON_PREFIXES
    # The acceptance evidence reports the ACTUAL emitted tree -- files AND
    # directories -- not a predicted pre-write count.
    assert evidence["emitted_path_count"] == len(_emitted_relative_paths(output))
    # The on-disk receipt carries the same evidence as the in-memory object.
    assert json.loads(receipt.read_text(encoding="utf-8"))["identity_acceptance"] == evidence


def test_identity_guard_catches_a_campaigned_root_readme(monkeypatch, tmp_path):
    # Negative (content, red-before/green-after): a root README that asserts the
    # source campaign's identity must fail the export closed. Reclassify the
    # source RHC README as COPY (its bytes declare the live Rolling High Club
    # campaign) and drop its neutral generation.
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["rules"] = [
        {"disposition": "COPY", "match": rule["match"]}
        if rule["match"] == "README.md"
        else rule
        for rule in policy["rules"]
    ]
    policy["generate"].pop("README.md")
    parsed = exporter.parse_policy(json.dumps(policy))
    monkeypatch.setattr(exporter, "load_policy", lambda ref, repo_root: parsed)
    with pytest.raises(exporter.ExportError):
        exporter.export(
            ROOT, "HEAD", tmp_path / "canvas", tmp_path / "canvas.receipt.json"
        )
    assert not (tmp_path / "canvas").exists()


def test_identity_guard_catches_a_named_skeleton_without_a_file(monkeypatch, tmp_path):
    # Negative (path, red-before/green-after): the named directory skeleton must
    # be omitted even when no file is emitted under it -- an empty preserved
    # ``characters/madma/`` still leaks the source campaign's character name.
    # Dropping the omission must fail the export closed.
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["identity"]["omitted_skeleton_prefixes"] = []
    parsed = exporter.parse_policy(json.dumps(policy))
    monkeypatch.setattr(exporter, "load_policy", lambda ref, repo_root: parsed)
    with pytest.raises(exporter.ExportError):
        exporter.export(
            ROOT, "HEAD", tmp_path / "canvas", tmp_path / "canvas.receipt.json"
        )
    assert not (tmp_path / "canvas").exists()


def test_identity_guard_is_token_driven_not_a_readme_special_case():
    # Negative (unit): the guard scans every emitted path for every declared
    # identity token, so an intentionally injected named entity/character path
    # (not merely the known README or Madma directory) is caught. This is a
    # genuine scan, not a static filename denylist.
    policy = _policy()
    evidence = exporter.identity_acceptance(
        policy,
        ["villain/gork.md", "characters/madma/", "tests/"],
        {"README.md": exporter.generated_bytes(policy, "README.md")},
    )
    assert evidence["accepted"] is False
    assert any("'gork'" in violation for violation in evidence["violations"])
    assert any("'madma'" in violation for violation in evidence["violations"])


def test_identity_guard_catches_a_content_token_and_a_missing_surface():
    policy = _policy()
    campaigned = exporter.identity_acceptance(
        policy, ["README.md"], {"README.md": b"# Rolling High Club\n"}
    )
    assert any(
        "asserts campaign identity token" in violation
        for violation in campaigned["violations"]
    )
    missing = exporter.identity_acceptance(policy, ["README.md"], {})
    assert any(
        "is not present in the export" in violation
        for violation in missing["violations"]
    )


def test_identity_guard_rejects_an_identity_path_injected_during_materialization(
    monkeypatch, tmp_path
):
    # Negative (actual output tree, red-before/green-after): an extra named,
    # identity-bearing path written into the completed tree AFTER the
    # pre-materialization precheck must fail the export closed. The old exporter
    # certified the PREDICTED path set and wrote a false accepted receipt; the
    # repair inspects the ACTUAL emitted files and directories before the receipt.
    canvas = tmp_path / "canvas"
    receipt = tmp_path / "canvas.receipt.json"
    state = {"injected": False}

    def inject(full, data, mode):
        if state["injected"]:
            return
        state["injected"] = True
        leaked = canvas / "characters" / "madma" / "leak.md"
        leaked.parent.mkdir(parents=True, exist_ok=True)
        leaked.write_text("leaked\n", encoding="utf-8")

    _wrap_writes(monkeypatch, inject)
    with pytest.raises(exporter.ExportError):
        exporter.export(ROOT, "HEAD", canvas, receipt)
    # Fail closed: no accepted receipt may be written for the contaminated tree.
    assert not receipt.exists()


def test_identity_guard_rejects_an_empty_named_directory_injected_during_materialization(
    monkeypatch, tmp_path
):
    # Negative (actual directory skeletons): a named empty directory with no file
    # still leaks the source-owned name; injecting ``characters/madma/`` during
    # materialization must fail the export closed and write no accepted receipt.
    canvas = tmp_path / "canvas"
    receipt = tmp_path / "canvas.receipt.json"
    state = {"injected": False}

    def inject(full, data, mode):
        if state["injected"]:
            return
        state["injected"] = True
        (canvas / "characters" / "madma").mkdir(parents=True, exist_ok=True)

    _wrap_writes(monkeypatch, inject)
    with pytest.raises(exporter.ExportError):
        exporter.export(ROOT, "HEAD", canvas, receipt)
    assert not receipt.exists()


def test_identity_guard_rejects_a_mutated_readme_written_during_materialization(
    monkeypatch, tmp_path
):
    # Negative (actual content bytes, red-before/green-after): the WRITTEN root
    # README is altered to assert the source campaign after the precheck but
    # before the inspection. The receipt must never certify the predicted,
    # pre-write bytes.
    canvas = tmp_path / "canvas"
    receipt = tmp_path / "canvas.receipt.json"

    def mutate_readme(full, data, mode):
        if full.name == "README.md" and full.parent == canvas:
            full.write_bytes(b"# Rolling High Club\n")

    _wrap_writes(monkeypatch, mutate_readme)
    with pytest.raises(exporter.ExportError) as excinfo:
        exporter.export(ROOT, "HEAD", canvas, receipt)
    assert "campaign identity token" in str(excinfo.value)
    assert not receipt.exists()


def test_identity_guard_rejects_an_unlisted_extra_path_during_materialization(
    monkeypatch, tmp_path
):
    # Negative (path inventory): the manifest guard compares the ACTUAL emitted
    # file/directory inventory against the authorized export output inventory, so
    # even a token-free extra path the token scan would not flag is rejected and
    # cannot be silently certified.
    canvas = tmp_path / "canvas"
    receipt = tmp_path / "canvas.receipt.json"
    state = {"injected": False}

    def inject(full, data, mode):
        if state["injected"]:
            return
        state["injected"] = True
        ghost = canvas / "docs" / "ghost.md"
        ghost.parent.mkdir(parents=True, exist_ok=True)
        ghost.write_text("no declared identity token\n", encoding="utf-8")

    _wrap_writes(monkeypatch, inject)
    with pytest.raises(exporter.ExportError) as excinfo:
        exporter.export(ROOT, "HEAD", canvas, receipt)
    assert "unexpected emitted path" in str(excinfo.value)
    assert not receipt.exists()


# --------------------------------------------------------------------------
# POST-EV2-Z7 repair: real-artifact path-kind + receipt byte provenance
# --------------------------------------------------------------------------

def test_inventory_kind_violation_distinguishes_a_symlink_from_a_regular_file():
    # Negative (unit, symlink-free, runs on every host): the previous inspector
    # recorded a regular file and a symlink that share a relative path as the
    # identical bare string, so a symlink substitution was invisible to the
    # inventory guard. The path-kind guard now compares the authorized species
    # to the actual no-follow species and rejects a symlink standing in for an
    # authorized regular file.
    expected = {"README.md": exporter.SPECIES_REGULAR}
    actual = {"README.md": exporter.SPECIES_SYMLINK}
    violations = exporter._emitted_inventory_violations(expected, actual)
    assert any(
        "authorized export output kind" in violation for violation in violations
    )
    # Symmetry: a directory standing in for an authorized regular file is caught
    # even though the file/directory names collide.
    assert exporter._emitted_inventory_violations(
        {"docs/guide.md": exporter.SPECIES_REGULAR},
        {"docs/guide.md": exporter.SPECIES_DIRECTORY},
    )
    # Control: matching species is not a violation.
    assert exporter._emitted_inventory_violations(expected, expected) == []


def test_clean_export_passes_kind_and_content_attestation(tmp_path):
    # Positive (mode/type/bytes): every emitted entry's actual no-follow species
    # is what its disposition implies, and every emitted regular file's REAL
    # bytes match its receipt digest -- not merely the token scan.
    output, _receipt, receipt_object = _sample_export(tmp_path)
    policy = _policy()
    resolved = [
        (mode, sha, path, exporter.disposition_for_path(policy, path))
        for mode, _otype, sha, path in exporter.tracked_entries("HEAD", ROOT)
    ]
    export_files = [
        exporter.generate_output_path(policy, path)
        if disposition == exporter.GENERATE_EMPTY
        else path
        for _mode, _sha, path, disposition in resolved
        if disposition != exporter.EXCLUDE
    ]
    expected = exporter._expected_output_inventory(
        policy, resolved, exporter._skeleton_dirs("HEAD", ROOT, policy), export_files
    )
    inventory = exporter._actual_emitted_inventory(output)
    assert exporter._emitted_inventory_violations(expected, inventory) == []
    entries = {entry["path"]: entry for entry in receipt_object["entries"]}
    assert entries  # non-vacuous
    for path, entry in entries.items():
        assert inventory.get(path) == exporter.SPECIES_REGULAR, path
        digest = hashlib.sha256((output / path).read_bytes()).hexdigest()
        assert digest == entry["sha256"], path
    assert exporter._emitted_content_violations(
        output, expected, inventory, receipt_object["entries"]
    ) == []
    assert receipt_object["identity_acceptance"]["accepted"] is True


def test_kind_guard_rejects_a_directory_replacing_a_regular_file(
    monkeypatch, tmp_path
):
    # Negative (kind, symlink-free, runs on every host): replacing an expected
    # regular file with a real DIRECTORY of the same relative path must fail
    # closed with no accepted receipt. (The directory surfaces as its own
    # ``name/`` inventory key, so the path-set guard catches it here; the
    # same-key symlink-vs-file distinction is proven by the unit test above and
    # the symlink negatives that run in Linux CI.)
    canvas = tmp_path / "canvas"
    receipt = tmp_path / "canvas.receipt.json"

    def swap_dir(full, data, mode):
        if full.name == "PROJECT_PRIMER.md" and full.parent == canvas:
            full.unlink()
            full.mkdir()

    _wrap_writes(monkeypatch, swap_dir)
    with pytest.raises(exporter.ExportError):
        exporter.export(ROOT, "HEAD", canvas, receipt)
    assert not receipt.exists()


def test_content_attestation_rejects_a_token_free_altered_regular_file(
    monkeypatch, tmp_path
):
    # Negative (byte provenance, symlink-free, red-before/green-after): a
    # regular file altered during materialization to content that carries NO
    # declared identity token once passed the token scan, and the receipt held
    # only the intended blob SHA. The byte-provenance guard now compares the
    # real materialized bytes to the intended digest and fails closed.
    canvas = tmp_path / "canvas"
    receipt = tmp_path / "canvas.receipt.json"
    victim = "PROJECT_PRIMER.md"

    def corrupt(full, data, mode):
        if str(full) == str(canvas / victim):
            full.write_bytes(data + b"\nAltered, but carries no identity token.\n")

    _wrap_writes(monkeypatch, corrupt)
    with pytest.raises(exporter.ExportError) as excinfo:
        exporter.export(ROOT, "HEAD", canvas, receipt)
    assert "do not match its authorized intended content" in str(excinfo.value)
    assert not receipt.exists()


def test_identity_guard_rejects_readme_symlinked_to_an_external_neutral_file(
    monkeypatch, tmp_path
):
    # Negative (path kind, red-before/green-after): after the precheck, replace
    # the WRITTEN root README regular file with a SYMLINK to a neutral file
    # OUTSIDE the canvas whose bytes carry no identity token. The previous
    # inspector followed the link (`is_file()` / `read_bytes()`), read the
    # neutral target, and certified acceptance with the intended blob SHA; the
    # repair reads the species with no-follow `lstat`, rejects the substituted
    # link, and writes no accepted receipt.
    _require_symlinks(tmp_path)
    canvas = tmp_path / "canvas"
    receipt = tmp_path / "canvas.receipt.json"
    outside = tmp_path / "outside-neutral.txt"
    outside.write_text("campaign-neutral content, no identity token\n", encoding="utf-8")

    def swap_readme(full, data, mode):
        if full.name == "README.md" and full.parent == canvas:
            full.unlink()
            os.symlink(outside, full)

    _wrap_writes(monkeypatch, swap_readme)
    with pytest.raises(exporter.ExportError) as excinfo:
        exporter.export(ROOT, "HEAD", canvas, receipt)
    assert "authorized export output kind" in str(excinfo.value)
    assert not receipt.exists()
    # The substituted target was never followed into the canvas.
    assert outside.read_text(encoding="utf-8") == (
        "campaign-neutral content, no identity token\n"
    )


def test_identity_guard_rejects_a_regular_file_replaced_by_external_symlink(
    monkeypatch, tmp_path
):
    # Negative (path kind): an expected regular non-content file replaced by a
    # symlink to another neutral external file must fail the path-kind guard even
    # though the relative names match exactly.
    _require_symlinks(tmp_path)
    canvas = tmp_path / "canvas"
    receipt = tmp_path / "canvas.receipt.json"
    outside = tmp_path / "external-neutral.txt"
    outside.write_text("no identity token here either\n", encoding="utf-8")
    victim = "PROJECT_PRIMER.md"

    def swap(full, data, mode):
        if str(full) == str(canvas / victim):
            full.unlink()
            os.symlink(outside, full)

    _wrap_writes(monkeypatch, swap)
    with pytest.raises(exporter.ExportError) as excinfo:
        exporter.export(ROOT, "HEAD", canvas, receipt)
    assert "authorized export output kind" in str(excinfo.value)
    assert not receipt.exists()


def test_authorized_git_symlink_copy_is_accepted_by_kind_and_target(tmp_path):
    # Positive (kind contract): a legitimate Git COPY mode ``120000`` symlink is
    # expected to be an actual on-disk symlink. Writing it through the real
    # ``_write_file`` and inspecting with the no-follow inventory + byte
    # attestation accepts it by its exact link target -- it is never treated as a
    # regular file -- while a substituted target is caught by the attestation.
    _require_symlinks(tmp_path)
    canvas = tmp_path / "canvas"
    canvas.mkdir()
    link_path = "neutral-link.txt"
    target = "PROJECT_PRIMER.md"
    exporter._write_file(
        canvas / link_path, target.encode("utf-8"), exporter.SYMLINK_MODE
    )
    assert (canvas / link_path).is_symlink()

    expected = {link_path: exporter.SPECIES_SYMLINK}
    actual = exporter._actual_emitted_inventory(canvas)
    assert actual[link_path] == exporter.SPECIES_SYMLINK
    assert exporter._emitted_inventory_violations(expected, actual) == []

    good = [
        {
            "path": link_path,
            "mode": exporter.SYMLINK_MODE,
            "sha256": hashlib.sha256(target.encode("utf-8")).hexdigest(),
        }
    ]
    assert exporter._emitted_content_violations(canvas, expected, actual, good) == []

    bad = [
        {
            "path": link_path,
            "mode": exporter.SYMLINK_MODE,
            "sha256": hashlib.sha256(b"some/other/target").hexdigest(),
        }
    ]
    assert exporter._emitted_content_violations(canvas, expected, actual, bad)


def test_inventory_fails_closed_on_unscannable_directory(monkeypatch, tmp_path):
    # Negative (traversal completeness, red-before/green-after, host-independent
    # monkeypatch so it works as root and non-root): a directory that cannot be
    # scanned must FAIL the export closed, never be silently omitted. The prior
    # inspector used ``os.walk`` with no ``onerror``; Python documents that
    # ``os.walk`` silently ignores ``scandir`` errors (and even ``DirEntry``
    # classification errors), so an unlisted file inside an expected preserved
    # skeleton would have been dropped from the inventory and falsely certified
    # clean. Here the expected ``inventory/weapons/`` skeleton refuses scanning
    # and also holds an unlisted injected file: the export must refuse and write
    # no accepted receipt.
    canvas = tmp_path / "canvas"
    receipt = tmp_path / "canvas.receipt.json"
    denied = canvas / "inventory" / "weapons"
    denied_abs = os.path.abspath(str(denied))
    real_scandir = os.scandir

    def denying_scandir(path):
        if os.path.abspath(str(path)) == denied_abs:
            raise PermissionError(13, "denied by proof")
        return real_scandir(path)

    state = {"injected": False}

    def inject(full, data, mode):
        if state["injected"]:
            return
        state["injected"] = True
        hidden = denied / "hidden-unlisted.md"
        hidden.parent.mkdir(parents=True, exist_ok=True)
        hidden.write_text("no identity token here\n", encoding="utf-8")

    _wrap_writes(monkeypatch, inject)
    monkeypatch.setattr(os, "scandir", denying_scandir)
    with pytest.raises(exporter.ExportError):
        exporter.export(ROOT, "HEAD", canvas, receipt)
    assert not receipt.exists()


def test_executable_mode_downgrade_is_rejected(monkeypatch, tmp_path):
    # Negative (POSIX executable fidelity, red-before/green-after): an expected
    # executable Git ``100755`` COPY regular file is chmodded 0755 -> 0644 AFTER
    # it is written, with its path and bytes unchanged. The prior inspector
    # verified bytes but no permissions, so the altered mode passed with the
    # intended blob SHA; the repair compares the real on-disk POSIX mode against
    # the authorized Git mode and fails closed. (Ubuntu CI runs this proof; a
    # non-POSIX host skips it.)
    _require_posix_modes(tmp_path)
    canvas = tmp_path / "canvas"
    receipt = tmp_path / "canvas.receipt.json"
    stripped = {"count": 0}

    def strip_exec(full, data, mode):
        if mode == "100755":
            os.chmod(full, 0o644)
            stripped["count"] += 1

    _wrap_writes(monkeypatch, strip_exec)
    with pytest.raises(exporter.ExportError) as excinfo:
        exporter.export(ROOT, "HEAD", canvas, receipt)
    assert "POSIX mode" in str(excinfo.value)
    assert stripped["count"] > 0
    assert not receipt.exists()


def test_non_executable_mode_upgrade_is_rejected(monkeypatch, tmp_path):
    # Negative (POSIX executable fidelity, red-before/green-after): an expected
    # non-executable COPY/GENERATE_EMPTY regular file is chmodded 0644 -> 0755
    # after writing, with bytes unchanged -- an accidental execute bit added. The
    # authorized Git mode is 100644, so the real mode mismatch must fail closed.
    _require_posix_modes(tmp_path)
    canvas = tmp_path / "canvas"
    receipt = tmp_path / "canvas.receipt.json"
    upgraded = {"count": 0}

    def add_exec(full, data, mode):
        if mode == "100644":
            os.chmod(full, 0o755)
            upgraded["count"] += 1

    _wrap_writes(monkeypatch, add_exec)
    with pytest.raises(exporter.ExportError) as excinfo:
        exporter.export(ROOT, "HEAD", canvas, receipt)
    assert "POSIX mode" in str(excinfo.value)
    assert upgraded["count"] > 0
    assert not receipt.exists()


def test_clean_export_preserves_posix_executable_modes(tmp_path):
    # Positive (POSIX executable fidelity): a fully clean export keeps every
    # emitted regular file's real on-disk mode equal to its authorized Git mode:
    # the executable ``.githooks/pre-commit`` COPY is 0755 and a non-executable
    # surface (the generated root README) is 0644.
    _require_posix_modes(tmp_path)
    output, _receipt, receipt_object = _sample_export(tmp_path)
    entries = {entry["path"]: entry for entry in receipt_object["entries"]}
    assert entries[".githooks/pre-commit"]["mode"] == "100755"
    assert stat.S_IMODE(os.lstat(output / ".githooks" / "pre-commit").st_mode) == 0o755
    assert entries["README.md"]["mode"] == "100644"
    assert stat.S_IMODE(os.lstat(output / "README.md").st_mode) == 0o644


def test_permission_contract_maps_git_modes():
    # Unit (every host): the authorized POSIX bits for a regular Git mode.
    assert exporter._permission_contract("100755") == 0o755
    assert exporter._permission_contract("100644") == 0o644
    # A symlink (or any non-regular mode) carries no POSIX permission contract.
    assert exporter._permission_contract(exporter.SYMLINK_MODE) is None
    assert exporter._permission_contract("100000") is None


def test_emitted_mode_violations_detects_a_changed_mode(tmp_path):
    # Unit (POSIX only): the mode guard compares real on-disk bits to the
    # authorized Git mode and is symmetric for both a stripped exec bit and an
    # added one, while a symlink mode is exempt.
    _require_posix_modes(tmp_path)
    target = tmp_path / "victim"
    target.write_bytes(b"x\n")
    os.chmod(target, 0o755)
    assert exporter._emitted_mode_violations(target, "victim", "100755") == []
    assert exporter._emitted_mode_violations(target, "victim", "100644")
    os.chmod(target, 0o644)
    assert exporter._emitted_mode_violations(target, "victim", "100644") == []
    assert exporter._emitted_mode_violations(target, "victim", "100755")
    assert (
        exporter._emitted_mode_violations(target, "victim", exporter.SYMLINK_MODE)
        == []
    )


def test_posix_mode_attestation_tracks_the_capability_predicate(monkeypatch):
    # Unit (every host): the receipt attestation is derived from the SAME
    # capability predicate the mode verifier uses, so it can never claim
    # ``verified`` while verification is skipped.
    monkeypatch.setattr(
        exporter, "_posix_permission_modes_observable", lambda: True
    )
    assert exporter._posix_mode_attestation() == "verified"
    monkeypatch.setattr(
        exporter, "_posix_permission_modes_observable", lambda: False
    )
    assert exporter._posix_mode_attestation() == "not_observable"


def test_receipt_records_posix_mode_attestation_verified_on_posix(tmp_path):
    # Positive (POSIX host): a fully clean export records the POSIX-mode
    # attestation as explicitly ``verified`` in a top-level, machine-readable
    # ``artifact_attestation`` -- the receipt states the mode proof instead of
    # leaving consumers to infer it from ``identity_acceptance.accepted``
    # (identity-only evidence). The host-independent dimensions stay verified.
    _require_posix_modes(tmp_path)
    output, receipt, receipt_object = _sample_export(tmp_path)
    attestation = receipt_object["artifact_attestation"]
    assert attestation["path_inventory"] == "verified"
    assert attestation["path_kind"] == "verified"
    assert attestation["content_digest"] == "verified"
    assert attestation["posix_mode"] == "verified"
    # The on-disk receipt carries the same attestation as the in-memory object.
    assert (
        json.loads(receipt.read_text(encoding="utf-8"))["artifact_attestation"]
        == attestation
    )


def test_receipt_records_mode_attestation_not_observable_when_capability_false(
    monkeypatch, tmp_path
):
    # Honesty (host-independent, red-before/green-after): when the capability
    # predicate says POSIX permission bits are not observable, the clean export
    # still succeeds -- path/kind/byte attestation still applies -- but the
    # receipt must record the mode attestation as ``not_observable``, never a
    # silent ``verified``. The value is derived from the same predicate the
    # verifier uses, so a skipped mode check can never be certified as passed.
    monkeypatch.setattr(
        exporter, "_posix_permission_modes_observable", lambda: False
    )
    output, receipt, receipt_object = _sample_export(tmp_path)
    attestation = receipt_object["artifact_attestation"]
    assert attestation["posix_mode"] == "not_observable"
    assert attestation["path_inventory"] == "verified"
    assert attestation["path_kind"] == "verified"
    assert attestation["content_digest"] == "verified"
    assert (
        json.loads(receipt.read_text(encoding="utf-8"))["artifact_attestation"]
        == attestation
    )


def test_receipt_records_machine_readable_artifact_attestation(tmp_path):
    # Evidence: every clean export records the capability-honest attestation
    # derived from the host predicate, so a consumer can distinguish a verified
    # POSIX-mode proof from a host that cannot observe the bits.
    output, receipt, receipt_object = _sample_export(tmp_path)
    attestation = receipt_object["artifact_attestation"]
    expected = (
        "verified"
        if exporter._posix_permission_modes_observable()
        else "not_observable"
    )
    assert attestation["posix_mode"] == expected
    assert (
        json.loads(receipt.read_text(encoding="utf-8"))["artifact_attestation"]
        == attestation
    )


def test_unknown_identity_field_is_rejected():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["identity"]["bogus"] = 1
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(json.dumps(policy))


def test_identity_content_surface_must_be_a_clean_file_path():
    for bad in ("../README.md", "docs/./guide.md", "README.md/"):
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        policy["identity"]["content_surfaces"] = {bad: ["x"]}
        with pytest.raises(exporter.ExportError):
            exporter.parse_policy(json.dumps(policy))


def test_identity_omitted_skeleton_must_be_owned_by_an_exclude_directory():
    # An omitted skeleton prefix that no EXCLUDE directory rule owns could hide
    # an unrelated namespace; it must fail closed.
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["identity"]["omitted_skeleton_prefixes"] = ["characters/"]
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(json.dumps(policy))


def test_identity_path_token_must_be_lowercase_and_trimmed():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["identity"]["path_tokens"] = ["Gork"]
    with pytest.raises(exporter.ExportError):
        exporter.parse_policy(json.dumps(policy))


# The POST-EV2-Z7 Mission-bound provenance assertion: on this Mission's own
# branch the cumulative diff against the approved base must stay exactly inside
# the Z7 machine Surface Budget (seven existing surfaces; create/delete none).
Z7_BASE_SHA = "d82f65785d8961df4bbfcf04cb78cf68a0f76c34"
Z7_BRANCH = "post-ev2-z7/product-identity-acceptance"
Z7_SURFACE_BUDGET = frozenset({
    "bootstrap/CLEAN_CAMPAIGN_EXPORT_POLICY.json",
    "scripts/export_clean_campaign.py",
    "tests/post_ev2_z/test_clean_campaign_export.py",
    ".github/workflows/post-ev2-z-clean-canvas.yml",
    "docs/POST-EV2-Z-CLEAN-CAMPAIGN-EXPORT.md",
    "CHANGELOG.md",
    "ENGINE_CHANGELOG.md",
})


def _on_z7_mission_branch():
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch == Z7_BRANCH:
        return True
    if branch != "HEAD":
        return False
    return Z7_BRANCH in (
        os.environ.get("GITHUB_HEAD_REF"),
        os.environ.get("GITHUB_REF_NAME"),
    )


def test_z7_cumulative_diff_stays_inside_the_mission_budget():
    if not _on_z7_mission_branch():
        pytest.skip("POST-EV2-Z7 mission-bound assertion")
    changed = _git("diff", "--name-only", Z7_BASE_SHA).stdout.split()
    untracked = _git("ls-files", "--others", "--exclude-standard").stdout.split()
    assert set(changed) | set(untracked) <= set(Z7_SURFACE_BUDGET)
