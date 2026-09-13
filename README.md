# Miyorare Source Packs

Official distribution repository for **Miyorare-maintained source packs**.

This repository keeps Source Pack releases separate from the main `Noirero/Miyorare` application releases so source updates can be published independently while APK/app versions remain easy to find.

## 📦 Official Packs

- 🇮🇩 **Miyorare-ID**
- 🇬🇧 **Miyorare-EN**

A logical Source Pack may consist of multiple internal shards/providers as required by compatibility and packaging.

## 🌐 Source Ecosystem

Miyorare Source Packs curate and adapt sources from several compatible ecosystems, including:

- **[Keiyoushi](https://github.com/keiyoushi/extensions-source)**
- **[UMA](https://github.com/InvalidDavid/UMA)**
- **[Gekkoushi](https://github.com/Gekkoushi/plugin-source)**

A source being included in a Miyorare Source Pack does not mean the corresponding website, service, content, or all upstream implementation is owned by Miyorare.

Miyorare is responsible for the curation, integration, packaging, verification, maintenance, and distribution of its official Source Packs.

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

Official packs are built from curated source definitions and, where supported by the current build pipeline, upstream repositories are pinned to explicit commits so upstream changes do not enter a release unexpectedly.

Release artifacts are verified using SHA-256 before publication. Miyorare also validates published Source Pack assets before installation where supported by the application.

A Source Pack, source, or upstream update should not be treated as trusted solely because it comes from a popular repository. Changes still require Miyorare curation and verification before becoming part of an official pack.

For the full security model and limitations, see:

**[Miyorare Security Policy](https://github.com/Noirero/Miyorare/blob/main/SECURITY.md)**

## 🏗️ Publishing

Release tags use the following format:

`miyorare-sources-vMAJOR.MINOR.PATCH`

Use **Actions → Miyorare Source Pack Release → Run workflow** and provide the new Source Pack version.

The workflow builds curated packs from the Miyorare `beta` source definition, verifies the output, and publishes an immutable versioned release here.

Published releases are treated as immutable. An existing Source Pack version is not overwritten; changes are published as a new version.

The application repository remains the source for Miyorare itself. This repository is the distribution endpoint for **Miyorare-maintained Source Packs**.

## ⚠️ Disclaimer

Miyorare Source Packs do not provide, store, or host manga or novels.

Sources act as integrations with external websites or services. Availability, security, policies, legality, and content of those external services remain outside Miyorare's control.
