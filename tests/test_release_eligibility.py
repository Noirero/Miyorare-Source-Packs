import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "release_eligibility",
    Path(__file__).resolve().parents[1] / "tools" / "release_eligibility.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

A = "a" * 40
B = "b" * 40


def source_registry():
    return {
        "providerBaselines": {
            provider: A
            for provider in MODULE.REQUIRED_PROVIDERS
        }
    }


def provider(runtime_health="HEALTHY", recovery_state="IDLE", active=A, lkg=A):
    return {
        "updateState": "PROMOTED",
        "runtimeHealth": runtime_health,
        "activeCommit": active,
        "lastKnownGood": lkg,
        "healthyHistory": [A],
        "recoveryState": recovery_state,
    }


def status(**overrides):
    providers = {
        name: provider()
        for name in MODULE.REQUIRED_PROVIDERS
    }
    providers.update(overrides)
    return {"schema": 3, "providers": providers}


class ReleaseEligibilityTests(unittest.TestCase):
    def test_healthy_active_lkg_is_eligible(self):
        value = status()
        MODULE.reconcile(value, source_registry())
        self.assertEqual("ELIGIBLE", value["providers"]["keiyoushi"]["releaseEligibility"])

    def test_degraded_active_lkg_is_still_eligible(self):
        value = status(uma=provider(runtime_health="DEGRADED"))
        MODULE.reconcile(value, source_registry())
        item = value["providers"]["uma"]
        self.assertEqual("ELIGIBLE", item["releaseEligibility"])
        self.assertEqual("ACTIVE_COMMIT_IS_LAST_KNOWN_GOOD", item["releaseEligibilityReason"])

    def test_broken_runtime_is_blocked(self):
        value = status(gekkoushi=provider(runtime_health="BROKEN"))
        MODULE.reconcile(value, source_registry())
        item = value["providers"]["gekkoushi"]
        self.assertEqual("BLOCKED", item["releaseEligibility"])
        self.assertEqual("ACTIVE_RUNTIME_BROKEN", item["releaseEligibilityReason"])

    def test_unknown_runtime_is_fail_closed(self):
        value = status(uma=provider(runtime_health="UNKNOWN"))
        MODULE.reconcile(value, source_registry())
        item = value["providers"]["uma"]
        self.assertEqual("BLOCKED", item["releaseEligibility"])
        self.assertEqual("RUNTIME_HEALTH_UNKNOWN", item["releaseEligibilityReason"])

    def test_active_commit_mismatch_is_blocked(self):
        value = status(keiyoushi=provider(active=B))
        MODULE.reconcile(value, source_registry())
        item = value["providers"]["keiyoushi"]
        self.assertEqual("BLOCKED", item["releaseEligibility"])
        self.assertEqual("ACTIVE_COMMIT_NOT_APPROVED_BASELINE", item["releaseEligibilityReason"])

    def test_temporarily_unavailable_is_blocked(self):
        value = status(uma=provider(runtime_health="DEGRADED", recovery_state="TEMPORARILY_UNAVAILABLE"))
        MODULE.reconcile(value, source_registry())
        self.assertEqual("BLOCKED", value["providers"]["uma"]["releaseEligibility"])

    def test_validate_rejects_stale_or_missing_eligibility(self):
        value = status()
        with self.assertRaises(MODULE.ReleaseEligibilityError):
            MODULE.validate(value, source_registry())
        MODULE.reconcile(value, source_registry())
        value["providers"]["uma"]["releaseEligibility"] = "BLOCKED"
        with self.assertRaises(MODULE.ReleaseEligibilityError):
            MODULE.validate(value, source_registry())


if __name__ == "__main__":
    unittest.main()
