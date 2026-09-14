import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "runtime_health",
    Path(__file__).resolve().parents[1] / "tools" / "runtime_health.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

A = "a" * 40
B = "b" * 40
C = "c" * 40


def registry():
    return {
        "policy": {
            "autoAdaptUntilCompatible": True,
            "retryLatestCandidateOnFailure": True,
            "separateRuntimeHealth": True,
            "maintainHealthyHistory": True,
            "emergencyAutoRepair": True,
            "validatedCanonicalFallback": True,
            "temporarilyUnavailableOnNoHealthyOption": True,
        },
        "providers": {
            name: {"lastKnownGood": A, "upstreamBase": A, "healthyHistory": [A], "healthyHistoryLimit": 5}
            for name in MODULE.REQUIRED_PROVIDERS
        },
    }


def state(reg=None, raw_status=None, raw_health=None):
    reg = reg or registry()
    health = MODULE.initialize_health_store(reg, raw_health or {"schema": 1, "providers": {}})
    status = MODULE.sync_status(reg, raw_status or {"providers": {}}, health)
    return reg, status, health


class RuntimeHealthTests(unittest.TestCase):
    def test_hold_does_not_change_runtime_health(self):
        reg, status, health = state()
        MODULE.mark_health(status, health, "keiyoushi", "HEALTHY")
        MODULE.hold_candidate(status, "keiyoushi", B, "candidate-failed")
        source = status["providers"]["keiyoushi"]
        self.assertEqual("HELD", source["updateState"])
        self.assertEqual("HEALTHY", source["runtimeHealth"])
        self.assertEqual(A, source["activeCommit"])

    def test_legacy_held_status_migrates_without_losing_persistent_health(self):
        raw_status = {"providers": {"keiyoushi": {"state": "held", "candidate": B, "lastKnownGood": A}}}
        raw_health = {"providers": {"keiyoushi": {"runtimeHealth": "BROKEN", "activeCommit": A, "healthyHistory": [A], "recoveryState": "ADAPTING_LATEST"}}}
        reg, status, health = state(raw_status=raw_status, raw_health=raw_health)
        source = status["providers"]["keiyoushi"]
        self.assertEqual("HELD", source["updateState"])
        self.assertEqual("BROKEN", source["runtimeHealth"])
        self.assertEqual(B, source["candidate"])

    def test_new_promotion_resets_runtime_health_to_unknown(self):
        reg, status, health = state()
        MODULE.mark_health(status, health, "uma", "HEALTHY")
        MODULE.promote_candidate(reg, status, health, "uma", B)
        self.assertEqual("PROMOTED", status["providers"]["uma"]["updateState"])
        self.assertEqual("UNKNOWN", status["providers"]["uma"]["runtimeHealth"])
        self.assertEqual(B, status["providers"]["uma"]["activeCommit"])

    def test_broken_current_prefers_latest_candidate_repair(self):
        reg, status, health = state()
        MODULE.hold_candidate(status, "keiyoushi", B, "candidate-failed")
        MODULE.mark_health(status, health, "keiyoushi", "BROKEN", "site-api-changed")
        plan = MODULE.recovery_plan(reg, status, "keiyoushi")
        self.assertEqual("ADAPT_LATEST", plan["action"])
        self.assertEqual(B, plan["commit"])

    def test_broken_without_latest_uses_previous_healthy(self):
        reg, status, health = state()
        status["providers"]["keiyoushi"]["activeCommit"] = B
        status["providers"]["keiyoushi"]["healthyHistory"] = [B, A]
        health["providers"]["keiyoushi"]["activeCommit"] = B
        health["providers"]["keiyoushi"]["healthyHistory"] = [B, A]
        MODULE.mark_health(status, health, "keiyoushi", "BROKEN")
        plan = MODULE.recovery_plan(reg, status, "keiyoushi")
        self.assertEqual("TRY_PREVIOUS_HEALTHY", plan["action"])
        self.assertEqual(A, plan["commit"])


if __name__ == "__main__":
    unittest.main()
