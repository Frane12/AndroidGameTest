#!/usr/bin/env python3
"""LEGO-1: source-proof-carrying recursive relation composition and learned ranking.
This experimental baseline learns structural utility ONLY on training SHA.
No learned rule may assert truth: every inserted clause is proof-replayed.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import pathlib
import random
import subprocess
import tempfile
import time

import drnas_x22_parallel_reducer as x22
import drnas_x24_gf2_proof_first as x24

ROOT=pathlib.Path("mre_lego1")
PROTO="DRNAS-LEGO1-PROOF-GRAMMAR-SHORT5-8SHA-4ARMS-2REPS-20261109-v1"
ARMS=("race_original","gf2_x24","lego_static","lego_learned")
CAP=5.0
SHARDS=4
REPS=2
EXPECTED=8*REPS*len(ARMS)
HELPER_CAP=.65
MAX_PREP=1.1
MAX_ROWS=200
MAX_JOINS=1800
MAX_CLAUSES=24

def need(ok,message):
    if not ok: raise RuntimeError("LEGO1_FAIL_CLOSED "+str(message))
def sha(path):return x22.digest(path)
def save(path,thing):return x22.save(path,thing)

def read_binary(clauses):
    edges=collections.defaultdict(list);ids=0
    for ix,cl in enumerate(clauses):
        if len(cl)!=2:continue
        a,b=cl
        if a==b or a==-b:continue
        for source,target in ((-a,b),(-b,a)):edges[source].append((target,ix))
        ids+=1
        if ids>=30000:break
    return edges

def get_path(edges,a,b,max_depth=5):
    if a==b:return []
    q=collections.deque([(a,0)]);seen={a};back={}
    while q and len(seen)<2000:
        vertex,depth=q.popleft()
        if depth>=max_depth:continue
        for target,index in edges.get(vertex,()):
            if target in seen:continue
            seen.add(target);back[target]=(vertex,index)
            if target==b:
                route=[];pos=b
                while pos!=a:
                    prev,idx=back[pos];route.append((prev,pos,idx));pos=prev
                return list(reversed(route))
            q.append((target,depth+1))
    return None

def check_path(clauses,a,b,route):
    at=a
    for frm,to,idx in route:
        need(frm==at and 0<=idx<len(clauses),"disconnected binary proof")
        need(len(clauses[idx])==2 and sorted(clauses[idx])==sorted((-frm,to)),
             "binary proof not in original source")
        at=to
    need(at==b,"binary proof wrong target")

def get_leaves(src,clauses,dirpath):
    """Replays exact XOR cubes with X24 and signed SCC-equivalent 2-way paths."""
    cert=dirpath/"native.cert";output=dirpath/"native_probe.cnf"
    try:
        p=subprocess.run([str(x24.BIN),str(src),str(cert)],
                         capture_output=True,text=True,timeout=HELPER_CAP)
    except subprocess.TimeoutExpired:return [],{}, "native_timeout"
    if p.returncode!=0:return [],{}, "native_exit_"+str(p.returncode)
    proof=x24.verify_certificate(src,cert,output) # full SOURCE replay
    leaves=[]
    for line in cert.read_text().splitlines():
        if not line.startswith("E "):continue
        rhs,vs,ids=x24.read_line(line,"E")
        leaves.append((rhs,vs,("xor",ids)))
    edges=read_binary(clauses)
    source_pairs=set()
    # Signed mutual paths, not a count of graph edges. Cap expensive BFS.
    for a in sorted((v for v in edges if v>0))[:64]:
        if len(source_pairs)>=24:break
        seen_nodes=set()
        q=collections.deque([(a,0)])
        seen_nodes.add(a)
        while q and len(seen_nodes)<80:
            x,d=q.popleft()
            if d>=3:continue
            for to,_ in edges.get(x,()):
                if to in seen_nodes:continue
                seen_nodes.add(to);q.append((to,d+1))
        for target in sorted(seen_nodes):
            if abs(target)<=a or (a,abs(target)) in source_pairs:continue
            fw=get_path(edges,a,target,max_depth=4)
            bw=get_path(edges,target,a,max_depth=4)
            if fw is None or bw is None:continue
            check_path(clauses,a,target,fw)
            check_path(clauses,target,a,bw)
            source_pairs.add((a,abs(target)))
            leaves.append((int(target<0),(a,abs(target)),("graph",(a,target,fw,bw))))
            if len(source_pairs)>=24:break
    for idx,cl in enumerate(clauses):
        if len(cl)==1:
            leaves.append((int(cl[0]>0),(abs(cl[0]),),("unit",idx)))
            if sum(1 for _,_,p in leaves if p[0]=="unit")>=12:break
    return leaves,dict(proof,graph_leaves=len(source_pairs),total_leaves=len(leaves)), "verified"

def replay(leaves,refs,clauses):
    vars_=set();rhs=0
    for index in sorted(refs):
        need(0<=index<len(leaves),"leaf index outside proof")
        b,vs,(kind,info)=leaves[index]
        if kind=="graph":
            a,target,fw,bw=info
            need(tuple(vs)==(a,abs(target)) and b==int(target<0),
                 "graph relation mislabelled")
            check_path(clauses,a,target,fw)
            check_path(clauses,target,a,bw)
        elif kind=="unit":
            need(0<=info<len(clauses) and len(clauses[info])==1 and
                 vs==(abs(clauses[info][0]),) and
                 b==int(clauses[info][0]>0),"unit proof mismatch")
        elif kind=="xor":
            need(len(vs) in (2,3,4) and len(info)==2**(len(vs)-1),
                 "incomplete parity block")
            seen=set()
            for ci in info:
                need(0<=ci<len(clauses),"source clause reference")
                cl=clauses[ci]
                need(len(cl)==len(vs) and tuple(sorted(abs(x) for x in cl))==vs,
                     "xor original clause mismatch")
                mask=sum(1<<vs.index(abs(l)) for l in cl if l<0)
                need(mask not in seen and mask.bit_count()%2==1-b,
                     "xor parity claim false")
                seen.add(mask)
        else:need(False,"unknown proof source")
        vars_.symmetric_difference_update(vs);rhs^=b
    return rhs,tuple(sorted(vars_))

def signature(left,right,output):
    cls=sorted((left["kind"],right["kind"]))
    wa,wb=sorted((len(left["vs"]),len(right["vs"])))
    shared=len(set(left["vs"])&set(right["vs"]))
    return "%s:%s|%d:%d|shared%d|out%d"%(
       cls[0],cls[1],wa,wb,shared,min(6,len(output)))

def make_grammar(leaves,clauses):
    nodes=[];seen=set()
    for i,(rhs,vs,(kind,_)) in enumerate(leaves):
        k=(rhs,vs)
        if k in seen:continue
        seen.add(k);nodes.append(dict(rhs=rhs,vs=vs,refs=frozenset({i}),
                                    kind=kind,depth=0,signature="leaf"))
    frontier=nodes[:]
    stats=dict(joins=0,levels=0)
    candidates=[]
    for depth in range(1,4):
        new=[]
        if not frontier:break
        # Compose proven subexpressions recursively, even from different
        # source representations. The learned table is not consulted here.
        for left in frontier[:70]:
            for right in nodes[:140]:
                if stats["joins"]>=MAX_JOINS or len(new)>=50:break
                if not set(left["vs"]).intersection(right["vs"]):continue
                stats["joins"]+=1
                new_vs=tuple(sorted(set(left["vs"])^set(right["vs"])))
                refs=left["refs"]^right["refs"]
                if not refs or len(refs)>10 or len(new_vs)>6:continue
                rhs=left["rhs"]^right["rhs"]
                key=(rhs,new_vs)
                if key in seen:continue
                need(replay(leaves,refs,clauses)==key,"recursive proof replay")
                row=dict(rhs=rhs,vs=new_vs,refs=refs,kind="join",
                         depth=depth,signature=signature(left,right,new_vs))
                new.append(row);seen.add(key)
                if len(new_vs)<=2:candidates.append(row)
            if stats["joins"]>=MAX_JOINS or len(new)>=50:break
        nodes.extend(new);frontier=new;stats["levels"]=depth
        if len(nodes)>MAX_ROWS:break
    return candidates,stats

def clauses_for(row):
    vs=row["vs"];rhs=row["rhs"]
    if not vs:return [()] if rhs else []
    if len(vs)==1:return [(vs[0] if rhs else -vs[0],)]
    if len(vs)==2:
        a,b=vs
        return [(-a,b),(a,-b)] if rhs==0 else [(a,b),(-a,-b)]
    return []

def structural_reward(edges,cs):
    """Training proxy: fraction of fresh binary implications under depth-3 BCP.
    This is NOT measured SAT solve acceleration."""
    reward=0
    for c in cs:
        if len(c)==0:reward+=5;continue
        if len(c)==1:reward+=2;continue
        a,b=c
        for frm,to in ((-a,b),(-b,a)):
            if get_path(edges,frm,to,max_depth=3) is None:reward+=1
    return reward

def select(leaves,candidates,clauses,model,policy):
    base={tuple(sorted(set(c))) for c in clauses}
    edges=read_binary(clauses)
    options=[];dedup=set()
    for row in candidates:
        key=(row["rhs"],row["vs"])
        if key in dedup:continue
        dedup.add(key)
        proposed=[c for c in clauses_for(row)
                  if tuple(sorted(c)) not in base]
        if not proposed:continue
        reward=structural_reward(edges,proposed)
        hist=model.get(row["signature"],{})
        average=hist.get("reward_sum",0)/max(1,hist.get("count",0))
        if policy=="learned":
            score=(average if hist.get("count",0)>=2 else 0,reward,-len(row["refs"]))
        else:score=(reward,-len(row["refs"]),-row["depth"])
        options.append((score,row,proposed,reward))
    options.sort(key=lambda z:z[0],reverse=True)
    selected=[];additional=[];seen=set(base)
    for score,row,proposed,reward in options:
        if len(selected)>=12 or len(additional)>=MAX_CLAUSES:break
        need(replay(leaves,row["refs"],clauses)==(row["rhs"],row["vs"]),
             "proof replay before inserting clauses")
        unique=[c for c in proposed if tuple(sorted(c)) not in seen]
        if len(additional)+len(unique)>MAX_CLAUSES:continue
        if not unique:continue
        for c in unique:seen.add(tuple(sorted(c)));additional.append(c)
        selected.append(dict(signature=row["signature"],depth=row["depth"],
                             width=len(row["vs"]),proof_leaves=len(row["refs"]),
                             structural_reward=reward,added=len(unique)))
    return additional,selected

def analyze(src,model,policy):
    begin=time.perf_counter()
    n,clauses=x22.read_cnf(src)
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        d=pathlib.Path(tmp)
        leaves,proof,state=get_leaves(src,clauses,d)
        if state!="verified":
            return [],dict(state=state,proof=proof,grammar={},selected=[])
        if time.perf_counter()-begin>MAX_PREP:
            return [],dict(state="budget_after_replay",proof=proof,grammar={},selected=[])
        candidates,gram=make_grammar(leaves,clauses)
        if time.perf_counter()-begin>MAX_PREP:
            return [],dict(state="budget_after_grammar",proof=proof,
                           grammar=gram,selected=[])
        added,selected=select(leaves,candidates,clauses,model,policy)
        if time.perf_counter()-begin>MAX_PREP:
            return [],dict(state="budget_after_select",proof=proof,
                           grammar=gram,selected=[])
        return added,dict(state="verified_added" if added else "verified_no_gain",
                          proof=proof,grammar=gram,selected=selected)

def train(cases):
    table={};samples=[]
    for case in cases:
        src=x22.ROOT/"cases"/case["filename"]
        need(sha(src)==case["sha256"],"training original SHA mismatch")
        _,report=analyze(src,{},"static")
        for selected in report.get("selected",[]):
            key=selected["signature"]
            d=table.setdefault(key,dict(count=0,reward_sum=0))
            d["count"]+=1;d["reward_sum"]+=selected["structural_reward"]
        samples.append(dict(sha256=case["sha256"],
                            selected=len(report.get("selected",[])),
                            reason=report["state"]))
    return table,samples

def roster():
    m=x22.verify_frozen()
    cases=sorted(m["cases"],key=lambda c:c["sha256"])
    need(len(cases)==24 and len({c["sha256"] for c in cases})==24,
         "source roster")
    return cases[:8],cases[8:16],cases[16:]

def freeze():
    trainset,testset,reserve=roster()
    ROOT.mkdir(parents=True,exist_ok=True)
    need(x24.BIN.exists(),"native helper missing")
    need(pathlib.Path("prior_x22/report.json").exists(),"X22 reference missing")
    selftest()
    table,samples=train(trainset)
    save(ROOT/"learned.json",table)
    save(ROOT/"train_report.json",samples)
    save(ROOT/"manifest.json",dict(protocol=PROTO,arms=ARMS,
         train=[dict(c) for c in trainset],cases=[dict(c) for c in testset],
         reserve=[dict(c) for c in reserve],cap_s=CAP,shards=SHARDS,
         repetitions=REPS,expected_trials=EXPECTED,
         parent_run=42598222415,parent_x22_run=42591977333,
         x22_manifest_sha=sha(x22.ROOT/"manifest.json"),
         x22_report_sha=sha("prior_x22/report.json"),
         x24_cpp_sha=sha("research/drnas_x24_gf2_proof_first.cpp"),
         x24_bin_sha=sha(x24.BIN),code_sha=sha(__file__),
         learned_sha=sha(ROOT/"learned.json"),
         training_does_not_use_evaluation_sha=True,
         training_only_structural_proxy=True,not_blind=True,
         independent_LRAT=False,no_auto_promotion=True))
    verify()
    print("LEGO1_FROZEN",json.dumps(dict(train=len(trainset),
       eval=len(testset),reserve=len(reserve),rules=len(table),
       trials=EXPECTED),sort_keys=True),flush=True)

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    tr,ev,rs=roster()
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         m["expected_trials"]==EXPECTED and m["cap_s"]==CAP and
         [x["sha256"] for x in ev]==[x["sha256"] for x in m["cases"]] and
         [x["sha256"] for x in tr]==[x["sha256"] for x in m["train"]],
         "protocol/roster drift")
    need(m["code_sha"]==sha(__file__) and
         m["learned_sha"]==sha(ROOT/"learned.json") and
         m["x24_bin_sha"]==sha(x24.BIN) and
         m["x24_cpp_sha"]==sha("research/drnas_x24_gf2_proof_first.cpp") and
         m["x22_manifest_sha"]==sha(x22.ROOT/"manifest.json") and
         m["x22_report_sha"]==sha("prior_x22/report.json"),
         "code/binary/reference drift")
    for case in m["cases"]:
        need(sha(x22.ROOT/"cases"/case["filename"])==case["sha256"],
             "evaluation SHA mismatch")
    return m

def trial(case,rep,arm,model):
    src=x22.ROOT/"cases"/case["filename"]
    need(sha(src)==case["sha256"],"original SHA mismatch")
    if arm in ("race_original","gf2_x24"):
        if arm=="race_original":
            old=x22.CAP
            try:x22.CAP=CAP;result=x22.trial(case,rep,"race_original")
            finally:x22.CAP=old
        else:
            old=x24.CAP
            try:x24.CAP=CAP;result=x24.run_gf2(case,rep)
            finally:x24.CAP=old
        result.update(protocol=PROTO,arm=arm,lego={})
        return result
    begin=time.perf_counter();cpu_before=x22.child_cpu()
    report={};added=[];status="TIMEOUT";winner=None;checked=False
    cpu=x22.cpus()
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        tmp=pathlib.Path(tmp)
        try:
            added,report=analyze(src,model, "learned" if arm=="lego_learned" else "static")
        except Exception as exc:
            added=[];report=dict(state="failed_closed",error=str(exc)[:250])
        if added:
            n,clauses=x22.read_cnf(src)
            augmented=tmp/"lego.cnf"
            with augmented.open("w") as f:
                f.write("p cnf %d %d\n"%(n,len(clauses)+len(added)))
                for c in itertools.chain(clauses,added):
                    f.write(" ".join(map(str,c))+" 0\n")
            need(len(x22.read_cnf(augmented)[1])==len(clauses)+len(added),
                 "augmentation invalid")
            chosen=augmented
        else:chosen=src
        prep=time.perf_counter()-begin
        entries=[]
        try:
            if prep<CAP-.1:
                entries.append(x22.launch("kissat",[x22.KISSAT,
                    "--seed="+str(x22.seed(case,rep)),src],cpu[0],tmp))
                entries.append(x22.launch("cadical",[x22.CADICAL,chosen],cpu[1],tmp))
                original=x22.read_cnf(src)[1]
                while time.perf_counter()-begin<CAP:
                    for entry in entries:
                        if entry["read"] or entry["p"].poll() is None:continue
                        entry["read"]=True
                        output,err=x22.read_output(entry)
                        status,checked=x22.solver_result(
                           entry["name"],entry["p"].returncode,output,original,{})
                        winner=entry["name"];break
                    if winner:break
                    if all(e["read"] for e in entries):break
                    time.sleep(.003)
        finally:x22.cleanup(entries)
    elapsed=time.perf_counter()-begin
    if elapsed>CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";winner=None;checked=False
    need(sha(src)==case["sha256"],"post-run source changed")
    return dict(protocol=PROTO,arm=arm,status=status,winner=winner,
        original_sha256=case["sha256"],gbd=case["gbd"],
        rep=rep,cap_s=CAP,seed=x22.seed(case,rep),
        SAT_original_witness_verified=checked,
        UNSAT_independent_LRAT=False,lego=report,
        clauses_added=len(added),preprocessing_E2E_s=round(prep,6),
        E2E_s=round(elapsed,6),
        child_cpu_s=round(x22.child_cpu()-cpu_before,6))

def shard(i):
    m=verify();need(0<=i<SHARDS,"bad shard")
    model=json.loads((ROOT/"learned.json").read_text())
    rows=[]
    for case in m["cases"][i::SHARDS]:
        for rep in range(REPS):
            order=list(ARMS);random.Random(x22.seed(case,rep)).shuffle(order)
            for arm in order:
                row=trial(case,rep,arm,model)
                rows.append(row);save(ROOT/("shard-%d.json"%i),rows)
                print("LEGO1_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==16,"incomplete shard")
    print("LEGO1_SHARD_PASS",i,len(rows),flush=True)

def audit():
    m=verify();rows=[]
    for i in range(SHARDS):
        file=ROOT/("shard-%d.json"%i)
        need(file.exists(),"missing shard")
        part=json.loads(file.read_text())
        need(len(part)==16,"incomplete shard")
        rows+=part
    need(len(rows)==EXPECTED,"incomplete audit")
    ref=json.loads(pathlib.Path("prior_x22/report.json").read_text())
    unsat=ref["confirmed_original_UNSAT"]
    seen=set();by_source=collections.defaultdict(list)
    for row in rows:
        key=(row["original_sha256"],row["rep"],row["arm"])
        need(key not in seen and row["protocol"]==PROTO and
             row["arm"] in ARMS and row["cap_s"]==CAP,"invalid row")
        seen.add(key);by_source[key[0]].append(row)
        if row["status"]=="SAT":
            need(row["SAT_original_witness_verified"],"missing SAT source witness")
        need(not(row["status"]=="SAT" and unsat[key[0]]),
             "reference SAT/UNSAT disagreement")
    for src,rs in by_source.items():
        statuses={r["status"] for r in rs if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"SAT/UNSAT mismatch")
    stats={}
    for arm in ARMS:
        subset=[r for r in rows if r["arm"]==arm]
        accepted=[r for r in subset if r["status"]=="SAT" or
                   (r["status"]=="UNSAT" and unsat[r["original_sha256"]])]
        stats[arm]=dict(trials=len(subset),accepted_solved=len(accepted),
            verified_SAT=sum(r["status"]=="SAT" for r in accepted),
            UNSAT_cross_agreement_not_LRAT=sum(r["status"]=="UNSAT" for r in accepted),
            PAR2_s=round(sum(r["E2E_s"] if r in accepted else 2*CAP
                              for r in subset),5),
            child_CPU_s=round(sum(r["child_cpu_s"] for r in subset),5),
            proven_added_clauses=sum(r.get("clauses_added",0) for r in subset),
            proof_replayed=sum(r.get("lego",{}).get("state") in
                                ("verified_added","verified_no_gain") for r in subset),
            preprocessing_s=round(sum(r.get("preprocessing_E2E_s",0)
                                      for r in subset),5),
            fallback=sum(r.get("lego",{}).get("state","").startswith(("failed","budget","native_"))
                         for r in subset))
    base=stats["race_original"]["PAR2_s"]
    for s in stats.values():
        s["delta_PAR2_vs_original_pct"]=round(100*(s["PAR2_s"]/base-1),4)
    report=dict(protocol=PROTO,scores=stats,not_blind=True,
        training_precommitted=True,independent_LRAT=False,
        total_trials=len(rows),train_count=8,eval_count=8,reserve_count=8)
    save(ROOT/"report.json",report)
    print("LEGO1_FINAL",json.dumps(stats,sort_keys=True),flush=True)

def parity_clauses(vs,rhs):
    out=[]
    for bits in itertools.product((0,1),repeat=len(vs)):
        if sum(bits)%2==rhs:continue
        out.append(tuple(-v if bits[i] else v for i,v in enumerate(vs)))
    return out

def selftest():
    need(x24.BIN.exists(),"native GF2 binary needed")
    # Two XOR blocks plus a graph equality yield a third-level relation:
    # x1+x2+x3=0; x2+x3+x4=0; x4=x5 => x1=x5.
    clauses=parity_clauses((1,2,3),0)+parity_clauses((2,3,4),0)
    clauses.extend([(-4,5),(4,-5)])
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        d=pathlib.Path(tmp);src=d/"source.cnf"
        src.write_text("p cnf 5 %d\n"%len(clauses)+
           "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
        leaves,info,state=get_leaves(src,clauses,d)
        need(state=="verified" and len(leaves)>=3,"toy leaves missing")
        candidates,stats=make_grammar(leaves,clauses)
        need(any(r["vs"]==(1,5) and r["rhs"]==0 and r["depth"]>=2
                 for r in candidates),"recursive cross-representation join missing")
        for policy in ("static","learned"):
            added,selected=select(leaves,candidates,clauses,{},policy)
            for truth in itertools.product((False,True),repeat=5):
                model=dict(enumerate(truth,1))
                need(x22.holds(clauses,model)==
                     x22.holds(clauses+added,model),
                     "toy proof has changed truth table")
    print("LEGO1_SELFTEST_PASS recursive signed-graph GF2 cross-representation proof",
          flush=True)

if __name__=="__main__":
    ROOT.mkdir(parents=True,exist_ok=True)
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="shard":shard(a.shard)
    else:globals()[a.action]()
