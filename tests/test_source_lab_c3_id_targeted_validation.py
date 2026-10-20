from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "source_lab_c3_id_targeted_validation.py"
SPEC = importlib.util.spec_from_file_location("c3", MODULE_PATH)
c3 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(c3)


def assessment(cid, *, farm_keiyoushi=None, inv_keiyoushi=None, inv_uma=None, farm_uma=None, inv_gekkoushi=None, farm_gekkoushi=None):
    return {
        "canonicalId": cid,
        "displayName": cid.rsplit(":", 1)[-1],
        "currentConsumerCoverageProviders": [],
        "providers": {
            "keiyoushi": {
                "consumerRole": "REFERENCE_NOT_DIRECTLY_PACKAGED",
                "farmIdentity": farm_keiyoushi,
                "inventoryIdentity": inv_keiyoushi,
            },
            "uma": {
                "consumerRole": "CURRENT_CONSUMER_CURATED",
                "farmIdentity": farm_uma,
                "inventoryIdentity": inv_uma,
            },
            "gekkoushi": {
                "consumerRole": "CURRENT_CONSUMER_INCLUDE_ALL",
                "farmIdentity": farm_gekkoushi,
                "inventoryIdentity": inv_gekkoushi,
            },
        },
    }


def fake_c2():
    rows = [
        {"canonicalId": cid, "reasons": ["reason"]}
        for cid in sorted(c3.EXPECTED_COHORT)
    ]
    assessments = [
        assessment(
            "miyorare:inventory-id:DAILYSUKA",
            farm_keiyoushi={"module": "src/id/dailysuka", "sourceId": 1, "sourceName": "DailySuka"},
        ),
        assessment(
            "miyorare:inventory-id:IKIRU",
            farm_keiyoushi={"module": "src/id/ikiru", "sourceId": 1, "sourceName": "Ikiru"},
            inv_keiyoushi={"module": "src/id/ikiru", "sourceId": 2, "sourceName": "Ikiru"},
        ),
        assessment(
            "miyorare:inventory-id:LUMOSKOMIK",
            inv_gekkoushi={"file": "src/main/kotlin/tsuki/site/madara/id/LumosKomik.kt", "sourceName": "LUMOSKOMIK"},
        ),
        assessment(
            "miyorare:inventory-id:MANGABALLINDONESIAN",
            inv_uma={"file": "src/main/kotlin/tsuki/site/all/Mangaball.kt", "sourceName": "MANGABALL_ID"},
        ),
        assessment(
            "miyorare:inventory-id:MIKOROKU",
            farm_keiyoushi={"module": "src/id/mikoroku", "sourceId": 3, "sourceName": "MikoRoku"},
            inv_keiyoushi={"module": "src/id/mikoroku", "sourceId": 4, "sourceName": "MikoRoku"},
        ),
        assessment(
            "miyorare:inventory-id:PORNHWA18",
            farm_keiyoushi={"module": "src/id/pornhwa18", "sourceId": 5, "sourceName": "Pornhwa18"},
        ),
        assessment(
            "miyorare:inventory-id:SOFTKOMIK",
            inv_uma={"file": "src/main/kotlin/tsuki/site/id/SoftKomik.kt", "sourceName": "SOFTKOMIK"},
        ),
        assessment(
            "miyorare:inventory-id:THRIVEMOE",
            inv_uma={"file": "src/main/kotlin/tsuki/site/id/ThriveMoe.kt", "sourceName": "THRIVEMOE"},
        ),
    ]
    return {
        "phase": "TRACK_C_BATCH_2_ID_CAPABILITY_HEALTH",
        "language": "id",
        "readOnly": True,
        "provenance": {"x": "y"},
        "c3Candidates": rows,
        "sourceAssessments": assessments,
        "summary": {"c3CanonicalSources": 8, "c3FindingRows": 9},
    }


