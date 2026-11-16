#!/usr/bin/env python3
"""DRNAS IPG7-B: configuration-guided DIRECT ORIGINAL CNF source-RUP proof.

This fills the original-standard-proof gap left by IPG7's 7-step
DERIVED configuration master. From a COMPLETELY SOURCE-VALIDATED original
three-machine minimal-overweight CNF, enumerate all exact-capacity masks.

When all such masks pairwise INTERSECT, a complete schedule is impossible.
For EACH exact mask S, emit a source-unit-propagation (RUP) derivation of

    OR_{j in S} ~x_(j,machine0) >= 1

which blocks filling machine0 with configuration S. This is a sound
consequence of the ORIGINAL 300-clause weighted source and captures an
actual lemma linking the short configuration argument to the source.

Then derive the final empty clause with source-RUP branching given all
the blocked configurations. The concatenated RUP trace is independently
replayed and converted to ONE STANDARD VeriPB proof checked DIRECTLY
against the ORIGINAL CNF, not against a projection.

IMPORTANT: Each per-configuration proof and the closing proof use
BOUNDED DPLL decision trees and source unit propagation. The master's
7-line pure POL proof is not literally imported into the source
certificate. We formalize its six full-bin EXCLUSIONS via RUP/VeriPB.
This is a standard original-CNF result, but NOT a search-free CP bridge,
not polynomial general PCMAX, and potentially slower than IPG5B's
existing 100-step DPLL proof. No main change and no SAT/CDCL solver.
"""
import argparse
import hashlib
import json
import pathlib
import sys
import time

from ipg7_config_master import read_dimacs,source_profile,sums

MAX_NODES=120000
MAX_STEPS=120000
MAX_SECONDS=25.0

def clause_bits(clause):
    pos=neg=0
    for lit in clause:
        if lit>0:pos|=1<<(lit-1)
        else:neg|=1<<(-lit-1)
    return pos,neg

def up(clauses,positive,negative):
    """Pure original-source unit propagation, no CDCL learning."""
    if positive&negative:return True,positive,negative
    while True:
        new_pos=new_neg=0
        used=positive|negative
        for pos,neg in clauses:
            if pos&positive or neg&negative:continue
            remaining_pos=pos&~used
            remaining_neg=neg&~used
            available=remaining_pos|remaining_neg
            if not available:return True,positive,negative
            if not(available&(available-1)):
                if remaining_pos:new_pos|=remaining_pos
                else:new_neg|=remaining_neg
        if (new_pos&(negative|new_neg)) or (new_neg&positive):
            return True,positive,negative
        if not ((new_pos|new_neg)&~used):
            return False,positive,negative
        positive|=new_pos
        negative|=new_neg

class SourceBranchProof:
    def __init__(self,clauses,weights,max_seconds=MAX_SECONDS):
        self.original=[clause_bits(c) for c in clauses]
        self.weights=weights
        self.jobs=len(weights)
        self.deadline=time.perf_counter()+max_seconds
        self.nodes=0
        self.conflict_leaves=0
        self.proof=[]
        self.case_proof_lengths=[]
        self.order=sorted(range(self.jobs),key=lambda j:(-weights[j],j))

    @staticmethod
    def bit(lit):
        return 1<<(lit-1)

    def append(self,path):
        if len(self.proof)>=MAX_STEPS:
            raise TimeoutError("RUP certificate step cap")
        self.proof.append(tuple(-lit for lit in path))

    def visit(self,source_clauses,path,positive,negative):
        self.nodes+=1
        if self.nodes>MAX_NODES or time.perf_counter()>self.deadline:
            raise TimeoutError("source configuration proof tree cap")
        bad,tr,fl=up(source_clauses,positive,negative)
        if bad:
            self.conflict_leaves+=1
            self.append(path)
            return
        choice=None
        for j in self.order:
            available=[]
            assigned=False
            for m in range(3):
                v=3*j+m+1
                if tr&self.bit(v):assigned=True
                if not(fl&self.bit(v)):available.append(v)
            if assigned:continue
            if len(available)<2:
                raise ValueError("unsupported incomplete original exactly-one UP")
            if choice is None or len(available)<len(choice):
                choice=available
        if choice is None:
            raise ValueError("SAT model during purported source UNSAT proof")
        for v in choice:
            path.append(v)
            self.visit(source_clauses,path,tr|self.bit(v),fl)
            path.pop()
        self.append(path)

    def one_configuration(self,mask):
        """Refute every source model with the machine-0 exact-T mask chosen."""
        S=[j for j in range(self.jobs) if mask&(1<<j)]
        fixed=[3*j+1 for j in S]
        true=sum(self.bit(v) for v in fixed)
        before=len(self.proof)
        self.visit(self.original,fixed[:],true,0)
        if self.proof[-1]!=tuple(-v for v in fixed):
            raise ValueError("configuration blocker root not derived")
        self.case_proof_lengths.append(len(self.proof)-before)
        return self.proof[-1]

    def refute_source(self):
        """Close ORIGINAL formula with earlier source-implied configuration blockers."""
        augmented=self.original+[clause_bits(c) for c in self.proof]
        starting=len(self.proof)
        self.visit(augmented,[],0,0)
        if self.proof[-1]:
            raise ValueError("source proof has no terminal empty clause")
        return len(self.proof)-starting

    def replay_all(self):
        """Local RUP replay on the exact original source; external check required."""
        database=self.original[:]
        for i,clause in enumerate(self.proof,1):
            tr=fl=0
            for lit in clause:
                if lit>0:fl|=self.bit(lit)
                else:tr|=self.bit(-lit)
            if not up(database,tr,fl)[0]:
                raise ValueError(f"invalid original-source RUP clause at index {i}")
            database.append(clause_bits(clause))
        return True

