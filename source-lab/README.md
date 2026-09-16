# Miyorare Source Lab

Android control panel for the Miyorare Compatibility Farm.

## Purpose

Source Lab is intentionally a separate Android app. It does **not** replace repository/CI automation and must never make the phone a required part of upstream maintenance.

Repository inspection remains read-only by default. GitHub App identity, owner identity, repository installation, and backend authorization are separate gates, and every write capability remains explicit and fail-closed.

## Implemented foundation

- seed-12 dashboard (12 canonical sources / 21 provider memberships);
- live read-only sync from `compatibility-farm-foundation` for:
  - `compatibility/source-registry.json`;
  - `upstream/status.json`;
- provider runtime-health display kept separate from candidate/test evidence;
- ID + EN source registry browser with embedded verified fallback data;
- authoritative Compatibility Farm checkpoint viewer;
- repair evidence visibility;
- exact checkpoint provenance (run, seed SHA, approval-foundation SHA, artifact id/digest);
- read-only parsing of recent `compatibility-farm-accelerated.yml` workflow runs;
- explicit safety boundary for `WAITING_FOR_APPROVAL`;
- owner access policy bound to immutable GitHub user id `149634319`;
- owner login bound to GitHub App id `4959004` and installation id `162045953` for `Noirero/Miyorare-Source-Packs`;
- Device Flow remains the interactive identity layer without embedding a client secret/private key;
- short-lived backend authorization client that verifies a GitHub Actions OIDC proof against GitHub's published JWKS;
- backend proof bound to a fresh 256-bit app challenge, exact workflow/ref/run/repository/actor claims, and JWT expiry;
- backend authorization grants **no write capability implicitly**;
- Android CI that produces and uploads a debug APK artifact.

## Backend authorization P0

GitHub login proves the owner identity and repository permission through the expected Source Lab GitHub App installation. It does not by itself unlock sensitive controls.

The backend authorization flow is:

1. The access gate first requires the exact owner GitHub user id, GitHub App id `4959004`, installation id `162045953`, repository, and admin repository permission.
2. Source Lab generates 32 cryptographically random bytes and sends the lowercase-hex challenge to the dedicated default-branch authorization workflow.
3. The workflow fails closed unless the dispatcher is GitHub user id `149634319`, the repository is exactly `Noirero/Miyorare-Source-Packs`, the event is `workflow_dispatch`, and the ref is `refs/heads/main`.
4. GitHub Actions mints a short-lived OIDC JWT whose audience is `miyorare-source-lab:<challenge>`.
5. Source Lab downloads the short-lived proof artifact and verifies the JWT signature with GitHub's OIDC JWKS.
6. Source Lab validates the exact issuer, audience, subject, actor id, repository id, owner id, workflow, workflow ref, event, ref, run id, issued-at/not-before/expiry claims.
7. Only then does the owner session become `BACKEND_AUTHORIZED` until the signed proof expires.

The backend workflow must exist on the repository **default branch** for `workflow_dispatch` to work. It is staged separately from the Android branch for that reason.

P0 backend authorization is session authorization only. `RUN_FARM`, `APPROVE`, `PROMOTE`, `SIGN`, and `PUBLISH` remain individually denied until a dedicated capability path explicitly grants them.

## Safety invariants

1. PASS is not PROMOTED.
2. `lastKnownGood` / `upstreamBase` must not move before exact approval authorization.
3. Candidate SHA, candidateSetId, expected LKG and evidence digest must be revalidated before promotion.
4. Stale/mismatched approval fails closed.
5. Candidate failure does not imply the active source is broken.
6. Runtime HEALTHY is not derived from fixture/shape evidence alone.
7. Regression budget remains zero.
8. Public/live repository inspection remains read-only.
9. No GitHub write token, client secret, or private signing key is embedded in the APK.
10. Backend authorization is short-lived and cryptographically verified.
11. Backend authorization never implies a write capability.
12. Sign/release/publish remain governed by the official release flow.

## Current authoritative Compatibility Farm checkpoint

- authoritative run: `35002747386`
- seed commit: `4dc733270e4022c0eff9fe91479d3cf5e78eadbe`
- approval-proof foundation: `7dfce1617d24ebf1a7e21ed8e41412d79791a731`
- artifact id: `10410915845`
- canonical coverage: `12/12`
- provider membership coverage: `21/21`
- failures: `0`
- generic auto-repair: `2/2`
- gate: `WAITING_FOR_APPROVAL`
- publish eligible: `false`

## Source Lab build checkpoint

The first artifact-producing Source Lab CI completed successfully:

- run: `35007505172`
- head SHA: `20020cbbfb8e60aa2c958b08aba330592bb7d28e`
- artifact: `miyorare-source-lab-debug`
- artifact id: `10412576077`
- artifact digest: `sha256:80f2b8fa2e787871e044d4c28a435677bbc2aebf2cb259442c30be0815610ef3`

The CI installs Android 35 requirements, builds `:app:assembleDebug`, and fails if the APK artifact is missing.

## Next engineering steps

P0 — read/inspect path:

- surface recent Compatibility Farm workflow history in the UI;
- parse authoritative run/artifact evidence instead of treating workflow status alone as compatibility evidence;
- add detailed provider/source current-vs-candidate inspection;
- keep verified embedded fallback data for temporary API/network failures.

P0 — capability control path:

- connect `Run Full Farm` to its own backend-authorized, least-privilege dispatch capability;
- keep `Approve exact candidate` disabled until exact candidate SHA + candidateSetId + expected LKG + evidence digest are wired end-to-end;
- preserve action-specific authorization rather than converting backend session authorization into a global write switch.

After approve-only upstream P0 lands:

- display exact candidate SHA + candidateSetId + expected LKG + evidence digest;
- enable exact-candidate approval;
- show authorization result and stale-approval reasons;
- only then expose promotion state.

Release/sign/publish remain governed by the official Miyorare release flow and stay outside Source Lab until their separate authorization paths are complete.
