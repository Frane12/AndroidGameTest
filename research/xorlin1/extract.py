#!/usr/bin/env python3
"""Source-only complete XOR2..6 extraction and GF(2) inconsistent subset.

No names, catalog SAT labels or solver outputs. A recognized XOR row must
have all 2^(w-1) source forbidden-assignment clauses on the identical
variable support, and all must forbid exactly one parity. Bitset Gaussian
elimination retains the original row-combination witness. No selected
contradiction => no proof, safely UNKNOWN.
"""
from collections import Counter,defaultdict
from pathlib import Path
import argparse,hashlib,json,time

MAX_SOURCE_BYTES=12_000_000
MAX_WIDTH=6
MAX_ROWS=4000

class Unsupported(ValueError):pass

def parse(raw):
    if len(raw)>MAX_SOURCE_BYTES:raise Unsupported("source bytes policy")
    nv=nc=None;clauses=[];pending=[]
    for line in raw.decode("ascii").splitlines():
        cols=line.split()
        if not cols or cols[0]=="c":continue
        if cols[0]=="p":
            if nv is not None or len(cols)!=4 or cols[1]!="cnf":
                raise Unsupported("malformed original DIMACS header")
            nv,nc=int(cols[2]),int(cols[3])
            if not 0<nv<=200_000 or not 0<nc<=400_000:
                raise Unsupported("DIMACS source size policy")
            continue
        if nv is None:raise Unsupported("missing DIMACS header")
        for col in cols:
            lit=int(col)
            if abs(lit)>nv:raise Unsupported("literal above source declared vars")
            if lit:pending.append(lit)
            else:clauses.append(tuple(pending));pending=[]
    if nv is None or pending or len(clauses)!=nc:
        raise Unsupported("source clause count mismatch")
    return nv,clauses

def recover_xors(clauses):
    grouped=defaultdict(set)
    for clause in clauses:
        if not 2<=len(clause)<=MAX_WIDTH:continue
        vs=tuple(sorted({abs(x) for x in clause}))
        if len(vs)!=len(clause):continue
        sign={abs(lit):int(lit<0) for lit in clause}
        bits=sum(sign[var]<<i for i,var in enumerate(vs))
        grouped[vs].add(bits)
    rows=[]
    for support,masks in grouped.items():
        width=len(support)
        if len(masks)!=(1<<(width-1)):continue
        bad_parities={m.bit_count()&1 for m in masks}
        if len(bad_parities)!=1:continue
        rows.append({"vars":list(support),
                     "forbidden_parity":next(iter(bad_parities))})
    rows.sort(key=lambda row:(len(row["vars"]),row["vars"]))
    if len(rows)>MAX_ROWS:raise Unsupported("too many XOR source groups")
    return rows

def gaussian(rows):
    basis={}
    for i,row in enumerate(rows):
        mask=sum(1<<(v-1) for v in row["vars"])
        rhs=1-row["forbidden_parity"]
        combo=1<<i
        while mask:
            lead=mask.bit_length()-1
            if lead not in basis:
                basis[lead]=(mask,rhs,combo)
                break
            bm,br,bc=basis[lead]
            mask^=bm;rhs^=br;combo^=bc
        else:
            if rhs:
                return [j for j in range(len(rows)) if combo>>j&1]
    return None

def derive(raw):
    started=time.perf_counter()
    nv,source=parse(raw)
    found=recover_xors(source)
    indices=gaussian(found)
    meta={"original_sha256":hashlib.sha256(raw).hexdigest(),
          "original_vars":nv,"original_clauses":len(source),
          "complete_source_xor_rows":len(found),
          "complete_xor_widths":dict(Counter(len(row["vars"]) for row in found)),
          "selected_rows":len(indices) if indices is not None else 0}
    if indices is None:
        meta["status"]="UNKNOWN_NO_GF2_CONTRADICTION"
        return None,meta
    selected=[found[i] for i in indices]
    degree=Counter(x for row in selected for x in row["vars"])
    if not degree or any(v%2 for v in degree.values()) or (
        sum(1-row["forbidden_parity"] for row in selected)%2!=1
    ):
        raise AssertionError("INTERNAL_GF2_WITNESS_INVALID")
    meta.update({"status":"SOURCE_GF2_CONTRADICTION",
                 "selected_degrees":dict(Counter(degree.values())),
                 "selected_widths":dict(Counter(len(r["vars"]) for r in selected)),
                 "search_s":round(time.perf_counter()-started,6)})
    cert={"format":"drnas-math5-eo-xor-unit-v1",
          "source_sha256":meta["original_sha256"],
          "xor_rows":selected,"exact_one_groups":[],"root_units":[]}
    return cert,meta

def main():
    arg=argparse.ArgumentParser()
    arg.add_argument("--cnf",required=True,type=Path)
    arg.add_argument("--certificate",required=True,type=Path)
    arg.add_argument("--meta",required=True,type=Path)
    a=arg.parse_args()
    try:
        cert,meta=derive(a.cnf.read_bytes())
        a.meta.parent.mkdir(parents=True,exist_ok=True)
        a.meta.write_text(json.dumps(meta,indent=2,sort_keys=True)+"\n")
        print("XORLIN1_SOURCE_REPORT "+json.dumps(meta,sort_keys=True),flush=True)
        if cert is None:
            a.certificate.unlink(missing_ok=True)
            return 2
        a.certificate.write_text(json.dumps(cert,indent=2,sort_keys=True)+"\n")
        return 0
    except (ValueError,TypeError,UnicodeError,OSError,OverflowError) as exc:
        a.certificate.unlink(missing_ok=True)
        print("XORLIN1_SAFE_UNKNOWN "+str(exc),flush=True)
        return 2
if __name__=="__main__":
    raise SystemExit(main())
