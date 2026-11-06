#!/usr/bin/env python3
"""R166x: source-certified GF(2) subset reasoning for MIXED original CNF.

Only complete original parity CNF blocks (width 2..6) and source units
authorize equations. Derive sparse 2..8 variable consequences by bounded
2-,3-,4-way XOR combinations with a replayable source-row combination.
Additionally, full-source Gaussian RREF may imply standalone unit clauses,
and a replayed 0=1 XOR contradiction is an UNSAT certificate for the *whole*
mixed CNF (even with residual non-XOR clauses). This does not generate LRAT.
All derived rows are independently replayed from selected source-certified
rows; no probabilistic GF2 guess and no use of labels to choose candidates.
"""
import argparse,collections,hashlib,json,math,pathlib,random,tempfile
import r164_pure_exact_gf2 as exact

MAX_DERIVED=120
MAX_UNITS=64
MAX_BEAM=384

def need(c,m):
    if not c:raise RuntimeError("R166X_PROOF_FAIL "+str(m))
def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def bits(mask):
    while mask:
        bit=mask&-mask
        yield bit.bit_length()   # 1-based DIMACS variable
        mask^=bit
def maskof(vs):
    z=0
    for v in vs:
        need(v>0 and not(z>>(v-1)&1),"invalid xor row")
        z|=1<<(v-1)
    return z

def source_equations(clauses):
    # Rebuild source complete parity truth-tables independently.
    groups=collections.defaultdict(set)
    units={}
    for clause in clauses:
        if len(clause)==1:
            v=abs(clause[0]); val=int(clause[0]>0)
            if v in units and units[v]!=val:
                # Both source units are retained for contradiction.
                pass
            else:units[v]=val
        if not 2<=len(clause)<=6 or len({abs(x) for x in clause})!=len(clause):
            continue
        a=sorted(clause,key=abs)
        groups[tuple(abs(v) for v in a)].add(sum((1<<i) for i,v in enumerate(a) if v<0))
    eq=[]
    for c in clauses:
        if len(c)==1:
            eq.append(((abs(c[0]),),int(c[0]>0)))
    for vs,masks in sorted(groups.items()):
        for parity in (0,1):
            prohibited={m for m in range(1<<len(vs)) if m.bit_count()%2==parity}
            if prohibited <= masks:
                eq.append((vs,1-parity))
    return eq,groups,units

def check_selected(ev,groups,units):
    result=[]
    for e in ev["selected"]:
        vs=tuple(e["source_vars"]);rhs=e["source_rhs"]
        need(2<=len(vs)<=6 and tuple(sorted(set(vs)))==vs,"source vars invalid")
        banned={i for i in range(1<<len(vs)) if i.bit_count()%2==1-rhs}
        need(banned<=groups[vs],"selected XOR NOT implied by source clauses")
        remain=tuple(v for v in vs if v not in units)
        rr=rhs
        for v in vs:
            if v in units:rr^=units[v]
        need(tuple(e["vars"])==remain and rr==e["rhs"],
             "source original unit substitution disagrees")
        need(2<=len(remain)<=6,"bad selected row")
        result.append((maskof(remain),rr))
    return result

def gaussian_full(eq):
    # Proof combination indices refer to independently source-reconstructed
    # XOR equations, including source unit clauses.
    piv={}
    for idx,(vs,rhs) in enumerate(eq):
        m=maskof(vs);parity=rhs;prov=1<<idx
        while m:
            lo=m&-m
            if lo not in piv:
                piv[lo]=(m,parity,prov)
                break
            q,b,p=piv[lo];m^=q;parity^=b;prov^=p
        else:
            if parity:
                verify_proof(eq,0,1,prov)
                return {"rank":len(piv),"unsat":prov,"units":[]}
    # Reverse Gauss-Jordan for implied *single-variable* consequences.
    for lead in sorted(piv.keys(),reverse=True):
        m,b,p=piv[lead]
        for other in sorted(piv.keys()):
            if other>=lead:break
            z,r,pr=piv[other]
            if z&lead:piv[other]=(z^m,r^b,pr^p)
    result=[]
    for m,b,p in piv.values():
        if m.bit_count()==1:
            verify_proof(eq,m,b,p)
            result.append((m,b,p))
    return {"rank":len(piv),"unsat":0,"units":result}

