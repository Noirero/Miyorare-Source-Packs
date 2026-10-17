# Miyorare Source Lab v1.2.15 — Continuity Plan

Status: **CURRENT / CONTINUITY AUTHORITY FOR SOURCE LAB v1.2.15**

This document exists to prevent long-running Source Lab work from drifting when a phase discovers bugs, dependencies, side work, interrupted sessions, model changes, or repository state changes.

It is intentionally concise. It is **not** a large progress tracker and must not be expanded into a continuously rewritten task checklist.

## 1. Authority and precedence

For Source Lab v1.2.15 work, use this precedence:

1. Latest explicit owner instruction.
2. Applicable Miyorare Source Pack governing documents and engineering protocol.
3. This file as the continuity authority for the v1.2.15 parent goal, phase order, scope locks, return targets, and resume checkpoint.
4. Repository state and exact-head evidence for implementation facts.

Repository state remains source of truth for code, commits, PRs, workflow runs, releases, and live contracts. This plan does not override newer repository evidence.

If a newer explicit owner decision changes this plan, update this file deliberately. Do not silently reinterpret the parent goal or phase acceptance criteria during implementation.

## 2. Parent goal — LOCKED

**Produce Miyorare Source Lab v1.2.15 as a targeted Backend Alignment Release for the Source Pack backend after P1, P2, and P3, without a broad UI redesign and without moving repository/CI automation onto the phone.**

v1.2.15 must keep Source Lab as an Android owner/viewer console over authoritative repository and CI state. The phone must not become a required component of normal Source Pack maintenance.

Core invariants that must survive every phase:

- repository/CI/backend state remains authoritative;
- Viewer paths remain read-only;
- owner identity and backend capability remain separate gates;
- mutation remains capability-specific and fail-closed;
- no GitHub client secret, private key, signing key, keystore secret, or equivalent release secret is embedded in the APK;
- PASS is not PROMOTED;
- operational health, compatibility evidence, and release eligibility are not collapsed into one meaning;
- last-known-good and exact candidate identity are not weakened for UI convenience;
- P2 evidence is produced by authoritative CI/runtime lanes, not made dependent on the phone;
- P3 Audio Catalog remains a catalog/release contract and is not folded into Compatibility Farm source counts;
- official Source Lab release publication is an explicit owner-triggered action, never a side effect of an ordinary branch push.

## 3. Locked phase sequence

The normal parent sequence is:

**SL13-A → SL13-B → SL13-C → SL13-D → SL13-E → SL13-F**

The `SL13-*` identifiers are intentionally retained as stable continuity IDs from the original plan. The owner retargeted the release identity from v1.2.13 to v1.2.15 after repository evidence proved v1.2.13 already existed and a historical push-trigger hazard produced v1.2.14. Renaming phase IDs would make continuity worse, so their IDs stay stable while the parent release target is v1.2.15.

A phase may temporarily spawn dependency/child work. Closing a child does **not** advance the parent sequence. After the child is verified, work returns to the parent phase that spawned it.

### SL13-A — Baseline and known fixes

**Goal**

Establish the exact v1.2.15 application baseline from the current Source Lab branch, preserve the already-merged publish-recovery correction, close baseline contract drift discovered by audit, and prove the branch is safe to use for later alignment work.

**Must include**

- refresh exact `source-lab-owner-access-temp` state before implementation;
- use the post-PR-#85 Source Lab state as the application baseline unless newer repository evidence requires adaptation;
- verify the `Resume Publish` / publish-recovery behavior is present and not regressed;
- make official Source Lab Stable Release explicit/manual-only so ordinary `source-lab/**` pushes cannot publish a new official APK;
- align Manual Run Farm with the current backend contract: exact provider, exact expected candidate, and exact Keiyoushi runtime-evidence run when required;
- reload authoritative Farm state and reject stale manual-recovery candidate identity immediately before dispatch;
- inspect current backend `main` contracts needed by later phases;
- identify exact files/contracts to be touched before later phase code changes.

**Must not include**

- broad UI redesign;
- P1 authority presentation implementation beyond what is required to repair the Manual Run Farm contract;
- P2 runtime-evidence viewer implementation;
- P3 Audio Catalog UI implementation;
- unrelated Source Lab cleanup merely because it is nearby.

**Exit condition**

The exact application baseline, exact backend authority, publish-recovery fix, explicit-only stable-release gate, Manual Run Farm contract, and intended v1.2.15 change surface are verified with no unresolved baseline ambiguity; exact-head Source Lab CI is green and ordinary branch pushes are proven not to trigger Stable Release.

