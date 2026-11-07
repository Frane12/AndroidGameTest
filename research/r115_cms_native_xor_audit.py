#!/usr/bin/env python3
"""R115 source-equivalent CNF -> native CryptoMiniSat XNF ablation; every 3-XOR block truth-table checked."""
import csv, hashlib, itertools, json, pathlib, re, statistics, subprocess, sys, time
from collections import defaultdict
root=pathlib.Path("r115_cms_native");root.mkdir(exist_ok=True)
cnf=root/"r115.cnf"
assert hashlib.sha256(cnf.read_bytes()).hexdigest()=="243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83"
n=250;clauses=[];cur=[]
for line in cnf.read_text().splitlines():
    if not line.strip() or line.startswith(("c","%","p")):continue
    for v in map(int,line.split()):
        if v==0:clauses.append(cur);cur=[]
        else:cur.append(v)
assert len(clauses)==1000 and not cur
groups=defaultdict(list)
for clause in clauses:
    variables=tuple(sorted(map(abs,clause)))
    assert len(variables)==3 and len(set(variables))==3
    groups[variables].append(clause)
assert len(groups)==250
lines=[f"p cnf {n} {len(groups)}"]
for vars_,group in sorted(groups.items()):
    assert len(group)==4
    masks=set()
    for clause in group:
        neg={abs(v) for v in clause if v<0}
        masks.add(sum(1<<j for j,v in enumerate(vars_) if v in neg))
    assert len(masks)==4
    parity={x.bit_count()%2 for x in masks}
    assert len(parity)==1
    rhs=1-next(iter(parity))
    assert masks=={i for i in range(8) if i.bit_count()%2==(1-rhs)}
    for bits in itertools.product((0,1),repeat=3):
        assign=dict(zip(vars_,bits))
        cnf_eval=all(any(bool(assign[abs(l)])==(l>0) for l in clause) for clause in group)
        xor_eval=((sum(bits)%2)==rhs)
        assert cnf_eval==xor_eval
    vl=list(vars_)
    if rhs==0:vl[0]=-vl[0]
    lines.append("x"+" ".join(map(str,vl))+" 0")
xnf=root/"r115_native_xor.xnf"
xnf.write_text("\n".join(lines)+"\n")
print("R115_XNF",json.dumps(dict(sha256=hashlib.sha256(xnf.read_bytes()).hexdigest(),xor_equations=250,verified_blocks=250)),flush=True)
def check(output):
    sat=bool(re.search(r"^s\s+SATISFIABLE\b",output,re.M))
    if not sat:return "UNSAT" if re.search(r"^s\s+UNSATISFIABLE\b",output,re.M) else "ERROR",False
    model={}
    for line in output.splitlines():
        if line.startswith("v "):
            for lit in map(int,line[2:].split()):
                if lit:model[abs(lit)]=lit>0
    if not model:return "INVALID_MODEL",False
    good=all(any(model.get(abs(l))==(l>0) for l in cl) for cl in clauses)
    return ("SAT" if good else "INVALID_MODEL"),good
modes={
"r28_source_cnf":["./r115_cms_native/r28",str(cnf),"/bin/false"],
"cms_source_cnf_gauss":["cryptominisat5","--threads=1","--autodisablegauss=0","--maxnummatrices=5","--verb=2",str(cnf)],
"cms_native_xor_gauss":["cryptominisat5","--threads=1","--autodisablegauss=0","--maxnummatrices=5","--verb=2",str(xnf)],
"cms_native_xor_no_matrix":["cryptominisat5","--threads=1","--maxnummatrices=0","--verb=2",str(xnf)],
}
rows=[]
for rep in range(3):
    names=list(modes)
    if rep%2:names.reverse()
    for name in names:
        t=time.perf_counter()
        try:
            p=subprocess.run(modes[name],capture_output=True,text=True,timeout=20)
            sec=time.perf_counter()-t
            out=p.stdout+"\n"+p.stderr
            status,ok=check(out);rc=p.returncode
        except subprocess.TimeoutExpired as e:
            sec=20.;status="TIMEOUT";ok=False;rc=124
            out=(e.stdout or b"").decode(errors="replace") if isinstance(e.stdout,bytes) else (e.stdout or "")
            out+="\nTIMEOUT"
        (root/f"{name}-rep{rep}.log").write_text(out)
        row=dict(rep=rep,mode=name,status=status,elapsed_s=round(sec,6),original_cnf_model_verified=ok,exit_code=rc)
        rows.append(row)
        print("R115_NATIVE_TRIAL",json.dumps(row,sort_keys=True),flush=True)
summary={}
for name in modes:
    trials=[r for r in rows if r["mode"]==name]
    solved=[r for r in trials if r["status"]=="SAT"]
    summary[name]=dict(sat=len(solved),total=len(trials),timeouts=sum(r["status"]=="TIMEOUT" for r in trials),
        median_s=round(statistics.median(r["elapsed_s"] for r in solved),6) if solved else None)
(root/"trials.csv").write_text("rep,mode,status,elapsed_s,original_cnf_model_verified,exit_code\n"+"".join(
 f'{r["rep"]},{r["mode"]},{r["status"]},{r["elapsed_s"]},{r["original_cnf_model_verified"]},{r["exit_code"]}\n' for r in rows))
(root/"summary.json").write_text(json.dumps(summary,indent=2))
print("R115_NATIVE_FINAL",json.dumps(summary,sort_keys=True),flush=True)
if any(r["status"] not in ("SAT","TIMEOUT") for r in rows):sys.exit(2)
