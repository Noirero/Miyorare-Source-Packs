import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools" / "source_lab_b3_runtime_validation.py"
SPEC = importlib.util.spec_from_file_location("source_lab_b3_runtime_validation", MODULE)
b3 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(b3)

COVERAGE_IDS = [f"miyorare:inventory-en:COVERAGE{i:02d}" for i in range(25)]
RUNTIME = {
    "miyorare:inventory-en:FIRESCANS": ["gekkoushi"],
    "miyorare:inventory-en:MANHWA18ORG": ["gekkoushi"],
    "miyorare:inventory-en:NOVELCROW": ["uma", "gekkoushi"],
    "miyorare:inventory-en:PAWMANGA": ["gekkoushi"],
    "miyorare:inventory-en:SHIBAMANGA": ["gekkoushi"],
    "miyorare:inventory-en:WHALEMANGA": ["gekkoushi"],
    "miyorare:inventory-en:WOOPREAD": ["gekkoushi"],
}
HEYTOON = "miyorare:inventory-en:HEYTOON"


def primary_state(provider: str, *, discovered: bool) -> dict:
    suffix = provider.capitalize()
    identity = {
        "file": f"src/main/kotlin/{suffix}.kt",
        "sourceName": suffix.upper(),
    }
    return {
        "discoveredInInventory": discovered,
        "farmIdentity": identity,
        "inventoryIdentity": identity if discovered else None,
        "identityAligned": True if discovered else None,
        "presentInFarm": True,
        "health": {"health": "UNKNOWN"},
    }


def empty_provider() -> dict:
    return {
        "discoveredInInventory": False,
        "farmIdentity": None,
        "inventoryIdentity": None,
        "identityAligned": None,
        "presentInFarm": False,
        "health": {"health": "UNKNOWN"},
    }


def synthetic_b2() -> dict:
    decisions = []
    for cid in COVERAGE_IDS:
        decisions.append({
            "canonicalId": cid,
            "displayName": cid.rsplit(":", 1)[-1],
            "inventoryPresent": False,
            "finding": {"type": "farmCanonicalMissingFromInventory", "detail": {}},
            "decision": {
                "decision": "B3_PRIMARY_COVERAGE_DECISION_REQUIRED",
                "nextPhase": "TRACK_B_BATCH_3",
            },
            "providers": {p: empty_provider() for p in ("keiyoushi", "uma", "gekkoushi")},
        })
    for cid, providers in RUNTIME.items():
        states = {"keiyoushi": empty_provider(), "uma": empty_provider(), "gekkoushi": empty_provider()}
        for provider in providers:
            states[provider] = primary_state(provider, discovered=True)
        decisions.append({
            "canonicalId": cid,
            "displayName": cid.rsplit(":", 1)[-1],
            "inventoryPresent": True,
            "finding": {"type": "farmProviderNotDiscovered", "detail": {"provider": "keiyoushi"}},
            "decision": {
                "decision": "B3_VALIDATE_PRIMARY_BEFORE_IGNORING_REFERENCE_GAP",
                "nextPhase": "TRACK_B_BATCH_3",
            },
            "providers": states,
        })
    states = {
        "keiyoushi": empty_provider(),
        "uma": primary_state("uma", discovered=False),
        "gekkoushi": primary_state("gekkoushi", discovered=True),
    }
    decisions.append({
        "canonicalId": HEYTOON,
        "displayName": "HeyToon",
        "inventoryPresent": True,
        "finding": {"type": "farmProviderNotDiscovered", "detail": {"provider": "uma"}},
        "decision": {
            "decision": "B3_TARGETED_PRIMARY_DISCOVERY_VALIDATION",
            "nextPhase": "TRACK_B_BATCH_3",
        },
        "providers": states,
    })
    return {
        "phase": "TRACK_B_BATCH_2_CAPABILITY_HEALTH_DECISION",
        "readOnly": True,
        "status": "COMPLETE_WITH_DECISIONS",
        "provenance": {
            "controlCommit": "a" * 40,
            "inventoryCommit": "b" * 40,
            "foundationCommit": "c" * 40,
        },
        "summary": {"batch3Rows": 33},
        "decisions": decisions,
    }


def current_inventory_from_b2(report: dict) -> dict:
    rows = []
    for row in report["decisions"]:
        providers = {}
        for provider, state in row["providers"].items():
            identity = state.get("inventoryIdentity")
            if state.get("discoveredInInventory") is True and isinstance(identity, dict):
                providers[provider] = dict(identity, available=True)
        if row.get("inventoryPresent") is True:
            rows.append({
                "canonicalId": row["canonicalId"],
                "displayName": row.get("displayName"),
                "language": "en",
                "providers": providers,
            })
    return {"sources": rows}


def parser_result(canonical_id: str, provider: str, passed: bool) -> dict:
    return {
        "canonicalId": canonical_id,
        "provider": provider,
        "status": "PASS" if passed else "FAIL",
        "parserExecution": passed,
        "detailsTraversal": passed,
        "chapterTraversal": passed,
        "pageTraversal": passed,
    }


