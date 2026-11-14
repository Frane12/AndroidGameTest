#!/usr/bin/env python3
"""Read-only, source-paired CF7 REAL100 verified leaderboard and interesting formulas.

No solver runs, no training, no promotion; consumes immutable artifacts from
GitHub Actions run 43613581688 and checks every source/arm pair.
"""
import collections, hashlib, json, pathlib

ROOT = pathlib.Path("leaderboard")
ARMS = ("CF7_B2L_32","CF6_BASE","CF5_BASE","CaDiCaL","Kissat")
CAP = 8.0
FOCUS = (
 "frb", "randxor", "miter", "break", "rphp", "ptn", "itc",
 "xor", "php", "scheduling", "multiplier", "circuit",
)
def main():
    manifest=json.loads(pathlib.Path("cf7/manifest.json").read_text())
    assert manifest["count"]==100 and manifest["cap_s"]==CAP
    assert tuple(manifest["arms"])==ARMS
    sources={s["id"]:s for s in manifest["sources"]}
    assert len(sources)==100 and len({s["sha256"] for s in sources.values()})==100
    by=collections.defaultdict(dict)
    for shard in range(10):
        d=pathlib.Path("downloaded")/("cf7-shard-"+str(shard))
        meta=json.loads((d/"meta.json").read_text())
        assert meta["index"]==shard and meta["trials"]==50
        rows=[json.loads(s) for s in (d/"trials.jsonl").read_text().splitlines() if s.strip()]
        assert len(rows)==50
        for row in rows:
            ident=row["id"]; arm=row["arm"]
            assert ident in sources and ident%10==shard
            assert arm in ARMS and arm not in by[ident]
            assert row["sha256"]==sources[ident]["sha256"]
            assert row["family"]==sources[ident]["normalized_name_family"]
            assert row["accepted"] == (bool(row["verified"]) and row["elapsed_e2e_s"]<=CAP)
            assert abs(row["PAR2_verified_s"]-(row["elapsed_e2e_s"] if row["accepted"] else 2*CAP))<0.00001
            if row["accepted"]: assert row["status"] in ("SAT_VERIFIED","UNSAT_CERTIFIED")
            by[ident][arm]=row
    assert len(by)==100 and all(set(rows)==set(ARMS) for rows in by.values())
    cases=[]
    for ident,rows in sorted(by.items()):
        accepted={a:r for a,r in rows.items() if r["accepted"]}
        assert len({r["status"] for r in accepted.values()})<=1, ("contradictory_result",ident)
        s=sources[ident]
        improvement=rows["CF5_BASE"]["PAR2_verified_s"]-rows["CF7_B2L_32"]["PAR2_verified_s"]
        best=min(accepted.items(),key=lambda x:x[1]["PAR2_verified_s"]) if accepted else None
        cases.append({
            "id":ident,"family":s["normalized_name_family"],"sha256":s["sha256"],
            "bytes":s.get("bytes"),"best_verified_arm":best[0] if best else None,
            "best_verified_s":best[1]["elapsed_e2e_s"] if best else None,
            "cf7_gain_vs_cf5_s":round(improvement,6),
            "interesting_family_match":any(k in s["normalized_name_family"].lower() for k in FOCUS),
            "arms":{a:{"status":r["status"],"accepted":r["accepted"],
                       "PAR2_verified_s":r["PAR2_verified_s"],
                       "elapsed_e2e_s":r["elapsed_e2e_s"]} for a,r in sorted(rows.items())}
        })
    table=[]
    for arm in ARMS:
        rs=[by[i][arm] for i in sorted(by)]
        table.append({"arm":arm,"PAR2_verified_s":round(sum(r["PAR2_verified_s"] for r in rs),5),
                      "verified":sum(bool(r["accepted"]) for r in rs),
                      "sat_verified":sum(r["accepted"] and r["status"]=="SAT_VERIFIED" for r in rs),
                      "unsat_certified":sum(r["accepted"] and r["status"]=="UNSAT_CERTIFIED" for r in rs)})
    table.sort(key=lambda x:x["PAR2_verified_s"])
    priorities=sorted(cases,key=lambda c:(not(c["cf7_gain_vs_cf5_s"]>0),
        not c["interesting_family_match"],-c["cf7_gain_vs_cf5_s"],c["id"]))
    ROOT.mkdir(exist_ok=True)
    report={"protocol":"REAL100-LEADERBOARD-READONLY-V1",
            "parent_run":43613581688,"source_count":100,"trial_count":500,
            "cap_s":CAP,"blind_holdout":False,
            "note":"Only CF5/CF6/CF7/Kissat/CaDiCaL were paired. Other builds must NOT be ranked here.",
            "arms_ranked":table,"cases":cases,"interesting_formula_ids":[p["id"] for p in priorities[:25]]}
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    lines=["# DRNAS REAL100 verified leaderboard","",
      "Source: GitHub Actions run 43613581688 (100 original SAT2024 formulas, 8s cap).",
      "This is not a blind holdout, and it does not rank LTM/X5/R153 builds.","",
      "| Arm | Verified | SAT | UNSAT | total PAR2 (s) |",
      "|---|---:|---:|---:|---:|"]
    for x in table:
        lines.append(f'| {x["arm"]} | {x["verified"]} | {x["sat_verified"]} | {x["unsat_certified"]} | {x["PAR2_verified_s"]:.5f} |')
    lines+=["","## Interesting actual SAT2024 formulas","",
             "| ID | Family | CF7 gain vs CF5 (PAR2 s) | Winner | Winner time (s) |",
             "|---:|---|---:|---|---:|"]
    for c in priorities[:25]:
        t= f'{c["best_verified_s"]:.4f}' if c["best_verified_s"] is not None else "unresolved"
        lines.append(f'| {c["id"]} | {c["family"]} | {c["cf7_gain_vs_cf5_s"]:+.4f} | {c["best_verified_arm"] or "none"} | {t} |')
    (ROOT/"README.md").write_text("\n".join(lines)+"\n")
    print("LEADERBOARD_FINAL "+json.dumps({"status":"COMPLETE","arms":table,
          "formula_count":len(cases),"trials":500,"top_ids":report["interesting_formula_ids"][:10]},sort_keys=True))

if __name__=="__main__":main()
