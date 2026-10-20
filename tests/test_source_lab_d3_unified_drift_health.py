from __future__ import annotations

import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("d3", ROOT / "tools" / "source_lab_d3_unified_drift_health.py")
assert SPEC and SPEC.loader
D3 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D3)

A = "a" * 40
B = "b" * 40
R = "c" * 40
LEGACY = "miyorare:miyorare-en:LEGACY"
NEW = "miyorare:inventory-en:NEW"


def baseline() -> dict:
    return {
        "schemaVersion": 1,
        "phase": D3.PHASE,
        "readOnlyAcceptance": True,
        "sourcePacksAfterD2": A,
        "compatibilityFarmBaseline": B,
        "reviewedPackAuthorityFarmCommit": R,
        "d2Artifact": {
            "runId": 1,
            "artifactId": 2,
            "name": "d2",
            "digest": "sha256:" + "1" * 64,
            "headSha": A,
            "requiredStatus": D3.D2_STATUS,
        },
        "permanentLayers": {
            "enDriftWorkflow": "b4",
            "idDriftWorkflow": "c4",
            "unifiedHealthWorkflow": "p2a",
            "canonicalRegistryTool": "canonical",
            "unifiedHealthTool": "health",
            "onboardingWorkflow": "onboarding",
        },
        "requiredInvariants": ["a", "b", "c", "d", "e"],
        "nextStage": D3.NEXT_STAGE,
    }


def d2() -> dict:
    return {
        "schemaVersion": 1,
        "phase": D3.D2_PHASE,
        "readOnly": True,
        "status": D3.D2_STATUS,
        "trackDClosed": False,
        "nextStage": D3.PHASE,
        "safety": {"mutate": False},
    }


def canonical(with_handoff: bool = True) -> dict:
    rows = [
        {
            "canonicalId": LEGACY,
            "packs": ["miyorare-en"],
            "packAuthority": "reviewed-existing-source-authority",
            "lifecycle": {"state": "active"},
            "compatibility": {"health": "HEALTHY"},
        }
    ]
    undeclared = []
    if with_handoff:
        rows.append({
            "canonicalId": NEW,
            "packs": [],
            "packAuthority": "undeclared",
            "lifecycle": {"state": "held"},
            "compatibility": {"health": "HELD"},
        })
        undeclared.append(NEW)
    return {
        "schemaVersion": 2,
        "kind": "MIYORARE_CANONICAL_SOURCE_REGISTRY",
        "migration": {
            "reviewedFarmCommit": R,
            "liveFarmCommit": B,
            "reviewedSourceBoundAuthority": True,
            "languageInferenceDisabled": True,
            "packMembershipAuthority": "source-declaration-or-exact-reviewed-source-authority",
            "undeclaredPackMembershipCount": len(undeclared),
            "undeclaredPackMembership": undeclared,
        },
        "sources": rows,
    }


def health(with_handoff: bool = True) -> dict:
    rows = [{"canonicalId": LEGACY, "packs": ["miyorare-en"], "health": "HEALTHY", "reasonCodes": ["FARM_RUNTIME_HEALTHY"]}]
    if with_handoff:
        rows.append({"canonicalId": NEW, "packs": [], "health": "HELD", "reasonCodes": ["PACK_MEMBERSHIP_UNDECLARED"]})
    return {"schemaVersion": 1, "kind": "MIYORARE_UNIFIED_SOURCE_HEALTH", "sources": rows}


def workflows() -> dict[str, str]:
    return {
        "enDriftWorkflow": "schedule:\npermissions:\n  contents: read\nTrack B EN parity drift detected\nExisting Source Lab inventory/Farm/PENDING/approval pipeline remains the handoff authority",
        "idDriftWorkflow": "schedule:\npermissions:\n  contents: read\nTrack C ID parity drift detected\nExisting Source Lab inventory/Farm/PENDING/approval pipeline remains the authority",
        "unifiedHealthWorkflow": "schedule:\ncontents: read\nCheckout live Compatibility Farm state\nCheckout exact reviewed Farm membership snapshot\n--reviewed-farm reviewed-farm/compatibility/source-registry.json\nUndeclared pack memberships fail-closed",
        "onboardingWorkflow": "packs:\nExplicit comma-separated pack membership\n'packs': requested_packs\n'packMembershipAuthority': 'owner-explicit-workflow-input'",
    }


class D3Tests(unittest.TestCase):
    def build(self, c=None, h=None, w=None, d2_report=None, farm=B):
        return D3.build_report(
            baseline(), d2_report or d2(), c or canonical(), h or health(), w or workflows(),
            {"controlHead": A, "compatibilityFarm": farm},
        )

    def test_clean_projection_with_owner_handoff_is_proven_fail_closed(self):
        report = self.build()
        self.assertEqual(report["status"], "D3_UNIFIED_DRIFT_HEALTH_PROVEN_WITH_OWNER_PACK_HANDOFFS")
        self.assertEqual(report["operationalHandoffs"]["count"], 1)
        self.assertEqual(report["operationalHandoffs"]["ownerPackAuthorityRequired"], [NEW])
        self.assertFalse(any(report["safety"].values()))
        self.assertEqual(report["nextStage"], D3.NEXT_STAGE)

    def test_no_handoff_is_fully_proven(self):
        report = self.build(c=canonical(False), h=health(False))
        self.assertEqual(report["status"], "D3_UNIFIED_DRIFT_HEALTH_PROVEN")
        self.assertEqual(report["operationalHandoffs"]["count"], 0)

    def test_undeclared_pack_must_be_held_in_canonical_projection(self):
        c = canonical()
        c["sources"][1]["lifecycle"]["state"] = "active"
        with self.assertRaisesRegex(D3.D3Error, "not held"):
            self.build(c=c)

    def test_unified_health_must_surface_undeclared_pack_handoff(self):
        h = health()
        h["sources"][1]["health"] = "UNKNOWN"
        with self.assertRaisesRegex(D3.D3Error, "did not surface"):
            self.build(h=h)

    def test_missing_read_only_drift_marker_fails_closed(self):
        w = workflows()
        w["enDriftWorkflow"] = w["enDriftWorkflow"].replace("contents: read", "")
        with self.assertRaisesRegex(D3.D3Error, "markers missing"):
            self.build(w=w)

    def test_d2_mutation_boundary_change_fails_closed(self):
        broken = deepcopy(d2())
        broken["safety"]["mutate"] = True
        with self.assertRaisesRegex(D3.D3Error, "D2 safety"):
            self.build(d2_report=broken)

    def test_farm_drift_fails_closed(self):
        with self.assertRaisesRegex(D3.D3Error, "Farm moved"):
            self.build(farm="d" * 40)


if __name__ == "__main__":
    unittest.main()
