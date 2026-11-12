#define main embedded_main
#include "audit_core.hpp"
#undef main

int main(){
    using namespace drnas;
    selftest();
    std::mt19937 rng(12062026);
    unsigned checked=0,backtracked=0;
    for(int n=5;n<=12;++n)for(int rep=0;rep<80;++rep){
        CNF f;f.vars=n;
        for(int c=0;c<5*n;++c){
            std::vector<int> vs;for(int v=1;v<=n;++v)vs.push_back(v);
            std::shuffle(vs.begin(),vs.end(),rng);
            vs.resize(2+rng()%std::min(5,n-1));
            for(auto&v:vs)if(rng()&1)v=-v;
            f.clauses.push_back(vs);
        }
        NativeCDCL s(n);s.add_cnf(f);
        const bool expected=brute_sat(f);
        const int result=s.solve(2);
        require(result==(expected?10:20),"bruteforce disagreement");
        if(expected)require(s.verify_original(f),"bad original witness");
        backtracked+=s.statistics().conflicts>0;++checked;
    }
    // Deliberately create entailed duplicate learned clauses, then exercise the
    // real production reduction and compaction code with a locked reason.
    CNF f;f.vars=16;f.clauses={{1}};
    for(int i=0;i<192;++i)f.clauses.push_back({1,2+i%13,2+(i+3)%13,2+(i+7)%13});
    NativeCDCL s(16);s.add_cnf(f);s.atlas16_keep_=true;
    for(size_t i=1;i<f.clauses.size();++i){
        int cid=int(s.clauses_.size());s.clauses_.push_back({f.clauses[i],true});
        s.attach(cid);s.atlas15_lbd_[cid]=10;s.atlas15_born_[cid]=0;++s.atlas15_live_learned_;
    }
    s.reasons_[1]=int(s.clauses_.size())-1; // Root unit is also implied by this satisfied learned clause.
    for(int i=1;i<=25;++i){s.stats_.conflicts=1500*i;s.atlas16_reduce_db();}
    s.atlas16_compact();
    require(s.atlas15_deleted_>0 && s.atlas16_compactions_>0,"reduction/compaction not exercised");
    require(s.reasons_[1]>=0 && !s.clauses_[s.reasons_[1]].lits.empty(),"locked reason lost");
    auto unchanged=s.clauses_;
    s.atlas16_compact(); // Explicit no-tombstone boundary: must not move away live clauses.
    require(s.clauses_.size()==unchanged.size(),"no-op compaction changed size");
    for(size_t i=0;i<unchanged.size();++i)
        require(s.clauses_[i].lits==unchanged[i].lits,"no-op compaction destroyed a clause");
    for(const auto& list:s.watches_)for(const auto& w:list){
        require(w.cid>=0 && size_t(w.cid)<s.clauses_.size(),"stale watch ID");
        const auto& c=s.clauses_[w.cid].lits;
        require(std::find(c.begin(),c.end(),w.blocker)!=c.end(),"stale blocker");
    }
    require(s.solve(2)==10 && s.verify_original(f),"post-compaction solve failed");
    std::cout<<"BCP1_CORE_TEST_PASS mixed_bruteforce="<<checked<<" backtracking_cases="<<backtracked
             <<" deleted="<<s.atlas15_deleted_<<" compactions="<<s.atlas16_compactions_<<"\n";
}