class C3Tests(unittest.TestCase):
    def test_exact_cohort_required(self):
        data = fake_c2()
        data["c3Candidates"].pop()
        with self.assertRaises(ValueError):
            c3.c3_rows(data)

    def test_source_id_only_reference_migration(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "src/id/ikiru").mkdir(parents=True)
            row = next(x for x in fake_c2()["sourceAssessments"] if x["canonicalId"].endswith(":IKIRU"))
            evidence = c3.reference_evidence(row["canonicalId"], row, root)
            self.assertEqual("REFERENCE_SOURCE_ID_MIGRATION_PRESENT", evidence["state"])

    def test_missing_reference_with_language_relocation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "src/en/pornhwa18").mkdir(parents=True)
            row = next(x for x in fake_c2()["sourceAssessments"] if x["canonicalId"].endswith(":PORNHWA18"))
            evidence = c3.reference_evidence(row["canonicalId"], row, root)
            self.assertEqual("REFERENCE_LANGUAGE_RELOCATED", evidence["state"])
            self.assertEqual(["src/en/pornhwa18"], evidence["relocations"])

    def test_missing_reference_without_relocation_is_removed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "src/id").mkdir(parents=True)
            row = next(x for x in fake_c2()["sourceAssessments"] if x["canonicalId"].endswith(":DAILYSUKA"))
            evidence = c3.reference_evidence(row["canonicalId"], row, root)
            self.assertEqual("REFERENCE_REMOVED_UPSTREAM", evidence["state"])

    def test_runtime_plan_is_source_scoped(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            kei = base / "kei"
            uma_c = base / "uma-c"
            gek_c = base / "gek-c"
            uma_l = base / "uma-l"
            gek_l = base / "gek-l"
            for path in (kei, uma_c, gek_c, uma_l, gek_l):
                path.mkdir(parents=True)
            for module in ("ikiru", "mikoroku"):
                (kei / f"src/id/{module}").mkdir(parents=True)
            (kei / "src/en/pornhwa18").mkdir(parents=True)
            runtime_files = {
                uma_c: [
                    "src/main/kotlin/tsuki/site/all/Mangaball.kt",
                    "src/main/kotlin/tsuki/site/id/SoftKomik.kt",
                    "src/main/kotlin/tsuki/site/id/ThriveMoe.kt",
                ],
                uma_l: [
                    "src/main/kotlin/tsuki/site/all/Mangaball.kt",
                    "src/main/kotlin/tsuki/site/id/SoftKomik.kt",
                ],
                gek_c: ["src/main/kotlin/tsuki/site/madara/id/LumosKomik.kt"],
                gek_l: ["src/main/kotlin/tsuki/site/madara/id/LumosKomik.kt"],
            }
            for root, files in runtime_files.items():
                for rel in files:
                    p = root / rel
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text("class X")
            plan, candidate, lkg = c3.build_plan(
                fake_c2(),
                keiyoushi_root=kei,
                candidate_roots={"uma": uma_c, "gekkoushi": gek_c},
                lkg_roots={"uma": uma_l, "gekkoushi": gek_l},
                commits={"candidate": {}, "lkg": {}},
            )
            self.assertEqual(8, plan["count"])
            self.assertEqual(4, candidate["count"])
            self.assertEqual(3, lkg["count"])
            self.assertEqual(
                {
                    "miyorare:inventory-id:LUMOSKOMIK",
                    "miyorare:inventory-id:MANGABALLINDONESIAN",
                    "miyorare:inventory-id:SOFTKOMIK",
                    "miyorare:inventory-id:THRIVEMOE",
                },
                {x["canonicalId"] for x in candidate["items"]},
            )

    def test_runtime_pass_requires_full_traversal(self):
        self.assertTrue(c3.runtime_pass({
            "status": "PASS",
            "parserExecution": True,
            "detailsTraversal": True,
            "chapterTraversal": True,
            "pageExtraction": True,
        }))
        self.assertFalse(c3.runtime_pass({"status": "PASS", "parserExecution": True}))

    def test_validated_uncurated_uma_routes_to_c4_without_adoption(self):
        item = {"canonicalId": "miyorare:inventory-id:SOFTKOMIK", "runtimeProvider": "uma"}
        runtime = {
            "status": "PASS", "parserExecution": True,
            "detailsTraversal": True, "chapterTraversal": True, "pageExtraction": True,
        }
        row = c3.disposition(item, runtime, runtime)
        self.assertEqual("UNCURATED_UMA_RUNTIME_VALIDATED", row["decision"])
        self.assertEqual("C4_CONSIDER_CURATED_ADOPTION", row["nextAction"])
        self.assertFalse(row["safety"]["autoAdoptProvider"])

    def test_failed_runtime_stays_in_c3_remediation(self):
        item = {"canonicalId": "miyorare:inventory-id:LUMOSKOMIK", "runtimeProvider": "gekkoushi"}
        row = c3.disposition(item, {"status": "FAIL"}, None)
        self.assertEqual("C3_REMEDIATION_REQUIRED", row["nextAction"])
        self.assertFalse(row["safety"]["mutateFarmAuthority"])


if __name__ == "__main__":
    unittest.main()