def profile(canonical_id: str, provider: str, passed: bool = True) -> dict:
    return {
        "canonicalId": canonical_id,
        "state": "PARSER_PENDING" if passed else "RETRY",
        "evidence": {
            "profile": {
                "memberships": [{
                    "provider": provider,
                    "profilePass": passed,
                    "exists": True,
                    "compile": True,
                    "authType": "NO_AUTH",
                    "probe": {"reachable": passed},
                }]
            }
        },
    }


class B3RuntimeValidationTest(unittest.TestCase):
    def build(self) -> dict:
        report = synthetic_b2()
        return b3.build_plan(
            report,
            current_inventory_from_b2(report),
            current_inventory_commit="d" * 40,
            foundation_commit="e" * 40,
            uma_candidate="1" * 40,
            uma_lkg="2" * 40,
            gekkoushi_candidate="3" * 40,
            gekkoushi_lkg="4" * 40,
        )

    def test_exact_33_row_contract_builds_expected_runtime_plan(self) -> None:
        plan = self.build()
        self.assertEqual(33, plan["summary"]["cohortRows"])
        self.assertEqual(25, plan["summary"]["noRuntimeRows"])
        self.assertEqual(8, plan["summary"]["runtimeSourceRows"])
        self.assertEqual(10, plan["summary"]["runtimeProviderPairs"])
        self.assertEqual(2, plan["summary"]["umaPairs"])
        self.assertEqual(8, plan["summary"]["gekkoushiPairs"])

    def test_heytoon_tests_missing_uma_and_discovered_gekkoushi(self) -> None:
        plan = self.build()
        heytoon = next(row for row in plan["sources"] if row["canonicalId"] == HEYTOON)
        self.assertEqual(["uma", "gekkoushi"], heytoon["runtimeProviders"])

    def test_primary_inventory_drift_is_fail_closed(self) -> None:
        report = synthetic_b2()
        inventory = current_inventory_from_b2(report)
        inventory["sources"].append({
            "canonicalId": COVERAGE_IDS[0],
            "displayName": "Changed",
            "language": "en",
            "providers": {
                "uma": {
                    "available": True,
                    "file": "src/new/Changed.kt",
                    "sourceName": "CHANGED",
                }
            },
        })
        with self.assertRaisesRegex(ValueError, "current primary inventory drift"):
            b3.build_plan(
                report,
                inventory,
                current_inventory_commit="d" * 40,
                foundation_commit="e" * 40,
                uma_candidate="1" * 40,
                uma_lkg="2" * 40,
                gekkoushi_candidate="3" * 40,
                gekkoushi_lkg="4" * 40,
            )

    def test_finalize_routes_candidate_runtime_pass_to_batch4(self) -> None:
        plan = self.build()
        candidate_results, lkg_results = [], []
        candidate_profiles = {"uma": {"results": []}, "gekkoushi": {"results": []}}
        lkg_profiles = {"uma": {"results": []}, "gekkoushi": {"results": []}}
        for provider, provider_plan in plan["providerPlans"].items():
            for item in provider_plan["items"]:
                cid = item["canonicalId"]
                candidate_results.append(parser_result(cid, provider, True))
                lkg_results.append(parser_result(cid, provider, False))
                candidate_profiles[provider]["results"].append(profile(cid, provider))
                lkg_profiles[provider]["results"].append(profile(cid, provider))
        report = b3.finalize(
            plan,
            candidate_profiles=candidate_profiles,
            lkg_profiles=lkg_profiles,
            candidate_parser={"results": candidate_results},
            lkg_parser={"results": lkg_results},
        )
        self.assertEqual(8, report["summary"]["batch4Rows"])
        self.assertEqual(25, report["summary"]["remainingBatch3Rows"])
        self.assertEqual({"CANDIDATE_RECOVERY": 10}, report["summary"]["differential"])

    def test_lkg_pass_candidate_fail_is_regression_and_stays_b3(self) -> None:
        plan = self.build()
        cid = plan["providerPlans"]["gekkoushi"]["items"][0]["canonicalId"]
        report = b3.finalize(
            plan,
            candidate_profiles={
                "uma": {"results": []},
                "gekkoushi": {"results": [profile(cid, "gekkoushi", False)]},
            },
            lkg_profiles={
                "uma": {"results": []},
                "gekkoushi": {"results": [profile(cid, "gekkoushi", True)]},
            },
            candidate_parser={"results": [parser_result(cid, "gekkoushi", False)]},
            lkg_parser={"results": [parser_result(cid, "gekkoushi", True)]},
        )
        evidence = next(row for row in report["runtimeEvidence"] if row["canonicalId"] == cid)
        self.assertEqual("CANDIDATE_REGRESSION", evidence["delta"])
        decision = next(row for row in report["decisions"] if row["canonicalId"] == cid)
        self.assertEqual("TRACK_B_BATCH_3", decision["nextPhase"])

    def test_safety_contract_is_read_only(self) -> None:
        plan = self.build()
        self.assertTrue(plan["readOnly"])
        for key in (
            "mutatesAuthorityState",
            "mutatesLastKnownGood",
            "mutatesRetryHeld",
            "mutatesCanonicalIds",
            "promotesProvider",
            "approvesOverlay",
            "keiyoushiRuntimeUsed",
        ):
            self.assertFalse(plan["safety"][key])


if __name__ == "__main__":
    unittest.main()
