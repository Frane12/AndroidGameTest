#!/usr/bin/env python3
"""C4 preregistered CAUSAL diagnostic: duplication multiplicity versus clause-load order.

On four selected DEVELOPMENT source SHA cases, compare (a) frozen original
C2 native, (b) frozen C2 dedup, (c) C4 duplicate-tail: same exact original
multiset and same unique first-occurrence order, but move duplicates to end.
Falsifier: tail behaves no differently from native when dedup changes CDCL,
which suggests multiplicity rather than clause load ordering. This experiment
does NOT demonstrate generalization or a blind speedup.
"""
from __future__ import annotations
import argparse,collections,hashlib,itertools,json,os,pathlib,random,subprocess,time
import c2_cnf_clean_ablation as c2
import c3_dedup_sha12_validation as c3
import mre11b_prospective_freeze as c1sources
import r195_native_cms_benchmark as cms
OUT=pathlib.Path("c4_out")
PROTO="DRNAS-C4-EXACT-DUPLICATE-TAIL-4FROZEN-SHA-3ARMS-3REPS-35S-v1"
CAP=35.0
REPS=3
MODES=("cpp_native","cpp_dedup","cpp_tail")
IDS=("220bb8aa093e502c47afcdac3140d67c",
     "fdfcd52a21824b7181d66672f283ba04",
     "695d8f6a2ee6e89e5a4f5d94abc3aca6",
     "037d21e060a2e3eab8b080aa84ceee75")
EXPECT_SHA=(
"69aa8b6bb96a5952fedf1007994b4255d06f7e32023390bc4c342b1b30a0356a",
"7f25d0862e92fb60d957ea903ded020ec2b83b2ceec2ba4bf015bdcb1d4c3ac1",
"eb9a4740b712b149f08d5b430ae5907109eac3f231ce549a281703bc8e0965fb",
"b84bff752c8292bacf847078d0fe2c2bf8ef86f429c08250e973a0525b607c39",
)
def need(ok,msg):
    if not ok:raise RuntimeError("C4_FAIL_CLOSED "+str(msg))
def sources():
    c1={x["gbd"]:x for x in c1sources.verify()["source_cases"]}
    c3src={x["gbd"]:x for x in c3.original_cases()}
    arr=[]
    for i,gbd in enumerate(IDS):
        original=(c1.get(gbd) if i==0 else c3src.get(gbd))
        need(original and original["sha256"]==EXPECT_SHA[i],"frozen source GBD/SHA mismatch")
        src=(c1sources.ROOT if i==0 else c3.SRC)/original["filename"]
        need(hashlib.sha256(src.read_bytes()).hexdigest()==EXPECT_SHA[i],"source SHA changed")
        arr.append(dict(gbd=gbd,sha256=EXPECT_SHA[i],path=src))
    need(len({x["sha256"] for x in arr})==4,"duplicate selected original")
    return arr
def gate_native(stdout,mode):
    if mode!="cpp_tail":return c2.parse_native_gate(stdout,mode)
    records=[l.split(" ",1)[1] for l in stdout.splitlines() if l.startswith("MRE10_GATE ")]
    need(len(records)==1,"C4 tail gate absent")
    data=json.loads(records[0])
    need(data["mode"]=="cpp_tail" and data["certificate"]=="original_CNF_exact_clause_permutation",
         "C4 original-CNF identity certificate missing")
    need(data["clauses_removed"]==0 and data["taut_clauses_removed"]==0 and
         data["duplicate_clauses_removed"]==0 and data["duplicate_literals_removed"]==0 and
         data["variables_eliminated"]==0,"tail mode changed clause multiset")
    need(bool(data["applied"])==(data["duplicate_clauses_moved"]>0),
         "tail gate activation inconsistency")
    return data
def seed(c,rep):
    s=PROTO+"|"+c["sha256"]+"|"+str(rep)
    return int(hashlib.sha256(s.encode()).hexdigest()[:8],16)
