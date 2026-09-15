# Miyorare Source Lab

Android control panel for the Miyorare Compatibility Farm.

## Purpose

Source Lab is intentionally a separate Android app. It does **not** replace repository/CI automation and must never make the phone a required part of upstream maintenance.

The app is currently a read-only control-plane client. Write actions remain locked until the approve-only upstream authorization path is complete.

## Access model

Source Lab uses a two-level access model:

- **PUBLIC_VIEWER** — available to everyone. Public users may inspect sources, providers, Compatibility Farm results, reports, repair evidence, run history, current/candidate state, and other public repository evidence.
- **OWNER_AUTHENTICATED** — reserved for the authorized repository owner. Sensitive controls include `RUN_FARM`, `APPROVE`, `PROMOTE`, `SIGN`, and `PUBLISH`.

The owner identity is bound to the stable GitHub numeric user ID `149634319` for `Noirero`, not to the username alone. Owner controls are fail-closed and require all of the following at the same time:

1. authenticated GitHub session;
2. exact numeric owner user ID;
3. exact repository `Noirero/Miyorare-Source-Packs`;
4. repository permission `admin`;
5. positive backend authorization.

App-side UI checks are not authoritative. The backend must independently verify the same identity and authorization before accepting a sensitive request. A modified APK must never be sufficient to bypass owner-only controls. No write token/PAT may be embedded in the APK.

The machine-readable policy is stored in `source-lab/security/access-policy.json` and the app-side default-deny gate is implemented in `AccessControl.kt`.

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
- public-viewer / owner-only access policy with default-deny unit tests;
- Android CI that runs tests, lint, builds, and uploads a debug APK artifact.

## Safety invariants

1. PASS is not PROMOTED.
2. `lastKnownGood` / `upstreamBase` must not move before exact approval authorization.
3. Candidate SHA, candidateSetId, expected LKG and evidence must be revalidated before promotion.
4. Stale/mismatched approval fails closed.
5. Candidate failure does not imply the active source is broken.
6. Runtime HEALTHY is not derived from fixture/shape evidence alone.
7. Regression budget remains zero.
8. Live repository access from the Android app is read-only for public users.
9. Sensitive controls default to DENY.
10. Owner identity is validated by exact GitHub numeric user ID, repository and backend authorization.
11. No GitHub write token is embedded in the APK.
12. This foundation does not sign, release or publish.

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

The localized Source Lab CI completed successfully before the owner-access foundation was added:

- run: `35013086790`
- head SHA: `877d31fe9f62d83dcc492f594d27abee5c5f5533`
- artifact: `miyorare-source-lab-debug`
- artifact id: `10414288710`
- artifact digest: `sha256:12c6f3bcb4f462244002d13aadf574aef5eff6d72e4be915eab6131b83197426`

CI runs unit tests, Android lint, `:app:assembleDebug`, and fails if the APK artifact is missing.

## Next engineering steps

P0 — read/inspect path:

- surface recent Compatibility Farm workflow history in the UI;
- parse authoritative run/artifact evidence instead of treating workflow status alone as compatibility evidence;
- add detailed provider/source current-vs-candidate inspection;
- keep verified embedded fallback data for temporary API/network failures.

P0 — secure control path:

- add secure GitHub OAuth/device-flow authentication without embedding a write token in the APK;
- have the backend independently verify exact numeric owner ID and repository permission;
- connect `Run Full Farm` to a dedicated, least-privilege workflow-dispatch path;
- keep `Approve exact candidate` disabled until upstream-sync approval authorization is fully wired.

After approve-only upstream P0 lands:

- display exact candidate SHA + candidateSetId + expected LKG + evidence digest;
- enable exact-candidate approval for the authorized owner only;
- show authorization result and stale-approval reasons;
- only then expose promotion state.

Release/sign/publish remain governed by the official Miyorare release flow and are outside the Source Lab foundation until explicitly authorized.
