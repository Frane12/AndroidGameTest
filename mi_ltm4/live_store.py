"""LTM4.1 long-term *observational* memory for native CDCL episodes.

Records only anonymized, variable-renaming-invariant event motifs and
co-occurring certified XOR motifs. This is a distinct namespace from the
proof-carrying GF(2) memory. Neither source conclusions, learned clauses nor
SAT/UNSAT outcomes can be loaded from this memory into the native engine.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS native_motifs(
  formula_sha TEXT NOT NULL,
  motif_key TEXT NOT NULL,
  reason_dependency_observed INTEGER NOT NULL,
  PRIMARY KEY(formula_sha,motif_key)
);
CREATE INDEX IF NOT EXISTS native_motifs_key ON native_motifs(motif_key);
CREATE TABLE IF NOT EXISTS cross_motifs(
  formula_sha TEXT NOT NULL,
  native_motif_key TEXT NOT NULL,
  xor_motif_key TEXT NOT NULL,
  PRIMARY KEY(formula_sha,native_motif_key,xor_motif_key)
);
"""

class NativeTraceMemory:
    def __init__(self,path,*,readonly=False):
        self.readonly=readonly
        if readonly:
            self.db=sqlite3.connect("file:"+str(Path(path).resolve())+"?mode=ro",uri=True)
        else:
            self.db=sqlite3.connect(str(path))
            self.db.executescript(SCHEMA)

    def remember(self,sha,trace,algebraic_motif_keys,*,max_cross=96):
        if self.readonly:
            raise PermissionError("Holdout evaluations cannot mutate memory")
        if not sha or not isinstance(trace,dict) or trace.get("kind")!="passive_native_cdcl_trace":
            raise ValueError("Invalid native trace")
        cdcl={}
        for ep in trace.get("episodes",[]):
            key=ep.get("key")
            if not ep.get("observational_only") or not isinstance(key,str) or not key.startswith("cdcl4:"):
                raise ValueError("Only audited native event observations accepted")
            cdcl[key]=int(bool(ep.get("reason_graph_available")))
        algebra=sorted(k for k in set(algebraic_motif_keys)
                       if isinstance(k,str) and k.startswith("traj4:"))
        cross=[(sha,cd,ex)
               for cd in sorted(cdcl) for ex in algebra][:max_cross]
        with self.db:
            self.db.executemany(
                "INSERT OR REPLACE INTO native_motifs VALUES (?,?,?)",
                [(sha,k,dep) for k,dep in cdcl.items()])
            self.db.executemany(
                "INSERT OR IGNORE INTO cross_motifs VALUES (?,?,?)",cross)

    def freeze(self,forbidden_shas):
        forbidden=set(forbidden_shas)
        native=defaultdict(set)
        reason=defaultdict(set)
        cross=defaultdict(set)
        all_shas=set()
        for sha,key,dependency in self.db.execute(
                "SELECT formula_sha,motif_key,reason_dependency_observed FROM native_motifs"):
            if sha in forbidden:
                raise AssertionError("Holdout leaked into native trace memory")
            all_shas.add(sha)
            native[key].add(sha)
            if dependency:
                reason[key].add(sha)
        for sha,cd,xor in self.db.execute(
                "SELECT formula_sha,native_motif_key,xor_motif_key FROM cross_motifs"):
            if sha in forbidden:
                raise AssertionError("Holdout leaked into cross-representation memory")
            all_shas.add(sha)
            cross[(cd,xor)].add(sha)
        outcome={
            "schema":"LTM4.1-OBSERVATION-ONLY",
            "training_formula_count":len(all_shas),
            "native_support":{k:len(v) for k,v in sorted(native.items())},
            "reason_dependency_support":{k:len(v) for k,v in sorted(reason.items())},
            "cross_support":{k[0]+"|"+k[1]:len(v)
                             for k,v in sorted(cross.items())},
            "active_policy":"BASE_ONLY_NO_CAUSAL_EVIDENCE"
        }
        outcome["snapshot_sha256"]=hashlib.sha256(json.dumps(
            outcome,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        return outcome

    def close(self):
        self.db.close()


def recognize(snapshot,trace,algebra_keys):
    observed={e["key"] for e in trace["episodes"]}
    pairs={cd+"|"+alg for cd in observed for alg in algebra_keys}
    return dict(
        observed_native_motifs=len(observed),
        matched_native_motifs=len(observed&set(snapshot["native_support"])),
        matched_cross_patterns=len(pairs&set(snapshot["cross_support"])),
        proposed_action="BASE",
        reason="No causally validated online policy: diagnostic only")
