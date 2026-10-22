"""HWB-01 BUILD write-authority proof matrix.

Covers the machine Surface Budget contract, authority discovery (via the
RHC_JOHNNY_FIXTURE hermetic seam), the path/action classifier, the local
ordinary-commit fence with real Git, installer idempotency/refusals, and
the trusted server check-pr grading of exact head/base objects.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_write_boundary.py"
INSTALLER = ROOT / "scripts" / "install_write_guard.py"
HOOK = ROOT / ".githooks" / "pre-commit"

REPOSITORY = "Nollie-gif/Rolling-High-Club"
BRANCH = "hardening/hwb-01-build-write-authority"
MISSION = "HWB_01_TEST"


def _load_validator():
    spec = importlib.util.spec_from_file_location("vwb", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vwb = _load_validator()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _git(cwd, *args, check=True):
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True)
    if check and proc.returncode != 0:
        raise AssertionError(f"git {args} failed: {proc.stderr}")
    return proc


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_contract(base_sha: str, branch: str = BRANCH,
                   repository: str = REPOSITORY,
                   create=("newfile.txt", "docs/new.md"),
                   modify=("docs/a.md",),
                   delete=()) -> str:
    allow = {"create": list(create), "modify": list(modify),
             "delete": list(delete)}
    block = json.dumps(
        {"surface_budget_version": 1, "repository": repository,
         "branch": branch, "base_sha": base_sha, "mission": MISSION,
         "allow": allow},
        indent=2,
    )
    return block


def _make_johnny(base_sha: str, branch: str = BRANCH,
                 repository: str = REPOSITORY, contract: str | None = None,
                 header: bool = True) -> str:
    parts = []
    if header:
        parts += ["## JOHNNY CHECKPOINT", "",
                  f"REPOSITORY: {repository}",
                  f"BUILD/HEAD BRANCH: {branch}",
                  f"BASE SHA: {base_sha}",
                  f"MISSION IDENTITY: {MISSION}", ""]
    parts += [f"<!-- RHC_SURFACE_BUDGET_V1",
              contract or _make_contract(base_sha, branch=branch,
                                         repository=repository),
              "-->", ""]
    return "\n".join(parts)


def _fixture_dir(tmp_path: Path, *bodies: str) -> str:
    fixture = tmp_path / "johnny_fixture"
    fixture.mkdir(exist_ok=True)
    for index, body in enumerate(bodies):
        _write(fixture / f"johnny_{index}.txt", body)
    return str(fixture)


def _init_repo(tmp_path: Path, branch: str = BRANCH):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "RHC Test")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "remote", "add", "origin",
         f"https://github.com/{REPOSITORY}.git")
    _write(repo / "docs" / "a.md", "seed\n")
    _write(repo / "README.md", "seed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-b", branch)
    return repo, base_sha


def _stage_guard_files(repo: Path):
    scripts = repo / "scripts"
    scripts.mkdir(exist_ok=True)
    shutil.copy(VALIDATOR, scripts / "validate_write_boundary.py")
    shutil.copy(INSTALLER, scripts / "install_write_guard.py")
    (repo / ".githooks").mkdir(exist_ok=True)
    shutil.copy(HOOK, repo / ".githooks" / "pre-commit")


def _install_guard(repo: Path):
    _stage_guard_files(repo)
    proc = subprocess.run([sys.executable, "scripts/install_write_guard.py"],
                          cwd=str(repo), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def _run_validator(args, cwd, fixture=None):
    env = dict(os.environ)
    env.pop("GITHUB_REPOSITORY", None)
    if fixture is None:
        env.pop("RHC_JOHNNY_FIXTURE", None)
    else:
        env["RHC_JOHNNY_FIXTURE"] = fixture
    return subprocess.run([sys.executable, str(VALIDATOR), *args],
                          cwd=str(cwd), capture_output=True, text=True,
                          env=env)


# --------------------------------------------------------------------------
# Machine contract
# --------------------------------------------------------------------------

def test_valid_contract_parses(tmp_path):
    body = _make_johnny("a" * 40)
    contract = vwb.extract_and_parse_contract(body)
    assert contract["surface_budget_version"] == 1
    assert contract["mission"] == MISSION


def test_contract_cli_valid(tmp_path):
    body = _make_johnny("a" * 40)
    proc = _run_validator(["validate-contract", "-"], cwd=ROOT)
    assert proc.returncode != 0  # empty stdin fails closed
    path = tmp_path / "johnny.txt"
    _write(path, body)
    proc = _run_validator(["validate-contract", str(path)], cwd=ROOT)
    assert proc.returncode == 0, proc.stderr


def test_contract_malformed_json_fails(tmp_path):
    block = "definitely not json"
    with pytest.raises(vwb.BoundaryError):
        vwb.extract_and_parse_contract(
            f"<!-- RHC_SURFACE_BUDGET_V1\n{block}\n-->")


@pytest.mark.parametrize("mutation", [
    "version_zero", "version_string", "missing_field", "extra_field",
    "duplicate_block", "missing_close", "cross_action_duplicate",
    "bad_path_traversal", "bad_path_absolute", "bad_path_glob",
    "bad_base_sha", "allow_extra_action", "allow_missing_action",
])
def test_contract_failures(tmp_path, mutation):
    base = "a" * 40
    contract = json.loads(_make_contract(base))
    if mutation == "version_zero":
        contract["surface_budget_version"] = 0
    elif mutation == "version_string":
        contract["surface_budget_version"] = "1"
    elif mutation == "missing_field":
        contract.pop("mission")
    elif mutation == "extra_field":
        contract["notes"] = "sneaky"
    elif mutation == "cross_action_duplicate":
        contract["allow"]["modify"] = list(contract["allow"]["modify"]) + [
            "newfile.txt"]
    elif mutation == "bad_path_traversal":
        contract["allow"]["create"] = ["../escape.txt"]
    elif mutation == "bad_path_absolute":
        contract["allow"]["create"] = ["/abs.txt"]
    elif mutation == "bad_path_glob":
        contract["allow"]["create"] = ["docs/*.md"]
    elif mutation == "bad_base_sha":
        contract["base_sha"] = "deadbeef"
    elif mutation == "allow_extra_action":
        contract["allow"]["upsert"] = []
    elif mutation == "allow_missing_action":
        contract["allow"].pop("delete")

    raw = json.dumps(contract, indent=2)
    if mutation == "duplicate_block":
        text = f"<!-- RHC_SURFACE_BUDGET_V1\n{raw}\n-->\n<!-- RHC_SURFACE_BUDGET_V1\n{raw}\n-->"
    elif mutation == "missing_close":
        text = f"<!-- RHC_SURFACE_BUDGET_V1\n{raw}\n"
    else:
        text = f"<!-- RHC_SURFACE_BUDGET_V1\n{raw}\n-->"

    with pytest.raises(vwb.BoundaryError):
        vwb.extract_and_parse_contract(text)


def test_prose_outside_block_cannot_create_authority(tmp_path):
    base = "a" * 40
    prose = _make_johnny(base) + (
        "\nNote: you may also create anything you like.\n"
        "ALLOW create: secret.txt\n"
        "<!-- RHC_SURFACE_BUDGET_V1X prose imitation -->\n"
    )
    contract = vwb.extract_and_parse_contract(prose)
    assert "secret.txt" not in (
        contract["allow"]["create"] + contract["allow"]["modify"])
    with pytest.raises(vwb.BoundaryError):
        vwb.grade_changes([("A", ["secret.txt"])], contract["allow"])


def test_identity_header_missing_field_fails():
    body = _make_johnny("a" * 40).replace("MISSION IDENTITY: " + MISSION + "\n", "")
    with pytest.raises(vwb.BoundaryError):
        vwb.parse_identity(body)


# --------------------------------------------------------------------------
# Classifier
# --------------------------------------------------------------------------

def test_classifier_authorized_actions_pass():
    allow = {"create": ["new.txt"], "modify": ["a.md"], "delete": []}
    assert vwb.grade_changes([("A", ["new.txt"]), ("M", ["a.md"])], allow)


def test_classifier_unauthorized_path_fails():
    allow = {"create": ["new.txt"], "modify": ["a.md"], "delete": []}
    with pytest.raises(vwb.BoundaryError):
        vwb.grade_changes([("A", ["other.txt"])], allow)
    with pytest.raises(vwb.BoundaryError):
        vwb.grade_changes([("M", ["new.txt"])], allow)  # create-only path
    with pytest.raises(vwb.BoundaryError):
        vwb.grade_changes([("A", ["a.md"])], allow)  # modify-only path
    with pytest.raises(vwb.BoundaryError):
        vwb.grade_changes([("D", ["a.md"])], allow)


def test_classifier_rename_copy_cannot_widen_authority():
    allow = {"create": ["dest.txt"], "modify": ["a.md"], "delete": []}
    with pytest.raises(vwb.BoundaryError):  # source delete unauthorized
        vwb.grade_changes([("R100", ["a.md", "dest.txt"])], allow)
    with pytest.raises(vwb.BoundaryError):  # destination create unauthorized
        vwb.grade_changes([("R100", ["old.txt", "a.md"])],
                          {"create": [], "modify": ["a.md"],
                           "delete": ["old.txt"]})
    with pytest.raises(vwb.BoundaryError):  # copy source unauthorized
        vwb.grade_changes([("C100", ["unlisted.md", "new.txt"])],
                          {"create": ["new.txt"], "modify": [], "delete": []})


def test_classifier_unknown_status_fails_closed():
    allow = {"create": ["new.txt"], "modify": ["a.md"], "delete": []}
    with pytest.raises(vwb.BoundaryError):
        vwb.grade_changes([("X", ["new.txt"])], allow)
    with pytest.raises(vwb.BoundaryError):
        vwb._parse_name_status("Q100\tsomefile\n")


def test_classifier_typechange_fails_closed():
    allow = {"create": ["new.txt"], "modify": ["a.md"], "delete": ["a.md"]}
    with pytest.raises(vwb.BoundaryError):
        vwb.grade_changes([("T", ["a.md"])], allow)


# --------------------------------------------------------------------------
# Authority discovery (fixture seam)
# --------------------------------------------------------------------------

def test_discovery_exactly_one_match(tmp_path, monkeypatch):
    repo, base = _init_repo(tmp_path)
    del repo
    fixture = _fixture_dir(tmp_path, _make_johnny(base))
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    authority = vwb.select_authority(
        vwb.discover_candidates(),
        {"repository": REPOSITORY, "branch": BRANCH},
        lambda sha: sha == base,
    )
    assert authority["contract"]["base_sha"] == base


def test_discovery_zero_matches_fails_closed(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    fixture = _fixture_dir(tmp_path)  # empty: no JOHNNY at all
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    with pytest.raises(vwb.BoundaryError):
        vwb.select_authority(
            vwb.discover_candidates(),
            {"repository": REPOSITORY, "branch": BRANCH},
            lambda sha: True)


def test_discovery_duplicate_matches_fail_closed(tmp_path, monkeypatch):
    repo, base = _init_repo(tmp_path)
    del repo
    fixture = _fixture_dir(tmp_path, _make_johnny(base), _make_johnny(base))
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    with pytest.raises(vwb.BoundaryError):
        vwb.select_authority(
            vwb.discover_candidates(),
            {"repository": REPOSITORY, "branch": BRANCH},
            lambda sha: sha == base)


def test_discovery_wrong_branch_fails_closed(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    body = _make_johnny("a" * 40, branch="some/other-branch")
    fixture = _fixture_dir(tmp_path, body)
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    with pytest.raises(vwb.BoundaryError):
        vwb.select_authority(
            vwb.discover_candidates(),
            {"repository": REPOSITORY, "branch": BRANCH},
            lambda sha: True)


def test_discovery_wrong_repository_fails_closed(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    body = _make_johnny("a" * 40, repository="Other/Repo")
    fixture = _fixture_dir(tmp_path, body)
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    with pytest.raises(vwb.BoundaryError):
        vwb.select_authority(
            vwb.discover_candidates(),
            {"repository": REPOSITORY, "branch": BRANCH},
            lambda sha: True)


def test_discovery_wrong_base_fails_closed(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    body = _make_johnny("b" * 40)
    fixture = _fixture_dir(tmp_path, body)
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    with pytest.raises(vwb.BoundaryError):
        vwb.select_authority(
            vwb.discover_candidates(),
            {"repository": REPOSITORY, "branch": BRANCH},
            lambda sha: sha == "a" * 40)  # only real base is ancestor


def test_discovery_wrong_mission_fails_closed(tmp_path, monkeypatch):
    repo, base = _init_repo(tmp_path)
    del repo
    other = _make_johnny(base)
    other = other.replace(f"MISSION IDENTITY: {MISSION}",
                          "MISSION IDENTITY: OTHER_MISSION")
    fixture = _fixture_dir(tmp_path, other)
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    with pytest.raises(vwb.BoundaryError):
        vwb.select_authority(
            vwb.discover_candidates(),
            {"repository": REPOSITORY, "branch": BRANCH},
            lambda sha: sha == base)


# --------------------------------------------------------------------------
# Local Git fence: check-staged + real git commit
# --------------------------------------------------------------------------

def test_check_staged_authorized_passes(tmp_path):
    repo, base = _init_repo(tmp_path)
    fixture = _fixture_dir(tmp_path, _make_johnny(base))
    _write(repo / "docs" / "a.md", "changed\n")
    _git(repo, "add", "-A")
    proc = _run_validator(["check-staged"], cwd=repo, fixture=fixture)
    assert proc.returncode == 0, proc.stderr


def test_check_staged_unauthorized_fails(tmp_path):
    repo, base = _init_repo(tmp_path)
    fixture = _fixture_dir(tmp_path, _make_johnny(base))
    _write(repo / "unauthorized.txt", "nope\n")
    _git(repo, "add", "-A")
    proc = _run_validator(["check-staged"], cwd=repo, fixture=fixture)
    assert proc.returncode != 0
    assert "WRITE BOUNDARY REFUSED" in proc.stderr


def test_check_staged_delete_fails(tmp_path):
    repo, base = _init_repo(tmp_path)
    fixture = _fixture_dir(tmp_path, _make_johnny(base))
    _git(repo, "rm", "README.md")
    proc = _run_validator(["check-staged"], cwd=repo, fixture=fixture)
    assert proc.returncode != 0


def test_check_staged_rename_fails_closed(tmp_path):
    repo, base = _init_repo(tmp_path)
    fixture = _fixture_dir(tmp_path, _make_johnny(base))
    _git(repo, "mv", "docs/a.md", "docs/renamed.md")
    proc = _run_validator(["check-staged"], cwd=repo, fixture=fixture)
    assert proc.returncode != 0


def test_check_staged_authorized_rename_passes(tmp_path):
    repo, base = _init_repo(tmp_path)
    # destination docs/new.md is in create; source needs delete authority
    fixture_body = _make_johnny(
        base,
        contract=_make_contract(base, modify=(), delete=["docs/a.md"]),
    )
    fixture = _fixture_dir(tmp_path, fixture_body)
    _git(repo, "mv", "docs/a.md", "docs/new.md")
    proc = _run_validator(["check-staged"], cwd=repo, fixture=fixture)
    assert proc.returncode == 0, proc.stderr


def test_check_staged_nothing_staged_passes(tmp_path):
    repo, base = _init_repo(tmp_path)
    fixture = _fixture_dir(tmp_path, _make_johnny(base))
    proc = _run_validator(["check-staged"], cwd=repo, fixture=fixture)
    assert proc.returncode == 0, proc.stderr


def test_real_git_commit_refuses_unauthorized(tmp_path, monkeypatch):
    repo, base = _init_repo(tmp_path)
    fixture = _fixture_dir(tmp_path, _make_johnny(base))
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    _install_guard(repo)
    _write(repo / "unauthorized.txt", "nope\n")
    _git(repo, "add", "-A")
    proc = _git(repo, "commit", "-m", "unauthorized", check=False)
    assert proc.returncode != 0
    assert "WRITE BOUNDARY REFUSED" in proc.stderr
    # nothing durable was created
    log = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert log == base


def test_real_git_commit_allows_authorized(tmp_path, monkeypatch):
    repo, base = _init_repo(tmp_path)
    body = _make_johnny(base, contract=_make_contract(base, create=("ok.txt",)))
    fixture = _fixture_dir(tmp_path, body)
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    _install_guard(repo)
    _write(repo / "ok.txt", "fine\n")
    _git(repo, "add", "ok.txt")
    proc = _git(repo, "commit", "-m", "authorized", check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr


# --------------------------------------------------------------------------
# Installer
# --------------------------------------------------------------------------

def test_installer_is_idempotent(tmp_path):
    repo, base = _init_repo(tmp_path)
    del base
    _install_guard(repo)
    proc = subprocess.run([sys.executable, "scripts/install_write_guard.py"],
                          cwd=str(repo), capture_output=True, text=True)
    assert proc.returncode == 0
    assert "ALREADY ACTIVE" in proc.stdout


def test_installer_refuses_other_hooks_path(tmp_path):
    repo, base = _init_repo(tmp_path)
    del base
    _git(repo, "config", "core.hooksPath", ".githooks-other")
    _stage_guard_files(repo)
    proc = subprocess.run([sys.executable, "scripts/install_write_guard.py"],
                          cwd=str(repo), capture_output=True, text=True)
    assert proc.returncode != 0
    assert "INSTALL REFUSED" in proc.stderr
    assert _git(repo, "config", "core.hooksPath").stdout.strip() \
        == ".githooks-other"


def test_installer_refuses_unrelated_old_style_hook(tmp_path):
    repo, base = _init_repo(tmp_path)
    del base
    old = repo / ".git" / "hooks" / "pre-commit"
    old.parent.mkdir(exist_ok=True)
    old.write_text("#!/bin/sh\necho unrelated\n", encoding="utf-8")
    _stage_guard_files(repo)
    proc = subprocess.run([sys.executable, "scripts/install_write_guard.py"],
                          cwd=str(repo), capture_output=True, text=True)
    assert proc.returncode != 0
    assert "INSTALL REFUSED" in proc.stderr


# --------------------------------------------------------------------------
# Trusted server fence: check-pr grades exact head/base objects
# --------------------------------------------------------------------------

def test_check_pr_authorized_passes(tmp_path):
    repo, base = _init_repo(tmp_path)
    body = _make_johnny(base, contract=_make_contract(base))
    fixture = _fixture_dir(tmp_path, body)
    _write(repo / "newfile.txt", "ok\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "authorized build")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    proc = _run_validator(
        ["check-pr", base, head, BRANCH, "--repository", REPOSITORY, "--head-repository", REPOSITORY],
        cwd=repo, fixture=fixture)
    assert proc.returncode == 0, proc.stderr


def test_check_pr_unauthorized_fails(tmp_path):
    repo, base = _init_repo(tmp_path)
    body = _make_johnny(base, contract=_make_contract(base))
    fixture = _fixture_dir(tmp_path, body)
    _write(repo / "unauthorized.txt", "nope\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "unauthorized build")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    proc = _run_validator(
        ["check-pr", base, head, BRANCH, "--repository", REPOSITORY, "--head-repository", REPOSITORY],
        cwd=repo, fixture=fixture)
    assert proc.returncode != 0
    assert "WRITE BOUNDARY REFUSED" in proc.stderr


def test_check_pr_base_mismatch_fails_closed(tmp_path):
    repo, base = _init_repo(tmp_path)
    body = _make_johnny(base, contract=_make_contract(base))
    fixture = _fixture_dir(tmp_path, body)
    _write(repo / "newfile.txt", "ok\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "authorized build")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    # head masquerading as base: not the JOHNNY-bound base -> fail closed
    proc = _run_validator(
        ["check-pr", head, head, BRANCH, "--repository", REPOSITORY, "--head-repository", REPOSITORY],
        cwd=repo, fixture=fixture)
    assert proc.returncode != 0


def test_check_pr_head_branch_mismatch_fails_closed(tmp_path):
    repo, base = _init_repo(tmp_path)
    body = _make_johnny(base, contract=_make_contract(base))
    fixture = _fixture_dir(tmp_path, body)
    _write(repo / "newfile.txt", "ok\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "authorized build")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    proc = _run_validator(
        ["check-pr", base, head, "someone-elses-branch",
         "--repository", REPOSITORY, "--head-repository", REPOSITORY],
        cwd=repo, fixture=fixture)
    assert proc.returncode != 0


def test_check_pr_missing_objects_fail_closed(tmp_path):
    repo, base = _init_repo(tmp_path)
    del repo
    fixture = _fixture_dir(tmp_path, _make_johnny(base))
    proc = _run_validator(
        ["check-pr", base, "c" * 40, BRANCH, "--repository", REPOSITORY, "--head-repository", REPOSITORY],
        cwd=ROOT, fixture=fixture)
    assert proc.returncode != 0


# --------------------------------------------------------------------------
# PR #64 repair regressions (six classified findings)
# --------------------------------------------------------------------------

# Finding 1: the versioned hook must be tracked executable so a fresh checkout
# actually runs it.

def _make_hook_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "hookrepo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "RHC Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / ".githooks").mkdir()
    shutil.copy(HOOK, repo / ".githooks" / "pre-commit")
    _git(repo, "add", ".githooks/pre-commit")
    _git(repo, "update-index", "--chmod=+x", ".githooks/pre-commit")
    _git(repo, "commit", "-m", "hook")
    return repo


def test_hook_is_tracked_executable():
    proc = _git(ROOT, "ls-files", "--stage", ".githooks/pre-commit")
    assert proc.stdout.startswith("100755"), proc.stdout


def test_hook_mode_preserved_by_fresh_clone(tmp_path):
    source = _make_hook_repo(tmp_path)
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", str(source), str(clone))
    mode = _git(clone, "ls-files", "--stage", ".githooks/pre-commit").stdout
    assert mode.startswith("100755"), mode


# Finding 2: authority must be bound to the PR head repository, not branch alone.

def test_check_pr_fork_head_repository_fails_closed(tmp_path):
    repo, base = _init_repo(tmp_path)
    body = _make_johnny(base, contract=_make_contract(base))
    fixture = _fixture_dir(tmp_path, body)
    _write(repo / "newfile.txt", "ok\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "authorized build")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    proc = _run_validator(
        ["check-pr", base, head, BRANCH, "--repository", REPOSITORY,
         "--head-repository", "Evil-Fork/Rolling-High-Club"],
        cwd=repo, fixture=fixture)
    assert proc.returncode != 0
    assert "WRITE BOUNDARY REFUSED" in proc.stderr


def test_check_pr_missing_head_repository_fails_closed(tmp_path):
    repo, base = _init_repo(tmp_path)
    body = _make_johnny(base, contract=_make_contract(base))
    fixture = _fixture_dir(tmp_path, body)
    _write(repo / "newfile.txt", "ok\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "authorized build")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    proc = _run_validator(
        ["check-pr", base, head, BRANCH, "--repository", REPOSITORY],
        cwd=repo, fixture=fixture)
    assert proc.returncode != 0


# Finding 3: a malformed matching open JOHNNY must fail closed, not be skipped.

def test_discovery_malformed_matching_candidate_fails_closed(tmp_path, monkeypatch):
    repo, base = _init_repo(tmp_path)
    del repo
    valid = _make_johnny(base)
    malformed = _make_johnny(base, contract="{ this is not json }")
    fixture = _fixture_dir(tmp_path, valid, malformed)
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    with pytest.raises(vwb.BoundaryError):
        vwb.select_authority(
            vwb.discover_candidates(),
            {"repository": REPOSITORY, "branch": BRANCH},
            lambda sha: sha == base)


# Finding 4: local fence classifies the prospective index from Mission BASE.

def test_check_staged_cumulative_base_coherent(tmp_path, monkeypatch):
    repo, base = _init_repo(tmp_path)
    body = _make_johnny(base, contract=_make_contract(base, create=("newfile.txt",),
                                                      modify=()))
    fixture = _fixture_dir(tmp_path, body)
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    _install_guard(repo)

    _write(repo / "newfile.txt", "v1\n")
    _git(repo, "add", "newfile.txt")
    first = _git(repo, "commit", "-m", "create authorized", check=False)
    assert first.returncode == 0, first.stdout + first.stderr
    head1 = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # Second commit edits the same create-authorized path: cumulative
    # BASE->index is still an add and must stay authorized.
    _write(repo / "newfile.txt", "v2\n")
    _git(repo, "add", "newfile.txt")
    proc = _run_validator(["check-staged"], cwd=repo, fixture=fixture)
    assert proc.returncode == 0, proc.stderr

    second = _git(repo, "commit", "-m", "edit authorized", check=False)
    assert second.returncode == 0, second.stdout + second.stderr
    head2 = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # Local and server classify the same cumulative candidate identically.
    server = _run_validator(
        ["check-pr", base, head2, BRANCH, "--repository", REPOSITORY,
         "--head-repository", REPOSITORY],
        cwd=repo, fixture=fixture)
    assert server.returncode == 0, server.stderr
    assert head1 and head2


# Finding 5: preserve an effective inherited (global/system) hooksPath.

def _installer_env_with_global(tmp_path, hooks_path_value):
    global_cfg = tmp_path / "global.gitconfig"
    global_cfg.write_text(
        "[core]\n\thooksPath = %s\n" % hooks_path_value, encoding="utf-8")
    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = str(global_cfg)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def test_installer_refuses_inherited_global_hooks_path(tmp_path):
    repo, base = _init_repo(tmp_path)
    del base
    _stage_guard_files(repo)
    env = _installer_env_with_global(tmp_path, ".githooks-other")
    proc = subprocess.run([sys.executable, "scripts/install_write_guard.py"],
                          cwd=str(repo), capture_output=True, text=True,
                          env=env)
    assert proc.returncode != 0
    assert "INSTALL REFUSED" in proc.stderr
    local = _git(repo, "config", "--local", "--get", "core.hooksPath",
                 check=False)
    assert local.stdout.strip() == ""


def test_installer_refuses_inherited_global_same_value(tmp_path):
    repo, base = _init_repo(tmp_path)
    del base
    _stage_guard_files(repo)
    env = _installer_env_with_global(tmp_path, ".githooks")
    proc = subprocess.run([sys.executable, "scripts/install_write_guard.py"],
                          cwd=str(repo), capture_output=True, text=True,
                          env=env)
    # A non-local origin is refused conservatively rather than overridden.
    assert proc.returncode != 0
    assert "INSTALL REFUSED" in proc.stderr


# Finding 6: copy detection must expose an unauthorized unchanged source.

def test_check_staged_copy_from_unauthorized_source_fails(tmp_path):
    repo, base = _init_repo(tmp_path)
    body = _make_johnny(
        base, contract=_make_contract(base, create=("dest.txt",), modify=()))
    fixture = _fixture_dir(tmp_path, body)
    shutil.copy(repo / "docs" / "a.md", repo / "dest.txt")
    _git(repo, "add", "dest.txt")
    proc = _run_validator(["check-staged"], cwd=repo, fixture=fixture)
    assert proc.returncode != 0
    assert "WRITE BOUNDARY REFUSED" in proc.stderr

    # Same evidence path on the server side: an unchanged unauthorized source
    # copied into a create-authorized destination is refused there too.
    _git(repo, "commit", "-m", "copy attempt", "--no-verify")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    server = _run_validator(
        ["check-pr", base, head, BRANCH, "--repository", REPOSITORY,
         "--head-repository", REPOSITORY],
        cwd=repo, fixture=fixture)
    assert server.returncode != 0


# --------------------------------------------------------------------------
# PR #64 repair round 2 regressions (2 P1s + workflow cleanup)
# --------------------------------------------------------------------------

# Finding 1: duplicate/malformed/incomplete/conflicting identity on a candidate
# that targets this repository/branch must fail closed, not be silently skipped.

def test_parse_identity_duplicate_field_fails():
    body = (
        f"REPOSITORY: {REPOSITORY}\n"
        f"REPOSITORY: {REPOSITORY}\n"  # duplicate even when identical
        f"BUILD/HEAD BRANCH: {BRANCH}\n"
        f"BASE SHA: {'a' * 40}\n"
        f"MISSION IDENTITY: {MISSION}\n"
    )
    with pytest.raises(vwb.BoundaryError):
        vwb.parse_identity(body)


def test_parse_identity_empty_field_fails():
    body = (
        f"REPOSITORY: {REPOSITORY}\n"
        f"BUILD/HEAD BRANCH: {BRANCH}\n"
        "BASE SHA:\n"
        f"MISSION IDENTITY: {MISSION}\n"
    )
    with pytest.raises(vwb.BoundaryError):
        vwb.parse_identity(body)


def test_parse_identity_malformed_base_sha_fails():
    body = (
        f"REPOSITORY: {REPOSITORY}\n"
        f"BUILD/HEAD BRANCH: {BRANCH}\n"
        "BASE SHA: not-a-40-hex-sha\n"
        f"MISSION IDENTITY: {MISSION}\n"
    )
    with pytest.raises(vwb.BoundaryError):
        vwb.parse_identity(body)


def test_discovery_targeting_incomplete_identity_fails_closed(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    # Names this repo + branch but omits BASE SHA entirely: targeted yet
    # unbindable, so it must fail closed rather than be skipped.
    body = (
        "## JOHNNY CHECKPOINT\n\n"
        f"REPOSITORY: {REPOSITORY}\n"
        f"BUILD/HEAD BRANCH: {BRANCH}\n"
        f"MISSION IDENTITY: {MISSION}\n"
    )
    fixture = _fixture_dir(tmp_path, body)
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    with pytest.raises(vwb.BoundaryError):
        vwb.select_authority(
            vwb.discover_candidates(),
            {"repository": REPOSITORY, "branch": BRANCH},
            lambda sha: True)


def test_discovery_valid_plus_duplicate_identity_candidate_fails_closed(
        tmp_path, monkeypatch):
    repo, base = _init_repo(tmp_path)
    del repo
    valid = _make_johnny(base)
    duplicate = (
        "## JOHNNY CHECKPOINT\n\n"
        f"REPOSITORY: {REPOSITORY}\n"
        "REPOSITORY: Evil-Fork/Rolling-High-Club\n"  # conflicting duplicate
        f"BUILD/HEAD BRANCH: {BRANCH}\n"
        f"BASE SHA: {base}\n"
        f"MISSION IDENTITY: {MISSION}\n"
        f"<!-- RHC_SURFACE_BUDGET_V1\n{_make_contract(base)}\n-->\n"
    )
    fixture = _fixture_dir(tmp_path, valid, duplicate)
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    with pytest.raises(vwb.BoundaryError):
        vwb.select_authority(
            vwb.discover_candidates(),
            {"repository": REPOSITORY, "branch": BRANCH},
            lambda sha: sha == base)


def test_discovery_valid_plus_malformed_base_sha_candidate_fails_closed(
        tmp_path, monkeypatch):
    # Names this repo + branch but gives a malformed BASE SHA: targeted yet
    # unbindable, so it must fail closed rather than be skipped as a non-match.
    repo, base = _init_repo(tmp_path)
    del repo
    valid = _make_johnny(base)
    malformed = _make_johnny(base).replace(f"BASE SHA: {base}",
                                           "BASE SHA: not-a-40-hex-sha")
    fixture = _fixture_dir(tmp_path, valid, malformed)
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    with pytest.raises(vwb.BoundaryError):
        vwb.select_authority(
            vwb.discover_candidates(),
            {"repository": REPOSITORY, "branch": BRANCH},
            lambda sha: sha == base)


def test_candidate_targeting_other_repo_with_bad_identity_is_skipped(
        tmp_path, monkeypatch):
    # A malformed candidate clearly aimed elsewhere stays ignorable, so a
    # single valid authority is still selectable.
    repo, base = _init_repo(tmp_path)
    del repo
    valid = _make_johnny(base)
    elsewhere = (
        "## JOHNNY CHECKPOINT\n\n"
        f"REPOSITORY: {REPOSITORY}\n"
        f"BUILD/HEAD BRANCH: some/other-branch\n"
        f"MISSION IDENTITY: {MISSION}\n"
    )
    fixture = _fixture_dir(tmp_path, valid, elsewhere)
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    authority = vwb.select_authority(
        vwb.discover_candidates(),
        {"repository": REPOSITORY, "branch": BRANCH},
        lambda sha: sha == base)
    assert authority["contract"]["base_sha"] == base


# Finding 2: duplicate JSON keys must fail closed at every nesting depth.

def test_contract_duplicate_top_level_key_fails():
    base = "a" * 40
    raw = (
        '{"surface_budget_version":1,'
        f'"repository":"{REPOSITORY}","repository":"Evil-Fork/Rolling-High-Club",'
        f'"branch":"{BRANCH}","base_sha":"{base}",'
        f'"mission":"{MISSION}",'
        '"allow":{"create":[],"modify":[],"delete":[]}}'
    )
    with pytest.raises(vwb.BoundaryError):
        vwb.parse_contract(raw)


def test_contract_duplicate_nested_key_fails():
    base = "a" * 40
    raw = (
        '{"surface_budget_version":1,'
        f'"repository":"{REPOSITORY}",'
        f'"branch":"{BRANCH}","base_sha":"{base}",'
        f'"mission":"{MISSION}",'
        '"allow":{"create":[],"create":[],"modify":[],"delete":[]}}'
    )
    with pytest.raises(vwb.BoundaryError):
        vwb.parse_contract(raw)


# Cleanup: the trusted validator path uses only the standard library, so the
# workflow must not install the repository requirements set.

def test_trusted_workflow_installs_no_dependencies():
    workflow = (ROOT / ".github" / "workflows" /
                "hard-write-boundary.yml").read_text(encoding="utf-8")
    assert "requirements.txt" not in workflow
    assert "pip install" not in workflow


# --------------------------------------------------------------------------
# Local semantic review round 4 regressions (3 P2 findings)
# --------------------------------------------------------------------------

# Finding 1: CRLF-terminated JOHNNY identity lines must still fail closed on
# malformed/duplicate targeting instead of being treated as unrelated.

def test_discovery_valid_plus_crlf_duplicate_candidate_fails_closed(
        tmp_path, monkeypatch):
    repo, base = _init_repo(tmp_path)
    del repo
    valid = _make_johnny(base)
    crlf_duplicate = valid.replace("\n", "\r\n")
    fixture = _fixture_dir(tmp_path, valid, crlf_duplicate)
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    with pytest.raises(vwb.BoundaryError):
        vwb.select_authority(
            vwb.discover_candidates(),
            {"repository": REPOSITORY, "branch": BRANCH},
            lambda sha: sha == base)


def test_discovery_valid_plus_crlf_malformed_base_candidate_fails_closed(
        tmp_path, monkeypatch):
    repo, base = _init_repo(tmp_path)
    del repo
    valid = _make_johnny(base)
    crlf_malformed = valid.replace(f"BASE SHA: {base}",
                                   "BASE SHA: not-a-40-hex-sha")
    crlf_malformed = crlf_malformed.replace("\n", "\r\n")
    fixture = _fixture_dir(tmp_path, valid, crlf_malformed)
    monkeypatch.setenv("RHC_JOHNNY_FIXTURE", fixture)
    with pytest.raises(vwb.BoundaryError):
        vwb.select_authority(
            vwb.discover_candidates(),
            {"repository": REPOSITORY, "branch": BRANCH},
            lambda sha: sha == base)


def test_crlf_candidate_targeting_this_repo_branch_is_detected():
    base = "a" * 40
    body = _make_johnny(base).replace("\n", "\r\n")
    normalized = vwb._normalize_newlines(body)
    assert vwb.targets_repo_branch(
        normalized, {"repository": REPOSITORY, "branch": BRANCH})


def test_crlf_valid_candidate_alone_still_parses():
    base = "a" * 40
    body = _make_johnny(base).replace("\n", "\r\n")
    identity = vwb.parse_identity(vwb._normalize_newlines(body))
    assert identity["base_sha"] == base


# Finding 2: installing core.hooksPath must not silently disable an unrelated
# existing hook other than pre-commit (e.g. commit-msg, pre-push).

def test_installer_refuses_unrelated_other_hook_kind(tmp_path):
    repo, base = _init_repo(tmp_path)
    del base
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "commit-msg").write_text(
        "#!/bin/sh\necho unrelated commit-msg\n", encoding="utf-8")
    _stage_guard_files(repo)
    proc = subprocess.run([sys.executable, "scripts/install_write_guard.py"],
                          cwd=str(repo), capture_output=True, text=True)
    assert proc.returncode != 0
    assert "INSTALL REFUSED" in proc.stderr
    local = _git(repo, "config", "--local", "--get", "core.hooksPath",
                 check=False)
    assert local.stdout.strip() == ""


def test_installer_ignores_sample_hooks(tmp_path):
    repo, base = _init_repo(tmp_path)
    del base
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "pre-push.sample").write_text(
        "#!/bin/sh\n# sample only\n", encoding="utf-8")
    _install_guard(repo)
    active = _git(repo, "config", "--local", "--get", "core.hooksPath")
    assert active.stdout.strip() == ".githooks"


# Finding 3: existing-hook detection must resolve the real hooks directory
# through Git so a linked worktree (where `.git` is a pointer file) is not
# blind to an unrelated hook living in the shared common Git directory.

def test_installer_refuses_unrelated_hook_from_linked_worktree(tmp_path):
    repo, base = _init_repo(tmp_path)
    del base
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "pre-push").write_text(
        "#!/bin/sh\necho unrelated pre-push\n", encoding="utf-8")

    worktree_parent = tmp_path / "wt"
    _git(repo, "worktree", "add", "-b", "wt-branch", str(worktree_parent))
    assert (worktree_parent / ".git").is_file(), (
        "expected a linked-worktree .git pointer file, not a directory")

    _stage_guard_files(worktree_parent)
    proc = subprocess.run([sys.executable, "scripts/install_write_guard.py"],
                          cwd=str(worktree_parent), capture_output=True,
                          text=True)
    assert proc.returncode != 0
    assert "INSTALL REFUSED" in proc.stderr
    local = _git(worktree_parent, "config", "--local", "--get",
                 "core.hooksPath", check=False)
    assert local.stdout.strip() == ""


# --------------------------------------------------------------------------
# HWB-03 fixed SAVE repository-history lane
# --------------------------------------------------------------------------

SAVE_BRANCH = "save/day-001-final"


def _init_save_repo(tmp_path: Path, branch: str = SAVE_BRANCH):
    repo = tmp_path / "save_repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "RHC Test")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "remote", "add", "origin",
         f"https://github.com/{REPOSITORY}.git")
    _write(repo / "canon" / "days" / "DAY_TEMPLATE.md", "template\n")
    _write(repo / "canon" / "days" / "day_100.md", "finalized existing day\n")
    _write(repo / "canon" / "timeline.md", "timeline\n")
    _write(repo / "scripts" / "tool.py", "print('tool')\n")
    _write(repo / "README.md", "seed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-b", branch)
    return repo, base_sha


def _save_check_pr(repo, base, head, branch=SAVE_BRANCH):
    return _run_validator(
        ["check-pr", base, head, branch, "--repository", REPOSITORY,
         "--head-repository", REPOSITORY],
        cwd=repo, fixture=None)


def test_is_save_branch_namespace():
    assert vwb.is_save_branch("save/day-001-final")
    assert not vwb.is_save_branch("save")
    assert not vwb.is_save_branch("saves/day-001-final")
    assert not vwb.is_save_branch("hardening/hwb-03-save-repository-history-authority")
    assert not vwb.is_save_branch("feature/save/day-001")


def test_grade_save_exactly_one_day_passes():
    assert vwb.grade_save_changes(
        [("A", ["canon/days/day_001.md"], "000000", "100644")])


@pytest.mark.parametrize("day_path", [
    "canon/days/day_001.md",       # leading zeroes permitted
    "canon/days/day_999.md",
    "canon/days/day_1000.md",      # no three-digit ceiling
    "canon/days/day_12547.md",     # uncapped archive identity
    "canon/days/day_000001.md",
])
def test_is_save_day_path_positive_identities_pass(day_path):
    assert vwb.is_save_day_path(day_path)
    assert vwb.grade_save_changes([("A", [day_path], "000000", "100644")])


@pytest.mark.parametrize("bad_path", [
    "canon/days/day_000.md",       # zero identity
    "canon/days/day_0.md",
    "canon/days/day_00.md",
    "canon/days/day_-1.md",        # signed form
    "canon/days/day_+1.md",
    "canon/days/day_1a.md",        # non-decimal
    "canon/days/day_.md",          # no digits
    "canon/days/day_1.md.bak",
    "canon/days/day_1.txt",
    "canon/days/notes.md",
    "canon/days/day_100.md.bak",
])
def test_is_save_day_path_malformed_identities_fail(bad_path):
    assert not vwb.is_save_day_path(bad_path)


# Python 3.12+ bounds `int()` decimal-string conversion at 4,300 digits, but
# the declared HWB-03 identity is unbounded, so positivity must not depend on
# integer conversion. A legal identity wider than that limit must still PASS,
# and an all-zero identity of the same width must still FAIL.
_OVER_INT_LIMIT_DIGITS = 4301


def test_is_save_day_path_identity_beyond_int_limit_passes():
    oversized = "1" + "0" * (_OVER_INT_LIMIT_DIGITS - 1)
    day_path = f"canon/days/day_{oversized}.md"
    assert len(oversized) > 4300
    assert vwb.is_save_day_path(day_path)
    assert vwb.grade_save_changes([("A", [day_path], "000000", "100644")])


def test_is_save_day_path_all_zero_identity_beyond_int_limit_fails():
    oversized = "0" * _OVER_INT_LIMIT_DIGITS
    day_path = f"canon/days/day_{oversized}.md"
    assert len(oversized) > 4300
    assert not vwb.is_save_day_path(day_path)
    with pytest.raises(vwb.BoundaryError):
        vwb.grade_save_changes([("A", [day_path], "000000", "100644")])



def test_grade_save_empty_candidate_fails():
    with pytest.raises(vwb.BoundaryError):
        vwb.grade_save_changes([])


def test_grade_save_day_plus_timeline_passes():
    assert vwb.grade_save_changes([
        ("A", ["canon/days/day_001.md"], "000000", "100644"),
        ("M", ["canon/timeline.md"], "100644", "100644"),
    ])
    assert vwb.grade_save_changes([
        ("C", ["canon/days/DAY_TEMPLATE.md", "canon/days/day_001.md"],
         "100644", "100644"),
        ("A", ["canon/timeline.md"], "000000", "100644"),
    ])


@pytest.mark.parametrize("entries", [
    [("M", ["canon/timeline.md"], "100644", "100644")],  # timeline only
    [("A", ["canon/days/day_001.md"], "000000", "100644"),
     ("A", ["canon/days/day_002.md"], "000000", "100644")],  # two days
    [("A", ["canon/days/notes.md"], "000000", "100644")],  # invalid day name
    [("A", ["canon/days/day_000.md"], "000000", "100644")],  # zero identity add
    [("A", ["canon/days/day_0.md"], "000000", "100644")],  # zero identity add
    [("A", ["canon/days/day_-1.md"], "000000", "100644")],  # signed form
    [("A", ["canon/days/DAY_TEMPLATE.md"], "000000", "100644")],
    [("M", ["canon/days/day_100.md"], "100644", "100644")],  # mutate history
    [("D", ["canon/days/day_100.md"], "100644", "000000")],  # delete history
    [("D", ["canon/timeline.md"], "100644", "000000")],  # delete timeline
    [("A", ["scripts/evil.py"], "000000", "100644")],  # engineering path
    [("M", ["scripts/tool.py"], "100644", "100644")],  # runtime/tool path
    [("A", ["canon/other.md"], "000000", "100644")],  # unrelated canon path
    [("R100", ["scripts/tool.py", "canon/days/day_001.md"],
      "100644", "100644")],  # rename into allowed surface
    [("C100", ["canon/days/day_100.md", "canon/days/day_001.md"],
      "100644", "100644")],  # copy existing history forward
    [("T", ["canon/days/day_100.md"], "100644", "120000")],  # type change
    [("A", ["canon/days/day_001.md"], "000000", "120000")],  # symlink at path
    [("A", ["canon/days/day_001.md"], "000000", "160000")],  # gitlink at path
])
def test_grade_save_forbidden_candidates_fail(entries):
    with pytest.raises(vwb.BoundaryError):
        vwb.grade_save_changes(entries)


def test_save_staged_add_day_passes(tmp_path):
    repo, base = _init_save_repo(tmp_path)
    del base
    _write(repo / "canon" / "days" / "day_001.md", "filled day\n")
    _git(repo, "add", "-A")
    proc = _run_validator(["check-staged"], cwd=repo, fixture=None)
    assert proc.returncode == 0, proc.stderr


def test_save_staged_day_plus_timeline_passes(tmp_path):
    repo, base = _init_save_repo(tmp_path)
    del base
    _write(repo / "canon" / "days" / "day_001.md", "filled day\n")
    _write(repo / "canon" / "timeline.md", "timeline\n- day 1\n")
    _git(repo, "add", "-A")
    proc = _run_validator(["check-staged"], cwd=repo, fixture=None)
    assert proc.returncode == 0, proc.stderr


def test_save_staged_template_copy_into_new_day_passes(tmp_path):
    repo, base = _init_save_repo(tmp_path)
    del base
    shutil.copy(repo / "canon" / "days" / "DAY_TEMPLATE.md",
                repo / "canon" / "days" / "day_001.md")
    _git(repo, "add", "-A")
    proc = _run_validator(["check-staged"], cwd=repo, fixture=None)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("mutation", [
    "timeline_only", "two_days", "invalid_day", "template_add",
    "mutate_history", "delete_history", "delete_timeline", "engineering",
    "runtime_tool", "unrelated_canon", "rename_into_allowed",
    "copy_existing_history", "empty_candidate", "zero_identity_day",
])
def test_save_staged_forbidden_candidates_fail(tmp_path, mutation):
    repo, base = _init_save_repo(tmp_path)
    del base
    if mutation == "timeline_only":
        _write(repo / "canon" / "timeline.md", "timeline\n- orphan\n")
    elif mutation == "two_days":
        _write(repo / "canon" / "days" / "day_001.md", "a\n")
        _write(repo / "canon" / "days" / "day_002.md", "b\n")
    elif mutation == "invalid_day":
        _write(repo / "canon" / "days" / "notes.md", "not a day\n")
    elif mutation == "zero_identity_day":
        _write(repo / "canon" / "days" / "day_000.md", "not a real day\n")
    elif mutation == "template_add":
        _write(repo / "canon" / "days" / "DAY_TEMPLATE.md", "changed\n")
    elif mutation == "mutate_history":
        _write(repo / "canon" / "days" / "day_100.md", "rewritten\n")
    elif mutation == "delete_history":
        _git(repo, "rm", "canon/days/day_100.md")
    elif mutation == "delete_timeline":
        _git(repo, "rm", "canon/timeline.md")
    elif mutation == "engineering":
        _write(repo / "tests" / "test_evil.py", "def test_x():\n    pass\n")
    elif mutation == "runtime_tool":
        _write(repo / "scripts" / "tool.py", "print('changed')\n")
    elif mutation == "unrelated_canon":
        _write(repo / "canon" / "other.md", "other\n")
    elif mutation == "rename_into_allowed":
        _git(repo, "mv", "scripts/tool.py", "canon/days/day_001.md")
    elif mutation == "copy_existing_history":
        shutil.copy(repo / "canon" / "days" / "day_100.md",
                    repo / "canon" / "days" / "day_001.md")
    elif mutation == "empty_candidate":
        pass  # no change at all: a normal SAVE must add one finalized day
    _git(repo, "add", "-A")
    proc = _run_validator(["check-staged"], cwd=repo, fixture=None)
    assert proc.returncode != 0
    assert "WRITE BOUNDARY REFUSED" in proc.stderr


@pytest.mark.parametrize("day", ["day_999", "day_1000", "day_12547"])
def test_save_staged_large_archive_identity_passes(tmp_path, day):
    repo, base = _init_save_repo(tmp_path)
    del base
    _write(repo / "canon" / "days" / f"{day}.md", "filled day\n")
    _git(repo, "add", "-A")
    proc = _run_validator(["check-staged"], cwd=repo, fixture=None)
    assert proc.returncode == 0, proc.stderr


def test_save_pr_empty_candidate_fails(tmp_path):
    repo, base = _init_save_repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    server = _save_check_pr(repo, base, head)
    assert server.returncode != 0
    assert "WRITE BOUNDARY REFUSED" in server.stderr


def test_save_pr_zero_identity_day_fails(tmp_path):
    repo, base = _init_save_repo(tmp_path)
    _write(repo / "canon" / "days" / "day_000.md", "zero\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "zero day", "--no-verify")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    server = _save_check_pr(repo, base, head)
    assert server.returncode != 0
    assert "WRITE BOUNDARY REFUSED" in server.stderr


def test_save_staged_symlink_at_allowed_path_fails(tmp_path):
    repo, base = _init_save_repo(tmp_path)
    del base
    target = repo / "symtarget.txt"
    _write(target, "target blob\n")
    sha = _git(repo, "hash-object", "-w", str(target)).stdout.strip()
    _git(repo, "update-index", "--add", "--cacheinfo",
         f"120000,{sha},canon/days/day_001.md")
    proc = _run_validator(["check-staged"], cwd=repo, fixture=None)
    assert proc.returncode != 0
    assert "WRITE BOUNDARY REFUSED" in proc.stderr


def test_non_save_branch_does_not_receive_save_authority(tmp_path):
    repo, base = _init_save_repo(tmp_path, branch="feature/not-a-save-branch")
    del base
    fixture = _fixture_dir(tmp_path)  # no JOHNNY authority at all
    _write(repo / "canon" / "days" / "day_001.md", "filled day\n")
    _git(repo, "add", "-A")
    # BUILD lane needs a JOHNNY; none exists, so it must fail closed rather
    # than inherit the fixed SAVE contract from the candidate shape.
    proc = _run_validator(["check-staged"], cwd=repo, fixture=fixture)
    assert proc.returncode != 0
    assert "WRITE BOUNDARY REFUSED" in proc.stderr


def test_save_local_server_parity_pass(tmp_path):
    repo, base = _init_save_repo(tmp_path)
    _write(repo / "canon" / "days" / "day_001.md", "filled day\n")
    _write(repo / "canon" / "timeline.md", "timeline\n- day 1\n")
    _git(repo, "add", "-A")
    local = _run_validator(["check-staged"], cwd=repo, fixture=None)
    assert local.returncode == 0, local.stderr
    _git(repo, "commit", "-m", "save day 1")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    server = _save_check_pr(repo, base, head)
    assert server.returncode == 0, server.stderr


def test_save_local_server_parity_fail(tmp_path):
    repo, base = _init_save_repo(tmp_path)
    _write(repo / "scripts" / "evil.py", "print('evil')\n")
    _git(repo, "add", "-A")
    local = _run_validator(["check-staged"], cwd=repo, fixture=None)
    assert local.returncode != 0
    _git(repo, "commit", "-m", "unauthorized save", "--no-verify")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    server = _save_check_pr(repo, base, head)
    assert server.returncode != 0
    assert "WRITE BOUNDARY REFUSED" in server.stderr


def test_save_pr_two_days_fails(tmp_path):
    repo, base = _init_save_repo(tmp_path)
    _write(repo / "canon" / "days" / "day_001.md", "a\n")
    _write(repo / "canon" / "days" / "day_002.md", "b\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "two days", "--no-verify")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    server = _save_check_pr(repo, base, head)
    assert server.returncode != 0
    assert "WRITE BOUNDARY REFUSED" in server.stderr


def test_save_pr_fork_head_repository_fails_closed(tmp_path):
    repo, base = _init_save_repo(tmp_path)
    _write(repo / "canon" / "days" / "day_001.md", "a\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "save day 1", "--no-verify")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    proc = _run_validator(
        ["check-pr", base, head, SAVE_BRANCH, "--repository", REPOSITORY,
         "--head-repository", "Evil-Fork/Rolling-High-Club"],
        cwd=repo, fixture=None)
    assert proc.returncode != 0
    assert "WRITE BOUNDARY REFUSED" in proc.stderr


def test_build_branch_does_not_receive_save_authority(tmp_path):
    repo, base = _init_repo(tmp_path)
    fixture = _fixture_dir(tmp_path, _make_johnny(base))
    _write(repo / "canon" / "days" / "day_001.md", "not authorized\n")
    _git(repo, "add", "-A")
    # The BUILD JOHNNY does not authorize this canon path; the fixed SAVE
    # policy must not leak into a non-save branch.
    proc = _run_validator(["check-staged"], cwd=repo, fixture=fixture)
    assert proc.returncode != 0
    assert "WRITE BOUNDARY REFUSED" in proc.stderr
