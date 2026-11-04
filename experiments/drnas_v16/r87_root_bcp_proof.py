#!/usr/bin/env python3
"""R87F2: independently replay original-CNF root BCP, then prove native GF2 rows.

The previous parity-only validator ignored root-BCP consequences used by
r32b_compute, so it can return false negatives. This is a forensic-only check.
No native solver patches, SAT-speed claims, or skipped certificates.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,subprocess
from pathlib import Path
import r32t_certified_short_xor as cert
import r83_live_xor_cdcl_wide as r83
import r87_unseen_official as holdout

def ck(v,m):
    if not v:raise RuntimeError("R87F2_FAIL_CLOSED "+str(m))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,obj):Path(p).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def parse_source(p):
    clauses=[];cur=[];n=declared=None
    for raw in Path(p).open(encoding="ascii",errors="strict"):
        line=raw.strip()
        if not line or line[0] in "c%":continue
        if line.startswith("p "):
            words=line.split()
            ck(n is None and len(words)==4 and words[1]=="cnf","invalid original header")
            n=int(words[2]);declared=int(words[3])
            ck(0<n<=4096 and 0<=declared<=60000,"native source scope exceeded")
            continue
        ck(n is not None,"missing DIMACS header")
        for token in line.split():
            lit=int(token)
            if lit:
                ck(abs(lit)<=n,"out-of-range literal")
                cur.append(lit)
            else:
                clauses.append(tuple(cur));cur=[]
    ck(n is not None and not cur and len(clauses)==declared,
       "DIMACS clause count mismatch")
    return n,clauses

def replay_root_bcp(n,original):
    """Queue-based full original CNF unit propagation with traceable premises.

    Clauses are normalized only by deleting duplicate literals/tautologies,
    preserving the original formula's logical meaning.
    """
    normalized=[];origin=[]
    for original_i,c in enumerate(original):
        seen=set(c)
        if any(-lit in seen for lit in seen):continue
        z=tuple(sorted(seen,key=lambda lit:(abs(lit),lit)))
        normalized.append(z);origin.append(original_i)
    occ=collections.defaultdict(list)
    remaining=[];satisfied=[False]*len(normalized)
    queue=collections.deque()
    for ci,c in enumerate(normalized):
        ck(len(c)>0,"original contains empty clause, root UNSAT - fail closed")
        remaining.append(len(c))
        for lit in c:occ[lit].append(ci)
        if len(c)==1:queue.append((c[0],ci))
    assigned=[0]*(n+1);trace=[]
    while queue:
        lit,ci=queue.popleft()
        var=abs(lit);val=1 if lit>0 else -1
        # An enqueued unit can become obsolete if another assignment
        # satisfied that clause first; skipping is logically mandatory.
        if satisfied[ci]:continue
        if assigned[var]:
            ck(assigned[var]==val,"BCP root conflict: no sound non-vacuous proof")
            continue
        ck(sum(assigned[abs(l)]==0 for l in normalized[ci])==1,
           "unit-premise invariant failed")
        ck(all((assigned[abs(l)]!= (1 if l>0 else -1))
               for l in normalized[ci] if abs(l)!=var),
           "unit premise not actually forcing the literal")
        assigned[var]=val
        trace.append(dict(literal=lit,clause_number=origin[ci]+1,
                          reason=[int(x) for x in normalized[ci]]))
        for j in occ[lit]:satisfied[j]=True
        for j in occ[-lit]:
            if satisfied[j]:continue
            remaining[j]-=1
            ck(remaining[j]>=0,"negative remaining count")
            if remaining[j]==0:
                raise RuntimeError("R87F2_FAIL_CLOSED original root BCP contradiction")
            if remaining[j]==1:
                unset=[q for q in normalized[j] if assigned[abs(q)]==0]
                ck(len(unset)==1,"BCP unit count inconsistent")
                queue.append((unset[0],j))
    return trace,normalized

def proof_with_bcp(original_path,emitted):
    independent,guard=cert.load_original(original_path)
    ck(guard is None,"independent original scope unsupported "+str(guard))
    n,clauses=parse_source(original_path)
    ck(independent["n"]==n and independent["clauses"]==len(clauses),
       "independent parser disagrees on original header")
    axioms=cert.complete_parity_axioms(independent)
    root,normalized=replay_root_bcp(n,clauses)
    basis={}
    contradictions=[]
    def insert(bits,rhs,kind):
        while bits:
            pivot=(bits&-bits).bit_length()
            if pivot not in basis:
                basis[pivot]=(bits,rhs,kind);return
            bits^=basis[pivot][0];rhs^=basis[pivot][1]
        if rhs:contradictions.append(kind)
    for eq,(vars_,rhs) in enumerate(axioms):
        insert(cert.to_bitrow(vars_),rhs,"original_complete_xor_"+str(eq))
    rank_parity=len(basis)
    for item in root:
        lit=item["literal"]
        insert(1<<(abs(lit)-1),int(lit>0),"original_root_bcp_clause_"+str(item["clause_number"]))
    ck(not contradictions,"inconsistent premises; cannot use ex-falso GF2 certification")
    failed=[]
    for vs,rhs in emitted:
        bits=cert.to_bitrow(vs);r=int(rhs)
        while bits:
            pivot=(bits&-bits).bit_length()
            if pivot not in basis:break
            bits^=basis[pivot][0];r^=basis[pivot][1]
        if bits or r:
            failed.append(dict(vars=list(vs),rhs=int(rhs),
               residual_vars=[i+1 for i in cert.indices_of_bits(bits)],
               residual_rhs=r))
    return dict(original_clauses=len(clauses),native_source_sha256=sha(original_path),
      complete_original_XOR_axioms=len(axioms),xor_only_rank=rank_parity,
      original_root_BCP_units=len(root),bcp_trace_sha256=hashlib.sha256(
           json.dumps(root,sort_keys=True).encode()).hexdigest(),
      root_bcp_reason_samples=root[:8],augmented_GF2_rank=len(basis),
      native_rows=len(emitted),proved=len(emitted)-len(failed),
      failed=failed[:8],sound=(len(failed)==0))

def main(a):
    root=Path(a.sources);mf=holdout.manifest(root)
    pins=Path(a.compiled)
    p=subprocess.run(["sha256sum","-c","r87-binaries.sha256"],cwd=pins,
                     capture_output=True,text=True)
    ck(p.returncode==0,"native binary pin drift")
    binary=(pins/"native-r87").resolve()
    result=[]
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    for shard,case in enumerate(mf["cases"]):
        original=(root/case["filename"]).resolve()
        ck(sha(original)==case["sha256"],"source hash mismatch")
        env=os.environ.copy()
        env.update(R32B_MODE="r32u",R32U_ACTIVE="0",R84_SCAN_EVERY="256",
          R85_CAP="64",R85_DIVERSE="0",R87_ADAPT="0",R32S_PASSIVE_TRACE="0")
        timeout=False
        try:
            p=subprocess.run([str(binary),str(original)],capture_output=True,
                            text=True,errors="replace",timeout=8,env=env)
            stdout=p.stdout
        except subprocess.TimeoutExpired as e:
            timeout=True;stdout=e.stdout or b""
            if isinstance(stdout,bytes):stdout=stdout.decode(errors="replace")
        emitted=[(tuple(int(v) for v in xs.split(",")),int(rhs))
                  for rhs,xs in r83.SOURCE_ROW.findall(stdout)]
        proof=proof_with_bcp(original,emitted)
        data=dict(shard=shard,gbd=case["gbd"],year=case["year"],
           sha256=case["sha256"],group=case["group"],
           runner=os.environ.get("RUNNER_NAME",""),
           commit=os.environ.get("GITHUB_SHA",""),
           native_binary_sha256=sha(binary),timeout=timeout,**proof)
        result.append(data)
        print("R87F2_BCP_AUGMENTED_PROOF",json.dumps(dict(shard=shard,
            gbd=case["gbd"],axioms=proof["complete_original_XOR_axioms"],
            bcp=proof["original_root_BCP_units"],
            emitted=proof["native_rows"],proved=proof["proved"],
            failures=proof["failed"][:2])),flush=True)
        save(out/"partial.json",dict(protocol="R87-ROOT-BCP-INDEPENDENT-v1",rows=result))
    ck(len(result)==8,"incomplete forensic sample")
    save(out/"r87-bcp-augmented-proof.json",
         dict(protocol="R87-ROOT-BCP-INDEPENDENT-v1",
              status="FORENSIC_NOT_BENCHMARK",
              original_manifest_sha256=sha(root/"manifest.json"),
              native_binary_sha256=sha(binary),
              all_proved=all(x["sound"] for x in result),sources=result))
    print("R87F2_FINAL_FORENSIC_PASS",len(result),
          "all_proved",all(x["sound"] for x in result),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--sources",required=True)
    p.add_argument("--compiled",required=True)
    p.add_argument("--out",required=True)
    main(p.parse_args())
