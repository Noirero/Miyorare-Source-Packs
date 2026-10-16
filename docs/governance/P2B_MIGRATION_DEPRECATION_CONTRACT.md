# P2-B — Migration & Deprecation Contract

Baseline: post-P2-A `main` at `0547cdf35c2c0cc242e3a7a4b2c03186809c4ced`.

P2-B makes migration and deprecation explicit, reviewable, and fail-closed. It does not redefine canonical identity: Canonical Source Registry V2 remains the identity authority and the Compatibility Farm remains the operational/LKG authority.

## Migration

A domain move or provider replacement is not an identity migration. The existing canonical ID remains stable. An identity replacement is exceptional and requires an explicit record naming both existing canonical IDs, a reason, evidence, approval state, aliases, and continuity treatment for favorites, history, progress, downloads, and aliases.

The target must already be a known canonical identity. Unknown identities are rejected rather than guessed or silently rewritten. Last-known-good is preserved until target compatibility is proven.

Migration never means deleting the old source record. Its terminal lifecycle may become `migrated` only through the appropriate lifecycle authority after the migration is actually accepted.

## Deprecation

Deprecation is not deletion. A temporary outage alone cannot deprecate a source. A deprecation record preserves the canonical identity and aliases, requires evidence and review state, and may identify a safe replacement when one exists.

Permanent removal is a separate decision. The ledger distinguishes `NOT_REQUESTED`, `OWNER_APPROVAL_REQUIRED`, and `OWNER_APPROVED`; an owner-approved removal is invalid unless the deprecation itself is approved. This contract records authorization evidence but does not itself delete source state or artifacts.

## State ledger

`governance/source-migration-deprecation-state.v1.json` is the explicit reviewed declaration ledger. It begins empty because P2-B does not infer historical migrations/deprecations from incomplete evidence. Future records must be added through review rather than synthesized from provider/domain changes.

## Validation

`tools/validate_migration_deprecation.py` validates declarations against the live Compatibility Farm canonical identity set. Regression tests cover unknown identities, same-identity pseudo-migrations, continuity completeness, LKG preservation, temporary-outage rejection, removal authorization, and duplicate record IDs.

`P2-B Migration Deprecation CI` checks the exact PR candidate against the live Compatibility Farm using read-only permissions and full-SHA-pinned Actions. The validator is a guardrail; it does not mutate the Farm, LKG, releases, aliases, or source lifecycle.
