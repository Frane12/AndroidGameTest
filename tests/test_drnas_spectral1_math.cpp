#include "../src/drnas_spectral1.hpp"
#include <cassert>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>

int main() {
    using drnas_spectral1::analyze;
    {
        // x1 xor x2 xor x3 = 0 encoded exactly by four CNF clauses.
        const std::vector<int> vars={1,2,3};
        const std::vector<std::vector<int>> cnf={
            {-1,2,3},{1,-2,3},{1,2,-3},{-1,-2,-3}
        };
        const auto a=analyze(vars,cnf);
        assert(a.feasible_assignments==4);
        assert(a.support_rank==1);
        assert(a.nonzero_coefficients==1);
        assert(a.nonlinear_coefficients==1);
        assert(a.walsh[0]==4 && a.walsh[7]==4);
        assert(a.nonlinear_energy==16 && a.nonconstant_energy==16);
        assert(a.laplacian_energy==96);
        for(int s=1;s<7;++s)assert(a.walsh[static_cast<size_t>(s)]==0);
        for(double value:a.nonlinear_influence)assert(std::fabs(value-1.0)<1e-15);
    }
    {
        // One OR constraint has full 3-dimensional spectral support.
        const auto a=analyze({1,2,3},{{1,2,3}});
        assert(a.feasible_assignments==7);
        assert(a.support_rank==3);
        assert(a.nonzero_coefficients==7);
        assert(a.nonconstant_energy==7);
        assert(a.nonlinear_coefficients==4);
        assert(a.laplacian_energy==24);
    }
    {
        // Constant satisfiable indicator: no nonzero frequencies.
        const auto a=analyze({1,2},{});
        assert(a.feasible_assignments==4 && a.support_rank==0);
        assert(a.nonconstant_energy==0 && a.nonlinear_energy==0);
    }
    {
        // Contradiction has zero spectrum: do not mistake zero for SAT.
        const auto a=analyze({1,2},{{1},{-1}});
        assert(a.feasible_assignments==0 && a.support_rank==0);
        for(int c:a.walsh)assert(c==0);
    }
    {
        // The analyzer must reject invalid local scopes.
        bool rejected=false;
        try{analyze({1,2},{{3}});}
        catch(const std::invalid_argument&){rejected=true;}
        assert(rejected);
    }
    std::cout<<"SPECTRAL1_MATH_PASS {\"parity_rank\":1,\"parity_feasible\":4,"
                "\"or_rank\":3,\"or_feasible\":7,\"integer_walsh\":true,"
                "\"no_unchecked_unsat\":true}\n";
}