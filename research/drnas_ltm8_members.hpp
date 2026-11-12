    ltm8::Policy ltm8_;
    std::vector<uint8_t> ltm8_seen_;
    mutable std::vector<uint64_t> ltm8_levels_;
    mutable uint64_t ltm8_stamp_=0;
    void ltm8_apply(){decay_=ltm8_.decay;atlas36_quota_pct_=ltm8_.quota;}
    int ltm8_pick(){
        if(heap_.empty())return 0;
        if(ltm8_.random_permil && ltm8_.next()%1000<unsigned(ltm8_.random_permil)){
            ++ltm8_.random_decisions;
            return heap_[ltm8_.next()%heap_.size()];
        }
        return pick_branch_variable();
    }
public:
    void ltm8_enable(bool chaos,uint64_t seed,const CNF& src){
        size_t binary=0,ternary=0;
        for(const auto& c:src.clauses){binary+=c.size()==2;ternary+=c.size()==3;}
        const int bucket=(src.vars>1000?4:0)+(binary*2>src.clauses.size()?1:ternary*4>src.clauses.size()*3?2:0);
        ltm8_.init(chaos,seed,bucket);ltm8_apply();
        ltm8_levels_.assign(size_t(n_)+1,0);
        ltm8_seen_.assign(size_t(n_)+1,0);
        // This controller owns decisions; avoid the old per-decision feedback cost.
        atlas13_c_enabled_=false;
    }
    void ltm8_finish(){
        if(!ltm8_.enabled)return;
        ltm8_.save();
        std::cout<<"LTM8_LEARNING windows="<<ltm8_.windows<<" loaded="<<ltm8_.loaded
                 <<" arm="<<ltm8_.arm<<" random_decisions="<<ltm8_.random_decisions
                 <<" decay="<<ltm8_.decay<<" restart_max="<<ltm8_.restart_max
                 <<" persistent="<<int(!ltm8_.path.empty())<<"\n";
    }
private:
