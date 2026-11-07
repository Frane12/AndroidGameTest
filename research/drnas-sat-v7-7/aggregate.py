#!/usr/bin/env python3
"""Join eight frozen independent V7.7 holdout shards. Reject duplicates.
Pilot is deliberately excluded. No formula selected by runtime outcome.
"""
import argparse,csv,json
from pathlib import Path
from benchmark import FIELDS,METHODS,report

INT_FIELDS={"repeat","phases","first_budget","stage1","second_budget","stage2",
            "extended","resumed","observed","short3","short5","short8",
            "sum_len","variables","clauses"}
FLOAT_FIELDS={"wall_s","native_s","short_fraction","probe_us","extension_us",
              "resume_us","cutoff_s"}

def main(root,out,reps,cutoff):
    root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    sources=sorted(root.glob("drnas-v77-shard*-results/v77_results/raw.csv"))
    if len(sources)!=8:
        raise RuntimeError(f"Expected EIGHT independent shards; got {len(sources)}")
    rows=[]
    ownership={}
    for path in sources:
        with path.open(newline="",encoding="utf8") as f:
            rs=list(csv.DictReader(f))
        if not rs:raise RuntimeError("Empty shard: "+str(path))
        for r in rs:
            name=r["case"]
            if name in ownership and ownership[name]!=str(path):
                raise RuntimeError("Duplicate CNF across shards: "+name)
            ownership[name]=str(path)
            typed={}
            for col in FIELDS:
                x=r.get(col)
                if col in INT_FIELDS:x=int(x) if x not in ("",None) else None
                elif col in FLOAT_FIELDS:x=float(x) if x not in ("",None) else None
                typed[col]=x
            rows.append(typed)
    s=report(rows,reps,cutoff)
    if len(rows)!=s["n_instances"]*len(METHODS)*reps:
        raise RuntimeError("Missing rows or incomplete paired benchmark")
    s["combined_shards"]=8
    s["raw_measurements"]=len(rows)
    (out/"summary.json").write_text(json.dumps(s,indent=2)+"\n",encoding="utf8")
    with (out/"all_raw.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        w.writeheader();w.writerows(rows)
    lines=[
        "# DRNAS SAT V7.7 — prospective SHA256 verified SATLIB results",
        "",
        f"**{s['n_instances']} distinct original external CNFs**, "
        f"two repetitions, eight independent holdout shards, "
        f"{s['raw_measurements']} measurement rows. "
        "Unmodified CaDiCaL 3.0.1, all timeouts retained in PAR-2.",
        "",
        "| Mode | PAR-2 total (s) | Speed ratio vs plain | Solved runs | Extended cases |",
        "|---|---:|---:|---:|---:|"
    ]
    for mode in METHODS:
        m=s["modes"][mode]
        lines.append(f"| {mode} | {m['PAR2_sum_case_medians_s']:.4f} | "
                     f"{m['ratio_plain_over_method']:.4f}x | "
                     f"{m['solved_runs']}/{m['total_runs']} | "
                     f"{m['extended_cases']} |")
    lines+=["","## Matched comparisons",
            "Positive ratio >1 favors quality_guided; bootstrap 95% intervals "
            "including 1 are inconclusive."]
    for name,v in s["contrasts"].items():
        ci=v["paired_bootstrap_95pct"]
        lines.append(f"- **{name}**: **{v['ratio_control_over_proposed']:.4f}x**, "
                     f"95% [{ci[0]:.4f}, {ci[1]:.4f}], "
                     f"{v['faster_instances']} faster, {v['slower_instances']} slower CNFs")
    lines+=["","## Clause-size observer diagnostic"]
    for name in ("quality_plain","quality_guided","quality_random"):
        m=s["modes"][name]
        lines.append(f"- {name}: extended {m['extended_cases']}/{m['n']} CNFs; "
                     f"checkpoint median clause offers {m['median_export_offers_at_checkpoint']}; "
                     f"median short<=5 fraction {m['median_short5_fraction_at_checkpoint']}")
    lines+=["","## Limitations"]
    lines+=["- "+v for v in s["caveats"]]
    (out/"research_report.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    print("\n".join(lines),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--repeats",type=int,default=2)
    p.add_argument("--cutoff",type=float,default=12)
    a=p.parse_args();main(a.root,a.out,a.repeats,a.cutoff)
