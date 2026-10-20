import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "source_lab_d1_convergence_baseline.py"
SPEC = importlib.util.spec_from_file_location("d1", MODULE_PATH)
d1 = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(d1)

SHA = "1" * 40


def baseline():
    return {
        "schemaVersion": 1,
        "phase": d1.PHASE,
        "readOnly": True,
        "sourcePacksAfterTrackC": SHA,
        "planningRefs": {"sourceInventory": SHA, "compatibilityFarm": SHA, "miyorareAmain2": SHA},
        "trackB": {"phase": "TRACK_B_BATCH_4_ADOPTION_DRIFT", "requiredStatus": "TRACK_B_CLOSED_BASELINE_CLEAN", "baseline": "x"},
        "trackC": {
            "phase": "TRACK_C_BATCH_5_ID_CLOSURE_HANDOFF",
            "requiredStatus": "TRACK_C_CLOSED_WITH_OPERATIONAL_HANDOFFS",
            "monitorPhase": "TRACK_C_BATCH_4_ID_ADOPTION_DRIFT",
            "requiredMonitorStatus": "TRACK_C_C4_COMPLETE_WITH_C3_REMEDIATION",
            "artifact": {"runId": 1, "artifactId": 2, "name": "c5", "digest": "sha256:" + "a" * 64, "headSha": SHA},
        },
        "expectedTrackCDispositions": {
            d1.LUMOS: "LUMOS_RECONCILIATION_ALREADY_SATISFIED_BY_LIFECYCLE",
            d1.MANGABALL: "MANGABALL_SOURCE_PARSER_FAILURE_ROUTED_TO_RETRY",
            d1.SOFTKOMIK: "SOFTKOMIK_AUTH_REQUIRED_ROUTED_TO_OWNER_ACTION",
        },
        "permanentAutomation": {"runtime": "runtime.yml", "approval": "approval.yml"},
        "transitionalMonitors": ["b4.yml", "c4.yml"],
        "nextStage": d1.NEXT_STAGE,
    }


def track_b():
    return {
        "schemaVersion": 1,
        "phase": "TRACK_B_BATCH_4_ADOPTION_DRIFT",
        "readOnly": True,
        "trackBClosed": True,
        "status": "TRACK_B_CLOSED_BASELINE_CLEAN",
        "handoff": {"required": False},
        "adoption": {"adoptionPerformed": False},
        "safety": {"x": False},
    }


def track_c_monitor():
    return {
        "schemaVersion": 1,
        "phase": "TRACK_C_BATCH_4_ID_ADOPTION_DRIFT",
        "readOnly": True,
        "status": "TRACK_C_C4_COMPLETE_WITH_C3_REMEDIATION",
        "handoff": {"driftRequired": False},
        "remediation": {"remainingRows": 3, "canonicalIds": [d1.LUMOS, d1.MANGABALL, d1.SOFTKOMIK]},
        "safety": {"x": False},
    }


def track_c():
    return {
        "schemaVersion": 1,
        "phase": "TRACK_C_BATCH_5_ID_CLOSURE_HANDOFF",
        "readOnly": True,
        "trackCClosed": True,
        "status": "TRACK_C_CLOSED_WITH_OPERATIONAL_HANDOFFS",
        "summary": {"sources": 3, "closureResolved": 3, "unresolved": 0, "operationalHandoffs": 2},
        "decisions": [
            {"canonicalId": d1.LUMOS, "disposition": "LUMOS_RECONCILIATION_ALREADY_SATISFIED_BY_LIFECYCLE"},
            {"canonicalId": d1.MANGABALL, "disposition": "MANGABALL_SOURCE_PARSER_FAILURE_ROUTED_TO_RETRY"},
            {"canonicalId": d1.SOFTKOMIK, "disposition": "SOFTKOMIK_AUTH_REQUIRED_ROUTED_TO_OWNER_ACTION"},
        ],
        "safetyBoundary": {"x": False},
    }


def a7():
    return {
        "schemaVersion": 1,
        "phase": "A7_LKG_SAFETY",
        "status": "SAFE",
        "violations": [],
        "mutatesFoundation": False,
        "promotionAttempted": False,
        "providerCount": 3,
        "activeSourceCount": 10,
        "activeMembershipCount": 12,
    }


