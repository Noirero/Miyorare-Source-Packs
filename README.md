# Miyorare Source Packs

Official distribution repository for **Miyorare-maintained source packs**.

This repository keeps Source Pack releases separate from the main `Noirero/Miyorare` application releases so source updates can be published independently while APK/app versions remain easy to find.

## 📦 Official Packs

- 🇮🇩 **Miyorare-ID**
- 🇬🇧 **Miyorare-EN**
- 🌐 **Miyorare-Global**

A logical Source Pack may consist of multiple internal shards/providers as required by compatibility and packaging.

## 🌐 Source Ecosystem

Miyorare Source Packs curate and adapt sources from several compatible ecosystems, including:

- **[Keiyoushi](https://github.com/keiyoushi/extensions-source)**
- **[UMA](https://github.com/InvalidDavid/UMA)**
- **[Gekkoushi](https://github.com/Gekkoushi/plugin-source)**

A source being included in a Miyorare Source Pack does not mean the corresponding website, service, content, or all upstream implementation is owned by Miyorare.

Miyorare is responsible for the curation, integration, packaging, verification, maintenance, and distribution of its official Source Packs.

## 🔄 Upstream Auto-Sync

Miyorare uses a provider-aware upstream synchronization pipeline. The goal is **auto-update by default, manual intervention only on incompatibility**.

The controlled flow is:

```text
upstream change
→ detect
→ classify / adapt / compatibility layer / overlay
→ validate
→ build and integration tests
→ promote safe changes as last-known-good
→ immutable Source Pack release
```

An upstream change is never published directly. If validation fails, the current last-known-good implementation remains authoritative for the affected provider/source.

Provider policies intentionally differ:

- **Keiyoushi** — registered canonical source modules are classified per source before promotion. Metadata-only changes can pass validation. The first reusable semantic adapter supports deterministic **domain/baseUrl changes** by safely rewriting the matching temporary UMA host literal and temporary canonical-domain verification metadata before build/test. Parser-code, selector/API logic, login/auth, or shared-runtime changes remain held until a reusable adapter explicitly supports them.
- **UMA** — candidate revisions must build the curated ID/EN shards successfully through the existing Miyorare compatibility layer.
- **Gekkoushi** — protected Miyorare overlays use a per-target reconciliation base. If upstream changes a protected target such as an overridden parser, that source remains on the Miyorare overlay and is reported as held, while unrelated safe Gekkoushi changes may continue through build/integration and promotion.

Miyorare-specific behavior is protected from upstream overwrite, including canonical source identity, legacy download aliases, provider migration rules, E-Hentai EN↔Global compatibility, Miyorare metadata, authentication adaptations, and Miyorare-specific capabilities.

The synchronization registry lives in `upstream/registry.json`. It stores each provider's last-known-good revision and policy. Protected overlay targets may additionally keep their own `overlayBases`, so a provider revision can advance without erasing the unresolved history of a source whose Miyorare overlay diverged from upstream.

`tools/upstream_sync.py` performs registry validation, upstream planning, reproducible pin materialization, reusable semantic-adapter invocation, per-target overlay conflict tracking, provider promotion, and explicit overlay-base reconciliation after manual review.

`tools/keiyoushi_intake.py` classifies registered Keiyoushi changes per canonical source/module. It is intentionally conservative because Keiyoushi `KeiSource` code and UMA/Tsuki parser code use different runtime APIs; source-code changes are not assumed portable merely because they target the same website.

`tools/keiyoushi_semantic_adapter.py` currently implements the first narrow cross-runtime adapter: verified domain/baseUrl migration. It only rewrites an UMA source when the old registered host is present as a clear string literal (or the new host is already present). Ambiguous dynamic-domain code is blocked. Adapter output is also written beside the disposable UMA checkout so Miyorare pack staging can embed exact `semanticAdapters` provenance in the shard metadata/JAR.

`.github/workflows/upstream-sync.yml` is the main automation pipeline. Failed candidates are held instead of replacing working revisions. Successful candidates can be promoted and, on the production/default branch, can dispatch a new immutable Source Pack release.

`.github/workflows/upstream-sync-status.yml` persists provider and per-source diagnostics after a sync run, including held Keiyoushi modules and protected Gekkoushi overlay conflicts. This status remains useful even when every candidate is held and no release is produced.

### Per-source fail-safe

A conflict in one protected source must not automatically block unrelated safe sources. For example:

```text
Gekkoushi update
├── Gelbooru → upstream touched protected Miyorare overlay → held on overlay
├── Source B → safe → may update
├── Source C → safe → may update
└── Source D → safe → may update
```

The provider can therefore be reported as `promoted-with-held-sources`. The held target keeps its previous overlay reconciliation base until the Miyorare overlay is reviewed and explicitly reconciled.

This does not mean every possible compile/runtime failure can already be isolated to a single source. Shared-runtime or shard-wide failures remain fail-closed until the engine has enough reusable isolation/adaptation support to prove that a partial promotion is safe.

### Future sources

This design applies to sources that already exist **and sources added later**. A new source should be onboarded with a stable canonical identity, upstream/provider mapping, applicable compatibility policy, last-known-good baseline, and any protected Miyorare overlay. Once its provider/pattern is supported by the engine, later compatible upstream updates should not require one-off updater code for that source.

Future source onboarding must reuse provider-level adapters and compatibility rules whenever possible instead of introducing a permanent bespoke updater. New semantic patterns should be implemented as reusable adapter capabilities so later sources using the same pattern inherit support automatically.

### Current runtime boundary

Keiyoushi APK extensions and UMA/Gekkoushi Tsuki JAR shards use different runtimes in Miyorare. The current auto-sync engine detects and classifies Keiyoushi upstream changes against canonical aliases and prevents unsupported parser/runtime changes from being promoted as if they were automatically portable.

It does **not** blindly transpile arbitrary Keiyoushi Android extension Kotlin into a Tsuki JAR. Cross-runtime adoption requires an explicit semantic adapter/runtime path and must pass the same safety gates rather than silently changing source identity, downloads, Favourite/History continuity, or authentication behavior.

### Staged activation

The auto-sync engine is staged on the Source Packs `beta` branch first. The scheduled workflow only becomes production-authoritative after this branch is reviewed and promoted to the repository default branch. Until then, `main` continues to use the existing release path and validated pins.

This staging rule prevents an unfinished adapter or workflow change from silently becoming a production updater.

## 🔗 Upstream & Attribution

| Upstream | Use in Miyorare |
| --- | --- |
| Keiyoushi | Reference/adaptation for compatible sources and extensions |
| UMA | Upstream source/plugin implementation and compatibility |
| Gekkoushi | Upstream source/plugin implementation and compatibility |
| Miyorare | Curation, compatibility layer, packaging, verification, maintenance, and distribution |

Copyright, attribution, and license requirements for upstream implementations remain subject to their respective upstream projects.

## 🔐 Security

Miyorare Source Packs use a controlled release process.

Official packs are built from curated source definitions and validated last-known-good upstream revisions. Automated synchronization may propose newer upstream revisions, but a candidate must pass its provider-specific compatibility checks and integration build before it can replace the relevant last-known-good pin or source state.

Release artifacts are verified using SHA-256 before publication. Miyorare also validates published Source Pack assets before installation where supported by the application.

A Source Pack, source, or upstream update should not be treated as trusted solely because it comes from a popular repository. Changes still require Miyorare validation before becoming part of an official pack.

For the full security model and limitations, see:

**[Miyorare Security Policy](https://github.com/Noirero/Miyorare/blob/main/SECURITY.md)**

## 🏗️ Publishing

Release tags use the following format:

`miyorare-sources-vMAJOR.MINOR.PATCH`

Use **Actions → Miyorare Source Pack Release → Run workflow** and provide the new Source Pack version when a manual release is required.

The release workflow reads validated last-known-good upstream revisions from the Source Pack registry, builds the curated packs from the Miyorare `beta` source definition, verifies the output, and publishes an immutable versioned release here.

Published releases are treated as immutable. An existing Source Pack version is not overwritten; changes are published as a new version.

The application repository remains the source for Miyorare itself. This repository is the distribution endpoint for **Miyorare-maintained Source Packs**.

## ⚠️ Disclaimer

Miyorare Source Packs do not provide, store, or host manga or novels.

Sources act as integrations with external websites or services. Availability, security, policies, legality, and content of those external services remain outside Miyorare's control.