def compare_exact_multisets():
    OUT.mkdir(exist_ok=True)
    checked=[]
    for item in sources():
        n,original=c2.read_clauses(item["path"])
        dst=OUT/("emit-"+item["gbd"]+".cnf")
        p=subprocess.run(["c4/bin/emit","--emit",str(item["path"]), "cpp_tail",str(dst)],
                         capture_output=True,text=True,errors="replace",check=True)
        g=gate_native(p.stdout,"cpp_tail")
        n2,new=c2.read_clauses(dst)
        need(n==n2 and collections.Counter(original)==collections.Counter(new),
             "C4 tail source literal clause multiset is NOT identical")
        # source-only duplicate inventory, no solver outcomes consulted
        seen=set();dup=0
        for clause in original:
            k=tuple(sorted(set(clause)))
            if k in seen:dup+=1
            else:seen.add(k)
        need(dup==g["duplicate_clauses_moved"],"tail duplicate tally mismatch")
        checked.append(dict(gbd=item["gbd"],sha256=item["sha256"],
            clause_count=len(original),duplicate_clauses=dup,
            gates_after_emit=g["applied"]))
    (OUT/"source-invariants.json").write_text(json.dumps(checked,indent=2,sort_keys=True)+"\n")
    need(len(checked)==4 and all(x["duplicate_clauses"]>0 for x in checked),
         "experiment must contain four positive duplicate examples")
    # A tiny explicit exact-multiset selftest.  The C4 reordering changes
    # the array order, but not a single clause, literal, or variable.
    small=OUT/"selftest.cnf"
    small.write_text("p cnf 4 7\n1 2 0\n-3 4 0\n2 1 0\n-4 3 0\n1 2 0\n3 -4 0\n-4 3 0\n")
    dest=OUT/"selftest-tail.cnf"
    p=subprocess.run(["c4/bin/emit","--emit",str(small),"cpp_tail",str(dest)],
                     capture_output=True,text=True,check=True)
    gate=gate_native(p.stdout,"cpp_tail")
    _,old=c2.read_clauses(small);_,new=c2.read_clauses(dest)
    need(collections.Counter(old)==collections.Counter(new) and old!=new,
         "selftest must reorder while maintaining identical source clauses")
    need(gate["duplicate_clauses_moved"]==4,"synthetic duplicate count mismatch")
    # check that the rebuilt solver's original source behavior still matches
    # the pinned C2 binary for original and dedup arms (result + CDCL counters)
    for mode in ("cpp_native","cpp_dedup"):
        outcomes=[]
        for binary in ("c2/bin/native","c4/bin/native"):
            env=os.environ.copy();env.pop("DRNAS_MAX_CONFLICTS",None)
            p=subprocess.run([binary,str(small),mode,"42"],capture_output=True,
                text=True,check=True,env=env)
            status,model,stats=cms.parsed_native(p.stdout)
            need(status=="SAT","native parity test did not solve original SAT")
            cms.verify_model(small,model)
            outcomes.append((status,stats))
        need(outcomes[0]==outcomes[1],"original C2 native or dedup parity changed")
    print("C4_EXACT_MULTIPLICITY_PARITY_PASS",json.dumps(checked,sort_keys=True),flush=True)
def trial(item,rep,mode):
    need(rep in range(REPS) and mode in MODES,"non-frozen trial")
    src=item["path"]
    need(hashlib.sha256(src.read_bytes()).hexdigest()==item["sha256"],"source SHA drift")
    binary="c4/bin/native" if mode=="cpp_tail" else "c2/bin/native"
    cmd=[str(pathlib.Path(binary).resolve()),str(src.resolve()),mode,str(seed(item,rep))]
    env=os.environ.copy();env.pop("DRNAS_MAX_CONFLICTS",None)
    begin=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
            timeout=CAP,check=False,env=env)
    except subprocess.TimeoutExpired:p=None
    status="TIMEOUT";stats=None;gate={};witness=False
    if p is not None:
        need(p.returncode==0,"C4 native crash: "+p.stderr[-500:])
        gate=gate_native(p.stdout,mode)
        status,model,stats=cms.parsed_native(p.stdout)
        if status=="SAT":
            cms.verify_model(src,model);witness=True
    wall=time.perf_counter()-begin
    if status not in ("SAT","UNSAT") or wall>CAP:status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"SAT model not verified against original SHA")
    need(status!="UNSAT","all four predeclared original cases have prior SAT witness")
    return dict(protocol=PROTO,gbd=item["gbd"],sha256=item["sha256"],
        rep=rep,seed=seed(item,rep),mode=mode,status=status,
        SAT_original_witness_verified=witness,cap_s=CAP,
        wall_s=round(wall,6),par2_s=round(wall if status=="SAT" else CAP*2,6),
        original_CNF_clause_multiset_preserved=(mode=="cpp_tail"),
        gate=gate,native_stats=stats,build_sha=os.environ.get("GITHUB_SHA","local"))
