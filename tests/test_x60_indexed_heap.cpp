// X6.0 indexed VSIDS invariant and identical ordering stress test.
// Runs without any benchmark source, solver binary, or holdout access.
#include "../src/drnas_x60_indexed_heap.hpp"
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <random>
#include <stdexcept>
#include <vector>

int main() {
    constexpr int N=96;
    std::mt19937_64 rng(6031415);
    std::vector<int8_t> assigned(N,0);
    std::vector<double> activity(N,0.0), base(N,0.0);
    drnas::IndexedVSIDSHeap heap;
    heap.reset(N);
    auto higher=[&](int a,int b) {
        const double sa=activity[a]+base[a], sb=activity[b]+base[b];
        return sa != sb ? sa>sb : a<b;
    };
    for(int i=0;i<N;++i) {
        base[i]=(i%9)*0.03125;
        heap.offer(i,higher);
    }
    uint64_t comparisons=0;
    for (int step=0;step<30000;++step) {
        const int v=static_cast<int>(rng()%N);
        const int op=static_cast<int>(rng()%9);
        if (op<=3) {
            activity[v]+=static_cast<double>(rng()%100)/8.0;
            if (!assigned[v]) heap.offer(v,higher);
        } else if (op==4) {
            assigned[v]=1;
            heap.erase(v,higher);
        } else if (op==5) {
            assigned[v]=0;
            heap.offer(v,higher);
        } else if (op==6) {
            for(double& x:activity) x*=0.0001;
            heap.rebuild(assigned,higher);
        } else if (op==7) {
            // Already-indexed key updates must not create duplicates.
            if (!assigned[v]) heap.offer(v,higher);
        }
        heap.verify(assigned,higher);
        std::vector<int> expected;
        for(int i=0;i<N;++i) if(!assigned[i])expected.push_back(i);
        std::sort(expected.begin(),expected.end(),higher);
        const auto top=heap.topK(3,higher);
        const size_t take=std::min<size_t>(3,expected.size());
        if(top.size()!=take || !std::equal(top.begin(),top.end(),expected.begin()))
            throw std::runtime_error("indexed topK disagrees with frozen score/tie-order");
        heap.verify(assigned,higher);
        comparisons+=take;
        if(step==1000) {
            const auto copy=heap;
            heap.reset(N);
            heap.rebuild(assigned,higher);
            heap.verify(assigned,higher);
            const auto rebuilt=heap.topK(3,higher);
            const auto cloned=copy.topK(3,higher);
            if(rebuilt!=cloned)
                throw std::runtime_error("copy or heapify is not deterministic");
        }
    }
    if(heap.size()>N) throw std::runtime_error("duplicate heap entries");
    std::cout<<"X60_INDEXED_HEAP_INVARIANT_PASS steps=30000 comparisons="
             <<comparisons<<" peak="<<heap.peak()<<"\n";
    return 0;
}
