# P2-A — Unified Health / Observability

Baseline: post-P1-D `main` at `68cc17a6764727fd72a2e4a5d97f68de4988fbd2`.

P2-A creates one deterministic, machine-readable per-source health projection without turning observability into a second mutable source registry. The Compatibility Farm remains the operational source/LKG state authority; Canonical Source Registry V2 rules remain the identity/origin projection authority; `upstream/status.json` contributes provider context and exact per-source hold evidence.

## Unified source record

Each record exposes canonical ID, display name, language/pack, health, lifecycle, reason codes, provider context, origin, last-known-good, last validation, last check, and evidence. Health values are `HEALTHY`, `DEGRADED`, `HELD`, `UNAVAILABLE`, `DEPRECATED`, or `UNKNOWN`.

`UNKNOWN` is deliberate and fail-closed. P2-A does not infer HEALTHY merely because a provider sync succeeded, a source is enrolled, or no failure was observed.

## Isolation rules

Provider state is context, not blanket source health. A provider-level `held` state therefore does not automatically mark every mapped source HELD. An exact per-source `sourceStatus` entry may change that source's projection. If an upstream status names a canonical ID that does not exist in the Farm, P2-A reports it under `unmatchedUpstreamSourceStatus` and does not guess an identity mapping.

This matters for current evidence such as the historical AQUAMANGA status whose canonical spelling does not match the Farm identity namespace: observability surfaces the mismatch instead of silently rewriting identity.

## Time and evidence

Existing state does not provide a trustworthy per-source wall-clock validation/check timestamp. P2-A therefore preserves known workflow run IDs and validation states while emitting `checkedAt: null`. It is forbidden to invent timestamps. A later producer may populate real timestamps only when backed by actual evidence.

## Non-authority

The generated health document is observational. It does not mutate source identity, provider mappings, Farm membership, LKG, lifecycle authority, promotion decisions, release state, or stable artifacts.

## Validation

`tools/unified_source_health.py` builds and validates the projection. Regression tests protect fail-closed UNKNOWN behavior, provider isolation, exact-source holds, unmatched identity reporting, identity/LKG preservation, and duplicate-ID rejection. Source Inventory CI builds the projection from the live Compatibility Farm plus repository `upstream/status.json` and uploads it beside the existing registry previews.
