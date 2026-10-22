# ORCHESTRATOR.md

## PURPOSE

Prepare the temporary BUILD handoff after a Mission is approved through Flight Control.

The **JOHNNY CHECKPOINT is a sufficient Builder Mission Packet**, not a minimal hint. It must let a fresh Builder start with zero useful memory, recover the approved Mission safely, and know what repository truth to read before editing.

Branch naming rule: use a normal Git-safe repository-approved BUILD branch name with no spaces.

## JOHNNY MECHANISM

The **JOHNNY CHECKPOINT is temporary branch-bound Mission context stored as a clearly labelled open GitHub Issue for the BUILD branch.**

It is NOT:
- a `.md` file;
- repository content;
- a committed artifact;
- a branch name;
- implementation truth;
- a substitute for repository manuals, code, tests, or live Orchestrator authority.

Do NOT create `JOHNNY_CHECKPOINT.md` or any equivalent repository artifact.

Before Builder implementation begins, the Orchestrator must:
1. establish the exact approved BASE SHA;
2. create or identify the BUILD branch from that BASE;
3. create exactly one branch-bound JOHNNY Issue;
4. bind REPOSITORY + BUILD/HEAD BRANCH + BASE SHA + MISSION IDENTITY;
5. preserve the human Mission core: WHAT / WHY / WIN;
6. state the Mission **THREAT MODEL** explicitly: which actors/failure classes are IN scope and which important threats are OUT of scope;
7. add enough current system state, authority/trust context, scars, boundaries, required repository reads, and proof expectations for a fresh Builder to execute safely;
8. classify whether the Mission adds or changes a runtime mutation domain or a same-save compatibility edge, and record exactly one explicit **MUTATION DOMAIN / COMPATIBILITY DECLARATION** (YES or NO) as required by that section;
9. set the current Builder gate;
10. verify the **Mission Boundary Triad** (THREAT MODEL × SURFACE BUDGET × DEFERRED OWNERSHIP) is mutually coherent with WHAT / WHY / WIN, the Architecture Pins, current repository truth, and the required proofs, and that each wall carries meaningful content rather than a placeholder — a Mission with a missing, empty, or contradictory wall is not released to BUILD;
11. verify JOHNNY against relevant repository truth before handoff.

**Sufficient, not exhaustive.** Carry what the fresh Builder needs to avoid archaeology or dangerous reconstruction. Do not dump project history, Asana, or chat logs into JOHNNY.

## MISSION BOUNDARY TRIAD

Every BUILD Mission is bounded by one reusable **Mission Boundary Triad**: **Threat Model × Surface Budget × Deferred Ownership**. These are not three unrelated headings — they are three walls that only together define a Mission's positive scope and its negative space. The Orchestrator must reason across all three as one boundary rather than filling them in independently.

- **Threat Model** — the actors and failure classes this Mission owns (IN) and the important threats it deliberately does not (OUT).
- **Surface Budget** — the exact files/surfaces this Mission may create, modify, or delete, and those it must not invent.
- **Deferred Ownership** — the adjacent valid concerns this Mission deliberately does not own, and the later owner/gate that does.

The triad is a reasoning boundary, not a fourth authority layer: it classifies work against the existing authority chain (human/product/game intent -> declared semantic invariant -> owning Mission/lane -> enforcement -> tests/review); it does not add one. A single concern is this Mission's work only when it is inside all three walls at once. A valid adjacent concern named under Deferred Ownership routes to its named later owner, never into the current patch. A surface outside the Surface Budget, a threat outside the Threat Model, or a concern owned by a later gate is a **STOP** — the Orchestrator classifies it before any repair, and the Builder returns rather than opportunistically editing an undeclared path.

Before releasing BUILD, the Orchestrator must verify the triad is mutually coherent with WHAT / WHY / WIN, the Architecture Pins, current repository truth, and the downstream pipeline.

## ENGINEERING SPINE

`BUILD → local proof → report → Orchestrator gate → PUSH + PR/CI → Orchestrator CODEX → [finding → JOHNNY scar/invariant update when needed → REPAIR → local proof → report → Orchestrator gate → PUSH + PR/CI → fresh CODEX] ↻ → exact-head clean → pre-merge sanity → MERGE exact cleared HEAD → POST-MERGE PROOF → CLOSEOUT`

