#!/usr/bin/env python3
"""CF6: fixed-budget, first-reduction clause swaps from the pinned CF5 core.

A pre-registered, source-blind experiment. The only algorithmic difference is
the set of unlocked learnt clauses deleted at the FIRST effective reduction.
Later CDCL, BCP, 1-UIP, restarts, proofs and deletion policy are untouched.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

R = Path(__file__).resolve().parents[1]
B = R / "build"
BASE = B / "drnas_clause_cf5.cpp"
SOURCE = B / "drnas_clause_cf6.cpp"
OUT = B / "drnas-clause-cf6"
PIN_CF5_SOURCE = "2d1ebcc42be6872819b08f9711df24b738e79273c9504e4d194e0b4cf4769a4e"
PIN_CF5_BINARY = "286626e221568b3c7541da7a1514fdee55f1462d4d0028a775cc5c7d0561fd5f"
ARMS = ("BASE", "LBD", "B2L_1", "B2L_8", "B2L_32",
        "L2B_1", "L2B_8", "L2B_32")

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def once(s, a, b):
    n = s.count(a)
    if n != 1:
        raise RuntimeError(("CF6_PINNED_SOURCE_ANCHOR_DRIFT", n, a[:170]))
    return s.replace(a, b)

def build():
    subprocess.run([sys.executable, str(R / "research/drnas_clause_cf5_build.py")],
                   cwd=R, check=True)
    assert sha(BASE) == PIN_CF5_SOURCE, ("CF5_SOURCE_NOT_FROZEN", sha(BASE))
    assert sha(B / "drnas-clause-cf5") == PIN_CF5_BINARY, "CF5_BINARY_NOT_FROZEN"
    s = BASE.read_text()
    s = once(s,
        'if(policy!="BASE" && policy!="LBD" && policy!="RECENT" && policy!="HASH")',
        'if(policy!="BASE" && policy!="LBD" && policy!="RECENT" && policy!="HASH"'
        ' && policy!="B2L_1" && policy!="B2L_8" && policy!="B2L_32"'
        ' && policy!="L2B_1" && policy!="L2B_8" && policy!="L2B_32")')

    s = once(s, '    void reportCf5() const {', r'''
    void configureCf6Snapshot(const std::string& path) {
        cf6_snapshot_path_=path;
    }
    void reportCf6() const {
        int64_t kept=0,deleted=0,kept_preuse=0,deleted_preuse=0;
        int64_t kept_bcp100=0, kept_analysis100=0, kept_bcp500=0, kept_analysis500=0;
        for(const auto& q:cf5_first_cohort_) {
            if(q.cf6_role==1) {
                if(q.deleted)throw std::runtime_error("CF6 kept swap was deleted");
                ++kept;kept_preuse+=q.preuse;
                kept_bcp100+=q.bcp100;kept_analysis100+=q.analysis100;
                kept_bcp500+=q.bcp500;kept_analysis500+=q.analysis500;
            }else if(q.cf6_role==2) {
                if(!q.deleted)throw std::runtime_error("CF6 deleted swap was retained");
                ++deleted;deleted_preuse+=q.preuse;
            }
        }
        std::cerr<<"CLCF6_STATS {\"policy\":\""<<cf5_policy_
                 <<"\",\"first_effective_reduce\":"<<(cf5_first_done_?"true":"false")
                 <<",\"first_candidate_digest\":"<<cf5_first_digest_
                 <<",\"candidate_count\":"<<cf5_first_cohort_.size()
                 <<",\"same_delete_count\":"<<cf5_first_deleted_
                 <<",\"mismatch_pairs\":"<<cf6_mismatch_pairs_
                 <<",\"pair_digest\":"<<cf6_pair_digest_
                 <<",\"requested_swaps\":"<<cf6_requested_swaps_
                 <<",\"actual_swaps\":"<<cf6_actual_swaps_
                 <<",\"swapped_in_kept\":"<<kept
                 <<",\"swapped_out_deleted\":"<<deleted
                 <<",\"swapped_in_preused\":"<<kept_preuse
                 <<",\"swapped_out_preused\":"<<deleted_preuse
                 <<",\"swapped_in_bcp100\":"<<kept_bcp100
                 <<",\"swapped_in_analysis100\":"<<kept_analysis100
                 <<",\"swapped_in_bcp500\":"<<kept_bcp500
                 <<",\"swapped_in_analysis500\":"<<kept_analysis500
                 <<"}\n";
    }
    void reportCf5() const {''')

    s = once(s, '    std::string cf5_policy_="BASE";',
        '''    std::string cf5_policy_="BASE";
    std::string cf6_snapshot_path_;
    int cf6_mismatch_pairs_=0,cf6_actual_swaps_=0,cf6_requested_swaps_=0;
    uint64_t cf6_pair_digest_=0;''')

    s = once(s,
        '''        int64_t bcp100=0,analysis100=0,bcp500=0,analysis500=0;
    };''',
        '''        int64_t bcp100=0,analysis100=0,bcp500=0,analysis500=0;
        int cf6_role=0; // 1=retained by a controlled swap; 2=deleted by swap
    };''')

    # Insert only after the original CF5 ranking has completed. All pre-split
    # analysis, candidate enumeration, learnt clauses, and first-state digest
    # are bit-identical to CF5. Sorting the comparator only changes deletion.
    anchor = '            for(size_t k=0;k<candidates.size()/(x5_retain_?3:2);++k) {'
    injection = r'''            if(first) {
                const size_t cutoff=candidates.size()/(x5_retain_?3:2);
                auto base_order=candidates;
                auto original_cmp=[&](int a,int b) {
                    const Clause& ca=clauses_[static_cast<size_t>(a)];
                    const Clause& cb=clauses_[static_cast<size_t>(b)];
                    if(ca.activity!=cb.activity)return ca.activity<cb.activity;
                    if(ca.lits.size()!=cb.lits.size())
                        return ca.lits.size()>cb.lits.size();
                    return a<b;
                };
                std::sort(base_order.begin(),base_order.end(),original_cmp);
                auto lbd_order=base_order;
                std::sort(lbd_order.begin(),lbd_order.end(),[&](int a,int b) {
                    const Clause& ca=clauses_[static_cast<size_t>(a)];
                    const Clause& cb=clauses_[static_cast<size_t>(b)];
                    if(ca.glue!=cb.glue)return ca.glue>cb.glue;
                    return original_cmp(a,b);
                });
                std::vector<uint8_t> base_deleted(clauses_.size(),0);
                std::vector<uint8_t> lbd_deleted(clauses_.size(),0);
                for(size_t k=0;k<cutoff;++k) {
                    base_deleted[static_cast<size_t>(base_order[k])]=1;
                    lbd_deleted[static_cast<size_t>(lbd_order[k])]=1;
                }
                // A: kept by BASE, deleted by LBD.
                // B: deleted by BASE, kept by LBD.
                std::vector<int> a,b;
                for(int cid:base_order) {
                    if(lbd_deleted[static_cast<size_t>(cid)] &&
                       !base_deleted[static_cast<size_t>(cid)])a.push_back(cid);
                    if(base_deleted[static_cast<size_t>(cid)] &&
                       !lbd_deleted[static_cast<size_t>(cid)])b.push_back(cid);
                }
                std::sort(a.begin(),a.end());
                std::sort(b.begin(),b.end());
                if(a.size()!=b.size())
                    throw std::runtime_error("CF6 mismatch pair symmetry failure");
                cf6_mismatch_pairs_=static_cast<int>(a.size());
                cf6_pair_digest_=1469598103934665603ULL;
                for(size_t k=0;k<a.size();++k) {
                    cf6_pair_digest_^=static_cast<uint64_t>(a[k]);
                    cf6_pair_digest_*=1099511628211ULL;
                    cf6_pair_digest_^=static_cast<uint64_t>(b[k]);
                    cf6_pair_digest_*=1099511628211ULL;
                }
                const bool from_base=cf5_policy_.rfind("B2L_",0)==0;
                const bool from_lbd=cf5_policy_.rfind("L2B_",0)==0;
                if(from_base||from_lbd) {
                    if(x5_retain_)
                        throw std::runtime_error("CF6 experiment requires no-retain");
                    cf6_requested_swaps_=std::stoi(cf5_policy_.substr(4));
                    cf6_actual_swaps_=std::min(cf6_requested_swaps_,
                                              cf6_mismatch_pairs_);
                    std::vector<uint8_t> selected=
                        from_base?base_deleted:lbd_deleted;
                    for(int k=0;k<cf6_actual_swaps_;++k) {
                        const int ai=a[static_cast<size_t>(k)];
                        const int bi=b[static_cast<size_t>(k)];
                        const int kept=from_base?bi:ai;
                        const int deleted=from_base?ai:bi;
                        selected[static_cast<size_t>(kept)]=0;
                        selected[static_cast<size_t>(deleted)]=1;
                        const int kr=clauses_[static_cast<size_t>(kept)].cf5_tracking_id;
                        const int dr=clauses_[static_cast<size_t>(deleted)].cf5_tracking_id;
                        if(kr<0||dr<0)throw std::runtime_error("CF6 missing cohort record");
                        cf5_first_cohort_[static_cast<size_t>(kr)].cf6_role=1;
                        cf5_first_cohort_[static_cast<size_t>(dr)].cf6_role=2;
                    }
                    const size_t actual=static_cast<size_t>(std::count(
                        selected.begin(),selected.end(),static_cast<uint8_t>(1)));
                    if(actual!=cutoff)
                        throw std::runtime_error("CF6 deletion count changed");
                    std::stable_partition(candidates.begin(),candidates.end(),
                        [&](int cid){return selected[static_cast<size_t>(cid)]!=0;});
                }
                // Source-agnostic full candidate identity ledger. Only opt-in
                // TRACE runs write this, never timed performance arms.
                if(!cf6_snapshot_path_.empty()) {
                    std::ofstream out(cf6_snapshot_path_);
                    if(!out)throw std::runtime_error("CF6 snapshot could not open");
                    out<<std::setprecision(17);
                    for(int cid:base_order) {
                        const Clause& c=clauses_[static_cast<size_t>(cid)];
                        uint64_t fingerprint=1469598103934665603ULL;
                        for(int lit:c.lits) {
                            fingerprint^=static_cast<uint64_t>(static_cast<int64_t>(lit));
                            fingerprint*=1099511628211ULL;
                        }
                        out<<"{\"cid\":"<<cid
                           <<",\"lbd\":"<<c.glue
                           <<",\"length\":"<<c.lits.size()
                           <<",\"activity\":"<<c.activity
                           <<",\"last_reason_use_conflict\":"<<c.cf5_last_use
                           <<",\"content_fingerprint\":\""<<std::hex<<fingerprint
                           <<std::dec<<"\",\"base_deleted\":"
                           <<(base_deleted[static_cast<size_t>(cid)]?"true":"false")
                           <<",\"lbd_deleted\":"
                           <<(lbd_deleted[static_cast<size_t>(cid)]?"true":"false")
                           <<"}\n";
                    }
                    if(!out)throw std::runtime_error("CF6 snapshot write failed");
                }
            }
''' + anchor
    s = once(s, anchor, injection)
    s = once(s,
        '    std::string cf5_policy="BASE";',
        '''    std::string cf5_policy="BASE";
    std::string cf6_snapshot_path;''')
    s = once(s,
        '        else if (opt=="--cf5-policy" && i+1<argc) cf5_policy=argv[++i];',
        '''        else if (opt=="--cf5-policy" && i+1<argc) cf5_policy=argv[++i];
        else if (opt=="--cf6-snapshot" && i+1<argc) cf6_snapshot_path=argv[++i];''')
    s = once(s,
        '            solver->configureCf5(cf5_policy);',
        '''            solver->configureCf5(cf5_policy);
            solver->configureCf6Snapshot(cf6_snapshot_path);''')
    s = once(s,
        '        solver->reportCf5();',
        '''        solver->reportCf5();
        solver->reportCf6();''')
    SOURCE.write_text(s)
    subprocess.run(["g++", "-std=c++20", "-O3", "-DNDEBUG", "-Wall",
                    "-Wextra", "-Wpedantic", "-Werror", str(SOURCE), "-o", str(OUT)],
                   cwd=R, check=True)
    print("CLCF6_BUILD", json.dumps({
        "status":"COMPILED",
        "cf5_original_source_sha":PIN_CF5_SOURCE,
        "cf5_original_binary_sha":PIN_CF5_BINARY,
        "cf6_source_sha":sha(SOURCE),
        "cf6_binary_sha":sha(OUT),
        "arms":list(ARMS),
        "identical_native_cdcl_except_first_delete_selection":True,
        "main_modified":False,
        "no_new_proof_clauses":True,
    }, sort_keys=True), flush=True)

if __name__ == "__main__":
    build()
