# ENGINE_CHANGELOG

Curated durable **engineering rationale** for Rolling High Club: *why* a change was made, which surfaces it affected, what was deliberately **not** built (non-goals), compatibility/recovery consequences, and the verification evidence. This is the continuity a fresh Builder consumes through the mandatory Continuity Gate so it does not re-derive the Mission from chat or Asana.

This is a **milestone / patch-series** ledger, **not a per-PR** review diary. An entry is published at coherent milestone/patch-series **closeout** — when a decision is durable enough to preserve — not on every engineering PR, and **not because CI or Codex ran** on an ordinary repair. Transient Codex findings and repair rounds live in the PR, Git history, and the branch-bound JOHNNY, not here. There is intentionally no gate requiring this file to change per engineering PR.

Newest first. This ledger records engineering decisions only; campaign canon/state lives in the campaign domains and `docs/RHC_WORKSYSTEM.md`.

> **Ledger start:** continuous engineering rationale begins with the entry below (2026-09-09). No claim is made of complete retroactive rationale before that date; older reasoning routes to Git history and the durable architecture docs (`PROJECT_PRIMER.md`, `README.md`, `ORCHESTRATOR.md`, `BUILDER.md`, `docs/`).

---

## 2026-10-16 - POST-EV2-Z7: product identity acceptance

### Why this milestone exists
PORT-01's downstream customer still carried a root README declaring itself the live Rolling High Club campaign, and a neutral generated `characters/madma/NARRATIVE_DIRECTION.md` at a campaign-specific path whose empty folder skeleton the exporter kept even though the body was neutral. The NAME/PATH leaked identity, not story/state; the root README was an actual campaign-identity claim. A green export did not yet mean the exported product asserted no source-campaign identity.

> Architecture sentence: **the emitted canvas must be provably free of source campaign identity -- the root README is a generated neutral genesis, named source-owned paths (and their empty folder skeletons) never ship, and an independent identity-acceptance check over the ACTUAL output tree fails closed on any leak.**

