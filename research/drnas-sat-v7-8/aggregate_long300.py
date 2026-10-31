#!/usr/bin/env python3
"""DRNAS SAT V7.8: independently combine all frozen SATLIB and Competition
2025 holdout shards, preserve source checks, raw paired measurements and
observational (not fitted) Benefit Predictor feature/label table.
"""
import argparse,csv,json,statistics
from pathlib import Path
from benchmark_long300 import FIELDS,METHODS,summarize

INTS={"repeat","hints","first_budget","stage1","second_budget","stage2","extended",
      "resumed","observed","short3","short5","short8","sum_len","variables",
      "clauses","selected","proposed","header_eligible","header_variables","header_clauses"}
FLOATS={"wall_s","native_s","short_fraction","probe_us","extension_us",
        "resume_us","preflight_us","mean_hint_margin","strong_fraction",
        "ternary_fraction","cutoff_s"}

def read_shards(root,pattern,count):
    paths=sorted(Path(root).glob(pattern))
    if len(paths)!=count:
        raise RuntimeError(f"{pattern}: expected {count} frozen shards, got {len(paths)}")
    rows=[];source_files=set()
    for path in paths:
        with path.open(encoding="utf8",newline="") as f:
            items=list(csv.DictReader(f))
        if not items:raise RuntimeError("Empty results "+str(path))
        for x in items:
            key=x["case"]
            if key in source_files and (key,path)==(None,None):
                raise RuntimeError("Never reached")
            row={}
            for col in FIELDS:
                v=x.get(col)
                if col in INTS:v=int(v) if v not in ("",None) else None
                elif col in FLOATS:v=float(v) if v not in ("",None) else None
                row[col]=v
            rows.append(row)
    names={}
    for path in paths:
        with path.open(encoding="utf8",newline="") as f:
            for row in csv.DictReader(f):
                k=row["case"]
                if k in names and names[k]!=str(path):
                    raise RuntimeError("Duplicate original CNF across shards: "+k)
                names[k]=str(path)
    return rows

def output_dataset(rows,reps,cutoff,dest):
    dest=Path(dest)
    dest.mkdir(parents=True,exist_ok=True)
    info=summarize(rows,reps,cutoff)
    info["measurement_rows"]=len(rows)
    eligible_rows=[r for r in rows if r["header_eligible"] == 1]
    info["eligible_header_count"]=len(set(r["case"] for r in eligible_rows))
    info["eligible_only"]=summarize(eligible_rows,reps,cutoff) if eligible_rows else None
    if len(rows)!=info["n_instances"]*reps*len(METHODS):
        raise RuntimeError("Incomplete paired raw data")
    (dest/"summary.json").write_text(json.dumps(info,indent=2)+"\n",encoding="utf8")
    with (dest/"all_raw.csv").open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    by={}
    for r in rows:
        by.setdefault(r["case"],{}).setdefault(r["method"],[]).append(r)
    # Labels are obtained *after* evaluating the trial. NEVER use this
    # file as a prospective test of a new predictor fitted to this data.
    diag=[]
    def score(trials):
        return statistics.median(2*cutoff if x["answer"]=="TIMEOUT"
                                 else x["wall_s"] for x in trials)
    for name,modes in sorted(by.items()):
        g=modes["fastpath_guided"]
        p=modes["fastpath_plain"]
        base=modes["plain"]
        # A censored formula may timeout under ALL modes; its native
        # feature fields are unavailable. Preserve the row as unknown,
        # never infer a false "not selected" label from absent telemetry.
        features=next((x for x in g if x["selected"] is not None),None)
        def med(field):
            values=[x[field] for x in g if x[field] is not None]
            return statistics.median(values) if values else None
        diag.append({
            "case":name,"family":g[0]["family"],"answer":g[0]["known_answer"],
            "vars":features["variables"] if features else None,
            "clauses":features["clauses"] if features else None,
            "fastpath_eligible":g[0]["header_eligible"],
            "mean_hint_margin":features["mean_hint_margin"] if features else None,
            "strong_fraction":features["strong_fraction"] if features else None,
            "ternary_fraction":features["ternary_fraction"] if features else None,
            "proposed_hints":features["proposed"] if features else None,
            "preflight_us_median":med("preflight_us"),
            "clause_offer_count_median":med("observed"),
            "short5_fraction_median":med("short_fraction"),
            "did_extend":int(any(x["extended"] for x in g)),
            "plain_s":score(base),"fastpath_plain_s":score(p),
            "fastpath_guided_s":score(g),
            "guided_benefit_over_matched_s":score(p)-score(g),
            "guided_speed_ratio_matched":score(p)/max(score(g),1e-12),
        })
    if diag:
        with (dest/"benefit_telemetry_observational.csv").open("w",newline="",encoding="utf8") as f:
            w=csv.DictWriter(f,fieldnames=list(diag[0]));w.writeheader();w.writerows(diag)
    return info

