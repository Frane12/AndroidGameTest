#!/usr/bin/env python3
"""R185 four independent GitHub runs: same-SHA cross-method audit and ranking.

Do not choose a 'winner' on censored all-TIMEOUT external originals.
Show per-run own clean baseline and ratios to avoid cross-machine clock bias.
Report synthetic development-control winner separately, not as broad SAT claim.
"""
import collections,json,pathlib,statistics
ROOT=pathlib.Path("r185/aggregate")
METHODS=("gf2_gate","gf2_short4","live_feedback","live_cooldown")
EXPECTED_RUNS={"gf2_gate":42216293355,"gf2_short4":42216297531,
               "live_feedback":42216302548,"live_cooldown":42216307152}
PROTO="DRNAS-R185-FOUR-INDEPENDENT-METHODS-FROZEN-SHA-v1"

def check(flag,msg):
    if not flag:raise RuntimeError("R185_AGGREGATE_FAIL "+str(msg))
def rd(file):return json.loads(pathlib.Path(file).read_text())
def main():
    reports={m:rd(ROOT/m/"report.json") for m in METHODS}
    manifests={r["case_manifest_sha256"] for r in reports.values()}
    check(len(manifests)==1,"four runs use different frozen original SHA cohorts")
    identities=None
    for m,r in reports.items():
        check(r["method"]==m and r["protocol"]==PROTO and
              r["status"]=="R185_METHOD_AUDIT_PASS","method run audit mismatch "+m)
        check(r["source_count"]==25 and r["attempts"]==100 and r["repetitions"]==2,
              "incomplete paired 100 trials "+m)
        pc={(z["sha256"],z["suite"]) for z in r["per_case"]}
        check(len(pc)==25,"per-case cardinality "+m)
        if identities is None:identities=pc
        else:check(pc==identities,"per-case source SHA mismatch "+m)
        trials=rd(ROOT/m/"all-trials.json")
        check(len(trials)==100,"raw trial cardinality mismatch "+m)
        observed=collections.defaultdict(list)
        for t in trials:
            check(t["sha256"] in {s for s,group in identities},"unknown source SHA "+m)
            check(t["method"]==m,"wrong algorithm labels "+m)
            observed[t["sha256"],t["arm"]].append(t)
        check(all(len(observed[s,arm])==2 and
                  {z["rep"] for z in observed[s,arm]}=={0,1}
                  for s,group in identities for arm in ("clean","method")),
                  "raw repeated SHA identity missing "+m)
    suites=("external_originals","medium_synthetic_controls","all_mixed")
    groups={}
    for suite in suites:
        table=[]
        for m in METHODS:
            v=reports[m]["groups"][suite]
            table.append({"method":m,
              "cases":v["cases"],"solved_clean_repetitions":v["solved_repetitions"]["clean"],
              "solved_method_repetitions":v["solved_repetitions"]["method"],
              "clean_PAR2_s":v["clean_PAR2_s"],
              "method_PAR2_s":v["method_PAR2_s"],
              "speed_ratio_own_clean_over_method":v["speed_ratio_clean_over_method"],
              "outcomes_method":v["outcomes"]["method"]})
        ranks=sorted(table,key=lambda x:(
            -x["solved_method_repetitions"],x["method_PAR2_s"],
            -x["speed_ratio_own_clean_over_method"]))
        top=ranks[0]
        tie=all(x["solved_method_repetitions"]==top["solved_method_repetitions"]
                and x["method_PAR2_s"]==top["method_PAR2_s"] for x in ranks)
        all_censored=all(x["solved_method_repetitions"]==0
                         and x["solved_clean_repetitions"]==0 for x in table)
        groups[suite]={"table":table,
            "winner_method":None if all_censored or tie else top["method"],
            "no_measurable_winner":all_censored or tie,
            "censored_all":all_censored,
            "ranking":[x["method"] for x in ranks]}
    # Keep rank on synthetic controls separate; reference identities have
    # appeared in R179 and R182 so cannot claim blind transfer.
    out={"protocol":"DRNAS-R185-FOUR-EXECUTIONS-FINAL-v1",
        "status":"R185_AGGREGATE_PASS","runs":EXPECTED_RUNS,
        "methods":list(METHODS),"same_source_manifest_sha256":next(iter(manifests)),
        "external_originals_already_used_in_R183_R184":True,
        "synthetic_controls_seen_in_R179_R182":True,
        "not_blind":True,"no_general_SAT_winner_claim":True,
        "fairness":"each method compared to clean CaDiCaL on its OWN same-SHA runner and cap",
        "groups":groups}
    ROOT.mkdir(parents=True,exist_ok=True)
    (ROOT/"final.json").write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R185 — four distinct logical methods, complete same-SHA audit\n\n")
        f.write("All four runs: **25 frozen CNFs each** (12 external previously seen in R183/R184, "
                "13 synthetic R179 development-only controls), 2 paired repeats, "
                "25-second wall cap. Each run carries a clean CaDiCaL control. "
                "Not a general SAT ranking or a new blind cohort.\n\n")
        for key,title in (("external_originals","External GBD originals"),
            ("medium_synthetic_controls","Known medium synthetic controls"),
            ("all_mixed","All cases (mixed distributions; not a world ranking)")):
            info=groups[key]
            f.write("## "+title+"\n\n")
            f.write("| Method | Solved attempts | Own-clean PAR2 s | Method PAR2 s | Own-clean speed ratio |\n")
            f.write("|---|---:|---:|---:|---:|\n")
            for v in info["table"]:
                f.write(f"| {v['method']} | {v['solved_method_repetitions']} | "
                    f"{v['clean_PAR2_s']} | {v['method_PAR2_s']} | "
                    f"{v['speed_ratio_own_clean_over_method']}x |\n")
            f.write("\n")
            if info["no_measurable_winner"]:
                f.write("**No measured winner**: all solvers unresolved or tied at the cap.\n\n")
            else:f.write(f"**Best on this cohort:** {info['winner_method']} "
                         "(paired measured PAR2; still needs independent replication).\n\n")
        f.write("Source-certified XOR contradictions and SAT models checked, "
                "but CaDiCaL UNSAT conclusions without source GF2 trace do not "
                "have independent LRAT certificates.\n")
    print("R185_AGGREGATE_FINAL",json.dumps({
        "runs":EXPECTED_RUNS,"groups":{k:{"winner":v["winner_method"],
           "censored":v["censored_all"],"ranking":v["ranking"],
           "results":v["table"]} for k,v in groups.items()}},sort_keys=True),flush=True)

if __name__=="__main__":main()
