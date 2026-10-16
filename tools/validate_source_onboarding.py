#!/usr/bin/env python3
"""Validate a source-onboarding declaration against existing governance authority."""
from __future__ import annotations
import argparse, json
from pathlib import Path

CAPS = {"browse","latest","search","filters","details","chapters","pages","download","authentication","migration","webview","challenge"}
BASELINE = {"browse","search","details","chapters","pages"}
PACKS = {"miyorare-id","miyorare-en","miyorare-global"}
ORIGINS = {"upstream-derived","miyorare-native","upstream-overlay"}
STATES = {"SUPPORTED","UNSUPPORTED","UNKNOWN"}
REQUIRED = {"canonicalId","displayName","language","packs","origin","providers","capabilities","risk","collisionCheck","build","runtimeSmoke","evidence","promotion"}
EVIDENCE = {"identity","manifest","build","targeted-contract","runtime-smoke","regression"}


def validate(d):
    errors=[]
    missing=sorted(REQUIRED-set(d))
    if missing: errors.append("missing:"+",".join(missing))
    cid=d.get("canonicalId","")
    if not isinstance(cid,str) or not cid.startswith("miyorare:"): errors.append("invalid-canonical-id")
    packs=d.get("packs")
    if not isinstance(packs,list) or not packs or any(p not in PACKS for p in packs): errors.append("invalid-explicit-pack-membership")
    if d.get("origin") not in ORIGINS: errors.append("invalid-origin")
    providers=d.get("providers")
    if not isinstance(providers,list) or not providers: errors.append("missing-provider-mapping")
    caps=d.get("capabilities")
    if not isinstance(caps,dict): errors.append("invalid-capabilities")
    else:
        if set(caps)-CAPS: errors.append("unknown-capability-name")
        if BASELINE-set(caps): errors.append("missing-baseline-capability-declaration")
        if any(v not in STATES for v in caps.values()): errors.append("invalid-capability-state")
        if any(caps.get(k)=="UNKNOWN" for k in BASELINE): errors.append("unknown-baseline-capability")
    risk=d.get("risk")
    if risk not in {"HIGH","VERY_HIGH"}: errors.append("new-source-risk-must-be-high-or-higher")
    collision=d.get("collisionCheck")
    if not isinstance(collision,dict) or collision.get("passed") is not True or not collision.get("evidence"): errors.append("collision-check-not-proven")
    build=d.get("build")
    if not isinstance(build,dict) or build.get("passed") is not True or not build.get("evidence"): errors.append("build-not-proven")
    smoke=d.get("runtimeSmoke")
    if not isinstance(smoke,dict) or smoke.get("passed") is not True or not smoke.get("evidence"): errors.append("runtime-smoke-not-proven")
    evidence=d.get("evidence")
    if not isinstance(evidence,list) or not EVIDENCE.issubset(set(evidence)): errors.append("insufficient-high-risk-evidence")
    promo=d.get("promotion")
    if not isinstance(promo,dict) or promo.get("class")!="source_onboarding" or promo.get("ownerApprovalRequired") is not True or promo.get("authority")!="source-lab-approve-ready-sources.yml": errors.append("invalid-promotion-authority")
    if d.get("lifecycle","candidate") != "candidate": errors.append("onboarding-must-start-candidate")
    return errors


def main():
    p=argparse.ArgumentParser(); p.add_argument("path",type=Path); a=p.parse_args()
    d=json.loads(a.path.read_text(encoding="utf-8")); errors=validate(d)
    if errors:
        print(json.dumps({"decision":"HELD","errors":errors},indent=2)); raise SystemExit(1)
    print(json.dumps({"decision":"READY_FOR_APPROVAL","canonicalId":d["canonicalId"]},indent=2))

if __name__=="__main__": main()
