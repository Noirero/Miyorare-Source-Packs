import unittest

from tools.branch_pr_hygiene import classify, evaluate


class BranchPrHygieneTests(unittest.TestCase):
    def test_state_bearing_is_protected(self):
        self.assertEqual(classify("compatibility-farm-foundation"), "STATE_BEARING")
        self.assertEqual(evaluate({"branch": "main"})["decision"], "PROTECTED")

    def test_unknown_fails_closed(self):
        result = evaluate({"branch": "mystery-branch", "activeReferences": []})
        self.assertEqual(result["decision"], "HELD")

    def test_open_pr_blocks_cleanup(self):
        result = evaluate({"branch": "feat/example", "openPullRequest": True, "activeReferences": []})
        self.assertEqual(result["reason"], "open-pull-request")

    def test_active_reference_blocks_cleanup(self):
        result = evaluate({"branch": "fix/example", "openPullRequest": False, "activeReferences": ["workflow:x"], "pullRequestState": "MERGED", "liveTargetVerified": True})
        self.assertEqual(result["reason"], "active-reference")

    def test_merged_requires_post_merge_verification(self):
        held = evaluate({"branch": "feat/example", "openPullRequest": False, "activeReferences": [], "pullRequestState": "MERGED", "liveTargetVerified": False})
        ready = evaluate({"branch": "feat/example", "openPullRequest": False, "activeReferences": [], "pullRequestState": "MERGED", "liveTargetVerified": True})
        self.assertEqual(held["decision"], "HELD")
        self.assertEqual(ready["decision"], "CLEANUP_ELIGIBLE")

    def test_closed_unmerged_requires_abandonment_approval(self):
        held = evaluate({"branch": "fix/example", "openPullRequest": False, "activeReferences": [], "pullRequestState": "CLOSED_UNMERGED"})
        ready = evaluate({"branch": "fix/example", "openPullRequest": False, "activeReferences": [], "pullRequestState": "CLOSED_UNMERGED", "abandonmentApproved": True})
        self.assertEqual(held["decision"], "HELD")
        self.assertEqual(ready["decision"], "CLEANUP_ELIGIBLE")

    def test_ephemeral_needs_completion_evidence(self):
        ready = evaluate({"branch": "cleanup-dispatch-smoke-test-20260918", "openPullRequest": False, "activeReferences": [], "pullRequestState": "NONE", "purposeComplete": True, "purposeEvidence": "run:123"})
        self.assertEqual(ready["decision"], "CLEANUP_ELIGIBLE")

    def test_classification_mismatch_fails_closed(self):
        result = evaluate({"branch": "feat/example", "classification": "EPHEMERAL", "activeReferences": []})
        self.assertEqual(result["decision"], "HELD")


if __name__ == "__main__":
    unittest.main()
