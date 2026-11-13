#pragma once
// Bounded exact local Walsh / affine reasoning. No generator metadata is read.
#include <array>
#include <functional>
#include <map>
#include <set>
#include <numeric>

namespace drnas_coop1 {
using Tick=std::chrono::steady_clock;
struct Block { std::vector<int> vars; std::vector<std::vector<int>> cnf; int last_state=-1; };
struct Analysis {
    std::vector<int> feasible,walsh;
    int rank=0,defect=0;
};
inline int affine_rank(const std::vector<int>& points) {
    if(points.empty())return 0;
    std::array<unsigned,8> basis{};int rank=0;
    for(int p:points){unsigned x=static_cast<unsigned>(p^points[0]);
        for(int j=7;j>=0;--j)if(x&(1u<<j)){
            if(basis[j])x^=basis[j];else{basis[j]=x;++rank;break;}
        }
    }return rank;
}
inline Analysis analyze(const Block& b,const std::vector<int8_t>& values) {
    const int k=static_cast<int>(b.vars.size()),N=1<<k;
    Analysis a;a.walsh.assign(static_cast<size_t>(N),0);
    for(int x=0;x<N;++x){bool ok=true;
        for(int j=0;j<k;++j){int v=values[b.vars[j]-1];if(v && (((x>>j)&1)!=(v>0))){ok=false;break;}}
        if(!ok)continue;
        for(const auto& c:b.cnf){bool sat=false;
            for(int l:c){int j=static_cast<int>(std::lower_bound(b.vars.begin(),b.vars.end(),std::abs(l))-b.vars.begin());
                if((((x>>j)&1)!=0)==(l>0)){sat=true;break;}}
            if(!sat){ok=false;break;}
        }
        if(ok){a.feasible.push_back(x);a.walsh[x]=1;}
    }
    a.rank=affine_rank(a.feasible);
    a.defect=a.feasible.empty()?0:((1<<a.rank)-static_cast<int>(a.feasible.size()));
    for(int len=1;len<N;len*=2)for(int off=0;off<N;off+=2*len)for(int j=0;j<len;++j){
        int u=a.walsh[off+j],v=a.walsh[off+j+len];a.walsh[off+j]=u+v;a.walsh[off+j+len]=u-v;
    }return a;
}
inline std::vector<int> canonical(std::vector<int> c){std::sort(c.begin(),c.end());return c;}
struct Output {std::vector<std::vector<int>> clauses;int hint=-1;};
class Engine {
 public:
    std::string mode="off";
    std::vector<std::vector<int>> originals;
    std::vector<Block> blocks;
    std::set<std::vector<int>> known;
    int passes=0,windows=0,affine_windows=0,nonaffine_windows=0,conditioned=0;
    int forced_parities=0,lemmas=0,proof_steps=0,hints=0,applied_hints=0,propagations=0,conflicts=0;
    int64_t last_dec=-1,last_conf=-1;
    int64_t activated_at_conflicts=-1;
    double ms=0;bool disabled=false;
    bool enabled()const{return mode!="off"&&!disabled;}
    void add(const std::vector<int>& c){
        if(!enabled())return;
        if(originals.size()>=12000){disabled=true;originals.clear();return;}
        originals.push_back(c);
    }
    void initialize(int n){
        if(!enabled())return;
        auto start=Tick::now();
        if(n>4096){disabled=true;originals.clear();return;}
        std::map<std::vector<int>,int> counts;
        for(const auto& c:originals){known.insert(canonical(c));
            if(c.size()<2||c.size()>8)continue;
            std::vector<int> v;for(int l:c)v.push_back(std::abs(l));
            std::sort(v.begin(),v.end());++counts[v];
        }
        std::vector<std::pair<std::vector<int>,int>> seeds(counts.begin(),counts.end());
        std::stable_sort(seeds.begin(),seeds.end(),[](const auto&a,const auto&b){
            if(a.second!=b.second)return a.second>b.second;
            return a.first<b.first;});
        if(seeds.size()>96)seeds.resize(96);
        std::set<std::vector<int>> used;std::vector<std::vector<int>> scopes;
        // Include unions first: a single XOR's CNF already provides unit propagation.
        for(size_t i=0;i<seeds.size()&&scopes.size()<40;++i){
            for(size_t j=i+1;j<seeds.size()&&scopes.size()<40;++j){
                std::vector<int> both,common;
                std::set_intersection(seeds[i].first.begin(),seeds[i].first.end(),seeds[j].first.begin(),seeds[j].first.end(),std::back_inserter(common));
                if(common.empty())continue;
                std::set_union(seeds[i].first.begin(),seeds[i].first.end(),seeds[j].first.begin(),seeds[j].first.end(),std::back_inserter(both));
                if(both.size()<=8&&used.insert(both).second)scopes.push_back(both);
            }
        }
        for(const auto& s:seeds)if(scopes.size()<64&&used.insert(s.first).second)scopes.push_back(s.first);
        for(const auto& v:scopes){
            if(std::chrono::duration<double,std::milli>(Tick::now()-start).count()>10)break;
            Block b;b.vars=v;
            for(const auto& c:originals){bool inside=true;
                for(int l:c)if(!std::binary_search(v.begin(),v.end(),std::abs(l))){inside=false;break;}
                if(inside)b.cnf.push_back(c);
                if(b.cnf.size()>=256)break;
            }
            if(b.cnf.size()>=2)blocks.push_back(std::move(b));
        }
        ms+=std::chrono::duration<double,std::milli>(Tick::now()-start).count();
    }
    // Construct a RUP derivation of target by a bounded resolution tree.
    // Every leaf weakens an original clause; each parent resolves its children.
    // Intermediate steps live in the proof, only the final lemma enters CDCL.
    bool certify(const Block& b,const std::vector<int>& target,
                 const std::function<void(const std::vector<int>&)>& emit,Tick::time_point deadline){
        unsigned mask=0,bits=0;
        for(int l:target){int j=static_cast<int>(std::lower_bound(b.vars.begin(),b.vars.end(),std::abs(l))-b.vars.begin());
            mask|=1u<<j;if(l<0)bits|=1u<<j;}
        unsigned all=(1u<<b.vars.size())-1;
        std::function<bool(unsigned,unsigned,bool)> visit=[&](unsigned assigned,unsigned x,bool root){
            if(proof_steps>=8192||Tick::now()>=deadline)return false;
            bool blocked=false;
            for(const auto& c:b.cnf){bool falsified=true;
                for(int l:c){int j=static_cast<int>(std::lower_bound(b.vars.begin(),b.vars.end(),std::abs(l))-b.vars.begin());
                    if(!(assigned&(1u<<j))||(((x>>j)&1u)==static_cast<unsigned>(l>0))){falsified=false;break;}}
                if(falsified){blocked=true;break;}
            }
            if(!blocked){
                if(assigned==all)throw std::runtime_error("COOP1 attempted non-entailed lemma");
                unsigned bit=1u<<std::countr_zero(all^assigned);
                if(!visit(assigned|bit,x&~bit,false)||!visit(assigned|bit,x|bit,false))return false;
            }
            if(!root){std::vector<int> clause;
                for(size_t j=0;j<b.vars.size();++j)if(assigned&(1u<<j))clause.push_back((x&(1u<<j))?-b.vars[j]:b.vars[j]);
                emit(clause);++proof_steps;
            }return true;
        };
        return visit(mask,bits,true);
    }
    Output step(const std::vector<int8_t>& values,int64_t decisions,int64_t cdcl_conflicts,
                const std::function<void(const std::vector<int>&)>& emit){
        Output out;
        if(!enabled()||blocks.empty()||passes>=24||ms>=30||lemmas>=256)return out;
        if(last_dec>=0&&!(decisions<8&&decisions!=last_dec)&&decisions-last_dec<16&&cdcl_conflicts-last_conf<16)return out;
        auto start=Tick::now();auto deadline=start+std::chrono::microseconds(2500);
        last_dec=decisions;last_conf=cdcl_conflicts;++passes;
        double best=0;
        for(auto& b:blocks){
            if(Tick::now()>=deadline||out.clauses.size()>=8)break;
            int state=0;std::vector<int> guard;unsigned free_mask=0;
            for(size_t j=0;j<b.vars.size();++j){int v=values[b.vars[j]-1];state=state*3+(v+1);
                if(v)guard.push_back(v>0?-b.vars[j]:b.vars[j]);else free_mask|=1u<<j;}
            if(state==b.last_state)continue;
            b.last_state=state;
            ++windows;if(!guard.empty())++conditioned;
            Analysis a=analyze(b,values);
            if(a.defect==0)++affine_windows;else ++nonaffine_windows;
            auto propose=[&](std::vector<int> clause){
                auto key=canonical(clause);if(known.count(key)||out.clauses.size()>=8)return;
                if(mode=="observe")return;
                if(!certify(b,clause,emit,deadline))return;
                known.insert(key);out.clauses.push_back(std::move(clause));++lemmas;
            };
            if(a.feasible.empty()){propose(guard);continue;}
            const int count=static_cast<int>(a.feasible.size());
            for(unsigned m=free_mask;m;m=(m-1)&free_mask){
                if(std::abs(a.walsh[m])!=count)continue;
                ++forced_parities;
                if(std::popcount(m)>2)continue;
                const unsigned rhs=a.walsh[m]<0?1u:0u;
                // Short saturated Walsh modes are exact affine consequences.
                for(unsigned x=m;;x=(x-1)&m){
                    if((static_cast<unsigned>(std::popcount(x))&1u)!=rhs){
                        auto c=guard;for(size_t j=0;j<b.vars.size();++j)if(m&(1u<<j))c.push_back((x&(1u<<j))?-b.vars[j]:b.vars[j]);
                        propose(std::move(c));
                    }
                    if(x==0)break;
                }
            }
            if(a.defect>0){
                for(size_t j=0;j<b.vars.size();++j)if(free_mask&(1u<<j)){
                    std::vector<int> lo,hi;for(int x:a.feasible)((x&(1u<<j))?hi:lo).push_back(x);
                    if(lo.empty()||hi.empty())continue;
                    int d0=(1<<affine_rank(lo))-static_cast<int>(lo.size());
                    int d1=(1<<affine_rank(hi))-static_cast<int>(hi.size());
                    double score=static_cast<double>(a.defect-d0-d1)/static_cast<double>(1<<a.rank);
                    if(score>best){best=score;out.hint=b.vars[j]-1;}
                }
            }
        }
        if(out.hint>=0)++hints;
        ms+=std::chrono::duration<double,std::milli>(Tick::now()-start).count();return out;
    }
    void report()const{
        std::cerr<<"COOP1_STATS {\"mode\":\""<<mode<<"\",\"blocks\":"<<blocks.size()
          <<",\"activated_at_conflicts\":"<<activated_at_conflicts<<",\"passes\":"<<passes<<",\"windows\":"<<windows<<",\"affine_windows\":"<<affine_windows
          <<",\"nonaffine_windows\":"<<nonaffine_windows<<",\"conditioned\":"<<conditioned
          <<",\"forced_parities\":"<<forced_parities<<",\"lemmas\":"<<lemmas<<",\"proof_steps\":"<<proof_steps
          <<",\"hints\":"<<hints<<",\"applied_hints\":"<<applied_hints<<",\"propagations\":"<<propagations
          <<",\"conflicts\":"<<conflicts<<",\"analysis_ms\":"<<ms<<"}\n";
    }
};
}
