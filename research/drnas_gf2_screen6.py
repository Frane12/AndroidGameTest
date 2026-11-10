#!/usr/bin/env python3
"""DRNAS GF2-SCREEN6: source-exact all-row parity screening without a CDCL run.

17 previously seen original SHA CNFs; independently verify every original
complete-parity clause block; substitute ORIGINAL CNF units only; probe
connected 2/3-row combinations and bounded sparse GF(2) Gaussian elimination.
This is a structural diagnostic, NOT an E2E SAT competition result or LRAT.
Combinatorial probes have explicit fixed caps and report truncation.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, pathlib, tempfile, time
import drnas_gf2_proof_first_s1 as gf
import drnas_equiv9_prospective_seed_holdout as e9
import r157_source_certified_xor as r157

ROOT=pathlib.Path("mre_gf2screen6")
PROTO="DRNAS-GF2-SCREEN6-17SHA-ALL-COMPLETE-XOR-PAIR-TRIPLE-GAUSS-v1"
SHARDS=5
COUNT=17
MAX_PAIR_CHECKS=160000
MAX_TRIPLE_CHECKS=160000
MAX_INTERMEDIATES=5500
MAX_GAUSS_OPS=80000
MAX_GAUSS_WIDTH=20
MAX_GAUSS_ROOTS=32
MAX_PROOFS_PER_METHOD=96
MAX_RETAINED_UNIQUE=18000
MAX_RESULT_WIDTH=4

def need(ok,what):
    if not ok: raise RuntimeError("GF2_SCREEN6_FAIL_CLOSED "+str(what))
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def digest(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def save(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def cases():
    cs=gf.cases()
    need(len(cs)==COUNT and len({c["sha256"] for c in cs})==COUNT,"source registry drift")
    for c in cs:gf.original_path(c)
    return cs

def full_source_scan(clauses):
    """Reconstruct ALL exact 2..6-variable parity blocks from original clauses.
    Every root equation is supported by all 2^(k-1) required source clauses.
    The unit-substituted equation is a consequence of those and source units.
    """
    groups=collections.defaultdict(set)
    units={}
    contradictory_units=False
    for clause in clauses:
        if len(clause)==1:
            v=abs(clause[0]);rhs=int(clause[0]>0)
            if v in units and units[v]!=rhs:contradictory_units=True
            units[v]=rhs
        if not 2<=len(clause)<=6:continue
        ordered=sorted(clause,key=abs)
        vs=tuple(abs(v) for v in ordered)
        if len(set(vs))!=len(vs):continue
        mask=sum(1<<i for i,l in enumerate(ordered) if l<0)
        groups[vs].add(mask)
    raw=[]
    seen=set()
    complete_blocks=0
    source_root_unary=0
    source_root_empty=0
    for vs,masks in groups.items():
        k=len(vs)
        for forbidden in (0,1):
            if not all(m in masks for m in range(1<<k)
                       if m.bit_count()%2==forbidden):
                continue
            complete_blocks+=1
            rhs=1-forbidden
            remaining=tuple(v for v in vs if v not in units)
            for v in vs:
                if v in units:rhs^=units[v]
            if len(remaining)==0:
                source_root_empty+=(rhs==1)
                continue
            if len(remaining)==1:
                source_root_unary+=1
                continue
            key=(remaining,rhs)
            if key in seen:continue
            seen.add(key)
            raw.append(key)
    raw.sort(key=lambda a:(len(a[0]),a[0],a[1]))
    return raw,dict(complete_source_blocks=complete_blocks,
        complete_source_XOR_post_units=len(raw),
        exact_source_units=len(units),
        source_root_unit_rows=source_root_unary,
        source_root_empty_contradictions=source_root_empty,
        contradictory_original_units=contradictory_units,
        original_groups=len(groups))

def xor2(a,b):
    return tuple(sorted(set(a)^set(b)))

class Recorder:
    def __init__(self,raw):
        self.raw=raw
        self.orig=set(raw)
        self.candidates={}
        self.calls=0
        self.saturated=False
    def consider(self,vars_,rhs,root_indices):
        self.calls+=1
        if len(vars_)>MAX_RESULT_WIDTH or (not vars_ and rhs==0):return
        if (vars_,rhs) in self.orig:return
        roots=tuple(sorted(root_indices))
        if len(roots)<2 or len(roots)>MAX_GAUSS_ROOTS:return
        strict=len(vars_)<min(len(self.raw[i][0]) for i in roots)
        key=(vars_,rhs)
        old=self.candidates.get(key)
        if old is None and len(self.candidates)>=MAX_RETAINED_UNIQUE:
            self.saturated=True
            return
        if old is None or (len(roots),roots)<(len(old["parents"]),tuple(old["parents"])):
            self.candidates[key]=dict(vars=list(vars_),rhs=rhs,
                parents=list(roots),strict_shorter_than_every_parent=strict,
                contradiction=(not vars_ and rhs==1))
    def report(self):
        best=sorted(self.candidates.values(),key=lambda x:(
            0 if x["contradiction"] else 1,
            len(x["vars"]),0 if x["strict_shorter_than_every_parent"] else 1,
            len(x["parents"]),tuple(x["vars"]),x["rhs"],tuple(x["parents"])))
        return dict(unique_short_novel=len(best),
            strict_shorter=sum(x["strict_shorter_than_every_parent"] for x in best),
            new_units=sum(len(x["vars"])==1 for x in best),
            new_binary_xor=sum(len(x["vars"])==2 for x in best),
            new_ternary_xor=sum(len(x["vars"])==3 for x in best),
            new_four_xor=sum(len(x["vars"])==4 for x in best),
            contradictory_GF2_zero_equals_one=sum(x["contradiction"] for x in best),
            candidates_considered=self.calls,
            uniqueness_store_saturated=self.saturated,
            proofs=best[:MAX_PROOFS_PER_METHOD])

def connected_pairs(raw):
    inv=collections.defaultdict(list)
    for i,(vs,rhs) in enumerate(raw):
        for v in vs:inv[v].append(i)
    seen=set()
    edges=[]
    capped=False
    for v,items in sorted(inv.items(),key=lambda x:(len(x[1]),x[0])):
        if len(items)<2:continue
        for i,j in itertools.combinations(items,2):
            key=(i,j)
            if key in seen:continue
            seen.add(key)
            edges.append(key)
            if len(edges)>=MAX_PAIR_CHECKS:
                capped=True;break
        if capped:break
    return inv,edges,capped

def pair_trip_screen(raw):
    pair=Recorder(raw)
    triple=Recorder(raw)
    inv,edges,pair_cap=connected_pairs(raw)
    mids=[]
    for i,j in edges:
        vs=xor2(raw[i][0],raw[j][0])
        rhs=raw[i][1]^raw[j][1]
        pair.consider(vs,rhs,(i,j))
        if vs and len(vs)<=12:
            mids.append((len(vs),i,j,vs,rhs))
    mids.sort(key=lambda z:(z[0],z[1],z[2]))
    mids_capped=len(mids)>MAX_INTERMEDIATES
    mids=mids[:MAX_INTERMEDIATES]
    triple_checks=0
    triple_capped=False
    seen_triples=set()
    for _,i,j,vs,rhs in mids:
        nbr=set()
        for v in vs:nbr.update(inv.get(v,()))
        for k in sorted(nbr):
            if k==i or k==j:continue
            ids=tuple(sorted((i,j,k)))
            if ids in seen_triples:continue
            seen_triples.add(ids)
            triple_checks+=1
            triple.consider(xor2(vs,raw[k][0]),rhs^raw[k][1],ids)
            if triple_checks>=MAX_TRIPLE_CHECKS:
                triple_capped=True;break
        if triple_capped:break
    return pair.report()|dict(pairs_evaluated=len(edges),
             pair_enumeration_capped=pair_cap),\
           triple.report()|dict(triples_evaluated=triple_checks,
             triple_enumeration_capped=triple_capped,
             pair_intermediates_total=len(mids),
             pair_intermediates_capped=mids_capped)

def gaussian_screen(raw):
    rec=Recorder(raw)
    basis={}
    ops=0;aborted_fill=0;aborted_support=0
    capped=False
    for idx,(vars_,rhs) in enumerate(raw):
        cur=set(vars_);bit=rhs;support={idx}
        while cur:
            pivot=min(cur)
            if pivot not in basis:
                basis[pivot]=(set(cur),bit,set(support))
                break
            bvars,brhs,bsupport=basis[pivot]
            cur^=bvars;bit^=brhs;support^=bsupport
            ops+=1
            if len(support)>=2:
                rec.consider(tuple(sorted(cur)),bit,support)
            if len(cur)>MAX_GAUSS_WIDTH:
                aborted_fill+=1;break
            if len(support)>MAX_GAUSS_ROOTS:
                aborted_support+=1;break
            if ops>=MAX_GAUSS_OPS:
                capped=True;break
        if capped:break
    return rec.report()|dict(gauss_xor_operations=ops,
        pivot_rank=len(basis),gauss_capped=capped,
        rows_aborted_width=aborted_fill,
        rows_aborted_proof_support=aborted_support)

def verify_candidate(proof,raw):
    parents=proof["parents"]
    need(len(parents)>=2 and len(parents)==len(set(parents)) and
         all(isinstance(i,int) and 0<=i<len(raw) for i in parents),
         "invalid root provenance")
    support=set();rhs=0
    for i in parents:
        vs,r=raw[i]
        support.symmetric_difference_update(vs)
        rhs^=r
    actual=tuple(sorted(support))
    need(actual==tuple(proof["vars"]) and rhs==proof["rhs"],
        "GF2 combination independently disagrees")
    need(len(actual)<=MAX_RESULT_WIDTH and (actual,rhs) not in set(raw),
        "derived result is not novel short GF2")
    need(proof["strict_shorter_than_every_parent"]==
         (len(actual)<min(len(raw[i][0]) for i in parents)),
         "strict-shorter flag invalid")
    need(proof["contradiction"]==(not actual and rhs==1),
         "algebraic contradiction flag invalid")

def screen_case(case):
    src=gf.original_path(case)
    n,clauses=e9.x22.read_cnf(src)
    need(sha(src)==case["sha256"],"source changed")
    begun=time.perf_counter()
    raw,root=full_source_scan(clauses)
    baseline=None
    with tempfile.TemporaryDirectory(dir=ROOT) as folder:
        f=pathlib.Path(folder)/"selected.tsv"
        p=pathlib.Path(folder)/"selected-proof.json"
        details=r157.extract(src,f,p,max_rows=100)
        base=[]
        for line in f.read_text().splitlines():
            k,rhs,*vs=map(int,line.split())
            need(k==len(vs) and (tuple(vs),rhs) in set(raw),
                 "R157 selected100 not independently root-certified")
            base.append((tuple(vs),rhs))
        baseline=dict(previous_selected100=len(base),
            previous_selected100_pair_short=pair_trip_screen(base)[0]["unique_short_novel"] if base else 0)
    pair,triple=pair_trip_screen(raw)
    gauss=gaussian_screen(raw)
    report=dict(source_sha256=case["sha256"],gbd=case["gbd"],
        filename=case["filename"],vars=n,clauses=len(clauses),
        source_exact_root_hash=digest(raw),root=root,
        baseline=baseline,method=dict(pair=pair,triple=triple,gaussian=gauss),
        screen_wall_s=round(time.perf_counter()-begun,4),
        no_CDCL_invoked=True,not_blind=True)
    for method,obj in report["method"].items():
        for proof in obj["proofs"]:verify_candidate(proof,raw)
    need(sha(src)==case["sha256"],"source changed during screen")
    return report

def reverify_record(case,record):
    src=gf.original_path(case)
    n,clauses=e9.x22.read_cnf(src)
    raw,root=full_source_scan(clauses)
    need(record["source_sha256"]==case["sha256"] and
         record["vars"]==n and record["clauses"]==len(clauses) and
         record["source_exact_root_hash"]==digest(raw) and
         record["root"]==root,"audit source XOR root mismatch")
    for method in ("pair","triple","gaussian"):
        rec=record["method"][method]
        need(len(rec["proofs"])<=MAX_PROOFS_PER_METHOD and
             rec["unique_short_novel"]>=len(rec["proofs"]),
             "audit root-derived count contradiction")
        for proof in rec["proofs"]:verify_candidate(proof,raw)

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    def cnf_xor(vs,rhs):
        # A CNF clause forbids one assignment, indicated by its bit mask.
        return [tuple(-v if mask&(1<<i) else v for i,v in enumerate(vs))
                for mask in range(1<<len(vs))
                if mask.bit_count()%2==1-rhs]
    clauses=(cnf_xor((1,2,3),0)+cnf_xor((1,2,4),1)+
             cnf_xor((5,6,7,8),0)+cnf_xor((5,6,9,10),0)+
             cnf_xor((7,8,9,11),1))
    raw,stats=full_source_scan(clauses)
    pair,tri=pair_trip_screen(raw)
    gauss=gaussian_screen(raw)
    need(stats["complete_source_blocks"]==5,"synthetic XOR group detection")
    need(any(p["vars"]==[3,4] and p["rhs"]==1 for p in pair["proofs"]),
         "pair 3xor->2xor fixture failed")
    need(any(p["vars"]==[10,11] and p["rhs"]==1 for p in tri["proofs"]),
         "triple 4xor->2xor fixture failed")
    for rec in (pair,tri,gauss):
        for proof in rec["proofs"]:verify_candidate(proof,raw)
    try:
        fake=dict(pair["proofs"][0]);fake["rhs"]^=1
        verify_candidate(fake,raw)
    except RuntimeError:pass
    else:raise RuntimeError("tampered GF2 pair proof unexpectedly verified")
    print("GF2_SCREEN6_SELFTEST_PASS "+json.dumps(dict(
        exact_original_XOR_groups=stats["complete_source_blocks"],
        pair_derived=pair["unique_short_novel"],
        triple_derived=tri["unique_short_novel"],
        gaussian_derived=gauss["unique_short_novel"],
        intentionally_tampered_proof_rejected=True),sort_keys=True),flush=True)

def freeze():
    cs=cases()
    m=dict(protocol=PROTO,cases=cs,source_SHA_roster_frozen=True,
        source_sha256_list=[c["sha256"] for c in cs],
        selected_from_previous_nonblind_original_S1=True,
        no_CDCL_no_SAT_speed_claims=True,independent_LRAT=False,
        source_exact_proof_required=True,source_full_original_XOR_scan=True,
        max_pair_evaluations=MAX_PAIR_CHECKS,
        max_triple_evaluations=MAX_TRIPLE_CHECKS,
        max_intermediates=MAX_INTERMEDIATES,
        max_gauss_ops=MAX_GAUSS_OPS,
        max_gauss_row_width=MAX_GAUSS_WIDTH,
        max_gauss_proof_roots=MAX_GAUSS_ROOTS,
        max_output_width=MAX_RESULT_WIDTH,
        all_combinatorial_caps_are_reported=True,
        code_SHA=sha(__file__),
        extractor_SHA=sha("research/r157_source_certified_xor.py"))
    save(ROOT/"manifest.json",m);verify()
    print("GF2_SCREEN6_FROZEN "+json.dumps(dict(sources=len(cs),shards=SHARDS,
          pair_cap=MAX_PAIR_CHECKS,triple_cap=MAX_TRIPLE_CHECKS,
          gauss_cap=MAX_GAUSS_OPS,not_blind=True,no_CDCL=True),sort_keys=True),flush=True)

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    cs=cases()
    need(m["protocol"]==PROTO and m["cases"]==cs and
         m["code_SHA"]==sha(__file__) and
         m["extractor_SHA"]==sha("research/r157_source_certified_xor.py"),
         "frozen source/code drift")
    return m

def shard(i):
    m=verify()
    need(0<=i<SHARDS,"invalid shard id")
    cs=[c for j,c in enumerate(m["cases"]) if j%SHARDS==i]
    out=[]
    for case in cs:
        rec=screen_case(case)
        out.append(rec)
        save(ROOT/f"shard-{i}.json",out)
        print("GF2_SCREEN6_CASE "+json.dumps(dict(
            sha=rec["source_sha256"],n_xor=rec["root"]["complete_source_XOR_post_units"],
            pair=rec["method"]["pair"]["unique_short_novel"],
            triple=rec["method"]["triple"]["unique_short_novel"],
            gauss=rec["method"]["gaussian"]["unique_short_novel"],
            strict_pair=rec["method"]["pair"]["strict_shorter"],
            strict_triple=rec["method"]["triple"]["strict_shorter"],
            strict_gauss=rec["method"]["gaussian"]["strict_shorter"],
            caps={k:v for k,section in rec["method"].items()
                      for k,v in section.items() if k.endswith("capped")},
            wall_s=rec["screen_wall_s"]),sort_keys=True),flush=True)
    print("GF2_SCREEN6_SHARD_PASS "+json.dumps(dict(shard=i,sources=len(out)),sort_keys=True),flush=True)

def audit():
    m=verify()
    all_records=[]
    for i in range(SHARDS):
        p=ROOT/f"shard-{i}.json"
        need(p.is_file(),"missing source shard "+str(i))
        records=json.loads(p.read_text())
        expected=[c for j,c in enumerate(m["cases"]) if j%SHARDS==i]
        need(len(records)==len(expected),"incomplete source coverage")
        for c,rec in zip(expected,records):
            reverify_record(c,rec)
            all_records.append(rec)
    need(len(all_records)==COUNT and
         len({r["source_sha256"] for r in all_records})==COUNT,
         "complete 17 distinct sources not audited")
    root_fields=("complete_source_blocks","complete_source_XOR_post_units",
                 "source_root_unit_rows","source_root_empty_contradictions")
    totals={k:sum(r["root"][k] for r in all_records) for k in root_fields}
    methods={}
    for method in ("pair","triple","gaussian"):
        methods[method]=dict(
            short_novel=sum(r["method"][method]["unique_short_novel"] for r in all_records),
            strict_shorter=sum(r["method"][method]["strict_shorter"] for r in all_records),
            new_binary=sum(r["method"][method]["new_binary_xor"] for r in all_records),
            new_unary=sum(r["method"][method]["new_units"] for r in all_records),
            new_unsat=sum(r["method"][method]["contradictory_GF2_zero_equals_one"] for r in all_records),
            capped_sources=sum(any(v for k,v in r["method"][method].items()
                if k.endswith("capped") or k=="uniqueness_store_saturated")
                for r in all_records),
            sources_with_short_novel=sum(r["method"][method]["unique_short_novel"]>0
                for r in all_records))
    report=dict(protocol=PROTO,sources=COUNT,shards=SHARDS,original_sha_verified=True,
        source_only_not_blind=True,one_cpu_CDCL_benchmark=False,
        PAR2_not_applicable_to_pure_screening=True,
        independent_original_CNF_parity_replay=True,
        final_proof_full_reverification=True,independent_LRAT=False,
        root_totals=totals,methods=methods,
        baseline_selected100_pairs=sum(r["baseline"]["previous_selected100_pair_short"]
                                       for r in all_records),
        total_screen_wall_s=round(sum(r["screen_wall_s"] for r in all_records),3),
        by_SHA=[dict(sha=r["source_sha256"],source_roots=r["root"]["complete_source_XOR_post_units"],
           baseline100=r["baseline"]["previous_selected100"],
           pair=r["method"]["pair"]["unique_short_novel"],
           triple=r["method"]["triple"]["unique_short_novel"],
           gaussian=r["method"]["gaussian"]["unique_short_novel"],
           pair_strict=r["method"]["pair"]["strict_shorter"],
           triple_strict=r["method"]["triple"]["strict_shorter"],
           gaussian_strict=r["method"]["gaussian"]["strict_shorter"],
           pair_cap=r["method"]["pair"]["pair_enumeration_capped"],
           triple_cap=r["method"]["triple"]["triple_enumeration_capped"],
           gaussian_cap=r["method"]["gaussian"]["gauss_capped"],
           source_contradiction=r["root"]["source_root_empty_contradictions"])
           for r in all_records],
        promising_SHA=[r["source_sha256"] for r in all_records if any(
            r["method"][mode]["strict_shorter"]>0
            for mode in ("pair","triple","gaussian"))])
    save(ROOT/"report.json",report)
    print("GF2_SCREEN6_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    if args.action=="shard":shard(args.shard)
    else:globals()[args.action]()
    if args.action=="verify":print("GF2_SCREEN6_VERIFY_PASS",flush=True)
