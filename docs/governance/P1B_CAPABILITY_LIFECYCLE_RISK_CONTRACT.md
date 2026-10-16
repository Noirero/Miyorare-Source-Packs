# P1-B — Capability + Lifecycle + Risk Contract

P1-B defines the vocabulary and fail-closed rules needed to describe what a source supports, where it is in its lifecycle, and how deeply a change must be validated.

## Capability

Capability state is explicit: `SUPPORTED`, `UNSUPPORTED`, or `UNKNOWN`. Unsupported is not the same as broken. Unknown support cannot be promoted as proven support.

The initial vocabulary covers browse, latest, search, filters, details, chapters, pages, download, authentication, migration, WebView, and challenge handling. This contract describes support; it does not invent capability evidence for existing sources.

## Lifecycle

P1-B reuses the lifecycle vocabulary established by Canonical Source Registry V2 and defines allowed transitions. Provider health and source lifecycle remain separate. A provider failure must not automatically demote unrelated sources. Deprecation is not deletion, and migration must preserve canonical identity continuity unless an explicit reviewed migration says otherwise.

## Risk

Risk is classified as LOW, MEDIUM, HIGH, VERY_HIGH, or UNKNOWN. Risk determines minimum validation depth; it is not promotion authority. Unknown classification fails closed to HELD. Shared-runtime changes are VERY_HIGH because validation must cover affected sources rather than only the initiating source.

## Integration boundary

P1-B is deliberately additive. Existing P1-A registry projections remain valid before capability/risk evidence is populated. A later integration may populate per-source capability and risk evidence only from authoritative manifests, tests, or observed compatibility evidence. This contract does not rewrite Farm state, source identity, provider baselines, LKG, or stable releases.
