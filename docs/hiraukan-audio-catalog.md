# Hiraukan audio catalog release asset

The pinned `Noirero/Miyorare` builder baseline now contains
`extensions/miyorare-audio/pack.json`. The Source Pack release workflow
validates that catalog and stages it as:

`miyorare-audio-extensions.json`

For this baseline and newer compatible baselines, the audio catalog is a
required release asset. Staging fails if the manifest or validator is missing,
if the catalog does not contain the six bundled Hiraukan runtimes, or if its
verified capability declarations drift from the Hiraukan runtime contract.

The asset remains separate from the strict Tsuki/JAR logical-pack manifest.
This prevents the Miyorare manga runtime from treating an audio catalog as a
Tsuki plugin.

The existing release-seal workflow downloads every non-seal release asset and
binds its name, size and SHA-256 into `miyorare-release-lock.json`. The lock
is marked immutable and sealed-before-publish, then attested through GitHub
OIDC. Therefore the Hiraukan audio catalog receives the same release-lock trust
boundary as the other release assets without changing the three required manga
logical packs.
