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
→ adapt / compatibility layer / overlay
→ validate
→ build and integration tests
→ promote as last-known-good
→ immutable Source Pack release
```

An upstream change is never published directly. If validation fails, the current last-known-good revision remains authoritative.

Provider policies intentionally differ:

- **Keiyoushi** — canonical/Mihon-compatible upstream metadata is revalidated against Miyorare aliases and compatibility rules before its pin can advance.
- **UMA** — candidate revisions must build the curated ID/EN shards successfully through the existing Miyorare compatibility layer.
- **Gekkoushi** — candidate revisions use the strictest policy. Miyorare performs a three-way-style overlay guard; if upstream modifies a protected target that Miyorare also overlays, automatic promotion is blocked until reviewed.

Miyorare-specific behavior is protected from upstream overwrite, including canonical source identity, legacy download aliases, provider migration rules, E-Hentai EN↔Global compatibility, Miyorare metadata, authentication adaptations, and Miyorare-specific capabilities.

The synchronization registry lives in `upstream/registry.json`. It stores each provider's last-known-good revision and policy. `tools/upstream_sync.py` performs registry validation, upstream planning, reproducible pin materialization, protected-overlay conflict checks, and promotion after validation.

`.github/workflows/upstream-sync.yml` is the automation pipeline. A failing provider candidate is held instead of replacing a working revision. Successful candidates can be promoted and, on the production/default branch, can dispatch a new immutable Source Pack release.

### Future sources

This design applies to sources that already exist **and sources added later**. A new source should be onboarded with a stable canonical identity, upstream/provider mapping, applicable compatibility policy, last-known-good baseline, and any protected Miyorare overlay. Once its provider/pattern is supported by the engine, later compatible upstream updates should not require one-off updater code for that source.

### Current runtime boundary

Keiyoushi APK extensions and UMA/Gekkoushi Tsuki JAR shards use different runtimes in Miyorare. The current auto-sync foundation can detect and validate Keiyoushi upstream changes against canonical aliases, but it does **not** blindly transpile arbitrary Keiyoushi Android extension code into a Tsuki JAR. Cross-runtime adoption requires an explicit compatible adapter/runtime path and must pass the same safety gates rather than silently changing source identity or downloads.

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

Official packs are built from curated source definitions and validated last-known-good upstream revisions. Automated synchronization may propose newer upstream revisions, but a candidate must pass its provider-specific compatibility checks and integration build before it can replace the last-known-good pin.

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
