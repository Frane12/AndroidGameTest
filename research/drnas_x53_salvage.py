#!/usr/bin/env python3
"""Audit the completed X5.3 432-trial run without rerunning or editing evidence.

The previous report failed because RLIMIT_FSIZE=128MiB generated SIGXFSZ
(wrapper rc=153), across X52/X53 AND CaDiCaL. This script preserves each
raw original trial and explicitly censors such runs as PROOF_FILE_LIMIT.
All other process errors and wrong answers still fail the report.
"""
import collections,hashlib,json,pathlib,random,statistics

OLD=pathlib.Path("x53_previous")
ARMS=("X52_BASE","X53_BASE","X53_GLUE","X53_UTILITY","KISSAT","CADICAL")
CAP=8.0


def main():
    protocol=json.loads(pathlib.Path("x53_freeze/protocol.json").read_text())
    files=[]
    for shard in range(12):
        path=OLD/f"x53-shard-{shard}"
        manifest=json.loads((path/"report.json").read_text())
        rows=[json.loads(line) for line in (path/"trials.jsonl").read_text().splitlines()]
        assert len(rows)==36 and manifest["trials"]==36 and manifest["shard"]==shard
        assert manifest["manifest_sha256"]==protocol["original_manifest_sha256"]
        assert manifest["binary_sha256"]==protocol["binary_sha256"]
        files.extend(rows)
    expected={(sha,rep,arm) for sha in protocol["source_sha256"]
              for rep in range(2) for arm in ARMS}
    assert len(files)==432 and {(x["sha256"],x["rep"],x["arm"]) for x in files}==expected
    proof_limited=[]
    bad=[]
    for row in files:
        if row["status"]=="PROCESS_ERROR":
            if row["returncode"]==153 and row["proof_size_bytes"]==128*1024*1024:
                proof_limited.append({"source_id":row["source_id"],"arm":row["arm"],
                                      "rep":row["rep"],"proof_bytes":row["proof_size_bytes"]})
                row["status"]="PROOF_FILE_LIMIT"
                row["accepted"]=False
                row["PAR2_s"]=2*CAP
            else:bad.append(row)
        if row["status"]=="WRONG_SAT":bad.append(row)
    if bad:
        raise RuntimeError(f"Found {len(bad)} genuine unattributed process/correctness errors")
    grouped=collections.defaultdict(list)
    for row in files:grouped[(row["sha256"],row["rep"])].append(row)
    assert len(grouped)==72 and all({v["arm"] for v in a}==set(ARMS) for a in grouped.values())
    overall={}
    for arm in ARMS:
        rows=[r for r in files if r["arm"]==arm]
        metrics=("watch_entries","dead_watch_entries","blocker_hits","long_literal_checks",
                 "watch_moves","reason_uses","analysis_uses","deleted_unused",
                 "deleted_used","live_learnt","live_used","live_unused")
        totals={k:sum((r.get("x53") or r.get("last_progress") or {}).get(k,0)
                      for r in rows) for k in metrics}
        overall[arm]={
            "trials":len(rows),"solved":sum(bool(r["accepted"]) for r in rows),
            "sat_verified":sum(bool(r["accepted"]) and r["status"]=="SAT_VERIFIED" for r in rows),
            "unsat_certified":sum(bool(r["accepted"]) and r["status"]=="UNSAT_CERTIFIED" for r in rows),
            "PAR2_s":round(sum(r["PAR2_s"] for r in rows),6),
            "proof_size_limit":sum(r["status"]=="PROOF_FILE_LIMIT" for r in rows),
            "timeout":sum(r["status"]=="timeout" for r in rows),
            "unknown":sum(r["status"]=="UNKNOWN" for r in rows),
            "telemetry":totals,
        }
    diffs={}
    for candidate in ("X53_GLUE","X53_UTILITY"):
        per_source=collections.defaultdict(float)
        for (sha,rep),rows in grouped.items():
            by={r["arm"]:r for r in rows}
            per_source[sha]+=by[candidate]["PAR2_s"]-by["X53_BASE"]["PAR2_s"]
        vals=list(per_source.values());rng=random.Random(531113)
        bootstrap=sorted(sum(rng.choices(vals,k=len(vals))) for _ in range(5000))
        diffs[candidate]={"delta_PAR2_s":round(sum(vals),6),
                          "source_cluster_95":[round(bootstrap[125],6),round(bootstrap[4874],6)]}
    report={
        "status":"COMPLETE_WITH_PROOF_RESOURCE_CENSORING",
        "original_run":43399730112,"original_manifest_sha256":protocol["original_manifest_sha256"],
        "source_count":36,"trials":len(files),"limits":{
            "proof_bytes":128*1024*1024,"solve_seconds":CAP,
            "error":"SIGXFSZ/returncode 153 after exactly 128MiB of proof output",
            "interpretation":"Resource-limited; not a logical SAT/UNSAT error; never accepted",
        },
        "resource_limited_attempts":len(proof_limited),
        "proof_limited_trials":proof_limited,"overall":overall,
        "paired":diffs,"interpretation_caveat":
        "Retrospective size-selected original SAT2024 instances, not a new blind holdout. "
        "The X53 used metric counts initial asserting enqueue; it is NOT evidence of subsequent reuse. "
        "Real64? No: 36 originals × 2 repeats; proof checker overhead reported separately."
    }
    out=pathlib.Path("x53_salvage");out.mkdir(exist_ok=True)
    (out/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("X53_SALVAGED "+json.dumps({"solved":{a:overall[a]["solved"] for a in ARMS},
        "PAR2":{a:overall[a]["PAR2_s"] for a in ARMS},
        "resource_limited_attempts":len(proof_limited),
        "pair_effects":diffs},sort_keys=True),flush=True)

if __name__=="__main__":main()
