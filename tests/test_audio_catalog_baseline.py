import copy
import json
import unittest
from pathlib import Path

from tools.validate_audio_catalog_baseline import (
    BaselineError,
    EXPECTED_RUNTIME_IDS,
    validate,
    validate_data,
)


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "compatibility" / "miyorare-audio-catalog-baseline.json"


def baseline_data() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


class AudioCatalogBaselineTests(unittest.TestCase):
    def test_repository_baseline_is_structurally_valid(self) -> None:
        result = validate(BASELINE)
        self.assertEqual("ELIGIBLE", result["releaseEligibility"])
        self.assertEqual("DEFERRED_BY_OWNER", result["deviceValidation"])
        self.assertFalse(result["deviceValidationRequiredForRelease"])
        self.assertFalse(result["deviceValidated"])
        self.assertEqual(40, len(result["miyorareCommit"]))
        self.assertEqual(40, len(result["hiraukanCommit"]))

    def test_repository_baseline_passes_release_gate(self) -> None:
        result = validate(BASELINE, require_release_eligible=True)
        self.assertEqual("ELIGIBLE", result["releaseEligibility"])

    def test_owner_deferred_device_test_does_not_block_after_beta_merge(self) -> None:
        data = baseline_data()
        data["releaseEligibility"] = {
            "state": "ELIGIBLE",
            "miyorareBetaMerged": True,
            "reason": "FINAL_MIYORARE_BETA_MERGED",
        }
        result = validate_data(data, require_release_eligible=True)
        self.assertEqual("ELIGIBLE", result["releaseEligibility"])
        self.assertFalse(result["deviceValidated"])

    def test_eligible_without_final_beta_merge_is_rejected(self) -> None:
        data = baseline_data()
        data["releaseEligibility"]["state"] = "ELIGIBLE"
        data["releaseEligibility"]["miyorareBetaMerged"] = False
        with self.assertRaises(BaselineError):
            validate_data(data)

    def test_deferred_device_test_cannot_claim_device_evidence(self) -> None:
        data = baseline_data()
        data["deviceValidation"]["validated"] = True
        with self.assertRaises(BaselineError):
            validate_data(data)

    def test_required_device_test_still_blocks_when_not_validated(self) -> None:
        data = baseline_data()
        data["deviceValidation"] = {
            "state": "REQUIRED",
            "requiredForRelease": True,
            "validated": False,
            "note": "Example required device gate",
        }
        data["releaseEligibility"] = {
            "state": "ELIGIBLE",
            "miyorareBetaMerged": True,
            "reason": "INVALID_EXAMPLE",
        }
        with self.assertRaises(BaselineError):
            validate_data(data)

    def test_exact_commit_identity_is_required(self) -> None:
        data = baseline_data()
        data["miyorare"]["catalogCommit"] = "abc123"
        with self.assertRaises(BaselineError):
            validate_data(data)

    def test_runtime_set_drift_is_rejected(self) -> None:
        data = baseline_data()
        data["expectedRuntimeIds"] = sorted(EXPECTED_RUNTIME_IDS - {"miyorare.audio.asmr18"})
        with self.assertRaises(BaselineError):
            validate_data(data)

    def test_validation_does_not_mutate_input(self) -> None:
        data = baseline_data()
        before = copy.deepcopy(data)
        validate_data(data)
        self.assertEqual(before, data)


if __name__ == "__main__":
    unittest.main()
