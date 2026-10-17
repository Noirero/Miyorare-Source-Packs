# Hiraukan audio catalog release asset

P3 adds the Hiraukan audio catalog to the official Miyorare Source Pack release boundary without changing the existing Tsuki/JAR logical-pack contract.

## Separate authorities

The manga Source Pack builder remains governed by `compatibility/miyorare-builder-baseline.json`. P3 does not move or downgrade that baseline.

Audio uses the independent `compatibility/miyorare-audio-catalog-baseline.json`, which pins:

- the exact `Noirero/Miyorare` Audio Pack catalog commit;
- the exact `Noirero/Hiraukan` runtime commit;
- the six expected built-in runtime IDs;
- explicit release eligibility.

Moving branch names are context only. Release validation consumes exact 40-character commits.

## Runtime contract

Schema v1 permits only `delivery.kind = builtin`. The catalog therefore cannot download or execute extension code. Before a new Source Pack draft can be sealed, P3 validates:

1. Miyorare's own Audio Pack schema and runtime-ID checks;
2. the exact six bundled Hiraukan runtime registrations;
3. the concrete Hiraukan `AudioExtensionManifest` declarations for ID, name, version, auth mode, languages, and capabilities;
4. P3 release eligibility.

The concrete `AudioExtensionManifest` declarations are used for capability comparison. `UnifiedSourceKind` is only a source-aggregation bridge and is not treated as the complete Audio Extension capability authority.

## Release and sealing

For a new unsealed draft, `source-pack-release-seal.yml` stages the exact validated catalog as:

`miyorare-audio-extensions.json`

Only then is the canonical release lock created. The existing seal already binds every non-seal release asset by name, byte size, and SHA-256, so the audio catalog is covered by `miyorare-release-lock.json` without being inserted into the manga/Tsuki logical-pack manifest.

If immutable seal assets already exist, P3 staging is skipped. A sealed release is never retroactively mutated to add the audio catalog.

## Current promotion state

The pinned Miyorare catalog currently comes from Audio Pack PR #219 and is structurally cross-validated against the pinned Hiraukan beta runtime. It is **not yet release-eligible** because the Miyorare Audio Pack has not been promoted to its final beta authority. Stable sealing therefore remains fail-closed.

Real-device validation was explicitly deferred by the owner on 2026-10-17 and is not a P3 release requirement. `deviceValidation.state = DEFERRED_BY_OWNER` records that decision while `validated = false` ensures repository/CI evidence is never misrepresented as physical-device evidence.

Once the final Miyorare beta Audio Pack authority exists, the catalog baseline must be advanced to that exact commit and `miyorareBetaMerged` / `releaseEligibility` may be changed only after refreshing repository truth and rerunning the full P3 validation lane.
