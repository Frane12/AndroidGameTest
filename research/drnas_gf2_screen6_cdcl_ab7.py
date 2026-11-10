#!/usr/bin/env python3
"""GF2-SCREEN6-CDCL-AB7: source-frozen E2E SAT test of verified strict-short XOR.

Diagnostic selection is explicitly NON-BLIND: SHA selected after SCREEN6 positive
math screening. Three independent repetitions, one logical CPU per solver,
7 paired configurations, 12s E2E cap, 21 trials. Real CaDiCaL IPASIR-UP.
Every derived row is replayed from original-CNF-complete XOR equations before
passing native C++. SAT models checked on ORIGINAL CNF. UNSAT no LRAT.
"""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, random, tempfile, time
import drnas_gf2_screen6 as sc
import drnas_gf2_cdcl_live5 as live
import drnas_equiv9_prospective_seed_holdout as e9
import r157_source_certified_xor as exporter

ROOT=pathlib.Path("mre_gf2_ab7")
DRIVER=live.DRIVER
PROTO="DRNAS-GF2-SCREEN6-CDCL-AB7-1SHA-7ARM-3REP-12S-ONECPU-v1"
SOURCE_SHA="358c1a50db28aab6824d572d9fb22ed5681afbf157d58d13db28d042a95e0bd2"
CAP=12.0
REPS=3
SHARDS=3
ARMS=("cadical_clean","cadical_orig72","cadical_pair64",
      "cadical_gauss24","cadical_mix","cadical_mix_shadow","kissat_orig")
MAX_SOURCE=100
PAIR_KEEP=64
GAUSS_KEEP=24
EXPECTED_SOURCE_EXACT_ROWS=635
EXPECTED_STRICT_PAIR=241
EXPECTED_STRICT_GAUSS=31

def need(flag,msg):
    if not flag:raise RuntimeError("GF2_AB7_FAIL_CLOSED "+str(msg))
