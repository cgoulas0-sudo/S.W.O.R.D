"""POST-EV2-6 proof: broad discovery, explicit admission, bounded hydration."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import story_retrieval as sr  # noqa: E402


def _write(base: Path, rel: str, text: str) -> Path:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _corpus(base: Path):
    _write(
        base,
        "canon/public.md",
        "# Public\n"
        "**Visibility:** NON_META\n"
        "Gork and Larloch are shared history.\n",
    )
    _write(
        base,
        "canon/hidden.md",
        "# Hidden\n"
        "**Visibility:** META\n"
        "Gork serves Larloch in secret.\n",
    )
    _write(base, "planned/plan.md", "# Plan\nGork may betray Larloch.\n")
    _write(base, "brainstorm/idea.md", "# Idea\nGork vs Larloch twist.\n")


def test_real_canary_discovers_multiple_real_sources_for_dm():
    manifest = sr.build_manifest(ROOT, git_head="deadbeef")
    receipt = sr.query_manifest(
        manifest, ROOT, "gork larloch", limit=50, profile=sr.DM_PROFILE
    )
    paths = {hit["path"] for hit in receipt["results"]}
    assert {
        "villain/gork.md",
        "characters/mugen.md",
        "inventory/weapons/vampire.md",
    } <= paths


def test_strok_ioulaum_is_honest_zero():
    manifest = sr.build_manifest(ROOT, git_head="deadbeef")
    receipt = sr.query_manifest(
        manifest, ROOT, "strok ioulaum", limit=50, profile=sr.DM_PROFILE
    )
    assert receipt["results"] == []
    assert receipt["complete"] is True
    assert receipt["absence_is_proof"] is False


def test_source_classes_and_authority_are_preserved(tmp_path):
    _corpus(tmp_path)
    manifest = sr.build_manifest(tmp_path, git_head=None)
    receipt = sr.query_manifest(
        manifest, tmp_path, "gork larloch", limit=50, profile=sr.DM_PROFILE
    )
    by_path = {hit["path"]: hit for hit in receipt["results"]}

    assert by_path["canon/public.md"]["source_class"] == "CANON"
    assert by_path["canon/public.md"]["authority"] == "canon"
    assert by_path["planned/plan.md"]["source_class"] == "DM_ONLY_PLAN"
    assert by_path["planned/plan.md"]["authority"] == "non_canon"


def test_dm_profile_can_hydrate_meta_and_non_canon(tmp_path):
    _corpus(tmp_path)
    manifest = sr.build_manifest(tmp_path, git_head=None)
    receipt = sr.query_manifest(
        manifest, tmp_path, "gork larloch", profile=sr.DM_PROFILE
    )
    paths = {hit["path"] for hit in receipt["results"]}
    assert "canon/hidden.md" in paths
    assert "planned/plan.md" in paths


def test_authoritative_profile_only_admits_unambiguous_non_meta(tmp_path):
    _corpus(tmp_path)
    manifest = sr.build_manifest(tmp_path, git_head=None)
    receipt = sr.query_manifest(
        manifest,
        tmp_path,
        "gork larloch",
        profile=sr.AUTHORITATIVE_PROFILE,
    )
    assert {hit["path"] for hit in receipt["results"]} == {"canon/public.md"}
    assert receipt["results"][0]["visibility_evidence"][
        "player_safe_whole_source"
    ] is True


def test_mixed_markdown_is_searchable_for_dm_but_not_player_hydratable(tmp_path):
    _write(
        tmp_path,
        "canon/mixed.md",
        "# Mixed\n"
        "**Visibility:** NON_META\n"
        "publictoken is visible.\n"
        "## Hidden\n"
        "- **Visibility:** META\n"
        "  secrettoken is hidden.\n",
    )
    manifest = sr.build_manifest(tmp_path, git_head=None)

    dm = sr.query_manifest(
        manifest, tmp_path, "secrettoken", profile=sr.DM_PROFILE
    )
    assert {hit["path"] for hit in dm["results"]} == {"canon/mixed.md"}

    authoritative = sr.query_manifest(
        manifest,
        tmp_path,
        "publictoken",
        profile=sr.AUTHORITATIVE_PROFILE,
    )
    assert authoritative["results"] == []


def test_later_non_meta_marker_does_not_retroactively_admit_markdown(tmp_path):
    _write(
        tmp_path,
        "canon/preface.md",
        "# Preface\n"
        "prefacetoken is unclassified.\n"
        "## Public\n"
        "**Visibility:** NON_META\n"
        "publictoken is visible.\n",
    )
    manifest = sr.build_manifest(tmp_path, git_head=None)
    source = manifest["sources"][0]
    assert source["visibility_evidence"]["mode"] == "ambiguous"
    assert source["visibility_evidence"]["player_safe_whole_source"] is False


def test_nested_mixed_json_is_refused_for_authoritative_profile(tmp_path):
    _write(
        tmp_path,
        "knowledge/mixed.json",
        json.dumps(
            {
                "default_visibility": "non_meta",
                "public": "publicjson",
                "children": [
                    {"visibility": "meta", "secret": "jsonsecret"}
                ],
            }
        ),
    )
    manifest = sr.build_manifest(tmp_path, git_head=None)

    dm = sr.query_manifest(
        manifest, tmp_path, "jsonsecret", profile=sr.DM_PROFILE
    )
    assert dm["results"]

    authoritative = sr.query_manifest(
        manifest,
        tmp_path,
        "publicjson",
        profile=sr.AUTHORITATIVE_PROFILE,
    )
    assert authoritative["results"] == []


def test_whole_json_non_meta_can_hydrate(tmp_path):
    _write(
        tmp_path,
        "knowledge/public.json",
        json.dumps(
            {
                "default_visibility": "non_meta",
                "facts": [{"statement": "publicjson"}],
            }
        ),
    )
    manifest = sr.build_manifest(tmp_path, git_head=None)
    receipt = sr.query_manifest(
        manifest,
        tmp_path,
        "publicjson",
        profile=sr.AUTHORITATIVE_PROFILE,
    )
    assert {hit["path"] for hit in receipt["results"]} == {
        "knowledge/public.json"
    }


def test_conflicting_root_visibility_keys_are_refused(tmp_path):
    _write(
        tmp_path,
        "knowledge/conflict.json",
        json.dumps(
            {
                "visibility": "non_meta",
                "default_visibility": "meta",
                "public": "publicjson",
            }
        ),
    )
    manifest = sr.build_manifest(tmp_path, git_head=None)
    source = manifest["sources"][0]
    assert source["visibility_evidence"]["mode"] == "meta_or_mixed"
    assert source["visibility_evidence"]["player_safe_whole_source"] is False

    receipt = sr.query_manifest(
        manifest,
        tmp_path,
        "publicjson",
        profile=sr.AUTHORITATIVE_PROFILE,
    )
    assert receipt["results"] == []


def test_nested_default_visibility_meta_is_refused(tmp_path):
    _write(
        tmp_path,
        "knowledge/nested_default.json",
        json.dumps(
            {
                "visibility": "non_meta",
                "public": "publicjson",
                "children": [
                    {"default_visibility": "meta", "secret": "jsonsecret"}
                ],
            }
        ),
    )
    manifest = sr.build_manifest(tmp_path, git_head=None)
    source = manifest["sources"][0]
    assert source["visibility_evidence"]["mode"] == "meta_or_mixed"
    assert source["visibility_evidence"]["player_safe_whole_source"] is False

    authoritative = sr.query_manifest(
        manifest,
        tmp_path,
        "publicjson",
        profile=sr.AUTHORITATIVE_PROFILE,
    )
    assert authoritative["results"] == []

    dm = sr.query_manifest(
        manifest, tmp_path, "jsonsecret", profile=sr.DM_PROFILE
    )
    assert {hit["path"] for hit in dm["results"]} == {
        "knowledge/nested_default.json"
    }


def test_nested_default_visibility_non_meta_stays_admitted(tmp_path):
    _write(
        tmp_path,
        "knowledge/consistent_default.json",
        json.dumps(
            {
                "default_visibility": "non_meta",
                "children": [
                    {"default_visibility": "non_meta", "public": "publicjson"}
                ],
            }
        ),
    )
    manifest = sr.build_manifest(tmp_path, git_head=None)
    receipt = sr.query_manifest(
        manifest,
        tmp_path,
        "publicjson",
        profile=sr.AUTHORITATIVE_PROFILE,
    )
    assert {hit["path"] for hit in receipt["results"]} == {
        "knowledge/consistent_default.json"
    }


def test_non_canon_stays_dm_only_even_if_marked_non_meta(tmp_path):
    _write(
        tmp_path,
        "planned/public_plan.md",
        "# Plan\n**Visibility:** NON_META\nplantoken\n",
    )
    manifest = sr.build_manifest(tmp_path, git_head=None)
    receipt = sr.query_manifest(
        manifest,
        tmp_path,
        "plantoken",
        profile=sr.AUTHORITATIVE_PROFILE,
    )
    assert receipt["results"] == []


def test_edit_add_remove_marks_manifest_stale(tmp_path):
    _corpus(tmp_path)
    manifest = sr.build_manifest(tmp_path, git_head=None)
    assert sr.check_freshness(manifest, tmp_path)["status"] == "fresh"

    _write(tmp_path, "canon/public.md", "# Changed\n")
    changed = sr.check_freshness(manifest, tmp_path)
    assert changed["status"] == "stale"
    assert "canon/public.md" in changed["changed_paths"]

    rebuilt = sr.build_manifest(tmp_path, git_head=None)
    _write(tmp_path, "canon/new.md", "# New\n")
    added = sr.check_freshness(rebuilt, tmp_path)
    assert "canon/new.md" in added["added_paths"]

    rebuilt2 = sr.build_manifest(tmp_path, git_head=None)
    (tmp_path / "canon" / "new.md").unlink()
    removed = sr.check_freshness(rebuilt2, tmp_path)
    assert "canon/new.md" in removed["removed_paths"]


def test_unrelated_engineering_change_does_not_stale_manifest(tmp_path):
    _corpus(tmp_path)
    manifest = sr.build_manifest(tmp_path, git_head=None)
    _write(tmp_path, "docs/engineering.md", "# change\n")
    assert sr.check_freshness(manifest, tmp_path)["status"] == "fresh"


def test_manifest_tamper_cannot_self_certify_against_current_sources(tmp_path):
    _corpus(tmp_path)
    manifest = sr.build_manifest(tmp_path, git_head=None)

    tampered = json.loads(json.dumps(manifest))
    tampered["sources"][0]["visibility_evidence"][
        "player_safe_whole_source"
    ] = True
    tampered["fingerprint"] = sr.compute_fingerprint(tampered["sources"])

    freshness = sr.check_freshness(tampered, tmp_path)
    assert freshness["status"] == "stale"


def test_mid_query_digest_change_fails_closed(tmp_path, monkeypatch):
    source = _write(
        tmp_path,
        "canon/public.md",
        "# Public\n**Visibility:** NON_META\nracetoken\n",
    )
    manifest = sr.build_manifest(tmp_path, git_head=None)
    original = sr.check_freshness

    def fresh_then_change(manifest_value, base_dir):
        receipt = original(manifest_value, base_dir)
        source.write_text(
            "# Public\n**Visibility:** NON_META\nracetoken changed\n",
            encoding="utf-8",
        )
        return receipt

    monkeypatch.setattr(sr, "check_freshness", fresh_then_change)
    receipt = sr.query_manifest(
        manifest,
        tmp_path,
        "racetoken",
        profile=sr.AUTHORITATIVE_PROFILE,
    )
    assert receipt["complete"] is False
    assert receipt["results"] == []
    assert "canon/public.md" in receipt["freshness"][
        "hydration_mismatch_paths"
    ]


def test_query_is_bounded_and_deterministic(tmp_path):
    for index in range(8):
        _write(
            tmp_path,
            f"canon/item_{index}.md",
            "# Item\n**Visibility:** NON_META\ngork larloch\n",
        )
    manifest = sr.build_manifest(tmp_path, git_head=None)
    one = sr.query_manifest(
        manifest, tmp_path, "gork larloch", limit=3, profile=sr.DM_PROFILE
    )
    two = sr.query_manifest(
        manifest, tmp_path, "gork larloch", limit=3, profile=sr.DM_PROFILE
    )
    assert one == two
    assert len(one["results"]) == 3
    assert one["truncated"] is True


def test_live_mutable_and_engineering_files_are_not_indexed(tmp_path):
    _corpus(tmp_path)
    _write(tmp_path, "state/live_status.json", "{}")
    _write(tmp_path, "docs/engineering.md", "# docs\n")
    _write(tmp_path, "scripts/tool.py", "print('x')\n")
    manifest = sr.build_manifest(tmp_path, git_head=None)
    paths = {source["path"] for source in manifest["sources"]}
    assert not any(path.startswith("state/") for path in paths)
    assert not any(path.startswith("docs/") for path in paths)
    assert not any(path.startswith("scripts/") for path in paths)


def test_missing_manifest_is_incomplete(tmp_path):
    receipt = sr.query_receipt(
        tmp_path / "missing.json",
        tmp_path,
        "anything",
        profile=sr.DM_PROFILE,
    )
    assert receipt["complete"] is False
    assert receipt["results"] == []
    assert receipt["absence_is_proof"] is False


def test_no_network_or_runtime_mutation_surface():
    script = (ROOT / "scripts" / "story_retrieval.py").read_text(
        encoding="utf-8"
    )
    for token in (
        "requests",
        "urllib",
        "socket",
        "CREATE FUNCTION",
        "stage_campaign",
        "publish_campaign",
    ):
        assert token not in script


def test_no_generated_manifest_committed():
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.splitlines()
    assert not any("story_retrieval_manifest.json" in path for path in tracked)
