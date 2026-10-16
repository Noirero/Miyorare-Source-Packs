# P0-A Stable Release Authority

Status: implemented authority guardrail for the P0-A consolidation.

## Authority model

The official `miyorare-sources-v*` stable release path has one release decision authority and one publishing workflow:

- Controller: `.github/workflows/source-pack-autonomous-release.yml`
- Publisher: `.github/workflows/release-source-packs.yml`
- Seal authority: `.github/workflows/source-pack-release-seal.yml`
- Post-publish auditor: `.github/workflows/source-pack-release-audit.yml`

`release-source-packs-after-merge.yml` is a wake-up/validation path only. It does not allocate a Source Pack version or dispatch the publisher directly.

## Source Lab signed-candidate route

Source Lab remains a candidate/signing subsystem, not a second stable-release policy authority. Its publish workflow verifies the signed candidate and live provider state, creates a temporary ref at the exact signed Foundation commit, and sends that signed release request to the authoritative controller.

The controller independently re-verifies the successful signing run, signing receipt and manifest checksum, GitHub artifact attestation, requested Foundation commit, and temporary ref SHA before allocating a stable version or dispatching the sole publisher on that exact ref.

The end-to-end route is therefore:

`Source Lab signed candidate -> exact temporary Foundation ref -> authoritative controller -> sole publisher -> seal -> audit`

The Source Lab publish workflow then consumes the controller result, verifies the candidate/signing/Foundation bindings, records the immutable publish receipt in Farm state, and removes the temporary ref.

## Version authority

Source Lab no longer allocates `miyorare-sources-v*` versions. Stable version allocation belongs to the authoritative controller. The publisher only receives the controller-selected immutable version.

No other workflow may independently allocate a stable Source Pack version or dispatch the publisher as a competing policy authority.

## Preserved security properties

P0-A preserves:

- exact signed candidate identity;
- owner/caller and signing-run validation;
- signing receipt and manifest digest validation;
- GitHub artifact attestation verification;
- live provider/LKG and evidence-binding verification before the request;
- exact signed Foundation commit through the temporary release ref;
- independent controller-side re-verification before publication;
- immutable release verification and publish receipt recording.

## Non-goals

P0-A does not change main required checks, autonomous promotion policy classes, per-source lifecycle/capability schemas, Source Lab APK releases (`source-lab-v*`), or Source Pack provider behavior. Those belong to later P0/P1 work.
