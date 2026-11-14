#pragma once
#include <map>
#include <set>
#include "delta4_join.hpp"

namespace drnas_coop4 {
// D4 remains the baseline. X adds bounded, indexed ORIGINAL-source resolution.
// A structural match is NOT labelled a beyond-affine/nonlinear witness.
class Delta4XEngine : public JoinEngine {
public:
    struct Candidate { std::vector<int> clause,a,b,reverse; int pivot=0,guard=0,left=0,right=0; };
    struct Alias { int guard=0; bool active=false; };
    int xmode=0; // 0: corrected D4, 1: X shadow, 2: X active
    int64_t xinput=0,xbinary_seen=0,xternary_seen=0,xreplacements=0;
    int64_t xpairs=0,xresolvents=0,xreverse_missing=0,xtautologies=0;
    int64_t xguard_wait=0,xsatisfied=0,xknown=0,xqueued=0,xinstalled=0,xshadow=0;
    int64_t xactivations=0,xdeactivations=0,xenqueues=0,xconflicts=0,xreason_analysis=0;
    int64_t xpasses=0,xnextconf=0,xlastdec=-1,xcursor=0,xlit=0,xpartner=0,xindex=0;
    double xms=0;
    bool xmerged=false,xprepared=false,xexhausted=false;
    std::vector<std::vector<int>> xbins,xterns,xshort;
    std::map<int,std::vector<int>> xocc;
    std::set<std::vector<int>> xbinary,xoriginal;
    std::vector<Candidate> xcandidates;
    std::set<std::pair<std::vector<int>,int>> xseen;
    std::map<std::vector<int>,Candidate> xpending;
    std::map<std::vector<int>,Alias> xaliases;

