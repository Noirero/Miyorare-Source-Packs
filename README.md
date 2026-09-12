# Miyorare Source Packs

Official release repository for Miyorare source packs.

This repository keeps source-pack releases separate from the main `Noirero/Miyorare` application releases so APK/app versions remain easy to find.

## Official packs

- **Miyorare-ID** — `miyorare-id.jar`
- **Miyorare-EN** — `miyorare-en.jar`

Release tags use the `miyorare-sources-vMAJOR.MINOR.PATCH` format. Published JAR assets are accompanied by SHA-256 data and are validated by Miyorare before installation.

## Publishing

Use **Actions → Miyorare Source Pack Release → Run workflow** and provide the new source-pack version. The workflow builds the curated packs from the Miyorare `beta` source definition, verifies the output, and publishes an immutable versioned release here.

The application repository remains the source for Miyorare itself; this repository is only the distribution endpoint for Miyorare-owned source packs.
