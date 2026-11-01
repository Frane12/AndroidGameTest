#!/usr/bin/env python3
"""V13.9.1: isolate external XOR success; freeze independent external 2026 CNFs.

Training/diagnostic input is NEVER included in prospective external sample.
Selection uses official verified labels and published CaDiCaL times only to
stratify sources. No DRNAS/Kissat timings are consulted for choosing inputs.
Every accepted external DIMACS is hashed before benchmarking.
"""
import argparse, collections, csv, hashlib, json, time
from pathlib import Path
import official_shortlong_select as source
import v137_fastpath as exact

PROTOCOL="DRNAS-V139-EXTERNAL-UNSEEN-FROZEN-20261101-v1"
SALT="DRNAS-V139-SOURCE-ID-ORDER-EXTERNAL-20261101"
TARGET=12
GROUPS=("SAT_fast","UNSAT_fast","SAT_mid","UNSAT_mid","SAT_hard","UNSAT_hard")
SOURCE_RUN=41239481557
LIMIT_ATTEMPTS=220
# Size preflight is deliberately bounded; this excludes many official 2026 CNFs.
source.RAW_CAP=96*1024**2
source.CNF_CAP=64*1024**2
source.VARIABLE_CAP=500_000
source.CLAUSE_CAP=1_000_000

def check(v,msg):
    if not v:raise RuntimeError(msg)
def load(path):return json.loads(Path(path).read_text())
def save(path,x):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def inspect(a):
    manifest=load(a.v138)
    known=[c for c in manifest["cases"] if c["id"].startswith("75429ff7ac")]
    check(len(known)==1,"The historical success ID must resolve to one real CNF")
    c=known[0]
    file=Path(a.out).with_suffix(".cnf")
    try:
        observed=source.download_and_features(c["id"],file)
        check(observed["sha256"]==c["sha256"] and
              observed["features"]==c["features"],"Downloaded source drift")
        raw=file.read_bytes()
        n,clauses=exact.read_dimacs(raw)
        eq=exact.xor_equations(n,clauses)
        check(eq is not None,"Historical external success no longer accepted as pure XOR")
        solved=exact.decide(raw)
        check(solved["status"]=="SAT" and solved["path"]=="affine_exact",
              "Historical SAT fast path not reproduced")
        check(exact.verify(n,clauses,solved),"SAT model invalid")
        incidence=collections.Counter()
        rhs=collections.Counter()
        for bits,b,support in eq:
            rhs[b]+=1
            for v in support:incidence[v]+=1
        pivots={};rank=0
        for bits,bit,support in eq:
            row=bits
            while row:
                j=row.bit_length()-1
                if j in pivots:row^=pivots[j]
                else:pivots[j]=row;rank+=1;break
        active=len(incidence)
        report={
          "purpose":"DESCRIPTIVE historical external success; previously seen; not holdout",
          "official_external_id":c["id"],"source_url":c["source_url"],
          "source_sha256":c["sha256"],"official_label":c["official_label"],
          "bytes":len(raw),"variables":n,"clauses":len(clauses),
          "all_clauses_3_literals":all(len(row)==3 for row in clauses),
          "four_clauses_per_xor_equation":len(clauses)==4*len(eq),
          "equations":len(eq),"xor_rhs_counts":dict(rhs),
          "active_variables":active,"unused_variables":n-active,
          "incidence_min":min(incidence.values()),"incidence_max":max(incidence.values()),
          "incidence_histogram":dict(collections.Counter(incidence.values())),
          "GF2_rank":rank,"GF2_nullity":n-rank,
          "verified_full_sat_model":True,"recognized_path":solved["path"],
          "hypothesis":"Full pure 3-XOR CNF admits polynomial GF(2) elimination; no claim why generic CDCL exceeded 20s",
          "known_v138_comparators":"V13.7 SAT ~0.08s, DRNAS/Kissat TIMEOUT at 20s per attempt",
          "limitations":"This formula and cohort were previously used in DRNAS development; not independent."
        }
        save(a.out,report)
        md=["# Historical external SAT formula — exact V13.7 explanation","",
           f"Official external ID: \`{c['id']}\` (from SAT Competition 2026).",
           f"SHA-256: \`{c['sha256']}\`. Known SAT status.",
           f"Variables: {n}; clauses: {len(clauses)}; exact three-variable XOR equations: {len(eq)}.",
           f"Every XOR equation is represented by exactly four complete forbidden-assignment clauses.",
           f"GF(2) rank: {rank}; nullity: {n-rank}; active variables: {active}.",
           f"Verified full SAT assignment against every DIMACS clause: **YES**.",
           f"Structural explanation: V13.7 recognizes the entire CNF as 3-XOR and uses GF(2) elimination; this is a known polynomial-time specialization.",
           "No proof of why the CDCL solvers did not finish in 20 seconds without CDCL trace analysis.",
           "This diagnosis is retrospective; it is not counted in fresh holdout results."]
        Path(a.md).write_text("\n".join(md)+"\n")
        print("V139_HISTORICAL_XOR_INSPECT_PASS",json.dumps(report,sort_keys=True),flush=True)
    finally:file.unlink(missing_ok=True)