def write_report(results,dest):
    lines=[
      "# DRNAS SAT V7.8 — Fast Path and Benefit Predictor telemetry",
      "",
      "Original competition holdout sources were SHA256-authenticated and "
      "selected before the previous V7.8 test. This is a longer-cutoff "
      "replication, not an independent new holdout. Timeouts count in PAR-2.",
      "",
      "## Algorithm",
      "Static header-only gate: variables >= 180, clauses >= 800, "
      "and 3.9 <= clauses/variables <= 4.4. Ineligible cases call untouched "
      "CaDiCaL. Eligible cases run V7.7 quality gating, with matching "
      "unhinted and random-sign controls paying the same feature-pass cost.",
      "",
      "## Long-cutoff dataset results",
    ]
    for name,info in results.items():
        lines+=["",f"### {name}: {info['n_instances']} distinct formulas",
                 f"Original solver: {info['unmodified_solver']}. "
                 f"{info['repetitions']} repeats, {info['cutoff_s']}s cutoff. "
                 f"{info['measurement_rows']} raw measurements.",
                 "",
                 "| Method | PAR2 time sum (s) | Ratio vs plain | Solved attempts | Gated CNFs |",
                 "|---|---:|---:|---:|---:|"]
        for mode in METHODS:
            m=info["methods"][mode]
            lines.append(f"| {mode} | {m['PAR2_sum_case_medians_s']:.4f} | "
                 f"{m['speed_ratio_plain_over_method']:.4f}x | "
                 f"{m['solved_runs']}/{m['total_runs']} | "
                 f"{m['gated_instances']} |")
        if info["eligible_only"]:
            e=info["eligible_only"]
            lines += ["",f"### Header-eligible ONLY: {info['eligible_header_count']} formulas",
                "", "| Method | PAR2 (s) | Baseline/method | Solved |",
                "|---|---:|---:|---:|"]
            for method in METHODS:
                em=e["methods"][method]
                lines.append(f"| {method} | {em['PAR2_sum_case_medians_s']:.4f} | "
                             f"{em['speed_ratio_plain_over_method']:.4f}x | "
                             f"{em['solved_runs']}/{em['total_runs']} |")
            c=e["contrasts"]["fastpath_guided_vs_fastpath_plain"]
            lines.append(f"Eligible-only guided/plain ratio: {c['ratio_control_over_method']:.4f}x "
                         f"95% bootstrap {c['paired_bootstrap_95pct']}; "
                         f"faster/slower: {c['faster_instances']}/{c['slower_instances']}")
        else:
            lines += ["", "No header-eligible formulas; no selective-performance claim."]
        lines+=["", "Matched-policy contrasts (ratio >1 favors first method; "
                  "95% bootstrap including 1 is inconclusive):"]
        for key,c in info["contrasts"].items():
            lo,hi=c["paired_bootstrap_95pct"]
            lines.append(f"- {key}: {c['ratio_control_over_method']:.4f}x "
                     f"[{lo:.4f}, {hi:.4f}], "
                     f"{c['faster_instances']} faster / "
                     f"{c['slower_instances']} slower instances")
        lines+=["", "Note: this corpus must not be reused as an independent "
                      "holdout for a predictor subsequently fitted using its "
                      "benefit telemetry."]
    lines+=["","## Interpretation and limitations",
         "- Timing is measured in original subprocess wall clock, including "
         "startup and CNF read; native microseconds exclude original CNF read.",
         "- Source class labels checked on every solved result, and SAT models "
         "validated independently in native code.",
         "- Some SAT Competition 2025 families may be censored by the 12s cutoff; "
         "always inspect solved counts and PAR2 before making acceleration claims.",
         "- The learned-clause-length callback is a proxy, not LBD or proven clause quality.",
         "- Telemetry is exploratory and contains counterfactual labels computed "
         "from matched runs; it is NOT an independently evaluated predictor.",
         "- Method names / decision branches are frozen in source, not selected "
         "using performance results."]
    (Path(dest)/"research_report.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    print("\n".join(lines),flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--root",required=True)
    a.add_argument("--out",required=True)
    x=a.parse_args()
    out=Path(x.out);out.mkdir(parents=True,exist_ok=True)
    specs={
       "competition2025_long300":("drnas-v78-long300-competition-shard*-results/v78_results/raw.csv",11,2,300)
    }
    result={}
    for name,(pattern,shards,reps,cutoff) in specs.items():
        rows=read_shards(x.root,pattern,shards)
        result[name]=output_dataset(rows,reps,cutoff,out/name)
    write_report(result,out)
