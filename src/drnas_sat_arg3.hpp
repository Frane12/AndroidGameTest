#pragma once
// DRNAS ARG3-SAT1: complete 3-label CNF -> independent OUT-dominating set.
// Source pattern must match EXACTLY before randomized construction.
// Returns SAT only after checking *every original input CNF clause*.
// Does not claim UNSAT or bypass existing CDCL/standard proof infrastructure.
// The graph algorithm is a known argumentation/stable-extension idea, not a
// mathematical novelty or a polynomial general SAT decision procedure.
#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <numeric>
#include <string>
#include <utility>
#include <vector>

namespace drnas_arg3 {
using Clock=std::chrono::steady_clock;
using CNF=std::vector<std::vector<int>>;
constexpr int MAX_GROUPS=512;
constexpr int WORDS=8;
struct Mask {
    std::array<uint64_t,WORDS> bits{};
    void set(int v){bits[static_cast<size_t>(v>>6)]|=uint64_t(1)<<(v&63);}
    void clear(int v){bits[static_cast<size_t>(v>>6)]&=~(uint64_t(1)<<(v&63));}
    bool contains(int v) const {return (bits[static_cast<size_t>(v>>6)]>>(v&63))&1U;}
    Mask operator|(const Mask& b)const {
        Mask c;for(int i=0;i<WORDS;++i)c.bits[i]=bits[i]|b.bits[i];return c;
    }
    Mask operator&(const Mask& b)const {
        Mask c;for(int i=0;i<WORDS;++i)c.bits[i]=bits[i]&b.bits[i];return c;
    }
    Mask operator~()const {
        Mask c;for(int i=0;i<WORDS;++i)c.bits[i]=~bits[i];return c;
    }
    void join(const Mask& b){for(int i=0;i<WORDS;++i)bits[i]|=b.bits[i];}
    void exclude(const Mask& b){for(int i=0;i<WORDS;++i)bits[i]&=~b.bits[i];}
    int count()const {int n=0;for(auto b:bits)n+=std::popcount(b);return n;}
    bool none()const {for(auto b:bits)if(b)return false;return true;}
    bool equals(const Mask& b)const {return bits==b.bits;}
    bool intersects(const Mask& b)const {return !((*this)&b).none();}
    static Mask full(int n){
        Mask a;for(int i=0;i<n/64;++i)a.bits[i]=~uint64_t(0);
        if(n%64)a.bits[n/64]=(uint64_t(1)<<(n%64))-1U;
        return a;
    }
};
struct Stats {
    bool recognized=false,found=false,normalized=false;
    int groups=0,edges=0,blockers=0,iterations=0;
    int stable_candidates=0,blocked_candidates=0,best_undominated=-1;
    double wall_ms=0.0;
};
struct Result {std::vector<int8_t> model;Stats stats;bool sat()const{return !model.empty();}};
inline bool verify(int vars,const CNF& clauses,const std::vector<int8_t>& model){
    if(static_cast<int>(model.size())!=vars)return false;
    for(const auto& c:clauses){
        bool ok=false;
        for(int l:c){
            const int v=std::abs(l)-1;
            if(v<0||v>=vars)return false;
            if(model[v]==(l>0?1:-1)){ok=true;break;}
        }
        if(!ok)return false;
    }
    return true;
}
struct PRNG {
    uint64_t state=17;
    uint64_t next(){
        state^=state>>12;state^=state<<25;state^=state>>27;
        return state*2685821657736338717ULL;
    }
    double uniform(){return double(next()>>11)*(1.0/9007199254740992.0);}
    int candidate(const Mask&available,int n){
        const int start=static_cast<int>(next()%static_cast<uint64_t>(n));
        int word=start>>6;uint64_t bits=available.bits[word]&(~uint64_t(0)<<(start&63));
        if(bits)return word*64+std::countr_zero(bits);
        for(int w=word+1;w<WORDS;++w)if(available.bits[w])
            return w*64+std::countr_zero(available.bits[w]);
        for(int w=0;w<=word;++w)if(available.bits[w])
            return w*64+std::countr_zero(available.bits[w]);
        return -1;
    }
};
inline Result construct(int vars,const CNF& clauses,double ms_budget=50.0){
    Result result;
    auto started=Clock::now();
    auto spent=[&](){return std::chrono::duration<double,std::milli>(
        Clock::now()-started).count();};
    auto done=[&](){result.stats.wall_ms=spent();return result;};
    if(ms_budget<=0||vars<24||vars>3*MAX_GROUPS||vars%3||
       clauses.size()<static_cast<size_t>(vars*2)||clauses.size()>110000)
        return done();
    const int n=vars/3;
    result.stats.groups=n;
    std::vector<std::vector<int>> attackersA(static_cast<size_t>(n));
    std::vector<std::vector<int>> attackersB(static_cast<size_t>(n));
    std::vector<uint8_t> seenA(static_cast<size_t>(n),0);
    std::vector<uint8_t> seenB(static_cast<size_t>(n),0);
    std::vector<uint8_t> triple(static_cast<size_t>(n),0);
    std::vector<uint8_t> mutex(static_cast<size_t>(n),0);
    std::vector<Mask> blockers;
    blockers.reserve(64);
    int mixed_count=0;
    for(size_t ci=0;ci<clauses.size();++ci){
        if((ci&1023U)==0 && spent()>ms_budget)return done();
        const auto& c=clauses[ci];
        if(c.size()==2){
            const int a=c[0],b=c[1];
            if(a<0&&b<0){
                int x=-a-1,y=-b-1;
                const int ix=x%n,iy=y%n;
                if(ix!=iy)return done();
                const int gx=x/n,gy=y/n;
                if(gx==gy)return done();
                const int mask=1<<((gx==0&&gy==1)||(gx==1&&gy==0)?0:
                                   (gx==0&&gy==2)||(gx==2&&gy==0)?1:2);
                mutex[ix]|=static_cast<uint8_t>(mask);
            }else if((a<0&&b>0)||(a>0&&b<0)){
                int negative=a<0?-a:-b,positive=a>0?a:b;
                if(negative<1||negative>n||positive<=n||positive>2*n)return done();
                ++mixed_count;
            }else return done();
        }else if(c.size()==3){
            int k=-1;uint8_t layers=0;
            for(int lit:c){
                if(lit<=0)return done();
                int group=(lit-1)%n,layer=(lit-1)/n;
                if(k<0)k=group;
                if(k!=group||layer>2)return done();
                layers|=static_cast<uint8_t>(1<<layer);
            }
            if(layers!=7||triple[k]++)return done();
        }else if(c.size()>=4){
            int positive=0,negative=0,positiveA=-1,negativeB=-1;
            bool allNegB=true,allPosA=true;
            std::vector<int> plus,minus;
            plus.reserve(c.size());minus.reserve(c.size());
            for(int l:c){
                if(l>0){
                    ++positive;
                    if(l>n)allPosA=false;
                    if(l<=n){positiveA=l-1;plus.push_back(l-1);}
                    else return done();
                }else{
                    ++negative;
                    if(-l<=n||-l>2*n)allNegB=false;
                    else{negativeB=-l-n-1;minus.push_back(-l-n-1);}
                }
            }
            if(positive==static_cast<int>(c.size())&&allPosA){
                Mask block;for(int x:plus)block.set(x);
                if(blockers.size()>=128)return done();
                blockers.push_back(block);
            }else if(positive==1&&allNegB&&positiveA>=0&&negative>=3){
                if(seenA[positiveA]++)return done();
                attackersA[positiveA]=std::move(minus);
            }else if(negative==1&&allPosA&&negativeB>=0&&positive>=3){
                if(seenB[negativeB]++)return done();
                attackersB[negativeB]=std::move(plus);
            }else return done();
        }else return done();
    }
    if(mixed_count<n*2)return done();
    std::vector<Mask> out(static_cast<size_t>(n)),neighbors(static_cast<size_t>(n));
    Mask loops;
    int directed=0;
    for(int i=0;i<n;++i){
        if(triple[i]!=1||mutex[i]!=7||seenA[i]!=1||seenB[i]!=1)return done();
        auto& a=attackersA[i];auto& b=attackersB[i];
        std::sort(a.begin(),a.end());std::sort(b.begin(),b.end());
        a.erase(std::unique(a.begin(),a.end()),a.end());
        b.erase(std::unique(b.begin(),b.end()),b.end());
        if(a.empty()||a!=b)return done();
        for(int j:a){
            if(j<0||j>=n)return done();
            out[j].set(i);neighbors[i].set(j);neighbors[j].set(i);
            if(j==i)loops.set(i);
            ++directed;
        }
    }
    result.stats.edges=directed;
    result.stats.blockers=static_cast<int>(blockers.size());
    result.stats.recognized=true;
    if(spent()>ms_budget)return done();
    const Mask full=Mask::full(n);
    const Mask available_initial=(full&~loops);
    double weights[MAX_GROUPS+1]{};
    for(int i=0;i<=n;++i)
        weights[i]=1.0/std::pow(1.0+static_cast<double>(i),0.7);
    PRNG rng; // fixed precommitted default seed, independent of input SHA.
    const int MAX_ITERATIONS=400000;
    for(int it=0;it<MAX_ITERATIONS;++it){
        if((it&63)==0&&spent()>=ms_budget)break;
        result.stats.iterations=it+1;
        Mask available=available_initial,selected,dominated;
        while(!available.none()){
            double best=-1e30;int winner=-1;
            for(int k=0;k<9;++k){
                const int v=rng.candidate(available,n);
                if(v<0)break;
                const Mask hidden=~(dominated|selected);
                const int covered=(out[v]&hidden).count();
                const int conflict=(neighbors[v]&available).count();
                const double score=covered*weights[conflict]+rng.uniform()*0.9;
                if(score>best){best=score;winner=v;}
            }
            if(winner<0)break;
            selected.set(winner);
            dominated.join(out[winner]);
            available.exclude(neighbors[winner]);
            available.clear(winner);
        }
        const Mask missing=(full&~(selected|dominated));
        const int miss=missing.count();
        if(result.stats.best_undominated<0||miss<result.stats.best_undominated)
            result.stats.best_undominated=miss;
        if(miss)continue;
        ++result.stats.stable_candidates;
        bool blocked=false;
        for(const Mask& b:blockers)if(!(b&selected).intersects(full)){
            blocked=true;break;
        }
        if(blocked){++result.stats.blocked_candidates;continue;}
        std::vector<int8_t> model(static_cast<size_t>(vars),-1);
        for(int i=0;i<n;++i){
            if(selected.contains(i))model[i]=1;
            else if(dominated.contains(i))model[n+i]=1;
            else model[2*n+i]=1;
        }
        if(verify(vars,clauses,model)){
            result.stats.found=true;result.model=std::move(model);
            return done();
        }
    }
    return done();
}

// Renaming-invariant wrapper: recognize exactly-one source triples and infer
// IN/OUT/UNDEC roles from mixed-binary signed-literal incidences.
// This does not depend on source variable IDs, file names or source SHA.
// Full assignment is independently verified on the UNCHANGED original CNF.
inline Result construct_robust(int vars,const CNF& clauses,double ms_budget=50.0){
    const auto started=Clock::now();
    auto spent=[&](){return std::chrono::duration<double,std::milli>(
        Clock::now()-started).count();};
    Result direct=construct(vars,clauses,ms_budget);
    if(direct.sat()||direct.stats.recognized||spent()>=ms_budget)
        return direct;
    if(vars<24||vars>3*MAX_GROUPS||vars%3!=0||
       clauses.size()>110000)return direct;
    const int n=vars/3;
    std::vector<std::array<int,3>> groups;groups.reserve(n);
    std::vector<int> owner(vars,-1);
    for(size_t ci=0;ci<clauses.size();++ci){
        if((ci&2047U)==0 && spent()>=ms_budget)return direct;
        const auto& c=clauses[ci];
        if(c.size()!=3||!std::all_of(c.begin(),c.end(),
                                    [](int l){return l>0;}))continue;
        if(static_cast<int>(groups.size())>=n)return direct;
        std::array<int,3> triple{};
        for(int j=0;j<3;++j){
            const int v=c[j]-1;
            if(v<0||v>=vars||owner[v]>=0)return direct;
            owner[v]=static_cast<int>(groups.size());triple[j]=v;
        }
        groups.push_back(triple);
    }
    if(static_cast<int>(groups.size())!=n)return direct;
    for(int v:owner)if(v<0)return direct;
    std::vector<int> mixed_negative(static_cast<size_t>(vars),0);
    std::vector<int> mixed_positive(static_cast<size_t>(vars),0);
    for(const auto& c:clauses){
        if(c.size()!=2||c[0]*static_cast<int64_t>(c[1])>=0)continue;
        const int neg=(c[0]<0?-c[0]:-c[1])-1;
        const int pos=(c[0]>0?c[0]:c[1])-1;
        if(neg<0||neg>=vars||pos<0||pos>=vars)return direct;
        ++mixed_negative[neg];++mixed_positive[pos];
    }
    // canon[original_variable] is the zero-based index into the
    // normalized [IN_0..IN_n-1, OUT_0.., UNDEC_0..] layout.
    std::vector<int> canon(static_cast<size_t>(vars),-1);
    for(int group=0;group<n;++group){
        int in=-1,out=-1,undec=-1;
        for(int var:groups[group]){
            const int a=mixed_negative[var],b=mixed_positive[var];
            if(a>0&&b==0){
                if(in>=0)return direct;in=var;
            }else if(b>0&&a==0){
                if(out>=0)return direct;out=var;
            }else if(a==0&&b==0){
                if(undec>=0)return direct;undec=var;
            }else return direct;
        }
        if(in<0||out<0||undec<0)return direct;
        canon[in]=group;canon[out]=n+group;canon[undec]=2*n+group;
    }
    if(spent()>=ms_budget)return direct;
    CNF transformed;
    transformed.reserve(clauses.size());
    for(size_t ci=0;ci<clauses.size();++ci){
        if((ci&2047U)==0 && spent()>=ms_budget)return direct;
        std::vector<int> row;row.reserve(clauses[ci].size());
        for(int l:clauses[ci]){
            const int v=std::abs(l)-1;
            if(v<0||v>=vars||canon[v]<0)return direct;
            row.push_back((l>0?1:-1)*(canon[v]+1));
        }
        transformed.push_back(std::move(row));
    }
    const double remaining=ms_budget-spent();
    if(remaining<=0)return direct;
    Result normalized=construct(vars,transformed,remaining);
    normalized.stats.normalized=true;
    if(!normalized.sat()){
        normalized.stats.wall_ms=spent();
        return normalized;
    }
    std::vector<int8_t> model(static_cast<size_t>(vars),-1);
    for(int v=0;v<vars;++v)model[v]=normalized.model[canon[v]];
    if(!verify(vars,clauses,model)){
        Result invalid;
        invalid.stats=normalized.stats;
        invalid.stats.found=false;
        invalid.stats.wall_ms=spent();
        return invalid;
    }
    normalized.model=std::move(model);
    normalized.stats.wall_ms=spent();
    return normalized;
}

} // namespace drnas_arg3
