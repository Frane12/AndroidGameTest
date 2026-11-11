"""LTM5: reversible graph transformations over certified source XOR relations.

Offline CDCL-state simulator / algebraic proof demonstrator, NOT a native
solver callback. Every derived row contains a parity proof over certified
source rows. A signed assignment transforms the row only CONDITIONALLY;
rollback restores previous states without changing the source formula.
"""
import hashlib
import json
from dataclasses import dataclass

try:
    from mi_ltm4.graph_shadow import graph
except ImportError:
    from graph_shadow import graph


@dataclass(frozen=True)
class XRow:
    variables: frozenset
    rhs: int
    provenance: frozenset

    def __post_init__(self):
        if self.rhs not in (0,1):
            raise ValueError("GF2 parity must be 0/1")


def row_from_source(source,index):
    return XRow(frozenset(source[index]["variables"]),
                int(source[index]["rhs"]),frozenset([index]))


def combine(a,b):
    """Exact XOR sum; provenance is also XORed, preserving cancellation."""
    return XRow(a.variables ^ b.variables, a.rhs ^ b.rhs,
                a.provenance ^ b.provenance)


def audit(row,sources):
    variables=frozenset()
    rhs=0
    if not row.provenance:
        return not row.variables and row.rhs==0
    for index in row.provenance:
        if not 0 <= index < len(sources):
            return False
        variables ^= frozenset(sources[index]["variables"])
        rhs ^= int(sources[index]["rhs"])
    return variables==row.variables and rhs==row.rhs


def restrict(row,assignments):
    """Condition a *proved* XOR equation on the current partial assignment."""
    vars_left=row.variables.difference(assignments)
    value=row.rhs
    for v in row.variables.intersection(assignments):
        value ^= int(bool(assignments[v]))
    return XRow(frozenset(vars_left),value,row.provenance)


def state_pattern(rows,assignments):
    """State signature invariant to variable renaming, NOT a proof of
    graph isomorphism. Polarity-sensitive parity is preserved."""
    entries=[]
    for row in rows:
        restricted=restrict(row,assignments)
        entries.append((len(row.variables),len(restricted.variables),
                        restricted.rhs,
                        sum(v in assignments for v in row.variables)))
    serialized=json.dumps(sorted(entries),separators=(",",":"))
    return hashlib.sha256(serialized.encode()).hexdigest()[:24]


class GraphTrajectory:
    def __init__(self,clauses):
        structural=graph(clauses)
        self.sources=structural["rows"]
        self.rows=[row_from_source(self.sources,i)
                   for i in range(len(self.sources))]
        self.initial_signature=structural["signature"]
        self.assignments={}
        self.level=0
        self.frames=[]
        self.events=[]
        self._emit("initial",source_count=len(self.sources))

    def _emit(self,kind,**info):
        current=[restrict(row,self.assignments) for row in self.rows]
        units=sum(len(row.variables)==1 for row in current)
        conflicts=sum(not row.variables and row.rhs for row in current)
        self.events.append(dict(
            kind=kind,level=self.level,assigned=len(self.assignments),
            active_units=units,active_conflicts=conflicts,
            state_signature=state_pattern(self.rows,self.assignments),
            **info))

    def decide(self,variable,value):
        variable=int(variable)
        if variable <= 0 or variable in self.assignments:
            raise ValueError("Decision must assign a new positive variable ID")
        self.frames.append((self.level,dict(self.assignments)))
        self.level+=1
        self.assignments[variable]=bool(value)
        self._emit("decision",value=bool(value))
        return self.current()

    def propagate(self,variable,value):
        variable=int(variable)
        if variable in self.assignments and self.assignments[variable]!=bool(value):
            raise ValueError("Conflicting propagation")
        self.assignments[variable]=bool(value)
        self._emit("propagation")
        return self.current()

    def backtrack(self,target_level):
        if target_level < 0 or target_level >= self.level:
            raise ValueError("Expected an earlier decision level")
        while self.level>target_level:
            previous_level,previous_assignments=self.frames.pop()
            self.level=previous_level
            self.assignments=previous_assignments
        self._emit("backtrack",target_level=target_level)
        return self.current()

    def derive_pair(self,i,j):
        if not 0<=i<len(self.rows) or not 0<=j<len(self.rows):
            raise IndexError("XOR graph row index out of range")
        row=combine(self.rows[i],self.rows[j])
        if not audit(row,self.sources):
            raise AssertionError("Invalid source proof in graph transformation")
        self._emit("algebraic_xor",from_rows=[i,j],
                   derived_width=len(row.variables),
                   proof_indices=sorted(row.provenance))
        return row

    def current(self):
        result=[]
        for row in self.rows:
            transformed=restrict(row,self.assignments)
            status=("conflict" if not transformed.variables and transformed.rhs
                    else "satisfied" if not transformed.variables
                    else "unit_candidate" if len(transformed.variables)==1
                    else "inactive")
            result.append(dict(status=status,
                               remaining=sorted(transformed.variables),
                               rhs=transformed.rhs,
                               provenance=sorted(row.provenance)))
        return result

    def transition_histogram(self):
        counts={}
        for before,after in zip(self.events,self.events[1:]):
            # This is a coarse, rename-invariant *transition-class*
            # representation, not a proof of equal graphs/trajectories.
            key=("%s:units%d>%d:conflicts%d>%d" %
                 (after["kind"],before["active_units"],after["active_units"],
                  before["active_conflicts"],after["active_conflicts"]))
            counts[key]=counts.get(key,0)+1
        return counts

    def trajectory_key(self):
        """Two formulas can share a coarse movement motif even with
        different variable names. No clauses are transferable from it."""
        sequence=[(x["kind"],x["active_units"],x["active_conflicts"])
                  for x in self.events]
        return hashlib.sha256(json.dumps(sequence,separators=(",",":")).encode()).hexdigest()[:24]
