    // DELTA3: promote a REAL nonlinear tuple witness to short global CNF
    // resolvents.  The witness only triggers discovery; it is NEVER itself
    // asserted as a SAT/UNSAT fact. Every emitted clause is a one-step RUP
    // consequence of two ORIGINAL clauses from different local blocks.
    //
    // The output clause has NO unproved trail assumptions: resolution
    // preserves all conditional guard literals automatically.
    void resolveBridge(const Block& left,const Block& right,
                       const std::vector<int8_t>& values,
                       const std::function<void(const std::vector<int>&)>& emit,
                       Output& out,Tick::time_point deadline) {
        struct Candidate {
            std::vector<int> clause;
            std::vector<int> lsource,rsource;
            int pivot=0;
            int free=0;
        };
        std::vector<Candidate> queue;
        std::set<std::vector<int>> seen;
        int checked_pairs=0;
        for(const auto& a:left.cnf){
            if(Tick::now()>=deadline||checked_pairs>=192)break;
            if(a.size()<2||a.size()>5)continue;
            for(const auto& b:right.cnf){
                if(Tick::now()>=deadline||checked_pairs>=192)break;
                ++checked_pairs;
                if(b.size()<2||b.size()>5)continue;
                for(int pivot:a){
                    if(std::find(b.begin(),b.end(),-pivot)==b.end())continue;
                    ++bridge_cross_proposals;
                    std::vector<int> c;
                    for(int lit:a)if(lit!=pivot)c.push_back(lit);
                    for(int lit:b)if(lit!=-pivot)c.push_back(lit);
                    std::sort(c.begin(),c.end());
                    c.erase(std::unique(c.begin(),c.end()),c.end());
                    if(c.size()<2||c.size()>3)continue;
                    bool tautology=false;
                    for(int lit:c)if(std::binary_search(c.begin(),c.end(),-lit)){
                        tautology=true;break;
                    }
                    if(tautology)continue;
                    if(known.count(c)){++bridge_known_skips;continue;}
                    // Do not inject a clause subsumed by any local original.
                    bool subsumed=false;
                    for(const Block* block:{&left,&right}){
                        for(const auto& source:block->cnf){
                            auto short_source=canonical(source);
                            short_source.erase(std::unique(short_source.begin(),
                                                           short_source.end()),
                                               short_source.end());
                            if(short_source.size()<=c.size() &&
                               std::includes(c.begin(),c.end(),
                                             short_source.begin(),short_source.end())){
                                subsumed=true;break;
                            }
                        }
                        if(subsumed)break;
                    }
                    if(subsumed)continue;
                    bool satisfied=false;
                    int free=0;
                    for(int lit:c){
                        const auto v=values[static_cast<size_t>(std::abs(lit)-1)];
                        if(v==0)++free;
                        else if((v>0)==(lit>0)){satisfied=true;break;}
                    }
                    if(satisfied){++bridge_satisfied_skips;continue;}
                    if(free<1)continue;
                    ++bridge_active_candidates;
                    if(!seen.insert(c).second)continue;
                    queue.push_back(Candidate{c,a,b,pivot,free});
                }
            }
        }
        std::sort(queue.begin(),queue.end(),[](const Candidate& a,const Candidate& b){
            if(a.clause.size()!=b.clause.size())return a.clause.size()<b.clause.size();
            if(a.free!=b.free)return a.free<b.free;
            return a.clause<b.clause;
        });
        int proposed=0;
        for(const auto& p:queue){
            if(proposed>=2||out.clauses.size()>=8||lemmas>=256||
               Tick::now()>=deadline)break;
            if(known.count(p.clause))continue;
            ++proposed;
            ++bridge_unique_candidates;
            if(join_mode=="bridge-shadow"){
                ++bridge_shadow_candidates;
                continue;
            }
            // Parents are exact ORIGINAL clauses; their one-step resolvent
            // is RUP. The proof logger writes BEFORE CDCL stores the lemma.
            emit(p.clause);
            known.insert(p.clause);
            out.clauses.push_back(p.clause);
            ++lemmas;
            ++bridge_injected;
            if(bridge_emit_events<8){
                ++bridge_emit_events;
                const auto vec=[](const std::vector<int>& v){
                    std::cerr<<"[";
                    for(size_t j=0;j<v.size();++j){
                        if(j)std::cerr<<",";
                        std::cerr<<v[j];
                    }
                    std::cerr<<"]";
                };
                std::cerr<<"DELTA3_LEMMA {\"clause\":";
                vec(p.clause);
                std::cerr<<",\"left\":";
                vec(p.lsource);
                std::cerr<<",\"right\":";
                vec(p.rsource);
                std::cerr<<",\"pivot\":"<<p.pivot<<"}\n";
            }
        }
    }
