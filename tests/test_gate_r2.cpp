#include "../src/drnas_gate_r2.hpp"
#include <cassert>
#include <iostream>
#include <limits>
#include <random>
using drnas::GateR2;
static void observe(GateR2& g,bool useful,bool adaptive=true,int64_t conflict=0) {
    auto d=g.next();
    assert(g.due(d,conflict,adaptive));
    assert(g.affordable(d,conflict,0.1,10.0,0.0,adaptive));
    g.cost(0.000020,0.1,0.000020);
    g.feedback(useful,d+1);
}
int main() {
    GateR2 g;
    for (int i=0;i<64;++i) assert(!g.due(i,0,true));
    for (int i=0;i<3;++i) {observe(g,true);assert(g.state()==GateR2::State::Check);}
    observe(g,true);assert(g.state()==GateR2::State::Active);
    // Mid-band feedback must not immediately chatter out of ACTIVE.
    observe(g,false);assert(g.state()==GateR2::State::Active);
    for (int i=0;i<8;++i) {observe(g,false);if(g.state()==GateR2::State::Sleep)break;}
    assert(g.state()==GateR2::State::Sleep);
    const auto switches=g.counters().switches;
    // A conflict wake cannot bypass the cost check or change state on denial.
    assert(g.due(g.next(),1000,true));
    assert(!g.affordable(g.next(),1000,0.01,1.0,0.01,true));
    assert(g.state()==GateR2::State::Sleep);
    assert(g.counters().switches==switches);
    assert(!g.affordable(g.next(),1000,0.81,1.0,0.0,true));
    // Successful periodic checking and forgetting after sleep.
    observe(g,true);assert(g.state()==GateR2::State::Check);
    assert(g.counters().decay_events==1);
    assert(g.counters().check_entries==1);
    for(int i=0;i<4;++i)observe(g,true);
    assert(g.state()==GateR2::State::Active);

    GateR2 fixed;
    int64_t previous=64;
    for(int i=0;i<20;++i) {
        observe(fixed,i%3!=0,false);
        assert(fixed.next()==previous+192);
        previous=fixed.next();
    }
    assert(fixed.counters().switches==0);
    GateR2 budget;
    assert(budget.due(64,0,true));
    assert(budget.affordable(64,0,0.0001,1.,0.,true));
    budget.cost(0.001,0.0011,0.001);
    assert(!budget.affordable(192,200,0.002,1.,0.001,true));
    bool threw=false;
    try {budget.cost(std::numeric_limits<double>::quiet_NaN(),0.,0.);}catch(const std::runtime_error&){threw=true;}
    assert(threw);
    // Many deterministic synthetic sequences test the controller's lifecycle.
    std::mt19937 rng(460702);
    for(int episode=0;episode<100;++episode){
        GateR2 f;
        for(int t=0;t<100;++t){
            const auto before=f.counters().switches;
            observe(f,(rng()%100)<static_cast<unsigned>(episode));
            assert(f.usefulness()>=0.0 && f.usefulness()<=1.0);
            assert(f.counters().switches<=before+1);
        }
    }
    std::cout<<"GATER2_CONTROLLER_TEST_PASS scenarios=budget,hysteresis,dwell,wake,forgetting,fixed,fuzz\n";
}
