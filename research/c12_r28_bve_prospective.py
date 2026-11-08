#!/usr/bin/env python3
"""C12: original-SHA official2026 pilot; real E2E, not blind to all historical GitHub data.
Three policies: frozen source-only C11; true in-process C8I BVE gate; paid restart probe;
R28 certified GF2 front-end only (falls back to unmodified Kissat on mixed CNF).
Never alter the frozen V15.3.1 solver.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, io, json, os, pathlib, random, re, subprocess, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "experiments/drnas_v16"))
import r32p_real_satcomp26_benchmark as r32p
import r52_prospective_2026_toprefs as r52
import mre11b_prospective_benchmark as ref
import r195_native_cms_benchmark as cms

PROTO = "DRNAS-C12-2026-NEW8-7ARMS-2REPS-30S-E2E-v1"
SALT = "DRNAS-C12-OFFICIAL26-LOCK-20261109-PREREGISTERED-1"
OUT = pathlib.Path("c12_out")
SOURCE = pathlib.Path("c12_sources")
CAP = 30.0
REPS = 2
SHARDS = 4
TARGET = 8
ARMS = ("kissat","cadical","cadical_noelim","gate16","r28_kissat","c11_static","c12_hybrid","probe_router")
# Eight independent policies -> 128 measured attempts. Pilot is a paid restart.
assert len(ARMS) == 8
HISTORY = (pathlib.Path("prior_c9c/c9c_official/manifest.json"),
           pathlib.Path("prior_c10b/c10b_official/manifest.json"))
STATUS = {"sat-verified":"SAT","unsat-verified":"UNSAT"}
RULE = "200<=nvars<=1500 and density<=60 => cadical_noelim; else nvars<=400 or density>=200 or (nvars>=25000 and density<=2) => kissat; else cadical"
GATE_RE = re.compile(r"^C8I_GATE_DECISION candidates=16 early_successes=(\d+) disabled=([01]) conflicts=(\d+)$", re.M)

def need(ok,why):
    if not ok: raise RuntimeError("C12_FAIL_CLOSED "+str(why))

def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()

def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def save(p,data):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def prior():
    ids=set(); shas=set(); provenance={}
    for p in HISTORY:
        need(p.is_file(),"missing historical original-source manifest "+str(p))
        d=json.loads(p.read_text()); need(len(d["cases"])>=8,"empty historical source manifest")
        for x in d["cases"]:
            ids.add(x["gbd"]);shas.add(x["sha256"])
        provenance[str(p)]=digest(p)
    c8=pathlib.Path("prior_c8d/report.json")
    need(c8.is_file(),"missing 19-SHA C8D audit for exclusion")
    d=json.loads(c8.read_text())
    need(d["source_count"]==19,"C8D exclusion source count mismatch")
    for x in d["per_source"]:
        shas.add(x["sha256"])
        if x.get("gbd"): ids.add(x["gbd"])
    provenance[str(c8)]=digest(c8)
    return ids,shas,provenance

def freeze():
    SOURCE.mkdir(parents=True,exist_ok=True)
    index=r52.fetch_bytes(r52.URI,100000)
    original=[x.strip().rsplit("/",1)[-1] for x in index.decode().splitlines() if x.strip()]
    need(len(original)==400 and len(set(original))==400,"official SAT2026 index drift")
    scores=r52.fetch_bytes(r52.SCORES,32*1024*1024)
    statuses={x["instanceid"]:STATUS.get(x["status"]) for x in csv.DictReader(io.StringIO(scores.decode()))
              if x.get("solverid")=="biere_cadical3[main]"}
    need(len(statuses)==400,"official reference index incomplete")
    old_ids,old_sha,historical=prior()
    ranked=sorted((g for g in original if g not in old_ids),
                  key=lambda g:sha_bytes((SALT+"|"+g).encode()))
    r32p.CNF_LIMIT=45*1024*1024
    selected=[]; attempts=[]; count=collections.Counter()
    for g in ranked[:250]:
        if len(selected)==TARGET:break
        s=statuses.get(g)
        if s not in STATUS.values() or count[s]>=5: continue
        record={"gbd":g,"reference":s}
        try:
            raw,_=r32p.request_url("https://benchmark-database.de/file/"+g,
                                 30*1024*1024,seconds=25)
            plain,kind=r32p.decode(raw)
            need(len(plain)<=45*1024*1024,"CNF uncompressed bytes exceed cap")
            n,m=r32p.parse_dimacs_metadata(plain)
            need(0<n<=100000 and 0<m<=950000,"CNF size exceeds cap")
            h=sha_bytes(plain)
            need(h not in old_sha and h not in {x["sha256"] for x in selected},
                 "history SHA collision")
            p=SOURCE/(g+".cnf");p.write_bytes(plain)
            selected.append(dict(gbd=g,sha256=h,filename=p.name,status=s,
                 nvars=n,nclauses=m,bytes=len(plain),raw_sha256=sha_bytes(raw),compression=kind))
            count[s]+=1;record.update(decision="ACCEPT_SHA_ONLY",sha256=h)
        except Exception as e:
            record.update(decision="REJECT_PRETIMING",reason=(type(e).__name__+":"+str(e))[:180])
        attempts.append(record)
        print("C12_SOURCE_SCAN",json.dumps(record,sort_keys=True),flush=True)
    need(len(selected)==TARGET and count["SAT"]>=2 and count["UNSAT"]>=2,
         "frozen source quota failed; no solver run allowed")
    need(len({x["sha256"] for x in selected})==TARGET,"duplicate source SHA")
    data=dict(protocol=PROTO,salt=SALT,cases=selected,official_source=True,
              source_count=TARGET,status_counts=dict(count),historical_manifest_sha256=historical,
              index_sha256=sha_bytes(index),scores_sha256=sha_bytes(scores),
              prior_source_sets_disjoint=True,not_guaranteed_globally_unseen=True,
              source_selection_only_official_status_and_precommitted_resource_caps=True,
              source_freeze_before_any_timed_solver=True,attempts=attempts,
              frozen_policy=RULE,no_auto_promotion=True,unsat_LRAT_independent=False)
    save(SOURCE/"manifest.json",data)
    (SOURCE/"source.sha256").write_text("".join(x["sha256"]+"  "+x["filename"]+"\n" for x in selected))
    print("C12_SOURCE_FROZEN",json.dumps({ "count":len(selected),"status_counts":dict(count),
          "manifest_SHA256":digest(SOURCE/"manifest.json")},sort_keys=True),flush=True)

def cases():
    d=json.loads((SOURCE/"manifest.json").read_text())
    need(d["protocol"]==PROTO and d["salt"]==SALT and
         d["source_freeze_before_any_timed_solver"],"source manifest drift")
    old_ids,old_sha,historical=prior()
    need(d["historical_manifest_sha256"]==historical,"historical audit changed after source lock")
    need(len(d["cases"])==TARGET and len({x["sha256"] for x in d["cases"]})==TARGET,
         "source count or duplicate")
    for x in d["cases"]:
        need(x["gbd"] not in old_ids and x["sha256"] not in old_sha,"old source reused")
        p=SOURCE/x["filename"]
        need(p.is_file() and p.stat().st_size==x["bytes"] and digest(p)==x["sha256"],
             "original CNF mismatch")
    return d["cases"]

def backend(n,m):
    d=m/n
    if 200<=n<=1500 and d<=60:return "cadical_noelim"
    if n<=400 or d>=200 or (n>=25000 and d<=2):return "kissat"
    return "cadical"

def binary(name):
    return str(pathlib.Path({"kissat":"built/bin/kissat_4_0_4",
          "cadical":"c8c/bin/plain","cadical_noelim":"c8c/bin/plain",
          "gate16":"c8c/bin/instrumented","r28_kissat":"c12_bin/r28_gf2"}[name]).resolve())

def command(name,p):
    if name=="r28_kissat": return [binary(name),str(p),binary("kissat")]
    return [binary(name)]+(["--no-elim"] if name=="cadical_noelim" else [])+[str(p)]

def env_for(mode):
    env=os.environ.copy()
    for v in ("DRNAS_C8C_TRACE","DRNAS_C8C_SKIP_VARS","DRNAS_C8C_SKIP_ALL_BVE",
              "DRNAS_C8H_LEARNED_TRACE","DRNAS_C8H_MIN_CONFLICT",
              "DRNAS_C8I_EARLY_GATE16","DRNAS_C8I_GATE_TRACE"):env.pop(v,None)
    if mode=="gate16":
        env["DRNAS_C8I_EARLY_GATE16"]="1"
        env["DRNAS_C8I_GATE_TRACE"]="1"
    return env

def invoke(mode,p,timeout):
    if timeout<=0:return None, "", 0.0
    st=time.perf_counter()
    try:
        proc=subprocess.run(command(mode,p),timeout=timeout,capture_output=True,
              text=True,errors="replace",env=env_for(mode),check=False)
        return proc,(proc.stderr or ""),time.perf_counter()-st
    except subprocess.TimeoutExpired as e:
        raw=e.stderr
        err=raw.decode(errors="replace") if isinstance(raw,bytes) else (raw or "")
        return None,err,time.perf_counter()-st

def trial(x,arm,rep,pos,seed):
    p=(SOURCE/x["filename"]).resolve()
    need(digest(p)==x["sha256"],"CNF changed before execution")
    start=time.perf_counter(); route=arm; probe=None
    if arm=="c11_static":
        route=backend(x["nvars"],x["nclauses"])
    elif arm=="c12_hybrid":
        route=backend(x["nvars"],x["nclauses"])
        # An actual R28 pre-solver is tried ONLY within its pinned executable resource bounds.
        # Otherwise C8I's early gate is an in-process CaDiCaL intervention, not a portfolio switch.
        if x["nvars"]<=3000 and x["bytes"]<=12*1024*1024:
            route="r28_kissat"
        elif route=="cadical":
            route="gate16"
    elif arm=="probe_router":
        # A separate killed process: costly online diagnostic, NOT in-process continuation.
        pp,stderr,probe_wall=invoke("gate16",p,min(0.5,CAP))
        pm=GATE_RE.search(stderr)
        probe=dict(budget_s=0.5,wall_s=round(probe_wall,6),
             early_gate_observed=bool(pm),
             early_successes=int(pm.group(1)) if pm else None,
             restarted_after_probe=True)
        if pp is not None:
            state,model=ref.external_parse(pp)
            if state in ("SAT","UNSAT"):
                need(state==x["status"],"pilot contradicts official status")
                if state=="SAT":cms.verify_model(p,model)
                elapsed=time.perf_counter()-start
                if elapsed<=CAP:
                    return row(x,arm,rep,pos,seed,"pilot_solved",state,elapsed,probe,state=="SAT")
        # No imputed evidence: if gate wasn't observed, use frozen source-only C11.
        route=("cadical_noelim" if int(pm.group(1))==0 else "cadical") if pm else backend(x["nvars"],x["nclauses"])
    remaining=CAP-(time.perf_counter()-start)
    result,stderr,spent=invoke(route,p,remaining)
    elapsed=time.perf_counter()-start
    state="TIMEOUT";verified=False
    if result is not None:
        state,model=ref.external_parse(result)
        need(state in ("SAT","UNSAT","TIMEOUT","UNKNOWN"),"unknown solver status")
        if state=="SAT":
            cms.verify_model(p,model);verified=True
        if state in ("SAT","UNSAT"):
            need(state==x["status"],"solver contradicted published reference")
    if elapsed>CAP or state not in ("SAT","UNSAT"):state="TIMEOUT";verified=False
    return row(x,arm,rep,pos,seed,route,state,elapsed,probe,verified)

def row(x,arm,rep,pos,seed,route,state,elapsed,probe,verified):
    return dict(protocol=PROTO,gbd=x["gbd"],source_sha256=x["sha256"],
        source_kind="official2026_new_vs_indexed_history",arm=arm,backend=route,
        reference=x["status"],status=state,rep=rep,order_index=pos,order_seed=seed,
        actual_solver_seed_not_changed=True,source_original_SHA_verified=True,
        SAT_original_witness_verified=verified,
        UNSAT_independent_LRAT=False,UNSAT_published_agreement=state=="UNSAT",
        wall_s=round(elapsed,6),PAR2_s=round(elapsed if state in ("SAT","UNSAT") else 2*CAP,6),
        total_wall_includes_header_and_pilot=True,probe=probe,
        runner=os.environ.get("RUNNER_NAME","unknown"),
        commit_sha=os.environ.get("GITHUB_SHA","unknown"),cap_s=CAP)

def shard(i):
    need(0<=i<SHARDS,"bad shard")
    cc=cases()
    OUT.mkdir(exist_ok=True)
    xs=[c for j,c in enumerate(cc) if j%SHARDS==i]
    need(len(xs)==2,"shard source split changed")
    rows=[]
    for x in xs:
        for rep in range(REPS):
            seed=int(sha_bytes((PROTO+"|"+x["sha256"]+"|"+str(rep)).encode())[:8],16)
            order=list(ARMS);random.Random(seed).shuffle(order)
            for pos,arm in enumerate(order):
                rr=trial(x,arm,rep,pos,seed);rows.append(rr)
                save(OUT/("shard-%d.json"%i),rows)
                print("C12_TRIAL",json.dumps(rr,sort_keys=True),flush=True)
    need(len(rows)==2*REPS*len(ARMS),"partial shard")
    print("C12_SHARD_PASS",i,len(rows),flush=True)

def audit():
    cc=cases(); bysha={x["sha256"]:x for x in cc}
    rows=[]
    for i in range(SHARDS):
        p=OUT/("shard-%d.json"%i)
        need(p.is_file(),"missing shard")
        part=json.loads(p.read_text())
        need(len(part)==2*REPS*len(ARMS),"incomplete shard")
        rows+=part
    need(len(rows)==TARGET*REPS*len(ARMS),"missing paired trials")
    groups=collections.defaultdict(set)
    for r in rows:
        x=bysha.get(r["source_sha256"])
        need(x and r["gbd"]==x["gbd"] and r["protocol"]==PROTO,"bad SHA pairing")
        need(r["arm"] in ARMS and r["rep"] in range(REPS) and r["cap_s"]==CAP,"bad arm/rep/cap")
        k=(r["source_sha256"],r["rep"])
        need(r["arm"] not in groups[k],"duplicate trial")
        groups[k].add(r["arm"])
        need(r["source_original_SHA_verified"] and r["total_wall_includes_header_and_pilot"],"incomplete E2E")
        if r["status"]=="TIMEOUT":
            need(r["PAR2_s"]==2*CAP,"bad PAR2 timeout")
        else:
            need(r["status"]==x["status"] and abs(r["PAR2_s"]-r["wall_s"])<1e-5,"bad result")
            if r["status"]=="SAT":need(r["SAT_original_witness_verified"],"unverified SAT witness")
    need(len(groups)==TARGET*REPS and all(set(ARMS)==x for x in groups.values()),"pairing incomplete")
    scores={}
    for arm in ARMS:
        rr=[x for x in rows if x["arm"]==arm]
        scores[arm]=dict(PAR2_s=round(sum(x["PAR2_s"] for x in rr),6),
             solved=sum(x["status"]!="TIMEOUT" for x in rr),attempts=len(rr),
             SAT_verified=sum(x["status"]=="SAT" for x in rr),
             UNSAT_without_LRAT=sum(x["status"]=="UNSAT" for x in rr),
             timeouts=sum(x["status"]=="TIMEOUT" for x in rr))
    for v in scores.values():v["speedup_vs_Kissat_x"]=round(scores["kissat"]["PAR2_s"]/v["PAR2_s"],6)
    per=[]
    for x in cc:
        rr=[r for r in rows if r["source_sha256"]==x["sha256"]]
        per.append(dict(gbd=x["gbd"],sha256=x["sha256"],reference=x["status"],
          modes={a:dict(PAR2_s=round(sum(r["PAR2_s"] for r in rr if r["arm"]==a),6),
             solved=sum(r["status"]!="TIMEOUT" for r in rr if r["arm"]==a)) for a in ARMS}))
    report=dict(protocol=PROTO,source_count=TARGET,full_trials=len(rows),
         original_source_SHA_verified=True,dev_test_policy="no model fitted; all 8 are fresh official evaluation relative to indexed C8D C9c C10b; all previous C8I/C11 strategies count as development",
         global_blind_claim=False,no_auto_promotion=True,independent_UNSAT_LRAT=False,
         repeats_are_not_independent_solver_seeds=True,cap_s=CAP,
         frozen_C11_policy=RULE,early_BVE_gate="C8I first 16 candidates, skip remainder if no eliminated vars",
         R28="exact GF2 with unchanged Kissat fallback; never claim mixed-CNF benefit without E2E proof",
         probe_router="separate 0.5s pilot and restart; pilot overhead charged, not in-process",
         scores=scores,per_formula=per,
         R28_activated_sources=sum(x["nvars"]<=3000 and x["bytes"]<=12*1024*1024 for x in cc))
    save(OUT/"report.json",report)
    print("C12_FINAL",json.dumps({k:v for k,v in report.items() if k!="per_formula"},sort_keys=True),flush=True)
    for r in per: print("C12_CASE",json.dumps(r,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=("freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="freeze":freeze()
    elif a.action=="verify":print("C12_SOURCE_SHA_VERIFIED",len(cases()),flush=True)
    elif a.action=="shard":shard(a.shard)
    else:audit()
if __name__=="__main__": main()