Rules:
- Builder stops and reports after each local BUILD or REPAIR before pushing.
- The Orchestrator evaluates that report. If work remains inside the already-authorized Mission and proof is coherent, the Orchestrator may release the next step without another human approval.
- CI and Codex are evidence gates, never Mission authority.
- Any implementation change after semantic review requires fresh exact-head review.
- Merge only the exact HEAD with current green proof/CI, exact-head semantic clearance, and required pre-merge sanity.
- Escalate to Nollie only for material scope/architecture change, an out-of-scope blocker, ambiguous authority/provenance, Mission redesign, or a project-specific STOP.

## JOHNNY UPDATE RULE

JOHNNY evolves while the branch is active, but only when Builder-relevant truth changes.

Update it when, for example:
- Codex/review discovers a new invariant, trust-boundary scar, or required proof;
- an in-scope repair needs a clarified constraint or new required repository read;
- the next fresh/restarted Builder needs a changed lifecycle instruction.

Do NOT churn JOHNNY for routine reports, unchanged green CI, or evidence that does not change the next Builder's model.

A live Orchestrator instruction in the current Builder execution may release the next routine lifecycle step without rewriting JOHNNY. A fresh/restarted Builder has no such memory and must recover from the current JOHNNY plus repository truth.

JOHNNY updates are control-plane changes only. They never change implementation HEAD and never require a cleanup commit.

## SEMANTIC AUTHORITY / NO-ORPHAN RULES

The authority chain is: **human/product/game intent -> declared semantic invariant -> owning Mission/lane -> enforcement -> tests/review**. Lane classification and semantic ownership come before lane-specific enforcement. When the current Mission explicitly authorizes the technical work, BUILD may implement enforcement for another lane's declared invariant, but the owning lane retains semantic authority. BUILD must not invent, widen, reinterpret, or impose that lane's rule.

- Guards, validators, CI, tests, regexes, implementation details, and review findings may enforce or provide evidence for declared law; they do not create product/game requirements.
- Every blocking rule must trace to an explicit semantic invariant and the Mission/lane that owns it. An orphan rule with no such owner is not enforceable authority.
- Severity is evidence priority, not semantic, scope, or ownership authority.
- Schematic notation is not an exact product constraint unless the owning invariant says so. In particular, `day_XXX` must not be promoted by workflow law into an exactly-three-digit or day-999 ceiling.
- If enforcement, implementation, proof, or review conflicts with declared intent, STOP and return to the Orchestrator. Do not silently choose or harden the stricter technical interpretation.

## REVIEW SCOPE CLASSIFICATION LAW

CI and Codex are evidence, never Mission authority. Before any review finding enters repair, the Orchestrator MUST classify it against all three walls of the Mission Boundary Triad — **Threat + Surface + Owner/now** — regardless of its severity label:

1. **Scope:** does the finding concern a surface actually declared in this Mission's SURFACE BUDGET, or an adjacent/invented/deferred surface?
2. **Threat model:** does the finding fall inside this Mission's required THREAT MODEL, or does it assume a threat the Mission explicitly excluded?
3. **Current surface:** is the finding about behavior this Mission is responsible for now, or behavior owned by a later gate under DEFERRED OWNERSHIP?

A finding becomes repair work only when it answers **YES / YES / YES** across the triad — in-threat-model, in-surface-budget, owned-now. Any NO routes the finding to its real owner instead of into this patch: an out-of-threat or later-owner finding returns to the Orchestrator, and a finding against an undeclared surface is resolved by removing/deferring the invented surface or returning to the Orchestrator, never by hardening the invention. **Severity is not scope: a `P1`/`P0` does not create a requirement, expand Mission scope, or grant surface, threat, or ownership authority.** Classify first; repair only surviving in-scope defects.

## MUTATION DOMAIN / COMPATIBILITY DECLARATION

Patch 1A makes runtime mutation-domain admission machine-readable (`public._rhc_save_domain_policy`) and Patch 1B makes same-save compatibility machine-readable (`_rhc_same_save_compatibility_policy` / `_rhc_require_same_save_compatibility`). Before any BUILD Mission is released, the Orchestrator must classify whether the Mission adds or changes a runtime mutation domain or a same-save compatibility edge, and record exactly one explicit answer in JOHNNY.