    static uint64_t mix(uint64_t z) { z+=0x9e3779b97f4a7c15ULL; z=(z^(z>>30))*0xbf58476d1ce4e5b9ULL; z=(z^(z>>27))*0x94d049bb133111ebULL; return z^(z>>31); }
    static void vec(const std::vector<int>& v) { std::cerr<<"["; for(size_t i=0;i<v.size();++i){if(i)std::cerr<<",";std::cerr<<v[i];}std::cerr<<"]"; }
    void setJoinMode(const std::string& m) {
        xmode=(m=="d4x"?2:(m=="d4x-shadow"?1:0));
        JoinEngine::setJoinMode(xmode?"d4":m);
    }
    void retain(std::vector<std::vector<int>>& pool,const std::vector<int>& c,int64_t count,size_t cap) {
        if(pool.size()<cap){pool.push_back(c);return;}
        // Preserve a connected prefix and sample the later stream, rather
        // than destroying every neighbourhood with a global reservoir.
        const auto half=cap/2;
        const auto slot=mix(static_cast<uint64_t>(count))%static_cast<uint64_t>(count-static_cast<int64_t>(half));
        if(slot<half){pool[half+static_cast<size_t>(slot)]=c;++xreplacements;}
    }
    void add(const std::vector<int>& c) {
        JoinEngine::add(c);
        if(!enabled()||!xmode)return;
        ++xinput;
        auto key=canonical(c);key.erase(std::unique(key.begin(),key.end()),key.end());
        if(key.size()==2){++xbinary_seen;retain(xbins,key,xbinary_seen,8192);}
        if(key.size()==3){++xternary_seen;retain(xterns,key,xternary_seen,16384);}
    }
    bool xReady(int64_t decisions,int64_t conflicts) const {
        return enabled()&&xmode&&xpasses<48&&xms<40.0&&lemmas<256&&
            (!delayed||conflicts>=64)&&
            (xlastdec<0||conflicts>=xnextconf||decisions-xlastdec>=64);
    }
    bool ready(int64_t decisions,int64_t conflicts) {
        return JoinEngine::ready(decisions,conflicts)||xReady(decisions,conflicts);
    }
    void prepareX(Tick::time_point deadline) {
        if(!xmerged){xshort=xbins;xshort.insert(xshort.end(),xterns.begin(),xterns.end());xmerged=true;}
        while(xindex<static_cast<int64_t>(xshort.size())&&Tick::now()<deadline){
            const auto& c=xshort[static_cast<size_t>(xindex)];
            xoriginal.insert(c);
            if(c.size()==2)xbinary.insert(c);
            for(int l:c)xocc[l].push_back(static_cast<int>(xindex));
            ++xindex;
        }
        xprepared=xindex==static_cast<int64_t>(xshort.size());
    }
    void discoverX(Tick::time_point deadline) {
        while(!xexhausted&&Tick::now()<deadline&&xpairs<50000&&xcandidates.size()<128){
            if(xcursor>=static_cast<int64_t>(xshort.size())){xexhausted=true;break;}
            const auto& a=xshort[static_cast<size_t>(xcursor)];
            if(xlit>=static_cast<int64_t>(a.size())){++xcursor;xlit=0;xpartner=0;continue;}
            const int pivot=a[static_cast<size_t>(xlit)];
            const auto it=xocc.find(-pivot);
            if(it==xocc.end()||xpartner>=static_cast<int64_t>(it->second.size())){++xlit;xpartner=0;continue;}
            const int j=it->second[static_cast<size_t>(xpartner++)];
            if(j<=xcursor)continue;
            ++xpairs;
            const auto& b=xshort[static_cast<size_t>(j)];
            std::vector<int> c;
            for(int l:a)if(l!=pivot)c.push_back(l);
            for(int l:b)if(l!=-pivot)c.push_back(l);
            c=canonical(c);c.erase(std::unique(c.begin(),c.end()),c.end());
            if(c.size()!=3)continue;
            bool taut=false;for(int l:c)if(std::binary_search(c.begin(),c.end(),-l))taut=true;
            if(taut){++xtautologies;continue;}
            ++xresolvents;
            if(xoriginal.count(c))continue;
            for(int guard:c){
                std::vector<int> residual;for(int l:c)if(l!=guard)residual.push_back(l);
                if((residual[0]>0)==(residual[1]>0))continue;
                const int neg=residual[0]<0?residual[0]:residual[1];
                const int pos=residual[0]>0?residual[0]:residual[1];
                const auto reverse=canonical({-neg,-pos});
                if(!xbinary.count(reverse)){++xreverse_missing;continue;}
                if(xseen.insert({c,guard}).second)
                    xcandidates.push_back(Candidate{c,a,b,reverse,pivot,guard,-neg,pos});
                if(xcandidates.size()>=128)break;
            }
        }
        if(xpairs>=50000)xexhausted=true;
    }
    Output step(const std::vector<int8_t>& values,int64_t decisions,int64_t conflicts,
                const std::function<void(const std::vector<int>&)>& emit) {
        // Give exact original-source guarded reasons first refusal: ordinary
        // D4 may otherwise install the same resolvent before X can record
        // provenance. A step with no X clause falls back to identical D4.
        // Shadow always falls back to D4 and never inserts X candidates.
        xpending.clear(); // clauses not stored after an early conflict may be rediscovered
        if(!xReady(decisions,conflicts))
            return JoinEngine::step(values,decisions,conflicts,emit);
        Output out;
        const auto start=Tick::now();++xpasses;xlastdec=decisions;xnextconf=conflicts+64;
        const double allowance=std::min(xprepared?2.0:6.0,40.0-xms);
        const auto deadline=start+std::chrono::microseconds(static_cast<int64_t>(allowance*1000));
        if(!xprepared)prepareX(deadline);
        if(xprepared)discoverX(deadline);
        int proposed=0;
        for(const auto& c:xcandidates){
            if(Tick::now()>=deadline||proposed>=2||out.clauses.size()>=8||xinstalled>=64||lemmas>=256)break;
            const int8_t gv=values[static_cast<size_t>(std::abs(c.guard)-1)];
            if(gv==0||((gv>0)==(c.guard>0))){++xguard_wait;continue;}
            bool sat=false;int free=0;
            for(int l:c.clause){const auto v=values[static_cast<size_t>(std::abs(l)-1)];if(!v)++free;else if((v>0)==(l>0))sat=true;}
            if(sat){++xsatisfied;continue;}
            if(known.count(c.clause)||xpending.count(c.clause)){++xknown;continue;}
            bool in_output=false;for(const auto& q:out.clauses)if(canonical(q)==c.clause)in_output=true;
            if(in_output)continue;
            ++proposed;
            if(xmode==1){++xshadow;continue;}
            // No unguarded replacement, no speculative enqueue, no double
            // proof emission. Normal storeClause(learnt=true) logs the proof.
            xpending.emplace(c.clause,c);out.clauses.push_back(c.clause);++xqueued;
            (void)free;
        }
        xms+=std::chrono::duration<double,std::milli>(Tick::now()-start).count();
        if(out.clauses.empty())return JoinEngine::step(values,decisions,conflicts,emit);
        return out;
    }
    bool onStored(const std::vector<int>& clause,const std::vector<int8_t>& values) {
        const auto key=canonical(clause);const auto it=xpending.find(key);
        if(it==xpending.end())return false;
        const auto c=it->second;xpending.erase(it);
        known.insert(key);++lemmas;++xinstalled;
        xaliases.try_emplace(key,Alias{c.guard,false});
        refresh(values);
        std::cerr<<"DELTA4X_ALIAS {\"installed\":true,\"guard\":"<<c.guard<<",\"a\":"<<c.left<<",\"b\":"<<c.right<<",\"pivot\":"<<c.pivot<<",\"forward\":";vec(c.clause);
        std::cerr<<",\"reverse\":";vec(c.reverse);std::cerr<<",\"parent_a\":";vec(c.a);std::cerr<<",\"parent_b\":";vec(c.b);std::cerr<<"}\n";
        return true;
    }
    void refresh(const std::vector<int8_t>& values) {
        for(auto& [key,a]:xaliases){(void)key;const auto v=values[static_cast<size_t>(std::abs(a.guard)-1)];const bool on=v!=0&&((v>0)!=(a.guard>0));
            if(on!=a.active){if(on)++xactivations;else ++xdeactivations;a.active=on;}}
    }
    void trailChange(int lit,const std::vector<int8_t>& values) {
        for(const auto& [key,a]:xaliases){(void)key;if(std::abs(lit)==std::abs(a.guard)){refresh(values);return;}}
    }
    void reportX() const {
        std::cerr<<"DELTA4X_STATS {\"mode\":"<<xmode<<",\"math_enabled\":"<<(enabled()?"true":"false")
          <<",\"declared_variables\":"<<declared_variables<<",\"d4_originals\":"<<originals.size()<<",\"blocks\":"<<blocks.size()
          <<",\"input_clauses\":"<<xinput<<",\"short_clauses_retained\":"<<(xbins.size()+xterns.size())
          <<",\"index_ready\":"<<(xprepared?"true":"false")<<",\"passes\":"<<xpasses<<",\"pairs_examined\":"<<xpairs
          <<",\"resolvents\":"<<xresolvents<<",\"reverse_missing\":"<<xreverse_missing<<",\"guarded_candidates\":"<<xcandidates.size()
          <<",\"guard_wait\":"<<xguard_wait<<",\"satisfied_skips\":"<<xsatisfied<<",\"known_skips\":"<<xknown
          <<",\"shadow_candidates\":"<<xshadow<<",\"queued\":"<<xqueued<<",\"installed\":"<<xinstalled
          <<",\"guard_activations\":"<<xactivations<<",\"guard_deactivations\":"<<xdeactivations
          <<",\"actual_enqueues\":"<<xenqueues<<",\"conflict_analysis_uses\":"<<xconflicts<<",\"reason_analysis_uses\":"<<xreason_analysis
          <<",\"analysis_ms\":"<<xms<<",\"structural_not_nonlinearity_proof\":true}\n";
    }
};
} // namespace drnas_coop4
