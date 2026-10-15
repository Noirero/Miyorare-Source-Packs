# P0-A implementation note

This branch intentionally does not weaken or replace the Source Lab exact signed-candidate publish path. The first consolidation step removes the duplicate after-merge version allocator/direct publisher dispatch and makes that path wake the authoritative autonomous controller instead.

The Source Lab route remains an explicit P0-A follow-up on this same workstream because its direct publisher dispatch is bound to an exact attested Foundation commit. It must not be redirected to a main-based release until the controller accepts and verifies an exact signed release request end-to-end.