def sha(path):return sc.sha(path)
def save(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def target():
    matches=[c for c in sc.cases() if c["sha256"]==SOURCE_SHA]
    need(len(matches)==1,"target frozen original SHA missing")
    return matches[0]
def fingerprints():
    return dict(
      code_sha=sha(__file__),
      screen6_sha=sha("research/drnas_gf2_screen6.py"),
      live5_sha=sha("research/drnas_gf2_cdcl_live5.py"),
      live5_cpp_sha=sha("research/drnas_gf2_cdcl_live5.cpp"),
      r157_sha=sha("research/r157_source_certified_xor.py"),
      pinned_native_binary_sha=sha(DRIVER),
      kissat_sha=sha(e9.KISSAT),
      historic_source_manifest_sha=sha("mre_gf2_s1/manifest.json"))

def rowtext(rows):
    return "".join(f"{len(vs)} {rhs} "+" ".join(map(str,vs))+"\n"
                   for vs,rhs in rows)

def build_input(case,folder):
    src=sc.gf.original_path(case)
    n,original=e9.x22.read_cnf(src)
    need(sha(src)==SOURCE_SHA,"original changed")
    raw,roots=sc.full_source_scan(original)
    need(len(raw)==EXPECTED_SOURCE_EXACT_ROWS and
         roots["complete_source_XOR_post_units"]==EXPECTED_SOURCE_EXACT_ROWS,
         "screen6 full-source exact parity roster drift")
    pair,triple=sc.pair_trip_screen(raw)
    gauss=sc.gaussian_screen(raw)
    need(pair["strict_shorter"]==EXPECTED_STRICT_PAIR and
         gauss["strict_shorter"]==EXPECTED_STRICT_GAUSS,
         "screen6 mathematical positive result changed")
    need(not pair["pair_enumeration_capped"] and not gauss["gauss_capped"],
         "proof-derived selection unexpectedly truncated")
    pair_proofs=[p for p in pair["proofs"] if p["strict_shorter_than_every_parent"]
                 and 2<=len(p["vars"])<=4][:PAIR_KEEP]
    gauss_proofs=[p for p in gauss["proofs"] if p["strict_shorter_than_every_parent"]
                  and 2<=len(p["vars"])<=4][:GAUSS_KEEP]
    need(len(pair_proofs)==PAIR_KEEP and len(gauss_proofs)==GAUSS_KEEP,
         "strict-short proof supply insufficient")
    for p in pair_proofs+gauss_proofs:sc.verify_candidate(p,raw)
    # Original control follows exactly the R157 LIVE5 reference route.
    src_tsv=pathlib.Path(folder)/"original-certified.tsv"
    srcproof=pathlib.Path(folder)/"original-evidence.json"
    exporter.extract(src,src_tsv,srcproof,max_rows=MAX_SOURCE)
    sourcecheck=live.independently_check_rows(src,original,src_tsv,srcproof)
    original_rows=[]
    for line in src_tsv.read_text().splitlines():
        k,rhs,*vs=map(int,line.split())
        need(k==len(vs) and (tuple(vs),rhs) in set(raw),
             "LIVE5 original row not in all CNF-certified root rows")
        original_rows.append((tuple(vs),rhs))
    need(sourcecheck["verified_rows"]==len(original_rows),"source rows mismatch")
    def transform(ps):
        return [(tuple(p["vars"]),p["rhs"]) for p in ps]
    pair_rows=transform(pair_proofs)
    gauss_rows=transform(gauss_proofs)
    unique=[];known=set()
    for val in original_rows+pair_rows+gauss_rows:
        if val not in known:unique.append(val);known.add(val)
    need(0<len(unique)<=300,"native XOR row budget")
    sets=dict(orig=original_rows,pair=pair_rows,gauss=gauss_rows,mix=unique,
              mix_shadow=unique)
    paths={}
    for name,rr in sets.items():
        p=pathlib.Path(folder)/(name+".tsv")
        p.write_text(rowtext(rr))
        # A second parse, independent of native C++, checks all passed rows.
        got=[]
        for line in p.read_text().splitlines():
            k,rhs,*vs=map(int,line.split())
            need(k==len(vs) and 2<=k<=6 and vs==sorted(set(vs)),
                 "native TSV format or source parity row bad")
            got.append((tuple(vs),rhs))
        need(got==rr,"native TSV roundtrip altered exact parity")
        paths[name]=p
    evidence=dict(source_sha=SOURCE_SHA,source_exact_roots=len(raw),
        pair_strict_found=pair["strict_shorter"],
        gaussian_strict_found=gauss["strict_shorter"],
        selected_source_rows=len(original_rows),
        selected_pair_rows=len(pair_rows),
        selected_gaussian_rows=len(gauss_rows),
        selected_mix_rows=len(unique),
        pair_provenance=pair_proofs,
        gaussian_provenance=gauss_proofs,
        row_sha256={name:hashlib.sha256(rowtext(rr).encode()).hexdigest()
                    for name,rr in sets.items()},
        screen6_root_hash=sc.digest(raw),
        parent_proof_type="independent original CNF parity blocks plus source units; exact GF2 parent replay",
        no_lrAT=True)
    return paths,evidence,original

def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    need(DRIVER.is_file(),"pinned CaDiCaL driver missing")
    case=target()
    with tempfile.TemporaryDirectory(dir=ROOT) as folder:
        paths,ev,original=build_input(case,folder)
        need(ev["selected_pair_rows"]==PAIR_KEEP and
             ev["selected_gaussian_rows"]==GAUSS_KEEP,
             "algebraic intervention rows absent")
    m=dict(protocol=PROTO,source_case=case,source_sha=SOURCE_SHA,source_count=1,
        trials=len(ARMS)*REPS,shards=SHARDS,reps=REPS,cap_s=CAP,arms=list(ARMS),
        one_logical_CPU_per_solver=True,source_sha_frozen=True,
        previously_screened_nonblind=True,screen6_source_selection_after_math_find=True,
        verify_original_SAT_witness=True,
        source_certified_XOR_parent_proofs=True,derived_parity_replay_required=True,
        independent_unsat_LRAT=False,UNSAT_only_crosssolver_agreement=True,
        native_mode_mapping={"cadical_orig72":"active",
           "cadical_pair64":"linear","cadical_gauss24":"linear",
           "cadical_mix":"linear_mixed","cadical_mix_shadow":"linear_shadow",
           "cadical_clean":"clean"},
        mix_shadow_matches_mix_source_rows=True,
        row_proof=ev,fingerprints=fingerprints())
    save(ROOT/"manifest.json",m);verify()
    print("GF2_AB7_FROZEN "+json.dumps(dict(SHA=SOURCE_SHA,source_rows=ev["selected_source_rows"],
        strict_pairs=ev["pair_strict_found"],strict_gauss=ev["gaussian_strict_found"],
        selected_pair=PAIR_KEEP,selected_gauss=GAUSS_KEEP,mixed=ev["selected_mix_rows"],
        trials=m["trials"],one_cpu=True,not_blind=True),sort_keys=True),flush=True)

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["source_case"]==target() and
         m["source_sha"]==SOURCE_SHA and m["arms"]==list(ARMS) and
         m["trials"]==len(ARMS)*REPS and m["cap_s"]==CAP and
         m["fingerprints"]==fingerprints(),"frozen source binary/protocol drift")
    return m

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    sc.selftest()
    case=target()
    with tempfile.TemporaryDirectory(dir=ROOT) as folder:
        paths,ev,original=build_input(case,folder)
        need(ev["selected_pair_rows"]==PAIR_KEEP and
             ev["selected_gaussian_rows"]==GAUSS_KEEP,
             "missing independently proven short parity")
        # Fail-closed parent tampering proof
        p=dict(ev["pair_provenance"][0]);p["rhs"]^=1
        raw,_=sc.full_source_scan(original)
        try:sc.verify_candidate(p,raw)
        except RuntimeError:pass
        else:raise RuntimeError("tampered pairxor proof not rejected")
    print("GF2_AB7_SELFTEST_PASS "+json.dumps(dict(
      exact_roots=ev["source_exact_roots"],parent_pair_short=ev["pair_strict_found"],
      parent_gauss_short=ev["gaussian_strict_found"],selected_pair=PAIR_KEEP,
      selected_gauss=GAUSS_KEEP,original_sha_verified=True,
      altered_provenance_rejected=True),sort_keys=True),flush=True)

