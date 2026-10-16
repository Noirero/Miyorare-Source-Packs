# P1-D — Full-SHA GitHub Actions Pinning

P1-D removes moving GitHub Action tags from repository workflows and replaces them with immutable 40-hex commit SHAs resolved from the exact major tags that were already in use. It is a supply-chain hardening change, not an Action major-version upgrade.

## Rules

- External GitHub Actions in `.github/workflows/*.yml` must use a 40-hex commit SHA.
- The SHA must also appear in `governance/action-pins.v1.json`; an arbitrary immutable SHA is not silently trusted.
- Local reusable workflows (`./.github/workflows/...`) are exempt because they are resolved from the repository revision already under review.
- Existing major-version behavior is preserved: for example, a workflow that used `actions/checkout@v4` remains on the commit resolved from `v4`, while `@v5` remains on the commit resolved from `v5`.
- Updating an Action later requires an explicit policy update plus normal PR/CI review. Moving tags must not be reintroduced.

## Resolved revisions

The approved mapping records the exact commits resolved during P1-D for checkout v4/v5, artifact upload/download, github-script, setup-java, setup-android, Gradle setup v4/v6, and build-provenance attestation v2.

## Validation

`tools/validate_action_pins.py` scans every workflow and fails closed when an external Action is unpinned, unknown to the policy, or pinned to an unapproved SHA. `tests/test_p1d_action_pins.py` protects the fail-closed behavior. The dedicated P1-D CI gate runs both.

P1-D does not change Source Pack identity, provider baselines, Compatibility Farm state, LKG state, promotion authority, or stable-release semantics.
