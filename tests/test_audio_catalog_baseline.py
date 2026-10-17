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
        self.assertEqual("BLOCKED", result["releaseEligibility"])
        self.assertEqual(40, len(result["miyorareCommit"]))
        self.assertEqual(40, len(result["hiraukanCommit"]))

    def test_repository_baseline_is_fail_closed_for_release(self) -> None:
        with self.assertRaises(BaselineError):
            validate(BASELINE, require_release_eligible=True)

    def test_release_can_only_become_eligible_when_both_external_gates_are_satisfied(self) -> None:
        data = baseline_data()
        data["releaseEligibility"] = {
            "state": "ELIGIBLE",
            "realDeviceValidated": True,
            "miyorareBetaMerged": True,
            "reason": "REAL_DEVICE_VALIDATED_AND_FINAL_MIYORARE_BETA_MERGED",
        }
        result = validate_data(data, require_release_eligible=True)
        self.assertEqual("ELIGIBLE", result["releaseEligibility"])

    def test_eligible_without_real_device_validation_is_rejected(self) -> None:
        data = baseline_data()
        data["releaseEligibility"]["state"] = "ELIGIBLE"
        data["releaseEligibility"]["miyorareBetaMerged"] = True
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