### SL13-B — P1 backend authority alignment

**Goal**

Make Source Lab represent current P1 operational authority correctly and make candidate-lock/scoped-approval state understandable without weakening backend authority.

**Must include**

- clearly distinguish operational health, compatibility evidence, and release eligibility;
- surface active commit and last-known-good where useful;
- surface release eligibility and reason where useful;
- represent locked candidate separately from live/newer upstream candidate when both exist;
- represent expected LKG / baseline identity needed to understand candidate-lock safety;
- represent source scope for scoped approval/promotion where the backend exposes it;
- preserve evidence binding / exact-candidate review semantics;
- expose stale/drift/lock reasons rather than replacing them with generic success/failure wording;
- add or update parser/contract tests needed for the current P1 schemas.

**Must not include**

- P2 Android/WebView runtime-evidence UI;
- P3 Audio Catalog UI;
- changing backend approval/promotion semantics merely to simplify the Android UI;
- merging operational health and compatibility proof into one status badge.

**Exit condition**

Source Lab reads and presents current P1 authority without semantic misrepresentation; candidate-lock and scoped-approval states are tested; exact-head validation is green; full self-audit finds no authority regression.

### SL13-C — P2 runtime evidence viewer

**Goal**

Allow Source Lab to explain authoritative runtime evidence produced by P2, beginning with BATCAVE, without making the phone an evidence-producing requirement.

**Must include**

- read authoritative P2 runtime-evidence state from repository/CI-backed data;
- show extension/runtime load result when available;
- show live request/result evidence when available;
- show Android/System WebView availability/evidence when available;
- distinguish WebView availability from proven DLE Guard execution;
- show challenge/trust evidence such as the `/_c` / `__guard_trust` path only when actually observed;
- preserve fail-closed states such as `androidWebViewExecutionProven=false` / infrastructure blocked when proof is incomplete;
- provide a useful Source Detail or diagnostics presentation without overcrowding the main Farm dashboard.

**Must not include**

- synthesizing a BATCAVE challenge;
- interpreting WebView installation/availability as proof that the protected path executed;
- requiring a physical phone or Source Lab APK to generate P2 release evidence;
- automatically reclassifying BATCAVE from HELD without authoritative evidence.

**Exit condition**

P2 evidence can be inspected accurately in Source Lab, incomplete evidence remains visibly incomplete/fail-closed, and backend semantics are preserved by tests and exact-head validation.

### SL13-D — P3 release catalog viewer

**Goal**

Expose the P3 Miyorare Audio Catalog authority as release/catalog information without contaminating Compatibility Farm source counts or lifecycle semantics.

**Must include**

- display the final Miyorare Audio Catalog authority when available;
- display exact Miyorare catalog commit and exact Hiraukan runtime authority;
- display the six expected builtin runtime identities/count in a useful form;
- display release eligibility and reason;
- display owner-deferred device validation accurately as deferred, not as passed device evidence;
- keep catalog/release information in Reports, release assets, diagnostics, or another clearly separate catalog surface.

**Must not include**

- adding the six audio runtimes to `In Farm`, Ready/Held/Retry/Approved source metrics;
- treating `DEFERRED_BY_OWNER` as device validation success;
- introducing downloadable unsigned executable audio-extension delivery;
- coupling P3 Audio Catalog back to the manga builder baseline.

**Exit condition**

Source Lab accurately displays the P3 catalog/release authority, the Compatibility Farm model remains separate, and exact-head tests/self-audit confirm no contract contamination.

### SL13-E — Backend/App contract compatibility guard

**Goal**

Reduce future backend/app semantic drift by adding focused compatibility validation between Source Lab parsers/presentation contracts and current backend schemas/authorities.

**Must include**

- identify the Source Lab-consumed backend contracts that can drift;
- add focused compatibility fixtures/tests for those contracts;
- fail closed on unsupported authority-critical schema changes instead of silently presenting misleading state;
- cover at least the P1 authority/candidate-lock contract plus the P2/P3 data consumed by v1.2.15;
- keep validation targeted and maintainable rather than creating a duplicate backend implementation inside Android tests.

**Must not include**

- a giant duplicated model of the whole Source Pack repository;
- broad unrelated CI refactors;
- making Source Lab CI responsible for backend mutation.

**Exit condition**

A relevant backend contract drift that would make v1.2.15 semantically unsafe is detectable by focused CI/tests before release.

### SL13-F — Final audit and v1.2.15 release preparation

**Goal**

Prove the completed v1.2.15 change set is coherent, regression-safe, and ready for owner release authorization.

**Must include**