def verify_proof(rows,target_mask,target_rhs,prov):
    mm=0;rr=0;ids=[]
    for i in bits(prov):
        idx=i-1
        need(idx<len(rows),"provenance outside source")
        vs,rhs=rows[idx]
        mm^=maskof(vs);rr^=rhs;ids.append(idx)
    need(ids and mm==target_mask and rr==target_rhs,
         "derived combination not equal to original equations")
    return ids

def residual_frequencies(clauses,source_eq):
    complete={}
    for vs,rhs in source_eq:
        if len(vs)<=1:continue
        complete[(vs,1-rhs)]=True
    freq=collections.Counter()
    binary=collections.Counter()
    for c in clauses:
        if len(c)==1:continue
        if 2<=len(c)<=6 and len(set(map(abs,c)))==len(c):
            order=sorted(c,key=abs);vs=tuple(abs(x) for x in order)
            parity=sum(x<0 for x in order)%2
            if complete.get((vs,parity)):continue
        for v in c:freq[abs(v)]+=1
        if len(c)==2:
            for v in c:binary[abs(v)]+=1
    return freq,binary

def rank_score(mask,orig,freq,binary,seen_output):
    vs=tuple(bits(mask));width=len(vs)
    hits=sum(min(freq[v],160) for v in vs)
    bin_hits=sum(min(binary[v],90) for v in vs)
    distinct=sum(freq[v]>0 for v in vs)
    # A short derived XOR relating variables already in non-XOR clauses
    # is more likely to affect CDCL than an isolated parity subsystem.
    overlap_penalty=sum(v in seen_output for v in vs)
    gain=(math.log2(1+hits)*4+math.log2(1+bin_hits)*2+distinct*2)
    return (gain/(width**1.8)+0.12*min(orig.bit_count(),5)
            -0.25*overlap_penalty/width)

