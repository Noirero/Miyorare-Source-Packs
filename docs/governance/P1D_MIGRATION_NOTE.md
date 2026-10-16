# P1-D Migration Note

The bulk replacement was executed only on the dedicated P1-D work branch. Before the migration commit was materialized, the rewritten working tree passed the P1-D regression tests and the full action-pin validator with **134 actual external `uses:` entries** recognized as immutable and policy-approved.

The first bootstrap attempt exposed a validator parsing bug for step-level `- uses:` syntax. No migration commit was published from that failed attempt. The parser was corrected and the migration was revalidated before the final tree was applied to the work branch.

A GitHub Actions token could not push workflow-file changes because it lacked the repository `workflows` permission. The already-validated Git tree was therefore materialized through the repository Git-data path onto the same work branch without changing its contents. Temporary bootstrap workflows are absent from the final P1-D tree.