- refresh exact repository state;
- full diff/self-audit across all v1.2.15 changes;
- regression review of Viewer mode, Owner authorization, capability gating, Farm dashboard, Sources, Approval Review, Reports, Diagnostics, Settings, manual recovery, and publish recovery;
- verify P1/P2/P3 presentation against exact current backend authorities;
- run exact-head Source Lab tests/lint/build/relevant CI;
- verify version/changelog/docs as appropriate for v1.2.15;
- verify produced APK identity/signing/release path using the explicit official Source Lab release process;
- stop at READY FOR OWNER RELEASE/MERGE AUTHORIZATION where an explicit owner authorization is required.

**Must not include**

- silently publishing/releasing/merging a privileged target without the required explicit owner authorization;
- introducing unrelated feature work during final audit;
- weakening a failing gate merely to finish the release.

**Exit condition**

All intended v1.2.15 scope is closed, exact-head CI is green, post-CI self-audit is clean, no unresolved in-scope blocker remains, and the release is ready for the owner's explicit final action where required.

## 4. Scope-lock rule

Before implementing a phase, its Goal / Must include / Must not include / Exit condition above is the locked contract.

A newly discovered idea or problem does not automatically change that contract.

If a finding would materially change the locked phase contract:

1. stop before broadening the implementation;
2. classify the finding;
3. explain why the phase contract would need to change;
4. obtain an explicit owner decision if the parent scope must change;
5. update this plan deliberately before continuing under the new scope.

Do not silently finish a phase with a materially different meaning from the phase originally approved.

## 5. Child-problem return rule — mandatory

**FIX CHILD PROBLEMS, THEN RETURN TO THE PARENT GOAL.**

When the active phase discovers a blocker/dependency:

1. record the parent phase;
2. classify the blocker as `DEPENDENCY / CHILD`;
3. solve the smallest safe child scope;
4. validate the child at exact repository state;
5. mark the child closed;
6. return to the recorded parent phase and its original exit condition;
7. do not advance to another parent phase until that exit condition is satisfied.

Example:

`SL13-B → CHILD-B1 parser bug → CHILD-B1.1 concurrency bug → close B1.1 → close B1 → RETURN SL13-B → finish SL13-B → SL13-C`

A child may have children. Every nested child returns to its immediate parent first. Side work must never become the new roadmap merely because it was the most recent task discussed.

## 6. Finding classification

Every material finding discovered during v1.2.15 work must be classified as one of:

- **IN-SCOPE** — directly part of the active phase contract.
- **DEPENDENCY / CHILD** — must be solved for the active phase to satisfy its exit condition.
- **FOLLOW-UP** — worthwhile, but not required to close the active phase or v1.2.15 parent goal.
- **UNRELATED** — outside this work; do not modify it as part of v1.2.15.

`FOLLOW-UP` and `UNRELATED` findings must not be pulled into the active implementation without an explicit owner scope change.

## 7. Next-work rule

The next engineering task is **not** determined merely by the last chat message, most recent bug, newest idea, or most recently edited file.

The next task is determined by:

1. latest explicit owner instruction;
2. the active child return target, if a child is open;
3. otherwise the active phase exit condition;
4. otherwise the next phase in the locked SL13 sequence.

If chat history, model memory, a handover note, or an implementation suggestion conflicts with the current repository evidence or this continuity sequence, refresh repository state and reconcile before writing.

## 8. Resume / recovery protocol

After interruption, model change, usage limit, or a later conversation:

1. read this file first;
2. read the `CURRENT CHECKPOINT` below;
3. refresh actual branch/PR/backend state;
4. treat repository state as truth if it moved after the checkpoint;
5. recover the active phase/child from the checkpoint;
6. continue from that point without restarting a broad audit unless repository movement invalidates prior evidence;
7. after a child closes, return to its recorded parent target.

Do not infer continuation from chat recency alone.

## 9. Checkpoint format

Keep the checkpoint short. Do not turn it into a large progress checklist.

Use this shape:

```text
CURRENT CHECKPOINT
Parent goal: Source Lab v1.2.15 Backend Alignment Release
Phase: SL13-X
Phase state: NOT_STARTED | ACTIVE | BLOCKED_BY_CHILD | READY_FOR_EXIT_AUDIT | CLOSED
Active child: NONE | CHILD-...
Child state: NONE | ACTIVE | CLOSED
Return target: <the exact parent goal/exit condition to resume>
Last verified repository state: <branch/ref + SHA or REFRESH_REQUIRED>
Last verified backend authority: <ref + SHA or REFRESH_REQUIRED>
Last verified evidence: <short factual checkpoint>
Next parent phase after closure: SL13-Y | NONE
Notes: <only continuity-critical notes>
```

