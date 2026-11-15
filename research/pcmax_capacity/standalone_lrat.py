#!/usr/bin/env python3
"""Proof-producing, solver-independent RUP/LRAT emitter for DRNAS.

Input: ORIGINAL DIMACS CNF + an independently verified DRNAS structural proof.
Output: proof.drat (DRUP subset of DRAT) + proof.lrat (direct LRAT), or UNKNOWN.
No Kissat/CaDiCaL/CMS, no external SAT solver, no proof post-converter.

A structural witness may supply a source-only *core* to focus the search.
All initial LRAT hints point to exact clause numbers in the ORIGINAL CNF,
and every new LRAT addition is justified by a reconstructed RUP trace.
A bounded, deterministic DPLL search discovers lemmas when no existing DRUP
trace is supplied. A failed or timed-out attempt is always UNKNOWN.

Independent drat-trim + lrat-check verify the final original-source proof.
The generator is a research prototype; large Hall/BDD proofs may exceed
budgets because polynomial-size structural proofs need not have short RUP
proofs without suitable extensions.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import time

from bridge_standard import CHECKERS, extract_core
from check_capacity import parse_cnf

class ProofBudget(Exception):
    pass

class InconsistentCore(Exception):
    pass

def original_clauses(raw):
    """Preserve original DIMACS input order for LRAT clause IDs.

    No reordering of source, and no mapping through preprocessed clauses.
    Each zero token ends a clause, even across multiple physical lines.
    """
    try:
        lines=raw.decode("ascii").splitlines()
    except UnicodeDecodeError as e:
        raise ValueError("CNF is not ASCII") from e
    header=None
    source=[]
    pending=[]
    for line in lines:
        words=line.strip().split()
        if not words or words[0]=="c":continue
        if words[0]=="p":
            if header is not None or len(words)!=4 or words[1]!="cnf":
                raise ValueError("invalid CNF header")
            header=(int(words[2]),int(words[3]))
            if min(header)<0:raise ValueError("negative CNF dimensions")
            continue
        if header is None:raise ValueError("CNF data precedes header")
        for word in words:
            value=int(word)
            if abs(value)>header[0]:raise ValueError("literal out of range")
            if value==0:
                source.append(tuple(sorted(set(pending),key=lambda x:(abs(x),x))))
                pending=[]
            else:pending.append(value)
    if header is None or pending or len(source)!=header[1]:
        raise ValueError("missing header, unterminated clause, or count mismatch")
    return header[0],source

def source_indices(source):
    refs={}
    for i,clause in enumerate(source,1):
        refs.setdefault(frozenset(clause),i)
    return refs

def clauses_from_existing_drup(path):
    clauses=[]
    if path is None or not Path(path).exists():return clauses
    for line in Path(path).read_text().splitlines():
        parts=line.strip().split()
        if not parts or parts[0] in ("c","d"):continue
        nums=[int(x) for x in parts]
        if not nums or nums[-1]!=0 or 0 in nums[:-1]:
            raise ValueError("invalid DRUP line")
        clauses.append(tuple(nums[:-1]))
        if len(clauses)>50000:raise ProofBudget("input DRUP step limit")
    return clauses

class StandaloneRUP:
    """Bounded proof generator with direct hints to original clause indices.

    The only inference rule used is RUP (reverse unit propagation). Each
    accepted lemma is unit-refutable under its negation, and its LRAT hints
    explicitly record the propagation clauses and final conflicting clause.
    """
    def __init__(self,nvars,original,core,budget_s=2.0,max_nodes=4000,
                 max_lemmas=6000,max_core_clauses=14000):
        self.deadline=time.monotonic()+max(0.01,budget_s)
        self.nvars=nvars
        self.max_nodes=max_nodes
        self.max_lemmas=max_lemmas
        self.nodes=0
        self.propagations=0
        if len(core)>max_core_clauses:
            raise ProofBudget("source core exceeds clause limit")
        lookup=source_indices(original)
        if not set(core).issubset(lookup):
            raise ValueError("source-only core contains non-original clause")
        self.db={}
        self.source_count=len(original)
        self.next_id=self.source_count+1
        # Keep original IDs for every source clause used as a hint.
        for clause in sorted(core,key=lambda c:lookup[c]):
            norm=tuple(sorted(clause,key=lambda x:(abs(x),x)))
            if any(-x in clause for x in clause):continue
            self.db[lookup[clause]]=norm
        self.clause_ids=list(self.db)
        self.drat=[]
        self.lrat=[]
        self.rup_cache={}
        self.occ=collections.Counter()
        for clause in self.db.values():
            for lit in clause:self.occ[abs(lit)]+=1
        self.max_clause_length=0
        self.abort_reason=""

    def guard(self):
        if time.monotonic()>self.deadline:raise ProofBudget("time budget")
        if self.nodes>self.max_nodes:raise ProofBudget("search node budget")
        if len(self.lrat)>self.max_lemmas:raise ProofBudget("proof step budget")

    def propagate(self,assumptions):
        """One deterministic UP trace, only source and already-derived lemmas.

        Returns (assignment, ordered LRAT hints, conflict). Each hint is a
        unit clause under the current assignment or the final empty clause.
        """
        self.propagations+=1
        assignment={}
        for lit in assumptions:
            var=abs(lit)
            sign=lit>0
            if var==0 or var>self.nvars:raise ValueError("invalid assumption")
            if var in assignment and assignment[var]!=sign:
                # Do not emit a lemma with contradictory decisions.
                raise InconsistentCore("conflicting branch assumptions")
            assignment[var]=sign
        hints=[]
        change=True
        while change:
            self.guard()
            change=False
            for i,cid in enumerate(self.clause_ids):
                if (i&1023)==0:self.guard()
                clause=self.db[cid]
                satisfied=False
                pending=0
                unit=0
                for lit in clause:
                    value=assignment.get(abs(lit))
                    if value is None:
                        pending+=1
                        unit=lit
                        if pending>1:break
                    elif value==(lit>0):
                        satisfied=True
                        break
                if satisfied:continue
                if pending>1:
                    # The early break above may have skipped a TRUE literal.
                    # Recheck candidate before classifying it as unresolved.
                    continue
                if pending==0:
                    hints.append(cid)
                    return assignment,hints,True
                variable=abs(unit)
                value=unit>0
                if variable in assignment:
                    # This can occur only if a contradictory assumption was
                    # processed; the upstream branch guard forbids it.
                    if assignment[variable]!=value:
                        hints.append(cid)
                        return assignment,hints,True
                    continue
                assignment[variable]=value
                hints.append(cid)
                change=True
        return assignment,hints,False

    def choose(self,assignment):
        """Branch on a variable of the shortest unresolved source clause."""
        best=None
        key=None
        for i,cid in enumerate(self.clause_ids):
            if (i&1023)==0:self.guard()
            clause=self.db[cid]
            satisfied=False
            pending=[]
            for lit in clause:
                val=assignment.get(abs(lit))
                if val is None:pending.append(lit)
                elif val==(lit>0):
                    satisfied=True
                    break
            if satisfied:continue
            if not pending:raise InconsistentCore("missed conflict in propagation")
            option=min(pending,key=lambda lit:(-self.occ[abs(lit)],abs(lit)))
            score=(len(pending),-self.occ[abs(option)],abs(option))
            if key is None or score<key:
                key=score
                best=option
        return best

    def add_nogood(self,decisions,hints):
        self.guard()
        clause=tuple(-lit for lit in decisions)
        if len({abs(l) for l in clause})!=len(clause):
            raise InconsistentCore("duplicate decision literal")
        canonical=tuple(sorted(clause,key=lambda x:(abs(x),x)))
        if canonical in self.rup_cache:return self.rup_cache[canonical]
        if not hints:
            # For a nonempty clause, contradictory assumptions would make it
            # tautological. This branch structure never creates such clauses.
            raise InconsistentCore("RUP proof has no source conflict")
        cid=self.next_id
        self.next_id+=1
        self.db[cid]=canonical
        self.clause_ids.append(cid)
        for lit in canonical:self.occ[abs(lit)]+=1
        self.drat.append(" ".join(map(str,canonical))+(" " if canonical else "")+"0")
        self.lrat.append(str(cid)+" "+(" ".join(map(str,canonical))+" " if canonical else "")+
                         "0 "+" ".join(map(str,hints))+" 0")
        self.rup_cache[canonical]=cid
        self.max_clause_length=max(self.max_clause_length,len(canonical))
        return cid

    def import_drup(self,existing):
        """Re-hint existing RUP proof, reconstructing each LRAT line ourselves."""
        for clause in existing:
            self.guard()
            if len(set(map(abs,clause)))!=len(clause):
                raise InconsistentCore("tautology in claimed DRUP proof")
            _,hints,conflict=self.propagate([-x for x in clause])
            if not conflict:raise InconsistentCore("input proof contains non-RUP step")
            self.add_nogood([-x for x in clause],hints)
        if not existing or existing[-1]:
            raise InconsistentCore("proof did not end with the empty clause")

    def search(self,decisions=()):
        self.nodes+=1
        self.guard()
        assignment,hints,conflict=self.propagate(decisions)
        if conflict:
            return self.add_nogood(decisions,hints)
        pivot=self.choose(assignment)
        if pivot is None:
            raise InconsistentCore("extracted core unexpectedly SAT")
        # Try a source-falsifying choice first; both children must close.
        self.search((*decisions,-pivot))
        self.search((*decisions,pivot))
        _,hints,conflict=self.propagate(decisions)
        if not conflict:
            raise InconsistentCore("child proofs failed to imply parent")
        return self.add_nogood(decisions,hints)

    def emit(self,drat,lrat):
        if not self.drat or self.drat[-1]!="0":
            raise InconsistentCore("no refutation of empty clause")
        if len(self.drat)!=len(self.lrat):
            raise InconsistentCore("DRAT/LRAT steps mismatch")
        Path(drat).write_text("\n".join(self.drat)+"\n")
        Path(lrat).write_text("\n".join(self.lrat)+"\n")

def produce(src,cert_path,out,budget_s=2.0,nodes=4000,
            existing_drup=None,max_core_clauses=14000):
    started=time.monotonic()
    raw=Path(src).read_bytes()
    source_sha=hashlib.sha256(raw).hexdigest()
    nvars,original=original_clauses(raw)
    result={"status":"UNKNOWN","source_sha256":source_sha,"method":"none",
            "source_clauses":len(original),"source_vars":nvars,
            "core_clauses":0,"proof_steps":0,"nodes":0,
            "native_proof_generator":True,"uses_external_solver":False,
            "standalone_drat":False,"standalone_lrat":False,
            "format":"DRUP_subset_of_DRAT_and_direct_LRAT"}
    out=Path(out)
    out.mkdir(parents=True,exist_ok=False)
    try:
        proof=json.loads(Path(cert_path).read_text())
        if proof.get("source_sha256")!=source_sha:
            raise ValueError("source certificate hash mismatch")
        fmt=proof.get("format")
        if fmt not in CHECKERS:
            raise ValueError("unsupported certificate format")
        # Never accept a certificate solely from the producer's claim.
        evidence=CHECKERS[fmt](raw,proof)
        if "VERIFIED" not in evidence["status"]:
            raise ValueError("source-bound structural certificate did not verify")
        result["method"]=fmt
        _,core=extract_core(raw,proof)
        if not core:
            # For mixed proofs, use the exact clauses sufficient for this
            # method if possible, or the complete original for tiny inputs.
            if len(original)<=512:
                core=set(frozenset(c) for c in original)
            else:
                raise ProofBudget("unsupported large mixed proof core")
        result["core_clauses"]=len(core)
        builder=StandaloneRUP(nvars,original,core,budget_s=budget_s,
                              max_nodes=nodes,max_core_clauses=max_core_clauses)
        if existing_drup and Path(existing_drup).is_file():
            # Rehint only, no SAT-search or other solver.
            builder.import_drup(clauses_from_existing_drup(existing_drup))
            result["mode"]="direct_lrat_from_existing_rup"
        else:
            builder.search()
            result["mode"]="source_core_proof_producing_dpll"
        builder.emit(out/"proof.drat",out/"proof.lrat")
        result.update(status="STANDALONE_PROOF_EMITTED",
                      standalone_drat=True,standalone_lrat=True,
                      proof_steps=len(builder.lrat),nodes=builder.nodes,
                      max_clause_length=builder.max_clause_length,
                      original_clause_ids=True)
    except (ProofBudget,InconsistentCore,ValueError,MemoryError,RecursionError,KeyError) as exc:
        result["reason"]=type(exc).__name__+": "+str(exc)
    result["generator_s"]=round(time.monotonic()-started,6)
    (out/"producer.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    return result

def main():
    a=argparse.ArgumentParser()
    a.add_argument("cnf",type=Path)
    a.add_argument("--certificate",type=Path,required=True)
    a.add_argument("--out",type=Path,required=True)
    a.add_argument("--budget-s",type=float,default=2.0)
    a.add_argument("--max-nodes",type=int,default=4000)
    a.add_argument("--max-core-clauses",type=int,default=14000)
    a.add_argument("--existing-drup",type=Path)
    args=a.parse_args()
    if not (0.02<=args.budget_s<=30):a.error("budget-s out of range")
    result=produce(args.cnf,args.certificate,args.out,args.budget_s,
                   args.max_nodes,args.existing_drup,args.max_core_clauses)
    print("STANDALONE_PROOF "+json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