def trial(case,rep,arm):
    need(arm in ARMS and 0<=rep<REPS,"invalid arm/rep")
    src=sc.gf.original_path(case)
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    started=time.perf_counter()
    parent_started=time.process_time()
    child_started=e9.x22.child_cpu()
    status="TIMEOUT";sat_verified=False;metrics={};rows_meta={}
    with tempfile.TemporaryDirectory(dir=ROOT) as folder:
        if arm in ("kissat_orig","cadical_clean"):
            n,original=e9.x22.read_cnf(src)
            selected_file=pathlib.Path(folder)/"empty.tsv"
            selected_file.write_text("")
        else:
            paths,rows_meta,original=build_input(case,folder)
            which={"cadical_orig72":"orig","cadical_pair64":"pair",
                   "cadical_gauss24":"gauss","cadical_mix":"mix",
                   "cadical_mix_shadow":"mix_shadow"}[arm]
            selected_file=paths[which]
            need(rows_meta==verify()["row_proof"],
                 "source-specific row selection/proof changed after freeze")
        prepass=time.perf_counter()-started
        available=CAP-prepass
        if available>.07:
            if arm=="kissat_orig":
                cmd=e9.command("kissat1",src,e9.seedpair(SOURCE_SHA,rep)[0])
            else:
                mode=verify()["native_mode_mapping"][arm]
                cmd=[DRIVER,mode,src,selected_file]
            status,sat_verified,metrics,_=live.run_child(cmd,original,available,cpu)
    e2e=time.perf_counter()-started
    if e2e>=CAP:
        status="TIMEOUT";sat_verified=False
    need(status!="SAT" or sat_verified,"unverified original SAT model")
    need(sha(src)==SOURCE_SHA,"source mutated during paired CDCL")
    expected=rows_meta.get("selected_source_rows",0) if arm=="cadical_orig72" else (
        PAIR_KEEP if arm=="cadical_pair64" else GAUSS_KEEP if arm=="cadical_gauss24"
        else rows_meta.get("selected_mix_rows",0) if arm in ("cadical_mix","cadical_mix_shadow")
        else 0)
    need(metrics.get("xor_rows",expected)==expected,
         "native solver got different number of source-certified XOR rows")
    return dict(protocol=PROTO,source_sha=SOURCE_SHA,arm=arm,rep=rep,
        cap_s=CAP,status=status,
        original_SHA_verified=True,source_CNFs_untouched=True,
        SAT_original_witness_verified=bool(sat_verified and status=="SAT"),
        UNSAT_independent_LRAT=False,logical_cpu=cpu,
        one_solver_child_max=True,
        wall_E2E_s=round(e2e,6),
        prep_E2E_s=round(prepass,6),
        parent_CPU_s=round(time.process_time()-parent_started,6),
        child_CPU_s=round(e9.x22.child_cpu()-child_started,6),
        independent_short_XOR_rows=expected,
        source_shortening_proof_sha=sc.digest(rows_meta) if rows_meta else None,
        native_live_metrics=metrics,
        timeout_telemetry_lower_bound=(status=="TIMEOUT"),
        timeout_telemetry_present=bool(status=="TIMEOUT" and
             metrics.get("telemetry_snapshots_seen",0)>0))

