"""Regress the approved-onboarding / declarative execution-plan boundary."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from parser_family_plan import execution_plan, validate_harness_files, validate_plan, ParserFamilyPlanError
from parser_harness_report import family_mappings, build_report, HarnessReportError


def read(path):
    return json.loads((ROOT / path).read_text())


class OnboardingCoverageTests(unittest.TestCase):
    def setUp(self):
        self.registry = read("compatibility/source-registry.json")
        self.families = read("compatibility/parser-families.json")
        self.receipt = read("automation/last-source-onboarding-approval.json")
        self.state = read("automation/pending-worker-state.json")
        self.provenance = read("compatibility/onboarding-harness-provenance.json")

    def test_all_approved_memberships_have_exact_evidence_and_executable_counterparts(self):
        rows = {(r["canonicalId"], r["provider"]): r for r in execution_plan(self.families, self.registry)["include"]}
        sources = {s["canonicalId"]: s for s in self.registry["sources"]}
        restored = {(m["canonicalId"], m["provider"]): m for m in self.provenance["memberships"]}
        approved = set()
        for item in self.receipt["sources"]:
            cid = item["canonicalId"]
            source, entry = sources[cid], self.state["sources"][cid]
            digest = hashlib.sha256(json.dumps(entry["evidence"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(item["evidenceSha256"], digest)
            self.assertEqual(source["onboardingApproval"]["evidenceSha256"], digest)
            self.assertEqual(entry["testedVersions"], item["testedVersions"])
            self.assertEqual({"state": "ACTIVE", "parserCoverageRequired": True}, source["compatibilityEnrollment"])
            self.assertEqual("REAL_PARSER_PASS", entry["evidence"]["gate"])

            memberships = {
                membership["provider"]: membership
                for membership in entry["evidence"]["parser"]["memberships"]
            }
            selected = set(item["providers"])
            held = {row["provider"] for row in item.get("heldProviders", [])}
            self.assertEqual(selected, set(source["providers"]))
            self.assertTrue(selected.isdisjoint(held))

            for provider in selected:
                membership = memberships[provider]
                key = cid, provider
                approved.add(key)
                self.assertEqual(membership["testClass"], rows[key]["testClass"])
                self.assertEqual("PASS", membership["status"])
                for flag in ("parserExecution", "detailsTraversal", "chapterTraversal", "pageExtraction"):
                    self.assertIs(membership[flag], True)
                provenance = restored[key]
                self.assertEqual(digest, provenance["evidenceSha256"])
                self.assertEqual(item["workerRunId"], provenance["workerRunId"])
                code = (ROOT / provenance["path"]).read_bytes()
                self.assertEqual(provenance["sha256"], hashlib.sha256(code).hexdigest())
                if provider == "keiyoushi":
                    self.assertEqual(membership["locator"], rows[key]["module"])
                    self.assertEqual("android-gradle-live-test", rows[key]["runner"])
                else:
                    self.assertIn(membership["fqcn"].encode(), code)

            for provider in held:
                self.assertNotIn((cid, provider), rows)

        self.assertEqual(approved, set(restored))
        validate_harness_files(self.families, self.registry, ROOT / "compatibility/harness")

    def test_missing_any_restored_membership_still_fails_closed(self):
        for restored in self.provenance["memberships"]:
            with self.subTest(source=restored["canonicalId"]):
                broken = copy.deepcopy(self.families)
                for family in broken["families"]:
                    if family["provider"] == restored["provider"]:
                        family["members"] = [m for m in family["members"] if m["canonicalId"] != restored["canonicalId"]]
                broken["families"] = [f for f in broken["families"] if f["members"]]
                with self.assertRaisesRegex(ParserFamilyPlanError, "missing real parser family coverage"):
                    validate_plan(broken, self.registry)

    def test_mapping_without_installed_harness_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ParserFamilyPlanError, "installed harness"):
                validate_harness_files(self.families, self.registry, Path(directory))

    def test_normalization_requires_new_memberships_not_only_old_seed_results(self):
        for provider in self.registry["scope"]["providers"]:
            mappings = family_mappings(self.registry, self.families, provider)
            restored = {r["canonicalId"] for r in self.provenance["memberships"] if r["provider"] == provider}
            old_only = {cls: {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}
                        for cid, cls in mappings if cid not in restored}
            with self.assertRaisesRegex(HarnessReportError, "JUnit suite missing"):
                build_report(self.registry, old_only, provider, mappings)

    def test_provider_execution_and_reporting_share_validated_plan(self):
        workflow = (ROOT / ".github/workflows/compatibility-farm-accelerated.yml").read_text()
        for provider in ("uma", "gekkoushi"):
            self.assertIn(f"plan --provider {provider} --output build/parser-plan-{provider}.json", workflow)
            self.assertIn(f"--provider {provider}\n          --families compatibility/parser-families.json", workflow)
        self.assertIn('RUNNER: ${{ matrix.runner }}', workflow)
        self.assertIn('"$RUNNER" == "android-gradle-live-test"', workflow)
        self.assertIn('testImplementation(libs.tachiyomi.lib.v14)', workflow)
        self.assertIn('testImplementation(libs.tachiyomi.lib.v16)', workflow)


if __name__ == "__main__":
    unittest.main()
