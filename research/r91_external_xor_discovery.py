"""Find external unseen XOR-CNF candidates by exact 3-variable parity patterns.

Input: directory of external DIMACS CNFs. No synthetic formulas, no labels
inferred from filenames. A four-clause 3-XOR pattern is necessary evidence
of an encoded XOR gate, not evidence of hard XOR reasoning.
"""
import argparse, hashlib, json, pathlib

def scan(path):
    patterns = {}
    nclauses=0
    with open(path, errors="replace") as f:
        for line in f:
            line=line.strip()
            if not line or line[0] in "cp%": continue
            if line[0] == "x": continue  # extended XCNF needs separate handling
            try: xs=[int(x) for x in line.split()]
            except ValueError: continue
            if not xs or xs[-1]!=0: continue
            lits=xs[:-1];nclauses+=1
            if len(lits)!=3 or len(set(map(abs,lits)))!=3: continue
            key=tuple(sorted(map(abs,lits)))
            mask=sum(1<<i for i,v in enumerate(key) if -v in lits)
            patterns[key]=patterns.get(key,0)|(1<<mask)
    xor=0
    for bits in patterns.values():
        # Odd- or even-parity forbidden assignments each have 4 sign patterns.
        if (bits&0x69)==0x69 or (bits&0x96)==0x96: xor+=1
    return xor,nclauses

def main():
    p=argparse.ArgumentParser()
    p.add_argument("root");p.add_argument("--limit",type=int,default=80)
    p.add_argument("--out",default="results/r91_xor_candidates.json")
    a=p.parse_args()
    candidates=[]
    for f in sorted(pathlib.Path(a.root).rglob("*.cnf")):
        xor,clauses=scan(f)
        if xor:
            candidates.append(dict(path=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),xor_triples=xor,clauses=clauses,source="external",status="candidate"))
    # deterministic: avoid cherry-picking based on solver runtime
    candidates.sort(key=lambda x:x["sha256"])
    unique={x["sha256"]:x for x in candidates}
    chosen=list(unique.values())[:a.limit]
    pathlib.Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(a.out).write_text(json.dumps(dict(requested=a.limit,found=len(unique),selected=len(chosen),items=chosen),indent=2))
    print(f"XOR-pattern candidate selection: {len(chosen)}/{a.limit} (from {len(unique)} unique candidates)")
    if len(chosen)<50: raise SystemExit("Insufficient external XOR candidates; no benchmark claim")

if __name__=="__main__": main()
