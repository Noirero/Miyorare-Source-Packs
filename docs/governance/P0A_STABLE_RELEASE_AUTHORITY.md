# P0-A Stable Release Authority

Status: implementation guardrail for the P0-A consolidation.

## Authority model

The official `miyorare-sources-v*` stable release path has one publishing workflow:

- Controller: `.github/workflows/source-pack-autonomous-release.yml`
- Publisher: `.github/workflows/release-source-packs.yml`
- Seal authority: `.github/workflows/source-pack-release-seal.yml`
- Post-publish auditor: `.github/workflows/source-pack-release-audit.yml`

`release-source-packs-after-merge.yml` is a wake-up/validation path only. It must never allocate a Source Pack version or dispatch the publisher directly.

## Source Lab signed-candidate constraint

Source Lab is a candidate/signing subsystem, not a second stable-release policy authority. Its publish path currently carries security properties that must not be weakened during P0-A:

- exact signed candidate identity;
- owner/caller and signing-run validation;
- signing receipt and manifest digest validation;
- GitHub artifact attestation verification;
- live provider/LKG and evidence-binding verification;
- exact signed Foundation commit via a temporary release ref;
- immutable release verification and publish receipt recording.

The remaining Source Lab routing change is only acceptable when the authoritative controller can preserve all of those bindings end-to-end. A redirect that silently releases `main` instead of the exact signed Foundation commit is forbidden.

## Version authority

Stable version allocation must converge to one authority. No new workflow may independently allocate `miyorare-sources-v*` versions. Existing duplicate allocation in the Source Lab signed path is treated as remaining P0-A debt until its exact-commit request can be routed through the authoritative controller without weakening the signed-candidate contract.

## Non-goals

P0-A does not change main required checks, autonomous promotion policy classes, per-source lifecycle/capability schemas, Source Lab APK releases (`source-lab-v*`), or Source Pack provider behavior. Those belong to later P0/P1 work.
