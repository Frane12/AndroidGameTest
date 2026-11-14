    // DELTAX-SIGNAL1: a SOURCE-BLIND, cheap measure of the structural
    // implication reach of a proposed, already source-RUP certified clause.
    // No graph labels, known answers, training-set IDs or SAT/UNSAT outcomes.
    // Computation is observational; it cannot enqueue literals or alter CDCL.
    int64_t deltax_signal_candidates_=0, deltax_signal_passed_=0;
    int64_t deltax_signal_rejected_=0, deltax_signal_event_logs_=0;
    int64_t deltax_signal_sum_reach_=0;
    static constexpr int deltax_signal_depth_=3;
    static constexpr int deltax_signal_node_budget_=160;

    int deltaxSignalThreshold()const {
        const std::string& mode=coop_.join_mode;
        if(mode.rfind("deltax-signal-",0)!=0)return -1;
        const std::string suffix=mode.substr(14);
        if(suffix.empty() || suffix.size()>2 ||
           !std::all_of(suffix.begin(),suffix.end(),
                        [](char c){return c>='0' && c<='9';}))
            throw std::runtime_error("DELTAX_SIGNAL_BAD_THRESHOLD");
        const int value=std::stoi(suffix);
        if(value>63)throw std::runtime_error("DELTAX_SIGNAL_THRESHOLD_TOO_HIGH");
        return value;
    }

    struct DeltaxSignalFeature {
        int binary_reach=0, unassigned_reach=0, original_binary_edges=0;
    };
    DeltaxSignalFeature deltaxSignalFeatures(const std::vector<int>& clause)const {
        DeltaxSignalFeature f;
        // A bounded BFS in the ORIGINAL binary implication graph starting
        // at both signs of each currently unassigned non-guard endpoint.
        // The guard is the currently FALSE literal; no assumption is made
        // that the CNF describes graph coloring.
        if(n_>4096)return f;
        std::vector<uint8_t> seen_lit(2*static_cast<size_t>(n_),0);
        std::vector<uint8_t> seen_var(static_cast<size_t>(n_),0);
        struct Node{int lit,depth;};
        std::vector<Node> work;
        work.reserve(deltax_signal_node_budget_);
        for(int lit:clause)if(value(lit)==0){
            for(int polarity:{-1,1}) {
                int start=std::abs(lit)*polarity;
                const size_t index=static_cast<size_t>(litIndex(start));
                if(!seen_lit[index]){
                    seen_lit[index]=1;
                    work.push_back({start,0});
                }
            }
        }
        size_t cursor=0;
        while(cursor<work.size() && cursor<deltax_signal_node_budget_) {
            const Node next=work[cursor++];
            if(next.depth>=deltax_signal_depth_)continue;
            for(const auto& [implied,cid]:binary_implications_[litIndex(next.lit)]){
                if(cid<0||static_cast<size_t>(cid)>=clauses_.size())
                    throw std::runtime_error("DELTAX_SIGNAL_BAD_BINARY_REASON_INDEX");
                const Clause& source=clauses_[static_cast<size_t>(cid)];
                if(source.learnt || source.deleted || source.lits.size()!=2)continue;
                ++f.original_binary_edges;
                const int var=std::abs(implied)-1;
                if(!seen_var[static_cast<size_t>(var)]){
                    seen_var[static_cast<size_t>(var)]=1;
                    ++f.binary_reach;
                    if(values_[static_cast<size_t>(var)]==0)++f.unassigned_reach;
                }
                const size_t index=static_cast<size_t>(litIndex(implied));
                if(!seen_lit[index] &&
                   work.size()<static_cast<size_t>(deltax_signal_node_budget_)){
                    seen_lit[index]=1;
                    work.push_back({implied,next.depth+1});
                }
            }
        }
        return f;
    }
    bool deltaxSignalPrefilter(const std::vector<int>& c) {
        const int threshold=deltaxSignalThreshold();
        if(threshold<0)return true;
        ++deltax_signal_candidates_;
        const DeltaxSignalFeature f=deltaxSignalFeatures(c);
        // "Reach" is not a proof of usefulness; it is a trainable
        // risk/utility proxy. Only a SOURCE-PROVED clause whose signal
        // passes can enter the existing two-clone GUARD1 check.
        const bool pass=f.unassigned_reach>=threshold;
        deltax_signal_sum_reach_+=f.unassigned_reach;
        if(pass)++deltax_signal_passed_;else ++deltax_signal_rejected_;
        if(deltax_signal_event_logs_<16){
            ++deltax_signal_event_logs_;
            std::cerr<<"DELTAX_SIGNAL_EVENT {\"min_unassigned_reach\":"<<threshold
                     <<",\"reach\":"<<f.binary_reach
                     <<",\"unassigned_reach\":"<<f.unassigned_reach
                     <<",\"original_binary_edges\":"<<f.original_binary_edges
                     <<",\"accepted_by_signal\":"<<(pass?"true":"false")
                     <<"}\n";
        }
        return pass;
    }
    void reportDeltaxSignal()const {
        std::cerr<<"DELTAX_SIGNAL_STATS {\"mode\":\""<<coop_.join_mode
                 <<"\",\"min_reach\":"<<deltaxSignalThreshold()
                 <<",\"tested\":"<<deltax_signal_candidates_
                 <<",\"preapproved\":"<<deltax_signal_passed_
                 <<",\"vetoed\":"<<deltax_signal_rejected_
                 <<",\"sum_unassigned_reach\":"<<deltax_signal_sum_reach_
                 <<",\"max_nodes\":"<<deltax_signal_node_budget_
                 <<",\"max_depth\":"<<deltax_signal_depth_
                 <<"}\n";
    }
