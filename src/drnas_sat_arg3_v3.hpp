#pragma once
// ARG3-V3: sound *SAT witness only* construction on partially preprocessed
// three-label argumentation encodings. Size and time bounded, in one process.
// Never claims UNSAT. Every proposed complete assignment is checked against
// ALL unchanged ORIGINAL DIMACS clauses. No filename/source SHA/answer oracle.
#include "drnas_sat_arg3.hpp"
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cmath>
#include <vector>

namespace drnas_arg3_v3 {
using drnas_arg3::CNF;
using drnas_arg3::Clock;
using drnas_arg3::Mask;
using drnas_arg3::PRNG;
using drnas_arg3::Result;
using drnas_arg3::MAX_GROUPS;

// Original CNF root units, optionally followed by bounded sound UCP.
// No root contradictory state can result in an UNSAT answer: just abstain.
inline bool root_propagate(int vars,const CNF& f,std::vector<int8_t>&root,
                          int& source_units,int& implied,
                          Clock::time_point deadline) {
    root.assign(static_cast<size_t>(vars),0);
    source_units=0;implied=0;
    for(const auto& c:f)if(c.size()==1) {
        int x=c[0], v=std::abs(x)-1;
        if(v<0||v>=vars)return false;
        int8_t value=x>0?1:-1;
        if(root[v]&&root[v]!=value)return false;
        if(!root[v]){root[v]=value;++source_units;}
    }
    // A small fixed number of full-clause scans; every inferred literal is
    // forced by the ORIGINAL CNF, never by graph assumptions.
    for(int round=0;round<3;++round) {
        bool changed=false;
        for(size_t ci=0;ci<f.size();++ci) {
            if((ci&511U)==0 && Clock::now()>=deadline)return true;
            const auto& clause=f[ci];
            bool satisfied=false;
            int unassigned=0,last=0;
            for(int lit:clause) {
                int v=std::abs(lit)-1;
                int8_t val=root[v];
                if(val==(lit>0?1:-1)){satisfied=true;break;}
                if(!val){++unassigned;last=lit;}
            }
            if(satisfied)continue;
            if(unassigned==0)return false; // abstain; no UNSAT conclusion
            if(unassigned==1) {
                int v=std::abs(last)-1;
                int8_t val=last>0?1:-1;
                if(root[v]&&root[v]!=val)return false;
                if(!root[v]) {root[v]=val;++implied;changed=true;}
            }
        }
        if(!changed)break;
    }
    return true;
}

// One generator family uses three contiguous [IN, OUT, UNDEC] layers.
// A very small number of one-hot triples may be missing because original
// root unit clauses already force a corresponding IN/OUT/UNDEC assignment.
// That omission is not used as an entailment: it only authorizes an
// attempted full SAT model that must pass the unmodified source checker.
inline Result construct_partial(int vars,const CNF& f,double budget_ms) {
    Result result;
    const auto begin=Clock::now();
    auto spent=[&](){return std::chrono::duration<double,std::milli>(
        Clock::now()-begin).count();};
    auto done=[&](){result.stats.wall_ms=spent();return result;};
    if(budget_ms<=0.0 || vars<24 || vars%3 ||
       vars>3*MAX_GROUPS || f.size()>110000 ||
       f.size()<static_cast<size_t>(vars*2))return done();
    const int n=vars/3;
    result.stats.groups=n;
    const auto deadline=begin+std::chrono::duration_cast<Clock::duration>(
        std::chrono::duration<double,std::milli>(budget_ms));
    auto expired=[&](){return Clock::now()>=deadline;};

    std::vector<int8_t> root;
    int units=0,implied=0;
    // Reserve only a small portion for propagation. Partial implication
    // closure is safe because it is never mistaken for a complete model.
    const auto root_deadline=begin+std::chrono::duration_cast<Clock::duration>(
        std::chrono::duration<double,std::milli>(
            std::min(15.0,budget_ms*0.30)));
    if(!root_propagate(vars,f,root,units,implied,root_deadline))return done();
    result.stats.root_units=units;
    result.stats.root_implied=implied;
    if(expired())return done();

    std::vector<uint8_t> triple(n,0),mutex(n,0);
    std::vector<Mask> out(static_cast<size_t>(n)),neighbors(static_cast<size_t>(n));
    std::vector<Mask> blockers;
    blockers.reserve(64);
    Mask loops;
    int mixed_edges=0;
    for(size_t ci=0;ci<f.size();++ci) {
        if((ci&1023U)==0 && expired())return done();
        const auto& c=f[ci];
        if(c.size()==3 && c[0]>0&&c[1]>0&&c[2]>0) {
            int g=(c[0]-1)%n;
            uint8_t mask=0;
            bool allsame=true;
            for(int l:c) {
                if((l-1)%n!=g){allsame=false;break;}
                mask|=uint8_t(1<<((l-1)/n));
            }
            if(allsame&&mask==7) {
                if(++triple[g]>1)return done();
            }
        }
        if(c.size()==2) {
            int a=c[0],b=c[1];
            if(a<0&&b<0) {
                int x=-a-1,y=-b-1;
                if(x%n==y%n && x/n!=y/n) {
                    int first=x/n,second=y/n;
                    int bit=(first==0&&second==1)||(first==1&&second==0)?0:
                            (first==0&&second==2)||(first==2&&second==0)?1:2;
                    mutex[x%n]|=uint8_t(1<<bit);
                }
            } else if((a<0)!=(b<0)) {
                int negative=(a<0?-a:-b),positive=(a>0?a:b);
                if(negative>=1&&negative<=n &&
                   positive>n&&positive<=2*n) {
                    int from=negative-1,to=positive-n-1;
                    out[from].set(to);
                    neighbors[from].set(to);
                    neighbors[to].set(from);
                    if(from==to)loops.set(from);
                    ++mixed_edges;
                }
            }
        }
        if(c.size()>=4 && blockers.size()<64) {
            bool positive_in=true;
            Mask block;
            for(int lit:c) {
                if(lit<1 || lit>n){positive_in=false;break;}
                block.set(lit-1);
            }
            if(positive_in)blockers.push_back(block);
        }
    }
    if(expired())return done();
    if(mixed_edges < n*3)return done();
    const int total_triples=std::count(triple.begin(),triple.end(),uint8_t(1));
    // Require at least 95% exact source one-hot triples. Other encodings
    // deliberately fall through to CDCL rather than being guessed about.
    if(total_triples < n-n/20)return done();
    int repaired=0;
    std::vector<int8_t> source_unit(vars,0);
    for(const auto& c:f)if(c.size()==1) {
        const int v=std::abs(c[0])-1;
        source_unit[v]=c[0]>0?1:-1;
    }
    for(int i=0;i<n;++i) {
        if(triple[i]==1) {
            if(mutex[i]!=7)return done();
        } else {
            // Only patch one-hot structures where ORIGINAL clauses already
            // explicitly fix IN_i=true, OUT_i=false, UNDEC_i=false.
            if(triple[i]!=0 || mutex[i]!=0 ||
               source_unit[i]!=1 ||
               source_unit[n+i]!=-1 ||
               source_unit[2*n+i]!=-1)return done();
            ++repaired;
        }
    }
    result.stats.repaired_groups=repaired;
    result.stats.recognized=true;
    result.stats.edges=mixed_edges;
    result.stats.blockers=static_cast<int>(blockers.size());
    if(expired())return done();

    Mask full=Mask::full(n),forced,banned;
    for(int i=0;i<n;++i) {
        if(root[i]==1 || root[n+i]==-1)forced.set(i);
        if(root[i]==-1 || root[n+i]==1 || root[2*n+i]==1)
            banned.set(i);
    }
    if(forced.intersects(banned))return done();
    for(int i=0;i<n;++i)if(forced.contains(i) &&
        neighbors[i].intersects(forced))return done();

    Mask available_start=full&~(loops|banned);
    Mask dominated_start;
    for(int i=0;i<n;++i)if(forced.contains(i)) {
        dominated_start.join(out[i]);
        available_start.exclude(neighbors[i]);
        available_start.clear(i);
    }

    // A planted-like forced root often already covers all outside groups.
    // It is safe to check a complete candidate before randomized search.
    auto verify_candidate=[&](const Mask& chosen,const Mask& dominated)->bool {
        if(!(full&~(chosen|dominated)).none())return false;
        ++result.stats.stable_candidates;
        for(const Mask& block:blockers)
            if(!block.intersects(chosen)){
                ++result.stats.blocked_candidates;
                return false;
            }
        std::vector<int8_t> model(static_cast<size_t>(vars),-1);
        for(int i=0;i<n;++i) {
            if(chosen.contains(i))model[i]=1;
            else if(dominated.contains(i))model[n+i]=1;
            else model[2*n+i]=1;
        }
        if(drnas_arg3::verify(vars,f,model)){
            result.stats.found=true;
            result.model=std::move(model);
            return true;
        }
        ++result.stats.invalid_candidates;
        return false;
    };
    if(verify_candidate(forced,dominated_start))return done();

    PRNG rng;
    std::vector<double> weights(n+1,1.0);
    for(int i=0;i<=n;++i)weights[i]=1.0/
        std::pow(1.0+static_cast<double>(i),0.7);
    for(int iter=0;iter<250000;++iter) {
        if((iter&31)==0 && expired())break;
        result.stats.iterations=iter+1;
        Mask available=available_start,selected=forced,dominated=dominated_start;
        while(!available.none()) {
            double best=-1e20;
            int winner=-1;
            for(int k=0;k<11;++k) {
                int v=rng.candidate(available,n);
                if(v<0)break;
                Mask uncovered=full&~(selected|dominated);
                int coverage=(out[v]&uncovered).count();
                int choices=(neighbors[v]&available).count();
                double score=coverage*weights[choices]+rng.uniform();
                if(score>best){best=score;winner=v;}
            }
            if(winner<0)break;
            selected.set(winner);
            dominated.join(out[winner]);
            available.exclude(neighbors[winner]);
            available.clear(winner);
        }
        const int missing=(full&~(selected|dominated)).count();
        if(result.stats.best_undominated<0 ||
           missing<result.stats.best_undominated)
            result.stats.best_undominated=missing;
        if(!missing&&verify_candidate(selected,dominated))return done();
    }
    return done();
}
} // namespace drnas_arg3_v3
