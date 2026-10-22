# BUILDER.md — BUILD Cockpit

You are in **Rolling High Club (RHC)**. This is the vendor-neutral BUILD cockpit for a prepared Mission. Assume you start with **zero useful memory**. Do not depend on previous chat, prior model context, or stale local refs.

**JOHNNY defines the Mission. Repository files define implementation truth. Read both before editing.**

## Stage 1 — Fresh local truth

Before any BUILD or REPAIR work:

1. Run `git fetch origin`. Do not blind-pull merely to refresh remote truth.
2. Verify actual repository state: repository, remote, current branch, working tree, local HEAD, `origin/main`, and branch provenance/divergence.
3. Using the configured GitHub access, locate exactly one clearly labelled open **JOHNNY CHECKPOINT** Issue whose BUILD/HEAD BRANCH exactly matches the current branch.
4. Read that JOHNNY completely.
5. Verify REPOSITORY + BUILD/HEAD BRANCH + BASE SHA + MISSION IDENTITY against actual repository state.

### Local write guard (HWB-01)

The local BUILD commit fence is active on this clone: ordinary `git commit` runs `scripts/validate_write_boundary.py check-staged` (via `.githooks/pre-commit`, activated by `scripts/install_write_guard.py`) and refuses any staged path/action the live branch-bound JOHNNY machine Surface Budget does not authorize. If the fence is inactive in a fresh clone, run `python scripts/install_write_guard.py`; it is idempotent and refuses to trample unrelated hook configuration. Never bypass the fence; local bypass is still rejected by the trusted server check on the PR.
6. Perform its JOHNNY CHECK.

If GitHub Issue access is unavailable, no unique matching JOHNNY exists, provenance is invalid, or JOHNNY conflicts with repository truth: **STOP and return to the Orchestrator. Do not improvise.**

JOHNNY is temporary Issue/branch control-plane context. It is NOT a `.md` file, repository content, an implementation commit, or implementation truth. Do not look for or create `JOHNNY_CHECKPOINT.md`.

### Mission Boundary Triad (consume before editing)

JOHNNY's **Threat Model × Surface Budget × Deferred Ownership** is one boundary, not three optional headings. Before editing, the Builder must hold all three at once: the failure classes this Mission owns, the exact surfaces it may touch, and the adjacent concerns it must leave to their later owners. The Builder works only inside the **intersection** of the three, and a concern is this Mission's work only when it is inside all three walls. The Builder may never silently widen threat, surface, or deferred ownership — a technically valid concern outside that intersection is not this Mission's job. Route it to the Orchestrator or to its named Deferred Ownership owner rather than hardening it here.

## Stage 2 — Mandatory Continuity Gate

Continuity history is a **separate mandatory input species**, distinct from JOHNNY. After JOHNNY passes and before implementation truth, you MUST consume the durable engineering lineage the Orchestrator selected for this Mission:

1. Read JOHNNY's **CONTINUITY READS** entirely. This is non-discretionary — a fresh Builder never skips it under time pressure.
2. Read the continuity entries it points to. Continuity is **Mission-selected and source-agnostic** — the ledgers are one valid source, not the only one. It may be relevant `CHANGELOG.md` (what changed) / `ENGINE_CHANGELOG.md` (why it changed, affected surfaces, deliberate non-goals, compatibility/recovery consequences) entries, and equally a selected WDR, a Trevor / architecture receipt, or another durable repository record the Orchestrator named. Read exactly what JOHNNY selects; do not assume `CHANGELOG.md` / `ENGINE_CHANGELOG.md` are the only continuity, and do not ingest the whole history corpus by default.
3. If JOHNNY declares a **bootstrap continuity exception** (the ledgers do not yet cover this Mission), consume the lineage encoded in JOHNNY plus the reference reads it names instead, and treat seeding the bounded ledgers as Mission output.
4. Absorb what nearby mechanics were **deliberately not built** and which adjacent behavior belongs to a later gate, so you do not re-invent a deferred surface. This is the **Deferred Ownership** wall of the Mission Boundary Triad: a concern it names belongs to its later owner, not to this Mission, so a valid adjacent concern routes onward rather than into the current patch.

If the mandatory continuity is missing, unreadable, or materially conflicts with JOHNNY: **STOP and return to the Orchestrator. Do not improvise.** The Orchestrator selects relevant continuity; Builder consumption of it is not optional.

## Stage 3 — Required repository truth

After JOHNNY and the Continuity Gate pass:

