#!/usr/bin/env python3
"""Whole-cohort SATLIB 225/250 benchmark audit. Screen provenance is not hidden."""
import csv,json,statistics,os,sys
from pathlib import Path
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path("combined-official")
ver="drnas-official-satlib-225-250-20261031-frozen-preselect-v1"
modes=("ca_plain","orig_v76","orig_v76_plain","v92_sparse","v92_structural")
groups=("uf225-960","uuf225-960","uf250-1065","uuf250-1065")
cases=[];rows=[];screens=[];errors=[];group_counts={}
for shard,group in enumerate(groups):
    folder=root/("shard-"+str(shard))
    m=json.loads((folder/"manifest.json").read_text())
    assert m["version"]==ver and m["group"]==group and tuple(m["modes"])==modes
    assert m["cap_s"]==4.0 and m["repeats"]==3
    sc=json.loads((folder/"screen.json").read_text())
    assert len(sc)==20 and all(x["family"]==group for x in sc)
    screens+=sc
    cs=m["cases"];cases+=cs
    group_counts[group]=len(cs)
    if cs:
        with (folder/"raw.csv").open(newline="") as f: rows+=list(csv.DictReader(f))
assert len(screens)==80
assert len(cases)==sum(group_counts.values())
assert len({c["original_sha256"] for c in cases})==len(cases)
assert len(rows)==len(cases)*3*len(modes)
cap=4.0
totals={mode:0.0 for mode in modes}
families={g:{mode:0.0 for mode in modes} for g in groups}
wins={m:0 for m in modes if m!="ca_plain"}
losses={m:0 for m in modes if m!="ca_plain"}
details=[]
lines=[
"# Official SATLIB SAT/UNSAT 225–250: frozen DRNAS comparative measurements","",
"The input is original SATLIB RND3SAT 225/250, not generated or transformed",
"apart from optional SATLIB '%' end marker removal. Original/archive SHA256 and",
"source member name are in manifest; archived originals preserved in artifacts.",
"",
"Protocol: four official archives, 20 SHA256-ranked distinct files per archive",
"screened with **CaDiCaL only** at 3 s. Eligible if 0.08–2.70s and truth",
"matches official SAT/UNSAT family. Up to six closest to 0.6s per family",
"are benchmarked with ALL frozen modes, three randomized-order repeats,",
"4-second cap each and 8s PAR2 penalty for a timeout.",
"Selection bias WARNING: filter uses the baseline performance, so aggregate",
"CaDiCaL/DRNAS speedup among selected cases is descriptive and can be biased.",
"This selection is **not** a full SAT Competition evaluation.",
"",
"## Screening counts",
"| Official archive | Screened | Medium eligible | Selected |",
"|---|---:|---:|---:|"]
for g in groups:
    eligible=sum(x["screen_eligible"] for x in screens if x["family"]==g)
    lines.append("| %s | 20 | %d | %d |"%(g,eligible,group_counts[g]))