def generate(source,weights,capacity,prefix,budget_seconds):
    start=time.perf_counter()
    raw=source.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    loads,source_clauses=source_profile(raw,weights,capacity)
    if sum(weights)!=3*capacity:
        raise ValueError("total_load_not_equal_three_T")
    configs=[i for i,total in enumerate(loads) if total==capacity]
    if not configs or len(configs)>32:
        raise ValueError("no_supportable_complete_configuration_profile")
    if any(not(a&b) for a in configs for b in configs):
        raise ValueError("source SAT: two disjoint full-machine configs exist")
    nvars,clauses=read_dimacs(raw)
    if nvars!=3*len(weights) or source_clauses!=len(clauses):
        raise ValueError("source changed after profile extraction")
    engine=SourceBranchProof(clauses,weights,budget_seconds)
    positions=[]
    for mask in configs:
        blocker=engine.one_configuration(mask)
        positions.append({"machine":0,"mask":mask,
                          "job_indices":[j for j in range(len(weights)) if mask>>j&1],
                          "clause":list(blocker),
                          "proof_position_1based":len(engine.proof),
                          "source_case_steps":engine.case_proof_lengths[-1]})
    closure_steps=engine.refute_source()
    engine.replay_all()
    prefix.parent.mkdir(parents=True,exist_ok=True)
    rup=prefix.with_suffix(".original.rup")
    with rup.open("w") as f:
        for clause in engine.proof:
            f.write(" ".join(map(str,clause))+" 0\n")
    metadata={
        "format":"DRNAS-IPG7B-ORIGINAL-CONFIG-RUP-V1",
        "status":"ORIGINAL_SOURCE_RUP_NEEDS_INDEPENDENT_DRAT_VERIPB",
        "original_source_sha256":digest,
        "original_source_vars":nvars,"original_source_clauses":len(clauses),
        "weights":weights,"capacity":capacity,
        "machine_count":3,"exact_capacity_masks":configs,
        "configurations_count":len(configs),
        "configuration_source_no_good_blocks":positions,
        "configuration_case_rup_steps":sum(engine.case_proof_lengths),
        "post_configuration_original_closure_rup_steps":closure_steps,
        "total_original_RUP_steps":len(engine.proof),
        "original_RUP_replay_passed":True,
        "search_nodes":engine.nodes,"UP_conflict_leaves":engine.conflict_leaves,
        "original_rup_sha256":hashlib.sha256(rup.read_bytes()).hexdigest(),
        "original_rup_bytes":rup.stat().st_size,
        "generation_s":round(time.perf_counter()-start,6),
        "DPLL_case_splitting_used":True,
        "CDCL_or_external_SAT_solver_used":False,
        "VeriPB_must_check_against_ORIGINAL_source":True,
        "derived_master_pure_PB_separately_verifiable":True,
        "limitation":"The FULL original-source bridge uses bounded DPLL case splits. It does not literally transplant the 7-line master proof or prove polynomial-time original PCMAX.",
    }
    dest=prefix.with_suffix(".certificate.json")
    dest.write_text(json.dumps(metadata,sort_keys=True,indent=2)+"\n")
    return metadata

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",required=True,type=pathlib.Path)
    p.add_argument("--weights-json",required=True,type=pathlib.Path)
    p.add_argument("--prefix",required=True,type=pathlib.Path)
    p.add_argument("--max-seconds",type=float,default=MAX_SECONDS)
    a=p.parse_args()
    try:
        spec=json.loads(a.weights_json.read_text())
        if spec.get("machines")!=3 or not .05<=a.max_seconds<=60:
            raise ValueError("unsupported source machine count/budget")
        report=generate(a.cnf,spec["weights"],spec["capacity"],a.prefix,a.max_seconds)
        print("IPG7B_DIRECT_ORIGINAL "+json.dumps({
            k:v for k,v in report.items() if k!="configuration_source_no_good_blocks"
        },sort_keys=True),flush=True)
        return 0
    except (OSError,ValueError,KeyError,TypeError,IndexError,OverflowError,
            UnicodeError,TimeoutError) as err:
        for ext in (".original.rup",".certificate.json"):
            a.prefix.with_suffix(ext).unlink(missing_ok=True)
        print("IPG7B_UNKNOWN "+str(err),flush=True)
        return 1
if __name__=="__main__":sys.exit(main())
