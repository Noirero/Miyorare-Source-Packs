# P0-C Automation Promotion Authority

Status: implemented authority guardrail for explicit automation promotion classes.

## Purpose

Automation is allowed to detect, fetch, adapt, validate, stage, and propose broadly. Promotion is narrower: it is permitted only when the candidate belongs to an explicitly authorized class and every gate for that class passes. Unknown, incompatible, stale, or incompletely evidenced candidates fail closed to `HELD`; the last-known-good state remains authoritative.

The machine-readable authority contract is `governance/automation-promotion-authority.v1.json`. `tools/validate_promotion_authority.py` binds that contract to the actual workflows and rejects authority drift.

## Authorized classes

### Builder baseline

The exact Miyorare manifest-changing builder commit is the only PR merge class currently authorized for deterministic automation. The authoritative controller may stage a baseline update, open a PR, validate the exact candidate, and request merge only when the manifest is synchronized with the Compatibility Farm, the exact Miyorare pack checks pass, Source Pack Builder Baseline CI passes, and protected `main` enforces `Main Required Gates`.

The repository ruleset remains an independent enforcement boundary. Automation is not authority to bypass it.

### Provider baseline

Provider candidates are not automation-mergeable. Upstream `autoPromote: true` metadata means that automation may discover/stage the provider candidate; it does not grant promotion authority.

Promotion requires the exact Source Lab candidate set, bound evidence, an Owner approval proof, the authorized-promotion chain, and a stale-write check against the Compatibility Farm. Failure or uncertainty remains `HELD` and preserves LKG.

### Source onboarding

New/pending source onboarding may be prepared and validated automatically, but activation remains Owner-controlled through the ready-source approval workflow. Automation may not infer approval from successful validation alone.

### Stable release

Stable publication is not a generic promotion class. P0-A remains authoritative: the Source Pack controller is the stable release decision/version authority and `release-source-packs.yml` is the sole stable publisher. Source Lab may supply an exact signed request but may not become a competing stable release authority.

## Fail-closed rules

The following never grant promotion authority by themselves:

- an upstream/provider `autoPromote` flag;
- freshness or a newer upstream commit;
- successful build alone;
- successful parser/runtime validation alone;
- an unrecognized candidate class;
- a stale approval, receipt, run, ref, or evidence binding.

When evidence is insufficient, the correct result is `HELD`, not an inferred promotion.

## Relationship to P0-A and P0-B

P0-A defines who may decide and publish a stable release. P0-B makes `Main Required Gates` mandatory for protected `main`. P0-C defines which automation classes are allowed to advance state and which require explicit Owner authority.

Together they form the P0 authority chain:

`explicit promotion class -> class-specific evidence/approval -> protected main gates when applicable -> authoritative stable controller -> sole publisher -> seal -> audit`
