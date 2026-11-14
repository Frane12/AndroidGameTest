    // DELTAX: proof-carrying guarded equivalence, discovered from a
    // REAL nonlinear separator witness. No variable substitution: CDCL owns
    // the trail and each added implication has a source-RUP clause reason.
    // Tracker is an OBSERVER; it never changes variable assignments or proof.
    struct DeltaxAlias {
        int guard=0, left=0, right=0;
        bool active=false;
    };
    std::vector<DeltaxAlias> deltax_aliases_;
    std::set<std::vector<int>> deltax_binary_originals_;
    std::set<std::vector<int>> deltax_clause_keys_;
    bool deltax_binaries_ready_=false;
    int64_t deltax_witnesses_=0,deltax_proposals_=0,deltax_candidates_=0;
    int64_t deltax_shadow_=0,deltax_injected_=0,deltax_events_=0;
    int64_t deltax_activation_=0,deltax_deactivation_=0;
    int64_t deltax_reason_uses_=0,deltax_conflict_uses_=0;
    int64_t deltax_active_=0,deltax_peak_active_=0,deltax_peak_compression_=0;
    int64_t deltax_guarded_undo_checks_=0;

    void deltaxPrepareOriginalBinaries() {
        if(deltax_binaries_ready_)return;
        deltax_binaries_ready_=true;
        // The reverse implication must come from the ORIGINAL input.
        // Learned clauses or label-specific metadata cannot authorize it.
        for(const auto& c:originals)
            if(c.size()==2 && std::abs(c[0])!=std::abs(c[1]))
                deltax_binary_originals_.insert(canonical(c));
    }
    bool deltaxIsClause(const std::vector<int>& c) const {
        return !deltax_clause_keys_.empty() &&
               deltax_clause_keys_.count(canonical(c))!=0;
    }
    void deltaxRecordUse(bool is_conflict) {
        if(is_conflict)++deltax_conflict_uses_;
        else ++deltax_reason_uses_;
    }
    void deltaxRefreshAliases(const std::vector<int8_t>& values) {
        if(deltax_aliases_.empty())return;
        std::map<int,int> parent;
        for(auto& e:deltax_aliases_) {
            const int8_t val=values[static_cast<size_t>(std::abs(e.guard)-1)];
            const bool on=val!=0 && ((val>0)!=(e.guard>0));
            if(on!=e.active) {
                if(on)++deltax_activation_;
                else {++deltax_deactivation_;++deltax_guarded_undo_checks_;}
                e.active=on;
            }
            if(on) {
                parent.emplace(e.left,e.left);
                parent.emplace(e.right,e.right);
            }
        }
        int64_t active=0;
        for(const auto& e:deltax_aliases_)if(e.active)++active;
        deltax_active_=active;
        deltax_peak_active_=std::max(deltax_peak_active_,active);
        if(parent.empty())return;
        const auto find_root=[&](int x){
            while(parent[x]!=x)x=parent[x];
            return x;
        };
        for(const auto& e:deltax_aliases_)if(e.active) {
            const int a=find_root(e.left),b=find_root(e.right);
            if(a!=b)parent[b]=a;
        }
        std::set<int> reps;
        for(const auto& [variable,ignored]:parent) {
            (void)ignored;
            reps.insert(find_root(variable));
        }
        deltax_peak_compression_=std::max<int64_t>(
            deltax_peak_compression_,
            static_cast<int64_t>(parent.size()-reps.size()));
    }
    void deltaxOnTrailChange(int lit,const std::vector<int8_t>& values) {
        if(deltax_aliases_.empty())return;
        for(const auto& a:deltax_aliases_) {
            if(std::abs(a.guard)==std::abs(lit)) {
                deltaxRefreshAliases(values);
                return;
            }
        }
    }

    void resolveDeltax(const Block& left,const Block& right,
                       const std::vector<int8_t>& values,
                       Output& out,Tick::time_point deadline) {
        if(deltax_witnesses_>=4||out.clauses.size()>=8)return;
        ++deltax_witnesses_;
        deltaxPrepareOriginalBinaries();
        struct Candidate {
            std::vector<int> clause;
            std::vector<int> parent_a,parent_b,reverse;
            int pivot=0,guard=0,a=0,b=0,free=0;
        };
        std::vector<Candidate> found;
        std::set<std::vector<int>> seen;
        int checked=0;
        const std::array<std::pair<const Block*,const Block*>,3> regions{{
            {&left,&right},{&left,&left},{&right,&right}}};
        for(const auto& region:regions) {
            if(checked>=192||Tick::now()>=deadline)break;
            for(const auto& original_a:region.first->cnf) {
                if(checked>=192||Tick::now()>=deadline)break;
                if(original_a.size()<2||original_a.size()>5)continue;
                for(const auto& original_b:region.second->cnf) {
                    if(checked>=192||Tick::now()>=deadline)break;
                    ++checked;
                    if(original_b.size()<2||original_b.size()>5)continue;
                    for(int pivot:original_a) {
                        if(std::find(original_b.begin(),original_b.end(),-pivot)==original_b.end())
                            continue;
                        ++deltax_proposals_;
                        std::vector<int> c;
                        for(int lit:original_a)if(lit!=pivot)c.push_back(lit);
                        for(int lit:original_b)if(lit!=-pivot)c.push_back(lit);
                        std::sort(c.begin(),c.end());
                        c.erase(std::unique(c.begin(),c.end()),c.end());
                        if(c.size()!=3||known.count(c)||!seen.insert(c).second)continue;
                        bool taut=false;
                        for(int lit:c)if(std::binary_search(c.begin(),c.end(),-lit)){
                            taut=true;break;
                        }
                        if(taut)continue;
                        for(int guard:c) {
                            const int8_t val=values[static_cast<size_t>(std::abs(guard)-1)];
                            // Exact conditional alias applies only when guard
                            // is currently FALSE. Guard is retained in CNF.
                            if(val==0||((val>0)==(guard>0)))continue;
                            std::vector<int> residual;
                            for(int lit:c)if(lit!=guard)residual.push_back(lit);
                            if(residual.size()!=2 || residual[0]*residual[1]>=0 ||
                               std::abs(residual[0])==std::abs(residual[1]))continue;
                            const int negative=residual[0]<0?residual[0]:residual[1];
                            const int positive=residual[0]>0?residual[0]:residual[1];
                            const auto reverse=canonical({-negative,-positive});
                            if(deltax_binary_originals_.count(reverse)==0)continue;
                            bool satisfied=false;
                            int free=0;
                            for(int lit:c) {
                                const int8_t x=values[static_cast<size_t>(std::abs(lit)-1)];
                                if(x==0)++free;
                                else if((x>0)==(lit>0)){satisfied=true;break;}
                            }
                            if(satisfied || free==0)continue;
                            found.push_back(Candidate{c,original_a,original_b,reverse,pivot,
                                                      guard,-negative,positive,free});
                            break;
                        }
                    }
                }
            }
        }
        std::stable_sort(found.begin(),found.end(),[](const Candidate& a,const Candidate& b){
            if(a.free!=b.free)return a.free<b.free;
            return a.clause<b.clause;
        });
        int submitted=0;
        for(const auto& c:found) {
            if(submitted>=2 || out.clauses.size()>=8 || lemmas>=256 ||
               Tick::now()>=deadline)break;
            if(known.count(c.clause))continue;
            ++submitted;++deltax_candidates_;
            const bool installed=join_mode=="deltax";
            if(!installed)++deltax_shadow_;
            else {
                // c is one-step resolution of two ORIGINAL clauses.
                // storeClause(learnt=true) is the sole proof-log write.
                // The existing CDCL bridge will then store the watched clause,
                // propagate its unit consequence and supply a reason clause.
                known.insert(c.clause);
                deltax_clause_keys_.insert(c.clause);
                deltax_aliases_.push_back(DeltaxAlias{c.guard,c.a,c.b,false});
                out.clauses.push_back(c.clause);
                ++lemmas;++deltax_injected_;
                deltaxRefreshAliases(values);
            }
            if(deltax_events_<8) {
                ++deltax_events_;
                const auto vec=[](const std::vector<int>& v){
                    std::cerr<<"[";
                    for(size_t i=0;i<v.size();++i){
                        if(i)std::cerr<<",";
                        std::cerr<<v[i];
                    }
                    std::cerr<<"]";
                };
                std::cerr<<"DELTAX_ALIAS {\"installed\":"
                         <<(installed?"true":"false")
                         <<",\"guard\":"<<c.guard
                         <<",\"a\":"<<c.a<<",\"b\":"<<c.b
                         <<",\"pivot\":"<<c.pivot
                         <<",\"forward\":";
                vec(c.clause);
                std::cerr<<",\"reverse\":";
                vec(c.reverse);
                std::cerr<<",\"parent_a\":";
                vec(c.parent_a);
                std::cerr<<",\"parent_b\":";
                vec(c.parent_b);
                std::cerr<<"}\n";
            }
        }
    }
    void reportDeltax(const std::vector<int8_t>& values) const {
        int64_t active=0;
        for(const auto& e:deltax_aliases_) {
            const int8_t val=values[static_cast<size_t>(std::abs(e.guard)-1)];
            if(val!=0 && ((val>0)!=(e.guard>0)))++active;
        }
        std::cerr<<"DELTAX_STATS {\"mode\":\""<<join_mode
                 <<"\",\"witnesses\":"<<deltax_witnesses_
                 <<",\"source_resolution_proposals\":"<<deltax_proposals_
                 <<",\"guarded_candidates\":"<<deltax_candidates_
                 <<",\"shadow_candidates\":"<<deltax_shadow_
                 <<",\"proof_carrying_injected\":"<<deltax_injected_
                 <<",\"guard_activations\":"<<deltax_activation_
                 <<",\"guard_deactivations\":"<<deltax_deactivation_
                 <<",\"rollback_checks\":"<<deltax_guarded_undo_checks_
                 <<",\"active_now\":"<<active
                 <<",\"peak_active\":"<<deltax_peak_active_
                 <<",\"max_alias_variables_removed\":"<<deltax_peak_compression_
                 <<",\"cdcl_reason_uses\":"<<deltax_reason_uses_
                 <<",\"cdcl_conflict_uses\":"<<deltax_conflict_uses_
                 <<"}\n";
    }