def registry():
    return {
        "schemaVersion": 1,
        "sources": [
            {"canonicalId": d1.LUMOS, "providers": ["uma"]},
            {"canonicalId": d1.MANGABALL, "providers": ["uma"]},
            {"canonicalId": d1.SOFTKOMIK, "providers": ["uma"]},
        ],
    }


def worker():
    return {
        "schemaVersion": 2,
        "sources": {
            d1.LUMOS: {"state": "APPROVED", "selectedProviders": ["uma"]},
            d1.MANGABALL: {"state": "RETRY", "failureCategory": "SOURCE_PARSER_FAILURE", "retryPolicy": {"genericFailThresholdAutoHold": False}},
            d1.SOFTKOMIK: {"state": "NEEDS_ATTENTION", "failureCategory": "AUTH_REQUIRED", "authType": "TOKEN"},
        },
    }


def presence():
    return {"runtime": {"path": "runtime.yml", "exists": True}, "approval": {"path": "approval.yml", "exists": True}}


class D1ConvergenceTests(unittest.TestCase):
    def build(self, **overrides):
        values = {
            "baseline": baseline(),
            "track_b": track_b(),
            "track_c_monitor": track_c_monitor(),
            "track_c": track_c(),
            "a7": a7(),
            "registry": registry(),
            "worker": worker(),
            "automation_presence": presence(),
            "current_refs": {"controlHead": SHA, "sourceInventory": SHA, "compatibilityFarm": SHA, "miyorareAmain2": SHA},
        }
        values.update(overrides)
        return d1.build_report(**values)

    def test_clean_convergence_routes_to_d2(self):
        report = self.build()
        self.assertEqual(report["status"], "D1_CONVERGENCE_BASELINE_CLEAN")
        self.assertFalse(report["trackDClosed"])
        self.assertEqual(report["nextStage"], d1.NEXT_STAGE)
        self.assertFalse(any(report["safety"].values()))

    def test_track_b_drift_blocks_d1(self):
        report = track_b()
        report["status"] = "TRACK_B_CLOSED_DRIFT_HANDOFF_REQUIRED"
        report["handoff"]["required"] = True
        with self.assertRaisesRegex(d1.ConvergenceError, "Track B drift"):
            self.build(track_b=report)

    def test_unexplained_id_drift_blocks_d1(self):
        report = track_c_monitor()
        report["status"] = "TRACK_C_C4_COMPLETE_DRIFT_HANDOFF_REQUIRED"
        report["handoff"]["driftRequired"] = True
        with self.assertRaisesRegex(d1.ConvergenceError, "unexplained Track C drift"):
            self.build(track_c_monitor=report)

    def test_track_c_unresolved_blocks_d1(self):
        report = track_c()
        report["summary"]["unresolved"] = 1
        with self.assertRaisesRegex(d1.ConvergenceError, "closure counts"):
            self.build(track_c=report)

    def test_lumos_provider_regression_blocks_d1(self):
        farm = registry()
        farm["sources"][0]["providers"] = ["gekkoushi"]
        with self.assertRaisesRegex(d1.ConvergenceError, "Lumos"):
            self.build(registry=farm)

    def test_mangaball_must_stay_non_terminal_retry(self):
        state = worker()
        state["sources"][d1.MANGABALL]["state"] = "NEEDS_ATTENTION"
        with self.assertRaisesRegex(d1.ConvergenceError, "MangaBall"):
            self.build(worker=state)

    def test_softkomik_requires_explicit_auth_owner_action(self):
        state = worker()
        state["sources"][d1.SOFTKOMIK]["failureCategory"] = "SOURCE_PARSER_FAILURE"
        with self.assertRaisesRegex(d1.ConvergenceError, "SoftKomik"):
            self.build(worker=state)

    def test_unsafe_lkg_blocks_d1(self):
        report = a7()
        report["status"] = "UNSAFE"
        report["violations"] = ["bad"]
        with self.assertRaisesRegex(d1.ConvergenceError, "LKG safety"):
            self.build(a7=report)

    def test_missing_permanent_automation_blocks_d1(self):
        paths = presence()
        paths["runtime"]["exists"] = False
        with self.assertRaisesRegex(d1.ConvergenceError, "automation missing"):
            self.build(automation_presence=paths)


if __name__ == "__main__":
    unittest.main()