def shard(i):
    cc=sources()
    need(i in range(4),"invalid source shard")
    OUT.mkdir(exist_ok=True);c=cc[i];rows=[]
    for rep in range(REPS):
        arms=list(MODES)
        random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(arms)
        for mode in arms:
            x=trial(c,rep,mode);rows.append(x)
            (OUT/("shard-%d.json"%i)).write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
            print("C4_TRIAL",json.dumps(x,sort_keys=True),flush=True)
    need(len(rows)==len(MODES)*REPS,"partial shard")
    print("C4_SHARD_PASS",i,len(rows),flush=True)
def audit():
    cc=sources();bysha={c["sha256"]:c for c in cc}
    rows=[]
    for i in range(4):
        p=OUT/("shard-%d.json"%i)
        need(p.is_file(),"shard missing")
        a=json.loads(p.read_text())
        need(len(a)==REPS*len(MODES),"partial source")
        rows.extend(a)
    need(len(rows)==4*REPS*len(MODES),"partial benchmark")
    grouped=collections.defaultdict(dict)
    for x in rows:
        c=bysha.get(x["sha256"])
        need(c is not None and x["gbd"]==c["gbd"],"source SHA drift")
        need(x["protocol"]==PROTO and x["mode"] in MODES and
             x["rep"] in range(REPS) and x["seed"]==seed(c,x["rep"]),
             "seed/mode mismatch")
        need(x["cap_s"]==CAP and x["status"] in ("SAT","TIMEOUT"),"status or cap mismatch")
        need(x["status"]!="SAT" or x["SAT_original_witness_verified"],
             "missing original SAT model")
        need(x["status"]!="TIMEOUT" or x["par2_s"]==2*CAP,"incorrect timeout PAR2")
        if x["status"]=="SAT":need(abs(x["wall_s"]-x["par2_s"])<2e-6,"solved PAR2 mismatch")
        if x["mode"]=="cpp_tail" and x["status"]=="SAT":
            need(x["gate"]["certificate"]=="original_CNF_exact_clause_permutation" and
                 x["gate"]["clauses_removed"]==0,"uncertified tail intervention")
        k=(x["sha256"],x["rep"])
        need(x["mode"] not in grouped[k],"duplicate arm")
        grouped[k][x["mode"]]=x
    need(len(grouped)==4*REPS and all(set(z)==set(MODES) for z in grouped.values()),
         "missing paired source/seed/mode")
    scores={}
    for mode in MODES:
        a=[x for x in rows if x["mode"]==mode]
        scores[mode]=dict(trials=len(a),
           solved=sum(x["status"]=="SAT" for x in a),
           timeouts=sum(x["status"]=="TIMEOUT" for x in a),
           par2_s=round(sum(x["par2_s"] for x in a),6),
           full_wall_s=round(sum(x["wall_s"] for x in a),6),
           moved_duplicates=sum(x["gate"].get("duplicate_clauses_moved",0) for x in a),
           removed_duplicates=sum(x["gate"].get("duplicate_clauses_removed",0) for x in a))
    baseline=scores["cpp_native"]["par2_s"]
    for mode in MODES:scores[mode]["speedup_vs_native_PAR2_x"]=round(baseline/scores[mode]["par2_s"],6)
    per_case={}
    for c in cc:
        z=[x for x in rows if x["sha256"]==c["sha256"]]
        per_case[c["gbd"]]={mode:dict(
            status=[x["status"] for x in z if x["mode"]==mode],
            par2_s=round(sum(x["par2_s"] for x in z if x["mode"]==mode),6),
            conflicts=[x["native_stats"]["conflicts"] if x["native_stats"] else None for x in z if x["mode"]==mode])
            for mode in MODES}
    output=dict(protocol=PROTO,cohort="POSTHOC four known C2/C3 case mechanisms, NOT holdout",
       source_sha=[c["sha256"] for c in cc],case_count=len(cc),
       reps=REPS,cap_s=CAP,trial_count=len(rows),
       original_sat_models_checked=True,independent_unsat_proof="not applicable to SAT selected cases",
       no_auto_promotion=True,compare_pinned_C2_native_vs_pinned_C2_dedup_vs_C4_tail=True,
       scores=scores,per_case=per_case)
    (OUT/"report.json").write_text(json.dumps(output,indent=2,sort_keys=True)+"\n")
    print("C4_FINAL",json.dumps({k:v for k,v in output.items() if k!="per_case"},sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="selftest":compare_exact_multisets()
    elif args.action=="shard":shard(args.shard)
    else:audit()
