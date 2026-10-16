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


def registry(canonical="miyorare:inventory-en:TEST", packs=None, origin=None, lifecycle="candidate"):
    return {
        "schemaVersion": 2,
        "kind": "MIYORARE_CANONICAL_SOURCE_REGISTRY",
        "sources": [{
            "canonicalId": canonical,
            "packs": [] if packs is None else packs,
            "origin": origin or {"kind": "upstream-derived", "providers": ["keiyoushi"], "authority": "legacy-upstream-identities"},
            "lifecycle": {"state": lifecycle},
        }],
    }


class UnifiedHealthTests(unittest.TestCase):
    def test_unknown_stays_fail_closed(self):
        result = build(farm(source()), {"workflowRunId": 999, "providers": {"keiyoushi": {"state": "synced"}}}, registry())
        item = result["sources"][0]
        self.assertEqual(item["health"], "UNKNOWN")
        self.assertIn("NO_PROVEN_SOURCE_HEALTH", item["reasonCodes"])
        self.assertIsNone(item["lastValidation"]["checkedAt"])
        self.assertEqual(item["lastKnownGood"], {"keiyoushi": "lkg"})

    def test_provider_hold_does_not_blanket_source(self):
        result = build(farm(source(runtimeHealth="HEALTHY", approvalState="APPROVED", publishEligible=True)), {"providers": {"keiyoushi": {"state": "held"}}}, registry(packs=["miyorare-en"], lifecycle="active"))
        self.assertEqual(result["sources"][0]["health"], "HEALTHY")
        self.assertEqual(result["sources"][0]["providers"][0]["status"], "held")

    def test_exact_source_hold_overrides_runtime_health(self):
        canonical = "miyorare:inventory-en:TEST"
        upstream = {"providers": {"keiyoushi": {"state": "held", "sourceStatus": [{"canonicalId": canonical, "state": "review-required", "action": "hold"}]}}}
        result = build(farm(source(canonical, runtimeHealth="HEALTHY")), upstream, registry(canonical, packs=["miyorare-en"], lifecycle="active"))
        self.assertEqual(result["sources"][0]["health"], "HELD")
        self.assertEqual(result["sources"][0]["reasonCodes"], ["EXPLICIT_UPSTREAM_SOURCE_HOLD"])

    def test_unmatched_upstream_identity_is_reported_not_remapped(self):
        upstream = {"providers": {"keiyoushi": {"sourceStatus": [{"canonicalId": "miyorare:miyorare-en:AQUAMANGA", "state": "review-required"}]}}}
        result = build(farm(source()), upstream, registry())
        self.assertEqual(result["sources"][0]["health"], "UNKNOWN")
        self.assertEqual(result["observability"]["unmatchedUpstreamSourceStatus"], ["miyorare:miyorare-en:AQUAMANGA"])

    def test_pack_and_origin_come_from_canonical_authority_not_language(self):
        canonical = "miyorare:inventory-id:TEST"
        authoritative_origin = {"kind": "miyorare-native", "providers": [], "authority": "source-declaration"}
        result = build(
            farm(source(canonical, language="id", lastKnownGood={"keiyoushi": "keep-me"})),
            {"providers": {}},
            registry(canonical, packs=["miyorare-global"], origin=authoritative_origin, lifecycle="active"),
        )
        item = result["sources"][0]
        self.assertEqual(item["canonicalId"], canonical)
        self.assertEqual(item["packs"], ["miyorare-global"])
        self.assertEqual(item["origin"], authoritative_origin)
        self.assertEqual(item["lastKnownGood"], {"keiyoushi": "keep-me"})
        validate(result)

    def test_undeclared_pack_authority_is_held(self):
        result = build(farm(source(runtimeHealth="HEALTHY")), {"providers": {}}, registry(lifecycle="held"))
        item = result["sources"][0]
        self.assertEqual(item["packs"], [])
        self.assertEqual(item["health"], "HELD")
        self.assertEqual(item["reasonCodes"], ["PACK_MEMBERSHIP_UNDECLARED"])

    def test_missing_canonical_authority_fails(self):
        with self.assertRaises(ValueError):
            build(farm(source()), {"providers": {}}, {"schemaVersion": 2, "kind": "MIYORARE_CANONICAL_SOURCE_REGISTRY", "sources": []})

    def test_duplicate_canonical_identity_fails(self):
        with self.assertRaises(ValueError):
            build(farm(source(), source()), {"providers": {}}, registry())


if __name__ == "__main__":
    unittest.main()
