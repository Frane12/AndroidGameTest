#!/usr/bin/env python3
"""Final strictly prospective original GBD polynomial family validation.

Requires ALL fifteen independently frozen single-formula shards. Pilot is excluded.
Every original input SHA256 has been locked before *any* solver timing.
Known SAT/UNSAT results verified for each successful run; timeouts remain
in PAR-2 with 2x cutoff penalty. Five repeats per mode. Paired bootstrap
over original distinct CNF instances (NOT over dependent repeat trials).
"""
import argparse,csv,json,statistics
from collections import defaultdict
from pathlib import Path
from benchmark import METHODS,FIELDS,summarize

INTS={"repeat","hints","first_budget","stage1","second_budget","stage2","extended",
      "resumed","observed","short3","short5","short8","sum_len","variables",
      "clauses","selected","proposed"}
FLOATS={"wall_s","native_s","short_fraction","probe_us","extension_us",
        "resume_us","preflight_us","mean_hint_margin","strong_fraction",
        "ternary_fraction","cutoff_s"}

def main(args):
    root=Path(args.root)
    shards=sorted(root.glob("drnas-polynomial-holdout-shard*-results/measurements/raw.csv"))
    if len(shards)!=15:
        raise RuntimeError(f"Require 15 independent single-formula shards, got {len(shards)}")
    seen={}
    rows=[]
    for shard in shards:
        with shard.open(encoding="utf8",newline="") as f:
            raw=list(csv.DictReader(f))
        if not raw:raise RuntimeError("Empty shard "+str(shard))
        for r in raw:
            name=r["case"]
            if name in seen and seen[name]!=str(shard):
                raise RuntimeError("Cross-shard duplicate original GBD CNF "+name)
            seen[name]=str(shard)
            o={}
            for k in FIELDS:
                v=r.get(k)
                if k in INTS:v=int(v) if v not in ("",None) else None
                elif k in FLOATS:v=float(v) if v not in ("",None) else None
                o[k]=v
            rows.append(o)
    if len(seen)!=15:
        raise RuntimeError("Expected exactly 15 fresh independent holdout CNFs; got "+str(len(seen)))
    result=summarize(rows,5,15)
    if len(rows)!=15*5*len(METHODS):
        raise RuntimeError("Incomplete paired experimental records")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    result["frozen_original_count"]=15
    result["holdout_shards"]=len(shards)
    result["method_count"]=len(METHODS)
    result["measurement_rows"]=len(rows)
    result["ground_truth"]="GBD meta.db family=polynomial-multiplication; SHA256-pinned original CNFs"
    result["excluded_a_priori"]=["newpol27-4.cnf.xz","newpol29-4.cnf.xz","newpol31-4.cnf.xz"]
    (out/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    with (out/"all_raw.csv").open("w",encoding="utf8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerows(rows)

    by=defaultdict(lambda:defaultdict(list))
    families={}
    for r in rows:
        by[r["case"]][r["method"]].append(r)
        families[r["case"]]=r["family"]
    def score(rows):
        return statistics.median([2*15 if x["answer"]=="TIMEOUT" else x["wall_s"] for x in rows])
    per_case=[]
    for name,modes in sorted(by.items()):
        plain=score(modes["plain"])
        guided=score(modes["quality_guided"])
        matched=score(modes["quality_plain"])
        random=score(modes["quality_random"])
        unit=dict(name=name,family=families[name],answer=modes["plain"][0]["known_answer"],
          plain_par2_s=plain,quality_guided_par2_s=guided,
          quality_plain_par2_s=matched,quality_random_par2_s=random,
          ratio_plain_over_quality_guided=plain/max(guided,1e-10),
          ratio_matched_over_quality_guided=matched/max(guided,1e-10),
          timed_out_plain=sum(r["answer"]=="TIMEOUT" for r in modes["plain"]),
          timed_out_quality_guided=sum(r["answer"]=="TIMEOUT" for r in modes["quality_guided"]))
        per_case.append(unit)
    with (out/"per_formula.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(per_case[0]));w.writeheader();w.writerows(per_case)

    lines=[
        "# DRNAS SAT — Independent polynomial multiplication family validation",
        "",
        "**Original external benchmark instances:** 15 holdout CNFs from Global Benchmark "
        "Database, SHA256 frozen BEFORE solver timing; 2 pilot CNFs excluded, "
        "3 additional >100MB originals excluded by predeclared size cap.",
        "",
        "**Protocol:** 5 repetitions per method, 15s wall-time cutoff per run, "
        "PAR-2 = 30s per timeout. Nine methods; 675 raw runs. "
        "Original CaDiCaL rel-3.0.1 library unchanged.",
        "",
        "| Method | PAR-2 sum of case medians, s (lower better) | Speed ratio CaDiCaL/method | Solved attempts |",
        "|---|---:|---:|---:|",
    ]
    for mode in METHODS:
        d=result["methods"][mode]
        lines.append(
          f"| {mode} | {d['PAR2_sum_case_medians_s']:.4f} | "
          f"{d['speed_ratio_plain_over_method']:.4f}x | "
          f"{d['solved_runs']}/{d['total_runs']} |")
    lines+=["", "## Direct matched controls",
        "A speed ratio >1 favors the first method; 95% paired bootstrap "
        "intervals including 1 do not establish reliable improvement."]
    for label,c in result["contrasts"].items():
        ci=c["paired_bootstrap_95pct"]
        lines.append(f"- {label}: {c['ratio_control_over_method']:.4f}x "
                     f"(95% bootstrap {ci[0]:.4f}–{ci[1]:.4f}); "
                     f"faster on {c['faster_instances']}, slower on {c['slower_instances']} CNFs")
    lines+=["","## Source family and outcome breakdown",
            "No post-hoc choice of a favorable parameter range."]
    for family,rr in result["families"].items():
        a=rr["plain"];b=rr["quality_guided"];c=rr["quality_plain"]
        lines.append(f"- {family}: {a['n_instances']} formulas; "
          f"plain {a['PAR2_sum_case_medians_s']:.3f}s; "
          f"guided {b['PAR2_sum_case_medians_s']:.3f}s; "
          f"matched-no-hint {c['PAR2_sum_case_medians_s']:.3f}s")
    lines+=["","## Case-level report"]
    for case in per_case:
        lines.append(f"- {case['name']} ({case['answer']}): "
          f"plain {case['plain_par2_s']:.4f}s; "
          f"guided {case['quality_guided_par2_s']:.4f}s; "
          f"matched {case['quality_plain_par2_s']:.4f}s; "
          f"ratio vs plain {case['ratio_plain_over_quality_guided']:.3f}x")
    lines+=["","## Limitations",
       "- All speed ratios here concern this set of 15 GBD-original instances, not general SAT or P vs NP.",
       "- GBD published labels provide correctness cross-check; successful SAT solutions checked clause-by-clause in C++. UNSAT results not externally certified by proof traces.",
       "- Pilot excluded from inference. The known previously favorable 2025 polynomial-multiplication instance is NOT in this holdout.",
       "- Original source compression and process startup included in wall-time but source-download/setup not.",
       "- Each solver method is run as a new process with original untouched source; timeout censored as PAR-2, no cherry-picking.",
       "- Paired bootstrap resamples original distinct instances and may be broad at sample size 15.",
       "- GBD family combines two authors, encodings and SAT/UNSAT statuses; compare with subfamilies, do not treat all as identical." ]
    (out/"research_report.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    print("\n".join(lines),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True);p.add_argument("--out",required=True)
    main(p.parse_args())