### Durable design
- **Two structural policy repairs, no source byte touched.** `README.md` moves COPY -> GENERATE_EMPTY with a fixed campaign-neutral generation constant; `characters/madma/NARRATIVE_DIRECTION.md` (and the empty `npc/profiles/bor-family/`) become EXCLUDE directory prefixes whose stale named folder skeletons are omitted by `identity.omitted_skeleton_prefixes`. RHC's own source README and canon are unchanged.
- **Declarative identity contract.** A new required policy `identity` block declares `path_tokens` (source-owned identity tokens forbidden in any emitted path -- file or preserved directory skeleton), `content_surfaces` (emitted user-facing surfaces whose actual bytes must not carry the declared tokens; `README.md`: `Rolling High Club`, `rhc-primary`), and `omitted_skeleton_prefixes` (validated fail-closed: each must be a clean repository-relative directory owned by an EXCLUDE directory rule).
- **Independent verification of the actual artifact.** `identity_acceptance` runs first as an early expected-tree preflight over the planned output paths and intended bytes (so a predicted leak fails fast with no output created), then authoritatively over the ACTUAL completed output via one strict, no-follow `os.scandir` walk: the real emitted file/directory path set (an unscannable directory or an unreadable entry fails closed, so `os.walk`'s documented silent drop of a `scandir` error -- or a swallowed `DirEntry` classification error -- can never certify a partial inventory), each entry's **no-follow filesystem species** read with `os.lstat`, each declared content surface read through its real on-disk bytes (only from an `lstat`-confirmed regular path, never by following a substituted link out of the canvas), the actual path/kind inventory compared against the authorized expected inventory, every emitted regular file's real bytes — or a legitimate Git `120000` COPY symlink's real `readlink` target — attested by SHA-256 against the exact intended digest, and every emitted regular file's real POSIX mode verified against its authorized Git `100755`/`100644` mode. A regular file and a symlink that share a relative path are no longer collapsed onto the same bare string: a regular file substituted by a symlink, or a preserved skeleton replaced by a symlink, fails closed, while an authorized Git `120000` symlink is expected to remain an actual symlink rather than being silently treated as a regular file. A leaked path token, a mutated README, an extra (even token-free) or missing materialized path, a substituted path kind, altered bytes, a changed executable bit, or any unreadable path/scan failure fails the export closed before any accepted receipt is written; the byte attestation closes the sibling false-certification where a token-free but altered materialized regular file could otherwise pass while the receipt held only the intended blob SHA, and the mode attestation closes the sibling where a 0755 → 0644 executable downgrade (or an accidental 0644 → 0755 bit) leaves kind and bytes identical. On acceptance the receipt records the machine-readable evidence for the completed tree: a top-level `artifact_attestation` states what this host actually proved — `path_inventory`/`path_kind`/`content_digest` verified on every host, and `posix_mode` derived from the same capability predicate the verifier uses (`verified` where the host exposes permission bits and every emitted regular file passed its authorized Git `100755`/`100644` mode, else `not_observable`, never a silent `verified`) — alongside the identity-only `identity_acceptance` evidence, whose boolean is not overloaded to mean platform mode proof. It never rewrites a byte and never reclassifies a path — it is not a content-based classifier, and hostile mutation *after* this inspection stays explicitly out of scope. POSIX permission fidelity is asserted only where the host exposes permission bits (`os.name == 'posix'`); the executable bit is not representable on Windows — the Ubuntu CI job proves it.
- **Narrow scope by construction.** The exception surface is exactly the declared `identity` block: no generic `RHC` substring removal, no general de-branding of stable runtime/SQL/API identifiers, reusable engine docs or provenance.

### Deliberate non-goals / deferred ownership
- No runtime/mechanic/schema/migration change and no `ENGINE_VERSION` bump; no PORT-01 or Copier change (PORT-01 owns re-exporting/resyncing after Z7 merges); no general identity-naming standard (a later explicit mission); no change to `docs/DM_CONTROL_ROOM.md` or other reusable docs, whose legitimate RHC references stay out of scope.

### Compatibility / recovery consequences
- Declared **NO**: no new runtime mutation domain and no same-save compatibility edge; no Patch 1A registry or Patch 1B dispatcher change.
- The only export-classification changes are `README.md` COPY -> GENERATE_EMPTY and the named skeletons (`characters/madma/NARRATIVE_DIRECTION.md`, the empty `npc/profiles/bor-family/`) EXCLUDE with their stale folder skeletons omitted; every other tracked path keeps its disposition and COPY bytes/modes are unchanged. Consumers get a canvas whose root README is campaign-neutral and which contains no named Madma path or directory.

### Verification evidence
- Positive: a fresh exact-HEAD export has a neutral root README (byte-equal to the policy constant, no identity token), no `characters/madma` file or folder, a clean `reality:campaign-root`, and a receipt recording `identity_acceptance` with `violations: []`.
- Negative (red before / green after): a synthetic policy that ships the RHC README as COPY and one that recreates the empty `characters/madma/` skeleton each fail the export closed before output creation; and contamination injected into the completed output -- an identity-bearing `characters/madma/` file or empty named directory, a root README altered after the precheck to assert the campaign, and a token-free unlisted extra path -- each fail the export closed with no accepted receipt written, where the previous exact head instead certified the predicted pre-write tree. The path-kind and byte-provenance siblings are proven too: a root README or a regular non-content file substituted by a symlink to a neutral external file fails the no-follow kind contract; a token-free but altered materialized regular file (accepted at the previous exact head, which held only the intended blob SHA) fails the byte attestation; a synthetic legitimate Git `120000` COPY symlink is accepted by its exact `readlink` target and a substituted target fails; an unreadable/unscannable expected directory (with a hidden unlisted child) is refused rather than silently dropped from the inventory; a post-write executable downgrade (0755 → 0644, bytes unchanged) and an accidental execute bit (0644 → 0755) are both refused, while a clean export keeps `.githooks/pre-commit` at 0755 and non-executable surfaces at 0644; and a clean export passes the kind/inventory, byte and POSIX-mode attestation with accepted evidence, recording a capability-honest `artifact_attestation` whose `posix_mode` is `verified` on a POSIX host that fully passed the mode contract and `not_observable` (never a silent `verified`) when the host cannot observe permission bits. `ENGINE_VERSION` stayed `1.1.0`; reference integrity, emitted RT01 workflows and the portable suite are unchanged.

---

## 2026-10-15 - POST-EV2-Z6: exported product acceptance

### Why this milestone exists
PORT-01's Bootstrap PR #4 stayed red after Z5: the copied RT01 runtime workflow's shard commands invoked four test trees the policy excludes (`tests/ev2121`, `tests/post_ev2_2`, `tests/post_ev2_9`, `tests/post_ev2_10`), so two shards ran pytest arguments that collect zero shipped tests, while the exporter's reference-integrity check blessed every invocation because `present` included the preserved skeleton directories. A green export check did not yet mean the exported product's shipped CI was coherent.

> Architecture sentence: **a shipped workflow's executable dependencies must resolve to real exported files — never to an empty preserved skeleton — and the shipped runtime workflow is the policy's one explicit, proven portability adaptation, generated as a fixed constant and bound to the source workflow by a sync guard.**

### Durable design
- **Species-aware reference integrity.** A Markdown hyperlink (navigational) may still be satisfied by a preserved skeleton directory; an executable workflow dependency (`run:` argument, static `working-directory`) is satisfied only by a real exported file at or under the resolved path; a static `working-directory` must be a real exported DIRECTORY -- validated by an exported file at or under it, never by an exported file at the exact path itself (a runner cannot change directory into a file) and never by an empty preserved skeleton or all-EXCLUDE directory; a local `uses: ./action` step only by that action's shipped `action.yml`/`action.yaml` metadata file, and a repo-root `uses: ./` only by the exported root's own `action.yml`/`action.yaml` (never silently discarded as an empty path). A static route naming a path that exists nowhere in the source tree fails the export closed (it cannot resolve in any exported tree either); a path operand carrying any part of an Actions `${{ ... }}` expression -- including a path fragment separated from the expression only by a slash within one shell argument, such as `${{ matrix.dir }}/tests/unit` or `tests/${{ matrix.dir }}/unit.py`, and including an expression with internal whitespace like `${{ matrix.dir }}` -- is recorded in the receipt's `unresolved_dynamic_routes` as explicitly classified, consciously unproven — never silently accepted, never claimed as proved; classification is per shell operand, so a whitespace-separated later argument (`${{ matrix.dir }} unit.py`) stays a statically checked operand. Deduplication is by normalized route *and* dynamic/static classification, so the same route occurring both statically and dynamically (in either order) keeps both classifications: a missing static executable dependency is not suppressed by a dynamic mention, and the dynamic receipt entry is not suppressed by a static occurrence. A step whose effective `working-directory` cannot be statically resolved (an Actions `${{ ... }}` expression, an absolute/`~`, `..` escape or backslash path) is likewise unlocatable: its repo-relative operands are recorded as consciously unproven in the same `unresolved_dynamic_routes` channel (with the unresolvable working directory itself) rather than silently proved as though rooted at the repository root. GENERATED control-plane surfaces are checked through their policy-generated bytes, not just COPY blobs.
- **Ownership audit before any policy/workflow change.** The four invoked trees are real-PostgreSQL runtime proofs over synthetic data whose test code carries RHC campaign-identity strings (`item:vampire`/`character:gork` in `tests/ev2121`/`tests/post_ev2_2`, `character:mugen` in `tests/post_ev2_9`/`tests/post_ev2_10`). Under the durable no-RHC-fixture-names invariant they are source-only proof: never COPY them merely to silence an empty-directory pytest argument, never strip them from the source workflow merely for green. Their proof stays live in source CI.
- **The generated runtime workflow is the single portability adaptation.** `bootstrap/CLEAN_CAMPAIGN_EXPORT_POLICY.json` classifies `.github/workflows/rt01-runtime.yml` GENERATE_EMPTY; its exported bytes are a fixed policy constant equal to the source workflow minus exactly the four source-only pytest arguments. The source workflow is unchanged for source CI (it keeps proving the four suites); the shipped workflow references only shipped executable surfaces. A structural Z-proof sync guard proves the generated bytes equal the source workflow minus exactly the audited arguments across the whole top-level contract as well as the job bodies (with a non-vacuous top-level-divergence negative), so the two cannot drift silently.
- **The proof is the exported product's own CI.** The Mission-local clean-canvas job executes every exported shard command verbatim inside a fresh independent canvas with the shipped PostgreSQL 15/17 services and fails closed on a non-zero exit or a shard that proves nothing (zero tests passed — a DB-gated proof silently skipping is a failure, not a pass). The Z proof adds the Python import-closure guard (syntax + absolute imports against exported files/stdlib/declared requirements) with a non-vacuous negative, and negatives for every new failure class.
- **Three non-overlapping acceptance layers.** Layer A is the official `rhysd/actionlint` (pinned v1.7.12, release archive SHA-256 verified before extraction/execution) linting the two ACTUAL emitted workflow bytes from outside the emitted tree, shellcheck/pyflakes disabled, with a deliberately invalid fixture proving the gate is non-vacuous; actionlint owns GitHub Actions syntax/expressions/schema, and its own docs confirm it does NOT report a missing local action directory, so it complements -- never replaces -- the exporter's `uses: ./` metadata and static `working-directory` path-kind checks. Layer B is the exporter (exact tree inventory, deterministic bytes/modes, path kinds, static repo-local dependency closure, honest `unresolved_dynamic_routes` receipt). Layer C is actual execution of the shipped shard commands and the full portable suite in fresh independent canvases. No single homegrown parser is asked to emulate the whole runner.

### Deliberate non-goals / deferred ownership
- No runtime/mechanic/schema/migration change and no `ENGINE_VERSION` bump; no Bootstrap/Copier or PORT-01 patch (PORT-01 owns re-exporting/resyncing Bootstrap PR #4 after Z6 merges and rerunning its downstream CI); no hard-write-boundary redesign — the shipped fence's repo-contextual default-deny contract is assessed and documented, and a dedicated hard-write-boundary product change stays separately owned; no general static shell interpreter (dynamically computed dependencies stay recorded-as-unproven, not magically resolved).

### Compatibility / recovery consequences
- Declared **NO**: no new runtime mutation domain and no same-save compatibility edge; no Patch 1A registry or Patch 1B dispatcher change.
- The only export-classification change is `.github/workflows/rt01-runtime.yml` COPY → GENERATE_EMPTY (same path, generated bytes, mode 100644 as before); every other tracked path keeps its disposition and COPY bytes/modes are unchanged. Exported-canvas consumers get a workflow whose shard commands reference only shipped test trees.

### Verification evidence
- Negative before fix (reproduced): fresh canvas from base `2a1eae0`; the exported shard commands `pytest tests/ev2121 tests/ev213` and the post-EV2 frontier command invoked four source-only trees that ship zero test files (`pytest tests/post_ev2_2` alone: "no tests ran", exit 5), and the pre-Z6 exporter accepted all four routes as present. Post-fix, forcing the shipped workflow back to its source bytes fails the export closed on all four skeleton-only routes.
- Shipped shard commands execute inside a fresh independent canvas (no RHC ancestry, no remotes) against real disposable PostgreSQL 15 and 17: all four shard commands green (263 + 163 + 338 + 72 + 483 tests passed across the shards), DB-gated proofs actually executing, none silently skipping.
- Exported Python import closure clean (119 exported `.py` files, 616 absolute import edges, zero unresolved); exported suite still free of RHC fixture names; Z proof green with the new guards and negatives; `ENGINE_VERSION` stayed `1.1.0`. The shipped hard-write-boundary fence was assessed portable-by-contract (default deny in a fresh repository until that repository establishes its own authority issue; `save/*` lane needs no issue). Merge identity recorded at closeout.

---

## 2026-10-15 - POST-EV2-Z5: portable exported test boundary

### Why this milestone exists
POST-EV2-Z4 proved a copied executable surface executes inside the exported canvas, but PORT-01's wider downstream full-suite run then exposed the complementary failure class: 13 exported tests still assumed historical RHC commit objects exist in the generated independent repository. The clean canvas is a structural copy-out with no RHC ancestry and no remotes, so a fixture that hard-codes an RHC commit SHA is impossible portable data — and a green source check does not mean the exported product is runnable.

> Architecture sentence: **source-history/provenance proofs stay in RHC, reusable Git-anchor behavior proofs ship but build their own temporary synthetic Git history, and a fresh independent exported repository runs the intended portable suite green with zero RHC ancestry.**

### Durable design
- **Reusable anchor tests are self-contained.** `tests/test_offscreen_anchor_context.py`, `tests/test_offscreen_run_resolution.py` and `tests/test_run_validation.py` build a temporary synthetic Git repository (`git init -b main` plus one committed tree carrying the reusable Scenario/Hook records and their schemas), redirect the validator's Git seam to it, and carry that synthetic commit as each anchored record's `campaign_anchor.base_commit`. The exercised semantics are real Git (`cat-file` object type, `merge-base --is-ancestor` against the synthetic `main`, `ls-tree`/`show` for anchored content and schema reads) — no production behavior is stubbed, skipped, deleted, or converted into a blanket ignore.
- **Provenance stays in source RHC.** `tests/post_ev2_1/test_clean_bootstrap_equivalence.py` proves the clean baseline is a byte-exact replay of a pinned historical RHC frontier; that is RHC source-repository provenance, not a portable Bootstrap invariant, so its disposition moves `COPY` → `EXCLUDE`. It remains a live RHC proof: `rt01-runtime.yml` runs `pytest tests/post_ev2_1` with `fetch-depth: 0` and PostgreSQL services.
- **The proof is the exported product.** The Mission-local clean-canvas workflow gains a `portable-suite` job that exports exact HEAD, initializes a brand-new independent repository on `main` (no remotes, no ancestry), and runs the full exported suite. The Z proof verifies that the full-suite command's `working-directory` is the exact canvas the job exported into — not merely that the command text exists — and a negative proof shows the check fails when the suite runs outside the canvas.

### Deliberate non-goals / deferred ownership
- No Git-anchor runtime/mechanic change, no Bootstrap/Copier or PORT-01 patch, no engine/runtime/campaign/state change, no `ENGINE_VERSION` bump, no blanket test ignore. PORT-01 still owns rerunning its downstream full-suite proof after Z5 closes.

### Compatibility / recovery consequences
- Declared **NO**: no new runtime mutation domain and no same-save compatibility edge; no Patch 1A registry or Patch 1B dispatcher change.
- The only export-classification change is the intentional `COPY` → `EXCLUDE` of the RHC provenance proof; every other tracked path keeps its disposition and COPY bytes/modes are unchanged.

### Verification evidence
- Source: the four portable anchor suites green (90 passed); POST-EV2-Z proof green (98 passed, 3 historical skips); `git diff --check` clean; local HWB-01 fence authorized the exact declared budget.
- Fresh exported canvas from exact HEAD (independent `main` repository, no RHC ancestry, no remotes): the 13 PORT-01 ancestry failures are gone and the full exported suite is green apart from Windows-only `test_write_boundary` artifacts (`python` Store-alias stub, NTFS executable-bit) that pass on Linux. Merge identity recorded at closeout.

---

## 2026-10-15 - POST-EV2-Z4 repair: copied-suite ownership split, context discriminator removed

### Why this repair exists
Every Z4 repair round that hardened the copied POST-EV2-14 suite's canvas-only skip discriminator surfaced the next discriminator defect in exact-head review (incomplete Z3 remap invariant, then schema-malformed genesis, then non-hardened JSON parsing, then negatives that were not parser-discriminating) — and the final round exposed the root cause behind the repeated findings: source/factory-only assertions had been placed inside a COPY-shipped module, forcing that module to infer source-vs-canvas context at all. A discriminator that exists only to skip assertions that should never have lived in the shipped module is itself the failure class; hardening it further cannot terminate the defect chain.

> Architecture sentence: **a COPY-shipped suite carries only portable assertions; source/factory wiring assertions live in the EXCLUDE-owned factory proof, so there is no context discriminator left to be the weak link.**

### Durable design
- **Portable copied suite.** The copied POST-EV2-14 brainstorm-lab suite keeps the complete portable bounded-lifecycle proof (including resolving the primary reality by its structural role — the unique parentless root record — instead of one RHC-only source path) and drops the three source/factory-only assertions plus all discriminator machinery, so it runs unchanged in source RHC and inside an exported canvas with no context inference and no skips.
- **Re-homed factory assertions.** The equivalent source wiring assertions moved into `tests/post_ev2_z/test_clean_campaign_export.py` — the EXCLUDE-owned factory proof that never ships in the exported tree: the source Entity V2 workflow runs the POST-EV2-14 suite, the export policy classifies every POST-EV2-14 surface as COPY, and a fresh export of exact HEAD contains them. They now run unconditionally in source RHC instead of being gated on an inferred context.
- **Negatives removed with the discriminator.** The discriminator-specific negative proofs (neutral-named child reality, schema-malformed genesis, duplicate-key/non-standard-constant/overflowing-number genesis) were deleted rather than replaced by another discriminator layer; nothing remains that needs them.
- **Unchanged guards.** The stale-identity guard (no COPY-shipped executable/structured surface may carry the remapped RHC-only primary-reality identity token), its trigger/admission coverage proof, and the Z workflow's inside-canvas execution of the copied POST-EV2-14 suite are all preserved unchanged.

### Deliberate non-goals / deferred ownership
- No exporter, policy, classification, workflow or reality-semantics change; no new general CI framework; no campaign data change; no `ENGINE_VERSION` change; no PORT-01 or downstream shim work (PORT-01 still owns consuming the corrected export and rerunning its preflight).

### Compatibility / recovery consequences
- Declared **NO**: no new runtime mutation domain and no same-save compatibility edge; no Patch 1A registry or Patch 1B dispatcher change.
- The copied suite proves strictly the portable POST-EV2-14 lifecycle guarantees; the factory gates it previously duplicated under an inferred context are owned by the Z factory proof and run unconditionally in source RHC.

### Verification evidence
- Source POST-EV2-14 suite green with no skips (77 passed); POST-EV2-Z exporter/classification/reference/determinism suite green including the re-homed assertions, the stale-identity guard and its negative proof and the trigger/admission coverage proof; the copied suite executed green from inside a fresh clean-canvas export initialized as a repository; `ENGINE_VERSION` stayed `1.1.0`; `git diff --check` clean and every changed file inside the machine Surface Budget. PR #255 merged exact final reviewed HEAD `9fded31eb812729ed38f488081ec43ee954c01a2` as main squash commit `9b24e5227be6ca08cc0b3f937d9b115b9a866bcb`; exact-main story-retrieval, Clean campaign exporter proof, Clean canvas representative proofs, and validate all passed.

---

## 2026-10-14 - POST-EV2-Z4: copied-test portability + inside-canvas runnable proof

### Why this milestone exists
PORT-01 returned the first concrete export-side portability blocker after POST-EV2-Z3: the Z3 remap correctly moved clean genesis to the campaign-neutral primary-reality path, but the COPY-shipped POST-EV2-14 brainstorm-lab test still hard-coded the RHC-only source path, so the shipped reusable test surface failed immediately inside the exported canvas while every source-repository check stayed green. A green source check did not yet mean the exported product was runnable; RHC must prove its exported test surface executes before downstream consumes it.

> Architecture sentence: **a COPY-shipped test surface resolves primary-reality identity by structural role and gates factory-only assertions on the factory's actual presence, while RHC CI executes the shipped suite inside the exported canvas and fails closed on any copied executable surface still carrying the remapped RHC-only identity.**

### Durable design
- **Structural primary-reality resolution in copied tests.** The copied POST-EV2-14 suite no longer hard-codes RHC's canonical primary-reality path; it resolves the primary record as the unique parentless root record in the shipped registry — RHC's canonical record in the source repository, the campaign-neutral genesis root in a clean canvas — matching the Z3 law that the primary reality is a semantic role, not a campaign literal.
- **Factory-only assertions are presence-gated, not deleted.** The three copied assertions that police RHC-only factory machinery (the source CI workflow, the export policy, the exporter) skip when that machinery is legitimately absent from an exported tree and remain active in the source repository, so the copied suite is runnable in both contexts without weakening any source-repository gate.
- **Inside-canvas execution is the proof.** The mission-local Z workflow's clean-canvas job now runs the shipped POST-EV2-14 suite from inside the exported canvas alongside the existing representative proofs, so a stale copied reference fails in RHC CI instead of first surfacing downstream; the copied test surface is also a workflow trigger so this Mission's own repair exercises the proof.
- **Durable class guard.** A new Z-suite guard fails closed when any COPY-classified executable/structured surface (everything except prose `*.md`, which may legitimately reference RHC source material) carries the RHC-only primary-reality identity token, with a synthetic negative proof that the guard catches the exact regression class rather than passing vacuously.

### Deliberate non-goals / deferred ownership
- No exporter, policy, classification or reality-semantics change; the exporter/policy were already correct.
- No PORT-01 or downstream shim work; PORT-01 still owns consuming the corrected export and rerunning its preflight.
- No new general CI framework, no runtime/SAVE/SQL/gameplay mechanics, no campaign data change, no `ENGINE_VERSION` change.

### Compatibility / recovery consequences
- Declared **NO**: no new runtime mutation domain and no same-save compatibility edge; no Patch 1A registry or Patch 1B dispatcher change.
- The copied suite keeps proving the same POST-EV2-14 guarantees in the source repository; only its portability inside an exported canvas changed.

### Verification evidence
- Reproduced the in-canvas failure first (4 failures inside a fresh clean-canvas export), then proved locally: source POST-EV2-14 suite green; the copied suite green when executed from inside a fresh clean-canvas export initialized as a repository; POST-EV2-Z exporter/classification/reference/determinism suite green including the new guard and its negative proof. Merge identity is recorded at closeout by the Orchestrator.

---

## 2026-10-14 - BTH-01 → POST-EV2-Z3: access boundary + proof hygiene + disposable non-canon labs + portable primary reality

### Why this milestone exists
After the clean-canvas/version milestone, four adjacent portability and control-boundary problems remained. RHC needed a deterministic semantic access seam for player/DM/BTH reads without duplicating authentication; the original Z/Z.1 proof still contained three historical mission assertions that had fossilized into global law; disposable Prequel/Sequel/What-If exploration needed a reusable NON-CANON lifecycle without becoming canonical reality or a second save authority; and PORT-01 proved the reusable reality engine still hard-coded Campaign #1's `reality:rhc-primary` identity into every future clean campaign.

> Architecture sentence: **Reader access is request-time admission over trusted identity, historical Mission proof is not permanent repository law, disposable brainstorm state is NON-CANON scratch with no merge-back authority, and the primary-reality role is structural campaign-neutral engine semantics rather than one campaign's literal ID.**

### Durable design
- **BTH reader exposure is not character knowledge.** BTH-01 consumes a trusted upstream principal and an explicitly classified semantic request, then returns exactly `ALLOW`, `BLOCK` or `SPOILER_CONFIRM`. Player access follows the owner of information: own controlled-character context may be admitted, another owner's private knowledge remains blocked, and BTH acknowledgement only authorizes reader exposure. It creates no knowledge mutation, no auth system, no frontend principal inference and no permission from prompt text.
- **Mission-local proof stays mission-local.** POST-EV2-Z2 gates only the three historical Z/Z.1 branch/base/surface assertions to their original mission context, including detached CI recognition, while durable exporter/classification/reference-integrity/determinism proofs remain active globally. The repair changes proof scope, not exporter behavior.
- **Disposable exploration is a separate NON-CANON lifecycle.** POST-EV2-14 provides begin / close / reset around caller-supplied isolated scratch state with exact origin/checkpoint provenance. CLOSED stays inspectable but non-writable; reset is recoverable and must prove structural cleanup; surviving metadata contains lifecycle/provenance only and never story payload.
- **Simpler state space beats validator accretion.** Repeated crash-window findings during POST-EV2-14 exposed that the first reset transaction carried too many independently coherent states. The final design deliberately collapses recovery to `lab.lock.json` + `reset.pending.json` + one fixed `active.tombstone` + one latest `last-reset.json`, with one complete-or-null provenance object and `reset_id` correlation.
- **Primary reality is a semantic role, not a campaign literal.** POST-EV2-Z3 removes the engine-wide `reality:rhc-primary` constant. A valid reality set has exactly one parentless root; every other reality declares exactly one admitted parent; parent resolution and acyclicity remain mandatory. RHC's own `reality:rhc-primary` record remains unchanged campaign canon.
- **Clean genesis is neutral end-to-end.** The Z exporter maps the RHC source primary record to `realities/registry/campaign-root.json` carrying `reality:campaign-root`; the exported neutral registry validates with the same engine validator. The remap contract rejects dot/normalization aliases, collisions, file-directory straddles and targets inside EXCLUDE-owned namespaces rather than comparing unsafe raw path strings.
- **CI admission is part of feature completeness.** Z3-owned reality surfaces participate in the dedicated Z workflow's `pull_request` and main-`push` path filters, while Entity V2 continues executing the reality registry/inheritance proof. `ENGINE_VERSION` remains the single version source and advances to `1.1.0`; receipt/tests derive from that source instead of duplicating a literal.

### Durable lessons
- Authentication/trusted identity and semantic context admission are different layers. A request-time access policy may consume trusted identity, but it must not infer or mint that identity itself.
- Historical mission assertions are evidence, not eternal product law. Preserve them in their original context while keeping only true durable invariants global.
- Repeated coherence findings can be evidence of excessive representable state. When bounded repairs keep creating new crash-window combinations, simplify the state machine instead of adding another ring of validators.
- Campaign-specific identity belongs to campaign data, not reusable engine mechanics. Validate structural roles by invariant, and validate normalized export destinations against the actual policy boundary rather than trusting raw path strings.

### Affected surfaces
- BTH-01: `scripts/context_access.py`, `tests/test_context_access.py`, `docs/BTH-01-PLAYER-DM-ACCESS.md`, BTH/knowledge protocol docs, existing Entity V2 CI admission and clean-export classification.
- POST-EV2-Z2: `tests/post_ev2_z/test_clean_campaign_export.py` only.
- POST-EV2-14: `scripts/brainstorm_lab.py`, `tests/post_ev2_14/test_brainstorm_lab.py`, `docs/POST-EV2-14-DISPOSABLE-BRAINSTORM-LAB.md`, plus bounded repository/CI/export-classification integration shipped by the Mission.
- POST-EV2-Z3: reality schema/validator/proof/docs; clean-export policy/exporter/proof/docs; dedicated Z workflow path admission; `ENGINE_VERSION`.
- This continuity patch changes only `CHANGELOG.md` and `ENGINE_CHANGELOG.md`; it changes no shipped implementation.

### Deliberate non-goals / deferred ownership
- Trusted account/session/role/controlled-character binding and product gateway wiring remain with CCC; BTH-01 does not duplicate authentication.
- POST-EV2-Z2 is not a general weakening of Z proof and does not change exporter semantics.
- POST-EV2-14 does not create canonical reality identity, automatic merge-back/canon promotion, hosted save-slot cloning, Supabase/RT01 mutation, multi-lab concurrency, hostile-filesystem hardening or CCC/platform provisioning.
- POST-EV2-Z3 does not migrate RHC's canonical primary reality, add runtime active-reality state, owner-specific reality overlays/divergences, carry-out/reconciliation, retrieval/RAG, Copier logic or CCC provisioning.
- PORT-01 now owns consuming the corrected clean export and rerunning downstream preflight; it must not reimplement primary-reality semantics.

### Compatibility / recovery consequences
- All four patches declare **NO** new runtime mutation domain and **NO** same-save compatibility edge; Patch 1A/1B require no update.
- BTH acknowledgement has no persistence side effect and cannot grant character knowledge.
- Z2 changes only where three historical assertions execute; durable clean-export behavior remains unchanged.
- POST-EV2-14 scratch state is explicitly NON-CANON and disposable; reset recovery never creates merge-back authority.
- Z3 preserves the existing RHC `reality:rhc-primary` record unchanged while allowing future campaigns to use different valid root IDs. `ENGINE_VERSION 1.1.0` is the comparable marker for this reusable-engine capability expansion, while exact Git commit identity remains separately preserved.

### Verification evidence
- **BTH-01** — PR #245, exact final reviewed HEAD `082b80fade5995809a09d9d3d21981d09fe92524`, squash merge `52851fb8c5d92c0aa28866af18ee56a7a05f34c1`.
- **POST-EV2-Z2** — PR #247, exact final reviewed HEAD `a6459582abfda534344da8f184a7873642fc6006`, squash merge `ee3b089473d56a2992e10510816a0e8806dcff14`.
- **POST-EV2-14** — PR #249, exact final reviewed HEAD `1ea19aa707ce7ebb5d5d5d0d1ab64abcf2e0bbe6`, squash merge `7cd7e2a15a0d46ca80103fc5b4b410d3b76b84f4`; final simplified model passed exact-head CI and fresh Codex review clean.
- **POST-EV2-Z3** — PR #251, exact final reviewed HEAD `c63ce0331dccde5fabc92ade25ee6d1d28299080`, squash merge/current base `a1b387075cd7d6aa619b28233f9360a9e6741068`; final exact-head Codex review clean and exact-main Story Retrieval, Entity V2 and POST-EV2-Z push proofs green.

---

## 2026-10-13 - CI Integrity → POST-EV2-Z.1: CI integrity + Clean Campaign Canvas / Engine Version Stamp closeout

### Why this milestone exists
Three completed engineering milestones had advanced main beyond the ledgers. Before real campaign data import, a green check had to mean the intended tests actually execute and a relevant data change is actually checked — 13 tracked Python test modules were not targeted by any runnable CI job, and the committed canonical root campaign JSON had no read-only validation. RHC then needed one deterministic clean campaign canvas as the input for RHC-Bootstrap (PORT-01): a structural copy-out that keeps reusable engine/runtime/mechanics while excluding the one living campaign's instance data, canon, story and history — without creating a second maintained engine fork or a second campaign authority. Finally, PORT-01's planned Copier `check-update` drift detection needed a *comparable* engine version identifier across campaign repos: the exporter pinned each export to an exact Git commit, but a raw commit SHA carries no ordering semantics.

> Architecture sentence: **CI admission proves existing tests actually execute within the existing proven job topology; the Z exporter is a deterministic, strictly structural factory boundary — not a second runtime, engine fork or campaign authority; and Z.1 adds one comparable SemVer engine-version source while exact Git commit identity remains separately preserved.**

### Durable design
- **Admission into existing proven jobs, not a new interpreter.** CI Integrity routed the eight omitted pure-Python modules into explicit executable steps in the existing Entity V2 workflow, and the `tests/hwb02`, `tests/ev2121` and `tests/ev213` real-PostgreSQL families into the matching existing RT01 shards as separate pytest processes (avoiding fixture/harness import collisions), extending both PR and push path filters for those families. The four-shard parallel topology and the stable `prove-runtime-foundation` aggregate check name are preserved; there is deliberately no serial all-tests-on-every-PR monolith and no general GitHub Actions/shell/pytest parser.
- **Read-only, path-exact canonical JSON checking.** The canonical-root validator checks only the exact six repository-relative canonical root documents, resolved from the repository root rather than the caller's working directory, and never selects a contract by basename — an external same-basename file receives no contract. It reuses the existing strict JSON parse hooks (duplicate keys, non-finite numbers) and applies only bounded owner-declared vocabularies; per-entity state/knowledge schemas are intentionally not applied to root document shapes. It checks committed bytes only: no writes, normalization, inference or generation, and no claim of universal future-test-inventory enforcement.
- **Structural-only, file-by-file export classification.** POST-EV2-Z classifies every tracked path exactly once as COPY / EXCLUDE / GENERATE_EMPTY using exact paths and (EXCLUDE-only) directory prefixes with longest-match resolution; unclassified and ambiguous paths fail closed, and the Classification Granularity Rule forbids folder-level COPY. No content scanning, name detection or text rewriting participates in classification. COPY surfaces are fetched byte-for-byte from the exact pinned (peeled) commit with Git modes preserved; GENERATE_EMPTY roots are emitted as contract-valid EMPTY/UNKNOWN state from fixed policy constants; repeated export from the same HEAD is deterministic; overwrite, source/output overlap and non-commit `--ref` targets are refused.
- **Reference integrity is explicit and total.** A retained control-plane route must resolve inside the exported tree. The check covers every route species that exists — Markdown hyperlink targets and workflow `run:` command arguments — by parsing workflow YAML with a real parser (PyYAML) and structurally walking `jobs.*.steps[].run`, so every YAML-equivalent key spelling decodes exactly as GitHub Actions decodes it, and by resolving each relative argument against the step's effective working directory. Routes into excluded source paths fail the export closed; placeholders and runtime facades that never resolved to a source path are ignored.
- **One comparable version source, exact identity preserved separately.** POST-EV2-Z.1 added exactly one new versioning source of truth — the root-level `ENGINE_VERSION` file carrying a SemVer string with ASCII-only numeric identifiers — rather than deriving a second authority from history or packaging. The exporter reads it from the exact source commit (like the portability policy), so the receipt's `engine_version` is bound to the exported tree and independent of working tree, branch name or history ordering; the exact `source_commit` remains separately recorded. A missing or malformed version source fails the export closed.
- **The proof derives from the source, never pins the value.** Z.1 tests derive the expected version from `ENGINE_VERSION` and assert receipt equality, so a legitimate future bump needs no test-literal edit; the mission-local workflow lists `ENGINE_VERSION` in both `pull_request.paths` and `push.paths`, asserted independently so one event cannot mask a missing trigger in the other; and a version-only change is sufficient to schedule the existing mission-local proof. The pre-merge startup repair removed the unavailable `runner` context from job-level `env` and derives the temporary canvas path only at step/runtime locations where that context exists, preserving the two existing jobs and their proof semantics.

### Durable lesson
A green check only means something when the intended tests actually execute and a relevant data change is actually checked — admission into existing proven jobs beats inventing a general CI interpreter. Export classification must stay structural and deterministic, and when a reference check must understand a structured format, parse the structure with a real parser and compare decoded values instead of pattern-matching textual spellings; a copied control/router file's internal references need an explicit automated resolution check across every referencing mechanism. Comparable metadata and exact identity are separate facts: keep one source of truth for each, let proofs derive from the source rather than pinning the current value, and keep a workflow's own trigger surface inside the proof it protects.

### Affected surfaces
- CI Integrity: `.github/workflows/entity-v2-identity.yml`, `.github/workflows/rt01-runtime.yml` (modified); `scripts/validate_canonical_root_json.py`, `tests/test_canonical_root_json.py` (new).
- POST-EV2-Z: `bootstrap/CLEAN_CAMPAIGN_EXPORT_POLICY.json`, `scripts/export_clean_campaign.py`, `docs/POST-EV2-Z-CLEAN-CAMPAIGN-EXPORT.md`, `tests/post_ev2_z/test_clean_campaign_export.py`, `.github/workflows/post-ev2-z-clean-canvas.yml` (new); one authorized PyYAML dependency line in `requirements.txt`.
- POST-EV2-Z.1: `ENGINE_VERSION` (new); the Z policy, exporter, proof, doc and mission-local workflow (modified: version stamping, trigger coverage, startup repair).
- This closeout updates only `CHANGELOG.md` / `ENGINE_CHANGELOG.md`; it does not alter the shipped machinery above.

### Deliberate non-goals / deferred ownership
- No runtime, SAVE, SQL, schema, mechanics, gameplay-rule or campaign-data change in any of the three milestones; CI Integrity created no new gameplay or policy rules.
- CI Integrity is not a universal future-proof test interpreter and built no general YAML/shell/pytest parser or duplicate test-ownership registry; repository-wide always-on CI classification enforcement remains a separately authorized CI Mission, if ever needed.
- RHC-Bootstrap repository placement/publication/provisioning, Copier template work, and consuming the `engine_version` receipt field: PORT-01.
- Isolated per-campaign database/save-slot provisioning: CCC-PLATFORM-01.
- Real RHC campaign history import: its dedicated later intake gate; moving RHC's own campaign into a save slot: a later, separate gate.
- Engine version-bump policy/cadence (what counts as a breaking engine change, when humans bump it): a human-owned policy decision, deliberately not solved by Z.1.
- Systematic scrub of surviving RHC example names (`item:vampire`/Madma/Gork) in genuinely reusable implementation-comment/baseline surfaces, and advancing the pinned equivalence-test frontier: explicitly deferred; the Z review accepted this residual risk and it is not reopened here.
- Hostile-filesystem / path-race hardening of the exporter: deliberately out of scope (trusted local/CI build tooling).

### Compatibility / recovery consequences
- None of the three milestones adds a runtime mutation domain or a same-save compatibility edge; no Patch 1A registry or Patch 1B dispatcher change was required.
- The Z exporter reads only Git objects and writes only outside the source tree; an export leaves the source tree unchanged, and receipts from before Z.1 simply lack `engine_version` while exact source-commit identity remains the durable pin.
- Existing global workflows are unchanged by Z/Z.1; the mission-local clean-canvas workflow is additive and trigger-scoped to its own surfaces.
- Branch protection/check configuration and HWB trusted controls remained with their existing owners throughout.

### Verification evidence
- CI Integrity — PR #232, final PR HEAD `b2d58c11ac0348ba13782796bd71538ffe1f5940`, merge `64260bc53575016a848283196c4b1bdd947cb5d4`; post-merge push proof green (all four RT01 shards, stable `prove-runtime-foundation`, Entity V2 `validate`, story-retrieval) per the JOHNNY #230 closeout.
- POST-EV2-Z — PR #239 (squash), exact final HEAD `accbb20c6e75a37a330bdb750ac321ea1b6b37d1`, merge `80cf8aa4a4cd3e10922dc0e3b92d4e8ab3cdf489`; five converging exact-head Codex rounds ending clean, final export with 0 dangling routes, post-merge CI green per the JOHNNY #238 closeout.
- POST-EV2-Z.1 — PR #241, exact final HEAD `f30ae0e8f72a089348bdb5fd3d3c034fc7dc26a0`, merge `9eb25499287c9f3a3de7dda28d85a5a77e83b6b4` (current approved main); three converging Codex rounds plus one pre-merge startup-failure repair, each re-proven, per the JOHNNY #240 record.

---

## 2026-10-11 - POST-EV2-11.9 → POST-EV2-12.2: Reputation + Business Economy milestone closeout

### Why this milestone exists
After Begin Day and multi-day intake were stable, the Business path still needed four things before a real Business could safely resolve: one reusable Reputation rule, a way for an existing Begin Day consumer to hand owner-state changes into the already-existing publication path, a complete validated Business input package, and one deterministic resolver/consumer that could execute those rules without becoming a second RNG, SAVE or state owner.

> Architecture sentence: **Business definition/config != Business instance != mutable Business state != daily resolution != immutable history. `live_status.businesses` remains the sole Business mutable-state owner; POST-EV2-8 remains the RNG root; POST-EV2-11.9 remains the Reputation delta/tier owner; Begin Day remains an opaque conductor; and Stage C contributes exactly one complete-set Business consumer returning one `businesses` state patch through the existing RT01 path.**

### Durable design
- **Reusable Reputation before economy.** POST-EV2-11.9 introduced a pure deterministic Business-owned 0–100 Reputation primitive with explicit consequence classes, bounded tiers and high-standing positive-gain asymmetry. Owners/workers may be contextually associated with a Business's standing, but no duplicated personal/faction ledger or automatic obedience/relationship/knowledge rule was created.
- **Permanent proof admission without topology drift.** POST-EV2-11.9A placed the Reputation test family in the existing post-EV2 RT01 shard and both PR/push triggers while preserving the four-shard layout and stable aggregate proof gate.
- **Transport is not ownership.** POST-EV2-11.10 lets one Begin Day consumer return an optional bounded top-level `live_status` `state_patch`. Begin Day deep-copies/transports it through the current publication candidate, rejects conflicting/unsafe patches, and never interprets the mechanic. Retry rehydrates published truth and does not rerun consumers.
- **Planner first, resolver second.** POST-EV2-12 Stage B added inert Business Cards plus a deterministic planner/validator and conditional dice manifest. POST-EV2-12.1 then completed the static/current-state contract: rolled/fixed revenue inputs, fixed daily cost, `active` separate from `funds_enabled`, approved 20/70/10 positive allocation, own-Recovery → HQ-Recovery → uncovered-loss waterfall, validated Business state and acyclic same-day `internal_sources`.
- **No repair arithmetic without an explicit basis.** POST-EV2-12.1.1 requires finite non-negative `facility_value` only for rolled Businesses that can suffer the approved Natural-1 repair mechanic; fixed-revenue Businesses reject that repair-only field. The planner preserves but never resolves it.
- **A validated package must carry what the resolver needs.** POST-EV2-12.1.2 retains the already-validated Reputation configuration inside normalized plan v4 instead of validating then discarding it. Stage C therefore receives one complete copy-isolated package and does not reopen config truth.
- **One deterministic Stage C resolver.** POST-EV2-12.2 resolves fixed/rolled revenue, existing active effect multipliers, same-day internal-source cost, Natural-1 repair and duration effects, POST-EV2-11.9 Reputation consequences, stored byproducts, positive allocation and deficit/repair waterfalls. Exactly one Business consumer owns the complete configured set and returns one top-level `businesses` patch; no per-Business consumers compete for that key.
- **Money is denomination-aware and owner-local.** Monetary arithmetic preserves value through gp → sp → cp conversion, rounds only below copper under the declared rule, reconciles splits at copper precision, and treats existing fund balances as Business-currency money rather than raw copper. Root-owned balances use the root Business Card's rounding rule; child-owned balances use the child's.
- **Hierarchy authority is corporation-local.** A Business follows its declared parent chain to its own root/HQ. Multiple independent corporation roots may coexist; cycles, broken/ambiguous chains, missing required balances or incompatible currencies fail closed. No company name or one-global-HQ assumption is hard-coded.
- **Open authoring, closed execution.** The generic Business contract can remain extensible for future Business-specific semantics, while Stage C applies only behavior it owns now — for example `stored` byproducts enter stock and unsupported dispositions fail closed rather than being silently invented.

### Durable lesson
A reusable subsystem becomes trustworthy when **validation, transport and resolution keep their ownership boundaries**. The planner must hand forward every validated rule the resolver genuinely needs; the conductor must transport owner-state without learning the mechanic; exact money must survive both denomination arithmetic and the real JSON persistence boundary; and generic hierarchy must derive authority from each corporation's declared parent chain rather than from a globally hard-coded HQ assumption.

### Affected surfaces
- Reputation: `scripts/reputation_resolver.py`, `config/REPUTATION_TEMPLATE.json`, `docs/POST-EV2-11-9-REPUTATION.md`, `tests/post_ev2_11_9/**`, and the existing RT01 workflow for CI admission.
- Begin Day transport: the POST-EV2-11 consumer contract/proof, including `tests/post_ev2_11/test_consumer_state_patch.py`, while retaining the existing RT01 publication owner.
- Business contract: `config/ECONOMY_TEMPLATE.json`, `scripts/business_plan.py`, Business docs/templates, `state/live_status.json#businesses`, and `tests/post_ev2_12/test_business_plan.py`.
- Stage C: `scripts/business_resolver.py`, `tests/post_ev2_12/test_business_day_resolver.py`, and `tests/post_ev2_12/test_business_begin_day_consumer.py`.
- This closeout updates only `CHANGELOG.md` / `ENGINE_CHANGELOG.md`; it does not alter the shipped mechanics above.

### Deliberate non-goals / deferred ownership
- No real RHC Business configuration, balances, stock, company hierarchy or campaign-state seeding.
- No FX mechanic, external-supplier pricing system, fleet/shipping/warehouse/scheduler/logistics subsystem, Security/org mechanic, Combat/Rest expansion, frontend/CCC authoring UI, new SAVE gateway, SQL schema or runtime mutation domain.
- No personal/faction Reputation ledger and no automatic propagation of Business standing into relationships, knowledge or obedience.
- Future Business-specific authoring semantics may extend the generic templates in their owning Mission; Stage C does not invent them early.

### Compatibility / recovery consequences
- None of POST-EV2-11.9, 11.9A, 11.10 or the POST-EV2-12 series adds a new runtime mutation domain or same-save compatibility edge.
- `live_status.businesses` remains the existing Business mutable-state owner; the Business consumer uses the existing Begin Day → RT01 publication path.
- Retry/rehydration continues to return already-published truth without rerunning Business RNG or consequences.
- Plan evolution is explicit: Stage B baseline → v2 in 12.1 → v3 in 12.1.1 → v4 in 12.1.2; the dice-manifest contract remains version 1.
- Existing Reputation semantics remain owned by POST-EV2-11.9; Stage C delegates rather than duplicating the formula.

### Verification evidence
- POST-EV2-11.9 — PR #195, final PR HEAD `add7edc9e2eeb63576098bbce5e08d9fc0e6296e`, merge `343b2093e3b6f2fc26936703e1064b94970fdef9`.
- POST-EV2-11.9A — PR #197, final PR HEAD `90369b19daae991ae205658259ddeccec99b2206`, merge `70761365f38c81d0d812a90fbb59a35991d01956`.
- POST-EV2-11.10 — PR #214, final PR HEAD `f1c98180dcd04f8fdb7b9b147a4ea25ad6130735`, merge `b090e08aaebc0b55313d2e5a450f80ee979cce94`.
- POST-EV2-12 Stage B — PR #218, final PR HEAD `6689cadf0c1a78491833c3211d8149a34cd3e1a5`, merge `b4d8102fc82e4ed16380aef9bcb4a48b4282e2e7`.
- POST-EV2-12.1 — PR #220, final PR HEAD `5bf6f35a1d3bac80eef9d53b9ec5b47ac99e75b1`, merge `48b4522b53ca8ffffbd972bfc8ee097c0b8d85fe`.
- POST-EV2-12.1.1 — PR #222, final PR HEAD `9236473d9e8a7d69fd44eaf2a57e0b12d20a4f5e`, merge `c8bd85c8f25b443918906e6d31d8da77292bf412`.
- POST-EV2-12.1.2 — PR #224, final PR HEAD `efb4eef5cd1fb4b2e6e79e906d61516670a05c45`, merge `7e1b704f2269c0f6ea336d13c6383de5ffff66fc`.
- POST-EV2-12.2 — PR #226, exact final reviewed HEAD `19c6d4919eab8d79b7e31843fae56a7f42eacfe6`, merge/main `3134e2e8a5a60f539b1f5274f6b6c37d651b35cb`; final exact-head Codex review clean and post-merge main proof green.

---

## 2026-10-01 - POST-EV2-11.5: Multi-Day Authoritative Gameplay Intake

### Why this milestone exists
Real tabletop play can already have covered several in-world days that RHC has not yet finalized, and one authoritative source document may carry all of them. An earlier attempt (PR #184, `POST-EV2-11.5 Historical Sync engine`) began building a dedicated historical-sync / bulk-history persistence engine. The durable question was not whether that engine could be hardened but whether RHC should tolerate a second historical persistence authority at all. Current repository truth already had the deterministic persistence it needed, so the correct outcome was to keep POST-EV2-11.5 as the semantic partitioner and let the existing ordinary Final Save remain the only writer.

> Architecture sentence: **POST-EV2-11.5 owns only the semantic partitioning of already-played multi-day authoritative gameplay. Each recognized completed day then delegates to the existing full ordinary one-day Final Save / SAVE contract unchanged — no Begin Day replay and no historical-sync / bulk-history / second Save Gateway / second Campaign Day authority.**

### Durable design
- **Semantic partition, deterministic persistence.** The DM agent recognizes completed in-world day boundaries from the supplied established facts and partitions the source into individual completed campaign days before any persistence begins.
- **One day per Final Save, in chronological order.** Each recognized day is finalized through the normal Save Completion Contract and the ordinary one-day repository-history path, never collapsed with another day into one finalized-day record.
- **No Begin Day replay.** Already-played days are established outcomes; Begin Day is live `N -> N+1` progression only and is never invoked, rerun or otherwise used to persist history, executing no live RNG, Rest, Business or Combat mechanics.
- **Ask, do not invent.** Ambiguous day boundaries, day numbering or canon status return to the Dungeon Master rather than being invented.
- **No new engine.** There is deliberately no dedicated Historical Sync engine, bulk-history admission lane, archive/import subsystem, second Save Gateway or second Campaign Day authority.
- **Existing DM correction/retcon authority preserved** for finalized history.

### Durable lesson
A multi-day source document is an **intake** problem, not a persistence problem: semantic day recognition belongs to the AI, while durable history belongs to the already-existing deterministic SAVE machinery. A bulk/historical writer would have duplicated the one-day Final Save contract and created a second history authority.

### Affected surfaces
Documentation / doctrine only: `docs/RHC_WORKSYSTEM.md`, `docs/DM_CONTROL_ROOM.md`, `canon/README.md`, `PLAY.md`; plus `CHANGELOG.md` / `ENGINE_CHANGELOG.md` (this continuity). No code, SQL, schema, migration, test, runtime, Supabase or campaign-state change.

### Deliberate non-goals / deferred ownership
- A dedicated historical/bulk persistence engine — deliberately rejected; existing Final Save/SAVE machinery persists each recognized day.
- Corrections to completed POST-EV2-10 / 10.5 / 11 / 11.5 mechanics or implementation — a separate owning Mission.
- Continuity after POST-EV2-11.5 — a later continuity closeout.

### Compatibility / recovery consequences
- No runtime mutation domain and no same-save compatibility edge is added.
- Ordinary Final Save semantics and the finalized-day archive are unchanged; the one-day contract is intentionally never widened into a bulk or multi-day writer.
- The superseded PR #184 Historical Sync engine was closed unmerged and is not shipped repository history.

### Verification evidence
- This is a documentation-only Mission; proof is the bounded diff across the workflow/doctrine docs above plus this continuity.
- PR #185 merged from exact cleared HEAD `c63624ac5a8ec66b8f058ec5554e3c254fb4f033` as `2a6c665c192aeafb9288834dab536998204dda7e`.

---

## 2026-09-30 - POST-EV2-11: Begin Day + Fresh-DM Boot

### Why this milestone exists
RHC already had Final Save / day archive, RT01 publication, RT02 Campaign Clock, compact current-runtime reads, project/history retrieval, one RNG root, Rest, Hooks and current-state owners — but no single safe day-opening command for a fresh DM/AI. A fresh DM had to reconstruct "current world + yesterday's memory + today's initialization" by hand, which risked a second day owner, rerolled mechanics or invented elapsed time. POST-EV2-11 closes that gap without inventing a new day owner.

> Architecture sentence: **Begin Day = current world + yesterday's finalized memory + today's initialization. It reads the exact previous finalized `canon/days/day_XXX.md`, changes only the day-boundary fields of the existing owners plus the RT02 Campaign Clock, dispatches only configured daily consumers through POST-EV2-8, publishes once through RT01 with RT02 as the only day authority, requires the existing mirror/verifier confirmation, and returns a derived boot packet that is never persisted as truth.**

### Durable design
- **Conductor, not a truth owner.** One command opens exactly the next live day (`N -> N+1`) from a finalized previous day, adding no new runtime key, mutation domain, Save Gateway, controller ledger, time source, RNG root, Hook lifecycle or persistence/mirror path, and no same-save compatibility edge.
- **Only day-boundary fields change.** `campaign_clock` day advances through validated RT02 `stage_campaign_clock` (elapsed minutes, phase and `long_rests_completed` carried forward exactly); `daily_recap`, `day_resolution`, `narrative_hooks` and active `live_status`/`dm_meta` are reconciled to the new day without rewriting unrelated content. `daily_recap.previous_day_record` points at the exact finalized Day N path that was actually read, with an immutable `carryover_active_hooks_at_start` snapshot taken from the Hook owner.
- **Single owners reused.** RT02 owns Campaign Day / elapsed time; RT01 owns publication; POST-EV2-8 owns RNG; POST-EV2-10 owns Rest and stays independent; POST-EV2-6 owns older/project-wide retrieval; RT04/POST-EV2-2 own Run reconciliation/HOT; finalized history belongs to `canon/days/day_XXX.md`.
- **Bounded consumer extension seam.** Configured daily consumers are dispatched deterministically by `consumer_id`, deduplicated and bounded, and receive the only randomness path (a declared seam calling `scripts/dice_resolver.py`); zero consumers means zero RNG and zero invented daily event. Begin Day never owns a mechanic's rules.
- **Fail-closed retry and provenance.** Requested day must equal published day (rehydrate) or published day + 1 (open); skip/backwards, missing/unfinalized previous day, Unknown/incoherent current day and unverifiable owner days fail closed. Retry rehydrates the existing published result and restores the exact finalized previous-day memory without rerolling; a degraded rehydration fails closed. The finalized day is resolved by **numeric day identity** across every legal `canon/days/day_<digits>.md` width, and more than one legal file for one numeric day fails closed as ambiguous.
- **Durable boundary and generation pin.** The gateway seam commits only after publication and mirror confirmation agree, so success is reported only for a durably committed, mirror-confirmed generation; the returned boot packet is pinned to that exact confirmed generation and a concurrent/later publication fails the pin closed.
- **One supported read.** `public.dm_begin_day_read()` is the service-only, published-only read of the current day-boundary bundle and coherence verdict; staged/future rows are never exposed.
- **Surviving law: BEGIN DAY IS A CONDUCTOR, NOT ANOTHER DAY OWNER.**

### Durable lesson
Opening a day is orchestration over existing owners, not a new source of truth. Reusing RT01/RT02 and the existing day-boundary owners keeps one day authority, one time source and one RNG root; a derived boot packet for a fresh DM is read output and must never be persisted as authority.

### Affected surfaces
`supabase/migrations/20260929000002_post_ev2_11_begin_day.sql`, `scripts/begin_day.py`, `tests/post_ev2_11/test_begin_day.py`, `docs/POST-EV2-11-BEGIN-DAY.md` (new); `docs/RHC_WORKSYSTEM.md`, `state/README.md`, `supabase/README.md`, `PLAY.md`, `.github/workflows/rt01-runtime.yml` (new test family), `tests/post_ev2_9/test_character_vitals_resources.py`, `tests/post_ev2_10/test_character_rest.py`, `tests/post_ev2_2/test_hot_run_registry.py` (minimal frontier updates); `CHANGELOG.md` / `ENGINE_CHANGELOG.md` (this continuity).

### Deliberate non-goals / deferred ownership
- **POST-EV2-11.5** — historical played-day backfill / bulk finalized-history intake.
- **POST-EV2-12** — Business/Economy templates + resolution; may attach later as a daily consumer.
- **POST-EV2-10** — Rest / Long Rest (independent).
- **Combat gates**, **RT04 / POST-EV2-2** Run reconciliation/HOT, **POST-EV2-6** older/project-wide retrieval, **POST-EV2-4A** temporal/timespace placement, **CCC/frontend** UI, and a **future scheduler / deferred events** owner.
- No real RHC day is opened and no real finalized `canon/days/day_XXX.md` is created or edited by BUILD proof.

### Compatibility / recovery consequences
- Begin Day adds no runtime state key, no mutation domain, no Patch 1A registry entry and no Patch 1B compatibility edge; the existing policy/runtime frontier is reused unchanged.
- The conductor fails closed on an unverifiable day sequence, previous-day finalization, owner coherence or mirror confirmation, preserving the last healthy published checkpoint; abort leaves Day N published truth unchanged.
- No production/deployment claim is made by this continuity.

### Verification evidence
- Pure orchestration proof (injected RT01/RT02 gateway seam) plus real PostgreSQL 15 and 17 with the full forward migration chain and one end-to-end publication through the real save/publication/mirror-confirmation spine, with synthetic days only: only the next day opens; skip/backwards, missing/unfinalized previous day, Unknown/incoherent current day and unverifiable owner days fail closed; only day-boundary fields change; zero consumers means zero RNG and a synthetic consumer uses the shared resolver via the declared seam; retry never creates a second RNG/consequence set; abort leaves Day N unchanged; mirror failure is not reported as success; publication is durable before success; the boot packet is derived, complete and generation-pinned; every legal finalized-day width resolves by numeric identity and an ambiguous day fails closed; no real RHC data is seeded.
- PR #182 merged from exact cleared HEAD `dff84eb8c4ce37268399dad7d3b86b1dee3ad413` as `4602c8ddd134a8cc2abd7a4ae66b6216308d7a3a`.

---

## 2026-09-29 - POST-EV2-10.5: RT01 parallel proof sharding

### Why this milestone exists
The RT01 runtime foundation had grown to a single serial pytest invocation whose wall-clock time made every runtime-sensitive PR slower to validate. The coverage was correct; only its execution shape was inefficient.

### Durable design
- **Four isolated shards, same proof.** The single invocation was split into four parallel jobs — runtime floor (RT01/RT02 + mirror), run spine (RT03/RT04/EV2-10), entity + timeline (EV2-11/EV2-13.1/EV2-13.420 + POST-EV2-1/2) and post-EV2 frontier (POST-EV2-3/4A/5/9/10/11).
- **Isolation, not re-specification.** Each shard runs on its own runner with its own PostgreSQL 15 (55432) and PostgreSQL 17 (55433) service containers while sharing the identical DSN environment and proof coverage used by the former serial run, so no two shards mutate the same disposable database.
- **Stable aggregate gate.** One `prove-runtime-foundation` job depends on every shard and succeeds only when all four succeed, failing if any shard fails, is cancelled or is otherwise not green — preserving the single branch-protection check name.
- **Workflow-only.** No runtime, schema, SQL, Supabase, campaign-state or game-mechanic behavior changed.

### Durable lesson
Parallelizing proof changes only the execution topology, not the proof itself; keeping the same PostgreSQL versions, DSNs and proof families preserves the exact signal while removing wall-clock cost, and a stable aggregate job keeps the merge gate unchanged.

### Affected surfaces
`.github/workflows/rt01-runtime.yml` only. No code, SQL, schema, test, runtime, Supabase or campaign-state change.

### Deliberate non-goals / deferred ownership
- No change to proof coverage, test semantics or the required runtime proof families.
- No new runtime surface, compatibility edge or production action.

### Compatibility / recovery consequences
- The branch-protection check name `prove-runtime-foundation` is preserved as the stable aggregate signal.
- Any future proof family is added to the relevant shard and to the aggregate dependency set rather than reintroducing a serial run.

### Verification evidence
- PR #179 merged from exact cleared HEAD `360e9a0322be3ecd3dd4c8befe81196b9bbad004` as `0ef4000eb9987f1c5e26d92acf906dac225a87a2`.

---

## 2026-09-29 - POST-EV2-10: Per-character Short/Long Rest lifecycle

### Why this milestone exists
POST-EV2-9 now owns current HP / Hit Dice / spell-slot pools / limited-use character resources, RT02 owns elapsed campaign time and POST-EV2-8 owns all mechanically required RNG, but RHC still lacked the bounded mechanic that says whether one specific character actually started, continued, interrupted or completed a valid Rest — and therefore which official Rest consequences may fire. Without it, Rest would have been inferred from prose or embedded in a shared scene, creating a second resource/state owner.

> Architecture sentence: **POST-EV2-10 does not create a new save system. It creates the bounded durable per-character Rest lifecycle on top of the existing RT01 SAVE / publish / mirror / confirm spine, with RT02 elapsed time as the only time source, POST-EV2-8 as the only RNG root, POST-EV2-9 as the only HP / Hit-Dice / resource owner, and controller authority resolved only from authoritative published Run truth.**

### Durable design
- **One dedicated engine-owned domain.** `character_rests` holds exactly one record per `character:<slug>`; the record owns only the lifecycle (status `idle|active|completed|interrupted`, `rest_kind`, start/completion anchors, `required_minutes`, personal `last_long_rest_completed_at_elapsed_minutes`, bounded ordered `interruptions` and `short_benefit_granted`). It never duplicates HP, Hit Dice, spell slots or feature charges.
- **Per-character independence.** A shared camp scene may contain several independent Rest attempts; there is never one shared mechanical Rest record, and interrupting one character's Rest does not alter another's.
- **Progress is derived, not ticked.** A start anchor plus a required duration is stored; completion is a legal transition once authoritative RT02 elapsed minutes satisfy it, with no minute-by-minute journal.
- **Absolute, replay-safe mutation.** `public.mutate_character_rest(<lock_token>, <request>)` stages one absolute replacement for a character's Rest record, so replaying one logical transition is idempotent and cannot double-spend or duplicate an interruption hour.
- **Single time and RNG owners.** Every anchor is stamped from published RT02 `elapsed_campaign_minutes`; supported Hit Point Die rolls come from `scripts/character_rest.py` through the shared POST-EV2-8 resolver and never from raw `random.*`; a required Constitution modifier may be supplied only with declared authoritative source provenance and is never stored or invented.
- **Resulting state persisted through the resource owner.** `mutate_character_rest` computes resulting HP / Hit Dice / resource values but persists them only through POST-EV2-9's `mutate_character_mechanics`, so POST-EV2-9's operation marker and exhaustive-writer contract remain true; no exclusion is invented between `character_rests` and `campaign_clock` / `character_mechanics`.
- **Controller authority is proven, never stored.** Resolved from authoritative published Run truth via the shared EV2-10 resolver (MAINRUN unclaimed, or exactly one RUN #; parked/duplicate/malformed published Runs fail closed), so a former/stale controller write fails closed.
- **Patch 1A/1B extended minimally.** `character_rests` is `dedicated`; the compatibility contract gains `mutate_character_rest` (blocked by a same-save `runs` change) and a trailing `character_rests` edge on `stage_runs`/`delete_runs`/`reconcile_runs`, keyed on the staging operation fact so a value-equal replay still closes every Run-ownership doorway and the marker never leaks.
- **One supported read.** `public.dm_runtime_read_character_rest(<character_id>)` is the `service_role`-only published read by exact identity, returning the RT01-D metadata envelope plus the record or truthful `record: null` absence.
- **Unsupported state fails closed.** Official Long-Rest effects RHC has no owner for (Exhaustion, condition/ability-score/HP-maximum reduction) are never invented; an `unknown` rest-sensitive `character_mechanics` section fails the route explicitly.
- **Surviving law: SHARED SCENE IS NOT SHARED REST; CAMPAIGN DAY IS NOT REST STATE.**

### Durable lesson
A shared scene and a shared mechanic are different scopes: Rest belongs to the character, not the camp, so per-character lifecycle independence is the correct model. Keeping time, randomness and resource state with their existing single owners — and persisting Rest consequences only through POST-EV2-9 — prevents Rest from becoming a second resource or time authority.

### Affected surfaces
`supabase/migrations/20260929000001_post_ev2_10_character_rest.sql`, `schemas/character_rests.schema.json`, `scripts/character_rest.py`, `tests/post_ev2_10/test_character_rest.py`, `docs/POST-EV2-10-CHARACTER-REST.md` (new); `.github/workflows/rt01-runtime.yml`, `PLAY.md`, `schemas/README.md`, `supabase/README.md`, `tests/post_ev2_1/test_same_save_compatibility_dispatcher.py`, `tests/post_ev2_2/test_hot_run_registry.py`, `tests/post_ev2_9/test_character_vitals_resources.py` (minimal frontier updates); `CHANGELOG.md` / `ENGINE_CHANGELOG.md` (this continuity).

### Deliberate non-goals / deferred ownership
- **Begin Day / Start-of-Day** — POST-EV2-11 (may consume Rest outcomes later; does not own Rest).
- **Combat Academy adaptation** — POST-EV2-12.
- **Conditions / Exhaustion / ability-score or HP-maximum reduction** — a later status / character-mechanics concern; Rest reports/fails closed rather than faking completion.
- **Item-owned charges** — a future item mechanic.
- **CCC/frontend presentation and UI** — later; this gate exposes backend semantics only.
- **World interruption generation / scheduler** — future work; this gate resolves explicit interruption facts only.
- **Real data intake / seeding** — INTAKE/BTH work; no real RHC Rest state is published.

### Compatibility / recovery consequences
- Existing EV2-13 `entity_state`, inventory, custody, knowledge, temporal, Clock and POST-EV2-9 owners are unchanged; the only new cross-domain relationship is the required Run-ownership exclusion.
- The forward migration chain gains one migration; existing databases upgrade normally and the clean baseline remains valid only for its pinned frontier.
- A former/stale controller write fails closed because published Run truth no longer grants it authority; abort leaves no residue.

### Verification evidence
- Focused proof ran on real PostgreSQL 15 and 17 through the full forward migration chain and the real save/publication/mirror-confirmation spine with synthetic characters only: per-character independence; the at-least-1-HP start rule; 60-minute Short and 480 + 60-per-interruption Long durations; the personal 16-hour wait; every interruption cause and the no-benefit Short interruption; the Long Rest interruption granting Short benefits and adding time; all-HP/all-Hit-Dice Long Rest restoration; clearing temporary HP; metadata-driven recharge only; unknown rest-sensitive state failing closed; shared-resolver Hit Point Die spending with a sourced Constitution modifier and no raw RNG; absolute replay idempotency; abort residue absence; published-only/service-role-only mutation and read; Patch 1A classification and generic bypass closure; and the Patch 1B Run-ownership exclusion in both orderings including value-equal replay.
- PR #177 merged from exact cleared HEAD `d8bc1e8df77988c33a978d76a8bc7edfea8e285d` as `0cc3801550b26011b295393cb4467ec3794477f1`.

---

## 2026-09-28 - POST-EV2-9: Character vitals + resources runtime

### Why this milestone exists
RHC character sheets could describe Max HP, Hit Dice, spell slots and limited-use features, but EV2-13 `entity_state` deliberately excludes HP/resources and no deterministic backend owner existed for a future CCC, AI action or POST-EV2-10 Rest to read/mutate safely. Without this Mission the frontend would have had to parse prose or invent a second resource ledger. POST-EV2-9 adds the smallest authoritative operational character-mechanics capability on the existing RT01 spine.

> Architecture sentence: **POST-EV2-9 does not create a new save system. It creates the bounded durable character-vitals/resources mutation surface on top of the existing RT01 SAVE / publish / mirror / confirm spine, with controller authority resolved only from authoritative published Run truth.**

### Durable design
- **One dedicated engine-owned domain.** `character_mechanics` is a JSON array holding exactly one authoritative record per `character:<slug>`, carrying bounded machine-readable definition/capacity plus current expendable state in the same record so a later Rest gate can consume bounded recharge metadata without a second ledger.
- **Explicit truth, bounded values.** Four required capability sections (`hp`, `hit_dice`, `spell_slots`, `resources`) each declare `known | unknown | not_applicable`. A `known` section requires its payload (an empty list means known to be none); `unknown`/`not_applicable` forbid it. Values are whole non-negative integers with `current <= maximum`; HP also carries optional non-capacity-bounded `temporary`. Records are canonically ordered so equivalent logical targets compare and replay stably.
- **Absolute, replay-safe mutation.** `public.mutate_character_mechanics(<lock_token>, <request>)` is the only writer and stages one absolute replacement for a character's record; a level/build change may replace capacity and current atomically in one validated target.
- **Controller authority is not stored.** It is resolved from authoritative published Run truth through the shared EV2-10 resolver exactly as EV2-10/EV2-11/EV2-13 do: under `mainrun` the character must be unclaimed, under `run` it must be controlled by exactly that RUN #, and parked/duplicate/malformed published Runs fail closed.
- **Patch 1A/1B extended minimally.** `character_mechanics` is `dedicated` with the exhaustive writer set `[mutate_character_mechanics]`; the compatibility contract gains the `mutate_character_mechanics` operation (blocked by a same-save `runs` change) and a trailing `character_mechanics` edge on `stage_runs`/`delete_runs`/`reconcile_runs`. Closure keys on the staging operation fact, not value equality, so a value-equal replay still closes every Run-ownership doorway and the marker never leaks into a later save.
- **One supported read.** `public.dm_runtime_read_character_mechanics(<character_id>)` is the `service_role`-only published read by exact identity; it returns the RT01-D metadata envelope plus the record or truthful `record: null` absence, and never consumes staged/future state as authority.
- **Surviving law: CHARACTER SHEET != LIVE RESOURCE STATE.** `characters/*.md` and the character-state template remain human/player-authoritative for what a character *can* have; the runtime owns only the explicitly supplied normalized current operational state.

### Durable lesson
Definition/capacity and current expendable state belong together in one bounded record with explicit Unknown, because splitting them across a sheet, a resource ledger and inferred defaults is how a second truth owner appears. The same discipline applies to authority: character-mechanics authority is proven against *published* Run truth, so it is deliberately mutually exclusive within one save with a Run-ownership change rather than inventing a new compatibility relationship.

### Affected surfaces
`supabase/migrations/20260928000001_post_ev2_9_character_vitals_resources.sql`, `schemas/character_mechanics.schema.json`, `docs/POST-EV2-9-CHARACTER-VITALS-RESOURCES.md`, `tests/post_ev2_9/test_character_vitals_resources.py` (new); `schemas/README.md`, `supabase/README.md`, `.github/workflows/rt01-runtime.yml`, `tests/post_ev2_1/test_same_save_compatibility_dispatcher.py`, `tests/post_ev2_2/test_hot_run_registry.py`, `tests/post_ev2_5/test_current_search.py` (modified minimally to the new frontier), `CHANGELOG.md` / `ENGINE_CHANGELOG.md` (this continuity).

### Deliberate non-goals / deferred ownership
- Rest / Long Rest lifecycle — POST-EV2-10.
- Semantic relative operations (damage, healing, spend/regain, death saves, action economy) — later combat/gameplay gates.
- Item-owned mutable charges, conditions/exhaustion/concentration, and CCC/frontend presentation or UI.
- Real character normalization/import/seeding and character-sheet derivation, leveling/build calculators and D&D rules compilers.
- `entity_state` (EV2-13) remains a separate owner; no full Markdown character-sheet clone was added.

### Compatibility / recovery consequences
- Existing EV2-13 `entity_state`, inventory, custody, knowledge, temporal and Clock owners are unchanged; no new cross-domain edge was invented beyond the required Run-ownership exclusion.
- `characters/*.md` and `characters/CHARACTER_STATE_TEMPLATE.json` remain the human/player source and are not promoted into a competing persistence path.
- The forward migration chain gains one migration; existing databases upgrade normally and the clean baseline remains valid only for its pinned frontier.
- A former/stale controller write fails closed because published Run truth no longer grants it authority.

### Verification evidence
- Focused POST-EV2-9 proof ran on real PostgreSQL 15 and 17 through the full forward migration chain and the real save/publication/mirror-confirmation spine with synthetic characters only (known/unknown/not_applicable separation, bounded values, duplicate/negative/fractional rejection, canonical ordering, MAINRUN and RUN # paths, parked/duplicate/malformed published Run rejection, Patch 1A classification and generic bypass closure, same-save Run-ownership exclusion in both orderings including value-equal replay and marker non-leakage, absolute replay idempotency, abort residue absence, published-only truthful absence, and service-role-only mutation/read).
- Exact-head CI was green and fresh Codex review was clean.
- PR #171 merged from exact cleared HEAD `340d05bf71cf41baebe3a9d7b58b648df5b69581` as `5719cfbd3bbfa48f90d43c140e7b5a6e608ea657`.
- Production closeout synchronized migration `post_ev2_9_character_vitals_resources`; production runtime remained generation 2, no campaign-state publication occurred and no real `character_mechanics` record was published.

---

## 2026-09-28 - POST-EV2-8: Universal D&D dice resolver

### Why this milestone exists
RHC had no single random-resolution primitive: any mechanic or adapter that needed a roll could reach for raw `random.*` and re-implement dice parsing, modifier arithmetic and Advantage/Disadvantage composition, producing divergent results and no auditable structure. POST-EV2-8 adds one shared resolver that owns randomness plus declared arithmetic only, leaving all rules meaning with the owning mechanics.

> Architecture sentence: **The resolver owns randomness and declared arithmetic. Owning mechanics keep roll necessity, rules meaning, DCs, consequences and persistence. One RNG root.**

### Durable design
- **One RNG root.** `scripts/dice_resolver.py` exposes `resolve(request, rng=None) -> dict`; future mechanics, AI/tool callers and frontend/backend adapters consume it rather than calling raw `random.*` or inventing their own RNG.
- **Machine-readable request.** A pure `NdM` notation plus sourced static `modifiers`, sourced `bonus_dice`/`penalty_dice` and explicit `advantage`/`disadvantage` source lists; only declared keys are accepted and an unknown field fails closed.
- **Structured result.** Raw `rolls`, `kept_rolls`/`dropped_rolls`, per-die bonus/penalty components and a deterministic `total = sum(kept_rolls) + modifier_total + bonus_total - penalty_total`, so every roll is auditable rather than collapsed to one number.
- **D&D Advantage/Disadvantage composition.** Valid only on a single `d20`: same-state sources do not stack; at least one Advantage and one Disadvantage source cancel to one normal die; all declared sources are preserved.
- **Bounded accepted work.** Declaration size is bounded so a caller cannot turn one request into unbounded rolling.
- **No meaning, no mutation.** The resolver decides no roll necessity, ability/skill/save, DC, success/failure, damage meaning, consequence or persistence, and performs no file, SQL, SAVE, canon or campaign-state mutation.
- **Surviving law: ONE RNG ROOT.**

### Durable lesson
Randomness and rules meaning are different owners. Extracting only the random/arithmetic layer into one primitive keeps every mechanic's semantics where it belongs while making results reproducible and testable; the seedable `rng` seam exists for tests and must never become production behavior.

### Affected surfaces
`scripts/dice_resolver.py`, `tests/test_dice_resolver.py`, `docs/POST-EV2-8-DICE-RESOLVER.md` (new); `PLAY.md` (updated), `CHANGELOG.md` / `ENGINE_CHANGELOG.md` (this continuity).

### Deliberate non-goals / deferred ownership
- No roll-necessity, DC, ability/skill/save or success/failure semantics.
- No damage, healing, combat or initiative consequence; Combat keeps those.
- No SAVE/SQL/canon/campaign-state mutation; `state/day_resolution.json` + SAVE keep durable mechanical outcomes and `scripts/offscreen_resolution.py` keeps off-screen Run consequence classification.
- Wiring existing owners onto the resolver remains a later gate.

### Compatibility / recovery consequences
- Existing owners and persistence are unchanged; the resolver is a new pure helper with no runtime surface.
- Production uses Python's unseeded runtime RNG; determinism is available only through the explicit test seam.
- Rolling never writes durable state by itself, so no compatibility edge or production synchronization is required.

### Verification evidence
- `tests/test_dice_resolver.py` covers notation parsing, sourced modifiers, sourced bonus/penalty components, Advantage/Disadvantage non-stacking and cancellation, unknown-field rejection, bounded work and deterministic test-seam seeding.
- Exact-head CI was green and fresh Codex review was clean.
- PR #169 merged as `7a640b7ac21ecc03a4ce1bc2d98dd2380a2f53d8`.

---

## 2026-09-27 - POST-EV2-7 zero-code closeout: Historical Run retrieval already satisfied

### Why this milestone exists
POST-EV2-7 was originally framed as a COLD historical Run archive plus selective-retrieval gate. An implementation attempt (PR #163, `POST-EV2-7A: COLD Run lifecycle + archive transition`) began building an explicit close/archive lifecycle and additional derived retrieval machinery. The durable question was not whether that code could be hardened but whether RHC needed the surface at all. A read-only audit of current `main` showed the product need was already satisfied by composition of existing owners, so the correct outcome was zero-code closure.

### Durable design
- **Historical Run truth already has an owner.** RT04 preserves played Runs that lose all mutable owners as `parked` while keeping their historical participation/evidence in authoritative `runs`.
- **HOTness is already derived.** POST-EV2-2 treats active Runs, Runs with mutable owners, or Runs with a current `dm_meta.run_claims` entry as operationally relevant; a parked/zero-owner/no-claim Run therefore remains historical Run truth without remaining HOT.
- **Canonical Run reads already exist.** RT03 remains the authoritative published Run reader; no archive reader is needed to keep completed Run history accessible.
- **Selective retrieval already exists.** POST-EV2-5 exact-focus search returns relevant published Runs by exact character/creature/location/party focus, including parked historical Runs, without hydrating unrelated Run history.
- **No second archive system.** No CLOSE RUN lifecycle, archive fields/persistence, schema/migration, projection/index, memory database, runtime domain, Patch 1A entry, Patch 1B edge or POST-EV2-6 widening was added.

### Durable lesson / scar preserved
A plausible future gate can become an implementation assumption before current repository truth is re-audited, and once code exists CI/review naturally audits that code rather than whether the surface belongs in the product. Review severity is not proof that the surface itself is needed. The durable lesson is placement-before-implementation: inspect current owners first, prove the gap, and close the gate if the gap disappears under audit instead of manufacturing work. The attempted PR #163 implementation did not merge, and a later-proposed Mechanic Placement Rule workflow text was reverted; neither is shipped repository history.

### Affected surfaces
Documentation/continuity only: `CHANGELOG.md` / `ENGINE_CHANGELOG.md` (this continuity). No `ORCHESTRATOR.md` rule and no other surface was changed by this closeout. Stale POST-EV2-7 archive directives still survive in `docs/POST-EV2-5-CURRENT-SEARCH.md` and `docs/POST-EV2-2-HOT-RUN-REGISTRY.md`; reconciling those out-of-budget docs is deliberately deferred.

### Deliberate non-goals / deferred ownership
- No runtime, SQL, schema, tests, save lifecycle, retrieval behavior, campaign state or production migration change.
- No new Run closure/archive semantics and no new retrieval implementation.
- No workflow-law codification; any future placement/workflow rule belongs to its own workflow Mission.
- Any future COLD Run capability gap belongs to a future proven need, not this closeout.
- Reconciliation of the surviving stale POST-EV2-7 directives in `docs/POST-EV2-5-CURRENT-SEARCH.md` and `docs/POST-EV2-2-HOT-RUN-REGISTRY.md` is outside this Mission's Surface Budget and remains deferred to a future docs-reconciliation owner.

### Compatibility / recovery consequences
- Current implementation truth shows the intended POST-EV2-7 capability is already satisfied by **RT04 + POST-EV2-2 + RT03 + POST-EV2-5**, and that behavior is unchanged.
- A future maintainer should rely on the current implementation truth above rather than on the surviving stale directives, which still assign a COLD historical Run archive/selective retrieval to POST-EV2-7 and are inaccurate.

### Verification evidence
- The repair is correct when the ledger no longer claims that the repository stops directing a future Builder toward a separate POST-EV2-7 COLD archive; it instead acknowledges the stale directives that still survive in `docs/POST-EV2-5-CURRENT-SEARCH.md` and `docs/POST-EV2-2-HOT-RUN-REGISTRY.md`, records that current implementation truth already satisfies the capability via RT04 + POST-EV2-2 + RT03 + POST-EV2-5, and defers their reconciliation as outside this Mission.
- No implementation, runtime, schema, migration or production change was made; no exact-head implementation CI applies because this Mission edits only continuity ledgers.

---

## 2026-09-27 - POST-EV2-6 closeout: Project-wide retrieval + hydration admission

### Why this milestone exists
POST-EV2-5 answered the narrow current-world question: “what authoritative published runtime records matter for this exact focus right now?” RHC still needed a separate broader read capability for older/project-wide story material without loading the whole repository into active context, treating a generated search artifact as truth, or making retrieval responsible for every source format's META/NON_META semantics.

POST-EV2-6 closes that gap with a repository-derived retrieval layer whose job is discovery and bounded hydration, not semantic ownership.

> Architecture sentence: **Search wide, hydrate narrow. POST-EV2-6 discovers project-wide candidates and proves freshness/provenance, then admits only bounded context that is safe for the requested reader profile; existing source/domain owners keep semantic authority.**

### Durable design
- **Discovery is not authority.** The deterministic manifest indexes only declared story roots and carries source path, source class, authority, SHA-256 and conservative visibility evidence. The manifest is generated, disposable and non-authoritative; rebuilding it never authors campaign truth.
- **Explicit admission before hydration.** The read flow is `SEARCH → CANDIDATE RECEIPT → HYDRATION ADMISSION → BOUNDED EXCERPT`. DM retrieval may hydrate declared searchable sources while preserving META/non-canon labels. Ordinary authoritative/player-safe hydration requires unambiguous whole-source `NON_META` evidence and rejects `non_canon` sources.
- **Safe incompleteness is intentional.** Mixed Markdown, nested/mixed JSON, unclear visibility inheritance or unclassified content fail closed for authoritative/player-safe hydration. POST-EV2-6 deliberately does **not** become a generic repository-wide Markdown/JSON visibility parser.
- **Freshness is source-set truth, not Git-HEAD decoration.** The manifest fingerprints the exact indexed source set and source content/evidence. Indexed add/edit/remove makes it stale; unrelated engineering edits do not. Manifest integrity is re-derived rather than self-certified, and bytes are SHA-256 checked again at hydration time so a mid-query source change returns incomplete/stale evidence instead of content under an obsolete receipt.
- **Zero-result honesty.** A fresh zero means no indexed lexical match, not semantic/project-wide absence. A stale/tampered/unavailable zero is explicitly incomplete and must never be read as proof of absence.
- **Bounded context.** Query results are deterministic and capped; hydration returns only the bounded excerpt needed from admitted sources. Searchable corpus is not active context.

### Ownership boundary with POST-EV2-5
- **POST-EV2-5** remains the only current published-world exact-focus runtime search through `public.dm_current_search(...)`.
- **POST-EV2-6** owns broader repository/project-history discovery plus freshness/provenance and hydration admission.
- POST-EV2-6 does not wrap or reimplement POST-EV2-5.

### Durable lesson
A retrieval service becomes unstable when it silently absorbs semantic ownership from the documents it searches. The first POST-EV2-6 candidate exposed this by trying to interpret arbitrary mixed Markdown/JSON visibility structure inside retrieval. The durable correction was architectural, not another parser patch: keep search responsible for discovery and freshness, add an explicit admission boundary, and prefer safe incompleteness when source semantics are ambiguous.

### Affected surfaces
`.github/workflows/story-retrieval.yml`, `scripts/story_retrieval.py`, `tests/post_ev2_6/test_story_retrieval.py`, `docs/POST-EV2-6-STORY-RETRIEVAL.md` (new); `README.md`, `PLAY.md` (updated).

### Deliberate non-goals / deferred ownership
- No Supabase/runtime SQL, mutation domain, save/publication path, Patch 1A/1B change or campaign-state mutation.
- No generic atomic visibility parser or repository-wide visibility normalization.
- No external web/lore adapter, Day Start orchestration, UI or Gate 36 intake.
- No committed generated retrieval manifest/cache and no automatic canon/knowledge promotion.

### Compatibility / recovery consequences
- Repository main remains implementation/canon truth; generated retrieval artifacts can always be rebuilt from current declared sources.
- POST-EV2-5 and existing runtime readers remain unchanged.
- If the manifest is missing, tampered or stale, retrieval fails closed to incomplete evidence; rebuild is the normal recovery path.
- Mixed/ambiguous sources remain DM-discoverable but intentionally unavailable to ordinary authoritative/player-safe hydration until an owning source contract can make them unambiguous.

### Verification evidence
- Focused POST-EV2-6 proof covered broad real-source discovery, honest sparse results, authority/source-class preservation, DM vs authoritative admission, mixed Markdown/JSON fail-closed behavior, stale edit/add/remove detection, manifest tamper resistance, hydration-time digest mismatch, bounded determinism and exclusion of runtime/engineering surfaces.
- Final repair proof: focused suite 22 passed; relevant POST-EV2-5 + POST-EV2-6 suite 75 passed; full suite 2285 passed with one known pre-existing unrelated Windows CRLF migration-drift failure.
- Hard Write Boundary and required CI were green on exact cleared HEAD `d445a18dc1e490f34b06bb0982c177abd317e0a1`; fresh final Codex review reported no major issues.
- PR #155 merged as `d3952de8b072a37b735490032779fc4f451d42bd`. Post-merge read-back confirmed all six implementation files on main were byte-identical to the exact cleared PR HEAD.

---

## 2026-09-26 - POST-EV2-5: Current published-world exact-focus search

### Why this milestone exists
RHC had trusted published-state readers, but a DM/AI asking about one specific current entity still had to know which runtime namespaces might contain relevant data and inspect more state than necessary. POST-EV2-5 adds the smallest current-world search facade without creating a parallel truth system, validator layer or persistence path.

> Architecture sentence: **Search decides relevance. Existing engine owners decide validity. POST-EV2-5 selects only the current published namespaces that can contribute to one exact focus, validates them through their existing owners, and returns only bounded exact-relation hits.**

### Durable design
- **Current published world only.** `public.dm_current_search(p_focus, p_limit)` reads only `campaign_runtime.published_generation`; staged/future generations never participate.
- **One exact focus per call.** Supported focus kinds are `character:`, `creature:`, `location:`, `faction:`, `party:` and `item:`. It does not perform fuzzy discovery or recursive graph expansion.
- **Selective reads first.** For the requested focus kind, only runtime namespaces that can contribute are fetched by exact key. The whole published generation is never aggregated merely to filter later.
- **Owner validators stay authoritative.** `entity_state`, `inventory`, `item_custody`, `item_admissions`, `applied_statuses`, `entity_knowledge` and `runs` continue to use their existing whole-collection/canonical owner contracts, including declared cross-collection laws such as admission↔custody linkage. POST-EV2-5 adds no weaker per-record validation.
- **Bounded, deterministic, non-recursive results.** Limit defaults to 20 and is clamped to 1–50; multi-hit domains expose truncation; IDs found in hits are never recursively hydrated.
- **Read-only facade.** The function owns no state, stages/publishes nothing and leaves `public.dm_runtime_read()` and `public.dm_runtime_read_run()` unchanged.

### Durable lesson
Selective context is safest when retrieval plugs into already-authoritative domain readers instead of copying their validation logic. The important separation is relevance versus validity: search may choose where to look, but it must never become a second owner of whether the returned state is legal.

### Affected surfaces
`supabase/migrations/20260926000001_post_ev2_5_current_search.sql`, `docs/POST-EV2-5-CURRENT-SEARCH.md`, `tests/post_ev2_5/test_current_search.py` (new); `supabase/README.md`, `PLAY.md`, `.github/workflows/rt01-runtime.yml`, `tests/post_ev2_2/test_hot_run_registry.py` (updated to the new read/migration frontier).

### Deliberate non-goals / deferred ownership
- No cache, index, graph/vector store, generic query language, second state reader or recursive hydration.
- No new mutation domain, Save Gateway writer, Patch 1A/1B compatibility edge or campaign-state publication.
- No repository/history search or external web/lore retrieval; those are outside POST-EV2-5.

### Compatibility / recovery consequences
- Existing domain validators/canonical Run read path remain the validity authority and fail closed unchanged.
- Existing runtime read surfaces remain available and behaviorally unchanged.
- The forward migration chain gains the read-only search function; production synchronization changed executable read capability only and did not publish campaign state.

### Verification evidence
- Focused PostgreSQL proof covered supported/unsupported focus kinds, exact routing, owner validation failures, cross-collection admission/custody law, bounded/truncated results, staged-generation exclusion, service-role-only execution and non-recursive output.
- Exact-head CI was green and fresh Codex review was clean.
- PR #151 merged as `24b255e451c1dbfb16a41f336e74d08ce7e641e7`; production synchronization completed with runtime still at generation 2 and no campaign-state publication.

---

## 2026-09-25 - POST-EV2-4B: Reality inheritance + explicit divergence foundation

### Why this milestone exists
An alternate RHC history should begin from the same established world/system as its parent and differ only where the DM explicitly declares a divergence. The retired PR #143 / JOHNNY #142 design modeled a reality as a subject-availability/scoping list, which inverted that model and forced pointless questions about whether unchanged characters, locations, spells, abilities, Hooks, etc. "exist" in each reality. POST-EV2-4B replaces that abstraction with the smallest repository identity + inheritance contract: name histories and their lineage, and declare that inheritance is the default.

### Durable design
- **Identity, not subject lists.** `schemas/reality.schema.json` defines `reality_id` (strict `reality:<lower-slug>` grammar), `display_name`, and an explicit `parent_reality_id`. It has no subjects/availability field and no override/state payload.
- **One root; explicit parent.** `reality:rhc-primary` is the single root primary reality and declares no parent; every alternate reality names exactly one admitted parent. `scripts/validate_realities.py` enforces set-level uniqueness, exactly-one-primary, parent resolution and acyclicity.
- **Inheritance first.** A child reality begins as parent + zero divergences; anything not explicitly diverged stays inherited unchanged. Reality identity alone clones/removes/rewrites/scopes no Entity/Hook/Scenario/Encounter/Run/system definition.
- **No mutation of the source.** Merely defining a child reality never mutates its parent/source; future divergence must be represented through the real owning domain, not a generic 4B truth blob.
- **Explicit NO runtime impact.** No runtime mutation domain or same-save compatibility edge is added; no Supabase migration/route/schema, no `temporal_positions` change, and Patch 1A/1B are untouched.

### Durable lesson
The failed availability-scope attempt asked "what exists in this reality?" — a question that only has a sensible answer if the model is exhaustive, which forces re-declaration and leaks validator holes. Inheritance-inverts the burden: a reality is defined by its parent plus the divergences that matter, so unchanged content needs no representation. Review severity on the retired design was evidence of that abstraction leak, not product law.

### Affected surfaces
`schemas/reality.schema.json` (create), `scripts/validate_realities.py` (create), `docs/POST-EV2-4B-REALITY-INHERITANCE.md` (create), `realities/README.md` and `realities/registry/rhc-primary.json` (create), `tests/test_reality_inheritance.py` (create), `tests/fixtures/realities/valid/*` (create); `PROJECT_PRIMER.md`, `README.md`, `schemas/README.md`, `.github/workflows/entity-v2-identity.yml` (modified), `CHANGELOG.md` / `ENGINE_CHANGELOG.md` (this continuity).

### Deliberate non-goals / deferred ownership
- Owner-specific reality overlays/divergences for character/entity/location/story state.
- Runtime registry/read of the active reality; explicit cross-reality transition; reality-qualified mutable state.
- Explicit traveler carry-out/reconciliation through existing owner routes; no automatic leak-back or blanket reset-on-return.
- Reality-aware retrieval/RAG; alternate-history merge/reconciliation/paradox policy; UI controls.
- Disposable PREQUEL/SEQUEL/What-If lab architecture remains with POST-EV2-8.

### Compatibility / recovery consequences
- Existing Entity/Hook/Scenario/Encounter/Run schemas, all runtime/Supabase surfaces, `temporal_positions`, and Patch 1A/1B are byte-identical to BASE.
- Entity V2 identity and ability/status-effect definition identities remain global and are neither duplicated nor reality-scoped.
- POST-EV2-4A remains lane-scoped world-calendar/timespace placement inside one reality; ordinary RUN/time/plane/timespace movement does not mint a reality.
- Future divergence and carry-out remain possible but require their own owner-specific Missions.

### Verification evidence
- Local BUILD proof: `scripts/validate_realities.py` validates the root registry and synthetic fixtures; `tests/test_reality_inheritance.py` covers Draft 2020-12 schema validity, strict ID grammar, primary/parent rules, uniqueness, resolution, cycle/self-parent fail-closed, forbidden availability/override surfaces, unchanged owner schemas, absence of runtime/temporal changes, pinned inheritance-by-default docs, deferred carry-out, and CI wiring.
- Final exact-head CI runs and merge identity are recorded by Orchestrator closeout.

---

## 2026-09-25 - POST-EV2-4A: Temporal / timespace travel continuity

### Why this milestone exists
RHC already separated mechanical duration (EV2-13.420), monotonic experienced Campaign Clock time (RT02), timed-status ageing (EV2-13.1) and knowledge (EV2-14), and explicitly deferred world-calendar position, chronology and temporal jumps. Real gameplay still needs portals, planar travel, magic and DM-authored effects to move a lane centuries backward or forward — or into a timespace whose local date is partly known or Unknown — without confusing that placement with Campaign Day identity, experienced elapsed time, mutable state, status ageing or knowledge. POST-EV2-4A adds the smallest authoritative contract for that lane placement.

### Durable design
- **One dedicated engine-owned placement domain.** `temporal_positions` is a JSON array holding exactly one record per play lane (`mainrun` or `run:<R##>`). It is not a world calendar, not an alternate-reality system and not a per-era copy of entity state.
- **`public.mutate_temporal_position(<lock_token>, <request>)` is the only writer.** It runs inside the normal RT01 begin→stage→publish→mirror/confirm lifecycle, `service_role` only. Absolute placement is replay-safe directly; a relative whole-year request pins its exact source position, derives one stable absolute target, treats current==target as an idempotent retry (including after uncertain publication), and fails closed on any stale/ambiguous current position.
- **Precision is truthful.** `chronology` carries any subset of the integer components year/month/day/hour/minute; a missing component is Unknown and no finer precision is invented. `timespace` is known (a lower-slug reference) or Unknown. No calendar-specific range/month-length rule is encoded; Harptos/Dalereckoning arithmetic stays deferred.
- **Time layering is preserved.** A placement never mutates Campaign Day, RT02 elapsed time, Long Rest count, entity state, applied statuses or knowledge. A backward date jump is not negative experienced time; a forward jump adds no intervening years to elapsed time.
- **Lane authority comes from published Run truth.** MAINRUN is always a valid lane and needs no Run proof; a RUN-scoped lane requires the exact Run identity in authoritative published Run truth and rejects a parked played Run, with missing/malformed/duplicate/non-authoritative batches failing closed through the shared reader. `dm_meta.run_claims` grants no authority.
- **Patch 1A grows by one domain, Patch 1B by one operation and one edge.** `temporal_positions` is `dedicated` with the exhaustive writer set `[mutate_temporal_position]`; the compatibility contract gains `mutate_temporal_position` (blocked by a same-save `runs` change) and a trailing `temporal_positions` edge on `stage_runs`/`delete_runs`/`reconcile_runs`. Closure is deliberately RUN-scoped: a MAINRUN placement neither is blocked by nor blocks a same-save `runs` or Campaign Clock change, because it rests on neither.

### Durable lesson
The declared time layering is a set of independent owners, not one clock with modes. A world-calendar jump is a placement change, not a duration change; the correct contract stores *where a lane is* and proves *which lane it is* without borrowing elapsed-time, status or knowledge semantics. Keeping the same-save closure RUN-scoped (rather than reusing the blanket domain exclusion) is the same discipline: only couple surfaces whose authority proof actually depends on the other fact.

### Affected surfaces
`supabase/migrations/20260925000001_post_ev2_4a_temporal_timespace_continuity.sql` (create), `docs/POST-EV2-4A-TEMPORAL-TIMESPACE-CONTINUITY.md` (create), `tests/post_ev2_4a/test_temporal_timespace_continuity.py` (create); `docs/CAMPAIGN_TIME.md`, `supabase/README.md`, `.github/workflows/rt01-runtime.yml`, `tests/post_ev2_1/test_same_save_compatibility_dispatcher.py`, `tests/post_ev2_2/test_hot_run_registry.py` (modified minimally to the new frontier), `CHANGELOG.md` / `ENGINE_CHANGELOG.md` (this continuity).

### Deliberate non-goals / deferred ownership
- No alternate reality / timeline identity (POST-EV2-4B), no paradox resolver, no historical rewriting.
- No full Forgotten Realms lore database, portal/spell catalog, NPC scheduling/autosave or general spatial movement.
- No automatic knowledge gain/loss, era-based content rewriting, or selective RAG/context hydration by era.
- Harptos/Dalereckoning representation, the exact RHC timeline anchor and non-trivial month/day calendar adapters remain a later consumer-driven gate.
- No ageing/rejuvenation gameplay effect.

### Compatibility / recovery consequences
- Published `runs` remains the only Run/controller authority; RT02 remains elapsed-time authority; EV2-13.420/EV2-13.1/EV2-14 semantics are unchanged.
- The forward migration chain gains one migration; existing databases upgrade normally and the clean baseline remains valid only for its pinned frontier.
- A MAINRUN placement remains fully independent of Campaign Clock and Run-ownership saves.

### Verification evidence
- Local BUILD proof: the focused POST-EV2-4A suite passed on real PostgreSQL 15 and 17 (Patch 1A classification and bypass closure, truthful Unknown, exact/partial/Unknown placement, unchanged day/time/state/status/knowledge, supported relative preservation, fail-closed unsupported arithmetic and Unknown year, independent lanes, published-Run authority, same-save RUN-scoped exclusion both orderings, absolute plus relative retry idempotency (same-save and post-publication) with stale-source rejection, publication integrity, service-role-only execution).
- The two frozen POST-EV2-1/2 regression files were updated minimally to the new frontier and pass.
- Final exact-head CI runs and merge identity are recorded by Orchestrator closeout.

---

## 2026-09-24 - POST-EV2-3: Run impact wiring + knower-safe reconciliation

### Why this milestone exists
RHC already contained every major piece needed for a Run to continue as a real canonical path: published `runs` as the sole controller authority, EV2-14 owner-local knowledge, RT04 safe Run reconciliation, and RT01 + POST-EV2-1 atomic publication/domain admission/same-save compatibility. EV2-14 deliberately shipped **no** runtime/Supabase knowledge mutation route, and RT04 deliberately **preserved** knowledge consequences instead of inventing a mutation surface. POST-EV2-3 wires those existing mechanisms together so knowledge can belong durably to the actual knower while Run impact keeps using existing domain owners rather than a new generic impact/lock engine.

### Durable design
- **One dedicated engine-owned knowledge domain.** `entity_knowledge` is a JSON array holding exactly one authoritative EV2-14 record per knower. It is the runtime representation of `schemas/knowledge.schema.json`, not a second knowledge store, and EV2-14 semantics are consumed unchanged.
- **`public.mutate_entity_knowledge(<lock_token>, <request>)` is the only writer.** It runs inside the normal RT01 begin→stage→publish→mirror/confirm lifecycle, `service_role` only, and stages the absolute record (replay-safe).
- **Knowledge belongs to the knower; authority is controller-bound.** The record is stored once per knower, never per Run. Controller truth is resolved only from published `runs` through the shared EV2-10 resolver: MAINRUN when no published Run claims the knower, exactly one RUN # when it does. A non-mutable knower (location/faction/party/item) can never be Run-claimed, so MAINRUN is its controller.
- **Patch 1A grows by one domain, Patch 1B by one operation and one edge.** `entity_knowledge` is `dedicated` with the exhaustive writer set `[mutate_entity_knowledge]`; the compatibility contract gains `mutate_entity_knowledge` (blocked by a same-save `runs` change) and a trailing `entity_knowledge` edge on `stage_runs`/`delete_runs`/`reconcile_runs`. Closure keys on the explicit staging operation fact, so a value-equal replay still closes every Run-ownership doorway and never leaks into a later save.
- **Handoff transfers controller only.** MAINRUN↔RUN handoff changes the controller; the record stays attached to the same entity and is never copied to another entity or party member.
- **RT04 boundary preserved.** A free-form `discovery` consequence remains evidence only and never synthesizes an EV2-14 record; RT04's reconciliation mapping is unchanged.

### Durable lesson
A "frozen exact snapshot" regression that hard-codes a policy edge set or a migration frontier is a forward-snapshot, not a permanent invariant. When a later Mission is explicitly authorized to extend that exact policy/migration frontier, the owning files must be updated minimally to the new intended frontier; keeping them green by weakening the new Mission's required Patch 1A/1B change would violate the Mission. This was surfaced as a BUILDER STOP, then resolved by an intentional Surface Budget widening rather than by silent scope creep.

### Affected surfaces
`supabase/migrations/20260924000001_post_ev2_3_knower_safe_run_impact.sql` (create), `docs/POST-EV2-3-RUN-IMPACT-WIRING.md` (create), `tests/post_ev2_3/test_run_impact_wiring.py` (create); `supabase/README.md`, `.github/workflows/rt01-runtime.yml`, `tests/post_ev2_1/test_same_save_compatibility_dispatcher.py`, `tests/post_ev2_2/test_hot_run_registry.py` (modified minimally to the new frontier), `CHANGELOG.md` / `ENGINE_CHANGELOG.md` (this continuity).

### Deliberate non-goals / deferred ownership
- No second Run registry, knowledge store, save engine, generic impact ledger or lock service.
- No automatic knowledge propagation on handoff/rejoin, party knowledge, or prose-to-knowledge inference.
- No Hook or location/world mutation routes; RT04 keeps preserving those consequences.
- No change to EV2-14 schemas/docs or the EV2-09A resolution schema.
- Selective context/retrieval remained deferred beyond POST-EV2-3; disposable brainstorm realities and real knowledge intake stay with their later owners.

### Compatibility / recovery consequences
- Published `runs` remains the only controller authority; RT03/RT04 behavior is unchanged.
- `dm_meta.run_claims` remains coordination-only and grants no write authority.
- The forward migration chain gains one migration; existing databases upgrade normally and the clean baseline remains valid only for its pinned frontier.

### Verification evidence
- Local BUILD proof: the focused POST-EV2-3 suite passed on real PostgreSQL 15 and 17 (happy path, EV2-14 negative shapes, controller law, Run-claim non-authority, ambiguous/parked/malformed Run truth, both same-save orderings, handoff without propagation, RT04 preservation, publication integrity, service-role-only execution).
- The two frozen POST-EV2-1/2 regression files were updated minimally to the new frontier and pass.
- Final exact-head CI runs and merge identity are recorded by Orchestrator closeout.

---

## 2026-09-24 - POST-EV2-2 closeout: HOT Run registry + reservations

### Why this milestone exists
Fresh DM/AI runtime reads needed a compact answer to “which Runs matter now, and what stable-ID targets are they currently concerned with?” without duplicating the existing Run/controller authority or introducing a new locking subsystem. RHC already had the required durable pieces: published `runs`, stable IDs, the RT01 Save Gateway/publication spine, RT03 canonical Run reads, and the DM-only generic `dm_meta` runtime surface.

POST-EV2-2 therefore closes the gap by composing those existing authorities rather than building another engine beside them.

### Durable design
- **Published `runs` remains the sole Run/controller authority.** Run identity, control state and mutable actor ownership continue to come only from the existing Run truth.
- **`dm_meta.run_claims` is coordination metadata only.** The optional field is keyed by existing Run IDs and contains arrays of stable semantic target IDs. It records what a Run is currently concerned with; it does not grant ownership, mutation permission or controller authority.
- **HOTness is derived, not separately persisted.** A DM/AI derives the operationally relevant Run set from published `runs` plus current `dm_meta.run_claims`. No second HOT registry is stored.
- **The existing persistence engine is reused unchanged.** Ordinary `dm_meta` staging/publication continues through RT01. Canonical Run reads continue through RT03. No dedicated claim mutation route was added.
- **POST-EV2-3 retains collision and permission ownership.** POST-EV2-2 deliberately does not define what overlapping claims mean, whether a target is full-control/bounded-influence/no-touch, or whether an overlap should block a write.

### Durable lesson
Before creating a new subsystem, first check whether the existing engine already owns the required state, persistence and authority. When it does, extend the smallest existing surface instead of creating a parallel registry, dispatcher or lock mechanism.

### Affected surfaces
- `state/dm_meta.json` gained the empty/default `run_claims: {}` coordination field.
- `state/README.md` documents the field and keeps `runs` as the only authoritative Run/controller registry.
- `docs/POST-EV2-2-HOT-RUN-REGISTRY.md` records the operating convention and boundaries.
- `tests/post_ev2_2/test_hot_run_registry.py` proves the convention, including platform-stable source binding of the unchanged EV2-08 Run schema.
- `.github/workflows/rt01-runtime.yml` runs the bounded POST-EV2-2 proof on the existing PostgreSQL 15/17 runtime CI matrix.

### Deliberate non-goals / deferred ownership
- No second Run/controller registry.
- No new runtime key or mutation domain.
- No SQL migration.
- No dedicated `set_run_claims` mutation route.
- No Patch 1A domain-registry change.
- No Patch 1B same-save compatibility change.
- No database/advisory/lease lock service.
- No repository-path lock or canonical write-scope machinery.
- No collision, impact or permission semantics; POST-EV2-3 owns those concerns.
- No production Supabase activation or campaign-state publication.

### Compatibility / recovery consequences
- Existing Run/controller authority and RT03 reads remain unchanged.
- Existing RT01 generic `dm_meta` persistence remains the only durable path for claim notes.
- Clearing a Run’s claim note does not alter or delete its Run history or controller record.
- A parked/off-screen zero-owner Run with no claim remains historical Run truth but need not appear in the HOT operating picture.
- Because the gate introduced no migration or new domain, production Supabase required no activation step.

### Verification evidence
- Focused POST-EV2-2 proof passed on real PostgreSQL 15 and 17.
- Final exact-head implementation HEAD `134874338cddea1ad4fcc34f52e2dfc2c6921342` passed Flight Control run 141, Entity V2 identity validation run 275 and RT01 runtime foundation run 82.
- Fresh exact-head Codex review was clean with all review threads resolved.
- PR #135 squash-merged to `main` as `ac0e68b97ad21897a6b301ce4c27d94c1877a50a`.
- Post-merge read-back confirmed all five authorized surfaces on `main`.
- No production Supabase mutation occurred.

---

## 2026-09-24 — POST-EV2-1 series closeout: Save Gateway domain dispatch + clean bootstrap

### Why this milestone exists
RHC's persistence spine had grown safely one domain at a time, but two kinds of duplication were accumulating inside the single Save Gateway. Generic staging/deletion carried hard-coded knowledge of which runtime keys were ordinary, dedicated or forbidden, while the same cross-domain exclusions were repeated across several generic and dedicated mutation doorways. That was correct but increasingly fragile: adding another domain or compatibility edge could require editing several functions and could leave one ordering or doorway inconsistent.

POST-EV2-1 solves that scaling problem **inside** the existing RT01 publication spine. It does not create another save engine. The series also makes the engineering workflow remember when those machine-readable policies must evolve, then finishes with a verified fresh-install baseline so clean environments do not need to reconstruct the entire historical migration chain forever.

### Durable design
- **ONE Save Gateway, modular inside.** RT01 still owns begin / stage / publish / mirror / confirm. POST-EV2-1 modularizes admission and compatibility decisions without splitting publication authority.
- **Patch 1A owns runtime-domain admission policy.** `public._rhc_save_domain_policy(text)` is the single server-owned machine-readable registry for `generic | dedicated | forbidden`. It consumes only the state key, has no caller-writable policy store, exposes every legal dedicated writer as an exhaustive array, and fails unknown/undeclared keys closed. Generic `stage_campaign_state` / `delete_staged_campaign_state` consult that registry rather than growing hard-coded domain branches.
- **Patch 1B owns shared same-save coordination law.** `_rhc_same_save_compatibility_policy`, `_rhc_same_save_compatibility` and `_rhc_require_same_save_compatibility` centralize the already-existing exclusions between Runs/reconciliation, inventory, custody/admission, mutable entity state, applied statuses and Campaign Clock. The dispatcher answers only whether already-legal operations may coexist in one active save; dedicated routes still own semantic validation and authority.
- **Coordination is centralized without centralizing domain semantics.** Patch 1B re-declares the affected doorways only enough to delegate compatibility. Existing controller proofs, request validation, normalization, absolute targets, operation-fact lock tokens and RT01 lifecycle semantics remain owned where they already lived.
- **Patch 1C turns future impact into an explicit BUILD declaration.** Every future JOHNNY must state exactly YES or NO for mutation-domain / same-save compatibility impact. A YES must name the domains, compatibility edges if any, semantic owner(s), and required Patch 1A registry / Patch 1B dispatcher update + proof. A NO explicitly says no such runtime policy change is required. This declaration is workflow authoring memory, not runtime authority and not a fourth Mission Boundary Triad wall.
- **Patch 1D adds a bounded fresh-install baseline, not a history rewrite.** `supabase/baselines/20260924_post_ev2_1_clean_bootstrap.sql` lives outside `supabase/migrations/` and is valid only for an empty environment with the Supabase baseline roles already present. Existing databases continue through the historical migration chain.
- **Baseline equivalence is both source-bound and behavioral.** The baseline is a deterministic flattened replay of the exact 18-migration frontier at `d3292fd53cbb162a9e13c9e6148f88cfc474fa75`. Tests read those migration bodies from the immutable Git object, require the current historical files to remain byte-for-byte identical, build the expected baseline from the pinned contents, and then compare full replay vs baseline on PostgreSQL 15 and 17 across authority-relevant catalog state, grants, RLS/policies, routines, role safety, Unknown-safe seed state, Patch 1A/1B outputs and representative Save Gateway behavior.

### Architecture scars worth preserving
1. **A machine-readable registry must describe every legal writer, not a convenient singular route.** Patch 1A review exposed `item_custody` as a multi-writer domain: both `mutate_item_custody` and `admit_item_identity` are legal. The durable contract therefore uses exhaustive `dedicated_routes` arrays so metadata cannot silently lie about authority.
2. **Shared compatibility law must preserve operation facts, not only final values.** Same-save safety is about what happened inside the active save. A value-equal replay may still prove that a protected mutation operation occurred, so the dispatcher preserves existing lock-token operation facts instead of weakening compatibility to final JSON equality.
3. **Workflow memory must bind semantics to the authoritative declaration section.** Patch 1C's initial whole-document substring proof could remain green if required YES clauses disappeared from the actual declaration. The repaired contract tests parse the doctrine/template sections locally so affected compatibility edges and required 1A/1B update+proof cannot survive merely as stray text elsewhere.
4. **A claimed historical cut point must be mechanically tied to immutable history.** Patch 1D's first source-binding proof compared the baseline with the current working-tree migrations. Review correctly showed that history and baseline could drift together and remain green. The durable proof now reads each migration from the pinned Git object and separately asserts current history still matches it byte-for-byte.
5. **Baseline convenience must never become upgrade authority.** A clean baseline outside `supabase/migrations/` is safe because it is explicitly fresh-environment-only. Historical migrations remain the durable upgrade/audit trail for existing databases.

### Affected surfaces
Across the completed series:
- Patch 1A added the domain-policy registry and re-declared the generic staging/deletion doorways.
- Patch 1B added the compatibility policy/evaluator/enforcer and re-declared only the already-affected mutation doorways to delegate shared compatibility.
- Patch 1C changed `ORCHESTRATOR.md` plus the workflow contract tests.
- Patch 1D added the clean baseline, equivalence proof and bootstrap documentation, updated `supabase/README.md`, and wired `tests/post_ev2_1/**` into the existing RT01 PostgreSQL 15/17 CI job.
- This continuity closeout itself changes only `CHANGELOG.md` and `ENGINE_CHANGELOG.md`.

### Deliberate non-goals / deferred ownership
- No second Save Gateway, publisher, generation counter, mirror path or domain-specific save engine.
- No new mutation domain or new compatibility edge was invented by POST-EV2-1; Patch 1A/1B encode and centralize the established rules.
- No semantic rewrite of Clock, reconciliation, inventory, custody/admission, entity-state or applied-status validation.
- No caller-writable policy table or client-selected compatibility authority.
- No migration squash, deletion, rename or retirement. The 18 historical migrations remain the upgrade/audit authority.
- No use of the clean baseline on existing databases.
- No campaign-data import, BTH persistence, Story/RAG work, UI work or POST-EV2-2 implementation inside this series.
- No automatic future policy mutation merely because a JOHNNY declares YES; the owning Mission must still include the required runtime surfaces inside its own Surface Budget and proof.

### Compatibility / recovery consequences
- Existing Save Gateway callers retain the same legal generic keys, dedicated routes and fail-closed cross-domain exclusions; policy ownership moved inward without changing the external authority model.
- Future runtime domains have one declared admission registry to extend, and future same-save edges have one shared compatibility contract to update, reducing the chance that one doorway or ordering is forgotten.
- A fresh Builder no longer depends on chat memory to remember those obligations: Patch 1C makes the impact declaration mandatory before BUILD.
- Fresh/empty environments may bootstrap from the pinned Patch 1D baseline and then continue only with migrations created after that frontier. Existing environments must never apply that baseline and continue historical upgrades normally.
- Production Supabase is now synchronized through Patch 1A and Patch 1B on the dedicated RHC PostgreSQL 17 project. The synchronization changed engine definitions only: runtime remained published generation 2, mirror-confirmed at `889a7c4c7bbb271dccb31b2d0f74c28cd70789c8`, with `published_day = NULL`, no active save and no new campaign-state publication.
- Internal Patch 1A/1B policy helpers remain unavailable to `service_role`; supported callers continue through the established semantic mutation doorways rather than calling the policy machinery directly.

### Verification evidence
- Patch 1A PR #125 merged as `03a8ea26f10475e1aa96feade2ba6425f93d2b66`.
- Patch 1B PR #127 merged as `49cbe871e9e34d55eadfe421093cced6836d1415`.
- Patch 1C PR #129 merged as `d3292fd53cbb162a9e13c9e6148f88cfc474fa75`.
- Patch 1D final exact reviewed HEAD `3087ca8636ce5bd44979aad306f7055c7adb7bfa` passed Flight Control #137, Entity V2 identity validation #269 and RT01 runtime foundation #78; fresh exact-head Codex reported no major issues. PR #131 merged as `15e9a01767297c0aeba5e671e647d701a63874a3`; post-merge read-back confirmed the baseline, equivalence test, clean-bootstrap doc, README migration frontier and runtime CI wiring on `main`.
- Production PostgreSQL 17 migration history now contains `post_ev2_1_save_domain_policy_registry` and `post_ev2_1_same_save_compatibility_dispatcher`. Live read-back confirmed the 1A registry and all three 1B policy/evaluator/enforcer functions are present, known policy outputs match the established domain/edge contracts, unknown keys/operations fail closed in policy classification, and `service_role` has no EXECUTE privilege on those internal helpers.
- Production runtime read-back after synchronization remained generation 2 with confirmed ref `889a7c4c7bbb271dccb31b2d0f74c28cd70789c8`, `published_day = NULL`, `save_in_progress = false` and no staging generation.


## 2026-09-23 — Canon Intake foundation series closeout

### Why this milestone exists
Entity V2 gave RHC stable owners, explicit identity, knowledge/state boundaries and a guarded persistence spine, but it did not answer the write-side question: how can externally sourced, AI-extracted, homebrew, adapted or newly authored material enter the repository without becoming canon merely because it was found or generated? The Canon Intake series creates that missing reception-and-promotion path while preserving human DM authority and the existing RT01/repository publication authorities.

The series deliberately separates **capture**, **classification**, **human decision**, **material comparison**, **collision safety**, and **promotion**. That separation is the main engineering result. Each stage produces evidence for the next stage; none may silently impersonate the authority owned by a later stage.

### Durable design
- **Shared provenance is logistics metadata, not authority.** HB-01 introduced one optional classification-only provenance contract across Entity, Hook, Scenario and Encounter: `official | homebrew | adapted | unknown`. Legacy absence remains valid/Unknown. Provenance never grants canon, gameplay, visibility or runtime authority.
- **Candidate identity and source traceability are mandatory.** CI-01 created the pre-canon candidate contract with stable `candidate_id`, attached source context and only `extracted | classified` lifecycle states. There is deliberately no approved/published/canon state in the candidate itself.
- **Human approval is separate evidence.** CI-02 records explicit per-candidate human `approved | rejected` decisions in a sidecar ledger. Mixed selective outcomes remain legal; approval never mutates the candidate and never means published truth.
- **Comparison material is a sidecar, never truth.** CI-02.1 carries the actual candidate material plus optional proposed target and base publication pin. Proposed target is intent, not reconciled ownership; the payload remains non-canon until later promotion succeeds.
- **Collision safety is deterministic and fail-closed.** CI-03 consumes the approved candidate, material envelope and caller-supplied authoritative observation, then emits exactly `clear | duplicate | stale | conflict | unresolved`. Base pin mismatch is stale; exact material match is duplicate; divergence is conflict; missing evidence is unresolved. No fuzzy/AI equality or semantic merge is allowed. Only `clear` may proceed.
- **Promotion is a bridge, not a publisher.** CI-04 translates one eligible candidate into an explicit route instruction: `runtime_save` for mutable operational state or `repository_canon` for static/authored canon. Those routes delegate only to existing authoritative owners. CI-04 itself contains no raw SQL writer, no runtime-published writer, no arbitrary Git writer, and no second generation counter.
- **Success means authoritative read-back.** A promotion receipt is evidence, not truth authority. Runtime success requires confirmed publication identity sufficient to bind generation/ref; repository success requires exact durable commit identity. A write attempt without valid read-back cannot validate as success.
- **Trust-boundary evidence is immutable and exactly bound.** Promotion dispatch requires factory-issued immutable validated context covering CI-01/02/02.1/03 lineage. Returned receipts must bind the exact `promotion_id`, candidate and route. The adapter-returned object is snapshotted before validation, and the same validated snapshot is exposed, closing mutation-after-validation false-success windows.
- **The series law is monotonic authority.** `Extracted != classified != DM-approved != collision-clear != promoted/canon`. Each transition adds evidence; no earlier stage can claim the authority of a later one.

### Architecture scars worth preserving
1. **CI-02.1 existed because CI-02's original design left no actual comparison material for CI-03.** The correction was a small sidecar patch, not a rewrite of CI-01/CI-02. This preserved existing contracts while restoring the data needed for deterministic collision checks.
2. **CI-03 proved that collision evidence must bind the exact proposed target.** Unbound observations could otherwise clear a different target. The classifier also had to permit known-present-but-unreadable material to become `unresolved`, validate nested publication identity strictly, and gate semantic classification behind structural validity.
3. **CI-04 exposed a genuine trust-boundary class of bugs that earlier pure validators did not.** The durable boundary rule is: privileged dispatch must consume immutable proof and expose exactly the evidence that was validated.
4. **Review findings did not widen ownership.** Every repair stayed inside CI-04's Threat × Surface × Owner/Now. No finding was allowed to invent BTH semantics, direct Supabase/Git execution, conflict resolution, or a second publisher simply because the severity was high.

### Affected surfaces
The series added shared provenance metadata to the existing Entity / Hook / Scenario / Encounter schemas and validators, then introduced the Canon Intake contracts and validators for candidate, decision, material envelope, collision classification, promotion instruction and promotion receipt, with focused docs/tests under the existing repository workflow. CI-04 added only an adapter/interface boundary and synthetic adapters for proof; no real authoritative writer was added.

### Deliberate non-goals / deferred ownership
- No automatic canonization or AI approval authority.
- No real RHC campaign candidate promotion inside the foundation series.
- No BTH-specific persistence or owner mapping; BTH gates own the first live canary.
- No conflict/stale/duplicate semantic merge or reconciliation engine.
- No durable intake/promotion history database beyond stable contract IDs and authoritative receipts returned by existing routes.
- No new Supabase schema/migration, second Save Gateway, second generation counter, raw SQL writer or direct `runtime-published` writer.
- No generic repository write executor.
- No RUN ownership transfer into Canon Intake; RUN patterns informed isolation/identity/replay design only.
- No bulk historical import; Gate 36 remains its owner.
- No frontend/Velare implementation; Gate 40 owns the user-facing intake/review experience.

### Compatibility / recovery consequences
- Existing CI-01/02/02.1/03 contracts remain independent sidecars and were not rewritten by later gates. A future consumer can recover the intake chain by stable IDs rather than by hidden shared mutable state.
- Existing RT01/SAVE runtime authority and repository-main canon authority are preserved unchanged. Canon Intake can prepare an instruction for those routes but cannot complete publication by itself.
- Legacy content without provenance remains valid and Unknown rather than being backfilled by inference.
- Duplicate/stale/conflict/unresolved material remains non-promotable until an explicit later owner resolves it. CI-04 never auto-reconciles those states.
- The completed foundation is reusable across future candidate types because it keeps payload typing and owner routing small and explicit rather than inventing a universal campaign schema.
- The first real end-to-end proof is intentionally deferred to the BTH live canary, where one approved known package can exercise intake → collision → promotion → authoritative read-back without bulk migration risk.

### Verification evidence
- HB-01 PR #110 merged as `3fe3f6f4b327a261d2f2b6539deae58dd6895411`.
- CI-01 PR #113 merged as `ebde7dfb01cd38de59b7e6453ef0b830b51cad40`.
- CI-02 PR #115 merged as `103128ad7bff7e461799ac0af6364d12a1bd17bc`.
- CI-02.1 PR #117 merged as `ec5be462a872dd005f32d8dd902645b89ab28b62`.
- CI-03 PR #119 merged as `e8a005f827b8f652e3f6ac8671fdf30846feb456`; final exact-head Codex review was clean.
- CI-04 exact cleared implementation HEAD `bf217b86b257c88769787819e64f16c3342c24d5` merged in PR #121 as `e303d2cb8c2c9479c92bb405e8fae2a547a619da`; final exact-head Codex review was clean and required PR CI was green.
- Post-merge CI-04 proof confirmed both promotion schemas/docs on `main`. Supabase impact checks across CI-02.1 / CI-03 / CI-04 required no migration or runtime publication; the live runtime remained generation 2, mirror-confirmed at published ref `889a7c4c7bbb271dccb31b2d0f74c28cd70789c8`.
- No real RHC campaign candidate was promoted by the foundation sequence.

---

## 2026-09-21 — Entity V2 series closeout

### Why this milestone exists
The original RHC repository could represent campaign facts, but one real entity's identity, mutable state, inventory, custody, knowledge and narrative participation could be scattered across different roots and accidental owners. The first attempt to solve that as one large Entity V2 redesign became a review monolith and was deliberately abandoned unmerged. The series was then rebuilt as small, independently mergeable gates so each authority boundary could be proven before the next layer depended on it.

EV2-14 closes that construction arc. The important result is not a larger schema; it is a set of durable ownership laws that later PLAY, SAVE, BTH, UI and intake work can consume without inventing parallel truth.

### Durable design
- **Persistent identity is explicit.** Stable entity identity is distinct from mutable roles such as NPC/villain classification. Gameplay does not silently mint persistent identities.
- **Owner-local state is the default.** State, knowledge and inventory belong to the entity that owns them. Unknown / known / not_applicable semantics remain explicit rather than filled by inference.
- **Mutable authority is singular.** A mutable actor is controlled by CAMPAIGN MAINRUN or exactly one current RUN. Handoff transfers authority; it does not duplicate mutable reality into per-Run copies.
- **Definitions, live instances, custody and provenance remain separate.** Reusable definitions do not become live state automatically. Unique-item legal ownership and physical possession are separate facts, and persistent item admission is explicit and human-approved.
- **Durable mutation stays on the existing persistence spine.** Entity/state/item evolution composes with RT01 rather than creating a second save engine or convenience bypass.
- **Time is layered.** Mechanical duration, monotonic experienced Campaign Clock time, world-calendar position and historical chronology are separate authorities. EV2-13.420 owns exact mechanical-duration conversion; EV2-13.1 ages live timed statuses only from monotonic experienced time.
- **Knowledge is three-axis.** EV2-14 separates world truth, the selected knower's confirmed/belief/suspicion state, and reader visibility. Reusable facts live in `knowledge/facts.json`; owner-local records reference them. Local assertions carry their own visibility. Fact existence, DM knowledge, another entity's knowledge, party membership, BTH publication or NON_META exposure never auto-propagates knowledge.
- **BTH is the canonical acceptance case.** One event may be true RHC canon and deliberately reader-visible while no hero knows it. Publication is exposure, not a character-knowledge mutation.
- **Safe projection is narrower than safe fact visibility.** A fact-reference may point at NON_META truth while its knower-local `topic`, `note` or `source` contains META provenance/context. Player-facing projection therefore exposes the referenced fact's classified safe content only; those local annotations remain DM/internal by default.

### Architecture scars worth preserving
1. **Monolithic Entity V2 / PR #6 was burned, not rescued.** Review discoveries were valuable, but implementation size became the defect. The rebuild proved that durable architecture can be recovered through small gates without preserving the failed container.
2. **The first EV2-13.420 temporal attempt / PR #99 was retired.** It mixed mechanical duration, world calendar, chronology, temporal jumps and controller concerns, and incorrectly treated a D&D turn as additive six-second elapsed time. The correction was to split time into layers and build only the smallest consumer-driven primitive.
3. **EV2-14 annotation projection P2 was real but local.** The correct repair was not a new visibility subsystem. It was to keep fact visibility authoritative on the underlying fact and make knower-local annotations internal by default for player-facing fact projection.
4. **Proof belongs to the claimed invariant.** The EV2-13.1 terminal lifecycle review exposed a missing direct regression even though implementation behavior was already correct; a tests-only repair was the right response.

### Affected surfaces
The completed series spans the Entity V2 schemas/validators and domain docs; relationship / Hook / Scenario / Encounter / Run records; inventory and item-custody/admission surfaces; engine-owned mutable entity state; duration and timed-status lifecycle helpers; owner-local knowledge/read semantics; associated runtime/Supabase domain routes where live mutation was actually required; and the focused tests / CI that enforce those boundaries.

### Deliberate non-goals / deferred ownership
- No bulk migration of all legacy RHC entities into Entity V2 merely to declare the series complete.
- No runtime/Supabase knowledge mutation or automatic knowledge propagation.
- No BTH persistence / SAVE integration; BTH-00 remains the owner.
- No RAG / embeddings / search-index architecture.
- No repository-wide META/NON_META terminology rename.
- No world-calendar/Harptos anchor invention from elapsed time.
- No broad entity-taxonomy expansion without a real consumer.
- No UI/frontend implementation inside Entity V2 itself.
- No destructive migration of legacy `npc/npc_state.json` knowledge solely to match the new model.

### Compatibility / recovery consequences
- Legacy NPC knowledge remains readable historical/legacy data while EV2-14 defines the forward owner-local authority model.
- Existing RT01/RT02 publication and Campaign Clock authority are preserved; Entity V2 composes with them rather than replacing them.
- `item:vampire` remains the first live admitted Entity V2 item proving the identity/custody/admission chain end to end.
- No real Entity V2 knowledge record exists merely because EV2-14 is complete. Future intake/runtime work must be explicit and consumer-driven.
- The planned Entity V2 construction series is now closed. Later work should consume these authorities instead of reopening the series by archaeology.

### Verification evidence
- EV2-14 final cleared PR HEAD: `fee8fbab8738cea4ba26d6cbe7ef8bb031856441`.
- PR #105 merged to `main` as `1d81a875692918ab3675d45c27bf305f71fc73b5`.
- Required PR CI was green; the only scoped Codex P2 was repaired and its thread resolved.
- Fresh exact-head Codex review on the repaired head reported no major issues.
- Post-merge Entity V2 identity validation completed successfully on the merge SHA.
- Asana EV2-14 closeout and the repository architecture snapshot record the series as COMPLETE; Git/PR history remains the forensic source of per-gate execution detail.

---

## 2026-09-15 — Post-HWB workflow closeout: Builder handoff + Mission Boundary Triad

### Why this milestone exists
After the Foundation Seal and Semantic Authority sequence, two small workflow gaps remained. The Builder still spent execution time watching CI after opening a PR even though evidence routing already belonged to the Orchestrator, and the repository had Threat Model, Surface Budget and Deferred Ownership concepts without one explicit rule that made them operate together during review/repair. Closing those two gaps as one small workflow sequence keeps execution cheaper and makes scope classification harder to accidentally widen.

### Durable design
- **Builder transport ends at the PR handoff.** After Orchestrator release, Builder pushes the approved branch, verifies exact local HEAD equals remote HEAD, opens/updates the PR, reports PR number + exact remote HEAD + exact changed files, then STOPS and returns to the Orchestrator. Builder does not wait or poll CI merely to report green status.
- **Orchestrator owns evidence lifecycle after handoff.** CI/Codex observation, review-finding classification, repair release, exact-head merge and closeout remain Orchestrator responsibilities.
- **Mission Boundary Triad is one boundary.** Threat Model × Surface Budget × Deferred Ownership are three walls of one Mission, not independent checklist headings.
- **Repair requires YES / YES / YES.** A finding becomes current repair work only when THREAT = YES, SURFACE = YES and OWNER/NOW = YES. Any NO routes the concern to its actual owner or STOP/defer path.
- **Severity never grants authority.** P0/P1 raises attention but cannot widen threat assumptions, authorize an undeclared path or pull later-owner work into the current Mission.
- **Triad and HWB have different jobs.** The Triad decides whether proposed work belongs to this Mission; HWB mechanically enforces the already-authorized path budget. The Triad does not replace Semantic Authority or create a fourth authority layer.

### Affected architecture
The completed sequence changed `BUILDER.md` in PR #82 and `ORCHESTRATOR.md` + `BUILDER.md` in PR #84. This continuity closeout itself changes only `CHANGELOG.md` and `ENGINE_CHANGELOG.md`.

### Deliberate non-goals / deferred ownership
- No GitHub Actions or Hard Write Boundary redesign.
- No new CI/Codex automation or Builder self-review mechanism.
- No runtime, Supabase, SAVE, canon or gameplay behavior change.
- No new Asana lifecycle state or live gate routing in repository documentation.
- No EV2-10 inventory/ownership design inside this closeout.
- No universal rule is created merely by describing the completed sequence.

### Compatibility / recovery consequences
- Existing BUILD authorization, branch-bound JOHNNY, exact-head review and merge law remain intact.
- Builder restarts still recover from current repository truth + JOHNNY; the stop-after-PR rule simply returns evidence watching to the Orchestrator earlier.
- Existing Surface Budget mechanics remain unchanged. The Triad adds semantic/workflow classification before repair rather than changing the mechanical fence.
- The next domain work can consume this workflow without carrying the completed post-HWB cleanup sequence in active construction context.

### Verification evidence
- Builder CI Polling Cleanup: exact implementation HEAD `c694f1e687e8cb91992acead5ca36ad1aa94ffb0`; one-file `BUILDER.md` patch; Flight Control, Entity V2 validation and Hard Write Boundary green; fresh exact-head Codex review found no major issues; PR #82 merged as `4a524e224fce06dcf29018dac62c01c0f9b09a59`; JOHNNY #81 closed completed.
- Mission Boundary Triad: exact implementation HEAD `1b5afda9bdc202f064a76f4e6468f243c6926b47`; local proof 25 workflow tests + 141 write-boundary tests + clean `git diff --check`; Flight Control, Entity V2 validation and Hard Write Boundary green; fresh exact-head Codex review found no major issues; PR #84 merged as `f897d354c57fc6f991ee35af1a92dde3f70bd898`; JOHNNY #83 closed completed.

---

## 2026-09-15 — HWB Foundation Seal + Semantic Authority patch series

### Why this milestone exists
The RHC control plane had learned how to describe scope through JOHNNY, Surface Budget, Dropgate lanes and exact-head review, but description alone was not enough. A capable Builder could still attempt out-of-scope writes, ordinary runtime SAVE could still widen authority by naming arbitrary keys, normal Final Save needed a repository-history route that did not borrow BUILD permission, and review/enforcement could still harden an accidental technical interpretation into product/game law. This patch series closes those gaps as one coherent protection milestone.

### Durable design
- **Foundation Seal has three distinct protection planes.** HWB-01 owns BUILD write authority, HWB-02 owns ordinary SAVE runtime-key authority, and HWB-03 owns normal SAVE repository-history authority. None of the three is a substitute for the others.
- **HWB-01 makes the branch-bound Surface Budget mechanical.** Local ordinary commits and a trusted base-defined server check grade BUILD writes against the same JOHNNY-declared machine budget. Unauthorized create/modify/delete/rename/copy/type-change evidence fails closed; the PR cannot edit the trusted judge that grades it.
- **HWB-02 makes runtime SAVE authority server-owned.** Ordinary SAVE generic stage/delete is restricted to exactly `daily_recap`, `day_resolution`, `live_status`, `dm_meta`, `narrative_hooks`, and `runs`. `campaign_clock` remains owned by RT02's dedicated route and `run_reconciliations` by RT04's dedicated route. The existing RT01 publication spine remains the one persistence engine.
- **HWB-03 gives Final Save its own repository-history contract.** A legal `save/*` candidate adds exactly one new `canon/days/day_<positive decimal integer>.md`, may optionally add/modify `canon/timeline.md`, cannot rewrite/delete finalized days, cannot DELETE, and cannot cross into engineering/runtime/schema/test/workflow surfaces. Campaign Day ID is archive sequence identity, not world chronology; leading zeroes are legal and there is no digit-count ceiling.
- **Semantic Authority sits above enforcement.** The durable authority chain is: **human/product/game intent -> declared semantic invariant -> owning Mission/lane -> enforcement -> tests/review**. Guards, validators, CI, tests, regexes, implementation details and review findings may enforce or provide evidence for declared law; they do not create product/game requirements.
- **No orphan blocking rules.** Every blocking rule must trace to a declared semantic invariant and the Mission/lane that owns it. If implementation, proof or review conflicts with declared intent, the system stops and returns to the Orchestrator instead of silently hardening the stricter technical interpretation.
- **Implementation authority is not semantic authority.** An explicitly authorized BUILD Mission may implement a guard for a SAVE/PLAY/READ-owned invariant, but that owning lane keeps the meaning of the rule. BUILD owns technical HOW only when authorized; it cannot invent, widen, reinterpret or impose the invariant.
- **Severity remains evidence priority, not authority.** Review severity can raise attention but cannot create scope, ownership, semantics or a new product requirement.

### Scars that shaped the durable law
- The HWB-03 `day_XXX` review nearly turned schematic notation into an undeclared exact-three-digit/day-999 gameplay rule. That finding was rejected as product-law invention; the actual invariant is an unbounded positive decimal archive identity.
- A real HWB-03 defect then showed why semantic declarations still need precise implementation: Python's bounded `int()` conversion would have created an accidental finite ceiling on an explicitly unbounded identity. Positivity is therefore proven lexically rather than by bounded numeric conversion.
- Semantic Authority's first wording over-corrected in the opposite direction by implying BUILD could enforce only BUILD-owned invariants. The final law separates implementation authority from semantic ownership, allowing authorized cross-lane technical implementation without transferring the meaning of the rule.

### Affected architecture
Across the completed series, the durable surfaces include the HWB-01 shared write-boundary validator/hook/server fence, HWB-02 forward runtime migration and proof, HWB-03 SAVE-lane extension to the shared write-boundary substrate, and the Semantic Authority rules in `ORCHESTRATOR.md`, `BUILDER.md`, and `tests/test_workflow_dropgate.py`. This continuity closeout itself changes only `CHANGELOG.md` and `ENGINE_CHANGELOG.md`.

### Deliberate non-goals / deferred ownership
- No universal policy registry or new governance framework beyond the declared authority chain.
- No merger of BUILD, SAVE, PLAY or READ lanes; lane separation is preserved.
- No alternate save engine, runtime rewrite, new Supabase domain, or gameplay/canon mutation in this closeout.
- No world-date/time-travel chronology design; Campaign Day archive identity remains separate from future temporal chronology work.
- No Builder CI-polling cleanup, Mission Boundary Triad implementation, root `.gitignore`, EV2-10 or other downstream gate inside this patch series closeout.
- No rule becomes authoritative merely because Codex, CI, a validator or a test asserts it.

### Compatibility / recovery consequences
- RT01/RT02/RT03/RT04 remain the runtime spine. HWB-02 narrows ordinary generic SAVE mutation without creating a second persistence path.
- Final Save no longer depends on BUILD/JOHNNY authority; the fixed SAVE repository-history contract is mechanically distinct from BUILD while remaining fail-closed.
- Existing branch-bound JOHNNY and Surface Budget remain the BUILD control-plane contract; Semantic Authority constrains what those mechanisms may legitimately enforce rather than replacing them.
- The dedicated live RHC Supabase project was caught up through RT02, RT03, RT04 and HWB-02 during HWB-02 closeout because repository progression had outpaced production activation.
- The Foundation Seal is complete, but it is not a claim that all future domain mechanics are built. It protects how later work gains authority and becomes durable.

### Verification evidence
- HWB-01: PR #64 merged final reviewed HEAD `c6af02fafcf04db9917aa8cee66be13015200b14` as `b9e73edd0d82c5f3601060086febfbd42b407528`; post-merge canary proved an authorized path passes and an added out-of-budget path fails the trusted Hard Write Boundary.
- HWB-02: exact implementation HEAD `3d3caecdfdefe54bc0d81d79d5998d2c6a312882`; 44 focused tests, 364 runtime-matrix tests and 714 full-suite tests passed with clean `git diff --check`; PR #70 merged as `45f97a8fdd231f2d20e34d1b186f7815422bbb93`, followed by live PostgreSQL 17 migration/read-back proof.
- HWB-03: final exact reviewed HEAD `fc2f10b4a78413bbccab6bbc8cb4f972a37da55d`; 141 focused write-boundary tests passed with clean `git diff --check`; PR #72 merged as `dc58f6d08a30b6d8f5fbac4bad2bb2977d9cba6e`.
- Semantic Authority / No-Orphan Rules: repaired exact HEAD `b337ebeb4ec46bfd2fa1631540ccac268ec2ae9b`; 25 workflow tests and 141 write-boundary tests passed with clean `git diff --check`; fresh exact-head Codex review found no major issues; PR #74 merged as `b6ac66af9fc03dea11a99f7f1f3fc1ba141d802a`.

---

## 2026-09-12 — RT04 Safe Run Reconciliation

### Why this milestone exists
RT03 could read one authoritative published Run, and EV2-09A could describe proposed consequences, but there was no legal bridge for accepting an off-screen Run resolution back into shared authoritative reality. RT04 adds that bridge without creating a parallel save engine or letting caller-supplied Run truth certify itself.

### Durable design
- **One reconciliation route inside the existing Save Gateway.** `public.reconcile_run_resolution(lock_token, request)` stages reconciliation only inside the normal `begin_campaign_save -> reconcile -> publish_campaign_save` lifecycle.
- **Source truth is always re-resolved.** The source Run is obtained only through `dm_runtime_read_run`; the caller identifies a Run but cannot supply authoritative Run state.
- **Translation is bounded by current legal owners.** RT04 can update the source Run's deterministic `outcome_summary`, apply the continuation-versus-collapse mutable-ownership law through subtractive `released_mutable_owners`, and stage the reconciliation receipt. It does not invent mutation APIs for domains that do not own one yet.
- **Unsupported consequences are preserved, not discarded.** Accepted effects targeting entity state, inventory/custody, Hook mutation, location/world state or knowledge remain in the `run_reconciliations` receipt with their validated summary and missing downstream owner.
- **Replay and same-save contradiction fail closed.** `run_reconciliations` is engine-owned and blocked from generic stage/delete; one source Run may be reconciled only once per active save; the candidate `runs` batch is validated before staging and generic `runs` mutation is closed after a new reconciliation is staged.
- **Mutable authority remains exclusive.** Stale/removed Runs, overlapping/newer owners, malformed lineage, ownership contradictions and replay fail before writes. A Run with remaining owners continues; a zero-owner result removes stale mutable authority while preserving historical participation.

### Affected surfaces
`supabase/migrations/20260912000001_rt04_safe_run_reconciliation.sql`, `tests/rt04/**`, `supabase/README.md`, `.github/workflows/rt01-runtime.yml`.

### Deliberate non-goals / deferred ownership
- No second save engine, alternate publish function, independent generation counter or parallel mirror path.
- No caller-controlled source truth and no ownership transfer primitive disguised as reconciliation; `released_mutable_owners` is subtractive-only.
- No new durable mutation surface for entity state, inventory/custody, Hooks, world/location state or knowledge.
- No live Supabase mutation/deployment during repository BUILD.
- No future Hard Write Boundary implementation inside RT04.

### Compatibility / recovery consequences
- RT04 extends the existing RT01 save/publication/mirror-confirmation spine rather than competing with it.
- Replay of one accepted resolution is blocked by durable consumption identity; chaining from a later published save remains legal because it starts from new authoritative state.
- Historical Run participation survives reconciliation even when mutable authority collapses.
- Unsupported-domain consequences remain recoverable as durable accepted receipts until their actual owners are built.

### Verification evidence
- Final focused RT04 proof: 64 passed on real PostgreSQL 15 and 17.
- Final full repository suite: 598 passed; `git diff --check` clean.
- PR #54 merged to `main` as `781ba6c4769a510e1941ec49af8a7bd2083566c3`.

---

## 2026-09-12 — RT03.5 CAMPAIGN MAINRUN Terminology Hardening

### Why this milestone exists
Before RT04, the repository had clear Run mechanics but no durable name for the normal authoritative gameplay lane. The generic word `main` was also dangerously overloaded with Git `main` and cross-continuity phrases such as `Prequel/Main Canon`. RT03.5 removes that semantic collision before reconciliation mechanics depend on the terminology.

### Durable design
- **CAMPAIGN MAINRUN / MAINRUN** names the normal authoritative Rolling High Club gameplay lane.
- **RUN #** remains a temporary continuation/execution lane inside the same campaign reality, not a parallel reality, alternate continuity or save slot.
- Repository **Git `main`** remains an engineering branch name only.
- PREQUEL/SEQUEL remain separate continuities; `Prequel/Main Canon` remains source/canon language for separate continuity and is explicitly not MAINRUN.
- EV2-08 now states the exclusive mutable-authority invariant in words: an entity may be mutable in exactly one current gameplay lane, either MAINRUN or exactly one RUN #. Parking alone does not release ownership; old Runs may preserve history after handoff without retaining mutable authority.

### Affected surfaces
`PROJECT_PRIMER.md`, `docs/EV2-08-RUN.md` only.

### Deliberate non-goals / deferred ownership
- No schema, migration, API/CLI, machine-readable value, runtime behavior, lifecycle transfer mechanism or reconciliation implementation.
- No repository-wide prose rewrite beyond the two authorized terminology surfaces.
- No persisted MAINRUN-like value was introduced.

### Compatibility / recovery consequences
- Existing Run data and validators remain unchanged; this is a domain-language hardening layer only.
- Future runtime/UI/API work has a stable human term for the gameplay lane without learning Git `main` as campaign vocabulary.
- RT04 can reason about MAINRUN-vs-RUN mutable authority without first inventing the terminology itself.

### Verification evidence
- Terminology re-scan found no remaining gameplay-lane `main` ambiguity in scope.
- Run validation reported 2 Scenario, 4 Encounter and 3 Run records valid; focused Run tests: 29 passed; `git diff --check` clean.
- Exact-head Codex review reported no major issues.
- PR #52 merged to `main` as `4de0c0353c2dcfe3c6196798a6c44bfc7778641b`.

---

## 2026-09-11 — RT03 Canonical Run Runtime Read / 09B-ID Canary

### Why this milestone exists
RT01 established the published-runtime spine and RT02 added authoritative campaign time, but the runtime still needed one real domain consumer to prove it could resolve a canonical entity-like record by identity without creating a second persistence model. The chosen canary was one EV2-08 Run.

### Durable design
- **One supported service read.** `public.dm_runtime_read_run(run_id)` returns the RT01-D runtime metadata envelope plus exactly one authoritative EV2-08-valid Run from the same published generation.
- **One system-owned namespace.** Canonical Run records live only in the published `runs` state key, whose value is a JSON array. Exact string `run_id` matching defines candidacy; arbitrary JSON elsewhere is discovery noise, never Run authority.
- **Truthful absence stays truthful.** Zero candidates returns `run: null` with coherent runtime metadata rather than fabricating a default.
- **Ambiguity and invalidity fail closed.** Malformed ids, unreadable `runs`, duplicate identity claims, invalid EV2-08 records and conflicting mutable ownership refuse the read.
- **Validation helpers are internal.** Record-shape/coherence helpers mirror EV2-08 semantics but are revoked from `service_role`; the supported service contract remains the metadata-bearing read.
- **RT03 is read-only.** No staging, seeding, Clock arithmetic, repository/Git resolution, mirror changes or new persistence path.

### Affected surfaces
`supabase/migrations/20260911000002_rt03_canonical_run_runtime_read.sql`, `tests/rt03/**`, `supabase/README.md`, `.github/workflows/rt01-runtime.yml`.

### Deliberate non-goals / deferred ownership
- No Run mutation or reconciliation route.
- No EV2-09A promotion to canon and no redesign of EV2-08.
- No recursive Scenario/Encounter/participant/location hydration.
- No Clock arithmetic from `campaign_anchor.campaign_time`.
- No Git/repository resolution or new mirror machinery.

### Compatibility / recovery consequences
- Existing RT01 mirror carriage transports published Run state generically; RT03 adds only canonical resolution/validation at read time.
- The read preserves parked Run truth and never promotes parked state into active authority.
- Cross-domain existence and Git-anchor validity remain repository-owned; RT03 consumes the Run record instead of absorbing those owners.

### Verification evidence
- Final focused RT03 proof: 81 passed on real PostgreSQL 15 with synthetic Run data.
- Final RT01/RT02/RT03 runtime matrix: 300 passed; final full repository suite: 534 passed; `git diff --check` clean.
- PR #50 merged to `main` as `1394316848cd5b3e70f96e323c4814541ec21d3c`.

---

## 2026-09-11 — RT02 Campaign Clock Foundation

### Why this milestone exists
After RT01 activation, RHC had a durable published runtime but no first-class in-world time authority. Day, broad phase, exact established duration and Long Rest count needed one deterministic owner that could advance without deriving fake precision from narration, wall-clock time or message count.

### Durable design
- **One Clock record, no parallel persistence path.** `campaign_clock` is one engine-owned state record inside the existing generation store.
- **One validated mutation route.** `public.stage_campaign_clock(lock_token, clock)` validates the complete absolute target against the authoritative published Clock. Generic `stage_campaign_state` / `delete_staged_campaign_state` reject `campaign_clock`.
- **Broad presentation time and monotonic duration coexist without pretending to be the same thing.** `day`/`phase` may remain partially Unknown, while `elapsed_campaign_minutes` and `long_rests_completed` are monotonic counters from the RT02 epoch.
- **Unknown is valid truth.** RT02 never backfills a current day, phase, elapsed duration or Long Rest count merely to satisfy the schema.
- **No second day authority.** `publish_campaign_save` derives `campaign_runtime.published_day` from the candidate Clock day; a null Clock day keeps the published locator null.
- **Replay is safe.** Staging an absolute target avoids double-advancing the monotonic counters when the same intended update is replayed.

### Affected surfaces
`supabase/migrations/20260911000001_rt02_campaign_clock.sql`, `docs/CAMPAIGN_TIME.md`, `docs/RHC_WORKSYSTEM.md`, `supabase/README.md`, `tests/rt02/**`, `.github/workflows/rt01-runtime.yml`.

### Deliberate non-goals / deferred ownership
- No Autosave or Deferred Event Scheduler.
- No Rest recovery/resource consequences, effect/status duration ticking, business/economy consumers or NPC schedules.
- No current-campaign time reconstruction/backfill.
- No mirror-worker or DM read-facade redesign.

### Compatibility / recovery consequences
- The existing RT01 Save Gateway remains the publication path; RT02 adds one protected semantic route rather than another save mechanism.
- `campaign_runtime.published_day` becomes derived checkpoint/locator metadata while `campaign_clock` owns semantic campaign time.
- Earlier campaign history is not reconstructed; counters begin truthfully at the RT02 epoch.

### Verification evidence
- Focused RT02 proof: 43 passed on PostgreSQL 15.
- RT01 A/B/C/D + activation/mirror/workflow matrix: 240 passed; full repository suite: 452 passed; `git diff --check` clean.
- PR #48 merged to `main` as `7723d48b00d013a823b5d1ab1d4719be7c6b79b9`.

---

## 2026-09-11 — RT01 Umbrella Activation PASS

### Why this milestone exists
RT01-A/B/C/D were intentionally inert implementation until one live managed-project proof could establish the complete authority contract. After the PostgreSQL 17 compatibility repair, activation resumed on the same dedicated RHC project and completed the cross-system proof instead of treating migration installation alone as cutover.

### Durable activation result
- **SQL/Supabase is now the live operational published-world surface.** This is the explicit RT01 umbrella ACTIVATION PASS. Repository `main` remains implementation/campaign-canon truth; `runtime-published` remains durable checkpoint/provenance evidence.
- **Unknown was preserved, not filled in.** Bootstrap generation 1 was published with `published_day = NULL` and empty state; activation did not invent campaign facts merely to make the runtime non-empty.
- **The first live checkpoint is exact and bound.** Generation 1 is verifier-confirmed at remote `runtime-published` SHA `ef6ba3b3eeb95891454a606ecdca0fb285cb374c`, with bootstrap base `de266f1e0108bd1aff93bd9d164abc22f7991412`, exact parent continuity, artifact-only commit shape, canonical byte parity and remote read-back.
- **Privilege isolation is live, not only tested.** `service_role` can use `dm_runtime_read()` but cannot directly SELECT raw generation storage, directly execute `dm_runtime_lookup()`, bind the bootstrap base or confirm the mirror. Verifier-only capability stays narrow.
- **Engineering release is live-safe.** A real `begin_engineering_release()` probe against the exact activation `main` SHA succeeded and was aborted cleanly, leaving generation 1, state, day and confirmed checkpoint unchanged.

### Activation boundary / consequences
- Migration installation alone was never authority cutover. The PASS required published-only read proof, guarded mutation/publication, exact Git mirror/read-back, verifier confirmation, privilege checks, Unknown-safe behavior and a live engineering-release lifecycle probe.
- No real RHC campaign entities, Hook/Scenario/Encounter/Run facts, world day or inventory were imported during activation. Generation 1 is deliberately empty/Unknown because that was the truthful state available at cutover.
- Historical RT01-A/B/C/D and PG17 compatibility ledger entries remain unchanged because their “inert” statements describe the state at those earlier milestones. This entry supersedes that state for all later work.
- RT01 is now closed; RT02 Campaign Clock may enter Design. No RT02 implementation is implied by this closeout.

### Live proof
- Dedicated RHC Supabase PostgreSQL 17: migrations `000001`-`000006` present.
- Published runtime: generation `1`, no active save/staging, `runtime_published_confirmed = true`.
- Confirmed Git checkpoint: `ef6ba3b3eeb95891454a606ecdca0fb285cb374c`.
- Exact bootstrap base: `de266f1e0108bd1aff93bd9d164abc22f7991412`.
- `runtime-published` differs from the base only by `runtime/published-checkpoint.json`.
- `dm_runtime_read()` returns generation 1/current fallback metadata; zero-hit targeted read returns `results: []` with the same coherent runtime metadata.
- Engineering-release begin/abort probe returned to the same confirmed generation 1 with no campaign mutation.

---

## 2026-09-10 — RT01 Activation Compatibility — PostgreSQL 17 verifier bootstrap

### Why this milestone exists
The first real RT01 umbrella activation reached a dedicated managed Supabase PostgreSQL 17 project. Migrations `000001`-`000003` applied, then `000004` failed atomically because the original RT01-C verifier check treated any `pg_auth_members` row as unsafe. PostgreSQL 16+/17 represents role membership with independent ADMIN/INHERIT/SET options and automatically gives a non-superuser `CREATEROLE` creator an ADMIN relationship on a role it creates. The literal zero-membership rule was therefore a PG15-era implementation assumption, not the actual security invariant.

### Durable design
- **Capability isolation is authoritative; literal zero membership is not.** `rhc_mirror_verifier` remains NOLOGIN and non-privileged. The security goal is that only the intended migration/mirror execution path can narrow into verifier authority while `service_role` and unrelated roles cannot.
- **PG16+/17 accepts one bounded creator relationship.** The migration accepts only the executing non-superuser creator's expected ADMIN relationship, rejects inherited access, unrelated members and incoming memberships, and ensures the intended executor has an explicit non-inherited SET path for `SET ROLE rhc_mirror_verifier`.
- **Unsafe state still fails closed.** Unsafe verifier attributes, missing expected creator ADMIN semantics, unrelated/incoming memberships, or inability to establish the narrow SET path abort installation before verifier object grants are trusted.
- **PG15 behavior stays strict.** The pre-PG16 path preserves the original membership-clean installation rule, keeping the existing RT01 A/B/C/D proof compatible.
- **Applied live migrations are immutable history.** Because `000001`-`000003` had already applied successfully to the dedicated RHC project, they became frozen. `000004` had rolled back atomically and was not applied, so correcting that pre-activation migration was the legal smallest repair surface. `000005`-`000006` remained untouched.

### Affected surfaces
`.github/workflows/rt01-runtime.yml`, `supabase/README.md`, `supabase/migrations/20260908000004_rt01c_runtime_published_git_handshake.sql`, `tests/rt01activation/test_pg17_verifier_compatibility.py`.

### Deliberate non-goals / deferred ownership
- No provider-superuser dependency and no manual/ad-hoc live Supabase workaround.
- No broad auth/RLS redesign, generic role-management framework, cryptographic worker identity, or hostile-provider/admin hardening.
- No change to campaign facts, state, day, generation, RT01-D semantics, or migrations `000001`-`000003` / `000005`-`000006`.
- No RT02+ implementation and no implicit SQL authority cutover. Compatibility repair is not activation.

### Compatibility / recovery consequences
- The dedicated RHC Supabase project remains intentionally inert with only `000001`-`000003` applied. Activation resumes from repaired `main` by applying `000004`-`000006`, proving live A/B/C/D, exact `runtime-published` SHA/read-back/verifier behavior, privilege boundaries and Unknown-safe state, then making an explicit Orchestrator ACTIVATION PASS or STOP decision.
- A failed pre-activation migration can be repaired when the failure was atomic and the migration was never recorded as applied; an already-applied production migration is not rewritten to make later activation easier.

### Verification evidence
- Exact cleared implementation HEAD: `37905a8c49cae824a90e6f7b965a7107452f4374`.
- Local proof: PostgreSQL 17 focused 4 passed; PostgreSQL 15 RT01 matrix 171 passed; full repository 409 passed; `git diff --check` passed.
- Exact-head PR CI passed for RT01 runtime foundation, Flight Control and Entity V2 identity validation.
- Fresh exact-head Codex review reported no major issues.
- PR #42 merged to `main` as `b3c23fb34f133924581d115bf6e28d109ca05a1b`.
- Post-merge `main` proof passed for RT01 runtime foundation and Entity V2 identity validation.

---

## 2026-09-10 — RT01-D DM Read Surface + engineering_release

### Why this milestone exists
RT01-A/B/C already provided the inert published-runtime floor, guarded SQL mutation lifecycle, and exact Git mirror/read-back confirmation handshake. What was still missing was a safe consumer-facing read contract and a legal way to adopt reviewed engine/runtime-support evolution from `main` without pretending that engineering work is a campaign mutation. RT01-D closes both gaps as the final implementation child of the RT01 foundation.

### Durable design
- **One SQL-first DM/AI read facade.** `dm_runtime_read()` owns both compact-context and targeted-read modes so every supported service-facing response carries one coherent runtime checkpoint envelope. Zero-hit lookups still carry generation/freshness metadata.
- **Published-only means published-only.** Service consumers do not read staging/future generations through raw generation storage. `dm_runtime_lookup()` remains an internal helper, and the forward RT01-D migration revokes `service_role` direct SELECT on `campaign_state_generations`.
- **Unknown remains a valid answer.** Generation 0 and uninitialized RHC owners remain empty/null/unknown-shaped; no current day, hook, party state or narrative fact is fabricated merely to satisfy a read schema.
- **Freshness states are explicit.** Current SQL generation may be mirror-pending while `last_confirmed_git_ref` points to an older durable checkpoint. Those are different truths and are labelled as such. Git fallback is pinned to an explicitly confirmed exact ref, never bare `main` or a mutable branch head.
- **Engineering evolution is not campaign mutation.** `engineering_release` clones the current published state, preserves campaign facts and `published_day` mechanically, binds one exact approved `origin/main` target, publishes through the existing SQL lifecycle, then adopts that engineering target into the runtime lineage.
- **Two-parent adoption is auditable.** The engineering Git candidate uses ordered parents `[confirmed runtime, approved main target]`, validates that the target is reachable from fetched `origin/main`, constrains changed paths to approved engineering/runtime-support surfaces, regenerates canonical checkpoint bytes, reads back the actual remote SHA, and finishes through the existing verifier boundary.
- **Retry repairs the same release.** If Git push/read-back/confirmation fails after SQL publication, the same published generation and bound engineering target are retried rather than consuming another generation.
- **Path scope is checked without rename folding.** Git rename detection is disabled for engineering-scope validation so a protected campaign source path renamed into an allowed engineering prefix cannot disappear from the changed-path evidence.

### Review lessons preserved as contract, not diary
Three review findings changed the durable contract and therefore matter beyond the transient PR archaeology:
1. A separately executable targeted helper without checkpoint metadata would split the read authority. The helper was made internal-only so supported targeted reads stay behind the metadata-bearing facade.
2. Default Git rename folding could hide a protected source path when moved into an allowed destination. Scope validation now evaluates changed paths with rename folding disabled.
3. `service_role` inherited raw SELECT on the generation store from RT01-A. That privilege was revoked in the forward RT01-D migration so supported service consumers cannot bypass the published-only facade into staging/future rows.

A separate review suggestion to detect arbitrary copies of unchanged protected bytes into allowed prefixes was deliberately **rejected**. That would change RT01-D from changed-path scope validation into semantic content-provenance/content-taint tracking. This Mission does not own hostile-maintainer or arbitrary byte-origin authentication, and severity did not expand its scope.

### Affected surfaces
`.github/workflows/rt01-runtime.yml`, `scripts/runtime_published_mirror.py`, `supabase/README.md`, `supabase/migrations/20260908000006_rt01d_dm_read_engineering_release.sql`, `tests/rt01d/**`.

### Deliberate non-goals / deferred ownership
- No RT01 umbrella activation or live SQL cutover.
- No provisioning of the dedicated RHC Supabase project inside repository implementation.
- No semantic copy-origin/content-taint tracking or hostile-maintainer authentication protocol.
- No player-facing auth/redaction product work.
- No RAG/vector/search-index subsystem.
- No RT02 Campaign Clock, RT03 Run/canary migration, RT04 reconciliation, scheduler/autosave, inventory/custody, EV2 redesign, broad real-data migration, or Mission10 economy/Knowledge compatibility baggage.
- No resurrection of the removed standalone mutable-head `--recover` consumer.

### Compatibility / recovery consequences
- Ordinary RT01-C one-parent save/mirror behavior remains compatible; RT01-D extends the same publication/confirmation spine rather than adding a parallel persistence path.
- The DM/AI now has a bounded published-runtime consumer contract, but SQL/Supabase remains inert as live RHC authority until the separate RT01 umbrella activation checklist explicitly passes.
- The RHC activation gate must provision a dedicated RHC Supabase project, apply migrations from current `main`, prove A/B/C/D against that live project, verify real `runtime-published` exact-SHA behavior and privileges, preserve Unknown if campaign state is not initialized, and then make an explicit Orchestrator activation decision. Provisioning/tests alone do not silently switch authority.

### Verification evidence
- Exact cleared implementation HEAD: `4bba8263a3501b4e10e1fcff716c19e56ce7c5bd`.
- Local exact-head proof reported: focused read-facade 10 passed; RT01 A/B/C/D compatibility matrix 171 passed; full repository 405 passed; `git diff --check` passed.
- Exact-head GitHub PR CI: all 5 checks passed.
- Fresh exact-head Codex review on `4bba8263a3` reported no major issues.
- PR #39 merged to `main` as merge commit `8ea9e5f48c32b71ada941d2b5bf6622a8d98c2b6`.
- Post-merge `main` proof at `8ea9e5f48c32b71ada941d2b5bf6622a8d98c2b6` completed successfully for repository validation and RT01 runtime-foundation proof.

---

## 2026-09-09 — RT01-C runtime-published Git Handshake

### Why this milestone exists
RT01-A created the inert published-runtime floor and RT01-B created the guarded SQL Save Gateway, but SQL and Git cannot share one literal transaction. RT01-C closes that durability gap without pretending they can: SQL may publish generation N while external Git proof is still pending, and the system must preserve that intermediate state until the real remote artifact is proven and verifier-confirmed.

### Durable design
- **Two-stage completion, not fake atomicity.** SQL publication creates durable mirror-pending state. The save is not COMPLETE until the `runtime-published` Git artifact exists remotely, its actual SHA is read back, exact checkpoint bytes are verified, and the verifier confirms that SHA against the same DB-owned generation/token.
- **Retry repairs N, never creates N+1.** While mirror proof is pending, `begin_campaign_save()` cannot advance the generation. Git or confirmation failure therefore resumes the already-published generation instead of silently consuming another one.
- **Bootstrap base is data, not a moving lookup.** The exact selected main anchor for first publication is durably bound before confirmation, so retry remains coherent even if main advances later.
- **Remote reuse is continuity + shape + bytes.** A pre-existing remote proof is reusable only when it has the exact expected parent, changes only `runtime/published-checkpoint.json`, and that artifact is byte-for-byte the canonical pending checkpoint. Commit metadata is not runtime authority.
- **Read back the real remote.** The worker confirms the SHA that actually exists on the remote after fetch/read-back; caller-supplied or working-tree identity is never authoritative publication proof.
- **Verifier authority is narrow.** Normal `service_role` may read the pending candidate as needed but cannot bind the bootstrap base or self-confirm external Git proof. `rhc_mirror_verifier` remains the narrow confirmation boundary and unsafe pre-existing role/membership state fails closed.
- **Precision and fresh-worker behavior are explicit invariants.** JSONB numeric precision is preserved through canonical serialization, and a fresh/single-branch worker fetches the confirmed runtime parent before constructing the next child.

### Scope correction that matters later
An earlier RT01-C iteration exposed a standalone `--recover` path that treated the mutable `runtime-published` head as a Git-only consumer recovery surface. Codex correctly found that this invented consumer could accept an invalid advanced head, but the restored workflow law then classified the finding before repair:

1. **Scope:** standalone Git-only recovery was not required to complete the RT01-C handshake.
2. **Threat model:** accidental branch drift is relevant to the handshake, but only on surfaces RT01-C owns.
3. **Current surface:** consumer fallback/recovery semantics belong to RT01-D or a later explicit recovery Mission.

The correct repair was therefore to **remove/defer the invented consumer**, not harden it into a larger product. RT01-C keeps the durable Git artifact and internal exact remote read-back required for save completion. Future RT01-D work may consume pinned Git, but it must define that consumer contract explicitly rather than resurrecting `--recover` by archaeology.

### Threat-model boundary
RT01-C is a durability / continuity / parity mechanism, not hostile repository-writer authentication. A malicious repository administrator or collaborator deliberately racing the worker with a same-parent/same-bytes forged commit is OUT of this Mission. Predetermined unique publication SHA, cryptographic worker identity and commit-metadata authentication were deliberately rejected as scope expansion. Severity from review never promoted those threats into RT01-C authority.

### Affected surfaces
`.github/workflows/rt01-runtime.yml`, `scripts/runtime_published_mirror.py`, `supabase/README.md`, `supabase/migrations/20260908000004_rt01c_runtime_published_git_handshake.sql`, `supabase/migrations/20260908000005_rt01c_bind_runtime_mirror_base.sql`, `tests/rt01c/**`, `tests/test_runtime_published_mirror.py`.

### Deliberate non-goals / deferred ownership
- No RT01-D `dm_runtime_read` / compact read facade / `engineering_release`.
- No standalone Git-only recovery product.
- No live SQL runtime cutover; RT01-A/B/C remain inert until RT01-D plus umbrella activation pass.
- No Clock, Runs, inventory/custody, Knowledge/RAG, scheduler/autosave, EV2 redesign, campaign migration or Mission10 legacy compatibility machinery.
- No hostile-maintainer authentication protocol.

### Compatibility / recovery consequences
- `runtime-published` is now a durable checkpoint/provenance surface backed by exact remote read-back and verifier confirmation, but not yet the routine DM read interface.
- Consumer-level pinned Git fallback remains intentionally undefined until RT01-D or another explicit recovery Mission owns it.
- Mainline workflow-restoration files were incorporated into the long-lived RT01-C branch without rewriting RT01-C history, proving the resumed Mission could re-enter through current Dropgate/JOHNNY rules.

### Verification evidence
- Exact cleared implementation HEAD: `ab0276ed0c624f4d4f9774f9357999edaa98f054`.
- PR #32 merged to main as merge commit `6363b2df443e47c72e5522955a05d71a8714613f`.
- Fresh exact-head Codex review found no major in-scope issue after the standalone recovery surface was removed/deferred.
- Pre-merge PR CI was green for Flight Control, Entity V2 identity validation and RT01 runtime foundation.
- Post-merge `main` proof at `6363b2df...` completed successfully for Entity V2 identity validation and RT01 runtime foundation.

---

## 2026-09-09 — Dropgate + Continuity Restoration

> **Bootstrap seed exception (one-time):** this seed entry is created in the same PR that first introduces the ledgers — the deliberate one-time exception to the milestone-closeout publication rule described below. The ledgers do not exist on `main` yet, so this restoration seeds them pre-merge instead of at a separate post-merge closeout. Do not read this pre-merge seed as contradicting that rule: every future entry is published at closeout after exact-head merge and post-merge proof, never seeded ahead of merge. After this Mission merges, the bootstrap exception is spent and the normal closeout rule governs.

### Why now
RHC's Builder/JOHNNY lifecycle (from PR #34) is strong but historically **lossy**: a fresh Builder could understand today's Mission yet still miss *why* nearby mechanics were deliberately not built. During RT01-C that gap let adjacent surfaces get invented; Codex then audited those inventions as if they were Mission requirements, and repairing before scope-classifying hardened the invention and grew review surface. RHC needs durable continuity and stricter lane/surface boundaries so a stateless Builder can start safely without chat archaeology or Asana access. This Mission restores the repository-construction safeguards RHC only partially inherited from Mission10-Beta.

### Baseline this builds on (seeded, bounded)
- **PR #34** delivered the current workflow baseline: sufficient branch-bound JOHNNY Mission Packet, stateless cold-start Builder, vendor-neutral `AGENT_HANDOFF.md` router, and Flight Control CI over the control files. This restoration adapts and extends that baseline; it does not restart it.

### What changed and why
- **One universal Dropgate** (`AGENT_HANDOFF.md`): the partial router became explicit five-lane routing (BUILD / PLAY / SAVE / READ / UNKNOWN-CONFLICT). UNKNOWN/CONFLICT **fails closed** by asking, never defaulting to BUILD, because the primary threat model is confused/stale/scope-drifting workers and accidental mistakes — guessing a lane is the dangerous default.
- **Mandatory Continuity Gate** (`BUILDER.md`, new Stage 2): continuity was previously whatever JOHNNY happened to list. Optional continuity gets skipped under pressure (a known failure mode), so continuity is now a **separate mandatory input species** the Orchestrator selects and the Builder must consume before implementation.
- **JOHNNY template extensions** (`ORCHESTRATOR.md`): added Port/Reference Contract, Surface Budget, Deferred Ownership, and Continuity Reads so a Mission's allowed surfaces and deferred neighbors are explicit at cold start — directly countering the RT01-C invented-surface scar.
- **Review Scope Classification Law** (`ORCHESTRATOR.md`): every finding is classified (scope / threat-model / current-surface) before repair. **Severity is not scope** — a P1 against an undeclared or deferred surface is removed/deferred, not hardened. This is the direct RT01-C lesson made into law.
- **`PLAY.md`**: a thin PLAY cockpit so campaign play routes cleanly without loading BUILD machinery, keeping BUILD and PLAY lanes separated. It duplicates no campaign authority; it points at the existing owners (`docs/DM_CONTROL_ROOM.md`, `docs/RHC_WORKSYSTEM.md`, `PROJECT_PRIMER.md`, `README.md`).
- **Ledgers** (`CHANGELOG.md`, `ENGINE_CHANGELOG.md`): seeded with bounded history so future Builders no longer need the bootstrap exception. Past decisions become input; new durable decisions become future ledger history at milestone closeout.

### Ledger policy (deliberate design)
- These ledgers are **curated milestone / patch-series continuity, not a per-PR** execution diary. The normal publication unit is a coherent milestone/patch-series **closeout** — after exact-head merge and post-merge proof, a small docs-only closeout updates the ledgers when there is durable meaning worth preserving.
- An earlier local-only build of this Mission added a per-engineering-PR ledger gate (a `validate_change_ledger` validator plus an inline CI floor requiring both ledgers or a `LEDGER-EXEMPT:` token on every engineering-sensitive PR). That policy was **rejected before first push**: forcing both ledgers to change on every PR turns them into noisy duplicates of Git/PR/Codex history that eventually rot (a named scar). The validator and its CI floor were removed; only Dropgate/JOHNNY/continuity contract validation remains in Flight Control.

### Affected surfaces
`AGENT_HANDOFF.md`, `BUILDER.md`, `ORCHESTRATOR.md`, `PLAY.md` (new), `CHANGELOG.md` (new), `ENGINE_CHANGELOG.md` (new), `.github/workflows/flight-control.yml`, `tests/test_workflow_dropgate.py` (new).

### Deliberate non-goals (rejected on purpose)
- **No mandatory per-engineering-PR ledger gate.** No `validate_change_ledger` validator, no both-ledgers-per-PR CI requirement, no `LEDGER-EXEMPT:` exemption ceremony. Continuity *consumption* is mandatory when JOHNNY selects it; ledger *publication* happens at milestone closeout.
- **No routine human-confirm-every-BUILD loop.** The historical mandatory human interpretation confirmation before every BUILD is explicitly **not** restored. The current no-routine-human-confirm workflow is preserved.
- **No new gate-file bureaucracy**: no `HUMAN_README.md`, no completion-receipt subsystem, no new runtime commands, no campaign/runtime/SQL surface.
- **No RT01-A/B/C/D implementation changes**; RT01-C mirror behavior (incl. its P1 #13 recovery-path question) is **deferred back to RT01-C** after this workflow patch merges. RT01-D `engineering_release`, Campaign Clock (RT02), Run runtime read (RT03) remain deferred to their gates.
- **No hostile-maintainer / forged-authority security hardening**: out of this Mission's threat model; any such design is a separate future security Mission.
- **No Beta campaign-specific mechanics** (Test Lab, Language-of-the-Sun) ported; Beta artifacts were adapted, not blind-copied.
- **No whole-repository documentation rewrite** and **no campaign canon/state change**.

### Compatibility / recovery consequences
- All strings currently asserted by `flight-control.yml` in `AGENT_HANDOFF.md`, `BUILDER.md`, `ORCHESTRATOR.md`, `AGENTS.md`, `CLAUDE.md` are preserved; edits are additive, so existing Flight Control checks continue to pass.
- `BUILDER.md` stages were renumbered (Continuity Gate inserted as Stage 2; former Stages 2–6 became 3–7). Cross-references were updated; no stage was removed.
- Flight Control now validates the restored Dropgate/JOHNNY/continuity contracts and the bounded, milestone-scoped ledgers, and actively guards against re-introducing the rejected per-PR ledger gate. It does **not** require ledger edits on engineering PRs.
- Campaign/runtime files are untouched by this Mission.

### Verification evidence
- `pytest tests/test_workflow_dropgate.py -v` — static Dropgate / continuity / ledger / lane contract suite covering the repository-side Proof Matrix, including proofs that the per-PR ledger gate is absent and that milestone-closeout publication is documented. (The suite grows as contracts evolve; it is described by what it proves, not by a fixed test count.)
- Existing Flight Control control-text checks remain green because all previously grepped strings are preserved.
- Cold-start acceptance matrix reported to the Orchestrator with the BUILD report.
