import unittest

from tools.source_lab_scoped_approval import ScopedApprovalError, build

CANDIDATE = "2" * 40
GOOD = ["AQUAMANGA", "ASURASCANS", "BACAMI", "KIRYUU", "KOMIKU"]
BLOCKED = "BATCAVE"


def fixture():
    gate = {
        "schemaVersion": 1,
        "candidate": CANDIDATE,
        "compatible": sorted(GOOD),
        "infrastructureBlocked": [BLOCKED],
        "state": "HELD",
        "candidateFarmAllowed": False,
    }
    sources = [
        {
            "canonicalId": name,
            "automationClass": "REVIEWED_COMPATIBLE",
            "evidenceDisposition": {"candidate": CANDIDATE, "evidenceType": "runtime-closure-execution"},
        }
        for name in GOOD
    ]
    sources.append({"canonicalId": BLOCKED, "automationClass": "NEEDS_REVIEW", "evidenceDisposition": None})
    disposition = {"candidate": CANDIDATE, "state": "hold", "blockingSourceCount": 1, "sources": sources}
    return gate, disposition


class ScopedApprovalTests(unittest.TestCase):
    def test_five_sources_become_scope_while_batcave_remains_excluded(self):
        runtime_gate, disposition = fixture()
        aggregate, gate = build(runtime_gate, disposition, "keiyoushi")
        self.assertEqual({"keiyoushi": sorted(GOOD)}, gate["sourceScope"])
        self.assertEqual([BLOCKED], gate["excludedInfrastructureBlocked"])
        self.assertEqual("HELD", gate["providerWideState"])
        self.assertTrue(gate["evidence"]["candidatePass"])
        self.assertEqual("sourceScope", gate["evidence"]["coverage"]["coverageUniverse"])
        self.assertEqual({"keiyoushi": sorted(GOOD)}, aggregate["sourceScope"])
        self.assertTrue(aggregate["parserExecution"])
        self.assertTrue(aggregate["candidatePass"])

    def test_batcave_cannot_enter_compatible_scope_without_exact_evidence(self):
        runtime_gate, disposition = fixture()
        runtime_gate["compatible"].append(BLOCKED)
        runtime_gate["compatible"].sort()
        runtime_gate["infrastructureBlocked"] = []
        with self.assertRaises(ScopedApprovalError):
            build(runtime_gate, disposition, "keiyoushi")

    def test_provider_wide_pass_cannot_be_fabricated(self):
        runtime_gate, disposition = fixture()
        runtime_gate["state"] = "READY"
        runtime_gate["candidateFarmAllowed"] = True
        with self.assertRaises(ScopedApprovalError):
            build(runtime_gate, disposition, "keiyoushi")

    def test_candidate_or_evidence_drift_rejects(self):
        runtime_gate, disposition = fixture()
        disposition["candidate"] = "3" * 40
        with self.assertRaises(ScopedApprovalError):
            build(runtime_gate, disposition, "keiyoushi")
        runtime_gate, disposition = fixture()
        disposition["sources"][0]["evidenceDisposition"]["candidate"] = "3" * 40
        with self.assertRaises(ScopedApprovalError):
            build(runtime_gate, disposition, "keiyoushi")


if __name__ == "__main__":
    unittest.main()
