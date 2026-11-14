        // GUARD3: only activate expensive proof emission when a chain of
        // mathematically forced colour equalities contradicts an actual edge.
        // This is a sufficient UNSAT signal, NEVER a heuristic branch ban.
        // For any two triangles sharing an edge, their opposite vertices have
        // the same colour in every proper 3-colouring. Collect such equalities,
        // then seek an actual edge joining vertices in one equality component.
        std::set<std::pair<int,int>> selected_pairs;
        if (math_guard3_enabled_) {
            struct Equality {
                int c, d, a, b;
            };
            std::vector<Equality> equalities;
            std::set<std::pair<int,int>> equality_seen;
            bool gate_budget=false;
            for (int a=0; a<vertices && !gate_budget; ++a) {
                for (int b=a+1; b<vertices && !gate_budget; ++b) {
                    if (!adjacency[a][b]) continue;
                    std::vector<int> common;
                    for (int c=0; c<vertices; ++c)
                        if (c!=a && c!=b && adjacency[a][c] && adjacency[b][c])
                            common.push_back(c);
                    for (size_t i=0; i<common.size() && !gate_budget; ++i) {
                        for (size_t j=i+1; j<common.size(); ++j) {
                            const int c=common[i], d=common[j];
                            if (equality_seen.insert({c,d}).second)
                                equalities.push_back({c,d,a,b});
                            if ((equalities.size() & 63)==0 &&
                                ms()>=math_guard2_budget_ms_*0.65) {
                                gate_budget=true;
                                break;
                            }
                        }
                    }
                }
            }
            st.math_guard3_equalities=static_cast<int64_t>(equalities.size());
            if (gate_budget || equalities.empty()) {
                st.math_guard2_budget_hit=gate_budget;
                st.math_guard2_wall_ms=ms();
                return;
            }
            std::vector<int> uf(static_cast<size_t>(vertices));
            for (int i=0;i<vertices;++i) uf[i]=i;
            const auto root=[&](int x) {
                while (uf[x]!=x) {uf[x]=uf[uf[x]];x=uf[x];}
                return x;
            };
            std::vector<std::vector<std::pair<int,int>>> link(
                static_cast<size_t>(vertices));
            for (size_t i=0;i<equalities.size();++i) {
                const auto& e=equalities[i];
                int x=root(e.c), y=root(e.d);
                if (x!=y) uf[x]=y;
                link[e.c].push_back({e.d,static_cast<int>(i)});
                link[e.d].push_back({e.c,static_cast<int>(i)});
            }
            bool found=false;
            for (int u=0;u<vertices && !found && !gate_budget;++u)
                for (int v=u+1;v<vertices && !found && !gate_budget;++v) {
                    if (!adjacency[u][v] || root(u)!=root(v)) continue;
                    ++st.math_guard3_candidate_edges;
                    std::vector<int> pred(static_cast<size_t>(vertices),-1);
                    std::vector<int> pred_edge(static_cast<size_t>(vertices),-1);
                    std::queue<int> q;
                    pred[u]=u;q.push(u);
                    while (!q.empty() && pred[v]<0) {
                        int x=q.front();q.pop();
                        for (const auto& [y,id]:link[x]) {
                            if (pred[y]>=0) continue;
                            pred[y]=x; pred_edge[y]=id;
                            q.push(y);
                        }
                    }
                    if (pred[v]<0) throw std::runtime_error("GUARD3 union-find path mismatch");
                    std::vector<int> path;
                    for (int x=v;x!=u;x=pred[x]) path.push_back(pred_edge[x]);
                    // A cheap 1- or 2-diamond conflict rarely repays its
                    // proof-engine overhead; use the precommitted threshold.
                    if (path.size()>=3 && path.size()<=32) {
                        for (int id:path) {
                            const auto& e=equalities[static_cast<size_t>(id)];
                            selected_pairs.insert({e.c,e.d});
                        }
                        found=true;
                        st.math_guard3_triggered=true;
                        st.math_guard3_path_len=static_cast<int64_t>(path.size());
                    }
                    if ((st.math_guard3_candidate_edges&15)==0 &&
                        ms()>=math_guard2_budget_ms_*0.80) gate_budget=true;
                }
            if (gate_budget || !found) {
                st.math_guard2_budget_hit=gate_budget;
                st.math_guard2_wall_ms=ms();
                return;
            }
        }
