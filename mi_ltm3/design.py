"""DRNAS MI-LTM3: deterministic, SHA-separated medium CNF cohort and audit.

384 original CNFs (6 families x 64); 192 training and 192 holdout.
Training uses a new generation per GitHub run; holdout remains frozen for
comparability. Every SAT case has a planted *verified* source witness.
UNSAT cases have a separately re-derived, source-clause-certified GF(2)
contradiction. No unsupported UNSAT receives a solved credit.
"""
import hashlib
import json
import random
from collections import Counter, defaultdict

FAMILIES = (
    "xor_overlap_planted", "xor_chain_planted", "xor_core_unsat",
    "xor_mixed_planted", "random3_planted", "near_xor_incomplete"
)
PER_FAMILY = 64
TRAIN_PER_FAMILY = 32


def xor_cnf(variables, rhs):
    return [tuple(-v if mask & (1 << i) else v for i,v in enumerate(variables))
            for mask in range(1 << len(variables))
            if mask.bit_count() % 2 != rhs]


def dimacs(n, clauses):
    return "p cnf %d %d\n" % (n,len(clauses)) + "".join(
        " ".join(map(str,clause)) + " 0\n" for clause in clauses)


def satisfies(clauses, assignment):
    return all(any(assignment[abs(v)] == (v>0) for v in clause)
               for clause in clauses)


def noise(rng, n, model, count):
    rows = []
    for _ in range(count):
        vars_ = rng.sample(range(1,n+1),3)
        clause = [v if rng.getrandbits(1) else -v for v in vars_]
        if not any(model[abs(v)] == (v>0) for v in clause):
            pos = rng.randrange(3)
            v = vars_[pos]
            clause[pos] = v if model[v] else -v
        rows.append(tuple(clause))
    return rows


def source_parity_unsat(clauses):
    """Independent small-XOR source certification and GF(2) contradiction.

    For a row to be accepted, the *original CNF* must contain every
    forbidden assignment's full clause on that support, not merely a
    detector claim. Gauss is performed in Python int bitsets.
    """
    groups = defaultdict(set)
    for clause in clauses:
        supp = tuple(sorted({abs(v) for v in clause}))
        if len(supp) not in (2,3) or len(supp)!=len(clause):
            continue
        signed = {abs(v):v for v in clause}
        mask = sum(1 << i for i,v in enumerate(supp) if signed[v] < 0)
        groups[supp].add(mask)
    basis = {}
    certified = 0
    for supp, seen in groups.items():
        for rhs in (0,1):
            forbidden = {mask for mask in range(1<<len(supp))
                         if mask.bit_count()%2 != rhs}
            if not forbidden <= seen:
                continue
            certified += 1
            mask = sum(1 << (v-1) for v in supp)
            bit = rhs
            while mask:
                pivot = mask.bit_length()-1
                if pivot not in basis:
                    basis[pivot] = (mask,bit)
                    break
                other, other_bit = basis[pivot]
                mask ^= other
                bit ^= other_bit
            if not mask and bit:
                return True, certified
    return False, certified


