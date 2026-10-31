// Single-instance adapter around the EXACT V7.2.1 benchmark implementation.
// Original source is included without changing its selector or CaDiCaL logic.
#define main drnas_v721_original_main
#include "../drnas-sat-v7-2-1/confidence_bench.cpp"
#undef main

int main(int argc, char **argv) {
    try {
        if (argc != 4) {
            std::cerr << "Usage: real_single method original.cnf seed\n";
            return 2;
        }
        const std::string method(argv[1]);
        if (method != "plain" && method != "majority" &&
            method != "selective" && method != "confidence" &&
            method != "confidence_random") {
            throw std::runtime_error("Unsupported method");
        }
        const auto formula=read_cnf(argv[2]); // not in timing, equal for all methods
        const uint32_t seed=std::stoul(argv[3]);
        const auto start=Clock::now();
        const Outcome result=solve(formula,method,seed);
        const double elapsed=std::chrono::duration<double,std::micro>(Clock::now()-start).count();
        // Prefix ensures machine reading is robust against possible native logs.
        std::cout << std::setprecision(12) << "DRNAS_RESULT\t" << method
                  << '\t' << (result.status==10?"SAT":"UNSAT")
                  << '\t' << elapsed
                  << '\t' << (result.hint.selected?1:0)
                  << '\t' << result.hint.candidates
                  << '\t' << result.hint.analysis_us
                  << '\t' << result.hint.pair_reuse
                  << '\t' << formula.vars
                  << '\t' << formula.clauses.size() << "\n";
        return 0;
    } catch (const std::exception &ex) {
        std::cerr << "ERROR: "<<ex.what()<< "\n";
        return 1;
    }
}
