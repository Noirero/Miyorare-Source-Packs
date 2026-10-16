import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("registry_v2", ROOT / "tools/canonical_source_registry_v2.py")
MODULE = importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(MODULE)
FARM_SHA="b"*40

def authority():
    return {"schemaVersion":1,"kind":"MIYORARE_EXISTING_SOURCE_PACK_AUTHORITY","reviewedFarmCommit":FARM_SHA,"rules":[
        {"canonicalPrefix":"miyorare:miyorare-id:","packs":["miyorare-id"]},
        {"canonicalPrefix":"miyorare:miyorare-en:","packs":["miyorare-en"]},
        {"canonicalPrefix":"miyorare:miyorare-global:","packs":["miyorare-global"]}]}

def legacy_source(**overrides):
    value={"canonicalId":"miyorare:miyorare-en:EXAMPLE","displayName":"Example","language":"en","providers":["keiyoushi"],"upstreamIdentities":{"keiyoushi":{"module":"src/en/example","sourceId":123}},"lastKnownGood":{"keiyoushi":"lkg"},"currentVersion":{"keiyoushi":"current"},"runtimeHealth":"HEALTHY","compatibilityBaseline":{"status":"VALIDATED"},"approvalState":"APPROVED","publishEligible":True,"protectedOverlays":[]}
    value.update(overrides); return value

class CanonicalSourceRegistryV2Tests(unittest.TestCase):
    def test_without_explicit_or_reviewed_pack_authority_holds(self):
        old=legacy_source(); result=MODULE.migrate({"schemaVersion":1,"sources":[old]}); source=result["sources"][0]
        self.assertEqual(source["packs"],[]); self.assertEqual(source["lifecycle"]["state"],"held"); self.assertEqual(source["compatibility"]["health"],"HELD")
    def test_reviewed_existing_source_authority_materializes_pack_without_language(self):
        old=legacy_source(language="zz"); source=MODULE.migrate({"schemaVersion":1,"sources":[old]},authority(),FARM_SHA)["sources"][0]
        self.assertEqual(source["packs"],["miyorare-en"]); self.assertEqual(source["packAuthority"],"reviewed-existing-source-authority"); self.assertEqual(source["lifecycle"]["state"],"active")
    def test_reviewed_authority_is_exact_farm_bound(self):
        with self.assertRaises(ValueError): MODULE.migrate({"schemaVersion":1,"sources":[legacy_source()]},authority(),"c"*40)
    def test_new_explicit_global_membership_overrides_legacy_authority(self):
        source=MODULE.migrate({"schemaVersion":1,"sources":[legacy_source(language="en",packs=["miyorare-global"])]},authority(),FARM_SHA)["sources"][0]
        self.assertEqual(source["packs"],["miyorare-global"]); self.assertEqual(source["packAuthority"],"source-declaration")
    def test_explicit_native_origin_wins_without_provider_inference(self):
        old=legacy_source(packs=["miyorare-en"],origin={"kind":"miyorare-native","providers":[]},upstreamIdentities={},providers=[])
        source=MODULE.migrate({"schemaVersion":1,"sources":[old]})["sources"][0]; self.assertEqual(source["origin"]["kind"],"miyorare-native"); self.assertEqual(source["origin"]["authority"],"source-declaration")
    def test_origin_without_declaration_or_upstream_identity_fails_closed(self):
        with self.assertRaises(ValueError): MODULE.migrate({"schemaVersion":1,"sources":[legacy_source(upstreamIdentities={})]})
    def test_unknown_metadata_does_not_invent_identity(self):
        with self.assertRaises(ValueError): MODULE.migrate({"schemaVersion":1,"sources":[{"canonicalId":None}]})
    def test_duplicate_provider_identity_fails_closed(self):
        base={"displayName":"A","language":"en","packs":["miyorare-en"],"origin":{"kind":"upstream-derived","providers":["keiyoushi"],"authority":"source-declaration"},"providers":{"keiyoushi":{"module":"same","sourceId":1}},"lifecycle":{"state":"candidate","ownerActionRequired":False},"compatibility":{"health":"UNKNOWN","baseline":{},"lastKnownGood":{},"currentVersion":{}}}
        first=dict(base,canonicalId="miyorare:inventory-en:A"); second=dict(base,canonicalId="miyorare:inventory-en:B")
        with self.assertRaises(ValueError): MODULE.validate({"schemaVersion":2,"kind":"MIYORARE_CANONICAL_SOURCE_REGISTRY","sources":[first,second]})

if __name__ == "__main__": unittest.main()
