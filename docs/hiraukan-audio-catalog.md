# Hiraukan audio catalog release asset

When the pinned `Noirero/Miyorare` builder contains
`extensions/miyorare-audio/pack.json`, the Source Pack release workflow
validates it and stages it as:

`miyorare-audio-extensions.json`

The asset remains separate from the strict Tsuki/JAR logical-pack manifest.
This prevents the Miyorare manga runtime from treating an audio catalog as a
Tsuki plugin.

The existing release-seal workflow downloads all non-seal release assets and
binds their name, size and SHA-256 into `miyorare-release-lock.json`.
Therefore the audio catalog receives the same immutable release-lock and OIDC
attestation boundary as the other release assets without changing the three
required manga logical packs.

Until the pinned builder baseline includes the audio-pack files, the asset is
omitted so existing Source Pack releases remain backward compatible.
