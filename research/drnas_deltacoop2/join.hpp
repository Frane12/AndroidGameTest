#pragma once
// Exact bounded relational join; no claim that semijoins are new mathematics.
namespace drnas_coop4 {
inline unsigned project_bits(unsigned x,const std::vector<int>& from,
                             const std::vector<int>& to) {
    unsigned y=0;
    for(size_t j=0;j<to.size();++j){
        const auto i=std::lower_bound(from.begin(),from.end(),to[j])-from.begin();
        if(x&(1u<<i))y|=1u<<j;
    }
    return y;
}
struct Hull {
    std::array<unsigned,8> basis{};
    unsigned origin=0; bool empty=true;
    explicit Hull(const std::vector<int>& points) {
        if(points.empty())return;
        empty=false;origin=static_cast<unsigned>(points[0]);
        for(int p:points){unsigned x=static_cast<unsigned>(p)^origin;
            for(int j=7;j>=0;--j)if(x&(1u<<j)){
                if(basis[j])x^=basis[j];else{basis[j]=x;break;}
            }
        }
    }
    bool contains(unsigned x)const {
        if(empty)return false;
        x^=origin;
        for(int j=7;j>=0;--j)if(x&(1u<<j)){
            if(!basis[j])return false;
            x^=basis[j];
        }
        return true;
    }
};
struct JoinResult {
    Block support;
    std::vector<int> left,right,units;
    bool conflict=false;
    int removed=0;
};
inline std::vector<int> table_units(const Block& b,const std::vector<int>& points,
                                  const std::vector<int8_t>& values) {
    std::vector<int> units;
    if(points.empty())return units;
    unsigned yes=(1u<<b.vars.size())-1,no=yes;
    for(int x:points){yes&=static_cast<unsigned>(x);no&=~static_cast<unsigned>(x);}
    for(size_t j=0;j<b.vars.size();++j)if(!values[b.vars[j]-1]){
        if(yes&(1u<<j))units.push_back(b.vars[j]);
        else if(no&(1u<<j))units.push_back(-b.vars[j]);
    }
    return units;
}
inline JoinResult join_pair(const Block& a,const std::vector<int>& ap,
                            const Block& b,const std::vector<int>& bp,
                            const std::vector<int8_t>& values) {
    JoinResult r;
    std::vector<int> sep;
    std::set_intersection(a.vars.begin(),a.vars.end(),b.vars.begin(),b.vars.end(),std::back_inserter(sep));
    std::set_union(a.vars.begin(),a.vars.end(),b.vars.begin(),b.vars.end(),std::back_inserter(r.support.vars));
    if(sep.empty()||r.support.vars.size()>12)throw std::runtime_error("DELTA2_BAD_PAIR");
    r.support.cnf=a.cnf;
    r.support.cnf.insert(r.support.cnf.end(),b.cnf.begin(),b.cnf.end());
    std::array<bool,256> as{},bs{};
    for(int x:ap)as[project_bits(static_cast<unsigned>(x),a.vars,sep)]=true;
    for(int x:bp)bs[project_bits(static_cast<unsigned>(x),b.vars,sep)]=true;
    for(int x:ap)if(bs[project_bits(static_cast<unsigned>(x),a.vars,sep)])r.left.push_back(x);
    for(int x:bp)if(as[project_bits(static_cast<unsigned>(x),b.vars,sep)])r.right.push_back(x);
    r.removed=static_cast<int>(ap.size()+bp.size()-r.left.size()-r.right.size());
    r.conflict=r.left.empty()||r.right.empty();
    if(!r.conflict){
        r.units=table_units(a,r.left,values);
        auto u=table_units(b,r.right,values);
        r.units.insert(r.units.end(),u.begin(),u.end());
        std::sort(r.units.begin(),r.units.end());
        r.units.erase(std::unique(r.units.begin(),r.units.end()),r.units.end());
    }
    return r;
}
// A concrete countermodel in Aff(Ta) JOIN Aff(Tb) proves that this pair's
// complete linear GF(2) consequences cannot derive the proposed conclusion.
// It does NOT rule out deductions using other blocks or all original clauses.
inline int affine_countermodel(const Block& a,const std::vector<int>& ap,
                               const Block& b,const std::vector<int>& bp,
                               const std::vector<int>& vars,int unit,
                               Tick::time_point deadline) {
    Hull ah(ap),bh(bp);
    for(unsigned x=0;x<(1u<<vars.size());++x){
        if((x&63u)==0&&Tick::now()>=deadline)return -2; // unclassified
        if(unit){
            auto j=std::lower_bound(vars.begin(),vars.end(),std::abs(unit))-vars.begin();
            if(((x&(1u<<j))!=0)==(unit>0))continue;
        }
        if(ah.contains(project_bits(x,vars,a.vars))&&
           bh.contains(project_bits(x,vars,b.vars)))return static_cast<int>(x);
    }
    return -1;
}
inline int tuple_countermodel(const Block& a,const std::vector<int>& ap,
                              const Block& b,const std::vector<int>& bp,
                              const std::vector<int>& vars,int blocked,
                              Tick::time_point deadline){
    Hull ah(ap),bh(bp);
    for(unsigned x=0;x<(1u<<vars.size());++x){
        if((x&63u)==0&&Tick::now()>=deadline)return -2;
        const auto ax=project_bits(x,vars,a.vars);
        if(ax==static_cast<unsigned>(blocked)&&ah.contains(ax)&&
           bh.contains(project_bits(x,vars,b.vars)))return static_cast<int>(x);
    }
    return -1;
}

class JoinEngine:public Engine {
 public:
    std::string join_mode="local";
    std::vector<std::pair<size_t,size_t>> pairs;
    bool pairs_prepared=false;
    std::map<std::pair<size_t,size_t>,int64_t> pair_states;
    int64_t pair_evaluations=0,tuples_removed=0,pair_unit_events=0,pair_conflict_events=0;
    int64_t beyond_pair_affine=0,affine_unclassified=0,join_certified=0,join_nonlinear_certified=0;
    int64_t unchanged_pairs=0,ready_skips=0,local_unit_events=0,local_conflict_events=0;
    int witnesses=0,tuple_witnesses=0,tuple_probes=0;
    int64_t nonlinear_tuple_events=0;
    void emitWitness(const Block& a,const Block& b,const std::vector<int8_t>& values,
                 const std::vector<int>& vars,int unit,int countermodel,int blocked=-1){
        if(blocked<0){if(witnesses>=4)return;++witnesses;}
        else{if(tuple_witnesses>=4)return;++tuple_witnesses;}
        const auto vec=[](const std::vector<int>& v){
            std::cerr<<"[";for(size_t j=0;j<v.size();++j){if(j)std::cerr<<",";std::cerr<<v[j];}std::cerr<<"]";
        };
        const auto block=[&](const Block& z){
            std::cerr<<"{\"vars\":";vec(z.vars);std::cerr<<",\"cnf\":[";
            for(size_t j=0;j<z.cnf.size();++j){if(j)std::cerr<<",";vec(z.cnf[j]);}std::cerr<<"]}";
        };
        std::vector<int> assumptions;
        for(int v:vars)if(values[v-1])assumptions.push_back(values[v-1]>0?v:-v);
        std::cerr<<"DELTA2_WITNESS {\"kind\":\""<<(blocked<0?"conclusion":"tuple")
                 <<"\",\"blocked_left_tuple\":"<<blocked<<",\"unit\":"<<unit<<",\"affine_countermodel\":"<<countermodel
                 <<",\"union_vars\":";vec(vars);std::cerr<<",\"assumptions\":";vec(assumptions);
        std::cerr<<",\"left\":";block(a);std::cerr<<",\"right\":";block(b);std::cerr<<"}\n";
    }
    void setJoinMode(const std::string& m){
        if(m!="local"&&m!="shadow"&&m!="join")throw std::runtime_error("DELTA2_BAD_MODE");
        join_mode=m;
    }
    bool ready(int64_t decisions,int64_t cdcl_conflicts){
        bool ok=enabled()&&passes<24&&ms<30&&lemmas<256&&
            (!delayed||cdcl_conflicts>=64)&&cdcl_conflicts>=gate_next_conflict&&
            (last_dec<0||(decisions<8&&decisions!=last_dec)||
             decisions-last_dec>=16||cdcl_conflicts-last_conf>=16);
        if(!ok)++ready_skips;
        return ok;
    }
    void prepare_pairs(){
        if(pairs_prepared)return;
        pairs_prepared=true;
        // Deterministic, labels/results never enter the selection.
        for(size_t i=0;i<blocks.size()&&pairs.size()<96;++i){
            for(size_t j=i+1;j<blocks.size()&&pairs.size()<96;++j){
                std::vector<int> common,both;
                const auto& a=blocks[i].vars;const auto& b=blocks[j].vars;
                std::set_intersection(a.begin(),a.end(),b.begin(),b.end(),std::back_inserter(common));
                if(common.size()<2||common.size()==std::min(a.size(),b.size()))continue;
                std::set_union(a.begin(),a.end(),b.begin(),b.end(),std::back_inserter(both));
                // The union need not be one of the 64 selected old windows.
                // Novel units are filtered against all evaluated single blocks.
                if(both.size()<=12)pairs.emplace_back(i,j);
            }
        }
    }
    Output step(const std::vector<int8_t>& values,int64_t decisions,int64_t cdcl_conflicts,
                const std::function<void(const std::vector<int>&)>& emit){
        Output out;
        if(!ready(decisions,cdcl_conflicts))return out;
        if(!prepared)prepare();
        if(blocks.empty()||ms>=30)return out;
        // Parent preparation already accounts for its own elapsed time.
        const auto work_start=Tick::now();
        prepare_pairs();
        auto deadline=std::min(work_start+std::chrono::microseconds(2500),
            work_start+std::chrono::microseconds(static_cast<int64_t>(std::max(0.0,30-ms)*1000)));
        last_dec=decisions;last_conf=cdcl_conflicts;++passes;
        const int old_lemmas=lemmas;
        std::vector<Analysis> tables(blocks.size());
        std::vector<bool> available(blocks.size(),false);
        std::set<int> local_units;
        bool local_conflict=false;
        auto propose=[&](const Block& b,int unit,bool from_join,bool nonlinear){
            std::vector<int> c;
            for(int v:b.vars)if(values[v-1])c.push_back(values[v-1]>0?-v:v);
            if(unit)c.push_back(unit);
            auto key=canonical(c);
            if(known.count(key)||out.clauses.size()>=8)return;
            if(unit)++delta_candidate_units;else ++delta_candidate_conflicts;
            if(join_mode=="shadow"||mode=="observe")return;
            if(!certify(b,c,emit,deadline)){++gate_certification_limits;return;}
            known.insert(key);out.clauses.push_back(c);++lemmas;
            if(from_join){++join_certified;if(nonlinear)++join_nonlinear_certified;}
        };
        for(size_t i=0;i<blocks.size();++i){
            if(Tick::now()>=deadline)break;
            auto& b=blocks[i];tables[i]=analyze(b,values);available[i]=true;++windows;
            auto& a=tables[i];
            if(a.defect==0)++affine_windows;else ++nonaffine_windows;
            if(a.feasible.empty()){
                local_conflict=true;++local_conflict_events;propose(b,0,false,false);continue;
            }
            for(int unit:table_units(b,a.feasible,values)){
                ++local_unit_events;local_units.insert(unit);propose(b,unit,false,false);
            }
        }
        if(join_mode!="local"&&!local_conflict){
            for(auto [i,j]:pairs){
                if(Tick::now()>=deadline||out.clauses.size()>=8)break;
                if(!available[i]||!available[j])continue;
                const auto& a=blocks[i];const auto& b=blocks[j];
                int64_t state=0;
                for(int v:a.vars)state=state*3+values[v-1]+1;
                for(int v:b.vars)state=state*3+values[v-1]+1;
                auto pos=pair_states.find({i,j});
                if(pos!=pair_states.end()&&pos->second==state){++unchanged_pairs;continue;}
                pair_states[{i,j}]=state;
                auto r=join_pair(a,tables[i].feasible,b,tables[j].feasible,values);
                ++pair_evaluations;tuples_removed+=r.removed;
                std::vector<int> candidates;
                if(r.conflict){++pair_conflict_events;candidates.push_back(0);}
                else for(int unit:r.units)if(!local_units.count(unit)){
                    ++pair_unit_events;candidates.push_back(unit);
                }
                for(int unit:candidates){
                    if(Tick::now()>=deadline)break;
                    const int witness=affine_countermodel(a,tables[i].feasible,b,tables[j].feasible,
                                                         r.support.vars,unit,deadline);
                    const bool nonlinear=witness>=0;
                    if(nonlinear){++beyond_pair_affine;
                        emitWitness(a,b,values,r.support.vars,unit,witness);}
                    if(witness==-2)++affine_unclassified;
                    propose(r.support,unit,true,nonlinear);
                }
                // Secondary diagnostic only, never injected or called speed
                // progress. At most 16 probes and 4 saved tuple witnesses/run.
                if(r.removed>0&&candidates.empty()&&tuple_probes<16&&Tick::now()<deadline){
                    for(int x:tables[i].feasible){
                        if(std::find(r.left.begin(),r.left.end(),x)!=r.left.end())continue;
                        ++tuple_probes;
                        const int w=tuple_countermodel(a,tables[i].feasible,b,tables[j].feasible,
                                                       r.support.vars,x,deadline);
                        if(w>=0){++nonlinear_tuple_events;emitWitness(a,b,values,r.support.vars,0,w,x);}
                        break;
                    }
                }
            }
        }
        if(lemmas>old_lemmas){gate_empty_streak=0;gate_next_conflict=cdcl_conflicts+64;}
        else{gate_empty_streak=std::min(5,gate_empty_streak+1);
             gate_next_conflict=cdcl_conflicts+std::min<int64_t>(2048,64LL<<gate_empty_streak);}
        ms+=std::chrono::duration<double,std::milli>(Tick::now()-work_start).count();
        return out;
    }
    void reportJoin()const{
        std::cerr<<"DELTA2_JOIN {\"mode\":\""<<join_mode<<"\",\"pairs\":"<<pairs.size()
          <<",\"pair_evaluations\":"<<pair_evaluations<<",\"tuples_removed\":"<<tuples_removed
          <<",\"pair_unit_events\":"<<pair_unit_events<<",\"pair_conflict_events\":"<<pair_conflict_events
          <<",\"beyond_pair_affine\":"<<beyond_pair_affine<<",\"affine_unclassified\":"<<affine_unclassified
          <<",\"join_certified\":"<<join_certified<<",\"join_nonlinear_certified\":"<<join_nonlinear_certified
          <<",\"nonlinear_tuple_events\":"<<nonlinear_tuple_events<<",\"tuple_probes\":"<<tuple_probes
          <<",\"unchanged_pairs\":"<<unchanged_pairs<<",\"ready_skips\":"<<ready_skips
          <<",\"local_unit_events\":"<<local_unit_events<<",\"local_conflict_events\":"<<local_conflict_events
          <<",\"analysis_ms\":"<<ms<<"}\n";
    }
};
} // namespace drnas_coop4