def freeze(a):
    ids=set();shas=set();sources=[]
    for p in (a.v131,a.mini,a.v100,a.v132,a.v138):
        doc=load(p)
        check(isinstance(doc["cases"],list),"Known-source manifest requires case list: "+p)
        for case in doc["cases"]:
            ids.add(case["id"])
            shas.add(case["sha256"])
        sources.append({"source":p,"sha256":sha(p),"n":len(doc["cases"])})
    check(len(ids)>=132,"Historical exclusion set surprisingly small")
    check(len(shas)>=132,"Historical SHA exclusion set surprisingly small")
    official=list(csv.DictReader(Path(a.scores).open(encoding="utf-8",newline="")))
    baseline=[r for r in official if r.get("solverid")=="biere_cadical3[main]"
              and r.get("status") in ("sat-verified","unsat-verified")]
    check(len(baseline)>=200,"Wrong pinned 2026 scoring archive")
    pools={g:[] for g in GROUPS}
    for r in baseline:
        ident=r["instanceid"]
        if ident in ids or ident in source.EXCLUDED:continue
        sec=float(r["runtime"])
        label="SAT" if r["status"]=="sat-verified" else "UNSAT"
        grade="fast" if sec<10 else "mid" if sec<180 else "hard"
        group=label+"_"+grade
        pools[group].append(r)
    for g in GROUPS:
        pools[g].sort(key=lambda x:hashlib.sha256(
          (SALT+"/"+g+"/"+x["instanceid"]).encode()).hexdigest())
    print("V139_PUBLIC_CANDIDATE_STRATA",{g:len(v) for g,v in pools.items()},flush=True)
    candidates={g:iter(pools[g]) for g in GROUPS}
    selected=[];attempts=[];seen=shas.copy()
    # Two rounds per stratum, then rotation to fill optional shortages.
    exhausted=set()
    while len(selected)<TARGET and len(attempts)<LIMIT_ATTEMPTS and len(exhausted)<len(GROUPS):
        for group in GROUPS:
            if len(selected)>=TARGET or len(attempts)>=LIMIT_ATTEMPTS:break
            if group in exhausted:continue
            try:r=next(candidates[group])
            except StopIteration:exhausted.add(group);continue
            ident=r["instanceid"]
            try:
                c=source.download_and_features(ident)
                check(c["sha256"] not in seen,"Historical SHA duplicate")
                seen.add(c["sha256"])
                c.update(cohort=group,official_label=group.split("_")[0],
                    published_baseline_s=float(r["runtime"]))
                selected.append(c)
                attempts.append({"id":ident,"cohort":group,"accepted":True})
                print("V139_ACCEPT",len(selected),group,ident,
                      c["cnf_bytes"],c["sha256"],flush=True)
            except Exception as e:
                attempts.append({"id":ident,"cohort":group,"accepted":False,
                                 "reason":str(e)[:180]})
                print("V139_REJECT",group,ident,str(e)[:145],flush=True)
    if len(selected)!=TARGET:
        # Save a useful audit even if the official dataset is too large.
        save(a.out+".diagnostic.json",{
          "status":"incomplete_preflight","eligible_found":len(selected),
          "attempts":len(attempts),"sample":[{"id":c["id"],"cohort":c["cohort"],
                       "sha256":c["sha256"]} for c in selected],
          "rejects":attempts[-35:],"source_strata":{g:len(v) for g,v in pools.items()}
        })
        raise RuntimeError("Insufficient SHA-disjoint source-downloadable 2026 CNFs "
                           f"{len(selected)}/{TARGET} after {len(attempts)} attempts")
    check(not ({x["id"] for x in selected}&ids),"Duplicate prior ID")
    check(not ({x["sha256"] for x in selected}&shas),"Duplicate prior SHA")
    check(len({x["sha256"] for x in selected})==TARGET,"Duplicate new SHA")
    # Freeze order before any DRNAS/Kissat timings on these 12.
    selected.sort(key=lambda c:hashlib.sha256(
        (SALT+"/schedule/"+c["id"]).encode()).hexdigest())
    report={"protocol":PROTOCOL,"cases":selected,"n":TARGET,"shards":6,
       "repetitions":2,"solver_limit_s":20,"source_scores_git_blob":source.SCORES_GIT_BLOB,
       "source_scores_sha256":sha(a.scores),"public_score_verified_count":len(baseline),
       "excluded_history_count_ids":len(ids),"excluded_history_count_sha":len(shas),
       "excluded_source_manifests":sources,
       "selection_rule":"Fixed hash ordering and round-robin official SAT/UNSAT runtime strata. Never DRNAS/Kissat timings.",
       "attempted_downloads":len(attempts),"rejections":[r for r in attempts if not r["accepted"]],
       "strata":dict(collections.Counter(x["cohort"] for x in selected)),
       "warnings":[
        "These 2026 Main Track CNFs are SHA/ID disjoint from V131, official-mini, V100, V132 and V138 manifests.",
        "Disjointness covers known referenced cohorts only, not a guarantee against all past unindexed projects.",
        "Official results are used only to stratify and validate SAT/UNSAT answers; no DRNAS/Kissat timing used to pick examples.",
        "Small 12-CNF sample, limited filesize and download availability; no representation or official rank claim.",
        "All binaries, algorithm and selection protocol must remain frozen prior to solving these cases.",
        "20s time cap, 3GiB, one pinned core; not official 5000s competition conditions."
       ]}
    save(a.out,report)
    print("V139_FRESH_EXTERNAL_FREEZE_PASS",TARGET,
          json.dumps(report["strata"],sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="command",required=True)
    z=sub.add_parser("inspect")
    for name in ("v138","out","md"):z.add_argument("--"+name,required=True)
    z=sub.add_parser("freeze")
    for name in ("v131","mini","v100","v132","v138","scores","out"):
        z.add_argument("--"+name,required=True)
    a=p.parse_args()
    {"inspect":lambda:inspect(a),"freeze":lambda:freeze(a)}[a.command]()
if __name__=="__main__":main()
