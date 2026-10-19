import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "b1",
    Path(__file__).resolve().parents[1] / "tools" / "source_lab_b1_en_mapping.py",
)
b1 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(b1)


def inv_source(cid, providers, *, attention=False, confidence="exact-name"):
    return {
        "canonicalId": cid,
        "displayName": cid,
        "language": "en",
        "providers": providers,
        "needsAttention": attention,
        "attentionReasons": ["x"] if attention else [],
        "identityConfidence": confidence,
    }


def farm_source(cid, providers, identities, state="ACTIVE"):
    return {
        "canonicalId": cid,
        "displayName": cid,
        "language": "en",
        "providers": providers,
        "upstreamIdentities": identities,
        "compatibilityEnrollment": {"state": state},
    }


class B1Tests(unittest.TestCase):
    def base(self):
        inventory = {
            "kind": "MIYORARE_SOURCE_INVENTORY",
            "informationalOnly": True,
            "stats": {"allSources": 4},
            "providerSnapshots": {
                "keiyoushi": {"commit": "k2"},
                "uma": {"commit": "u2"},
                "gekkoushi": {"commit": "g2"},
            },
            "sources": [
                inv_source("a", {"uma": {"file": "u.kt", "sourceName": "A"}}),
                inv_source(
                    "b",
                    {
                        "gekkoushi": {"file": "g.kt", "sourceName": "B"},
                        "keiyoushi": {"module": "src/en/b", "sourceId": 2},
                    },
                ),
                inv_source("c", {"keiyoushi": {"module": "src/en/c", "sourceId": 3}}),
                inv_source(
                    "d",
                    {
                        "uma": {"file": "du.kt", "sourceName": "D"},
                        "gekkoushi": {"file": "dg.kt", "sourceName": "D"},
                        "keiyoushi": {"module": "src/en/d", "sourceId": 4},
                    },
                    attention=True,
                ),
            ],
        }
        farm = {
            "sources": [
                farm_source("a", ["uma"], {"uma": {"file": "u.kt", "sourceName": "A"}}),
                farm_source(
                    "b",
                    ["gekkoushi", "keiyoushi"],
                    {
                        "gekkoushi": {"file": "g.kt", "sourceName": "B"},
                        "keiyoushi": {"module": "src/en/b", "sourceId": 2},
                    },
                ),
            ]
        }
        aliases = {
            "aliases": [
                {
                    "canonicalId": "a",
                    "language": "en",
                    "verifiedDomain": "a.test",
                    "official": {"sourceName": "A"},
                    "uma": {"file": "u.kt", "sourceName": "A"},
                }
            ]
        }
        upstream = {
            "providers": {
                "keiyoushi": {"lastKnownGood": "k1"},
                "uma": {"lastKnownGood": "u1"},
                "gekkoushi": {"lastKnownGood": "g1"},
            }
        }
        status = {
            "providers": {
                "keiyoushi": {"activeCommit": "k1", "lastKnownGood": "k1"},
                "uma": {"activeCommit": "u1", "lastKnownGood": "u1"},
                "gekkoushi": {"activeCommit": "g1", "lastKnownGood": "g1"},
            },
            "automation": {
                "candidates": {
                    "keiyoushi": {"candidate": "kc"},
                    "uma": {"candidate": "u2"},
                    "gekkoushi": {"candidate": "g2"},
                }
            },
        }
        return inventory, farm, aliases, upstream, status

    def test_counts_and_roles(self):
        report = b1.build_report(*self.base())
        self.assertEqual(report["summary"]["inventoryEnSources"], 4)
        self.assertEqual(report["summary"]["primaryCoveredSources"], 3)
        self.assertEqual(report["summary"]["referenceOnlyKeiyoushiSources"], 1)
        self.assertEqual(report["summary"]["primaryOverlapUmaGekkoushiSources"], 1)
        self.assertEqual(report["inventoryProviderCombinationCounts"]["keiyoushi+uma+gekkoushi"], 1)
        self.assertEqual(report["authority"]["keiyoushiRole"], "REFERENCE_RECOVERY_COMPARISON_ONLY")

    def test_snapshot_relation(self):
        report = b1.build_report(*self.base())
        self.assertEqual(report["providerSnapshotRelations"]["uma"]["relation"], "FARM_CANDIDATE")
        self.assertEqual(report["providerSnapshotRelations"]["gekkoushi"]["relation"], "FARM_CANDIDATE")
        self.assertEqual(report["providerSnapshotRelations"]["keiyoushi"]["relation"], "UNTRACKED_BY_FARM_STATUS")

    def test_identity_drift_detected(self):
        values = list(self.base())
        values[1]["sources"][0]["upstreamIdentities"]["uma"]["file"] = "old.kt"
        report = b1.build_report(*values)
        self.assertEqual(len(report["findings"]["providerIdentityDrift"]), 1)

    def test_farm_provider_not_discovered_detected(self):
        values = list(self.base())
        values[1]["sources"][0]["providers"].append("gekkoushi")
        values[1]["sources"][0]["upstreamIdentities"]["gekkoushi"] = {
            "file": "x.kt",
            "sourceName": "A",
        }
        report = b1.build_report(*values)
        self.assertEqual(
            report["findings"]["farmProviderNotDiscovered"],
            [{"canonicalId": "a", "provider": "gekkoushi"}],
        )

    def test_official_alias_missing_is_finding_not_mutation(self):
        values = list(self.base())
        values[2]["aliases"].append(
            {
                "canonicalId": "missing",
                "language": "en",
                "official": {"sourceName": "M"},
                "uma": {"file": "m.kt", "sourceName": "M"},
            }
        )
        report = b1.build_report(*values)
        self.assertIn("missing", report["findings"]["officialAliasMissingFromInventory"])
        self.assertTrue(report["readOnly"])
        self.assertEqual(report["status"], "COMPLETE_WITH_FINDINGS")

    def test_invalid_inventory_rejected(self):
        values = list(self.base())
        values[0]["informationalOnly"] = False
        with self.assertRaises(ValueError):
            b1.build_report(*values)


if __name__ == "__main__":
    unittest.main()
