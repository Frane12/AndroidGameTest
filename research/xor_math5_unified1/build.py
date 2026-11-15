#!/usr/bin/env python3
"""Build one native X59 CDCL with opt-in SAT construct and source-backed MATH5 UNSAT.
Do not change frozen source files, baselines, or main.
MATH5 produces custom evidence, never claimed to be DRAT/LRAT.
"""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build" / "xor_math5_unified1"
OUT.mkdir(parents=True, exist_ok=True)

# Recreate the pinned, already-tested MATH5 inference header without editing
# the original MATH4/X59 source. This also validates the MATH4 source hashes.
subprocess.run([sys.executable, str(ROOT / "research/math5_proofio/build_legacy.py")],
               cwd=ROOT, check=True)
header = (ROOT / "build/math5-src/math5_exactone_xor.hpp").read_text()
end = "\n} // namespace math5\n"
assert header.count(end) == 1, "Unexpected MATH5 namespace; refuse build"
header = header.split(end)[0] + end + "\n} // namespace pcmax\n"
(OUT / "math5_unit_only.hpp").write_text(header)

source = (ROOT / "src/drnas_x59.cpp").read_text()
def replace_once(old, new):
    global source
    assert source.count(old) == 1, (old[:100], source.count(old))
    source = source.replace(old, new, 1)

replace_once('#include "drnas_sat_construct.hpp"', r'''#include "drnas_sat_construct.hpp"
#include <filesystem>
#include <iterator>
#include <openssl/sha.h>

// Include ONLY the original MATH5 proof generator. Never start a parallel
// MATH5 CDCL solver, second subprocess, or alternative solver portfolio.
namespace pcmax {
struct Result {
    bool verified=false;
    double elapsed=0.0;
    int groups=0, machines=0, demand=0, capacity=0, rounds=0;
    std::string reason, certificate_json;
};
}
#include "math5_unit_only.hpp"
''')

replace_once('    void configureSatConstruct(double budget_ms) { sat_construct_ms_=budget_ms; }',
r'''    void configureSatConstruct(double budget_ms) { sat_construct_ms_=budget_ms; }
    void configureMath5(double budget_ms, std::string raw_sha, std::string certificate) {
        math5_ms_=budget_ms;
        math5_sha_=std::move(raw_sha);
        math5_certificate_=std::move(certificate);
        math5_reason_ = math5_sha_.empty() ? "SKIP_OVERSIZE_SOURCE" : "NOT_RUN";
    }
    bool math5Found() const { return math5_found_; }
    bool math5Attempted() const { return math5_attempted_; }
    double math5Seconds() const { return math5_elapsed_s_; }
    const std::string& math5Reason() const { return math5_reason_; }''')

replace_once('        Prop p;\n        if (!x46_clone_) {',r'''        // One guarded attempt on ORIGINAL clauses only. MATH5 is a bounded,
        // same-process source-derived UNSAT proof producer. Any UNKNOWN
        // falls through to exactly the existing native CDCL search.
        if (math5_ms_>0 && !x46_clone_ && !timedOut() &&
            !math5_sha_.empty() && n_>0 && n_<=6000 &&
            original_count_<=100000 && !math5_certificate_.empty()) {
            const auto started=Clock::now();
            std::vector<std::vector<int>> original;
            original.reserve(static_cast<size_t>(original_count_));
            size_t lits=0;
            for (const auto& c:clauses_) {
                if (c.learnt) continue;
                lits+=c.lits.size();
                if(lits>1500000) break;
                original.push_back(c.lits);
            }
            if (lits<=1500000 && !timedOut()) {
                const double copy_ms=std::chrono::duration<double,std::milli>(
                    Clock::now()-started).count();
                const double allowed_ms=std::max(0.0,math5_ms_-copy_ms);
                if(allowed_ms>0.0) {
                    math5_attempted_=true;
                    const auto candidate=pcmax::math5::xor_unit(
                        original,n_,math5_sha_,allowed_ms/1000.0);
                    math5_reason_=candidate.reason;
                    if(candidate.verified) {
                        if(candidate.certificate_json.empty())
                            throw std::runtime_error("MATH5 missing certificate");
                        std::ofstream cert(math5_certificate_,std::ios::binary|std::ios::trunc);
                        if(!cert)throw std::runtime_error("MATH5 certificate open failed");
                        cert<<candidate.certificate_json<<"\n";
                        cert.flush();
                        if(!cert)throw std::runtime_error("MATH5 certificate write failed");
                        math5_found_=true;
                        math5_elapsed_s_=std::chrono::duration<double>(
                            Clock::now()-started).count();
                        return Result::UNSAT;
                    }
                } else math5_reason_="BUDGET_EXHAUSTED_BEFORE_ALGEBRA";
            } else math5_reason_="SOURCE_TOO_LARGE_OR_TIMEOUT";
            math5_elapsed_s_=std::chrono::duration<double>(
                Clock::now()-started).count();
        }
        Prop p;
        if (!x46_clone_) {''')

