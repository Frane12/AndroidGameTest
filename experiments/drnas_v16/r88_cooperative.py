#!/usr/bin/env python3
"""DRNAS R88 experimental cooperative SAT: sound bounded local BCP learning.

Splits ORIGINAL real CNFs into overlapping clause communities. Every shared
lemma is a RUP/BCP consequence of a source-clause subset plus earlier verified
lemmas. Final solve always handles the entire untouched or clause-augmented CNF.
Learning is measured separately from wall time; no learned hint can change SAT
semantics. This is exploratory (not a competition solver or a proof of speedup).
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, os, random, re, resource
import statistics, subprocess, tempfile, time
from pathlib import Path

PROTO = "DRNAS-R88-COOPERATIVE-REAL-CNF-20261104-v1"
CAP = 12.0
REPS = 2
MODES = ("clean", "cooperative", "native_r87", "cooperative_native")
MAX_CLAUSES = 160000
MAX_LITERALS = 950000
MAX_VARS = 150000
MAX_BYTES = 24 * 1024 * 1024

def require(ok, message):
    if not ok: raise RuntimeError("R88_FAIL_CLOSED " + str(message))

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
    return h.hexdigest()

def read_cnf(path):
    require(path.stat().st_size <= MAX_BYTES, "CNF exceeds bounded analysis size")
    n = m = None
    clauses, pending, literals = [], [], 0
    with open(path, "rt", encoding="ascii", errors="strict") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("c"): continue
            if s.startswith("%"): break
            if s.startswith("p "):
                require(n is None and not pending, "duplicate or late DIMACS header")
                words = s.split()
                require(len(words) == 4 and words[1] == "cnf", "non-CNF input")
                n, m = map(int, words[2:])
                require(0 <= n <= MAX_VARS and 0 <= m <= MAX_CLAUSES, "scope caps")
                continue
            require(n is not None, "DIMACS header missing")
            for token in s.split():
                x = int(token)
                if x == 0:
                    clauses.append(tuple(pending))
                    pending = []
                    require(len(clauses) <= m, "clause count exceeds DIMACS")
                else:
                    require(0 < abs(x) <= n, "literal out of range")
                    pending.append(x)
                    literals += 1
                    require(literals <= MAX_LITERALS, "literal cap")
    require(n is not None and len(clauses) == m and not pending,
            "truncated DIMACS")
    return n, clauses

def fingerprint(n, clauses):
    size = len(clauses)
    hist = collections.Counter(map(len, clauses))
    degree = collections.Counter(abs(x) for c in clauses for x in c)
    horn = sum(sum(x > 0 for x in c) <= 1 for c in clauses)
    neg = sum(x < 0 for c in clauses for x in c)
    lits = sum(hist[k]*k for k in hist)
    dsu = {}
    def find(x):
        dsu.setdefault(x,x)
        while dsu[x] != x:
            dsu[x] = dsu[dsu[x]]
            x = dsu[x]
        return x
    def union(a,b):
        a,b = find(a),find(b)
        if a != b: dsu[b] = a
    for clause in clauses:
        if len(clause) > 1:
            root=abs(clause[0])
            for x in clause[1:]: union(root,abs(x))
        elif clause: find(abs(clause[0]))
    components=len({find(x) for x in degree})
    binary_frac=hist[2]/max(1,size)
    horn_frac=horn/max(1,size)
    if components >= 2 and size >= 10: label="disconnected"
    elif horn_frac >= .9: label="horn_dominant"
    elif binary_frac >= .65: label="binary_implication"
    elif hist[3]/max(1,size) >= .7: label="three_cnf"
    elif max(degree.values(),default=0) >= 0.16*max(1,size): label="hub_heavy"
    else: label="mixed_general"
    top=sum(v for _,v in degree.most_common(max(1,len(degree)//100)))
    return dict(variables=n,clauses=size,literals=lits,
        active_variables=len(degree),components=components,
        unit=hist[1],binary=hist[2],ternary=hist[3],
        horn_fraction=round(horn_frac,6),
        binary_fraction=round(binary_frac,6),
        positive_fraction=round(1-neg/max(1,lits),6),
        top_one_pct_degree_share=round(top/max(1,lits),6),
        structure=label)

def partition(clauses, k=4, limit=2400):
    degrees=collections.Counter(abs(lit) for clause in clauses for lit in clause)
    groups=[[] for _ in range(k)]
    coverage=collections.defaultdict(set)
    for idx,clause in enumerate(clauses):
        # Stable hub anchor: clauses sharing strong variables tend to meet.
        if clause:
            pivot=max((abs(x) for x in clause),key=lambda x:(degrees[x],-x))
            group=(pivot*2654435761 & 0xffffffff)%k
        else: group=idx%k
        if len(groups[group]) < limit:
            groups[group].append(tuple(clause))
            for x in clause: coverage[abs(x)].add(group)
    bridges=[x for x,g in coverage.items() if len(g)>1]
    bridges.sort(key=lambda x:(-degrees[x],x))
    return groups, bridges, degrees

def bcp_conflict(clauses, assumptions, collect=False):
    """BCP/RUP with optional full local implication trail for safe exchange."""
    index=collections.defaultdict(list)
    for idx,clause in enumerate(clauses):
        for x in {abs(t) for t in clause}:index[x].append(idx)
    assignment={}
    queue=collections.deque()
    def reply(flag):
        if not collect:return flag
        return flag,tuple(x if val else -x for x,val in assignment.items())
    def add(lit):
        x=abs(lit);val=lit>0
        if x in assignment:return assignment[x]==val
        assignment[x]=val;queue.append(x)
        return True
    for literal in assumptions:
        if not add(literal):return reply(True)
    for clause in clauses:
        if not clause:return reply(True)
        if len(clause)==1 and not add(clause[0]):return reply(True)
    while queue:
        var=queue.popleft()
        for idx in index[var]:
            clause=clauses[idx]
            remaining=0;unassigned=0;satisfied=False
            for lit in clause:
                val=assignment.get(abs(lit))
                if val is None:remaining=lit;unassigned+=1
                elif val==(lit>0):
                    satisfied=True;break
            if satisfied:continue
            if not unassigned:return reply(True)
            if unassigned==1 and not add(remaining):return reply(True)
    return reply(False)

def assumptions_for_round(bridges, rnd, budget=24):
    # Probe both polarities and a few 2-variable cuts. No outcome screening.
    top=bridges[:min(len(bridges),8)]
    candidates=[()] if rnd==0 else []
    candidates += [(x,) for x in top] + [(-x,) for x in top]
    pairs=[]
    for i in range(len(top)):
        for j in range(i+1,len(top)):
            x,y=top[i],top[j]
            for a,b in ((x,y),(x,-y),(-x,y),(-x,-y)):
                pairs.append((a,b))
    if pairs:
        offset=(rnd*7) % len(pairs)
        candidates+=pairs[offset:]+pairs[:offset]
    return candidates[:budget]

def cooperative_learn(clauses, max_lemmas=48, rounds=3):
    """Inductive, cross-community exchange of certified unit/binary/ternary.

    RUP test: F_local + previously shared true clauses + negated candidate
    must conflict by BCP. Consequently every exported lemma is entailed by
    the original formula. Cross influence counts only lemmas NOT already
    provable by BCP from the sender's local clauses alone.
    """
    start=time.monotonic()
    # Large original CNFs remain exact for global solve; local proof
    # communities use a deterministic subset to avoid expensive analysis.
    stride=max(1,(len(clauses)+11999)//12000)
    sample=clauses[::stride]
    groups,bridges,degrees=partition(sample,limit=1800)
    ledger=[];known=set();shared=[];total_probes=0
    cross_received=0;useful_after_share=0;causal_cross=0
    # Finite proactive budget even when hard formulas time out.
    deadline=start+(0.45 if len(clauses)<=25000 else 0.8)
    active=sum(bool(g) for g in groups)
    for rnd in range(rounds):
        newest=[]
        for group_id,local in enumerate(groups):
            if not local:continue
            premises=local+shared
            seen_before=len(shared)
            group_count=0
            for assumptions in assumptions_for_round(bridges,rnd,budget=18):
                if (len(ledger)>=max_lemmas or
                    group_count>=max(3,max_lemmas//max(1,active)) or
                    time.monotonic()>=deadline):break
                total_probes+=1
                conflict,trail=bcp_conflict(premises,assumptions,collect=True)
                candidates=[]
                if conflict:
                    candidates=[tuple(-x for x in assumptions)]
                else:
                    # F and assumptions imply every BCP-trail literal. Negate
                    # the guard, then append the proven consequent.
                    guarded=tuple(-x for x in assumptions)
                    for implied in trail:
                        if implied not in assumptions:
                            candidates.append(guarded+(implied,))
                candidates.sort(key=lambda cl:(len(cl),-max(
                    (degrees[abs(t)] for t in cl),default=0),tuple(cl)))
                for raw in candidates[:12]:
                    if (len(ledger)>=max_lemmas or
                        group_count>=max(3,max_lemmas//max(1,active))):break
                    lemma=tuple(sorted(set(raw),key=lambda x:(abs(x),x)))
                    if lemma in known or any(-x in lemma for x in lemma):
                        continue
                    # Independently replay RUP on exactly the frozen sender
                    # community and the prior, already certified broadcasts.
                    if not bcp_conflict(premises,tuple(-x for x in lemma)):
                        continue
                    known.add(lemma);newest.append(lemma);group_count+=1
                    cross=bool(seen_before) and not bcp_conflict(
                        local,tuple(-x for x in lemma))
                    causal_cross+=int(cross)
                    ledger.append(dict(lemma=list(lemma),from_group=group_id,
                        round=rnd,prior_shared=seen_before,bcp_verified=True,
                        causal_cross_group=cross))
                    if seen_before:useful_after_share+=1
        if newest:
            shared.extend(newest)
            cross_received+=len(newest)*max(0,active-1)
        if time.monotonic()>=deadline:break
    require(len(shared)<=max_lemmas and len(ledger)<=max_lemmas,
            "certified lemma hard cap violated")
    preceding=[]
    for item in ledger:
        local=groups[item["from_group"]]
        require(bcp_conflict(local+preceding[:item["prior_shared"]],
                             [-x for x in item["lemma"]]),
                "proof-chain replay failed")
        preceding.append(tuple(item["lemma"]))
    return shared,dict(communities=active,
        community_sizes=[len(g) for g in groups],bridge_variables=len(bridges),
        probes=total_probes,certified_lemmas=len(shared),
        broadcasts=cross_received,lemmas_after_prior_sharing=useful_after_share,
        causal_cross_group_lemmas=causal_cross,
        sampled_clauses=len(sample),time_bounded=True,
        proof_chain=ledger)

def write_augmented(n, clauses, extras, target):
    with open(target,"w") as f:
        f.write(f"p cnf {n} {len(clauses)+len(extras)}\n")
        for clause in list(clauses)+list(extras):
            f.write(" ".join(map(str,clause))+" 0\n")

def memory_limit():
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))

def solve(exe, source, original, cap, native=False):
    import r32p_real_satcomp26_benchmark as reference
    env=os.environ.copy()
    if native:
        env.update(R32B_MODE="r32u",R32U_ACTIVE="1",R87_ADAPT="1",
                   R84_SCAN_EVERY="16",R85_DIVERSE="0",R85_CAP="64")
    start=time.monotonic()
    try:
        p=subprocess.run([str(exe),str(source)],env=env,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,errors="replace",timeout=cap,preexec_fn=memory_limit)
        require(p.returncode in (10,20),
                f"solver error code {p.returncode} {p.stderr[-300:]}")
        answer="SAT" if p.returncode==10 else "UNSAT"
        if answer=="SAT": reference.verify_sat_witness(original,p.stdout)
    except subprocess.TimeoutExpired:answer="TIMEOUT"
    elapsed=time.monotonic()-start
    if elapsed>cap:answer="TIMEOUT"
    return dict(answer=answer,wall_s=round(min(cap,elapsed),6),
                par2_s=round(2*cap if answer=="TIMEOUT" else elapsed,6),
                witness_verified=answer=="SAT")

def measure(args):
    root=Path(args.sources).resolve()
    manifest=json.loads((root/"manifest.json").read_text())
    require(manifest["protocol"]=="DRNAS-R88-BULK-OFFICIAL-CNF-20261104-v1",
            "wrong source manifest")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    compiled=Path(args.compiled).resolve()
    for binary in ("clean","native-r87"):
        require((compiled/binary).is_file(),f"missing {binary}")
    require(subprocess.run(["sha256sum","-c","r87-binaries.sha256"],
        cwd=compiled,capture_output=True).returncode==0,"binary SHA mismatch")
    os.chmod(compiled/"clean",0o755);os.chmod(compiled/"native-r87",0o755)
    if hasattr(os,"sched_setaffinity"):
        cpu=min(os.sched_getaffinity(0))
        os.sched_setaffinity(0,{cpu})
    rows=[]
    for case in manifest["cases"]:
        source=root/case["filename"]
        require(sha(source)==case["sha256"],"original CNF SHA mismatch")
        t=time.monotonic()
        n,clauses=read_cnf(source)
        features=fingerprint(n,clauses)
        extras,telemetry=cooperative_learn(clauses)
        with tempfile.TemporaryDirectory() as folder:
            augmented=Path(folder)/"augmented.cnf"
            write_augmented(n,clauses,extras,augmented)
            prep_s=time.monotonic()-t
            for rep in range(REPS):
                modes=list(MODES)
                random.Random(int(hashlib.sha256((case["sha256"]+
                    str(rep)+PROTO).encode()).hexdigest(),16)).shuffle(modes)
                for mode in modes:
                    cooperative="cooperative" in mode
                    native="native" in mode
                    exe=compiled/("native-r87" if native else "clean")
                    result=solve(exe,augmented if cooperative else source,
                                 source,CAP,native=native)
                    if cooperative:
                        result["total_s"]=round(prep_s+result["wall_s"],6)
                        result["total_par2_s"]=round(prep_s+result["par2_s"],6)
                    else:
                        result["total_s"]=result["wall_s"]
                        result["total_par2_s"]=result["par2_s"]
                    expected=case.get("official_status","UNKNOWN")
                    if expected in ("SAT","UNSAT") and result["answer"]!="TIMEOUT":
                        require(result["answer"]==expected,
                                "disagrees with published verified official status")
                    row=dict(protocol=PROTO,source_sha=case["sha256"],
                        source_id=case["gbd"],year=case["year"],
                        index_sha=manifest["index_sha256"],rep=rep,
                        mode=mode,run_id=os.environ.get("GITHUB_RUN_ID","local"),
                        commit=os.environ.get("R88_CODE_SHA",os.environ.get("GITHUB_SHA","local")),
                        prior_tested=case.get("historically_used","unknown"),
                        **features,**{k:v for k,v in telemetry.items() if k!="proof_chain"},
                        prep_s=round(prep_s,6),**result)
                    rows.append(row)
                    print("R88_TRIAL",json.dumps(dict(source=case["gbd"],
                        mode=mode,rep=rep,answer=result["answer"],
                        par2=result["total_par2_s"],lemmas=len(extras))),flush=True)
                    (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
        require(len(rows)% (REPS*len(MODES))==0,"paired case incomplete")
    expected=len(manifest["cases"])*REPS*len(MODES)
    require(len(rows)==expected,"incomplete experiment")
    print("R88_MEASURE_PASS",args.year,args.shard,len(rows),flush=True)

def selftest():
    # F1=(a), F2=(not a or b), F3=(not b) is UNSAT.
    clauses=[(1,),(-1,2),(-2,)]
    require(bcp_conflict(clauses,()),"unsat core")
    require(not bcp_conflict([(1,2)],()),"SAT unit propagation")
    require(bcp_conflict([(1,2)],(-1,-2)),"assumption conflict")
    conflict,trail=bcp_conflict([(-1,2),(-2,3)],(1,),collect=True)
    require(not conflict and 3 in trail,"cross-subproblem implied literal")
    require(bcp_conflict([(-1,2),(-2,3)],(1,-3)),
            "source-certified guarded implication")
    require(not bcp_conflict([(1,2)],(-1,)),"compatible assumptions")
    n=3
    f=fingerprint(n,clauses)
    require(f["clauses"]==3 and f["unit"]==2,"feature count")
    extras,t=cooperative_learn(clauses)
    require(all(x["bcp_verified"] for x in t["proof_chain"]),"certs")
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/"f.cnf"
        write_augmented(n,clauses,extras,p)
        require(len(read_cnf(p)[1])==len(clauses)+len(extras),"DIMACS rewrite")
    print("R88_LOCAL_COOP_SOUNDNESS_SELFTEST_PASS",len(extras))

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    q=sub.add_parser("measure")
    q.add_argument("--sources",required=True);q.add_argument("--compiled",required=True)
    q.add_argument("--year",type=int,required=True);q.add_argument("--shard",type=int,required=True)
    q.add_argument("--out",required=True)
    a=p.parse_args()
    if a.cmd=="selftest":selftest()
    else:measure(a)

if __name__=="__main__":main()
