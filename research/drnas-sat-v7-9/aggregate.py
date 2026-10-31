#!/usr/bin/env python3
"""V7.9: validate completeness of eight genuine original GBD holdout shards,
preserve 216 raw paired trials, compute PAR2 and paired bootstrap confidence
intervals. One shard = exactly one original instance. Pilot excluded.
"""
import argparse,csv,json
from pathlib import Path
from benchmark import FIELDS,METHODS,summarize

INT_FIELDS={"repeat","path","eligible","checkpoint","stage1","budget2",
            "stage2","candidate_count","observed","short5","resumed",
            "variables","clauses","timeout_probe_observed","timeout_probe_short5",
            "timeout_probe_candidates","cutoff_s"}
FLOAT_FIELDS={"wall_s","native_s","short_ratio","preflight_us","probe_us",
              "extend_us","resume_us"}

def main(args):
    expected=json.loads(Path(args.manifest).read_text())
    cases={x["name"]:x for x in expected["samples"]
            if x["group"]=="holdout" and
               x["source_validation"]["validation"]=="sha256_verified"}
    if len(cases)!=8:
        raise RuntimeError("Holdout frozen member count unexpectedly changed")
    root=Path(args.root)
    paths=sorted(root.glob("drnas-v79-holdout-shard*-results/measurements/raw.csv"))
    if len(paths)!=len(cases):
        raise RuntimeError(f"Expected exactly {len(cases)} shard files; got {len(paths)}")
    rows=[]
    seen=set()
    for path in paths:
        with path.open(encoding="utf8",newline="") as f:raw=list(csv.DictReader(f))
        if len(raw)!=3*len(METHODS):
            raise RuntimeError(f"Incomplete independent shard {path}: {len(raw)} expected {3*len(METHODS)}")
        names={r["case"] for r in raw}
        if len(names)!=1:
            raise RuntimeError("One shard contained multiple originals: "+str(names))
        key=next(iter(names))
        if key not in cases:raise RuntimeError("Unregistered original "+key)
        if key in seen:raise RuntimeError("Original duplicated across shards "+key)
        seen.add(key)
        for r in raw:
            parsed={}
            for col in FIELDS:
                v=r.get(col)
                if col in INT_FIELDS:
                    v=int(v) if v not in ("",None) else None
                elif col in FLOAT_FIELDS:
                    v=float(v) if v not in ("",None) else None
                parsed[col]=v
            if parsed["known_answer"]!=cases[key]["status"]:
                raise RuntimeError("Published label drift "+key)
            rows.append(parsed)
    if seen!=set(cases):
        raise RuntimeError("Frozen inputs missing: "+str(set(cases)-seen))
    report=summarize(rows,reps=3,timeout=15)
    if len(rows)!=216:raise RuntimeError("Incomplete 216-run original benchmark")
    report["source"]="Global Benchmark Database SHA256-pinned original CNFs"
    report["candidate_count"]=18
    report["originals_verified"]=9
    report["pilot_excluded"]=1
    report["originals_size_excluded"]=9
    report["original_holdout_verified"]=8
    report["measurement_rows"]=len(rows)
    report["prior_development_data"]="DRNAS V7.8 and previous GBD-15 benchmark; none of eight original source hashes overlap."
    report["proposed_rule"]="O(1) static bypass if n<180 or n>120000 or m<800 or m>500000. Otherwise unhinted checkpoint 1024 conflicts; choose 512-conflict hint extension only when observed >=64, short<=5 >=20, short share>=37%, hints >=64 and 25%-75% variable coverage. Otherwise split-only. Guard not a learned predictor."
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    with (out/"all_raw.csv").open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    readme=[
      "# DRNAS NeuroFlow V7.9 — Prospective 3-path selective CDCL test",
      "",
      "Eight original GBD holdout CNFs, SHA256 frozen before testing;",
      "one additional SAT pilot excluded; nine oversized original candidates",
      "excluded solely based on predeclared source-size caps. The surviving",
      "set is not class-balanced. Solver uses unmodified CaDiCaL 3.0.1.",
      "",
      "## Prospective benchmark",
      "Three repeats per method, original CNF unchanged, per-subprocess",
      "wall-time limit 15 seconds, PAR2 30 seconds for timeout,",
      "all nine alternatives evaluated in randomized matched order.",
      "Total 216 verified paired trials.",
      "",
      "| Method | PAR2 sum s (lower is better) | Plain/method | Solved | Guided path cases |",
      "|---|---:|---:|---:|---:|"
    ]
    for method in METHODS:
        m=report["methods"][method]
        readme.append(f"| {method} | {m['par2_sum_case_medians_s']:.4f} | "
           f"{m['speed_ratio_plain_over_method']:.4f}x | "
           f"{m['solved_attempts']}/{m['attempts']} | {m['path_guide_cases']} |")
    readme+=["","## Paired comparisons"]
    for key,v in report["contrasts"].items():
        lo,hi=v["paired_bootstrap_95pct"]
        readme.append(f"- {key}: {v['speed_ratio_control_over_method']:.4f}x "
           f"CI [{lo:.4f},{hi:.4f}], faster {v['faster_instances']}, slower {v['slower_instances']}.")
    readme+=["","## Per original CNF"]
    for c in report["per_case"]:
        readme.append(f"- {c['case']} ({c['status']}): plain {c['plain_par2_s']:.3f}s; "
             f"V7.9 {c['v79_selective_par2_s']:.3f}s; "
             f"matched plain {c['v79_matched_plain_par2_s']:.3f}s; "
             f"guided1024 {c['guided1024_par2_s']:.3f}s")
    readme+=["","## Interpretation limits",
        "- 15 second cap causes timeouts that reduce discrimination of methods on large CNFs.",
        "- Only eight holdout originals (six SAT, two UNSAT); insufficient for sweeping generalization.",
        "- The selector chooses a path after observation of the SAME in-flight solver. Cannot know counterfactual benefit of a different path.",
        "- Matched hint/no-hint/random modes use same checkpoint and budgets, allowing causal interpretation only of within-case controlled comparisons.",
        "- This experimental V7.9 is not evidence of P=NP, general polynomial-time SAT solving or global solver superiority.",
        "- GitHub scheduling variability and process runtime can affect small timing differences.",
        "- SAT positive models are checked; UNSAT outcomes rely on CaDiCaL and published GBD status labels; no independent UNSAT certificates.",
        "- The largest GBD cases may be bypassed intentionally by the predeclared n/m guard; monitor selection counts.",
        ""]
    (out/"research_report.md").write_text("\n".join(readme),encoding="utf8")
    print("\n".join(readme),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--manifest",required=True)
    main(p.parse_args())
