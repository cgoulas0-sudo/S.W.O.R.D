"""Static contract suite for the RHC Dropgate + Continuity Restoration.

Verifies the repository-side Proof Matrix: the universal Dropgate lanes, the
mandatory Continuity Gate, the JOHNNY template extensions, the review
scope-classification law, lane separation, and the milestone-level continuity
ledgers. These are documentation/workflow contracts, so the suite reads the
control files as text and asserts the required properties.

Policy note: RHC deliberately does NOT enforce a per-engineering-PR ledger gate.
The ledgers are curated milestone / patch-series continuity, published at
coherent closeout — not per-PR execution diaries. Proofs 9 and 16 assert that
the rejected per-PR enforcement (and its `validate_change_ledger` validator) is
absent, and that the milestone publication semantics are documented.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


# --- Proof 1: AGENT_HANDOFF routes all five lanes explicitly ------------------

def test_dropgate_declares_all_five_lanes():
    text = _read("AGENT_HANDOFF.md")
    assert "Repository Dropgate" in text
    for lane in ("BUILD", "PLAY", "SAVE", "READ", "UNKNOWN"):
        assert lane in text, f"Dropgate missing lane {lane}"
    assert "CONFLICT" in text


# --- Proof 2: UNKNOWN/CONFLICT fails closed, never defaults to BUILD ----------

def test_unknown_conflict_stops_and_asks():
    text = _read("AGENT_HANDOFF.md").upper()
    assert "STOP" in text and "ASK" in text
    assert "DO NOT DEFAULT TO BUILD" in text


# --- Proof 3: vendor stubs route through the universal Dropgate ---------------

def test_vendor_stubs_point_to_dropgate():
    for stub in ("AGENTS.md", "CLAUDE.md"):
        assert "AGENT_HANDOFF.md" in _read(stub), f"{stub} must route to the Dropgate"


# --- Proof 4: BUILD routes to BUILDER.md + prepared JOHNNY, not Asana/chat ----

def test_build_lane_routes_to_builder_and_johnny_not_asana():
    text = _read("AGENT_HANDOFF.md")
    assert "BUILDER.md" in text and "ORCHESTRATOR.md" in text
    assert "JOHNNY" in text
    assert "never reconstructs the Mission from Asana or chat" in text


# --- Proof 5: BUILDER has a mandatory Continuity Gate before implementation ---

def test_builder_has_mandatory_continuity_gate():
    text = _read("BUILDER.md")
    assert "Mandatory Continuity Gate" in text
    assert "separate mandatory input species" in text
    assert text.index("Mandatory Continuity Gate") < text.index("Required repository truth")
    for anchor in (
        "zero useful memory",
        "git fetch origin",
        "Report before push",
        "fresh exact-head semantic review",
        "Do not look for or create `JOHNNY_CHECKPOINT.md`",
    ):
        assert anchor in text, f"BUILDER.md lost required anchor: {anchor}"


# --- Proof 6: JOHNNY template carries the restored control sections -----------

def test_johnny_template_has_restored_sections():
    text = _read("ORCHESTRATOR.md")
    for section in (
        "THREAT MODEL",
        "PORT / REFERENCE CONTRACT",
        "SURFACE BUDGET",
        "DEFERRED OWNERSHIP",
        "CONTINUITY READS",
    ):
        assert section in text, f"JOHNNY template missing section: {section}"


# --- Proof 7: review law requires classification before repair ---------------

def test_review_scope_classification_law():
    text = _read("ORCHESTRATOR.md")
    assert "REVIEW SCOPE CLASSIFICATION LAW" in text
    for term in ("Scope", "Threat model", "Current surface"):
        assert term in text
    assert "Severity is not scope" in text
    assert "classify" in text.lower() and "before" in text.lower()


# --- Proof 7A: enforcement traces to declared semantic authority -------------

def test_semantic_authority_chain_has_no_orphan_rules():
    orch = _read("ORCHESTRATOR.md")
    assert "SEMANTIC AUTHORITY / NO-ORPHAN RULES" in orch
    assert (
        "human/product/game intent -> declared semantic invariant -> owning "
        "Mission/lane -> enforcement -> tests/review"
    ) in orch
    lowered = orch.lower()
    for mechanism in ("validators", "ci", "tests", "regexes", "review findings"):
        assert mechanism in lowered
    assert "do not create product/game requirements" in lowered
    assert "every blocking rule must trace" in lowered
    assert "explicit semantic invariant" in lowered
    assert "severity is evidence priority" in lowered
    assert "build may implement enforcement for another lane's declared invariant" in lowered
    assert "owning lane retains semantic authority" in lowered
    assert "build must not invent, widen, reinterpret, or impose" in lowered


# --- Proof 7B: conflicts stop; schematic notation cannot legislate meaning ---

def test_semantic_conflicts_stop_and_day_notation_is_not_product_law():
    orch = _read("ORCHESTRATOR.md")
    lowered = orch.lower()
    assert "stop and return to the orchestrator" in lowered
    assert "do not silently choose or harden" in lowered
    assert "`day_xxx`" in lowered
    assert "exactly-three-digit" in lowered
    assert "day-999 ceiling" in lowered


# --- Proof 7C: Builder preserves invariants and lane ownership ----------------

def test_builder_preserves_declared_semantics_and_lane_ownership():
    builder = _read("BUILDER.md")
    lowered = builder.lower()
    assert "preserve the declared semantic invariants" in lowered
    assert "do not infer new product/game requirements" in lowered
    assert "implementation or proof appears to contradict" in lowered
    assert "stricter technical interpretation" in lowered
    assert "declared invariant and owning mission/lane" in lowered
    assert "build may own the technical how of enforcement" in lowered
    assert "semantic authority remains with that lane" in lowered
    assert "build must not invent, widen, reinterpret, or impose" in lowered
    worksystem = _read("docs/RHC_WORKSYSTEM.md").lower()
    assert "no johnny, builder lifecycle, codex review, or flight control" in worksystem


# --- Proof 8: both ledgers exist with bounded scope + correct ownership -------

def test_ledgers_exist_bounded_and_scoped():
    changelog = _read("CHANGELOG.md")
    engine = _read("ENGINE_CHANGELOG.md")
    assert "Ledger start" in changelog and "Ledger start" in engine
    assert "does not claim complete retroactive history" in changelog
    assert "No claim is made of complete retroactive rationale" in engine
    assert "non-goals" in engine.lower()
    assert "PR #34" in changelog and "PR #34" in engine
    assert "human-confirm-every-BUILD" in engine or "human confirm" in engine.lower()
    assert "RT01-C" in engine


# --- Proof 9: NO per-engineering-PR ledger gate; validator removed ------------

def test_no_per_pr_ledger_enforcement():
    assert not (ROOT / "tools" / "validate_change_ledger.py").exists()
    workflow = _read(".github/workflows/flight-control.yml")
    assert "LEDGER-EXEMPT" not in workflow
    assert "require BOTH" not in workflow
    assert "Change-Ledger Gate" not in workflow
    assert "python tools/validate_change_ledger.py" not in workflow
    for rel in ("CHANGELOG.md", "ENGINE_CHANGELOG.md"):
        text = _read(rel)
        assert "not a per-PR" in text, f"{rel} must disclaim per-PR ledger semantics"


# --- Proof 16: milestone/patch-series closeout is the publication unit --------

def test_ledger_publication_is_milestone_not_per_pr():
    for rel in ("CHANGELOG.md", "ENGINE_CHANGELOG.md"):
        lowered = _read(rel).lower()
        assert "milestone" in lowered, f"{rel} must state milestone-level publication"
        assert "closeout" in lowered, f"{rel} must name closeout as the publication unit"
    engine = _read("ENGINE_CHANGELOG.md").lower()
    assert "not because ci" in engine or "not because codex" in engine or "codex ran" in engine


# --- Proof 10: PLAY route does not load BUILD machinery ----------------------

def test_play_lane_has_no_build_machinery():
    play = _read("PLAY.md")
    assert "PLAY is not BUILD" in play
    assert "DM_CONTROL_ROOM.md" in play and "RHC_WORKSYSTEM.md" in play
    lowered = play.lower()
    assert "johnny" not in lowered.split("build", 1)[0] or "no johnny" in lowered
    assert "no johnny" in lowered or "no `changelog.md`" in lowered


# --- Proof 11: SAVE points to real persistence, no direct-write/chat success --

def test_save_lane_points_to_worksystem_no_shortcut():
    handoff = _read("AGENT_HANDOFF.md")
    assert "RHC_WORKSYSTEM.md" in handoff
    assert "no direct-write" in handoff.lower() or "no chat-level" in handoff.lower()
    assert "committed repository state" in handoff


# --- Proof 12: READ is explicitly non-mutating -------------------------------

def test_read_lane_is_non_mutating():
    handoff = _read("AGENT_HANDOFF.md")
    assert "READ performs no mutation" in handoff


# --- Proof 13: lifecycle rules remain intact ---------------------------------

def test_lifecycle_rules_intact():
    builder = _read("BUILDER.md")
    orch = _read("ORCHESTRATOR.md")
    assert "Report before push" in builder
    assert "After Orchestrator release:" in builder
    assert "fresh exact-head semantic review" in builder
    assert "Merge only that exact cleared HEAD." in builder
    assert "Merge only the exact HEAD" in orch


# --- Proof 14: no routine human-confirm-every-BUILD loop ----------------------

def test_no_routine_human_confirm_loop():
    engine = _read("ENGINE_CHANGELOG.md")
    assert "No routine human-confirm-every-BUILD loop" in engine
    for rel in ("BUILDER.md", "ORCHESTRATOR.md", "AGENT_HANDOFF.md", "PLAY.md"):
        text = _read(rel).lower()
        assert "confirm every build" not in text
        assert "human approval before every build" not in text


# Mission-specific scope proof (for example, "this PR touched no campaign files")
# deliberately does NOT live in this persistent suite. It belongs to the current
# JOHNNY / PR diff / Orchestrator evidence so future legitimate SAVE PRs are not
# turned into repository-wide failures.


# --- Repair proof A: READ routes workflow status to live Asana first ----------

def test_read_lane_routes_workflow_status_to_asana_first():
    handoff = _read("AGENT_HANDOFF.md")
    assert "live Asana first" in handoff
    assert "active gate" in handoff and "next authorized action" in handoff
    assert "not** global" in handoff or "not global" in handoff.replace("**", "")
    assert "never reconstructs the Mission from Asana or chat" in handoff
    assert "READ performs no mutation" in handoff


# --- Repair proof B: continuity is source-agnostic, not ledger-only ----------

def test_continuity_gate_is_source_agnostic():
    builder = _read("BUILDER.md")
    orch = _read("ORCHESTRATOR.md")
    for text in (builder, orch):
        lowered = text.lower()
        assert "source-agnostic" in lowered, "continuity must be declared source-agnostic"
        assert "wdr" in lowered, "continuity must admit a selected WDR"
        assert "trevor" in lowered or "receipt" in lowered, "continuity must admit Trevor/receipt"
    assert "not the only" in builder.lower() or "only continuity" in builder.lower()


# --- Repair proof C: ledgers carry the explicit one-time bootstrap exception --

def test_ledgers_declare_bootstrap_seed_exception():
    for rel in ("CHANGELOG.md", "ENGINE_CHANGELOG.md"):
        text = _read(rel)
        assert "Bootstrap seed exception" in text, f"{rel} missing bootstrap seed exception"
        lowered = text.lower()
        assert "one-time" in lowered, f"{rel} must call the seed one-time"
        assert "pre-merge" in lowered or "same pr" in lowered, f"{rel} must note pre-merge seeding"
        assert "closeout" in lowered, f"{rel} must contrast with the normal closeout rule"


# --- Repair proof D: PLAY re-routes explicit SAVE intent, does not own save ---

def test_play_reroutes_explicit_save_intent():
    play = _read("PLAY.md")
    lowered = play.lower()
    assert "not a save cockpit" in lowered or "not** a save cockpit" in lowered
    assert "re-route" in lowered, "PLAY must re-route explicit save intent, not own it"
    assert "RHC_WORKSYSTEM.md" in play, "PLAY must keep the pointer to the SAVE authority"
    assert "does not restate or own the save procedure" in lowered
    assert "persist meaningful current continuity deltas" not in play, (
        "PLAY must not duplicate the Quicksave/Autosave mechanics"
    )
    assert "canon/days/day_XXX.md" not in play, (
        "PLAY must not duplicate the Final Save mechanics"
    )


# --- Repair proof E: PLAY and READ lanes do not overlap at the Dropgate -------

def test_play_and_read_lanes_do_not_overlap():
    handoff = _read("AGENT_HANDOFF.md")
    lowered = handoff.lower()
    assert "standalone" in lowered
    assert "continuing a live session" in lowered
    assert "canon question / narration" not in handoff


# --- Review repair: every JOHNNY declares an explicit threat model ------------

def test_johnny_template_requires_explicit_threat_model():
    orch = _read("ORCHESTRATOR.md")
    template = orch.split("# JOHNNY CHECKPOINT TEMPLATE", 1)[1]
    assert "## THREAT MODEL" in template
    section = template.split("## THREAT MODEL", 1)[1].split("\n## ", 1)[0].lower()
    assert "required" in section
    assert "in scope" in section
    assert "out of scope" in section
    assert "does not replace it" in template.lower(), (
        "optional TRUST BOUNDARIES must not substitute for the required threat model"
    )


# --- Review repair: Surface Budget governs Builder execution -----------------

def test_builder_stage4_enforces_surface_budget():
    builder = _read("BUILDER.md")
    stage4 = builder.split("## Stage 4", 1)[1].split("## Stage 5", 1)[0]
    assert "SURFACE BUDGET" in stage4
    lowered = stage4.lower()
    assert "active implementation constraint" in lowered
    assert "outside that budget" in lowered
    assert "stop and return to the orchestrator" in lowered
    assert "review severity expands the budget" in lowered


# --- Patch 1C: JOHNNY declares mutation-domain/compatibility impact pre-BUILD ---

def test_johnny_requires_mutation_domain_compatibility_declaration():
    orch = _read("ORCHESTRATOR.md")
    lowered = orch.lower()

    # Doctrine exists and is owned by the Orchestrator's authoring obligations.
    assert "mutation domain / compatibility declaration" in lowered
    assert "classify whether the mission adds or changes a runtime mutation domain" in lowered

    # Prove the durable doctrine declaration locally. These assertions must not
    # be satisfiable by the later JOHNNY template or unrelated document text.
    doctrine = orch.split("\n## MUTATION DOMAIN / COMPATIBILITY DECLARATION\n", 1)[1].split(
        "\n## HARD WRITE BOUNDARY", 1
    )[0]
    doctrine_lower = doctrine.lower()
    assert "workflow authoring memory, not runtime authority" in doctrine_lower
    assert "not a fourth wall of the mission boundary triad" in doctrine_lower

    doctrine_yes = doctrine.split("- **YES**", 1)[1].split("\n- **NO**", 1)[0].lower()
    assert "affected runtime mutation domain" in doctrine_yes
    assert "affected same-save compatibility edge" in doctrine_yes
    assert "owning semantic route" in doctrine_yes
    assert "required patch 1a registry" in doctrine_yes
    assert "patch 1b dispatcher update" in doctrine_yes
    assert "proof" in doctrine_yes

    doctrine_no = doctrine.split("- **NO**", 1)[1].lower()
    assert "no patch 1a registry or patch 1b dispatcher change is required" in doctrine_no

    # Prove the JOHNNY-template declaration independently from the doctrine.
    template = orch.split("# JOHNNY CHECKPOINT TEMPLATE", 1)[1]
    assert "## MUTATION DOMAIN / COMPATIBILITY DECLARATION" in template
    section = template.split("\n## MUTATION DOMAIN / COMPATIBILITY DECLARATION\n", 1)[1].split(
        "\n## ", 1
    )[0]
    section_lower = section.lower()
    assert "required" in section_lower
    assert "yes:" in section_lower and "no:" in section_lower
    assert "workflow authoring memory, not runtime authority" in section_lower
    assert "not a fourth mission boundary triad wall" in section_lower

    template_yes = section_lower.split("yes:", 1)[1].split("no:", 1)[0]
    assert "affected runtime mutation domain" in template_yes
    assert "affected same-save compatibility edge" in template_yes
    assert "owning semantic route" in template_yes
    assert "required patch 1a registry" in template_yes
    assert "patch 1b dispatcher update" in template_yes
    assert "proof" in template_yes

    template_no = section_lower.split("no:", 1)[1]
    assert "no mutation-domain/compatibility registry-dispatcher change is required" in template_no

    # Match the complete JOHNNY CHECK heading so CHECK proof cannot leak from
    # the earlier JOHNNY CHECKPOINT/template declaration text.
    check = template.split("\n## JOHNNY CHECK\n", 1)[1].split("\n## CLOSEOUT", 1)[0].lower()
    assert "mutation domain / compatibility declaration" in check
    assert "exactly one explicit yes or no" in check
    assert "before build release" in check