def make_case(family, case_id, *, generation=0):
    if family not in FAMILIES or case_id < 0:
        raise ValueError("Unknown family or case index")
    seed = int.from_bytes(hashlib.sha256(
        ("MI-LTM3-v1|%s|%d|%d" % (family,case_id,generation)).encode()
    ).digest()[:8],"big")
    rng = random.Random(seed)
    n = (48,64,80)[case_id % 3]
    model = {v:bool(rng.getrandbits(1)) for v in range(1,n+1)}
    v = rng.sample(range(1,n+1),18)
    clauses = []
    def add_xor(vars_):
        rhs = sum(model[x] for x in vars_) & 1
        clauses.extend(xor_cnf(vars_,rhs))
        return rhs
    if family == "xor_overlap_planted":
        for j in range(10):
            a,b,c,d = v[j],v[j+1],v[j+2],v[j+3]
            add_xor((a,b,c))
            add_xor((b,c,d))
        clauses.extend(noise(rng,n,model,int(2.6*n)))
    elif family == "xor_chain_planted":
        for j in range(12):
            add_xor((v[j],v[j+1]))
        clauses.extend(noise(rng,n,model,int(3.2*n)))
    elif family == "xor_core_unsat":
        a,b,c = v[:3]
        p = add_xor((a,b))
        q = add_xor((b,c))
        clauses.extend(xor_cnf((a,c),1-(p^q)))
        clauses.extend(noise(rng,n,model,int(3.5*n)))
    elif family == "xor_mixed_planted":
        for _ in range(28):
            add_xor(rng.sample(range(1,n+1),3))
        clauses.extend(noise(rng,n,model,int(3.6*n)))
    elif family == "random3_planted":
        clauses.extend(noise(rng,n,model,int(4.1*n)))
    elif family == "near_xor_incomplete":
        for _ in range(12):
            vs = rng.sample(range(1,n+1),3)
            rhs = sum(model[x] for x in vs)&1
            pieces = xor_cnf(vs,rhs)
            pieces.pop(rng.randrange(len(pieces)))
            clauses.extend(pieces)
        clauses.extend(noise(rng,n,model,int(3.8*n)))
    # Original formula, no post-processing or injected relations here.
    if family != "xor_core_unsat" and not satisfies(clauses,model):
        raise AssertionError("Planted witness does not satisfy source CNF")
    if family == "xor_core_unsat":
        is_unsat,rows=source_parity_unsat(clauses)
        if not is_unsat or rows<3:
            raise AssertionError("Independent source GF2 contradiction missing")
    raw = dimacs(n,clauses)
    return dict(family=family,case=case_id,generation=generation,n=n,
                clauses=clauses,raw=raw,
                sha=hashlib.sha256(raw.encode()).hexdigest(),
                expect=("UNSAT_GF2_PROVEN" if family=="xor_core_unsat"
                        else "SAT_PLANTED"),
                planted=None if family=="xor_core_unsat" else model)


def cohort(*, training_generation):
    cases=[]
    seen=set()
    for family in FAMILIES:
        for case_id in range(PER_FAMILY):
            # Source holdout fixed, disjoint in seed *and* SHA from training.
            split="train" if case_id < TRAIN_PER_FAMILY else "holdout"
            generation=training_generation if split=="train" else 0
            case=make_case(family,case_id,generation=generation)
            if case["sha"] in seen:
                raise AssertionError("Duplicate source CNF SHA")
            seen.add(case["sha"])
            case["split"]=split
            cases.append(case)
    assert len(cases)==384 and len(seen)==384
    return cases


def opportunity_key(clauses,n):
    """Very cheap renaming-invariant grouping; NOT a mathematical proof.

    Count duplicated supports that *could* encode 2/3-XORs.
    A collision can affect only routing decisions, never SAT correctness.
    """
    count = Counter()
    bins = Counter()
    for cl in clauses:
        bins[len(cl)] += 1
        if 2<=len(cl)<=3 and len(set(map(abs,cl)))==len(cl):
            count[tuple(sorted(map(abs,cl)))] += 1
    x2 = sum(len(s)==2 and c>=2 for s,c in count.items())
    x3 = sum(len(s)==3 and c>=4 for s,c in count.items())
    def bucket(x):
        return "0" if x==0 else "1" if x<5 else "5" if x<20 else "20"
    return "n%s/c%s/x2%s/x3%s" % (
        (n//16)*16, (len(clauses)//100)*100, bucket(x2), bucket(x3))


def digest_manifest(cases):
    manifest=[dict(family=x["family"],case=x["case"],split=x["split"],
                   sha256=x["sha"],vars=x["n"],clauses=len(x["clauses"]),
                   expected=x["expect"]) for x in cases]
    encoded=json.dumps(manifest,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(encoded.encode()).hexdigest(),manifest
