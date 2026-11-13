// DRNAS X6.0: indexed VSIDS max-heap, comparator supplied by the owning solver.
// No references/pointers into Solver state are stored: speculative Solver copies
// remain independent. This data structure never decides SAT or UNSAT.
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace drnas {
class IndexedVSIDSHeap {
public:
    void reset(int n) {
        if (n < 0) throw std::invalid_argument("negative indexed heap size");
        heap_.clear();
        position_.assign(static_cast<size_t>(n), -1);
        inserts_ = removes_ = updates_ = swaps_ = peak_ = 0;
    }
    size_t size() const { return heap_.size(); }
    uint64_t inserts() const { return inserts_; }
    uint64_t removes() const { return removes_; }
    uint64_t updates() const { return updates_; }
    uint64_t swaps() const { return swaps_; }
    uint64_t peak() const { return peak_; }

    template<class Higher> void offer(int v, Higher higher) {
        checkVar(v);
        int pos = position_[static_cast<size_t>(v)];
        if (pos >= 0) {
            ++updates_;
            repair(static_cast<size_t>(pos), higher);
        } else {
            position_[static_cast<size_t>(v)] = static_cast<int>(heap_.size());
            heap_.push_back(v);
            ++inserts_;
            peak_ = std::max<uint64_t>(peak_, heap_.size());
            siftUp(heap_.size() - 1, higher);
        }
    }

    template<class Higher> void erase(int v, Higher higher) {
        checkVar(v);
        const int old = position_[static_cast<size_t>(v)];
        if (old < 0) return;
        ++removes_;
        const size_t at = static_cast<size_t>(old);
        const int last = heap_.back();
        heap_.pop_back();
        position_[static_cast<size_t>(v)] = -1;
        if (at < heap_.size()) {
            heap_[at] = last;
            position_[static_cast<size_t>(last)] = static_cast<int>(at);
            repair(at, higher);
        }
    }

    // O(n) heapify after the rare global VSIDS activity rescale.
    template<class Higher> void rebuild(const std::vector<int8_t>& values, Higher higher) {
        if (values.size() != position_.size())
            throw std::runtime_error("indexed heap rebuild dimension mismatch");
        heap_.clear();
        std::fill(position_.begin(), position_.end(), -1);
        for (size_t v=0; v<values.size(); ++v) {
            if (values[v] != 0) continue;
            position_[v] = static_cast<int>(heap_.size());
            heap_.push_back(static_cast<int>(v));
        }
        peak_ = std::max<uint64_t>(peak_, heap_.size());
        for (size_t k=heap_.size()/2; k>0; --k)
            siftDown(k-1, higher);
    }

    // Stable highest-score/lowest-index ordering, as in X5 Entry::operator<.
    // Remove/reinsert at most three roots; all membership is restored.
    template<class Higher> std::vector<int> topK(int k, Higher higher) {
        std::vector<int> out;
        if (k <= 0) return out;
        out.reserve(static_cast<size_t>(k));
        while (!heap_.empty() && static_cast<int>(out.size()) < k) {
            const int v = heap_.front();
            erase(v, higher);
            out.push_back(v);
        }
        for (int v : out) offer(v, higher);
        return out;
    }

    // Only used in explicit safety-audit mode, never the performance arm.
    template<class Higher> void verify(const std::vector<int8_t>& values, Higher higher) const {
        if (values.size() != position_.size())
            throw std::runtime_error("indexed heap audit dimensions");
        size_t free_count=0;
        for (size_t v=0; v<values.size(); ++v) {
            const int p=position_[v];
            if (values[v] == 0) {
                ++free_count;
                if (p < 0 || static_cast<size_t>(p) >= heap_.size()
                    || heap_[static_cast<size_t>(p)] != static_cast<int>(v))
                    throw std::runtime_error("indexed heap missing or duplicate free variable");
            } else if (p != -1) {
                throw std::runtime_error("indexed heap contains assigned variable");
            }
        }
        if (heap_.size() != free_count)
            throw std::runtime_error("indexed heap size != free variable count");
        for (size_t k=0; k<heap_.size(); ++k) {
            if (position_[static_cast<size_t>(heap_[k])] != static_cast<int>(k))
                throw std::runtime_error("indexed heap inverse position mismatch");
            if (k && higher(heap_[k], heap_[(k-1)/2]))
                throw std::runtime_error("indexed heap priority order violated");
        }
    }
private:
    std::vector<int> heap_;
    std::vector<int> position_;
    uint64_t inserts_=0, removes_=0, updates_=0, swaps_=0, peak_=0;

    void checkVar(int v) const {
        if (v < 0 || static_cast<size_t>(v) >= position_.size())
            throw std::runtime_error("indexed heap variable out of bounds");
    }
    void swapNodes(size_t a, size_t b) {
        if (a == b) return;
        std::swap(heap_[a], heap_[b]);
        position_[static_cast<size_t>(heap_[a])] = static_cast<int>(a);
        position_[static_cast<size_t>(heap_[b])] = static_cast<int>(b);
        ++swaps_;
    }
    template<class Higher> void siftUp(size_t i, Higher higher) {
        while (i > 0) {
            const size_t p=(i-1)/2;
            if (!higher(heap_[i], heap_[p])) break;
            swapNodes(i,p);
            i=p;
        }
    }
    template<class Higher> void siftDown(size_t i, Higher higher) {
        while (true) {
            const size_t left=2*i+1, right=left+1;
            if (left >= heap_.size()) break;
            size_t best=left;
            if (right < heap_.size() && higher(heap_[right],heap_[left])) best=right;
            if (!higher(heap_[best],heap_[i])) break;
            swapNodes(i,best);
            i=best;
        }
    }
    template<class Higher> void repair(size_t i, Higher higher) {
        if (i && higher(heap_[i], heap_[(i-1)/2]))
            siftUp(i,higher);
        else
            siftDown(i,higher);
    }
};
} // namespace drnas
