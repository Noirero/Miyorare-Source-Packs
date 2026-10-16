import json
import unittest
from pathlib import Path


class ActionPinEvidenceTests(unittest.TestCase):
    def test_resolution_evidence_matches_policy(self):
        policy = json.loads(Path('governance/action-pins.v1.json').read_text(encoding='utf-8'))
        evidence = json.loads(Path('governance/action-pin-resolution-evidence.v1.json').read_text(encoding='utf-8'))
        self.assertEqual(evidence.get('schemaVersion'), 1)
        self.assertEqual(evidence.get('kind'), 'MIYORARE_ACTION_PIN_RESOLUTION_EVIDENCE')
        resolved = {(item['action'], item['tag']): item['commit'] for item in evidence['entries']}
        approved = {
            (action, tag): sha
            for action, versions in policy['approved'].items()
            for tag, sha in versions.items()
        }
        self.assertEqual(resolved, approved)


if __name__ == '__main__':
    unittest.main()
