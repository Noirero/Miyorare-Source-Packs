# P1-D Action Reference Inventory

Baseline: post-P1-C `main` at `bfd9595b1d94aaaa3a8de359fd0a66fa8a297505`.

The migration audit found 134 external GitHub Action uses across repository workflows. The moving references belonged to ten exact action/tag pairs:

- `actions/checkout@v5` — 77 occurrences
- `actions/checkout@v4` — 2 occurrences
- `actions/upload-artifact@v4` — 21 occurrences
- `actions/download-artifact@v5` — 13 occurrences
- `actions/github-script@v8` — 3 occurrences
- `actions/setup-java@v5` — 9 occurrences
- `android-actions/setup-android@v4` — 7 occurrences
- `gradle/actions/setup-gradle@v6` — 8 occurrences
- `gradle/actions/setup-gradle@v4` — 2 occurrences
- `actions/attest-build-provenance@v2` — 5 textual occurrences, including workflow contract assertions that intentionally track the attestation action reference.

Counts above are audit evidence from the one-shot migration run. The permanent validator is authoritative for the final repository state: every actual external `uses:` entry must be a policy-approved 40-hex SHA. Local reusable workflows remain repository-local and are exempt.
