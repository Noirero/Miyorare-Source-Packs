#!/usr/bin/env python3
"""Build deterministic evidence digests for approve-only candidate identity.

The binding fingerprints the raw real-parser aggregate, the derived candidate gate, and every
repair evidence file separately. It is intentionally data-only: no registry mutation, approval,
promotion, signing, release, or publish action happens here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


class ApprovalEvidenceError(ValueError):
    pass


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ApprovalEvidenceError(f"evidence file does not exist: {path}")
    return _sha256_bytes(path.read_bytes())


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApprovalEvidenceError(f"invalid JSON evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ApprovalEvidenceError(f"{path} must contain a JSON object")
    return value


def build_binding(aggregate_path: Path, gate_path: Path, repair_paths: Iterable[Path]) -> dict[str, Any]:
    aggregate = _load_object(aggregate_path)
    gate = _load_object(gate_path)

    if aggregate.get("parserExecution") is not True or aggregate.get("candidatePass") is not True:
        raise ApprovalEvidenceError("aggregate must be a passing real-parser candidate")
    if gate.get("approvalState") != "WAITING_FOR_APPROVAL" or gate.get("publishEligible") is not False:
        raise ApprovalEvidenceError("candidate gate must be WAITING_FOR_APPROVAL and not publish eligible")

    repairs: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for path in sorted((Path(item) for item in repair_paths), key=lambda item: item.name):
        if path.name in seen_names:
            raise ApprovalEvidenceError(f"duplicate repair evidence filename: {path.name}")
        seen_names.add(path.name)
        repairs.append({"name": path.name, "sha256": _sha256_file(path)})

    aggregate_repair = aggregate.get("repairEvidence")
    if isinstance(aggregate_repair, dict):
        reported = aggregate_repair.get("reportedMemberships")
        if isinstance(reported, int) and reported >= 0 and reported != len(repairs):
            raise ApprovalEvidenceError(
                f"repair evidence file count {len(repairs)} does not match aggregate reportedMemberships {reported}"
            )

    return {
        "schemaVersion": 1,
        "farmEvidenceSha256": _sha256_file(aggregate_path),
        "gateSha256": _sha256_file(gate_path),
        "repairEvidenceSha256": _sha256_bytes(_canonical(repairs)),
        "repairEvidenceCount": len(repairs),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aggregate", required=True, type=Path)
    parser.add_argument("--gate", required=True, type=Path)
    parser.add_argument("--repair", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        binding = build_binding(args.aggregate, args.gate, args.repair)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(binding, indent=2, sort_keys=True))
        return 0
    except (ApprovalEvidenceError, OSError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