- **YES** — the Mission adds or changes a runtime mutation domain or a same-save compatibility edge. JOHNNY must name the affected runtime mutation domain(s); the affected same-save compatibility edge(s), if any; the owning semantic route(s)/lane(s); and the required Patch 1A registry and/or Patch 1B dispatcher update plus the proof that demonstrates it.
- **NO** — the Mission adds or changes no runtime mutation domain and no same-save compatibility edge. JOHNNY must state explicitly that no Patch 1A registry or Patch 1B dispatcher change is required.

The declaration is **workflow authoring memory, not runtime authority**: it is not a fourth wall of the Mission Boundary Triad and it does not create, widen, or reinterpret domain or compatibility semantics. Machine-readable runtime policy remains server-owned Patch 1A/1B implementation truth. A YES declaration does not itself authorize a runtime change outside that Mission's Surface Budget; the required registry/dispatcher update still belongs to the owning Mission and must sit inside its Surface Budget. A generic phrase such as "consider registry impact" is too weak: the declaration forces an explicit YES or NO and defines what each answer requires.

## HARD WRITE BOUNDARY (HWB-01)

Builder write authority is enforced mechanically at two points of the same lifecycle:

1. **Local ordinary-commit fence** — `.githooks/pre-commit` (activated per clone by `scripts/install_write_guard.py`, which sets `core.hooksPath`) runs `scripts/validate_write_boundary.py check-staged` on every ordinary `git commit`. An unauthorized staged path/action is refused.
2. **Trusted server PR fence** — `.github/workflows/hard-write-boundary.yml` (`pull_request_target`) checks out the exact PR base SHA and runs the base-defined `scripts/validate_write_boundary.py check-pr` against the exact immutable PR head/base. The PR head is data only; PR-controlled code never executes with authority credentials, so a PR cannot weaken or neutralize the fence and grade itself.

Both fences share ONE authority contract: the single machine Surface Budget block (`RHC_SURFACE_BUDGET_V1`) inside the unique open branch-bound JOHNNY. Default deny; ambiguous identity/authority/evidence fails closed. Bypassing the local hook locally never authorizes a write — the trusted server fence still rejects the PR. After merge, the Orchestrator must make the trusted check required in the main ruleset and run authorized + bypass adversarial canaries.

# JOHNNY CHECKPOINT TEMPLATE

Use this as the temporary GitHub Issue for the BUILD Mission. Omit empty ceremony, but never omit context a fresh Builder actually needs. **THREAT MODEL, SURFACE BUDGET, and DEFERRED OWNERSHIP are required control fields for every BUILD Mission: together they are the Mission Boundary Triad, and they must be coherent with each other, not three independently-filled headings.**

## JOHNNY CHECKPOINT

REPOSITORY: [owner/repository]
BUILD/HEAD BRANCH: [exact BUILD branch]
BASE SHA: [exact approved starting commit]
MISSION IDENTITY: [short unique Mission name]

## MISSION

WHAT: [What behavior/outcome is approved?]

WHY: [Why is this needed?]

WIN: [What observable result proves success?]

## CURRENT SYSTEM STATE

[What already exists, what state the Mission starts from, and what must not be rebuilt.]

## MUTATION DOMAIN / COMPATIBILITY DECLARATION

[REQUIRED. Exactly one explicit answer, YES or NO. YES: name the affected runtime mutation domain(s); the affected same-save compatibility edge(s), if any; the owning semantic route(s)/lane(s); and the required Patch 1A registry and/or Patch 1B dispatcher update + proof. NO: state explicitly that no mutation-domain/compatibility registry-dispatcher change is required. This is workflow authoring memory, not runtime authority, and not a fourth Mission Boundary Triad wall.]

## AUTHORITY / OWNERSHIP

[Who owns consequential facts or decisions relevant to this Mission.]

## THREAT MODEL

[REQUIRED. State the actors, failure classes, and assumptions that are **IN scope**, plus the important threats explicitly **OUT of scope**. Review findings are classified against this declaration. Do not leave the Orchestrator or Builder to infer the threat model from severity, chat, or optional trust notes. This is one wall of the Mission Boundary Triad; it bounds the Mission only together with SURFACE BUDGET and DEFERRED OWNERSHIP.]

