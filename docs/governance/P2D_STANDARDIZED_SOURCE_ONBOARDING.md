# P2-D — Standardized Source Onboarding

Baseline: post-P2-C `main` at `52f524aa1c3b62847a94f0dbd11afbe3590861a5`.

P2-D turns the existing Governance V1 onboarding requirements into one deterministic admission contract. It does not create or approve a real source by itself.

## Admission sequence

1. Define a permanent Miyorare canonical identity and prove there is no collision.
2. Declare provider mapping and origin independently from identity.
3. Declare explicit pack membership. Language never implies Global membership.
4. Declare known capabilities as SUPPORTED, UNSUPPORTED, or UNKNOWN; unsupported is not broken.
5. Classify a new source at HIGH risk or higher. UNKNOWN fails closed.
6. Prove build and targeted contract behavior.
7. Perform runtime smoke and regression evidence appropriate for a new source.
8. Bind evidence to the candidate and keep lifecycle at `candidate` until approval.
9. Route promotion through the existing `source_onboarding` authority: `source-lab-approve-ready-sources.yml`, with explicit owner approval and exact Farm/stale-write gates.

## Boundaries

Build success alone is insufficient. A failed/incomplete candidate never replaces LKG. The validator does not modify the Compatibility Farm, canonical registry, stable releases, source implementation, or promotion authority. `READY_FOR_APPROVAL` means the declaration meets admission evidence requirements; it is not approval and cannot merge/promote itself.

The contract intentionally reuses existing authorities rather than creating a second registry or a parallel promotion path: Canonical Source Registry V2 remains identity/pack/origin authority; P1-B remains capability/lifecycle/risk authority; P0-C remains promotion authority.
