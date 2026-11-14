// PG14: one-process, proof-first, bounded congruence preprocessing.
// This file is included INSIDE class Solver in the generated experimental
// CF6-derived C++ source. No second solver, no main branch changes.
//
// Only logically implied binary clauses are added to the ORIGINAL formula.
// Their DRAT/RUP validity is independently checked on original CNFs.
// No source clause deletion, no variable substitution, no SAT reconstruction.
// Gate pattern: (o | -a | -b) & (-o | a) & (-o | b) => o <-> (a & b).
void configurePG14(bool enabled) { pg14_enabled_ = enabled; }
void preprocessPG14() {
    if(!pg14_enabled_)return;
    const auto started=Clock::now();
    auto seconds=[&](){return std::chrono::duration<double>(Clock::now()-started).count();};
    const double budget_s=std::min(0.35,std::max(0.06,timeout_s_*0.03));
    int64_t root_assigned=static_cast<int64_t>(trail_.size());
    int64_t binary_count=0,gate_patterns=0,gate_matches=0;
    int64_t original_equivalences=0,gate_equalities=0,added_clauses=0;
    int rounds=0;
    const char* state="completed";
    // Guard prevents large-scale heap allocation and high preprocessing cost.
    if(n_<=0 || n_>200000 || original_count_>500000 || timedOut()) {
        state="skipped_size_or_time";
        std::cerr<<"PG14_PREPROCESS {\"state\":\""<<state<<"\",\"root_assigned\":"
                 <<root_assigned<<",\"nvars\":"<<n_<<",\"clauses\":"<<original_count_
                 <<",\"time_s\":"<<seconds()<<"}\n";
        return;
    }
    struct DSU {
        std::vector<int> p;
        std::vector<unsigned char> rk;
        explicit DSU(int n):p(static_cast<size_t>(n)),rk(static_cast<size_t>(n),0){
            std::iota(p.begin(),p.end(),0);
        }
        int find(int x){
            while(p[static_cast<size_t>(x)]!=x){
                p[static_cast<size_t>(x)]=p[static_cast<size_t>(p[static_cast<size_t>(x)])];
                x=p[static_cast<size_t>(x)];
            }
            return x;
        }
        bool unite(int x,int y){
            x=find(x);y=find(y);
            if(x==y)return false;
            if(rk[static_cast<size_t>(x)]<rk[static_cast<size_t>(y)])std::swap(x,y);
            p[static_cast<size_t>(y)]=x;
            if(rk[static_cast<size_t>(x)]==rk[static_cast<size_t>(y)])
                ++rk[static_cast<size_t>(x)];
            return true;
        }
    };
    const int nodes=2*n_;
    DSU dsu(nodes);
    // Original binary implication graph and its reverse, for exact SCCs.
    std::vector<std::vector<int>> edges(static_cast<size_t>(nodes));
    std::vector<std::vector<int>> reverse(static_cast<size_t>(nodes));
    for(int u=0;u<nodes;++u){
        for(const auto& edge:binary_implications_[static_cast<size_t>(u)]){
            int v=static_cast<int>(litIndex(edge.first));
            edges[static_cast<size_t>(u)].push_back(v);
            reverse[static_cast<size_t>(v)].push_back(u);
            ++binary_count;
        }
    }
    std::vector<unsigned char> visited(static_cast<size_t>(nodes),0);
    std::vector<size_t> next(static_cast<size_t>(nodes),0);
    std::vector<int> order;
    order.reserve(static_cast<size_t>(nodes));
    std::vector<int> stack;
    for(int root=0;root<nodes;++root){
        if(visited[static_cast<size_t>(root)])continue;
        visited[static_cast<size_t>(root)]=1;
        stack.push_back(root);
        while(!stack.empty()){
            int u=stack.back();
            size_t& at=next[static_cast<size_t>(u)];
            auto& adj=edges[static_cast<size_t>(u)];
            if(at<adj.size()){
                int v=adj[at++];
                if(!visited[static_cast<size_t>(v)]){
                    visited[static_cast<size_t>(v)]=1;
                    stack.push_back(v);
                }
            }else{
                order.push_back(u);
                stack.pop_back();
            }
        }
    }
    std::vector<int> component(static_cast<size_t>(nodes),-1);
    std::vector<int> leader;
    for(auto it=order.rbegin();it!=order.rend();++it){
        int root=*it;
        if(component[static_cast<size_t>(root)]>=0)continue;
        int c=static_cast<int>(leader.size());
        leader.push_back(root);
        component[static_cast<size_t>(root)]=c;
        stack.push_back(root);
        while(!stack.empty()){
            int u=stack.back();stack.pop_back();
            for(int v:reverse[static_cast<size_t>(u)]){
                if(component[static_cast<size_t>(v)]>=0)continue;
                component[static_cast<size_t>(v)]=c;
                stack.push_back(v);
            }
        }
    }
    for(int v=0;v<n_;++v){
        if(component[static_cast<size_t>(2*v)]==
           component[static_cast<size_t>(2*v+1)]){
            // Binary 2-SAT contradiction. Both unit clauses are RUP via
            // implication paths, followed by the final empty clause.
            storeClause({v+1},true);
            storeClause({-(v+1)},true);
            root_unsat_=true;
            state="binary_unsat";
            added_clauses=2;
            std::cerr<<"PG14_PREPROCESS {\"state\":\""<<state
                     <<"\",\"nvars\":"<<n_<<",\"root_assigned\":"<<root_assigned
                     <<",\"added_clauses\":2,\"time_s\":"<<seconds()<<"}\n";
            return;
        }
    }
    for(int i=0;i<nodes;++i){
        int other=leader[static_cast<size_t>(component[static_cast<size_t>(i)])];
        if(dsu.unite(i,other))++original_equivalences;
        dsu.unite(i^1,other^1);
    }
    // Encode each binary clause only once, preserving literal signs.
    auto pairkey=[&](int a,int b)->uint64_t{
        if(a>b)std::swap(a,b);
        return (static_cast<uint64_t>(static_cast<uint32_t>(a+n_))<<32) |
               static_cast<uint32_t>(b+n_);
    };
    std::unordered_set<uint64_t> bins;
    bins.reserve(static_cast<size_t>(std::max<int64_t>(16,binary_count)));
    for(int cid=0;cid<original_count_;++cid){
        const auto& c=clauses_[static_cast<size_t>(cid)].lits;
        if(c.size()==2)bins.insert(pairkey(c[0],c[1]));
    }
    struct Gate{int output;int a;int b;};
    std::vector<Gate> gates;
    gates.reserve(static_cast<size_t>(original_count_/3));
    for(int cid=0;cid<original_count_;++cid){
        if((cid&2047)==0 && (seconds()>budget_s || timedOut())){
            state="budget_exhausted_extract";break;
        }
        const auto& c=clauses_[static_cast<size_t>(cid)].lits;
        if(c.size()!=3)continue;
        for(int j=0;j<3;++j){
            int out=c[static_cast<size_t>(j)];
            int a=-c[static_cast<size_t>((j+1)%3)];
            int b=-c[static_cast<size_t>((j+2)%3)];
            if(a==b || a==-b || a==out || b==out)continue;
            if(bins.count(pairkey(-out,a)) && bins.count(pairkey(-out,b))){
                gates.push_back({out,a,b});
                ++gate_patterns;
            }
        }
    }
    // No modification if there is no gate/congruence to exploit.
    if(state[0]!='b' || std::string(state)=="completed"){
        for(int round=0;round<5;++round){
            if(seconds()>budget_s || timedOut()){state="budget_exhausted_round";break;}
            std::unordered_map<uint64_t,int> first;
            first.reserve(gates.size()*2+1);
            int round_new=0;
            for(size_t j=0;j<gates.size();++j){
                if((j&2047u)==0 && (seconds()>budget_s || timedOut())){
                    state="budget_exhausted_round";break;
                }
                const auto& gate=gates[j];
                int a=dsu.find(static_cast<int>(litIndex(gate.a)));
                int b=dsu.find(static_cast<int>(litIndex(gate.b)));
                if(a>b)std::swap(a,b);
                uint64_t signature=(static_cast<uint64_t>(static_cast<uint32_t>(a))<<32) |
                                    static_cast<uint32_t>(b);
                auto it=first.find(signature);
                if(it==first.end()){first.emplace(signature,gate.output);continue;}
                int other=it->second;
                int o=gate.output;
                int O=dsu.find(static_cast<int>(litIndex(o)));
                int P=dsu.find(static_cast<int>(litIndex(other)));
                if(O==P)continue;
                ++gate_matches;
                if(O==dsu.find(static_cast<int>(litIndex(-other)))){
                    // Two opposite literals provably equal => UNSAT.
                    storeClause({o},true);
                    storeClause({-o},true);
                    root_unsat_=true;
                    added_clauses+=2;
                    state="gate_unsat";
                    break;
                }
                // Each direction is a valid RUP clause from gate encoding
                // plus previously derived equivalence clauses.
                storeClause({-o,other},true);
                storeClause({o,-other},true);
                added_clauses+=2;
                ++gate_equalities;
                ++round_new;
                dsu.unite(static_cast<int>(litIndex(o)),
                          static_cast<int>(litIndex(other)));
                dsu.unite(static_cast<int>(litIndex(-o)),
                          static_cast<int>(litIndex(-other)));
                if(gate_equalities>=50000){
                    state="equality_limit";break;
                }
            }
            ++rounds;
            if(root_unsat_ || round_new==0 || std::string(state)!="completed")break;
        }
    }
    // New implied binary clauses must propagate against existing root units.
    // No deletion, variable elimination, model rewrite, or extra decision.
    if(added_clauses)qhead_=0;
    std::cerr<<"PG14_PREPROCESS {\"state\":\""<<state
             <<"\",\"nvars\":"<<n_<<",\"clauses\":"<<original_count_
             <<",\"root_assigned\":"<<root_assigned
             <<",\"binary_edges\":"<<binary_count
             <<",\"scc_equivalence_links\":"<<original_equivalences
             <<",\"and_gate_patterns\":"<<gate_patterns
             <<",\"matched_gates\":"<<gate_matches
             <<",\"gate_equalities\":"<<gate_equalities
             <<",\"added_clauses\":"<<added_clauses
             <<",\"rounds\":"<<rounds
             <<",\"time_s\":"<<seconds()<<"}\n";
}
