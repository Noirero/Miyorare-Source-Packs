# Miyorare Source Lab

Android control panel for the Miyorare Compatibility Farm.

## Purpose

Source Lab is intentionally a separate Android app. It does **not** replace repository/CI automation and must never make the phone a required part of upstream maintenance.

The app is currently a read-only control-plane client. Write actions remain locked until the approve-only upstream authorization path is complete.

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
- remote Farm and Approve controls visibly present but intentionally locked;
- Android CI that produces and uploads a debug APK artifact.

## Safety invariants

1. PASS is not PROMOTED.
2. `lastKnownGood` / `upstreamBase` must not move before exact approval authorization.
3. Candidate SHA, candidateSetId, expected LKG and evidence must be revalidated before promotion.
4. Stale/mismatched approval fails closed.
5. Candidate failure does not imply the active source is broken.
6. Runtime HEALTHY is not derived from fixture/shape evidence alone.
7. Regression budget remains zero.
8. Live repository access from the Android app is read-only.
9. No GitHub write token is embedded in the APK.
10. This foundation does not sign, release or publish.

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

- surface the recent Compatibility Farm workflow history in the UI;
- parse authoritative run/artifact evidence instead of treating workflow status alone as compatibility evidence;
- add detailed provider/source current-vs-candidate inspection;
- keep verified embedded fallback data for temporary API/network failures.

P0 — secure control path:

- add secure GitHub/control authentication without embedding a write token in the APK;
- connect `Run Full Farm` to a dedicated, least-privilege workflow-dispatch path;
- keep `Approve exact candidate` disabled until upstream-sync approval authorization is fully wired.

After approve-only upstream P0 lands:

- display exact candidate SHA + candidateSetId + expected LKG + evidence digest;
- enable exact-candidate approval;
- show authorization result and stale-approval reasons;
- only then expose promotion state.

Release/sign/publish remain governed by the official Miyorare release flow and are outside the Source Lab foundation until explicitly authorized.
