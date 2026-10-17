# Miyorare Source Lab

Android owner/viewer console for the Miyorare Source Pack backend and Compatibility Farm.

## Purpose

Source Lab is intentionally a separate Android app. It does **not** replace repository/CI automation and does not make a phone a required part of normal Source Pack maintenance.

Repository, CI, and backend state remain authoritative. Viewer paths are read-only. GitHub identity, owner identity, backend authorization, and action-specific capability are separate gates, and mutations remain explicit and fail-closed.

The current development target is **Source Lab v1.2.15 — Backend Alignment**. Publishing an official stable APK remains a separate owner-triggered action.

## Current architecture

- live Compatibility Farm state is read from `compatibility-farm-foundation` and pinned to one exact Farm commit before related registry/status/worker files are parsed;
- Source Registry, Farm status, and pending-worker schemas are checked fail-closed before authority-critical state is presented;
- operational health is kept separate from compatibility evidence and release eligibility;
- active commit and last-known-good state are shown independently from newer/live candidate state;
- candidate-lock review preserves candidate identity, expected baseline/LKG context, evidence binding, publish eligibility, and scoped source authority;
- P2 BATCAVE runtime evidence is read from authoritative GitHub Actions evidence and does not depend on Source Lab or a physical phone to produce proof;
- P2 distinguishes WebView availability/request success from proven protected-path execution and remains fail-closed when `__guard_trust` / bound execution proof is incomplete;
- P3 Miyorare Audio Catalog is presented as separate catalog/release authority and is never folded into Compatibility Farm source counts;
- P3 preserves exact Miyorare catalog revision, exact Hiraukan runtime authority, six builtin audio-runtime bindings, release eligibility, and owner-deferred device-validation state;
- Reports and Diagnostics expose authority/provenance details without turning the dashboard into a second backend implementation.

## Owner authorization and control

GitHub login proves identity and repository access, but does not by itself unlock sensitive actions.

The Owner path remains layered:

1. Source Lab verifies the expected GitHub identity/repository installation context.
2. A short-lived backend authorization proof is obtained and cryptographically validated.
3. Backend authorization grants no write capability implicitly.
4. Each control action requires its own capability and current authoritative state.
5. Mutation flows refresh/revalidate authority before dispatch rather than trusting stale UI state.

Manual Farm recovery is deliberately narrow. Source Lab requires an exact provider and exact expected candidate, reloads the authoritative Farm snapshot immediately before dispatch, and rejects candidate drift. Keiyoushi recovery additionally requires the exact runtime-evidence run when the backend contract requires it.

Approval, promotion, signing, publishing, and recovery remain governed by their backend contracts. `PASS` is never treated as `PROMOTED`.

## Safety invariants

1. Repository/CI/backend state is authoritative.
2. Viewer mode remains read-only.
3. Owner identity, backend authorization, and action capability are separate gates.
4. Backend authorization never implies a global write switch.
5. `PASS` is not `PROMOTED`.
6. Candidate SHA, candidate-set identity, expected LKG/baseline, evidence binding, and source scope must remain exact where the backend requires them.
7. Stale or mismatched authority fails closed.
8. Candidate failure does not imply the active source is broken.
9. WebView availability or request success alone does not prove a protected runtime path executed.
10. P3 Audio Catalog data is not Compatibility Farm source membership.
11. No GitHub client secret, private key, signing key, keystore secret, or equivalent release secret is embedded in the APK.
12. Stable Source Lab publication is never a side effect of an ordinary branch push.

## Validation and release path

Internal Source Lab CI runs unit tests, debug lint, and debug assembly, verifies the debug APK exists, and intentionally does not publish it.

The official `Source Lab Stable Release` workflow is `workflow_dispatch` only and requires an explicit release version. The trusted Source Lab branch is checked out at an exact source commit; CI parity checks run again; release lint and release assembly run with repository-held signing configuration; the APK signature is verified; and the APK plus SHA-256 digest are published only through that explicit release flow.

Existing official tags are treated as immutable source identities: the release workflow refuses to reuse a version tag that already points to different source code.

## v1.2.15 alignment scope

The v1.2.15 alignment work covers:

- explicit/manual-only stable release safety and current manual Farm recovery contract;
- P1 operational-authority, candidate-lock, scoped-approval, and release-eligibility presentation;
- P2 BATCAVE authoritative runtime-evidence inspection;
- P3 Miyorare Audio Catalog authority presentation;
- focused backend/app compatibility guards for authority-critical contract drift;
- final release-readiness audit and exact-head validation before any owner-authorized stable publication.

For phase continuity and exact verification checkpoints, see `SOURCE_LAB_V1_2_15_PLAN.md`.