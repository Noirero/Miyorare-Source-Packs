# P1-C — Workflow Permission Audit

Baseline audited: `main` at `d0e769ff4fb107fc611e7e25c02690f89f38c9d0` after P1-B.

## Result

The repository already separates many read-only validators from state-mutating and publishing workflows. No `write-all` authority is accepted. P1-C turns that convention into an enforceable repository policy so future workflow edits cannot silently gain write authority.

## Authority boundaries

- Validators and auditors are read-only.
- Exact-head orchestration may use `actions: write` only when it dispatches validation workflows.
- Compatibility Farm / Source Lab state mutators may use `contents: write` only where their existing flow writes the state/ref they own.
- The Source Pack stable controller retains only the write scopes required to create/update its controlled PR/ref and dispatch the sole publisher.
- The sole Source Pack publisher may use `contents: write` for immutable release publication.
- Signing/sealing paths may use `id-token: write` and `attestations: write`; ordinary workflows may not.
- `pull-requests: write` is restricted to the authoritative autonomous release controller.

## Guardrail

`governance/workflow-permission-policy.v1.json` records the allowed write authorities. `tools/validate_workflow_permissions.py` audits every workflow and fails if a workflow relies on implicit top-level permissions, uses `write-all`/`read-all`, or introduces an unlisted write scope. The P1-C CI workflow runs this audit whenever workflow or permission-policy files change.

P1-C does not pin third-party Actions to full SHAs; that is intentionally reserved for P1-D.
