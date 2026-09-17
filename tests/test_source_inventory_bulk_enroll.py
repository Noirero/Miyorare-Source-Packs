import copy
import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "source_inventory_bulk_enroll.py"
SPEC = importlib.util.spec_from_file_location("source_inventory_bulk_enroll", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


BASELINES = {
    "keiyoushi": "1" * 40,
    "uma": "2" * 40,
    "gekkoushi": "3" * 40,
}


def registry():
    return {
        "schemaVersion": 1,
        "scope": {
            "languages": ["id", "en"],
            "providers": ["keiyoushi", "uma", "gekkoushi"],
            "cohort": "seed-12",
            "targetSize": 1,
            "enrollmentMode": "owner-managed",
        },
        "providerBaselines": copy.deepcopy(BASELINES),
        "defaults": {
            "repairPolicy": {
                "autoDiagnose": True,
                "safeSelfRepair": True,
                "keepLastKnownGood": True,
                "validatedCanonicalFallback": True,
                "holdRequiresOwnerAction": False,
            }
        },
        "sources": [
            {
                "canonicalId": "miyorare:miyorare-id:EXISTING",
                "displayName": "Existing",
                "language": "id",
                "adapterFamily": "known",
                "compatibilityEnrollment": {"state": "ACTIVE", "parserCoverageRequired": True},
                "providers": ["uma"],
                "sentinel": "preserve-me",
            }
        ],
    }


def inventory(*sources):
    return {
        "schemaVersion": 1,
        "kind": "MIYORARE_SOURCE_INVENTORY",
        "informationalOnly": True,
        "sources": list(sources),
    }


class BulkEnrollmentTest(unittest.TestCase):
    def test_enrolls_id_and_en_as_pending_and_preserves_existing(self):
        value, report = MODULE.enroll(
            inventory(
                {
                    "canonicalId": "miyorare:miyorare-id:EXISTING",
                    "displayName": "Existing",
                    "language": "id",
                    "needsAttention": False,
                    "providers": {"uma": {"sourceName": "EXISTING", "file": "src/id/Existing.kt"}},
                },
                {
                    "canonicalId": "miyorare:inventory-id:NEWID",
                    "displayName": "New ID",
                    "language": "id",
                    "needsAttention": False,
                    "providers": {"keiyoushi": {"sourceName": "New ID", "module": "src/id/newid", "sourceId": 1}},
                },
                {
                    "canonicalId": "miyorare:inventory-en:NEWEN",
                    "displayName": "New EN",
                    "language": "en",
                    "needsAttention": False,
                    "providers": {"uma": {"sourceName": "NEWEN", "file": "src/main/kotlin/tsuki/site/en/NewEn.kt"}},
                },
                {
                    "canonicalId": "miyorare:inventory-es:SKIP",
                    "displayName": "Skip",
                    "language": "es",
                    "needsAttention": False,
                    "providers": {"uma": {"sourceName": "SKIP", "file": "skip.kt"}},
                },
            ),
            registry(),
            {
                "keiyoushi": {"src/id/newid/build.gradle.kts"},
                "uma": {"src/main/kotlin/tsuki/site/en/NewEn.kt"},
                "gekkoushi": set(),
            },
            inventory_commit="a" * 40,
            foundation_commit="b" * 40,
            workflow_run_id=42,
        )
        self.assertEqual(3, len(value["sources"]))
        existing = next(s for s in value["sources"] if s["canonicalId"].endswith(":EXISTING"))
        self.assertEqual("preserve-me", existing["sentinel"])
        pending = [s for s in value["sources"] if s["canonicalId"] != existing["canonicalId"]]
        self.assertTrue(all(s["compatibilityEnrollment"] == {"state": "PENDING", "parserCoverageRequired": False} for s in pending))
        self.assertTrue(all(s["publishEligible"] is False for s in pending))
        self.assertEqual("inventory-managed-id-en", value["scope"]["enrollmentMode"])
        self.assertEqual(["id", "en"], value["scope"]["autoEnrollmentLanguages"])
        self.assertEqual(2, report["enrolled"])
        self.assertEqual(1, report["alreadyEnrolled"])

    def test_holds_needs_attention_and_missing_baseline(self):
        value, report = MODULE.enroll(
            inventory(
                {
                    "canonicalId": "miyorare:inventory-id:ATTENTION",
                    "displayName": "Attention",
                    "language": "id",
                    "needsAttention": True,
                    "providers": {"keiyoushi": {"sourceName": "Attention", "module": "src/id/attention"}},
                },
                {
                    "canonicalId": "miyorare:inventory-en:FUTURE",
                    "displayName": "Future",
                    "language": "en",
                    "needsAttention": False,
                    "providers": {"uma": {"sourceName": "FUTURE", "file": "future.kt"}},
                },
            ),
            registry(),
            {"keiyoushi": set(), "uma": set(), "gekkoushi": set()},
            inventory_commit="a" * 40,
            foundation_commit="b" * 40,
        )
        self.assertEqual(1, len(value["sources"]))
        self.assertEqual(1, report["skippedNeedsAttention"])
        self.assertEqual(1, report["skippedMissingAtBaseline"])

    def test_conflicting_duplicate_inventory_canonical_is_held(self):
        base = {
            "canonicalId": "miyorare:inventory-id:DUP",
            "displayName": "Dup",
            "language": "id",
            "needsAttention": False,
            "providers": {"uma": {"sourceName": "DUP", "file": "dup.kt"}},
        }
        other = copy.deepcopy(base)
        other["displayName"] = "Different"
        value, report = MODULE.enroll(
            inventory(base, other),
            registry(),
            {"keiyoushi": set(), "uma": {"dup.kt"}, "gekkoushi": set()},
            inventory_commit="a" * 40,
            foundation_commit="b" * 40,
        )
        self.assertEqual(1, len(value["sources"]))
        self.assertEqual(1, report["skippedDuplicateInventoryCanonical"])


if __name__ == "__main__":
    unittest.main()
