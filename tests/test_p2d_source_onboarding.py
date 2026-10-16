import unittest
from tools.validate_source_onboarding import validate

REV="a"*40

def ref(label): return f"{label}:{REV}"

def valid():
    return {
      "canonicalId":"miyorare:miyorare-en:EXAMPLE","displayName":"Example","language":"en","candidateRevision":REV,
      "packs":["miyorare-en"],"origin":"upstream-derived","providers":[{"provider":"keiyoushi","sourceKey":"example"}],
      "capabilities":{"browse":"SUPPORTED","search":"SUPPORTED","details":"SUPPORTED","chapters":"SUPPORTED","pages":"SUPPORTED","download":"UNSUPPORTED"},
      "risk":"HIGH","collisionCheck":{"passed":True,"evidence":ref("registry-scan")},
      "build":{"passed":True,"evidence":ref("build")},"runtimeSmoke":{"passed":True,"evidence":ref("smoke")},
      "evidence":{"identity":ref("registry"),"manifest":ref("manifest"),"build":ref("build"),"targeted-contract":ref("contract"),"runtime-smoke":ref("smoke"),"regression":ref("regression")},
      "promotion":{"class":"source_onboarding","ownerApprovalRequired":True,"authority":"source-lab-approve-ready-sources.yml","requiredGates":["ready-for-approval-state","exact-farm-state","owner-dispatch","stale-write-check"]},
      "lifecycle":"candidate"
    }

class Tests(unittest.TestCase):
    def test_valid_candidate(self): self.assertEqual(validate(valid()),[])
    def test_identity_required(self):
        d=valid(); d["canonicalId"]="keiyoushi:example"; self.assertIn("invalid-canonical-id",validate(d))
    def test_pack_is_explicit(self):
        d=valid(); d["packs"]=[]; self.assertIn("invalid-explicit-pack-membership",validate(d))
    def test_unknown_baseline_capability_holds(self):
        d=valid(); d["capabilities"]["pages"]="UNKNOWN"; self.assertIn("unknown-capability",validate(d))
    def test_unknown_nonbaseline_capability_holds(self):
        d=valid(); d["capabilities"]["webview"]="UNKNOWN"; self.assertIn("unknown-capability",validate(d))
    def test_unsupported_capability_is_explicit_not_failure(self):
        d=valid(); d["capabilities"]["webview"]="UNSUPPORTED"; self.assertNotIn("unknown-capability",validate(d))
    def test_new_source_cannot_be_low_risk(self):
        d=valid(); d["risk"]="LOW"; self.assertIn("new-source-risk-must-be-high-or-higher",validate(d))
    def test_runtime_smoke_required(self):
        d=valid(); d["runtimeSmoke"]["passed"]=False; self.assertIn("runtime-smoke-not-proven",validate(d))
    def test_candidate_revision_required(self):
        d=valid(); d["candidateRevision"]="not-a-sha"; self.assertIn("invalid-candidate-revision",validate(d))
    def test_proof_must_bind_exact_revision(self):
        d=valid(); d["build"]["evidence"]="run:1"; self.assertIn("build-not-proven",validate(d))
    def test_evidence_must_bind_exact_revision(self):
        d=valid(); d["evidence"]["regression"]="run:2#regression"; self.assertIn("insufficient-or-unbound-high-risk-evidence",validate(d))
    def test_owner_promotion_authority_required(self):
        d=valid(); d["promotion"]["ownerApprovalRequired"]=False; self.assertIn("invalid-promotion-authority",validate(d))
    def test_exact_promotion_gates_required(self):
        d=valid(); d["promotion"]["requiredGates"].remove("stale-write-check"); self.assertIn("invalid-promotion-required-gates",validate(d))
    def test_candidate_lifecycle_required(self):
        d=valid(); d.pop("lifecycle"); errors=validate(d); self.assertTrue(any(e.startswith("missing:") for e in errors)); self.assertIn("onboarding-must-start-candidate",errors)

if __name__ == "__main__": unittest.main()