## STATE / LIFECYCLE MODEL

[Only when meaningful transitions, crash/retry behavior, or ordered gates matter.]

## TRUST BOUNDARIES

[Only when identity, authorization, external evidence, hostile/stale input, or privilege matters. This may add detail to the required THREAT MODEL, but it does not replace it.]

## ARCHITECTURE PINS

[Architectural facts/decisions Builder must preserve.]

## PORT / REFERENCE CONTRACT

[When the Mission adapts prior art or another repository: what to ADAPT, PORT, or REJECT, and the exact reference semantics to preserve. Include only when the Mission is a restoration/adaptation; state that copying is not blind cloning. Omit for a purely native change.]

## SURFACE BUDGET

[REQUIRED. The exact set of files/surfaces this Mission may create or modify, and the surfaces it must NOT invent. A surface outside this budget is a STOP-and-return, not a helpful extra. Severity of a later finding never expands this budget. One wall of the Mission Boundary Triad: a finding that answers NO here is not repair work.]

## DEFERRED OWNERSHIP

[Adjacent behavior that is deliberately NOT this Mission's job, and which later gate/Mission owns it. This is what keeps a helpful Builder from inventing a deferred surface. One wall of the Mission Boundary Triad: a valid concern named here routes to its later owner, never into the current patch.]

## KNOWN SCARS / FAILURE MODES

[Prior findings or failure classes the fresh Builder must not regress.]

## HARD BOUNDARIES

[Explicitly forbidden or out-of-scope work.]

## CONTINUITY READS

[The durable engineering lineage the Builder must consume through the mandatory Continuity Gate. Continuity is **source-agnostic and Mission-selected**: name whichever durable records this Mission actually needs — relevant `CHANGELOG.md` / `ENGINE_CHANGELOG.md` entries, a selected WDR, a Trevor / architecture receipt, or another declared durable repository record — or declare a bootstrap exception plus the reference reads that stand in for missing ledger history. Do not hard-code the ledgers as the only continuity source. Orchestrator selects the relevant records so cold start stays bounded; Builder consumption is non-discretionary. This is a separate input species from REQUIRED REPOSITORY READS, not a duplicate of it.]

## REQUIRED REPOSITORY READS

[Exact repository manuals/files/functions/tests the fresh Builder must read before editing. JOHNNY defines the Mission; repository files define implementation truth.]

## PROOF MATRIX

[Required happy-path, failure, retry, migration, stale-state, hostile-input, or regression cases when relevant.]

## STOP CONDITIONS

[Mission-specific STOP conditions in addition to Flight Control hard stops.]

## CURRENT BUILDER GATE

PHASE: [BUILD | REPAIR | REVIEW | MERGE | POST-MERGE | CLOSEOUT]
AUTHORIZED NEXT ACTION: [What the Builder may do now.]

## JOHNNY CHECK

Before code, Builder must verify that:
- this is the unique clearly labelled open JOHNNY Issue for the current BUILD branch;
- REPOSITORY, BUILD/HEAD BRANCH, BASE SHA, and MISSION IDENTITY are coherent with actual repository state;
- WHAT / WHY / WIN, the required THREAT MODEL, and all included pins, Port/Reference Contract, Surface Budget, Deferred Ownership, Continuity Reads, boundaries, scars, reads, proofs, and current gate are mutually consistent;
- the required **MUTATION DOMAIN / COMPATIBILITY DECLARATION** is present, gives exactly one explicit YES or NO, and is coherent with the Surface Budget and the Mission's runtime impact before BUILD release;
- the **Mission Boundary Triad** (Threat Model × Surface Budget × Deferred Ownership) is cross-coherent with WHAT / WHY / WIN and with each other — not three independently-filled fields — and does not introduce a fourth authority layer;
- required repository reads exist and relevant repository truth does not conflict with JOHNNY.

If JOHNNY is missing, duplicated, unclear, stale, provenance-invalid, conflicts with repository truth, or requires material scope expansion:

**STOP and return to the Orchestrator. Do not reconstruct or improvise the Mission.**

## CLOSEOUT

After the exact cleared HEAD is merged and post-merge proof succeeds, the Orchestrator independently verifies final state, preserves durable meaning through the project closeout rules, closes JOHNNY, reconciles the live control surface, and leaves the next gate clean.
