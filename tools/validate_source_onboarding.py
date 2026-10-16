#!/usr/bin/env python3
"""Validate a source-onboarding declaration against existing governance authority."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

CAPS={"browse","latest","search","filters","details","chapters","pages","download","authentication","migration","webview","challenge"}
BASELINE={"browse","search","details","chapters","pages"}; PACKS={"miyorare-id","miyorare-en","miyorare-global"}
ORIGINS={"upstream-derived","miyorare-native","upstream-overlay"}; STATES={"SUPPORTED","UNSUPPORTED","UNKNOWN"}
REQUIRED={"canonicalId","displayName","language","packs","origin","providers","capabilities","risk","collisionCheck","build","runtimeSmoke","evidence","promotion","lifecycle","candidateRevision"}
EVIDENCE={"identity","manifest","build","targeted-contract","runtime-smoke","regression"}
PROMOTION_GATES={"ready-for-approval-state","exact-farm-state","owner-dispatch","stale-write-check"}
REVISION_RE=re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def bound(value, revision):
    return isinstance(value,str) and bool(value.strip()) and isinstance(revision,str) and revision in value


def validate(d):
    errors=[]; missing=sorted(REQUIRED-set(d))
    if missing: errors.append("missing:"+",".join(missing))
    cid=d.get("canonicalId","")
    if not isinstance(cid,str) or not cid.startswith("miyorare:"): errors.append("invalid-canonical-id")
    revision=d.get("candidateRevision")
    if not isinstance(revision,str) or not REVISION_RE.fullmatch(revision): errors.append("invalid-candidate-revision")
    packs=d.get("packs")
    if not isinstance(packs,list) or not packs or any(p not in PACKS for p in packs): errors.append("invalid-explicit-pack-membership")
    if d.get("origin") not in ORIGINS: errors.append("invalid-origin")
    if not isinstance(d.get("providers"),list) or not d.get("providers"): errors.append("missing-provider-mapping")
    caps=d.get("capabilities")
    if not isinstance(caps,dict): errors.append("invalid-capabilities")
    else:
        if set(caps)-CAPS: errors.append("unknown-capability-name")
        if BASELINE-set(caps): errors.append("missing-baseline-capability-declaration")
        if any(v not in STATES for v in caps.values()): errors.append("invalid-capability-state")
        if any(v=="UNKNOWN" for v in caps.values()): errors.append("unknown-capability")
    if d.get("risk") not in {"HIGH","VERY_HIGH"}: errors.append("new-source-risk-must-be-high-or-higher")
    for field,error in (("collisionCheck","collision-check-not-proven"),("build","build-not-proven"),("runtimeSmoke","runtime-smoke-not-proven")):
        item=d.get(field)
        if not isinstance(item,dict) or item.get("passed") is not True or not bound(item.get("evidence"),revision): errors.append(error)
    evidence=d.get("evidence")
    if not isinstance(evidence,dict) or not EVIDENCE.issubset(evidence) or any(not bound(evidence.get(k),revision) for k in EVIDENCE): errors.append("insufficient-or-unbound-high-risk-evidence")
    promo=d.get("promotion")
    if not isinstance(promo,dict) or promo.get("class")!="source_onboarding" or promo.get("ownerApprovalRequired") is not True or promo.get("authority")!="source-lab-approve-ready-sources.yml": errors.append("invalid-promotion-authority")
    elif set(promo.get("requiredGates",[])) != PROMOTION_GATES: errors.append("invalid-promotion-required-gates")
    if d.get("lifecycle") != "candidate": errors.append("onboarding-must-start-candidate")
    return errors


def main():
    p=argparse.ArgumentParser(); p.add_argument("path",type=Path); a=p.parse_args(); d=json.loads(a.path.read_text(encoding="utf-8")); errors=validate(d)
    if errors: print(json.dumps({"decision":"HELD","errors":errors},indent=2)); raise SystemExit(1)
    print(json.dumps({"decision":"READY_FOR_APPROVAL","canonicalId":d["canonicalId"],"candidateRevision":d["candidateRevision"]},indent=2))
if __name__=="__main__": main()
