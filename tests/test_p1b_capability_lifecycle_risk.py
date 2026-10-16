import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p1b", ROOT / "tools/validate_capability_lifecycle_risk.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class P1BContractTests(unittest.TestCase):
    def contract(self):
        return json.loads((ROOT / "governance/source-capability-lifecycle-risk.v1.json").read_text())

    def test_repository_contract_validates(self):
        MODULE.validate_contract(self.contract())

    def test_unknown_risk_fails_closed(self):
        contract = self.contract()
        contract["validation"]["riskMinimumEvidence"]["UNKNOWN"] = ["runtime-smoke"]
        with self.assertRaises(ValueError):
            MODULE.validate_contract(contract)

    def test_registry_without_capability_evidence_remains_compatible(self):
        registry = {
            "schemaVersion": 2,
            "kind": "MIYORARE_CANONICAL_SOURCE_REGISTRY",
            "sources": [{"canonicalId": "miyorare:miyorare-en:A", "lifecycle": {"state": "active"}}],
        }
        MODULE.validate_registry(registry)

    def test_unsupported_is_valid_capability_state(self):
        registry = {
            "schemaVersion": 2,
            "kind": "MIYORARE_CANONICAL_SOURCE_REGISTRY",
            "sources": [{
                "canonicalId": "miyorare:miyorare-en:A",
                "lifecycle": {"state": "active"},
                "capabilities": {"authentication": "UNSUPPORTED", "search": "SUPPORTED"},
                "risk": {"level": "LOW"},
            }],
        }
        MODULE.validate_registry(registry)

    def test_invalid_capability_and_risk_are_rejected(self):
        registry = {
            "schemaVersion": 2,
            "kind": "MIYORARE_CANONICAL_SOURCE_REGISTRY",
            "sources": [{
                "canonicalId": "miyorare:miyorare-en:A",
                "lifecycle": {"state": "active"},
                "capabilities": {"telepathy": "SUPPORTED"},
                "risk": {"level": "EXTREME"},
            }],
        }
        with self.assertRaises(ValueError):
            MODULE.validate_registry(registry)


if __name__ == "__main__":
    unittest.main()
