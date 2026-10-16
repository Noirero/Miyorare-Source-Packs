# P1-A — Canonical Source Registry V2

Status: foundation contract and migration guardrail.

## Purpose

Miyorare Source Packs currently has useful source metadata in more than one layer: informational inventory, Compatibility Farm membership/state, upstream provider registry/status, alias mappings, and pack manifests. P1-A establishes one canonical per-source model so identity is not inferred from provider, domain, pack, or current upstream implementation.

## Authority boundaries

Canonical Source Registry V2 owns per-source identity, provider mappings, explicit pack membership, origin classification, lifecycle, and compatibility/LKG metadata. It does not replace provider registry authority, stable release authority, P0 promotion authority, or runtime health evidence producers.

`canonicalId` is permanent unless an explicit reviewed migration says otherwise. Provider replacement, domain migration, parser replacement, pack movement, or upstream rename must not silently create a new source identity.

## V2 source model

Each source requires:

- `canonicalId` and display/language metadata;
- explicit `packs` membership;
- `origin` (`upstream-derived`, `miyorare-native`, or `upstream-overlay`);
- provider-specific identities under `providers`;
- lifecycle state independent of provider health;
- compatibility health plus baseline/current/LKG evidence.

Unknown identity is not synthesized during authoritative migration. Ambiguity must stop migration for that entry rather than rewrite user-facing identity.

## Migration strategy

The existing Compatibility Farm schemaVersion 1 registry is the migration input because it already preserves canonical IDs, provider identities, current versions, LKG, overlays, approval state, and runtime health. Migration is additive and identity-preserving. The existing Farm registry remains operational authority until a later P1-A integration step explicitly switches consumers after exact validation.

This PR therefore does not mutate `compatibility-farm-foundation`, Source Lab state, provider baselines, pack membership in Miyorare, LKG, or stable releases. It defines and tests the V2 contract first so integration can be surgical rather than a flag-day schema replacement.
