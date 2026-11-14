    // MATH-GUARD4: proof-first original-source resolution in SAME CDCL process.
    // OFF=0 SHADOW=1 ON=2 SELECTIVE=3. No speculative branch bans.
    // A resolvent of (x OR A) and (~x OR B) is a RUP consequence.
    // Only binary resolvents are injected, and only when both literals are
    // unassigned at root (so existing root BCP remains valid).
    void runMathGuard4() {
        stats_.mg_mode=mg_mode_;
        if (mg_mode_==0) return;
        const auto begin=Clock::now();
        const auto ms=[&]() {
            return std::chrono::duration<double,std::milli>(Clock::now()-begin).count();
        };
        if(n_>250000 || original_count_>250000) {
            stats_.mg_gate_skips=1;stats_.mg_wall_ms=ms();return;
        }
        if(mg_mode_==3 &&
           (n_>120000 || mg_orig_binary_<16 || mg_orig_ternary_<16 ||
            mg_orig_binary_*3 < static_cast<int64_t>(original_count_))) {
            stats_.mg_gate_skips=1;stats_.mg_wall_ms=ms();return;
        }
        struct Arm {
            int cid=0;
            int residual[2]={0,0};
            int n=0;
        };
        struct Bucket {
            std::vector<Arm> pos,neg;
        };
        std::map<int,Bucket> buckets;
        std::set<std::vector<int>> known;
        constexpr int SCAN_CAP=6000,PER_POLARITY=6,PAIR_CAP=12000,CLAUSE_CAP=32;
        for(int cid=0; cid<static_cast<int>(clauses_.size()) &&
                stats_.mg_scanned<SCAN_CAP;++cid) {
            if((cid&127)==0 && ms()>=mg_budget_ms_*0.50) {
                stats_.mg_budget_hit=true;break;
            }
            const auto& clause=clauses_[static_cast<size_t>(cid)];
            if(clause.learnt || clause.deleted)continue;
            ++stats_.mg_scanned;
            if(clause.lits.size()==2) {
                auto old=clause.lits;
                std::sort(old.begin(),old.end());
                known.insert(std::move(old));
            }
            if(clause.lits.size()<2 || clause.lits.size()>3)continue;
            for(int pivot:clause.lits) {
                auto& b=buckets[std::abs(pivot)];
                auto& part=pivot>0?b.pos:b.neg;
                if(part.size()>=PER_POLARITY)continue;
                Arm a; a.cid=cid;
                for(int lit:clause.lits)if(lit!=pivot)
                    a.residual[a.n++]=lit;
                part.push_back(a);
            }
        }
        struct ResultClause {
            std::vector<int> resolvent;
            int a,b,pivot;
        };
        std::vector<ResultClause> found;
        bool stop=false;
        for(const auto& [pivot,b]:buckets) {
            if(stop)break;
            for(const auto& a:b.pos) {
                if(stop)break;
                for(const auto& neg:b.neg) {
                    if((stats_.mg_pairs&63)==0 && ms()>=mg_budget_ms_) {
                        stats_.mg_budget_hit=true;stop=true;break;
                    }
                    if(++stats_.mg_pairs>PAIR_CAP || static_cast<int>(found.size())>=CLAUSE_CAP) {
                        stop=true;break;
                    }
                    std::vector<int> r;
                    for(int j=0;j<a.n;++j)r.push_back(a.residual[j]);
                    for(int j=0;j<neg.n;++j)r.push_back(neg.residual[j]);
                    std::sort(r.begin(),r.end());
                    r.erase(std::unique(r.begin(),r.end()),r.end());
                    if(r.size()!=2 || r[0]==-r[1])continue;
                    if(value(r[0])!=0 || value(r[1])!=0)continue;
                    if(!known.insert(r).second)continue;
                    found.push_back({std::move(r),a.cid,neg.cid,pivot});
                }
            }
        }
        stats_.mg_candidates=static_cast<int64_t>(found.size());
        bool inject=mg_mode_==2 || (mg_mode_==3 && found.size()>=3);
        if(mg_mode_==3 && !inject)++stats_.mg_gate_skips;
        if(inject) {
            for(const auto& c:found) {
                if(ms()>=mg_budget_ms_*1.30) {
                    stats_.mg_budget_hit=true;break;
                }
                if(stats_.mg_installed<8) {
                    const auto emit_vec=[](const std::vector<int>& v) {
                        std::cerr<<"[";
                        for(size_t i=0;i<v.size();++i) {
                            if(i)std::cerr<<",";
                            std::cerr<<v[i];
                        }
                        std::cerr<<"]";
                    };
                    std::cerr<<"MG4_LEMMA {\"pivot\":"<<c.pivot<<",\"parent_a\":";
                    emit_vec(clauses_[static_cast<size_t>(c.a)].lits);
                    std::cerr<<",\"parent_b\":";
                    emit_vec(clauses_[static_cast<size_t>(c.b)].lits);
                    std::cerr<<",\"clause\":";
                    emit_vec(c.resolvent);
                    std::cerr<<"}\n";
                }
                // storeClause emits the RUP addition in the original DRAT proof.
                const int id=storeClause(c.resolvent,true);
                mg_clause_ids_.insert(id);
                ++stats_.mg_installed;
                ++stats_.learnt;
            }
        }
        stats_.mg_wall_ms=ms();
    }
