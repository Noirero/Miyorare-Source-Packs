import unittest

from tools.validate_migration_deprecation import validate

A = "miyorare:inventory-en:A"
B = "miyorare:inventory-en:B"


def registry():
    return {"sources": [{"canonicalId": A}, {"canonicalId": B}]}


def state(migrations=None, deprecations=None):
    return {
        "schemaVersion": 1,
        "kind": "MIYORARE_SOURCE_MIGRATION_DEPRECATION_STATE",
        "migrations": migrations or [],
        "deprecations": deprecations or [],
    }


def migration(**overrides):
    item = {
        "id": "migration-a-b",
        "sourceCanonicalId": A,
        "targetCanonicalId": B,
        "reason": "explicit identity replacement",
        "continuity": {"favorites": "migrate", "history": "migrate", "progress": "migrate", "downloads": "migrate", "aliases": "preserve"},
        "aliases": ["legacy-a"],
        "lkgPolicy": "preserve-until-target-proven",
        "evidence": ["review:example"],
        "approval": "PROPOSED",
    }
    item.update(overrides)
    return item


def deprecation(**overrides):
    item = {
        "id": "deprecate-a",
        "canonicalId": A,
        "reason": "permanent upstream retirement",
        "temporaryOutageOnly": False,
        "replacementCanonicalId": B,
        "aliases": ["legacy-a"],
        "evidence": ["upstream:retirement-notice"],
        "approval": "PROPOSED",
        "removal": "NOT_REQUESTED",
    }
    item.update(overrides)
    return item


class MigrationDeprecationTests(unittest.TestCase):
    def test_valid_migration_preserves_continuity_and_lkg_policy(self):
        validate(state(migrations=[migration()]), registry())

    def test_domain_or_provider_change_cannot_fake_identity_migration(self):
        with self.assertRaises(ValueError):
            validate(state(migrations=[migration(targetCanonicalId=A)]), registry())

    def test_unknown_identity_fails_closed(self):
        with self.assertRaises(ValueError):
            validate(state(migrations=[migration(targetCanonicalId="miyorare:inventory-en:UNKNOWN")]), registry())

    def test_missing_continuity_fails(self):
        continuity = migration()["continuity"].copy()
        continuity.pop("downloads")
        with self.assertRaises(ValueError):
            validate(state(migrations=[migration(continuity=continuity)]), registry())

    def test_lkg_must_survive_until_target_proven(self):
        with self.assertRaises(ValueError):
            validate(state(migrations=[migration(lkgPolicy="replace-immediately")]), registry())

    def test_temporary_outage_cannot_be_deprecation(self):
        with self.assertRaises(ValueError):
            validate(state(deprecations=[deprecation(temporaryOutageOnly=True)]), registry())

    def test_deprecation_is_not_implicit_removal(self):
        validate(state(deprecations=[deprecation()]), registry())
        with self.assertRaises(ValueError):
            validate(state(deprecations=[deprecation(removal="OWNER_APPROVED", approval="PROPOSED")]), registry())

    def test_approved_deprecation_can_record_owner_approved_removal(self):
        validate(state(deprecations=[deprecation(approval="APPROVED", removal="OWNER_APPROVED")]), registry())

    def test_duplicate_record_ids_fail(self):
        with self.assertRaises(ValueError):
            validate(state(migrations=[migration(id="same")], deprecations=[deprecation(id="same")]), registry())


if __name__ == "__main__":
    unittest.main()
