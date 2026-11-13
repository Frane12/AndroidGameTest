#include "../src/drnas_gate_r2.hpp"
#include "../build/drnas_gate_r3.hpp"
#include <cassert>
#include <iostream>
#include <random>
#include <sstream>
using drnas::GateR2;
using drnas::GateR3;
template<class Gate> static int64_t observe(Gate& g, bool useful, int64_t conflicts=0) {
    const auto d=g.next();
    assert(g.due(d,conflicts,true));
    assert(g.affordable(d,conflicts,0.1,10.0,0.0,true));
    g.cost(0.000020,0.1,0.000020);
    g.feedback(useful,d+1);
    return d;
}
int main() {
    GateR2 old;
    GateR3 strict, off(true);
    int64_t last=0;
    for(int i=0;i<4;++i){
        last=observe(old,false);assert(observe(strict,false)==last);
        assert(observe(off,false)==last);
    }
    assert(old.state()==GateR2::State::Sleep);
    assert(strict.state()==GateR3::State::Sleep);
    assert(off.state()==GateR3::State::Sleep);
    const auto periodic=strict.next();
    assert(old.due(last+256,128,true));
    assert(!strict.due(last+256,128,true));
    assert(!strict.due(last+1023,512,true));
    assert(!strict.due(last+1024,511,true));
    assert(strict.due(last+1024,512,true));
    assert(strict.affordable(last+1024,512,.1,10.,0.,true));
    assert(strict.counters().shock_wakes==1);
    assert(strict.state()==GateR3::State::Check); // never directly ACTIVE
    assert(!off.due(last+1024,100000,true));
    assert(off.due(periodic,100000,true));
    assert(off.affordable(periodic,100000,.1,10.,0.,true));
    assert(off.counters().periodic_wakes==1 && off.counters().shock_wakes==0);

    GateR3 denied;
    for(int i=0;i<4;++i)last=observe(denied,false);
    const auto d=last+1024;
    assert(denied.due(d,512,true));
    assert(!denied.affordable(d,512,.01,1.,.01,true));
    assert(denied.state()==GateR3::State::Sleep);
    assert(denied.counters().shock_wakes==0);
    for(int k=1;k<192;++k)assert(!denied.due(d+k,100000,true));
    assert(denied.due(d+192,100000,true));
    assert(!denied.affordable(d+192,100000,.81,1.,0.,true));

    // With no conflict shocks, R2/R3/NO_SHOCK must have identical states,
    // feedback and schedules. This is the one-change isolation regression.
    std::mt19937 random(463031);
    for(int episode=0;episode<100;++episode){
        GateR2 a;GateR3 b,c(true);
        for(int t=0;t<100;++t){
            const bool good=(random()%100)<static_cast<unsigned>(episode);
            assert(a.next()==b.next() && b.next()==c.next());
            observe(a,good);observe(b,good);observe(c,good);
            assert(static_cast<int>(a.state())==static_cast<int>(b.state()));
            assert(static_cast<int>(b.state())==static_cast<int>(c.state()));
            assert(a.usefulness()==b.usefulness() && b.usefulness()==c.usefulness());
            assert(a.counters().permits==b.counters().permits);
            assert(a.counters().switches==b.counters().switches);
            assert(b.counters().switches==c.counters().switches);
        }
    }
    std::ostringstream json;off.write(json);
    assert(json.str().find("\"conflict_wake_disabled\":true")!=std::string::npos);
    std::cout<<"GATER3_CONTROLLER_TEST_PASS boundaries=4x,disabled,periodic,budget,timeout no_shock_equivalence_events=10000\n";
}
