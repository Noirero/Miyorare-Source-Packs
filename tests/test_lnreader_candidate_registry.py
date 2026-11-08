import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools" / "lnreader_candidate_registry.py"
SPEC = importlib.util.spec_from_file_location("lnreader_candidate_registry", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

def registry():
    return json.loads((ROOT / "registry/lnreader/en-id-candidates.v1.json").read_text(encoding="utf-8"))

class LnReaderCandidateRegistryTests(unittest.TestCase):
    def test_pinned_official_scope_has_unique_english_and_indonesian_candidates(self):
        counts = MODULE.validate(registry())
        self.assertEqual(counts, {"en": 187, "id": 11})
        self.assertEqual(len(registry()["candidates"]), 198)
        self.assertFalse(any(x["state"] == "READY" for x in registry()["candidates"]))

    def test_language_identity_provenance_and_readiness_fail_closed(self):
        original = registry()
        for changes in [
            {"language": "fr"},
            {"id": "../directory"},
            {"version": "latest"},
            {"codeUrl": "https://evil.invalid/x.js"},
            {"state": "READY"},
            {"distribution": {"artifact": "SEALED", "verifiedSha256": None}},
        ]:
            doc = copy.deepcopy(original)
            item = next(x for x in doc["candidates"] if x["id"] != "chikari")
            item.update(changes)
            with self.assertRaises(MODULE.CandidateRegistryError, msg=str(changes)):
                MODULE.validate(doc)

    def test_duplicate_id_is_rejected(self):
        doc = registry()
        doc["candidates"].append(copy.deepcopy(doc["candidates"][0]))
        with self.assertRaises(MODULE.CandidateRegistryError):
            MODULE.validate(doc)

    def test_chikari_api_probe_does_not_claim_epub_or_android_readiness(self):
        doc = registry()
        pilot = next(x for x in doc["candidates"] if x["id"] == "chikari")
        self.assertEqual(pilot["state"], "TESTING")
        self.assertEqual(pilot["checks"]["api"], "PASS")
        self.assertEqual(pilot["checks"]["android"], "UNKNOWN")
        self.assertEqual(pilot["distribution"]["artifact"], "UNPUBLISHED")
        doc["pilot"]["state"] = "READY"
        with self.assertRaises(MODULE.CandidateRegistryError):
            MODULE.validate(doc)

if __name__ == "__main__":
    unittest.main()
