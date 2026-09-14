import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "probe_host_guard",
    Path(__file__).resolve().parents[1] / "tools" / "probe_host_guard.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProbeHostGuardTests(unittest.TestCase):
    def test_dynamic_host_is_never_a_static_probe_target(self):
        self.assertFalse(MODULE.is_static_host("$domain"))
        self.assertFalse(MODULE.is_static_host("${domain}"))
        self.assertTrue(MODULE.is_static_host("hentalk.pw"))

    def test_network_only_broken_is_downgraded_until_runtime_confirmation(self):
        state = {
            "sources": {
                "uma:en:EXAMPLE": {
                    "runtimeHealth": "BROKEN",
                    "probeOutcome": "hard-failure",
                    "consecutiveFailures": 4,
                    "recoveryState": "ADAPTING_LATEST",
                }
            }
        }
        changed = MODULE.downgrade_unconfirmed_network_breaks(state)
        source = state["sources"]["uma:en:EXAMPLE"]
        self.assertEqual(["uma:en:EXAMPLE"], changed)
        self.assertEqual("DEGRADED", source["runtimeHealth"])
        self.assertEqual("AWAITING_RUNTIME_CONFIRMATION", source["recoveryState"])
        self.assertEqual(4, source["networkFailureStreak"])

    def test_runtime_confirmed_broken_is_preserved(self):
        state = {
            "sources": {
                "uma:en:EXAMPLE": {
                    "runtimeHealth": "BROKEN",
                    "probeOutcome": "hard-failure",
                    "runtimeConfirmedBroken": True,
                    "consecutiveFailures": 4,
                    "recoveryState": "ADAPTING_LATEST",
                }
            }
        }
        changed = MODULE.downgrade_unconfirmed_network_breaks(state)
        self.assertEqual([], changed)
        self.assertEqual("BROKEN", state["sources"]["uma:en:EXAMPLE"]["runtimeHealth"])


if __name__ == "__main__":
    unittest.main()
