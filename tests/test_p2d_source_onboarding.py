import unittest
from tools.validate_source_onboarding import validate


def valid():
    return {
      "canonicalId":"miyorare:miyorare-en:EXAMPLE","displayName":"Example","language":"en",
      "packs":["miyorare-en"],"origin":"upstream-derived","providers":[{"provider":"keiyoushi","sourceKey":"example"}],
      "capabilities":{"browse":"SUPPORTED","search":"SUPPORTED","details":"SUPPORTED","chapters":"SUPPORTED","pages":"SUPPORTED","download":"UNSUPPORTED"},
      "risk":"HIGH","collisionCheck":{"passed":True,"evidence":"registry-scan:abc"},
      "build":{"passed":True,"evidence":"run:1"},"runtimeSmoke":{"passed":True,"evidence":"run:2"},
      "evidence":["identity","manifest","build","targeted-contract","runtime-smoke","regression"],
      "promotion":{"class":"source_onboarding","ownerApprovalRequired":True,"authority":"source-lab-approve-ready-sources.yml"},
      "lifecycle":"candidate"
    }

class Tests(unittest.TestCase):
    def test_valid_candidate(self): self.assertEqual(validate(valid()),[])
    def test_identity_required(self):
        d=valid(); d["canonicalId"]="keiyoushi:example"; self.assertIn("invalid-canonical-id",validate(d))
    def test_pack_is_explicit(self):
        d=valid(); d["packs"]=[]; self.assertIn("invalid-explicit-pack-membership",validate(d))
    def test_unknown_baseline_capability_holds(self):
        d=valid(); d["capabilities"]["pages"]="UNKNOWN"; self.assertIn("unknown-baseline-capability",validate(d))
    def test_new_source_cannot_be_low_risk(self):
        d=valid(); d["risk"]="LOW"; self.assertIn("new-source-risk-must-be-high-or-higher",validate(d))
    def test_runtime_smoke_required(self):
        d=valid(); d["runtimeSmoke"]["passed"]=False; self.assertIn("runtime-smoke-not-proven",validate(d))
    def test_collision_evidence_required(self):
        d=valid(); d["collisionCheck"]["evidence"]=""; self.assertIn("collision-check-not-proven",validate(d))
    def test_owner_promotion_authority_required(self):
        d=valid(); d["promotion"]["ownerApprovalRequired"]=False; self.assertIn("invalid-promotion-authority",validate(d))
    def test_candidate_lifecycle_required(self):
        d=valid(); d["lifecycle"]="active"; self.assertIn("onboarding-must-start-candidate",validate(d))

if __name__ == "__main__": unittest.main()