replace_once('    double sat_construct_ms_=0.0, sat_construct_elapsed_s_=0.0;',
r'''    double sat_construct_ms_=0.0, sat_construct_elapsed_s_=0.0;
    double math5_ms_=0.0, math5_elapsed_s_=0.0;
    bool math5_attempted_=false, math5_found_=false;
    std::string math5_sha_,math5_certificate_,math5_reason_="OFF";''')

replace_once('    double sat_construct_ms=0.0;',
r'''    double sat_construct_ms=0.0, math5_ms=0.0;
    std::string math5_certificate;''')

replace_once('        else if (opt=="--sat-construct-ms" && i+1<argc) sat_construct_ms=std::stod(argv[++i]);',
r'''        else if (opt=="--sat-construct-ms" && i+1<argc) sat_construct_ms=std::stod(argv[++i]);
        else if (opt=="--math5-ms" && i+1<argc) math5_ms=std::stod(argv[++i]);
        else if (opt=="--math5-certificate" && i+1<argc) math5_certificate=argv[++i];''')

replace_once('    if (input.empty() || (mode!="core" && mode!="trace") || !std::isfinite(seconds) || seconds<0)',
r'''    if (!std::isfinite(math5_ms)||math5_ms<0||math5_ms>1000)
        throw std::runtime_error("invalid --math5-ms");
    if (math5_ms>0 && (math5_certificate.empty() ||
        math5_certificate==input || math5_certificate==proof_path))
        throw std::runtime_error("MATH5 needs a distinct custom certificate; JSON is not DRAT/LRAT");
    if (math5_ms==0 && !math5_certificate.empty())
        throw std::runtime_error("--math5-certificate requires --math5-ms");
    if (input.empty() || (mode!="core" && mode!="trace") || !std::isfinite(seconds) || seconds<0)''')

replace_once('    solver->finishParsing();',r'''    solver->finishParsing();
    if(math5_ms>0) {
        std::string raw_sha;
        std::error_code ec;
        const auto size=std::filesystem::file_size(input,ec);
        if(!ec && size<=8*1024*1024) {
            std::ifstream bytes(input,std::ios::binary);
            if(!bytes)throw std::runtime_error("cannot read MATH5 source SHA");
            std::string raw((std::istreambuf_iterator<char>(bytes)),
                            std::istreambuf_iterator<char>());
            unsigned char digest[SHA256_DIGEST_LENGTH];
            SHA256(reinterpret_cast<const unsigned char*>(raw.data()),
                   raw.size(),digest);
            std::ostringstream hex;
            hex<<std::hex<<std::setfill('0');
            for(unsigned char b:digest)hex<<std::setw(2)<<int(b);
            raw_sha=hex.str();
        }
        solver->configureMath5(math5_ms,raw_sha,math5_certificate);
    }''')

replace_once('    if(r==Result::UNSAT)solver->writeProofClause({});',
r'''    // Never forge a DRAT empty clause when UNSAT came from custom MATH5
    // structural evidence. The external checker must validate its JSON.
    if(r==Result::UNSAT && !solver->math5Found())solver->writeProofClause({});''')

replace_once('    if (show_stats) {\n        std::cerr<<"SAT_CONSTRUCT_STATS ',
r'''    if (show_stats) {
        std::cerr<<"MATH5_UNIFIED_STATS {\"enabled\":"<<(math5_ms>0?"true":"false")
                 <<",\"attempted\":"<<(solver->math5Attempted()?"true":"false")
                 <<",\"found\":"<<(solver->math5Found()?"true":"false")
                 <<",\"reason\":\""<<solver->math5Reason()
                 <<"\",\"wall_s\":"<<solver->math5Seconds()<<"}\n";
        std::cerr<<"SAT_CONSTRUCT_STATS ''')

out = OUT / "drnas_x59_math5.cpp"
out.write_text(source)
cmd=[os.environ.get("CXX","g++"),"-std=c++20","-O3","-DNDEBUG",
     "-I"+str(ROOT/"src"),"-I"+str(OUT),str(out),"-lcrypto",
     "-o",str(ROOT/"build/drnas-x59-xor-math5-unified1")]
print("MATH5_UNIFIED_BUILD", " ".join(cmd), flush=True)
subprocess.run(cmd,cwd=ROOT,check=True)
print("MATH5_UNIFIED_BUILD_OK", flush=True)
