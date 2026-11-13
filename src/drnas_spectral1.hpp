#pragma once
// DRNAS SPECTRAL1: exact local Walsh-Hadamard spectrum over F_2^k, k <= 8.
// Research-only feature: spectrum influences branching, NEVER SAT/UNSAT claims.
// The function f(x)=1 iff all local ORIGINAL CNF clauses are satisfied;
// Walsh coefficient W(s)=sum_x f(x)*(-1)^{s dot x}. No floating-point FFT.
#include <algorithm>
#include <bit>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace drnas_spectral1 {
struct Spectrum {
    int dimension = 0;
    int feasible_assignments = 0;
    int support_rank = 0;
    int nonzero_coefficients = 0;
    int nonlinear_coefficients = 0;
    std::int64_t nonconstant_energy = 0;
    std::int64_t nonlinear_energy = 0;
    std::int64_t laplacian_energy = 0;
    std::vector<double> nonlinear_influence;
    std::vector<int> walsh;  // Exact integer coefficients, local only.
};

// Variable order is arbitrary but MUST be distinct and positive, 2 <= k <= 8.
// Clauses must use ONLY these variables; no labels or external information.
inline Spectrum analyze(const std::vector<int>& variables,
                        const std::vector<std::vector<int>>& clauses) {
    const int k = static_cast<int>(variables.size());
    if (k < 2 || k > 8)
        throw std::invalid_argument("spectral local dimension must be 2..8");
    for (int i=0; i<k; ++i) {
        if (variables[i] <= 0)
            throw std::invalid_argument("invalid spectral variable");
        for (int j=0; j<i; ++j)
            if (variables[j] == variables[i])
                throw std::invalid_argument("duplicate spectral variable");
    }
    struct MaskClause { unsigned pos=0, neg=0; };
    std::vector<MaskClause> prepared;
    prepared.reserve(clauses.size());
    for (const auto& c : clauses) {
        MaskClause out;
        for (int lit : c) {
            int ix = -1;
            for (int j=0; j<k; ++j)
                if (variables[j] == (lit>0 ? lit : -lit)) {ix=j;break;}
            if (ix<0)
                throw std::invalid_argument("spectral clause leaves local scope");
            if (lit>0) out.pos |= (1u << ix);
            else out.neg |= (1u << ix);
        }
        prepared.push_back(out);
    }
    const int count = (1 << k);
    Spectrum result;
    result.dimension=k;
    result.nonlinear_influence.assign(static_cast<size_t>(k),0.0);
    result.walsh.assign(static_cast<size_t>(count),0);
    for (int x=0; x<count; ++x) {
        bool satisfiable=true;
        for (const auto& c : prepared) {
            // Original clause is satisfied by a true positive or false negative.
            if (((static_cast<unsigned>(x) & c.pos) == 0u) &&
                (((~static_cast<unsigned>(x)) & c.neg) == 0u)) {
                satisfiable=false;break;
            }
        }
        if (satisfiable) {
            result.walsh[static_cast<size_t>(x)]=1;
            ++result.feasible_assignments;
        }
    }
    // Integer FWHT, exact: no numerical noise or ambiguous zero threshold.
    for (int len=1;len<count;len*=2) {
        for (int off=0;off<count;off+=2*len) {
            for (int j=0;j<len;++j) {
                const int a=result.walsh[static_cast<size_t>(off+j)];
                const int b=result.walsh[static_cast<size_t>(off+j+len)];
                result.walsh[static_cast<size_t>(off+j)]=a+b;
                result.walsh[static_cast<size_t>(off+j+len)]=a-b;
            }
        }
    }
    // GF(2)-rank of nonzero frequency masks. The local truth function
    // depends on at most 'support_rank' independent XOR coordinates.
    unsigned pivots[8]={0,0,0,0,0,0,0,0};
    std::vector<std::int64_t> influence(static_cast<size_t>(k),0);
    for (int mask=1;mask<count;++mask) {
        const int coefficient=result.walsh[static_cast<size_t>(mask)];
        if (coefficient==0)continue;
        ++result.nonzero_coefficients;
        unsigned residue=static_cast<unsigned>(mask);
        for (int bit=k-1;bit>=0;--bit) {
            if (!(residue & (1u << bit)))continue;
            if (pivots[bit])residue ^= pivots[bit];
            else {pivots[bit]=residue;++result.support_rank;break;}
        }
        const int degree=std::popcount(static_cast<unsigned>(mask));
        const std::int64_t energy=static_cast<std::int64_t>(coefficient)*coefficient;
        result.nonconstant_energy+=energy;
        result.laplacian_energy+=2*degree*energy;
        if (degree>=2) {
            ++result.nonlinear_coefficients;
            result.nonlinear_energy+=energy;
            for (int bit=0;bit<k;++bit)
                if (mask & (1 << bit))influence[static_cast<size_t>(bit)]+=energy;
        }
    }
    if (result.nonlinear_energy>0) {
        for (int i=0;i<k;++i)
            result.nonlinear_influence[static_cast<size_t>(i)]=
                static_cast<double>(influence[static_cast<size_t>(i)])/
                static_cast<double>(result.nonlinear_energy);
    }
    return result;
}
} // namespace drnas_spectral1