lines+=["","## All selected official cases",
"| Official case | SAT/UNSAT | CaDiCaL | DRNAS v7.6 guided | v7.6 no hints | v9.2 sparse | v9.2 structural | Max speedup v. CaDiCaL |",
"|---|---|---:|---:|---:|---:|---:|---:|"]
for c in cases:
    sub=[r for r in rows if r["case"]==c["name"]]
    assert len(sub)==3*len(modes)
    assert {r["sha256"] for r in sub}=={c["sha256"]}
    med={}
    solved={}
    for mode in modes:
        item=[r for r in sub if r["mode"]==mode]
        assert len(item)==3 and {int(x["repeat"]) for x in item}=={0,1,2}
        for r in item:
            if r["status"]=="ERROR":errors.append(c["name"]+" "+mode+": ERROR")
            if r["status"] in ("SAT","UNSAT") and r["status"]!=c["truth"]:
                errors.append(c["name"]+" "+mode+": contradicts official "+c["truth"])
        solved[mode]=sum(r["status"] in ("SAT","UNSAT") for r in item)
        med[mode]=statistics.median(float(r["wall_s"]) if r["status"] in ("SAT","UNSAT") else cap*2 for r in item)
        totals[mode]+=med[mode];families[c["family"]][mode]+=med[mode]
    comps={mode:(med["ca_plain"]/med[mode]) if
           mode!="ca_plain" and solved[mode]==3 and solved["ca_plain"]==3 else None
           for mode in modes if mode!="ca_plain"}
    for mode,ratio in comps.items():
        if ratio is not None:
            wins[mode]+=ratio>1.25
            losses[mode]+=ratio<0.8
    best_mode=max((mode for mode in comps if comps[mode] is not None),
                  key=lambda mode:comps[mode],default=None)
    best_ratio=comps[best_mode] if best_mode else None
    lines.append("| %s | %s | "%(c["name"],c["truth"])+
       " | ".join("%.4fs (%d/3)"%(med[m],solved[m]) for m in modes)+
       " | "+("%.2fx (%s)"%(best_ratio,best_mode) if best_ratio is not None else "n/a")+" |")
    details.append(dict(case=c["name"],family=c["family"],sat=c["truth"],
        source_member=c["source_member"],original_sha256=c["original_sha256"],
        screen_time_s=c["screen_time_s"],median_PAR2=med,solved=solved,
        speedup_vs_cadical=comps,best_mode=best_mode,best_ratio=best_ratio))
lines+=["","## Aggregate over ALL selected cases, no exclusions",
"| Mode | Sum of median PAR2 (s; lower better) |",
"|---|---:|"]
for mode in modes:lines.append("| %s | %.5f |"%(mode,totals[mode]))
lines+=["","## Family-aggregated PAR2 (seconds)",
"| Archive | CaDiCaL | Guided v7.6 | No-hints v7.6 | Sparse v9.2 | Structural v9.2 |",
"|---|---:|---:|---:|---:|---:|"]
for group in groups:
    lines.append("| %s | "%group+" | ".join("%.3f"%families[group][mode] for mode in modes)+" |")
lines+=["","## Practical wins vs CaDiCaL (>1.25x) and losses (<0.8x)",
"| Mode | Wins | Losses |","|---|---:|---:|"]
for mode in wins:lines.append("| %s | %d | %d |"%(mode,wins[mode],losses[mode]))
eligible=[x for x in screens if x["screen_eligible"]]
best=sorted([dict(case=x["case"],ratio=x["best_ratio"],mode=x["best_mode"],
                  family=x["family"],truth=x["sat"]) for x in details
             if x["best_ratio"] is not None],key=lambda x:-x["ratio"])
lines+=["","## Strongest individual selected benchmark",
      json.dumps(best[:3],ensure_ascii=False),
      "Errors: "+("none detected" if not errors else str(errors)),
      "UNSAT claim is based on SATLIB's official family labels and agreement",
      "among these solvers; independently checked DRAT/LRAT proofs not collected.",
      "A few dozen 3-SAT cases cannot establish a world record or broad SAT performance."]
report="\n".join(lines)+"\n"
root.mkdir(exist_ok=True)
(root/"summary.md").write_text(report)
(root/"details.json").write_text(json.dumps(details,indent=2))
(root/"totals.json").write_text(json.dumps(totals,indent=2))
(root/"screen_all.json").write_text(json.dumps(screens,indent=2))
with (root/"all_raw.csv").open("w",newline="") as f:
    if rows:
        wr=csv.DictWriter(f,fieldnames=rows[0].keys())
        wr.writeheader();wr.writerows(rows)
with open(os.environ.get("GITHUB_STEP_SUMMARY",str(root/"actions.md")),"a") as f:f.write(report)
print(report,flush=True)
if errors:raise RuntimeError("Solver correctness failures; inspect raw")
