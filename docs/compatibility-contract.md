# Compatibility contract lifecycle

The compatibility contract is versioned independently from Source Pack releases. A contract change is intentional API evolution, not an automatic consequence of an upstream provider update.

The authoritative bytes are mirrored at the same path in both repositories:

`compatibility/miyorare-source-pack-contract.v1.json`

A compatible release must satisfy the contract that is current in both repositories. Contract mismatch blocks release sealing. Miyorare CI also compares the two copies and fails closed when they diverge.

Changing a manifest schema, required shard, digest requirement, plugin container, source-pack release identity, atomic-install guarantee, rollback behavior, or release-signing policy requires a reviewed contract update on both repositories before a new Source Pack release can be considered compatible.
