# P1-D Validation Scope

P1-D validates repository workflow supply-chain references only. It intentionally preserves each Action's existing major-version line while replacing its moving tag with the commit resolved from that tag during the P1-D audit.

The permanent gate checks actual external `uses:` entries, not arbitrary documentation text. Contract assertions that intentionally name an Action reference were migrated to the same immutable SHA so existing release/control-plane checks continue to describe the real workflow behavior.
