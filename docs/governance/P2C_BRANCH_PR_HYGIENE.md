# P2-C — Branch / PR Hygiene

Baseline: post-P2-B `main` at `029491164118d8ef59f2559843577b7f22f23544`.

P2-C defines fail-closed branch and pull-request hygiene. It deliberately does not delete branches. Cleanup eligibility is evidence for an owner decision, not destructive authorization.

## Branch classes

- **STATE_BEARING** — `main` and `compatibility-farm-foundation`. Never automatically deleted or force-updated.
- **ACTIVE_WORK** — normal `feat/`, `fix/`, `hardening/`, `audit/`, `phase*`, and `perf/` work branches. Eligible only after merge/post-merge verification or explicitly reviewed abandonment.
- **EPHEMERAL** — smoke-test, cleanup, compatibility snapshot, and release-eligibility branches. Eligible only after their purpose is proven complete and references are clear.
- **UNKNOWN** — held. Naming is never enough evidence to delete an ambiguous branch.

The current repository has a large historical branch population spanning Farm staging, Source Lab recovery, release eligibility, fixes, experiments, and completed governance work. P2-C therefore does not mass-delete historical branches. Each candidate must be classified against PR state and live references first.

## Reference safety

A branch is not cleanup-eligible while referenced by a workflow, ruleset, release/compatibility contract, active automation, or open PR. The Compatibility Farm state branch is already protected by an active repository ruleset against deletion and non-fast-forward updates; P2-C treats that protection as architecture, not cleanup noise.

## PR hygiene

Merged work branches require live-target/post-merge verification before becoming cleanup-eligible. Closed-unmerged branches require explicit reviewed abandonment. Audit evidence such as exact base/head, checks, reviews, and post-merge verification remains in GitHub history even if a later owner-authorized cleanup removes the disposable branch ref.

## Automation boundary

`tools/branch_pr_hygiene.py` only evaluates supplied evidence. `CLEANUP_ELIGIBLE` means the branch passed hygiene checks; it does not delete the branch and does not grant deletion authority. `UNKNOWN`, missing reference scans, open PRs, active references, or incomplete merge/abandonment evidence fail closed to `HELD`.
