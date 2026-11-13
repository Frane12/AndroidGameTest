    drnas_coop4::Engine coop_;
    int coop_hint_=-1;
    // Additional lifetime metadata travels with each Clause through CDCL GC.
    // Only certified affine clauses added by retain mode are considered for expiry.
    std::string coop4_policy_="keep";
    std::vector<int> coop4_ids_;
    std::set<std::vector<int>> coop4_expired_keys_;
    int64_t coop4_next_sweep_=64;
    void configureCoop4Policy(const std::string& policy) {
        if(policy!="keep" && policy!="short" && policy!="long" &&
           policy!="adaptive")throw std::runtime_error("invalid COOP4 retention policy");
        coop4_policy_=policy;
    }
    void coop4RecordUse(int cid,bool conflict) {
        if(cid<0 || cid>=static_cast<int>(clauses_.size()))return;
        Clause& c=clauses_[static_cast<size_t>(cid)];
        if(!c.coop4_origin || c.deleted || x46_clone_ || probing_)return;
        if(stats_.conflicts<=c.coop4_born)return;
        if(c.coop4_uses==0){
            ++coop_.lifetime_first_use;
            const auto age=stats_.conflicts-c.coop4_born;
            coop_.lifetime_first_use_age_sum+=age;
            coop_.lifetime_first_use_age_max=std::max(coop_.lifetime_first_use_age_max,age);
        }else ++coop_.lifetime_reused;
        if(c.coop4_uses<65535)++c.coop4_uses;
        c.coop4_last=stats_.conflicts;
        if(conflict)++coop_.lifetime_used_conflict;
        else ++coop_.lifetime_used_reason;
    }
    void coop4RetentionSweep() {
        if(coop_.mode!="retain" || stats_.conflicts<coop4_next_sweep_ ||
           x46_clone_ || probing_ || coop4_ids_.empty())return;
        coop4_next_sweep_=stats_.conflicts+64;
        ++coop_.lifetime_sweeps;
        const bool keep=coop4_policy_=="keep";
        std::vector<uint8_t> locked;
        if(!keep){
            locked.assign(clauses_.size(),0);
            for(int v=0;v<n_;++v)
                if(values_[v]!=0 && reasons_[v]>=0)
                    locked[static_cast<size_t>(reasons_[v])]=1;
        }
        size_t kept=0;
        for(int cid:coop4_ids_) {
            if(cid<0 || cid>=static_cast<int>(clauses_.size()))
                throw std::runtime_error("COOP4 stale clause id");
            Clause& c=clauses_[static_cast<size_t>(cid)];
            if(c.deleted)continue;
            if(keep){coop4_ids_[kept++]=cid;continue;}
            const int64_t ttl=(coop4_policy_=="short"?128:
                (coop4_policy_=="long"?1024:
                (c.coop4_uses>=2?4096:(c.coop4_uses==1?1024:128))));
            if(stats_.conflicts-c.coop4_last<ttl) {
                if(c.coop4_uses>0)++coop_.lifetime_retained_use;
                coop4_ids_[kept++]=cid;continue;
            }
            if(locked[static_cast<size_t>(cid)]) {
                ++coop_.lifetime_locked_protected;
                coop4_ids_[kept++]=cid;continue;
            }
            const auto key=drnas_coop4::canonical(c.lits);
            coop4_expired_keys_.insert(key);
            coop_.known.erase(key); // a later recertification is allowed
            ++coop_.lifetime_expired;
            if(c.coop4_uses==0)++coop_.lifetime_expired_unused;
            else if(c.coop4_uses==1)++coop_.lifetime_expired_once;
            else ++coop_.lifetime_expired_multiple;
            const int64_t age=stats_.conflicts-c.coop4_born;
            coop_.lifetime_expired_age_sum+=age;
            coop_.lifetime_expired_age_max=std::max(coop_.lifetime_expired_age_max,age);
            c.deleted=true;
            // Remove each binary implication edge at the moment of expiry;
            // long clause watchers are skipped when c.deleted and swept by GC.
            if(c.lits.size()==2) {
                const auto remove_edge=[&](int lit){
                    auto& edges=binary_implications_[litIndex(lit)];
                    std::erase_if(edges,[cid](const auto& e){return e.second==cid;});
                };
                remove_edge(-c.lits[0]);
                remove_edge(-c.lits[1]);
            }
        }
        coop4_ids_.resize(kept);
        coop_.lifetime_current_active=static_cast<int64_t>(kept);
        coop_.lifetime_active_peak=std::max(coop_.lifetime_active_peak,
                                            coop_.lifetime_current_active);
    }
    void configureCoop(const std::string& mode,bool eager) {
        coop_.mode=mode;
        coop_.delayed=!eager;
        // Avoid copying any original clauses for disabled high-dimensional cases.
        if(n_>4096)coop_.disabled=true;
    }
    void initializeCoop() { coop_.initialize(n_); }
    void reportCoop() const { coop_.report(); }
    Prop cooperate() {
        coop_hint_=-1;
        if(!coop_.enabled() || x46_clone_)return Prop{};
        auto out=coop_.step(values_,stats_.decisions,stats_.conflicts,
            [&](const std::vector<int>& c){writeProofClause(c);});
        coop_hint_=out.hint;
        for(auto& c:out.clauses){
            std::stable_sort(c.begin(),c.end(),[&](int a,int b){
                if((value(a)==0)!=(value(b)==0))return value(a)==0;
                return levels_[std::abs(a)-1]>levels_[std::abs(b)-1];
            });
            int free=0,unit=0,maxlevel=0;bool sat=false;
            for(int l:c){if(value(l)==0){++free;unit=l;}
                if(value(l)==1)sat=true;
                maxlevel=std::max(maxlevel,levels_[std::abs(l)-1]);}
            int cid=storeClause(std::move(c),true);++stats_.learnt;
            clauses_[cid].glue=computeGlue(clauses_[cid].lits);
            if(coop_.mode=="retain") {
                Clause& q=clauses_[static_cast<size_t>(cid)];
                q.coop4_origin=true;
                q.coop4_born=stats_.conflicts;
                q.coop4_last=stats_.conflicts;
                q.coop4_uses=0;
                coop4_ids_.push_back(cid);
                ++coop_.lifetime_inserted;
                if(q.lits.size()==2)++coop_.lifetime_binary;
                else if(q.lits.size()>2)++coop_.lifetime_long;
                const auto key=drnas_coop4::canonical(q.lits);
                if(coop4_expired_keys_.erase(key)>0)++coop_.lifetime_relearned;
                coop_.lifetime_current_active=static_cast<int64_t>(coop4_ids_.size());
                coop_.lifetime_active_peak=std::max(coop_.lifetime_active_peak,
                                                   coop_.lifetime_current_active);
            }
            if(sat)continue;
            if(free==0){
                cancelUntil(maxlevel);++coop_.conflicts;
                return Prop{PropResult::CONFLICT,cid,0};
            }
            if(free==1){
                // Assert at the highest antecedent level; root units survive restarts.
                if(maxlevel<decisionLevel()){cancelUntil(maxlevel);coop_hint_=-1;}
                if(!enqueue(unit,cid))throw std::runtime_error("COOP4 unit enqueue failed");
                ++coop_.propagations;
            }
        }
        return propagate(-1);
    }
    void configureX5(