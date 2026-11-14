    // MATH-GUARD2: a single-process, root-level proof-producing graph-3-colour detector.
    // Every diamond consists of triangles (a,b,c) and (a,b,d). Resolution
    // proves c_k => not d_j for k!=j. No speculative claims are ever injected.
    void runMathGuard2() {
        const auto start=Clock::now();
        const auto ms=[&]() {
            return std::chrono::duration<double,std::milli>(Clock::now()-start).count();
        };
        auto& st=stats_;
        // Strict bounded input recognition; never assume variable naming alone
        // proves that an arbitrary CNF is a graph-colouring instance.
        if (n_<12 || n_%3!=0 || n_/3>96 || original_count_>24000) {
            st.math_guard2_wall_ms=ms();
            return;
        }
        const int vertices=n_/3;
        std::set<std::vector<int>> known;
        for (const Clause& clause:clauses_) {
            if (clause.learnt || clause.deleted) continue;
            auto x=clause.lits;
            std::sort(x.begin(),x.end());
            known.insert(std::move(x));
            ++st.math_guard2_scanned;
            if ((st.math_guard2_scanned&255)==0 && ms()>=math_guard2_budget_ms_) {
                st.math_guard2_budget_hit=true;
                st.math_guard2_wall_ms=ms();
                return;
            }
        }
        std::vector<bool> vertex_ok(static_cast<size_t>(vertices),false);
        for (int v=0;v<vertices;++v) {
            vertex_ok[v]=known.count({3*v+1,3*v+2,3*v+3})!=0;
        }
        std::vector<std::vector<bool>> adjacency(
            static_cast<size_t>(vertices),std::vector<bool>(static_cast<size_t>(vertices),false));
        for (int a=0;a<vertices;++a) {
            if (!vertex_ok[a]) continue;
            for (int b=a+1;b<vertices;++b) {
                if (!vertex_ok[b]) continue;
                bool edge=true;
                for (int k=0;k<3;++k) {
                    std::vector<int> clause={-(3*a+k+1),-(3*b+k+1)};
                    std::sort(clause.begin(),clause.end());
                    if (!known.count(clause)) {edge=false; break;}
                }
                adjacency[a][b]=adjacency[b][a]=edge;
            }
            if ((a&7)==0 && ms()>=math_guard2_budget_ms_) {
                st.math_guard2_budget_hit=true;
                st.math_guard2_wall_ms=ms();
                return;
            }
        }
        // Certificate clauses, independently checked at build time.
        // Every clause is the binary resolvent of earlier/original clauses.
        // This vector is generated from diamond_proof.json.
        static const std::vector<std::vector<int>> proof_steps={
            // MATH_GUARD2_CERTIFICATE_STEPS
        };
        std::set<std::pair<int,int>> done;
        bool stop=false;
        for (int a=0;a<vertices&&!stop;++a) for (int b=a+1;b<vertices&&!stop;++b) {
            if (!adjacency[a][b]) continue;
            std::vector<int> common;
            for (int c=0;c<vertices;++c) {
                if (c!=a&&c!=b&&adjacency[a][c]&&adjacency[b][c]) common.push_back(c);
            }
            for (size_t i=0;i<common.size()&&!stop;++i)
                for (size_t j=i+1;j<common.size()&&!stop;++j) {
                    if (ms()>=math_guard2_budget_ms_ ||
                        st.math_guard2_diamonds>=32 ||
                        st.math_guard2_lemmas>=960) {
                        st.math_guard2_budget_hit=ms()>=math_guard2_budget_ms_;
                        stop=true;break;
                    }
                    const int c=common[i],d=common[j];
                    if (!done.insert({c,d}).second) continue;
                    const int mapping[4]={a,b,c,d};
                    ++st.math_guard2_diamonds;
                    for (const auto& templ:proof_steps) {
                        std::vector<int> learned;
                        learned.reserve(templ.size());
                        for (int lit:templ) {
                            const int index=(std::abs(lit)-1)/3;
                            const int color=(std::abs(lit)-1)%3;
                            const int mapped=3*mapping[index]+color+1;
                            learned.push_back(lit<0?-mapped:mapped);
                        }
                        std::sort(learned.begin(),learned.end());
                        if (!known.insert(learned).second) continue;
                        if (learned.size()==2) ++st.math_guard2_binary;
                        storeClause(std::move(learned),true);
                        ++st.math_guard2_lemmas;
                    }
                }
        }
        st.math_guard2_wall_ms=ms();
    }
