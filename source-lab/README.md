# Miyorare Source Lab

Android control panel for the Miyorare Compatibility Farm.

## Purpose

Source Lab is intentionally a separate Android app shell. It does **not** replace the repository/CI automation and must never make the phone a required part of upstream maintenance.

Current foundation capabilities:

- seed-12 dashboard (12 canonical sources / 21 provider memberships);
- provider runtime-health display kept separate from candidate evidence;
- source registry browser for ID + EN;
- authoritative Compatibility Farm checkpoint viewer;
- repair evidence visibility;
- exact provenance view (run, seed SHA, approval-foundation SHA, artifact id/digest);
- explicit safety boundary for WAITING_FOR_APPROVAL;
- placeholders for remote Farm trigger and exact-candidate approval.

## Safety invariants

1. PASS is not PROMOTED.
2. `lastKnownGood` / `upstreamBase` must not move before exact approval authorization.
3. Candidate SHA, candidateSetId, expected LKG and evidence must be revalidated before promotion.
4. Stale/mismatched approval fails closed.
5. Candidate failure does not imply the active source is broken.
6. Runtime HEALTHY is not derived from fixture/shape evidence alone.
7. Regression budget remains zero.
8. This foundation does not sign, release or publish.

## Current data checkpoint

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

## Next engineering steps

P0:

- replace embedded checkpoint data with read-only repository/API sync;
- wire workflow run listing and authoritative artifact parsing;
- add secure GitHub authentication without embedding a token in the APK;
- connect Run Farm control to a dedicated workflow-dispatch endpoint;
- keep Approve disabled until upstream-sync approval authorization is fully wired.

After approve-only P0 lands:

- display exact candidate SHA + candidateSetId + expected LKG + evidence digest;
- enable exact-candidate approval;
- show authorization result and stale-approval reasons;
- only then expose promotion status.

Release/sign/publish remain governed by the official Miyorare release flow and are outside this foundation app commit.
