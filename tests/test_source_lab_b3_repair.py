from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "source_lab_b3_repair", ROOT / "tools" / "source_lab_b3_repair.py"
)
repair = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(repair)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class Batch3RepairTest(unittest.TestCase):
    def test_pawmanga_patch_is_fail_closed_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "src/main/kotlin/tsuki/site/madara/en/PawManga.kt"
            write(target, 'x\nMadaraParser(context, MangaParserSource.PAWMANGA, "pawmanga.com", 10)\n')
            receipt = repair.apply_profile(root, "miyorare:inventory-en:PAWMANGA", "gekkoushi")
            text = target.read_text(encoding="utf-8")
            self.assertIn("override val withoutAjax = true", text)
            self.assertIn('listUrl = "webtoon/"', text)
            self.assertNotEqual(receipt["beforeSha256"], receipt["afterSha256"])
            with self.assertRaises(ValueError):
                repair.apply_profile(root, "miyorare:inventory-en:PAWMANGA", "gekkoushi")

    def test_repair_plan_uses_only_bound_targets(self) -> None:
        items = []
        for canonical_id in sorted({cid for cid, _ in repair.TARGETS}):
            candidate = {provider: {"identity": None} for provider in repair.PRIMARY}
            for cid, provider in repair.TARGETS:
                if cid == canonical_id:
                    candidate[provider] = {"identity": {"file": repair.TARGETS[(cid, provider)]["file"]}}
            items.append({"canonicalId": canonical_id, "candidate": candidate})
        plan = repair.build_repair_plan({"items": items})
        self.assertEqual(plan["count"], 3)
        novel = next(row for row in plan["items"] if row["canonicalId"].endswith(":NOVELCROW"))
        self.assertEqual(novel["providers"], ["gekkoushi", "uma"])

    def test_finalize_routes_network_and_missing_terminally(self) -> None:
        plan = {"count": 2, "cohortSha256": "x", "items": [
            {"canonicalId": "missing", "candidate": {"uma": {"identity": None}, "gekkoushi": {"identity": None}}, "lkg": {"uma": {"identity": None}, "gekkoushi": {"identity": None}}},
            {"canonicalId": "network", "candidate": {"uma": {"identity": {"file": "x"}}, "gekkoushi": {"identity": None}}, "lkg": {"uma": {"identity": {"file": "x"}}, "gekkoushi": {"identity": None}}},
        ]}
        profile = {"results": [{"canonicalId": "network", "failureCategory": "NETWORK_TRANSIENT"}]}
        out = repair.finalize(plan, profile, profile, {"results": []}, {"results": []}, {"results": []}, [])
        decisions = {row["canonicalId"]: row["decision"] for row in out["decisions"]}
        self.assertEqual(decisions["missing"], "B3_UNSUPPORTED_NO_PRIMARY_IMPLEMENTATION")
        self.assertEqual(decisions["network"], "B3_TEMPORARILY_UNAVAILABLE_NETWORK")

    def test_finalize_routes_proven_repair_to_batch4(self) -> None:
        canonical_id = "miyorare:inventory-en:PAWMANGA"
        plan = {"count": 1, "cohortSha256": "x", "items": [{
            "canonicalId": canonical_id,
            "candidate": {"uma": {"identity": None}, "gekkoushi": {"identity": {"file": "x"}}},
            "lkg": {"uma": {"identity": None}, "gekkoushi": {"identity": {"file": "x"}}},
        }]}
        live = {"results": [{
            "canonicalId": canonical_id,
            "provider": "gekkoushi",
            "status": "PASS",
            "parserExecution": True,
            "detailsTraversal": True,
            "chapterTraversal": True,
            "pageExtraction": True,
        }]}
        receipt = {"canonicalId": canonical_id, "provider": "gekkoushi"}
        out = repair.finalize(plan, {"results": []}, {"results": []}, {"results": []}, {"results": []}, live, [receipt])
        self.assertEqual(out["decisions"][0]["decision"], "B4_REPAIR_RUNTIME_PROVEN")
        self.assertEqual(out["decisions"][0]["nextPhase"], "TRACK_B_BATCH_4")


if __name__ == "__main__":
    unittest.main()