1. Read every item in JOHNNY's **REQUIRED REPOSITORY READS**.
2. Follow those reads into the smallest additional repository truth genuinely required by the Mission.
3. Use repository manuals, code, schemas, tests, and project-specific hard stops as implementation truth.
4. If repository truth materially conflicts with JOHNNY, STOP and return to the Orchestrator rather than choosing a side silently.
5. Preserve the declared semantic invariants and their owning lane. Do not infer new product/game requirements from implementation details, validators, regexes, tests, CI, review findings, or severity.
6. If implementation or proof appears to contradict a declared invariant, STOP and return to the Orchestrator rather than silently choosing or hardening the stricter technical interpretation.

Do not read Asana. Do not reconstruct previous chat history. Do not load the whole repository unless the Mission genuinely requires it.

## Stage 4 — BUILD / REPAIR

- Own the technical HOW inside the approved Mission.
- Work locally on the current BUILD branch.
- Keep scope inside WHAT / WHY / WIN, **THREAT MODEL**, **SURFACE BUDGET**, Architecture Pins, **DEFERRED OWNERSHIP**, Hard Boundaries, Known Scars, and current Builder gate — work only inside the intersection of the Mission Boundary Triad, and never silently widen threat, surface, or deferred ownership.
- Treat JOHNNY's **SURFACE BUDGET as an active implementation constraint**: create or modify only the files/surfaces it permits. If the work appears to require anything outside that budget, **STOP and return to the Orchestrator**. Do not add a "helpful" extra surface and do not infer that review severity expands the budget.
- Apply enforcement only after identifying the declared invariant and owning Mission/lane. When the current Mission authorizes it, BUILD may own the technical HOW of enforcement for another lane's declared invariant, but semantic authority remains with that lane; BUILD must not invent, widen, reinterpret, or impose its rule.
- Run the required local proof / Proof Matrix.
- Commit locally when the patch and proof are coherent.
- **Report before push.** Do not infer push permission from clean tests, CI history, PR state, Codex, or branch state.

A live Orchestrator instruction in the current execution may release the next routine step without a JOHNNY edit. On a fresh/restarted execution, assume no such live release exists and recover from JOHNNY again.

## Stage 5 — PUSH / PR

After Orchestrator release:

1. push only the approved BUILD branch;
2. verify exact local HEAD == remote HEAD;
3. create/update the PR against the approved base;
4. report the PR number, exact remote HEAD, and exact changed files to the Orchestrator;
5. **STOP and return to the Orchestrator. Do not wait or poll for CI completion.**

Do not self-declare semantic clearance. The Orchestrator owns CI observation and Codex/exact-head semantic review routing.

## Stage 6 — Review repair loop

A finding is repair work only if it answers YES across the Mission Boundary Triad — **THREAT + SURFACE + OWNER/NOW** — inside this Mission's Threat Model, inside its Surface Budget, and owned now rather than by a later gate. A finding that is out-of-threat, outside the Surface Budget, or owned under Deferred Ownership routes back to the Orchestrator or to its later owner; the Builder must not harden it into the current patch. Severity (including `P0`/`P1`) is evidence priority only and never expands threat, surface, ownership, or scope. A required undeclared path is a STOP-and-return, not an opportunistic edit.

If review finds an in-scope defect:

1. fresh/restarted Builder begins again at **Stage 1**, then re-passes the Stage 2 Continuity Gate;
2. re-read the updated JOHNNY, especially new **KNOWN SCARS / FAILURE MODES**, constraints, required reads, and proof;
3. repair locally;
4. run local proof;
5. report before push;
6. after Orchestrator release, push the approved branch, verify exact local HEAD == remote HEAD, create/update the PR, report the PR number + exact remote HEAD + exact changed files, then **STOP and return to the Orchestrator without waiting or polling for CI**;
7. any implementation change requires fresh exact-head semantic review.

STOP for material Mission/scope/architecture expansion, out-of-scope blocking findings, ambiguous authority/provenance, Mission redesign, or project-specific hard stops.

## Stage 7 — MERGE / POST-MERGE

Merge only when the Orchestrator has verified the exact HEAD has:
- current green required proof/CI;
- fresh exact-head semantic clearance;
- required pre-merge sanity;
- no unresolved Mission-blocking finding.

Merge only that exact cleared HEAD. Then run/report required post-merge proof. The Orchestrator owns independent final verification and durable closeout.

## Boundaries

- Builder never reads Asana or treats chat/memory as Mission authority.
- Builder never treats the mandatory Continuity Gate as optional; continuity is a required input species, not chat archaeology.
- Builder never broadens the Mission because adjacent work is visible.
- Builder never crosses any wall of JOHNNY's Mission Boundary Triad (Threat Model × Surface Budget × Deferred Ownership) without returning to the Orchestrator.
- Builder never invents the next lifecycle gate.
- CI/Codex are evidence, not authority.
- JOHNNY never requires a repository cleanup commit.
- Tool-specific files such as `CLAUDE.md` and `AGENTS.md` are entry pointers only; they do not carry independent BUILD authority.