The checkpoint records continuity, not every completed subtask.

## 10. Historical baseline and retarget decision

Verified history relevant to this plan:

- Source Lab v1.2.12 was released from `f661f0bfc312a6e1990f438066e35f0a61cbf6bf`.
- PR #85 publish-recovery UI was merged afterward, producing application baseline `7cca36bbfc6c1a5bdaca31c49bdea3ee36bc0253`.
- That exact post-PR-#85 state was already released as official Source Lab v1.2.13 before this Backend Alignment work began.
- The original continuity-plan commit `d2e6bdede8e387f200ea0b96cf552819c3546415` touched `source-lab/**`; the historical Stable Release workflow treated every such push as a release trigger and automatically published official immutable v1.2.14. This was an unintended workflow side effect discovered during SL13-A audit, not a completed Backend Alignment release.
- The owner explicitly approved retargeting this Backend Alignment parent release to **v1.2.15**.
- CHILD-A2 changed Stable Release at `c9c19fc7df752e651a275ad9319cdb566120f751` so release is `workflow_dispatch` only and requires an explicit version. Subsequent branch writes did not trigger Stable Release.
- CHILD-A1 aligned Manual Run Farm at `c80e137d0f4f477e677d3454520a30d590db4c33`: explicit provider + expected candidate, exact Keiyoushi runtime-evidence run when required, fresh-snapshot stale-candidate rejection, recovery target UI, and focused contract tests.
- CHILD-A1 exact-head Source Lab CI run `39048352150` completed successfully, including unit tests, debug lint, and debug assembly.
- Backend Source Pack `main` remained `e20015393591d22398aa623b227e17afe26fc19d` at the SL13-A exit audit.
- Compatibility Farm authority remained `955f2ede6ddb2ae4f61f46074bacb937f68fc14f` at the SL13-A exit audit.
- CHILD-B1 pinned Source Lab Farm authority reads to one exact Compatibility Farm commit before loading registry, status, and pending-worker state; exact-head Source Lab CI run `39049949271` completed successfully at `4cded9bd04d266a78b2f4b58bd5cbcdc96188a77`.
- SL13-C added a read-only BATCAVE P2 evidence viewer over authoritative GitHub Actions job logs. It validates exact run/candidate/Miyorare/bound-proof provenance, exposes extension install/load, live request/result, System WebView, `__guard_trust`, protected-path proof, and infrastructure-blocked state, and fails closed when evidence is unavailable or inconsistent. Exact-head Source Lab CI run `39061852772` succeeded at `4d1b0d9d8f35a8c75bc25a45673fd6d28fc25d33`.

These SHAs are historical checkpoint evidence, not permanent assumptions. Refresh exact repository/backend state before every write and before every phase exit audit.

## 11. CURRENT CHECKPOINT

```text
CURRENT CHECKPOINT
Parent goal: Source Lab v1.2.15 Backend Alignment Release
Phase: SL13-C
Phase state: CLOSED
Active child: NONE
Child state: CLOSED
Return target: SL13-C exit condition is satisfied. The next parent task is SL13-D targeted pre-change audit; refresh the current P3 Audio Catalog authority and Source Lab change surface before implementation.
Last verified repository state: source-lab-owner-access-temp @ 4d1b0d9d8f35a8c75bc25a45673fd6d28fc25d33 before this closure-record commit; refresh exact head before the next write
Last verified backend authority: main @ e20015393591d22398aa623b227e17afe26fc19d; compatibility-farm-foundation @ 563c043c03fd1aad566a0e71c00a1de4ae1b1983
Last verified evidence: SL13-C reads authoritative BATCAVE P2 evidence from GitHub Actions without Owner authentication, validates exact provenance fail-closed, and presents runtime PASS separately from DLE Guard protected-path proof. Current evidence remains extension install/load success, live request success with 10 results, System WebView available, `__guard_trust` not observed, androidWebViewExecutionProven=false, infrastructureBlocked=true. Exact-head Source Lab CI run 39061852772 succeeded at 4d1b0d9d8f35a8c75bc25a45673fd6d28fc25d33; cumulative SL13-C diff touched only Source Lab app/test files and did not mutate backend/Farm/LKG/approval/promotion state.
Next parent phase after closure: SL13-D
Notes: Viewer path remains read-only. If CI logs expire or the P2 contract drifts, Source Lab shows evidence unavailable and infers no protected-path success. Stable Release remains explicit workflow_dispatch-only. Stop here until SL13-D is explicitly started.
```
