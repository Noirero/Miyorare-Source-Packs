# Miyorare Source Pack trust model

The Source Pack pipeline has three domain outcomes. GitHub job success/failure is not the compatibility state.

- **PASS** — the active last-known-good provider set is valid and no candidate is blocked.
- **HELD** — a candidate update is blocked, but the active last-known-good set remains safe and installable.
- **FAIL** — the active state is broken, malformed, or cannot be trusted. Release is blocked.

`upstream/status.json` contains provider-level evidence. `tools/source_pack_outcome.py` derives the canonical top-level result written to `upstream/outcome.json`.

## Compatibility boundary

`compatibility/miyorare-source-pack-contract.v1.json` is the explicit contract between `Noirero/Miyorare` and this repository. The same bytes must exist in both repositories. It defines manifest versions, required languages/providers, runtime atomicity and rollback expectations, digest policy, release identity, and fail-closed behavior.

## Release sealing

A published Source Pack release is sealed by `.github/workflows/source-pack-release-seal.yml`.

The seal workflow validates the release manifest, recomputes every manifest-bound JAR SHA-256, records every release asset name/size/SHA-256 in `miyorare-release-lock.json`, writes a checksum for the lock, and creates a GitHub OIDC artifact attestation for the lock. The seal files are uploaded without overwrite semantics.

Because the signed lock transitively binds every release asset, changing, removing, replacing, or adding an asset after sealing changes the release relative to its cryptographically attested state. `.github/workflows/source-pack-release-audit.yml` re-downloads sealed releases and verifies both the GitHub attestation and exact lock-to-release equality.

Older releases that predate this model remain legacy releases. New releases are expected to carry the signed lock.
