#!/usr/bin/env python3
"""DRNAS C8D: C7 BVE/duplicate causal proxy x early bounded CDCL dynamics.
Development diagnostics: C7 six previously-seen original SHA, four CMS modes,
two independent conflict budgets (128, 1024), two seeds = 96 bounded probes.
Prospective *relative to C7*, not globally blind: 19 original S1 source SHA,
seven full SAT/UNSAT arms x 2 seeds x 15s end-to-end = 266 trials.
A bounded-CDCL diagnostic is NEVER counted as full SAT without an original
CNF witness; any router probe and abandoned solver work are charged to wall.
C8D dynamic pilots use fresh processes; learned state is NOT transferred.
BVE raw-resolvent eligibility proxy is NOT evidence of actual CMS BVE events.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,statistics,subprocess,time
import c5_early_cdcl_bounded as c5
import c6_cms_inprocessing_factorial as c6
import c7_standard_solver_bve_crosscheck as c7
import mre11b_prospective_benchmark as ref
import r195_native_cms_benchmark as cms

PROTO="DRNAS-C8D-C7-BVE-EARLY-CDCL-19SHA-7ARM-2REP-15S-v1"
ROOT=pathlib.Path("c8d_out")
S1=pathlib.Path("c8d_s1_source")/"s1_router"
REPS=2;CAP=15.0;SHARDS=5
MODES=("cms_native","cms_dedup_nobve","cms_nobve","cadical","kissat","c8_bve_static","c8_bve_early")
DIAG_MODES=("cpp_native","cpp_dedup","c6_native_nobve","c6_dedup_nobve")
DIAG_BUDGETS=(128,1024)
PROBE_CONFLICTS=256
PILOT_CAP_S=0.65
SCAN_CLAUSES=12000
SCAN_BYTES=1048576

def need(ok,msg):
    if not ok:raise RuntimeError("C8D_FAIL_CLOSED "+str(msg))
def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for part in iter(lambda:f.read(1<<20),b""):h.update(part)
    return h.hexdigest()
def save(path,value):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n")
def seed(c,rep):
    s=PROTO+"|"+c["sha256"]+"|"+str(rep)
    return int(hashlib.sha256(s.encode()).hexdigest()[:8],16)
def dev_sources():
    cc,_=c7.get_cases()
    need(len(cc)==6 and len({c["sha256"] for c in cc})==6,"C7 source drift")
    return cc
def hold_sources():
    m=json.loads((S1/"manifest.json").read_text())
    need(m["total_cases"]==20 and len(m["cases"])==20 and
         m["protocol"]=="DRNAS-S1-20EXTERNAL-SHA-DISJOINT-C3-3BACKENDS-2ROUTERS-2REP-15S-PAR2-v1",
         "S1 source list changed")
    old={c["sha256"] for c in dev_sources()}
    out=[]
    for c in m["cases"]:
        src=S1/"sources"/c["name"]
        need(src.is_file() and sha(src)==c["sha256"] and
             True,"source SHA mismatch")
        if c["sha256"] in old:continue  # Predeclared exact SHA overlap exclusion, never runtime based.
        out.append(dict(sha256=c["sha256"],gbd=c["gbd"],path=src,
                        cohort=c["cohort"],prior_reference_status=c["prior_reference_status"]))
    need(len(out)==19 and len({c["sha256"] for c in out})==19,
         "exact one C7/S1 overlap exclusion expected, no other source change")
    return out
def inspect(path):
    """Source-only capped prefix: C7 two-sided occurrence eligibility proxy.
    Tracks duplicate multisets and signed occurrences. No solver execution."""
    start=time.perf_counter()
    observed=0;binary=0;horn=0;duplicate=0
    pos=collections.Counter();neg=collections.Counter()
    upos=collections.Counter();uneg=collections.Counter()
    seen=set();nvars=None;bytes_read=0;buf=[]
    with pathlib.Path(path).open("rb") as f:
        for line in f:
            bytes_read+=len(line)
            if bytes_read>SCAN_BYTES or observed>=SCAN_CLAUSES:break
            s=line.strip()
            if not s or s.startswith(b"c"):continue
            if s.startswith(b"p "):
                a=s.split()
                need(len(a)==4 and a[1]==b"cnf","bad DIMACS header")
                nvars=int(a[2]);continue
            need(nvars is not None,"no header")
            try:lits=[int(x) for x in s.split()]
            except ValueError:raise RuntimeError("C8D_FAIL_CLOSED malformed CNF literal")
            for lit in lits:
                if lit:
                    need(1<=abs(lit)<=nvars,"bad literal ID")
                    buf.append(lit);continue
                clause=tuple(sorted(set(buf)));buf=[]
                observed+=1
                if len(clause)==2:binary+=1
                if sum(v>0 for v in clause)<=1:horn+=1
                if clause in seen:duplicate+=1
                else:
                    seen.add(clause)
                    for v in clause:
                        (upos if v>0 else uneg)[abs(v)]+=1
                for v in clause:
                    (pos if v>0 else neg)[abs(v)]+=1
                if observed>=SCAN_CLAUSES:break
    need(nvars is not None and observed>0,"empty original")
    def eligibility(a,b):
        return a>0 and b>0 and a*b<=a+b
    keys=set(pos)|set(neg)|set(upos)|set(uneg)
    before=sum(eligibility(pos[v],neg[v]) for v in keys)
    after=sum(eligibility(upos[v],uneg[v]) for v in keys)
    flips=sum(not eligibility(pos[v],neg[v]) and eligibility(upos[v],uneg[v]) for v in keys)
    old_pairs=sum(pos[v]*neg[v] for v in keys)
    new_pairs=sum(upos[v]*uneg[v] for v in keys)
    return dict(observed=observed,nvars=nvars,
       binary_fraction=round(binary/observed,6),
       horn_fraction=round(horn/observed,6),
       duplicate_count=duplicate,
       duplicate_fraction=round(duplicate/observed,6),
       source_BVE_eligible_proxy=before,dedup_BVE_eligible_proxy=after,
       proxy_flips_on=flips,
       pair_drop_fraction=round((old_pairs-new_pairs)/max(1,old_pairs),6),
       scan_truncated=(bytes_read>SCAN_BYTES or observed>=SCAN_CLAUSES),
       scan_cost_s=round(time.perf_counter()-start,6))
def static_choice(f):
    """Frozen C7 hypothesis, no usage of S1 historical solver performance."""
    if f["duplicate_fraction"]>=0.035 and (
        f["pair_drop_fraction"]>=0.10 or f["proxy_flips_on"]>0):
        return "cms_dedup_nobve","C7_duplicate_BVE_proxy"
    if f["binary_fraction"]>=0.96 and f["horn_fraction"]>=0.96 and f["duplicate_fraction"]<0.005:
        return "cms_native","strong_binary_Horn_CMS"
    return "cadical","default_CaDiCaL"
def dynamic_choice(f,pilots):
    """Early dynamics only changes branch if complete, bounded metrics support it.
    Both pilots started from the original CNF and the SAME frozen seed.
    Selection thresholds frozen *before* S1-source benchmark."""
    baseline=static_choice(f)
    a=pilots.get("cpp_native");b=pilots.get("c6_dedup_nobve")
    if not a or not b or not a.get("stats") or not b.get("stats"):
        return baseline
    if a["status"]!="BUDGET" or b["status"]!="BUDGET":
        return baseline
    na=a["stats"];nb=b["stats"]
    if na["conflicts"]<64 or nb["conflicts"]<64:
        return baseline
    # Compare actual solver effort at approximately the same conflict budget.
    # Smaller decisions and propagation counts alone do not prove quality.
    da=na["decisions"]/na["conflicts"];db=nb["decisions"]/nb["conflicts"]
    pa=na["propagations"]/na["conflicts"];pb=nb["propagations"]/nb["conflicts"]
    if f["duplicate_count"]>=8 and f["pair_drop_fraction"]>=0.075 and (
        db<da*0.75 and pb<pa*1.30):
        return "cms_dedup_nobve","early_dedup_lower_decisions_and_BVE_geometry"
    if f["binary_fraction"]>=0.90 and da<db*.70 and pa<pb*1.3 and (
        a["wall_s"] < b["wall_s"]*.8):
        return "cms_native","early_native_dominance"
    return baseline
def selftest():
    f=dict(observed=3000,binary_fraction=.3,horn_fraction=.5,
           duplicate_count=180,duplicate_fraction=.06,
           pair_drop_fraction=.4,proxy_flips_on=0)
    need(static_choice(f)[0]=="cms_dedup_nobve","BVE static")
    f["duplicate_fraction"]=0;f["duplicate_count"]=0
    need(static_choice(f)[0]=="cadical","CaDiCaL static")
    f["binary_fraction"]=.97;f["horn_fraction"]=.98
    need(static_choice(f)[0]=="cms_native","CMS dense static")
    f["binary_fraction"]=.3;f["horn_fraction"]=.5
    a=dict(status="BUDGET",wall_s=.05,stats=dict(conflicts=256,decisions=1000,propagations=10000))
    b=dict(status="BUDGET",wall_s=.05,stats=dict(conflicts=256,decisions=200,propagations=9000))
    f["duplicate_count"]=100;f["duplicate_fraction"]=.03
    need(dynamic_choice(f,{"cpp_native":a,"c6_dedup_nobve":b})[0]=="cms_dedup_nobve",
         "early dynamic BVE")
    print("C8D_C7_BVE_AND_EARLY_CDCL_RULES_FROZEN_PASS",flush=True)
def native_command(src,mode,s):
    binary="c2/bin/native" if mode in ("cpp_native","cpp_dedup") else "c6/bin/native"
    return [str(pathlib.Path(binary).resolve()),str(pathlib.Path(src).resolve()),mode,str(s)]
def probe(c,rep,mode,budget,cap):
    need(mode in DIAG_MODES and budget in (*DIAG_BUDGETS,PROBE_CONFLICTS),"bad pilot")
    src=c["path"]
    need(sha(src)==c["sha256"],"original source SHA changed")
    env=os.environ.copy();env["DRNAS_MAX_CONFLICTS"]=str(budget)
    start=time.perf_counter()
    try:
        p=subprocess.run(native_command(src,mode,seed(c,rep)),
             capture_output=True,text=True,errors="replace",
             check=False,timeout=cap,env=env)
    except subprocess.TimeoutExpired:p=None
    wall=time.perf_counter()-start
    status="PILOT_TIMEOUT";stats=None;verified=False
    if p is not None:
        need(p.returncode==0,"bounded CMS crashed "+p.stderr[-300:])
        c6.native_gate(p.stdout,mode)
        status,stats=c5.parse_result(p.stdout)
        need(status in ("SAT","UNSAT","BUDGET"),"bounded UNKNOWN result")
        if status=="SAT":
            x,model,_=cms.parsed_native(p.stdout)
            need(x=="SAT","SAT model verdict mismatch")
            cms.verify_model(src,model);verified=True
        if status in ("SAT","UNSAT") and c.get("expected_status","UNKNOWN")!="UNKNOWN":
            need(status==c["expected_status"],"bounded terminal contradicts reference")
    return dict(mode=mode,budget=budget,status=status,stats=stats,
       wall_s=round(wall,6),sat_witness_verified=verified,
       pilot_is_not_full_PAR2=True)
def diagnostic_shard(idx):
    cc=dev_sources()
    need(idx in range(6),"bad C7 diagnostic shard")
    c=cc[idx];rows=[]
    for rep in range(REPS):
        combo=[(mode,budget) for mode in DIAG_MODES for budget in DIAG_BUDGETS]
        random.Random(PROTO+c["sha256"]+str(rep)).shuffle(combo)
        for mode,budget in combo:
            a=probe(c,rep,mode,budget,cap=4.0)
            row=dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],rep=rep,
              seed=seed(c,rep),source_cohort="C7_development_not_blind",**a)
            rows.append(row);save(ROOT/f"diag-{idx}.json",rows)
            print("C8D_DIAG",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==REPS*len(DIAG_MODES)*len(DIAG_BUDGETS),"diagnostic shortfall")
    print("C8D_DIAG_SHARD_PASS",idx,len(rows),flush=True)
def run_full(c,rep,mode):
    need(mode in MODES,"invalid full arm")
    src=c["path"];need(sha(src)==c["sha256"],"source SHA changed")
    start=time.perf_counter();f=None;pilots=[];selection="";backend=mode
    early_terminal=None
    if mode.startswith("c8_"):
        f=inspect(src)
        backend,selection=static_choice(f)
    if mode=="c8_bve_early":
        pilot_results={}
        for pilot_mode in ("cpp_native","c6_dedup_nobve"):
            if time.perf_counter()-start>=CAP-0.1:break
            x=probe(c,rep,pilot_mode,PROBE_CONFLICTS,
                    min(PILOT_CAP_S,max(.05,CAP-(time.perf_counter()-start)-.05)))
            pilots.append(x);pilot_results[pilot_mode]=x
            if x["status"] in ("SAT","UNSAT"):
                backend=("cms_native" if pilot_mode=="cpp_native" else "cms_dedup_nobve")
                selection="verified_early_terminal_reuse_no_restart"
                early_terminal=x;break
        if early_terminal is None:
            backend,selection=dynamic_choice(f,pilot_results)
    remaining=CAP-(time.perf_counter()-start)
    status="TIMEOUT";verified=False;full_stats=None
    if early_terminal:
        status=early_terminal["status"]
        verified=early_terminal["sat_witness_verified"]
        # Only terminal bounded SAT/UNSAT can be legitimately reused.
        need(status=="UNSAT" or verified,"early SAT model not checked")
    elif remaining>0.03:
        if backend=="cadical":
            cmd=["/usr/bin/cadical",str(src.resolve())]
        elif backend=="kissat":
            cmd=[str(pathlib.Path("built/bin/kissat_4_0_4").resolve()),str(src.resolve())]
        else:
            cm={"cms_native":"cpp_native","cms_nobve":"c6_native_nobve",
                "cms_dedup_nobve":"c6_dedup_nobve"}
            need(backend in cm,"invalid live backend")
            cmd=native_command(src,cm[backend],seed(c,rep))
        env=os.environ.copy();env.pop("DRNAS_MAX_CONFLICTS",None)
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                             check=False,timeout=remaining,env=env)
        except subprocess.TimeoutExpired:p=None
        if p is not None:
            if backend in ("cadical","kissat"):
                status,model=ref.external_parse(p)
            else:
                need(p.returncode==0,"full native failed "+p.stderr[-500:])
                c6.native_gate(p.stdout,cm[backend])
                status,model,full_stats=cms.parsed_native(p.stdout)
            if status=="SAT":
                cms.verify_model(src,model);verified=True
    elapsed=time.perf_counter()-start
    if status not in ("SAT","UNSAT") or elapsed>CAP:
        status="TIMEOUT";verified=False
    if status in ("SAT","UNSAT") and c["prior_reference_status"]!="UNKNOWN":
        need(status==c["prior_reference_status"],"terminal contradicts independently frozen prior reference")
    if status=="SAT":need(verified,"SAT not verified on original SHA")
    return dict(protocol=PROTO,source_sha256=c["sha256"],gbd=c["gbd"],
      cohort=c["cohort"],rep=rep,seed=seed(c,rep),mode=mode,
      backend=backend,selection_reason=selection,source_BVE_proxy=f,
      pilots=pilots,early_terminal_reused=early_terminal is not None,
      pilot_cost_s=round(sum(p["wall_s"] for p in pilots),6),
      status=status,original_SAT_witness_verified=verified,
      UNSAT_independent_LRAT=False,wall_s=round(elapsed,6),cap_s=CAP,
      par2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),
      native_stats=full_stats,probes_abandoned_restart_not_preserved=True,
      external_default_seed_not_randomized=(backend in ("cadical","kissat")))
def shard(idx):
    ss=hold_sources();need(idx in range(SHARDS),"bad holdout shard")
    cases=ss[idx::SHARDS];need(len(cases)==(4 if idx<4 else 3),"source-per-shard drift")
    rows=[]
    for c in cases:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                x=run_full(c,rep,mode)
                rows.append(x);save(ROOT/f"shard-{idx}.json",rows)
                print("C8D_TRIAL",json.dumps(x,sort_keys=True),flush=True)
    need(len(rows)==len(cases)*REPS*len(MODES),"shard trials missing")
    print("C8D_SHARD_PASS",idx,len(rows),flush=True)
def audit_diag():
    cc=dev_sources();by_sha={x["sha256"]:x for x in cc}
    rows=[];seen=set()
    for i in range(6):
        x=json.loads((ROOT/f"diag-{i}.json").read_text())
        need(len(x)==16,"incomplete early diagnostic")
        rows+=x
    need(len(rows)==96,"96 diagnostics absent")
    for x in rows:
        c=by_sha.get(x["sha256"])
        need(c is not None and x["protocol"]==PROTO and
             x["seed"]==seed(c,x["rep"]) and
             x["budget"] in DIAG_BUDGETS and
             x["mode"] in DIAG_MODES,"diagnostic source drift")
        key=(x["sha256"],x["rep"],x["mode"],x["budget"])
        need(key not in seen,"duplicate diagnostic");seen.add(key)
        need(x["status"] in ("SAT","UNSAT","BUDGET","PILOT_TIMEOUT"),"diagnostic status invalid")
        if x["status"]=="SAT":need(x["sat_witness_verified"],"unproven diag SAT")
    report=dict(protocol=PROTO,status="C8D_EARLY_DIAG_PASS",
         development_C7_not_blind=True,independent_process_per_budget=True,
         bounded_diagnostics_not_PAR2=True,source_count=6,attempts=96,
         per_mode_budget={m+":"+str(b):dict(
            attempts=len([x for x in rows if x["mode"]==m and x["budget"]==b]),
            budget_reached=sum(x["status"]=="BUDGET" for x in rows if x["mode"]==m and x["budget"]==b),
            solved_before_limit=sum(x["status"] in ("SAT","UNSAT") for x in rows if x["mode"]==m and x["budget"]==b),
            total_probe_wall_s=round(sum(x["wall_s"] for x in rows if x["mode"]==m and x["budget"]==b),6))
            for m in DIAG_MODES for b in DIAG_BUDGETS})
    save(ROOT/"diagnostic-report.json",report)
    print("C8D_DIAGNOSTIC_FINAL",json.dumps(report,sort_keys=True),flush=True)
def audit():
    cases=hold_sources();by_sha={c["sha256"]:c for c in cases}
    rows=[];paired=collections.defaultdict(dict)
    for i in range(SHARDS):
        a=json.loads((ROOT/f"shard-{i}.json").read_text())
        need(len(a)==(4 if i<4 else 3)*REPS*len(MODES),"partial full-solve shard")
        rows+=a
    need(len(rows)==266,"incomplete 266 original paired full trials")
    for x in rows:
        c=by_sha.get(x["source_sha256"])
        need(c is not None and x["gbd"]==c["gbd"] and x["cohort"]==c["cohort"]
             and x["protocol"]==PROTO and x["mode"] in MODES and
             x["rep"] in range(REPS) and x["seed"]==seed(c,x["rep"]) and
             x["cap_s"]==CAP,"source or protocol mismatch")
        need(x["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid terminal")
        if x["status"]=="SAT":need(x["original_SAT_witness_verified"],"SAT witness absent")
        need(abs(x["par2_s"]-(2*CAP if x["status"]=="TIMEOUT" else x["wall_s"]))<.000002,
             "PAR2 not full E2E")
        if x["mode"]=="c8_bve_early":
            need(len(x["pilots"]) in (1,2),"must charge actual pilot")
            if not x["early_terminal_reused"]:
                b=dynamic_choice(x["source_BVE_proxy"],{p["mode"]:p for p in x["pilots"]})[0]
                need(b==x["backend"],"early gate changed post hoc")
        elif x["mode"]=="c8_bve_static":
            need(x["pilots"]==[] and
                 static_choice(x["source_BVE_proxy"])[0]==x["backend"],
                 "static gate drift")
        else:
            known={"cms_native","cms_dedup_nobve","cms_nobve","cadical","kissat"}
            need(x["mode"] in known and x["backend"]==x["mode"] and x["pilots"]==[],
                 "reference mode changed")
        key=(x["source_sha256"],x["rep"])
        need(x["mode"] not in paired[key],"duplicate mode")
        paired[key][x["mode"]]=x
    need(len(paired)==38 and all(set(v)==set(MODES) for v in paired.values()),
         "unpaired 40-source-seed x 6-arm cohort")
    for pair in paired.values():
        need(len({x["status"] for x in pair.values() if x["status"]!="TIMEOUT"})<=1,
             "SAT/UNSAT disagreement")
    scores={}
    for mode in MODES:
        a=[x for x in rows if x["mode"]==mode]
        scores[mode]=dict(trials=len(a),
             solved=sum(x["status"]!="TIMEOUT" for x in a),
             SAT=sum(x["status"]=="SAT" for x in a),
             UNSAT_without_LRAT=sum(x["status"]=="UNSAT" for x in a),
             timeouts=sum(x["status"]=="TIMEOUT" for x in a),
             PAR2_s=round(sum(x["par2_s"] for x in a),6),
             pilot_s=round(sum(x["pilot_cost_s"] for x in a),6),
             early_verified_terminals=sum(x["early_terminal_reused"] for x in a),
             selected=dict(collections.Counter(x["backend"] for x in a)))
    base=scores["cadical"]["PAR2_s"]
    for v in scores.values():v["PAR2_speedup_vs_CaDiCaL_x"]=round(base/v["PAR2_s"],6)
    per=[]
    for c in cases:
        xx=[x for x in rows if x["source_sha256"]==c["sha256"]]
        per.append(dict(sha256=c["sha256"],cohort=c["cohort"],
             BVE_proxy=next(x["source_BVE_proxy"] for x in xx if x["mode"]=="c8_bve_static"),
             by_mode={m:dict(PAR2_s=round(sum(x["par2_s"] for x in xx if x["mode"]==m),6),
                            solved=sum(x["status"]!="TIMEOUT" for x in xx if x["mode"]==m))
                      for m in MODES}))
    oracle=round(sum(min(v["par2_s"] for v in pair.values()
                       if v["mode"] in ("cms_native","cms_dedup_nobve","cms_nobve","cadical","kissat"))
                     for pair in paired.values()),6)
    report=dict(protocol=PROTO,status="C8D_E2E_AUDIT_PASS",
       full_trials=len(rows),source_count=20,repeats=REPS,cap_s=CAP,
       source_SHA_disjoint_from_C7=True,
       excluded_one_original_C7_overlap_by_SHA_before_trials=True,
       S1_cohort_previously_evaluated_not_global_blind=True,
       no_pilot_state_reuse=True,pilot_wall_charged=True,
       BVE_proxy_not_actual_internal_BVE_event=True,
       original_SAT_witness_verified=True,UNSAT_independent_LRAT=False,
       no_auto_promotion=True,oracle_five_backend_PAR2_s=oracle,
       scores=scores,per_source=per)
    save(ROOT/"report.json",report)
    print("C8D_FINAL",json.dumps({k:v for k,v in report.items() if k!="per_source"},sort_keys=True),flush=True)
    for x in per:print("C8D_CASE",json.dumps(x,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","verify","diagnostic","audit_diagnostic","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="verify":print("C8D_SOURCE_SHA_PASS",len(dev_sources()),len(hold_sources()),flush=True)
    elif a.action=="diagnostic":diagnostic_shard(a.shard)
    elif a.action=="audit_diagnostic":audit_diag()
    elif a.action=="shard":shard(a.shard)
    else:audit()
