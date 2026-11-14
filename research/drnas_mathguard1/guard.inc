    // MATH-GUARD1 is a proof-first root pass inside the SAME CDCL process.
    // It performs exact short-clause resolution, not a speculative second search.
    // Every emitted clause C is the direct resolvent of TWO ORIGINAL parents:
    // (x v A), (~x v B) entail (A v B). We emit only unit/binary resolvents.
    // A learned clause is therefore RUP; no heuristic UNSAT pruning is possible.
    // The pass is bounded in clause visits, pair checks, lemma count and wall ms.
    void runMathGuard() {
        const auto started=Clock::now();
        const auto elapsed_ms=[&]() {
            return std::chrono::duration<double,std::milli>(Clock::now()-started).count();
        };
        struct Arm {
            int cid=0;
            int residual[2]={0,0};
            int n=0;
        };
        struct Bucket {
            std::vector<Arm> positive,negative;
        };
        std::map<int,Bucket> buckets;
        std::set<std::vector<int>> existing;
        auto& st=stats_;

        // Large instances must not pay an unbounded preprocessing penalty.
        // The scan still includes only original clauses, never learnt clauses.
        if (n_ <= 1000000 && original_count_ <= 800000) {
            constexpr int SCAN_CAP=12000, PER_POLARITY=8;
            for (int cid=0;cid<static_cast<int>(clauses_.size()) &&
                           st.math_guard_scanned<SCAN_CAP;++cid) {
                if ((cid&127)==0 && elapsed_ms()>=math_guard_ms_*0.60) {
                    st.math_guard_budget_hit=true;
                    break;
                }
                const Clause& c=clauses_[static_cast<size_t>(cid)];
                if (c.learnt) continue;
                ++st.math_guard_scanned;
                if (c.lits.size()<=2) {
                    auto short_clause=c.lits;
                    std::sort(short_clause.begin(),short_clause.end());
                    existing.insert(std::move(short_clause));
                }
                if (c.lits.size()<2 || c.lits.size()>3) continue;
                for (int pivot:c.lits) {
                    auto& b=buckets[std::abs(pivot)];
                    auto& vec=pivot>0?b.positive:b.negative;
                    if (vec.size()>=PER_POLARITY) continue;
                    Arm a;
                    a.cid=cid;
                    for (int lit:c.lits) if (lit!=pivot)
                        a.residual[a.n++]=lit;
                    vec.push_back(a);
                }
            }
            auto log_clause=[](const std::vector<int>& clause) {
                std::cerr<<"[";
                for (size_t i=0;i<clause.size();++i) {
                    if(i)std::cerr<<",";
                    std::cerr<<clause[i];
                }
                std::cerr<<"]";
            };
            bool stopped=false;
            for (const auto& [pivot,b]:buckets) {
                if (stopped || root_unsat_) break;
                for (const Arm& a:b.positive) {
                    if (stopped || root_unsat_) break;
                    for (const Arm& neg:b.negative) {
                        if ((st.math_guard_pairs&63)==0 && elapsed_ms()>=math_guard_ms_) {
                            st.math_guard_budget_hit=true;
                            stopped=true;
                            break;
                        }
                        if (st.math_guard_pairs++>=40000 ||
                            st.math_guard_lemmas>=128) {
                            stopped=true;
                            break;
                        }
                        std::vector<int> resolvent;
                        for (int i=0;i<a.n;++i) resolvent.push_back(a.residual[i]);
                        for (int i=0;i<neg.n;++i) resolvent.push_back(neg.residual[i]);
                        std::sort(resolvent.begin(),resolvent.end());
                        resolvent.erase(std::unique(resolvent.begin(),resolvent.end()),
                                        resolvent.end());
                        if (resolvent.empty() || resolvent.size()>2 ||
                            (resolvent.size()==2 && resolvent[0]==-resolvent[1]))
                            continue;
                        if (!existing.insert(resolvent).second) {
                            ++st.math_guard_duplicate;
                            continue;
                        }

                        // Evidence is emitted BEFORE mutation; parent CIDs remain
                        // from the original CNF, and both are externally auditable.
                        if (st.math_guard_lemmas<16) {
                            std::cerr<<"MATH_GUARD_LEMMA {\"pivot\":"<<pivot
                                     <<",\"parent_positive\":";
                            log_clause(clauses_[static_cast<size_t>(a.cid)].lits);
                            std::cerr<<",\"parent_negative\":";
                            log_clause(clauses_[static_cast<size_t>(neg.cid)].lits);
                            std::cerr<<",\"clause\":";
                            log_clause(resolvent);
                            std::cerr<<"}\n";
                        }
                        const int cid=storeClause(std::move(resolvent),true);
                        ++st.learnt;
                        ++st.math_guard_lemmas;
                        if (clauses_[static_cast<size_t>(cid)].lits.size()==1) {
                            ++st.math_guard_units;
                            if (!enqueue(clauses_[static_cast<size_t>(cid)].lits[0],cid))
                                root_unsat_=true;
                        }
                    }
                }
            }
        }
        st.math_guard_wall_ms=elapsed_ms();
    }