def candidates(selected,freq,binary,max_extra=MAX_DERIVED):
    base=[(m,b,1<<i) for i,(m,b) in enumerate(selected)]
    origseen={(m,b) for m,b in selected}
    # Keep the shortest proof for every inferred equation.
    found={}
    def put(m,b,p):
        width=m.bit_count()
        if not 2<=width<=8 or (m,b) in origseen:return
        k=(m,b)
        old=found.get(k)
        if old is None or p.bit_count()<old.bit_count():
            found[k]=p
    # Stage 1: source pairs, with low-width wider intermediates for
    # three/four-way Gaussian cancellation.
    partial=[]
    n=len(base)
    for i in range(n):
        x,b,p=base[i]
        for j in range(i+1,n):
            y,c,q=base[j]
            if (x&y)==0:continue
            m=x^y;bit=b^c;pro=p^q
            if m.bit_count()>12:continue
            partial.append((m,bit,pro))
            put(m,bit,pro)
    partial.sort(key=lambda z:(z[0].bit_count(),-rank_score(z[0],z[2],freq,binary,set()),z[0],z[1]))
    beam=partial[:MAX_BEAM]
    # Stage 2: 3 and 4-source bounded sparse elimination.
    for step in (3,4):
        nxt={}
        for m,b,p in beam:
            for x,y,q in base:
                if not(m&x):continue
                mm=m^x
                if mm.bit_count()>12:continue
                par=b^y;prov=p^q
                if prov==0:continue
                put(mm,par,prov)
                key=(mm,par)
                old=nxt.get(key)
                if old is None or prov.bit_count()<old.bit_count():
                    nxt[key]=prov
        beam=sorted(((m,b,p) for (m,b),p in nxt.items()),
            key=lambda z:(z[0].bit_count(),
                          -rank_score(z[0],z[2],freq,binary,set()),
                          z[0],z[1]))[:MAX_BEAM]
    # Reserve space for 3+ source consequences, unlike R165's only-pairwise
    # closure; all candidates are exact GF2 XOR combinations.
    multi=[(m,b,p) for (m,b),p in found.items() if p.bit_count()>=3]
    pair=[(m,b,p) for (m,b),p in found.items() if p.bit_count()==2]
    selected_rows=[];picked=set();used=set()
    def harvest(cands,limit):
        order=sorted(cands,key=lambda z:(-rank_score(z[0],z[2],freq,binary,used),
                                          z[0].bit_count(),z[0],z[1]))
        for m,b,p in order:
            if len(selected_rows)>=limit:break
            if (m,b) in picked:continue
            verify_proof([(tuple(bits(x)),r) for x,r in selected],m,b,p)
            selected_rows.append((m,b,p))
            picked.add((m,b));used.update(bits(m))
    harvest(multi,min(max_extra,max(0,max_extra*3//4)))
    harvest(multi+pair,max_extra)
    return selected_rows,dict(pairwise_candidates=len(pair),
      multiway_candidates=len(multi),
      multiway_selected=sum(p.bit_count()>=3 for _,_,p in selected_rows))

def prepare(source,ev,output_dir,max_derived=MAX_DERIVED):
    source=pathlib.Path(source);out=pathlib.Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    n,clauses=exact.parse_dimacs(source)
    ownsha=sha(source)
    need(ownsha==ev["source_sha256"],"source SHA differs from R157 evidence")
    source_eq,groups,units=source_equations(clauses)
    selected=check_selected(ev,groups,units)
    gf=gaussian_full(source_eq)
    freq,binary=residual_frequencies(clauses,source_eq)
    source_masks={m for m,b in selected}
    implied_units=[]
    for m,b,p in gf["units"]:
        v=m.bit_length()
        if v in units:continue
        implied_units.append((m,b,p))
    implied_units.sort(key=lambda z:(-freq[z[0].bit_length()],z[0]))
    implied_units=implied_units[:MAX_UNITS]
    advanced,meta=candidates(selected,freq,binary,max_derived)
    for m,b,p in advanced:verify_proof([(tuple(bits(z)),r) for z,r in selected],m,b,p)
    for m,b,p in implied_units:verify_proof(source_eq,m,b,p)
    if gf["unsat"]:verify_proof(source_eq,0,1,gf["unsat"])
    # A native rows TSV contains source-certified original selected rows
    # followed by independently replay-verified advanced consequences.
    tsv=out/"gauss.tsv"
    lines=[f"{m.bit_count()} {b} "+" ".join(map(str,bits(m)))+"\n" for m,b in selected]
    lines += [f"{m.bit_count()} {b} "+" ".join(map(str,bits(m)))+"\n" for m,b,_ in advanced]
    need(len(lines)<=300,"native row input cap exceeded")
    tsv.write_text("".join(lines))
    unitfile=out/"gauss-units.tsv"
    unitfile.write_text("".join(f"{v[0].bit_length()} {v[1]}\n" for v in implied_units))
    proof_rows=[dict(vars=list(bits(m)),rhs=b,source_indices=verify_proof(
        [(tuple(bits(z)),r) for z,r in selected],m,b,p),
         coefficient_size=p.bit_count()) for m,b,p in advanced]
    proof_units=[dict(var=m.bit_length(),rhs=b,source_indices=verify_proof(
        source_eq,m,b,p),coefficient_size=p.bit_count()) for m,b,p in implied_units]
    contradiction=verify_proof(source_eq,0,1,gf["unsat"]) if gf["unsat"] else []
    certificate=dict(protocol="R166X-SOURCE-VERIFIED-MIXED-GAUSS-v1",
        source_sha256=ownsha,source_selected_rows=len(selected),
        source_full_equations=len(source_eq),rank=gf["rank"],
        source_clauses=len(clauses),source_variables=n,
        derived_short_rows=len(advanced),derived_units=len(implied_units),
        contradiction_found=bool(contradiction),contradiction_original_indices=contradiction,
        derived=proof_rows,units=proof_units,
        proof_origin="original CNF complete XOR truth tables and original units",
        caveat="No LRAT/FRAT; contradiction replayed in GF2, not proof in CNF proof format",**meta)
    report=out/"gauss-cert.json"
    report.write_text(json.dumps(certificate,sort_keys=True,indent=2)+"\n")
    result=dict(source_sha256=ownsha,tsv=str(tsv),units_tsv=str(unitfile),certificate=str(report),
        rows_sha256=sha(tsv),unit_sha256=sha(unitfile),certificate_sha256=sha(report),
        derived_short_rows=len(advanced),derived_units=len(implied_units),**meta,
        contradiction_found=bool(contradiction),source_selected_rows=len(selected))
    print("R166X_CERT_PASS",json.dumps(result,sort_keys=True),flush=True)
    return result

def replay(source,ev,cert_path,tsv_path,units_path):
    n,clauses=exact.parse_dimacs(source)
    eq,groups,units=source_equations(clauses)
    selected=check_selected(ev,groups,units)
    cert=json.loads(pathlib.Path(cert_path).read_text())
    need(cert["source_sha256"]==sha(source),"replay source hash mismatch")
    need(cert["source_selected_rows"]==len(selected) and cert["source_full_equations"]==len(eq),
         "source equation count drift")
    rows=[]
    for d in cert["derived"]:
        m=maskof(d["vars"]);b=d["rhs"];ids=d["source_indices"]
        mm=0;r=0
        for i in ids:
            need(0<=i<len(selected),"short proof index outside input")
            mm^=selected[i][0];r^=selected[i][1]
        need(mm==m and r==b,"short derived XOR proof invalid")
        rows.append((m,b))
    reported=[(m,b) for m,b in selected]+rows
    original_tsv="".join(f"{m.bit_count()} {b} "+" ".join(map(str,bits(m)))+"\n" for m,b in reported)
    need(pathlib.Path(tsv_path).read_text()==original_tsv,"derived TSV changed after certification")
    for d in cert["units"]:
        m=1<<(d["var"]-1);b=d["rhs"];rr=0;mm=0
        for i in d["source_indices"]:
            need(0<=i<len(eq),"unit proof index outside source")
            mm^=maskof(eq[i][0]);rr^=eq[i][1]
        need(mm==m and rr==b,"implied unit proof invalid")
    expected_units="".join(f"{d['var']} {d['rhs']}\n" for d in cert["units"])
    need(pathlib.Path(units_path).read_text()==expected_units,"derived units TSV changed")
    if cert["contradiction_found"]:
        mm=0;rr=0
        for i in cert["contradiction_original_indices"]:
            need(0<=i<len(eq),"unsat proof index outside source")
            mm^=maskof(eq[i][0]);rr^=eq[i][1]
        need(mm==0 and rr==1,"mixed XOR contradiction replay failed")
    return True

def selftest():
    # Source equations x^y=0, x^z=0, z^w=0 -> y^w=0
    s=[(maskof((1,2)),0),(maskof((1,3)),0),(maskof((3,4)),0)]
    freq=collections.Counter({2:20,4:20})
    rows,meta=candidates(s,freq,collections.Counter(),12)
    need(any(m==maskof((2,4)) and b==0 and p.bit_count()>=3 for m,b,p in rows),
         "three-way source consequence unavailable")
    eq=[((1,2),0),((1,),1)]
    gf=gaussian_full(eq)
    need(any(m==maskof((2,)) and b==1 for m,b,p in gf["units"]),
         "full Gaussian derived unit missing")
    unsat=gaussian_full([((1,),0),((1,),1)])
    need(unsat["unsat"]!=0,"Gaussian contradiction missing")
    for m,b,p in rows:verify_proof([(tuple(bits(x)),y) for x,y in s],m,b,p)
    print("R166X_GAUSS_PROOF_SELFTEST_PASS",meta,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--selftest",action="store_true")
    p.add_argument("--source");p.add_argument("--r157-cert");p.add_argument("--out")
    a=p.parse_args()
    if a.selftest:selftest()
    else:
        need(a.source and a.r157_cert and a.out,"missing source, cert or out")
        x=prepare(a.source,json.loads(pathlib.Path(a.r157_cert).read_text()),a.out)
        need(replay(a.source,json.loads(pathlib.Path(a.r157_cert).read_text()),
                    x["certificate"],x["tsv"],x["units_tsv"]),"independent replay failed")
