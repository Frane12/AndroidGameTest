#pragma once
// ARG3-V4: bounded three-state clause-guided local repair.
// Every returned SAT model is verified on ALL original CNF clauses.
// Never proves UNSAT or alters the fallback native CDCL's learned clauses.
// Uses source-backed one-hot triples, source units, sound root BCP and
// direct local minimization of violated ORIGINAL CNF clauses.
#include "drnas_sat_arg3_v3.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <string>
#include <vector>

namespace drnas_arg3_v4 {
using CNF=drnas_arg3::CNF;
using Clock=drnas_arg3::Clock;
using PRNG=drnas_arg3::PRNG;
constexpr int MAX_GROUPS=drnas_arg3::MAX_GROUPS;
struct Stats {
    bool eligible=false,recognized=false,found=false;
    int groups=0,original_units=0,root_implied=0;
    int exact_triples=0,repaired_triples=0;
    int forced_groups=0,initial_unsat=-1,best_unsat=-1;
    int best_undec=0,restarts=0,moves=0,wrong_candidates=0;
    int original_clauses=0,total_literals=0;
    double wall_ms=0.0;
};
struct Outcome {
    std::vector<int8_t> model;
    Stats stats;
    bool sat()const{return !model.empty();}
};
struct Occ {
    int ci;
    uint8_t layer;
    bool positive;
};
inline Outcome construct(int vars,const CNF& f,double budget_ms=100.0) {
    Outcome out;
    const auto began=Clock::now();
    const auto elapsed=[&](){
        return std::chrono::duration<double,std::milli>(
            Clock::now()-began).count();
    };
    const auto finish=[&](){
        out.stats.wall_ms=elapsed();
        return out;
    };
    if(!std::isfinite(budget_ms)||budget_ms<=0||vars<24||vars%3||
       vars>3*MAX_GROUPS||f.empty()||f.size()>110000)
        return finish();
    const int n=vars/3;
    const auto deadline=began+std::chrono::duration_cast<Clock::duration>(
        std::chrono::duration<double,std::milli>(budget_ms));
    const auto expired=[&](){return Clock::now()>=deadline;};
    out.stats.groups=n;
    out.stats.original_clauses=static_cast<int>(f.size());
    out.stats.eligible=true;
    int64_t literal_count=0;
    for(const auto& c:f){
        literal_count+=static_cast<int64_t>(c.size());
        if(literal_count>1300000||c.empty())return finish();
        for(int lit:c)
            if(!lit||(int64_t)std::abs((int64_t)lit)>vars)return finish();
    }
    out.stats.total_literals=static_cast<int>(literal_count);
    if(expired())return finish();

    std::vector<int8_t> root;
    const auto bcp_limit=began+std::chrono::duration_cast<Clock::duration>(
        std::chrono::duration<double,std::milli>(
            std::min(12.0,budget_ms*0.18)));
    if(!drnas_arg3_v3::root_propagate(vars,f,root,
        out.stats.original_units,out.stats.root_implied,bcp_limit))
        return finish();
    if(expired())return finish();

    std::vector<uint8_t> triples(n,0),mutex(n,0);
    std::vector<int8_t> explicit_unit(vars,0);
    for(size_t ci=0;ci<f.size();++ci){
        if((ci&2047U)==0&&expired())return finish();
        const auto& c=f[ci];
        if(c.size()==1){
            const int v=std::abs(c[0])-1;
            const int8_t val=c[0]>0?1:-1;
            if(explicit_unit[v]&&explicit_unit[v]!=val)return finish();
            explicit_unit[v]=val;
        }else if(c.size()==3){
            if(c[0]>0&&c[1]>0&&c[2]>0){
                const int g=(c[0]-1)%n;
                uint8_t mask=0;bool same=true;
                for(int l:c){
                    if((l-1)%n!=g){same=false;break;}
                    int layer=(l-1)/n;
                    if(layer>2){same=false;break;}
                    mask|=static_cast<uint8_t>(1<<layer);
                }
                if(same&&mask==7&&++triples[g]>1)return finish();
            }
        }else if(c.size()==2&&c[0]<0&&c[1]<0){
            const int a=-c[0]-1,b=-c[1]-1;
            if(a%n==b%n&&a/n!=b/n){
                int x=a/n,y=b/n;
                int bit=(x==0&&y==1)||(x==1&&y==0)?0:
                        (x==0&&y==2)||(x==2&&y==0)?1:2;
                mutex[a%n]|=static_cast<uint8_t>(1<<bit);
            }
        }
    }
    out.stats.exact_triples=
        static_cast<int>(std::count(triples.begin(),triples.end(),uint8_t(1)));
    if(out.stats.exact_triples<n-n/20)return finish();
    std::vector<uint8_t> allowed(n,0);
    for(int g=0;g<n;++g){
        if(triples[g]==1){
            if(mutex[g]!=7)return finish();
        }else{
            // A missing group must be explicitly fixed in the ORIGINAL
            // source by exactly one positive and two negative unit clauses.
            int chosen=-1;
            for(int layer=0;layer<3;++layer) {
                if(explicit_unit[layer*n+g]==1){
                    if(chosen>=0)return finish();
                    chosen=layer;
                }
            }
            if(chosen<0||mutex[g]!=0)return finish();
            for(int layer=0;layer<3;++layer)
                if(explicit_unit[layer*n+g]!=(layer==chosen?1:-1))
                    return finish();
            ++out.stats.repaired_triples;
        }
        int forced=-1;
        uint8_t mask=0;
        for(int layer=0;layer<3;++layer){
            const int8_t fixed=root[layer*n+g];
            if(fixed>0){
                if(forced>=0)return finish();
                forced=layer;
            }else if(!fixed){
                mask|=static_cast<uint8_t>(1<<layer);
            }
        }
        if(forced>=0){
            if(root[forced*n+g]<0)return finish();
            mask=static_cast<uint8_t>(1<<forced);
        }
        if(!mask)return finish();
        allowed[g]=mask;
        if((mask&(mask-1))==0)++out.stats.forced_groups;
    }
    out.stats.recognized=true;
    if(expired())return finish();

    std::vector<std::vector<Occ>> occ(static_cast<size_t>(n));
    for(size_t ci=0;ci<f.size();++ci){
        if((ci&2047U)==0&&expired())return finish();
        for(int lit:f[ci]) {
            const int v=std::abs(lit)-1;
            occ[v%n].push_back(Occ{static_cast<int>(ci),
                                  static_cast<uint8_t>(v/n),lit>0});
        }
    }
    if(expired())return finish();
    const int m=static_cast<int>(f.size());
    std::vector<uint8_t> state(n,2);
    std::vector<int> sat(m,0);
    std::vector<int> bad,location(m,-1),weights(m,1);
    bad.reserve(f.size());
    std::vector<int> touched,delta(m,0);
    std::vector<int> stamps(m,0);
    int epoch=0;
    PRNG rng;
    auto choose=[&](int mask,int preferred)->int{
        if(mask&(1<<preferred))return preferred;
        int options[3],sz=0;
        for(int x=0;x<3;++x)if(mask&(1<<x))options[sz++]=x;
        return options[static_cast<int>(rng.next()%static_cast<uint64_t>(sz))];
    };
    auto putbad=[&](int ci){
        if(location[ci]>=0)return;
        location[ci]=static_cast<int>(bad.size());bad.push_back(ci);
    };
    auto delbad=[&](int ci){
        int pos=location[ci];
        if(pos<0)return;
        int tail=bad.back();
        bad[pos]=tail;location[tail]=pos;
        bad.pop_back();location[ci]=-1;
    };
    auto full_recompute=[&](){
        bad.clear();std::fill(location.begin(),location.end(),-1);
        for(int ci=0;ci<m;++ci) {
            int good=0;
            for(int lit:f[ci]){
                int v=std::abs(lit)-1;
                const bool value=state[v%n]==v/n;
                if((lit>0)==value)++good;
            }
            sat[ci]=good;
            if(!good)putbad(ci);
        }
    };
    auto candidate=[&](int g,int next)->const std::vector<int>&{
        ++epoch;
        if(epoch==std::numeric_limits<int>::max()){
            std::fill(stamps.begin(),stamps.end(),0);epoch=1;
        }
        touched.clear();
        const int old=state[g];
        for(const Occ& x:occ[g]){
            const int ci=x.ci;
            if(stamps[ci]!=epoch){
                stamps[ci]=epoch;delta[ci]=0;
                touched.push_back(ci);
            }
            const int was=(x.positive==(old==x.layer));
            const int now=(x.positive==(next==x.layer));
            delta[ci]+=now-was;
        }
        return touched;
    };
    auto score_move=[&] (int g,int next)->int64_t{
        if(next==state[g])return std::numeric_limits<int64_t>::min()/4;
        const auto& changed=candidate(g,next);
        int64_t gain=0;
        for(int ci:changed){
            const int before=sat[ci],after=before+delta[ci];
            if(before==0&&after>0)gain+=weights[ci];
            if(before>0&&after==0)gain-=weights[ci];
        }
        return gain;
    };
    auto apply=[&](int g,int next){
        const auto& changed=candidate(g,next);
        for(int ci:changed){
            int before=sat[ci];
            sat[ci]+=delta[ci];
            if(before==0&&sat[ci]>0)delbad(ci);
            else if(before>0&&sat[ci]==0)putbad(ci);
        }
        state[g]=static_cast<uint8_t>(next);
    };
    auto verify_assignment=[&]()->bool{
        std::vector<int8_t> model(static_cast<size_t>(vars),-1);
        int undec=0;
        for(int g=0;g<n;++g){
            model[state[g]*n+g]=1;
            if(state[g]==2)++undec;
        }
        if(drnas_arg3::verify(vars,f,model)){
            out.model=std::move(model);
            out.stats.found=true;out.stats.best_undec=undec;
            return true;
        }
        ++out.stats.wrong_candidates;
        return false;
    };
    int best=m+1;
    const int MAX_MOVES=350000;
    const int MOVES_PER_RESTART=3500;
    for(int restart=0;restart<800;++restart){
        if(expired()||out.stats.moves>=MAX_MOVES)break;
        ++out.stats.restarts;
        for(int g=0;g<n;++g) {
            int preferred=restart==0?2:restart==1?0:
                           static_cast<int>(rng.next()%3ULL);
            state[g]=static_cast<uint8_t>(choose(allowed[g],preferred));
        }
        full_recompute();
        if(out.stats.initial_unsat<0)out.stats.initial_unsat=static_cast<int>(bad.size());
        if(static_cast<int>(bad.size())<best){
            best=static_cast<int>(bad.size());
            out.stats.best_unsat=best;
        }
        if(bad.empty()&&verify_assignment())return finish();
        for(int iteration=0;iteration<MOVES_PER_RESTART &&
            out.stats.moves<MAX_MOVES;++iteration){
            if((out.stats.moves&63)==0&&expired())return finish();
            ++out.stats.moves;
            if(bad.empty()) {
                if(verify_assignment())return finish();
                break;
            }
            const int ci=bad[static_cast<size_t>(
                rng.next()%static_cast<uint64_t>(bad.size()))];
            const auto& clause=f[ci];
            if(clause.empty())return finish();
            int best_group=-1,best_next=-1;
            int64_t best_score=std::numeric_limits<int64_t>::min();
            const int tries=std::min<int>(24,static_cast<int>(clause.size()));
            const int offset=static_cast<int>(rng.next()%clause.size());
            for(int k=0;k<tries;++k){
                const int lit=clause[static_cast<size_t>(
                    (offset+k)%clause.size())];
                int v=std::abs(lit)-1,g=v%n;
                if((allowed[g]&(allowed[g]-1))==0)continue;
                // A move should ideally make the chosen source literal true.
                for(int next=0;next<3;++next){
                    if(!(allowed[g]&(1<<next))||next==state[g])continue;
                    const bool literal_true=(lit>0)==(next==v/n);
                    if(!literal_true)continue;
                    int64_t gain=score_move(g,next);
                    // Add only tiny randomized tie-breaker, no status oracle.
                    if(gain>best_score||(gain==best_score && (rng.next()&1))){
                        best_score=gain;best_group=g;best_next=next;
                    }
                }
            }
            if(best_group<0)break; // root-fixed source clause: no valid move
            apply(best_group,best_next);
            if(static_cast<int>(bad.size())<best){
                best=static_cast<int>(bad.size());
                out.stats.best_unsat=best;
            }
            if(bad.empty()&&verify_assignment())return finish();
            // Breakout: increase weight only of currently violated source
            // clauses. This NEVER changes truth/validity of the original CNF.
            if(iteration%127==126){
                int samples=std::min<int>(16,static_cast<int>(bad.size()));
                for(int a=0;a<samples;++a){
                    int index=bad[static_cast<size_t>(
                        rng.next()%static_cast<uint64_t>(bad.size()))];
                    if(weights[index]<64)++weights[index];
                }
            }
        }
    }
    return finish();
}
} // namespace drnas_arg3_v4
