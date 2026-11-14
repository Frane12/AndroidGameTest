#!/usr/bin/env python3
"""COOP55: convert bounded failed-literal BCP into a RUP proof-carrying nogood.

Two same-source fallback variants: proof learning OFF/ON. A speculative BCP
conflict under current CDCL decisions and an additional literal justifies the
clause (-literal OR -decision_1 OR ... OR -decision_k) by RUP. No speculative
trail or reason graph is committed. The clause is inserted into actual CDCL
with proof logging, then its asserting literal is enqueued and the main loop
restarts propagation. This is a research experiment, not a production claim.
"""
import pathlib,hashlib,subprocess
R=pathlib.Path(__file__).resolve().parents[2]; B=R/"build"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rep(s,a,b):
    if s.count(a)!=1:raise RuntimeError(f"COOP55_SOURCE_DRIFT count={s.count(a)} {a[:110]!r}")
    return s.replace(a,b)
subprocess.run(["python3",str(R/"research/drnas_coop54/build.py")],cwd=R,check=True)
parent="5bb08736a569daa5b566767e4fe1a8338c6a40816e8e64a34c6bd23f75b35652"
assert sha(B/"drnas-coop54-gate")==parent,"COOP54B pinned source changed"
s=(B/"drnas_coop54_gate.cpp").read_text()
# All returned clauses are RUP with respect to current original+proved learnt
# clauses, because current decision literals plus failed probe assumption unit
# propagate to a conflict. Exhaustive tiny oracle + drat-trim verifies this.
s=rep(s, '    int coop_hint_=-1;',
r'''    static constexpr bool coop55_learn_=COOP55_LEARN!=0;
    int64_t coop55_seen_conflicts_=0,coop55_learned_=0;
    int64_t coop55_skipped_level_=0,coop55_forced_=0;
    bool coop55_pending_propagate_=false;
    void reportCoop55() const {
        std::cerr<<"COOP55_RUP {\"learn_enabled\":"<<(coop55_learn_?"true":"false")
                 <<",\"failed_probe_conflicts\":"<<coop55_seen_conflicts_
                 <<",\"learned_nogoods\":"<<coop55_learned_
                 <<",\"level_or_budget_skips\":"<<coop55_skipped_level_
                 <<",\"forced_literals\":"<<coop55_forced_
                 <<"}\n";
    }
    bool coop55LearnFailed(int failed_literal) {
        if(!coop55_learn_ || coop55_learned_>=32 ||
           decisionLevel()>64 || timedOut() ||
           (timeout_s_>0 && elapsed()>timeout_s_*0.85)) {
            ++coop55_skipped_level_;return false;
        }
        const int v=std::abs(failed_literal)-1;
        if(v<0 || v>=n_ || values_[static_cast<size_t>(v)]!=0)
            throw std::runtime_error("COOP55_FAILED_LITERAL_NOT_FREE");
        std::vector<int> nogood;
        nogood.reserve(static_cast<size_t>(decisionLevel()+1));
        nogood.push_back(-failed_literal);
        for(int level=decisionLevel()-1;level>=0;--level) {
            const int index=trail_lim_[static_cast<size_t>(level)];
            if(index<0 || index>=static_cast<int>(trail_.size()))
                throw std::runtime_error("COOP55_INVALID_DECISION_TRAIL");
            nogood.push_back(-trail_[static_cast<size_t>(index)]);
        }
        // storeClause writes the RUP line into the existing original-CNF DRAT
        // before insertion. -failed_literal is the only currently unassigned
        // literal, so this newly learned clause is asserting.
        const int cid=storeClause(std::move(nogood),true);
        clauses_[static_cast<size_t>(cid)].glue=
            computeGlue(clauses_[static_cast<size_t>(cid)].lits);
        clauses_[static_cast<size_t>(cid)].last_used=stats_.conflicts;
        ++stats_.learnt;
        if(!enqueue(-failed_literal,cid))
            throw std::runtime_error("COOP55_ASSERTION_CONTRADICTION");
        ++coop55_learned_;++coop55_forced_;
        coop55_pending_propagate_=true;
        coop_hint_=-1;
        return true;
    }
    int coop_hint_=-1;''')
s=rep(s,
'''        if(normal.contradiction || guided.contradiction) {
            ++coop5_conflict_probes_;
            ++coop5_rejected_;
            coop5Adjust(false);
            return baseline; // never declare SAT/UNSAT from a probe
        }''',
'''        if(normal.contradiction || guided.contradiction) {
            ++coop5_conflict_probes_;
            ++coop5_rejected_;
            ++coop55_seen_conflicts_;
            coop5Adjust(false);
            const int failed=guided.contradiction?
                phase_[static_cast<size_t>(hint)]*(hint+1):
                phase_[static_cast<size_t>(baseline)]*(baseline+1);
            (void)coop55LearnFailed(failed);
            return baseline; // force via CDCL with proof, never assert UNSAT
        }''')
s=rep(s,
'''            if (v == -1) {
                if (!verifyModel())''',
'''            if(coop55_pending_propagate_){
                // The newly learned clause already asserted a RUP-certified
                // unit under the active trail. Let CDCL propagate/reason
                // BEFORE choosing another decision.
                coop55_pending_propagate_=false;
                continue;
            }
            if (v == -1) {
                if (!verifyModel())''')
s=rep(s,
'        coop_.report(); coop5Report(); reportCoop53();',
'        coop_.report(); coop5Report(); reportCoop53(); reportCoop55();')
for mode,flag in (("shadow","0"),("active","1")):
    dst=B/("drnas_coop55_"+mode+".cpp")
    dst.write_text(s)
    binary=B/("drnas-coop55-"+mode)
    subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG",
                    "-Wall","-Wextra","-Wpedantic","-Werror",
                    "-DCOOP5_DYNAMIC_DEFAULT=0","-DCOOP52_FALLBACK_DEFAULT=1",
                    "-DCOOP53_REPAIR=1","-DCOOP55_LEARN="+flag,
                    str(dst),"-o",str(binary)],cwd=R,check=True)
    print("COOP55_BUILD",mode,sha(binary),flush=True)
print("COOP55_BASELINE_COOP54B_SHA",parent,flush=True)
