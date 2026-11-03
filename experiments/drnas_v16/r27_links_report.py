#!/usr/bin/env python3
"""R27 paired structural vs R26 timing report; never fits a selector."""
import argparse, json, statistics
from pathlib import Path
from collections import Counter

MODES = ("R26_native","R25_previous","DRNAS_V1531","CaDiCaL301","Kissat404")
CAP=10.0

def load(p):
    return json.loads(Path(p).read_text())

def median_par2(trials,mode):
    rows=[t for t in trials if t["mode"]==mode]
    if len(rows)!=2:
        raise RuntimeError(f"Missing two paired attempts for {mode}")
    v=[20.0 if t["status"]=="TIMEOUT" else float(t["seconds"]) for t in rows]
    return round(statistics.median(v),6)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--combined",required=True)
    p.add_argument("--historical",required=True)
    p.add_argument("--json",required=True)
    p.add_argument("--md",required=True)
    a=p.parse_args()
    manifest=load(Path(a.input)/"manifest.json")
    inputs={c["sha256"]:c for c in manifest["cases"]}
    indexed={}
    for shard in range(5):
        for r in load(Path(a.historical)/f"r26-shard-{shard}/rows.json"):
            spec=r["case"];key=spec["sha256"]
            assert key in inputs and inputs[key]["id"]==spec["id"]
            indexed[key]={m:median_par2(r["trials"],m) for m in MODES}
    analyzed={}
    for shard in range(4):
        folder=Path(a.combined)/f"r27-shard-{shard}"
        meta=load(folder/"metadata.json")
        assert meta["selected_count"]==len(meta["sha256"]), "Inconsistent shard"
        for sha in meta["sha256"]:
            row=load(folder/(sha[:20]+".json"))
            assert row["sha256"]==sha and sha not in analyzed
            assert row["gf2_boundary_projection"]["replay_valid"]
            analyzed[sha]=row
    assert len(analyzed)==17, f"Expected 17 mapping cases; got {len(analyzed)}"
    rows=[]
    for sha,row in analyzed.items():
        baseline=indexed[sha]
        x=dict(id=row["source_id"],family=row["source_family"],
               label=row["status_from_prior_manifest_not_detector"],sha256=sha,
               vars=row["variables_declared"],clauses=row["clauses_declared"],
               blocks=row["genuine_complete_xor_blocks"],
               xor_clause_pct=row["exact_xor_clause_share_pct"],
               interface_vars=row["interface_variables"],
               xor_vars=row["xor_variables"],
               interface_fraction=row["interface_fraction_of_xor_vars"],
               residual_touch=row["residual_clauses_touching_xor"],
               residual_mixed=row["residual_clauses_cross_xor_nonxor"],
               residual_binary_bridge=row["residual_binary_touch_xor"],
               components=row["xor_components"],
               sampled_rank=row["gf2_boundary_projection"]["independent_boundary_rows"],
               novel_short=row["gf2_boundary_projection"]["novel_short_relations"],
               contradiction_rows=row["gf2_boundary_projection"]["contradiction_rows"],
               sample_size=row["gf2_boundary_projection"]["sample_equations"],
               complete_projection=row["gf2_boundary_projection"]["projection_complete"],
               time_r26=baseline["R26_native"],time_kissat=baseline["Kissat404"],
               time_cadical=baseline["CaDiCaL301"],
               time_v1531=baseline["DRNAS_V1531"])
        rows.append(x)
    rows.sort(key=lambda x:(x["family"],x["id"]))
    poly=[r for r in rows if r["family"]=="polynomial_gbd_original"]
    assert len(poly)==10
    summary={"polynomial":{
        "n":len(poly),
        "xor_share_pct_range":[min(x["xor_clause_pct"] for x in poly),
                               max(x["xor_clause_pct"] for x in poly)],
        "interface_fraction_range":[min(x["interface_fraction"] for x in poly),
                                    max(x["interface_fraction"] for x in poly)],
        "total_boundary_variables":sum(x["interface_vars"] for x in poly),
        "total_mixed_residual_clauses":sum(x["residual_mixed"] for x in poly),
        "total_novel_short_relations_sampled":sum(x["novel_short"] for x in poly),
        "CaDiCaL_wins_over_Kissat":[x["id"] for x in poly
            if x["time_cadical"] < x["time_kissat"]],
        "all_three_timeout":[x["id"] for x in poly if
            x["time_cadical"]==20 and x["time_kissat"]==20 and x["time_r26"]==20]
    }}
    report=dict(protocol="DRNAS-R27-EXACT-XOR-RESIDUAL-INTERFACE-20261103-v1",
                original_manifest_sha256=__import__("hashlib").sha256(
                    (Path(a.input)/"manifest.json").read_bytes()).hexdigest(),
                caveats=["Observational, not learned strategy, not an NP breakthrough",
                         "R26 comparison uses historical identical SHA source CNFs",
                         "The five historical shards may run on different runner hardware",
                         "All individual solver comparisons are paired within each original shard",
                         "GF(2) rank is an exact lower bound for a deterministic subset when sample_size < total blocks",
                         "CNF co-occurrence does not establish a CDCL implication or cause",
                         "PAR2 timeout is 20 seconds at 10-second cap"],
                summary=summary,rows=rows)
    Path(a.json).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    lines=["# DRNAS R27 — authentic polynomial XOR↔residual boundary map",
           "17 SHA-locked original sources: 10 polynomial, 3 algebra control, 4 XOR controls.",
           "Exact full XOR clauses only; GF(2) projection independently certificate replayed.",
           "R26 paired timing imported from immutable original R26 53-CNF competition-style run.",
           "Timeout=20s PAR2 (10s attempt cap), NOT actual 20-second solve.",
           "**Static CNF topology, not the runtime CDCL reason/implication graph.**","",
           "## Authentic polynomial multiplication (10 formulas)",
           "| Original formula | XOR blocks | CNF in XOR % | Interface vars | Residual crossing | New short GF(2)* | Kissat PAR2 s | CaDiCaL PAR2 s |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in poly:
        lines.append(f'| {r["id"]} | {r["blocks"]} | {r["xor_clause_pct"]:.2f} | '
                     f'{r["interface_vars"]} | {r["residual_mixed"]} | {r["novel_short"]} | '
                     f'{r["time_kissat"]:.3f} | {r["time_cadical"]:.3f} |')
    lines+=["","*New short GF(2) is from sampled Gaussian elimination over exact blocks.",
            "For >2500 blocks the projection is a deterministic **subset**, NOT all implied relations.","",
            "## Highest-contrast formula (CaDiCaL fast / Kissat capped)"]
    for r in poly:
        if r["time_cadical"]<r["time_kissat"]:
            lines.append(f'**{r["id"]}**: CaDiCaL {r["time_cadical"]:.3f}s, '
                         f'Kissat {r["time_kissat"]:.3f}s PAR2; '
                         f'{r["blocks"]} exact XOR blocks, '
                         f'{r["interface_vars"]} cross-structure variables, '
                         f'{r["residual_mixed"]} residual clauses joining XOR and non-XOR variables.')
    lines+=["","## Original XOR controls (4 formulas)",
            "| Formula | XOR blocks | XOR clause share | Boundary vars | Kissat PAR2 s |",
            "|---|---:|---:|---:|---:|"]
    for r in rows:
        if r["family"] in ("xor_gf2_new","xor4_new","xor6_new"):
            lines.append(f'| {r["id"]} | {r["blocks"]} | {r["xor_clause_pct"]:.2f}% | '
                         f'{r["interface_vars"]} | {r["time_kissat"]:.4f} |')
    lines+=["","## Interpretation",
            "- Certified XOR blocks are logically valid equations over GF(2).",
            "- Interface variables appear inside the exact XOR blocks **and** elsewhere in CNF.",
            "- Crossing residual clauses couple those equations to non-XOR constraints, which a pure XOR linear solve does not discharge.",
            "- R27 observes topology; whether a special propagation or solver choice helps requires separate randomized paired A/B tests.",
            "- No filter was trained or adapted using these historical outcomes."]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)

if __name__=="__main__":
    main()
