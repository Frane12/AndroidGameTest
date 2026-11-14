// Experimental domain guard for exact independent-transversal SAT subclass.
// No UNSAT inference: on any mismatch or failure, fall back to original CDCL.
// This header is included only by the experiment-specific generated X5 clone.

struct WorkerDomainAnswer {
    bool eligible = false;
    bool solved = false;
    bool exhausted = false;
    int64_t nodes = 0;
    double elapsed_ms = 0.0;
    const char* reason = "not_checked";
    std::vector<int8_t> model;
};

static WorkerDomainAnswer tryWorkerDomainSAT(
    int n, const std::vector<std::vector<int>>& originals, double budget_ms) {
    WorkerDomainAnswer a;
    const auto start = Clock::now();
    const auto finish = [&]() {
        a.elapsed_ms = std::chrono::duration<double,std::milli>(Clock::now()-start).count();
        return a;
    };
    if (n < 1 || n > 2500 || originals.empty() || originals.size() > 100000 ||
        budget_ms <= 0.0) {
        a.reason = "size_or_budget_gate"; return finish();
    }
    const auto deadline = start + std::chrono::duration_cast<Clock::duration>(
        std::chrono::duration<double,std::milli>(budget_ms));
    std::vector<std::vector<int>> groups;
    std::vector<std::pair<int,int>> exclusions;
    groups.reserve(48);
    for (const auto& clause : originals) {
        // Every clause must be either a positive choice or a negative pair.
        if (clause.size() >= 3 && clause.size() <= 128 &&
            std::all_of(clause.begin(),clause.end(),[](int x){return x>0;})) {
            groups.push_back(clause);
            if (groups.size() > 48) {
                a.reason = "too_many_groups"; return finish();
            }
        } else if (clause.size()==2 && clause[0]<0 && clause[1]<0 &&
                   clause[0]!=clause[1]) {
            exclusions.emplace_back(-clause[0],-clause[1]);
        } else {
            a.reason = "different_clause_signature"; return finish();
        }
    }
    if (groups.size()<2 || exclusions.empty()) {
        a.reason = "no_groups_or_exclusions"; return finish();
    }
    std::vector<int> owner(static_cast<size_t>(n)+1, -1);
    int candidates = 0;
    for (size_t g=0;g<groups.size();++g) {
        for (int v:groups[g]) {
            if (v<1 || v>n || owner[static_cast<size_t>(v)]>=0) {
                a.reason = "overlapping_or_bad_groups"; return finish();
            }
            owner[static_cast<size_t>(v)]=static_cast<int>(g);
            ++candidates;
        }
    }
    if (candidates>2500) {a.reason="too_many_candidates";return finish();}
    a.eligible=true;
    // Exclusions on variables outside all positive clauses are irrelevant:
    // those variables can be set FALSE in any SAT witness of this class.
    const size_t pitch=static_cast<size_t>(n)+1;
    std::vector<uint8_t> banned(pitch*pitch,0);
    for (const auto& [x,y]:exclusions) {
        if (owner[x]>=0 && owner[y]>=0) {
            banned[static_cast<size_t>(x)*pitch+y]=1;
            banned[static_cast<size_t>(y)*pitch+x]=1;
        }
    }
    auto conflicts=[&](int x,int y) {
        return banned[static_cast<size_t>(x)*pitch+static_cast<size_t>(y)]!=0;
    };
    std::vector<int> chosen(groups.size(),-1), winning;
    bool aborted=false;
    std::function<bool(std::vector<std::vector<int>>&,int)> dfs;
    dfs=[&](std::vector<std::vector<int>>& available,int depth)->bool {
        ++a.nodes;
        if(a.nodes>2048 || Clock::now()>=deadline) {
            aborted=true;return false;
        }
        if(depth==static_cast<int>(groups.size())) {
            winning=chosen;return true;
        }
        int pivot=-1;
        size_t smallest=static_cast<size_t>(-1);
        for (size_t g=0;g<available.size();++g) {
            if(chosen[g]>=0)continue;
            if(available[g].empty())return false;
            if(available[g].size()<smallest) {
                smallest=available[g].size();pivot=static_cast<int>(g);
            }
        }
        if(pivot<0)return false;
        std::vector<std::pair<int,int>> ranking;
        ranking.reserve(available[static_cast<size_t>(pivot)].size());
        for(int v:available[static_cast<size_t>(pivot)]) {
            int impact=0;
            for(size_t h=0;h<available.size();++h) {
                if(static_cast<int>(h)==pivot || chosen[h]>=0)continue;
                for(int w:available[h])impact+=conflicts(v,w);
            }
            ranking.emplace_back(impact,v);
        }
        std::sort(ranking.begin(),ranking.end());
        for (const auto& [impact,v]:ranking) {
            (void)impact;
            if(Clock::now()>=deadline){aborted=true;return false;}
            chosen[static_cast<size_t>(pivot)]=v;
            std::vector<std::vector<int>> next=available;
            bool viable=true;
            for(size_t h=0;h<available.size();++h) {
                if(chosen[h]>=0)continue;
                auto& opts=next[h];
                opts.erase(std::remove_if(opts.begin(),opts.end(),
                    [&](int w){return conflicts(v,w);}),opts.end());
                if(opts.empty()){viable=false;break;}
            }
            if(viable && dfs(next,depth+1))return true;
            chosen[static_cast<size_t>(pivot)]=-1;
            if(aborted)return false;
        }
        return false;
    };
    if (Clock::now()>=deadline) {
        a.reason="budget_exhausted";a.exhausted=true;return finish();
    }
    std::vector<std::vector<int>> available=groups;
    const bool found=dfs(available,0);
    a.exhausted=aborted;
    if(!found) {
        a.reason=aborted?"budget_exhausted":"no_witness_bounded";
        return finish();
    }
    // Verify every original clause, not merely the detected choice groups.
    a.model.assign(static_cast<size_t>(n)+1,static_cast<int8_t>(-1));
    for(int v:winning) {
        if(v<1 || v>n)throw std::runtime_error("domain guard witness out of range");
        a.model[static_cast<size_t>(v)]=1;
    }
    for(const auto& clause:originals) {
        bool satisfied=false;
        for(int lit:clause) {
            if(a.model[static_cast<size_t>(std::abs(lit))]==(lit>0?1:-1)) {
                satisfied=true;break;
            }
        }
        if(!satisfied)throw std::runtime_error("domain guard produced invalid original CNF witness");
    }
    a.solved=true;a.reason="original_cnf_sat_witness_verified";
    return finish();
}
