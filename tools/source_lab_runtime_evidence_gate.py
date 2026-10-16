#!/usr/bin/env python3
"""Verify exact Source Lab Keiyoushi runtime-closure disposition fail closed."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
HEX40 = re.compile(r"^[0-9a-f]{40}$")
class GateError(ValueError): pass

def verify(data, candidate, compatible, blocked):
    if not HEX40.fullmatch(candidate) or data.get("candidate") != candidate:
        raise GateError("runtime evidence disposition candidate mismatch")
    sources = data.get("sources")
    if not isinstance(sources, list): raise GateError("disposition sources missing")
    index = {s.get("canonicalId"): s for s in sources if isinstance(s, dict)}
    if (compatible | {blocked}) - set(index): raise GateError("expected source missing from disposition")
    for canonical in sorted(compatible):
        source = index[canonical]
        evidence = source.get("evidenceDisposition")
        if source.get("automationClass") != "REVIEWED_COMPATIBLE":
            raise GateError(f"{canonical}: runtime evidence not accepted")
        if not isinstance(evidence, dict) or evidence.get("candidate") != candidate or evidence.get("evidenceType") != "runtime-closure-execution":
            raise GateError(f"{canonical}: accepted evidence is not exact runtime-closure evidence")
    source = index[blocked]
    if source.get("automationClass") != "NEEDS_REVIEW" or source.get("evidenceDisposition") is not None:
        raise GateError(f"{blocked}: must remain fail-closed NEEDS_REVIEW")
    if data.get("state") != "hold" or data.get("blockingSourceCount", 0) < 1:
        raise GateError("runtime disposition must remain held")
    return {"schemaVersion":1,"candidate":candidate,"compatible":sorted(compatible),"infrastructureBlocked":[blocked],"state":"HELD","candidateFarmAllowed":False}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--disposition",type=Path,required=True); p.add_argument("--expected-candidate",required=True); p.add_argument("--compatible",action="append",default=[]); p.add_argument("--blocked",required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    try:
        data=json.loads(a.disposition.read_text()); result=verify(data,a.expected_candidate,set(a.compatible),a.blocked); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); print(json.dumps(result,indent=2,sort_keys=True)); return 0
    except (GateError,OSError,json.JSONDecodeError) as e: print(f"error: {e}"); return 1
if __name__ == "__main__": raise SystemExit(main())
