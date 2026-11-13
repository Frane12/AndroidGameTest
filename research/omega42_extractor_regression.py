#!/usr/bin/env python3
"""Ω4.2 independent source-XOR regression; no SAT solver or benchmark labels.

Detects the previous comparison-order false alarm when original CNF entails both
XOR parities for one support. Checks 320 deterministic synthetics, including
incomplete parity negative controls, with a separate clause-mask implementation.
"""
import argparse,collections,hashlib,json,pathlib,random,subprocess,tempfile

def encode(rows,n,extra=()):
    clauses=[]
    for vars_,rhs in rows:
        for bits in range(1<<len(vars_)):
            if bits.bit_count()%2!=rhs:
                clauses.append(tuple(-v if bits>>i&1 else v for i,v in enumerate(vars_)))
    clauses.extend(tuple(c) for c in extra)
    return ("p cnf %d %d\n"%(n,len(clauses))+
        "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode(),clauses

def certified_by_clause_masks(clauses):
    groups=collections.defaultdict(set)
    for cl in clauses:
        if len(cl) not in (2,3,4):continue
        vs=tuple(sorted(abs(v) for v in cl))
        if len(set(vs))!=len(vs):continue
        mask=sum(1<<vs.index(-v) for v in cl if v<0)
        groups[vs].add(mask)
    expected=set()
    for vars_,masks in groups.items():
        for rhs in (0,1):
            blocked={i for i in range(1<<len(vars_)) if i.bit_count()%2!=rhs}
            if blocked.issubset(masks):
                expected.add((vars_,rhs))
    return expected

def check(exporter,root,idx,raw,clauses):
    source=root/"case.cnf";rows=root/"rows.tsv"
    source.write_bytes(raw)
    p=subprocess.run([str(exporter),"export",str(source),str(rows)],
        capture_output=True,text=True,timeout=2)
    if p.returncode!=0:
        (root/"counterexample.cnf").write_bytes(raw)
        raise RuntimeError(f"EXTRACTOR_FAILED case={idx} {p.stderr}")
    found=set()
    for line in rows.read_text().splitlines():
        vals=list(map(int,line.split()))
        n,rhs=vals[:2];vars_=tuple(vals[2:])
        if n!=len(vars_) or rhs not in (0,1):
            raise AssertionError("Malformed row")
        key=(vars_,rhs)
        if key in found:raise AssertionError("Duplicate row")
        found.add(key)
    expected=certified_by_clause_masks(clauses)
    if found!=expected:
        (root/"counterexample.cnf").write_bytes(raw)
        raise AssertionError(f"Wrong detected exact XOR rows case={idx} found={found} expected={expected}")
    return found

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--exporter",type=pathlib.Path,required=True)
    a.add_argument("--output",type=pathlib.Path,required=True)
    opts=a.parse_args()
    opts.output.parent.mkdir(parents=True,exist_ok=True)
    rng=random.Random(42022026)
    failures=0;rows_found=0;both_parities=0;partial_negative=0
    with tempfile.TemporaryDirectory() as tmp:
        tmp=pathlib.Path(tmp)
        n=8
        for i in range(320):
            equations=[]
            for k in range(1+rng.randrange(5)):
                w=rng.choice((2,3,4));vs=tuple(sorted(rng.sample(range(1,n+1),w)))
                rhs=rng.getrandbits(1)
                equations.append((vs,rhs))
            if i%11==0:
                # Explicitly contradict same support; independent extractors
                # must emit both equations in identical canonical order.
                vs=tuple(sorted(rng.sample(range(1,n+1),3)))
                equations.extend(((vs,0),(vs,1)))
            if i%7==0 and equations:
                raw,clauses=encode(equations,n)
                # Remove one original forbidden clause for a selected equation,
                # not the whole formula; complete-closure detection must abstain
                # unless remaining clauses still independently certify a row.
                clauses=clauses[:-1]
                partial_negative+=1
                raw=("p cnf %d %d\n"%(n,len(clauses))+
                    "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
            else: raw,clauses=encode(equations,n)
            found=check(opts.exporter,tmp,i,raw,clauses)
            rows_found+=len(found)
            if any((vs,0) in found and (vs,1) in found for vs,rhs in found):
                both_parities+=1
        report={"seed":42022026,"cases":320,"status":"PASS",
          "source_rows_verified":rows_found,"cases_with_both_parities":both_parities,
          "incomplete_encoding_controls":partial_negative,
          "unverified_or_false_rows":0,
          "extractor_sha256":hashlib.sha256(opts.exporter.read_bytes()).hexdigest()}
        opts.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
        print("OMEGA42_EXTRACTOR_FINAL "+json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":main()
