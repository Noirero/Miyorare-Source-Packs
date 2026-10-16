import unittest

from tools.unified_source_health import build, validate


def source(canonical="miyorare:inventory-en:TEST", **overrides):
    value = {
        "canonicalId": canonical,
        "displayName": "Test",
        "language": "en",
        "providers": ["keiyoushi"],
        "upstreamIdentities": {"keiyoushi": {"sourceName": "Test"}},
        "runtimeHealth": "UNKNOWN",
        "approvalState": "NOT_READY",
        "publishEligible": False,
        "compatibilityBaseline": {"status": "PENDING"},
        "lastKnownGood": {"keiyoushi": "lkg"},
        "currentVersion": {"keiyoushi": "current"},
        "enrollmentEvidence": {"workflowRunId": 123, "inventoryCommit": "abc"},
        "protectedOverlays": [],
    }
    value.update(overrides)
    return value


def farm(*sources):
    return {"schemaVersion": 1, "sources": list(sources)}


class UnifiedHealthTests(unittest.TestCase):
    def test_unknown_stays_fail_closed(self):
        result = build(farm(source()), {"workflowRunId": 999, "providers": {"keiyoushi": {"state": "synced"}}})
        item = result["sources"][0]
        self.assertEqual(item["health"], "UNKNOWN")
        self.assertIn("NO_PROVEN_SOURCE_HEALTH", item["reasonCodes"])
        self.assertIsNone(item["lastValidation"]["checkedAt"])
        self.assertEqual(item["lastKnownGood"], {"keiyoushi": "lkg"})

    def test_provider_hold_does_not_blanket_source(self):
        result = build(farm(source(runtimeHealth="HEALTHY", approvalState="APPROVED", publishEligible=True)), {"providers": {"keiyoushi": {"state": "held"}}})
        self.assertEqual(result["sources"][0]["health"], "HEALTHY")
        self.assertEqual(result["sources"][0]["providers"][0]["status"], "held")

    def test_exact_source_hold_overrides_runtime_health(self):
        canonical = "miyorare:inventory-en:TEST"
        upstream = {"providers": {"keiyoushi": {"state": "held", "sourceStatus": [{"canonicalId": canonical, "state": "review-required", "action": "hold"}]}}}
        result = build(farm(source(canonical, runtimeHealth="HEALTHY")), upstream)
        self.assertEqual(result["sources"][0]["health"], "HELD")
        self.assertEqual(result["sources"][0]["reasonCodes"], ["EXPLICIT_UPSTREAM_SOURCE_HOLD"])

    def test_unmatched_upstream_identity_is_reported_not_remapped(self):
        upstream = {"providers": {"keiyoushi": {"sourceStatus": [{"canonicalId": "miyorare:miyorare-en:AQUAMANGA", "state": "review-required"}]}}}
        result = build(farm(source()), upstream)
        self.assertEqual(result["sources"][0]["health"], "UNKNOWN")
        self.assertEqual(result["observability"]["unmatchedUpstreamSourceStatus"], ["miyorare:miyorare-en:AQUAMANGA"])

    def test_lkg_and_identity_are_observational_only(self):
        canonical = "miyorare:inventory-id:TEST"
        result = build(farm(source(canonical, language="id", lastKnownGood={"keiyoushi": "keep-me"})), {"providers": {}})
        item = result["sources"][0]
        self.assertEqual(item["canonicalId"], canonical)
        self.assertEqual(item["packs"], ["miyorare-id"])
        self.assertEqual(item["lastKnownGood"], {"keiyoushi": "keep-me"})
        validate(result)

    def test_duplicate_canonical_identity_fails(self):
        with self.assertRaises(ValueError):
            build(farm(source(), source()), {"providers": {}})


if __name__ == "__main__":
    unittest.main()