def shard(i):
    m=verify()
    need(0<=i<SHARDS,"invalid shard")
    case=m["source_case"]
    order=list(ARMS)
    random.Random(SOURCE_SHA+"|AB7|"+str(i)).shuffle(order)
    rs=[]
    for arm in order:
        rec=trial(case,i,arm)
        rec["shard"]=i
        rs.append(rec)
        save(ROOT/f"shard-{i}.json",rs)
        print("GF2_AB7_TRIAL "+json.dumps(rec,sort_keys=True),flush=True)
    need(len(rs)==len(ARMS),"incomplete paired shard")
    print("GF2_AB7_SHARD_PASS "+json.dumps(dict(shard=i,trial_count=len(rs))),flush=True)

def audit():
    m=verify()
    # Reverify SHA, full original CNF row evidence and every frozen parent proof.
    with tempfile.TemporaryDirectory(dir=ROOT) as folder:
        files,ev,_=build_input(m["source_case"],folder)
        need(ev==m["row_proof"],"final independent proof replay failed")
    all_rows=[]
    for i in range(SHARDS):
        path=ROOT/f"shard-{i}.json"
        need(path.is_file(),"missing shard artifact")
        r=json.loads(path.read_text())
        need(len(r)==len(ARMS) and
             {x["arm"] for x in r}==set(ARMS) and
             all(x["rep"]==i and x["shard"]==i and
                 x["source_sha"]==SOURCE_SHA and x["original_SHA_verified"] for x in r),
             "paired original source shard corrupted")
        all_rows+=r
    need(len(all_rows)==len(ARMS)*REPS and
         len({(x["arm"],x["rep"]) for x in all_rows})==len(all_rows),
         "duplicate/missing benchmark trials")
    for x in all_rows:
        if x["status"]=="SAT":need(x["SAT_original_witness_verified"],"SAT original not verified")
        if x["status"]=="TIMEOUT" and x["arm"] not in ("kissat_orig",):
            need(x["timeout_telemetry_present"],"missing flushed timeout telemetry")
    unsat_agreed=any(x["arm"]=="kissat_orig" and x["status"]=="UNSAT" for x in all_rows) and any(
        x["arm"]=="cadical_clean" and x["status"]=="UNSAT" for x in all_rows)
    need(len({x["status"] for x in all_rows if x["status"]!="TIMEOUT"})<=1,
         "SAT UNSAT contradiction on original SHA")
    def accepted(x):
        return x["status"]=="SAT" and x["SAT_original_witness_verified"] or x["status"]=="UNSAT" and unsat_agreed
    def par2(x):return x["wall_E2E_s"] if accepted(x) else CAP*2
    def score(rs):
        return dict(trials=len(rs),solved=sum(bool(accepted(x)) for x in rs),
            SAT_verified=sum(x["status"]=="SAT" for x in rs),
            UNSAT_agreed_no_LRAT=sum(x["status"]=="UNSAT" and unsat_agreed for x in rs),
            timeout=sum(x["status"]=="TIMEOUT" for x in rs),
            PAR2_s=round(sum(par2(x) for x in rs),6),
            E2E_wall_s=round(sum(x["wall_E2E_s"] for x in rs),6),
            CPU_total_s=round(sum(x["parent_CPU_s"]+x["child_CPU_s"] for x in rs),6),
            prep_s=round(sum(x["prep_E2E_s"] for x in rs),6),
            independently_proven_parity_rows=sum(x["independent_short_XOR_rows"] for x in rs),
            XOR_lemmas_emitted=sum(x["native_live_metrics"].get("clauses_emitted",0) for x in rs),
            XOR_lemmas_delivered=sum(x["native_live_metrics"].get("delivery_confirmed",0) for x in rs),
            shadow_candidates=sum(x["native_live_metrics"].get("shadow_candidates",0) for x in rs),
            ready_events=sum(x["native_live_metrics"].get("ready_events",0) for x in rs),
            native_callbacks=sum(x["native_live_metrics"].get("live_callbacks",0) for x in rs))
    scores={a:score([x for x in all_rows if x["arm"]==a]) for a in ARMS}
    ref=scores["cadical_clean"]["PAR2_s"]
    for a,v in scores.items():v["PAR2_speedup_vs_clean_x"]=round(ref/v["PAR2_s"],6)
    paired={}
    for arm in ARMS:
        if arm=="cadical_clean":continue
        diffs=[]
        for rep in range(REPS):
            a=next(x for x in all_rows if x["arm"]==arm and x["rep"]==rep)
            b=next(x for x in all_rows if x["arm"]=="cadical_clean" and x["rep"]==rep)
            diffs.append(par2(a)-par2(b))
        paired[arm]=dict(PAR2_gain_s=round(-sum(diffs),6),
            wins=sum(d<-.02 for d in diffs),
            losses=sum(d>.02 for d in diffs),
            ties=sum(abs(d)<=.02 for d in diffs),
            best_gain_s=round(min(diffs),6),
            worst_regression_s=round(max(diffs),6))
    report=dict(protocol=PROTO,original_SHA=SOURCE_SHA,not_blind=True,
        mathematical_target_selected_after_screen6=True,one_logical_CPU=True,
        original_input_unchanged=True,all_SAT_models_independently_verified=True,
        independent_XOR_parent_proof_replay=True,LRAT=False,
        unsat_reference_agreement=bool(unsat_agreed),
        source_proof_counts={k:m["row_proof"][k] for k in
            ("source_exact_roots","pair_strict_found","gaussian_strict_found",
             "selected_source_rows","selected_pair_rows","selected_gaussian_rows",
             "selected_mix_rows")},
        trials=len(all_rows),scores=scores,paired=paired,
        per_rep={str(i):{a:score([x for x in all_rows if x["rep"]==i and x["arm"]==a])
                          for a in ARMS} for i in range(REPS)})
    save(ROOT/"report.json",report)
    print("GF2_AB7_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    args=ap.parse_args()
    if args.action=="shard":shard(args.shard)
    else:globals()[args.action]()
    if args.action=="verify":print("GF2_AB7_VERIFY_PASS",flush=True)
