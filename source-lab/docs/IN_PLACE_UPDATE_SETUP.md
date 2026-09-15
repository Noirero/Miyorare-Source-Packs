# Source Lab in-place update signing

Goal: every new Source Lab APK can be installed over the previous Source Lab installation without uninstalling it or losing app data.

Android requires all updates for the same `applicationId` to use the same signing key. Source Lab therefore uses one dedicated update keystore stored only as GitHub Actions secrets. The keystore, passwords, private GitHub App key, and access tokens must never be committed to this repository or embedded in the APK.

## One-time setup from Android with Termux

Install a current Termux build, then run:

```sh
pkg update
pkg install openjdk-17 coreutils
keytool -genkeypair \
  -keystore miyorare-source-lab-update.jks \
  -alias sourcelab \
  -keyalg RSA \
  -keysize 3072 \
  -validity 10000
```

Choose and retain the keystore password and key password. Keep `miyorare-source-lab-update.jks` backed up privately. Losing this key means future APKs cannot update installations signed by it.

Convert the keystore to a single-line base64 value:

```sh
base64 -w 0 miyorare-source-lab-update.jks > source-lab-keystore.b64
```

In GitHub open:

`Noirero/Miyorare-Source-Packs` → Settings → Secrets and variables → Actions → New repository secret

Create exactly these four secrets:

- `SOURCE_LAB_KEYSTORE_B64` = complete contents of `source-lab-keystore.b64`
- `SOURCE_LAB_KEYSTORE_PASSWORD` = keystore password
- `SOURCE_LAB_KEY_ALIAS` = `sourcelab`
- `SOURCE_LAB_KEY_PASSWORD` = key password

Never put these values in repository variables, issues, discussions, source code, APK resources, or chat messages.

## CI behavior

The Source Lab workflow assigns a monotonically increasing `versionCode` derived from the GitHub Actions run number.

When all four stable-signing secrets exist, CI signs the debug APK with the persistent Source Lab update key, verifies the APK certificate with `apksigner`, and uploads artifact:

`miyorare-source-lab-updateable-debug`

If any signing secret is missing, tests/lint/build may still run, but CI intentionally withholds the installable APK artifact. This prevents accidentally distributing another APK signed with an ephemeral runner debug key.

## First migration

An APK already installed from an older CI run was signed with a different ephemeral debug key. Android cannot convert that installation to the new persistent key.

Therefore there is exactly one unavoidable migration after stable signing is configured:

1. Back up anything needed from the current development build.
2. Uninstall the old Source Lab APK once.
3. Install the first `miyorare-source-lab-updateable-debug` APK.
4. From that point onward, install newer updateable APKs directly over the existing app; do not uninstall.

The package remains `com.noirero.miyorare.sourcelab`. Future builds must never rotate the Source Lab update keystore unless a deliberate package/signing migration is planned.
