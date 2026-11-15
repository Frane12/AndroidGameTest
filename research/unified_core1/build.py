from pathlib import Path
import subprocess,sys,hashlib,json
R=Path(__file__).resolve().parents[2]
subprocess.run([sys.executable,str(R/'research/math5/build.py')],cwd=R,check=True)
D=R/'build/unified_core1';D.mkdir(exist_ok=True)
h=(R/'build/math5-src/math5_exactone_xor.hpp').read_text();end='\n} // namespace math5\n'
(D/'math5_only.hpp').write_text(h.split(end)[0]+end+'\n} // namespace pcmax\n')
s=(R/'src/drnas_x59.cpp').read_text()
def rep(a,b):
 global s
 assert s.count(a)==1,(a[:80],s.count(a))
 s=s.replace(a,b)
rep('#include "drnas_sat_construct.hpp"','#include "drnas_sat_construct.hpp"\n#include "pcmax_capacity.hpp"\n#include "pcmax_clause_hall.hpp"\n#include "hall3_guard.hpp"\n#include "math5_only.hpp"\n#include <openssl/sha.h>\n#include <filesystem>')
rep('    Result solve() {','''    void configureUnified(double ms, int mask, std::string sha, std::string cert) {
        unified_ms_=ms; unified_mask_=mask; unified_sha_=std::move(sha); unified_cert_=std::move(cert);
    }
    bool structuralFound() const { return unified_structural_; }
    Result solve() {''')
a=s.index('        // Opt-in ARG3-V3') if '        // Opt-in ARG3-V3' in s else s.index('        if (arg3_v3_ms_>0')
# Replace all independent guard calls, retain exact original CDCL loop.
a=s.index('        if (root_unsat_) return Result::UNSAT;')+len('        if (root_unsat_) return Result::UNSAT;')
b=s.index('        Prop p;',a)
s=s[:a]+r'''
        if(unified_ms_>0 && !x46_clone_ && n_<=15000 && original_count_<=130000) {
            const auto begin=Clock::now();
            auto remaining=[&](){return std::max(0.0,std::min(unified_ms_-
                std::chrono::duration<double,std::milli>(Clock::now()-begin).count(),
                timeout_s_>0 ? (timeout_s_-std::chrono::duration<double>(Clock::now()-begun_).count())*1000 : unified_ms_));};
            std::vector<std::vector<int>> original;
            size_t literals=0, binaries=0, wide=0, triples=0;
            for(const auto& c:clauses_) {
                if(c.learnt)continue;
                literals+=c.lits.size();
                if(literals>600000 || remaining()<=0 || timedOut())break;
                binaries+=c.lits.size()==2; wide+=c.lits.size()>2; triples+=c.lits.size()==3;
                original.push_back(c.lits);
            }
            if(literals<=600000 && original.size()==clauses_.size() && remaining()>0) {
                // One source copy, shared wall budget. Individual routines retain
                // their independently tested internal indices and size gates.
                if((unified_mask_&1) && remaining()>0) {
                    satconstruct::Limits limits;limits.max_ms=std::min(25.0,remaining());
                    auto out=satconstruct::analyze(n_,original,limits);
                    if(out.sat()) {leaf_model_=std::move(out.model);
                        if(!verifyModel())throw std::runtime_error("unified invalid SAT");
                        sat_construct_method_=out.method; sat_construct_found_=true;
                        return Result::SAT;}
                }
                if((unified_mask_&8) && triples && binaries && remaining()>0) {
                    auto out=drnas_arg3::construct_robust(n_,original,std::min(15.0,remaining()));
                    arg3_stats_=out.stats;
                    if(out.sat()) {leaf_model_=std::move(out.model);
                        if(!verifyModel())throw std::runtime_error("ARG3 invalid SAT");
                        return Result::SAT;}
                }
                if(!unified_cert_.empty() && !unified_sha_.empty() && n_<=6000 && original_count_<=100000) {
                    pcmax::Result out;
                    if((unified_mask_&2) && wide && remaining()>0)
                        out=pcmax::math5::xor_unit(original,n_,unified_sha_,std::min(35.0,remaining())/1000.0);
                    if(!out.verified && (unified_mask_&4) && binaries>=2 && remaining()>0) {
                        pcmax::Options opts;opts.seconds=remaining()/1000.0;
                        out=pcmax::analyze_hall3(original,n_,unified_sha_,opts);
                    }
                    if(out.verified && !timedOut()) {
                        if(out.certificate_json.empty())throw std::runtime_error("missing structural proof");
                        std::ofstream cert(unified_cert_,std::ios::binary|std::ios::trunc);
                        cert<<out.certificate_json<<"\n";cert.flush();
                        if(!cert)throw std::runtime_error("certificate write failed");
                        unified_structural_=true;return Result::UNSAT;
                    }
                }
            }
        }
''' + s[b:]
rep('    double sat_construct_ms_=0.0, sat_construct_elapsed_s_=0.0;', '''    double unified_ms_=0;
    int unified_mask_=15;
    bool unified_structural_=false;
    std::string unified_sha_,unified_cert_;
    double sat_construct_ms_=0.0, sat_construct_elapsed_s_=0.0;''')
rep('    std::string x46_model_path,x47_guard_path,proof_path;', '    double unified_ms=100; int unified_mask=15; std::string unified_cert;\n    bool proof_binary=true;\n    std::string x46_model_path,x47_guard_path,proof_path;')
rep('        else if (opt=="--proof" && i+1<argc)', '''        else if (opt=="--unified-ms" && i+1<argc) unified_ms=std::stod(argv[++i]);
        else if (opt=="--unified-mask" && i+1<argc) unified_mask=std::stoi(argv[++i]);
        else if (opt=="--unified-off") unified_ms=0;
        else if (opt=="--certificate" && i+1<argc) unified_cert=argv[++i];
        else if (opt=="--proof-text") proof_binary=false;
        else if (opt=="--proof" && i+1<argc)''')
rep('    std::ofstream proof;', '''    if(!std::isfinite(unified_ms)||unified_ms<0||unified_ms>1000||unified_mask<0||unified_mask>15)
        throw std::runtime_error("invalid unified budget/mask");
    if(sat_construct_ms>0||arg3_ms>0||arg3_v3_ms>0||x46_conflicts>0)
        throw std::runtime_error("use unified mask; independent guards and clone probes disabled");
    if(!unified_cert.empty()) {
        if(std::filesystem::exists(unified_cert) || std::filesystem::weakly_canonical(unified_cert)==std::filesystem::weakly_canonical(input) || (!proof_path.empty() && std::filesystem::weakly_canonical(unified_cert)==std::filesystem::weakly_canonical(proof_path)))
            throw std::runtime_error("certificate must be a fresh distinct output");
    }
    std::ofstream proof;''')
rep('    solver->finishParsing();', '''    solver->finishParsing();
    std::string digest;
    if(unified_ms>0 && !unified_cert.empty() && std::filesystem::file_size(input)<=8*1024*1024) {
        std::ifstream bytes(input,std::ios::binary);
        std::string raw((std::istreambuf_iterator<char>(bytes)),{});
        unsigned char hash[SHA256_DIGEST_LENGTH];SHA256(reinterpret_cast<const unsigned char*>(raw.data()),raw.size(),hash);
        std::ostringstream hex;hex<<std::hex<<std::setfill('0');
        for(auto x:hash)hex<<std::setw(2)<<int(x);digest=hex.str();
    }
    solver->configureUnified(unified_ms,unified_mask,digest,unified_cert);''')
rep('    if(r==Result::UNSAT)solver->writeProofClause({});','    if(r==Result::UNSAT && !solver->structuralFound())solver->writeProofClause({});')
# Identical checked binary serialization used by MATH5.
rep('bool restarts, std::ostream* proof) {','bool restarts, std::ostream* proof, bool binary=true) {')
rep('x5_restarts_=restarts; proof_=proof;','x5_restarts_=restarts; proof_=proof; proof_binary_=binary;')
rep('    std::ostream* proof_=nullptr;', '    bool proof_binary_=true;\n    std::ostream* proof_=nullptr;')
rep('        proof.open(proof_path);','        proof.open(proof_path,std::ios::out|std::ios::binary);')
rep('                                proof_path.empty()?nullptr:&proof);','                                proof_path.empty()?nullptr:&proof,proof_binary);')
rep('        for (int lit:lits) *proof_ << lit << \' \';\n        *proof_ << "0\\n";',r'''        if(proof_binary_) {
            proof_->put('a');
            for(int lit:lits) {uint32_t u=uint32_t(2*std::abs(int64_t(lit))+(lit<0));
                while(u>=128){proof_->put(char((u&127)|128));u>>=7;}proof_->put(char(u));}
            proof_->put(0);
        } else {for(int lit:lits)*proof_<<lit<<' ';*proof_<<"0\n";}''')
(D/'solver.cpp').write_text(s)
subprocess.run(['g++','-std=c++20','-O3','-DNDEBUG','-I'+str(R/'src'),'-I'+str(D),str(D/'solver.cpp'),'-lcrypto','-o',str(R/'build/drnas-unified-core1')],check=True)
print('UNIFIED_BUILD_OK')
files=[R/'src/drnas_x59.cpp',R/'src/drnas_sat_construct.hpp',R/'src/drnas_sat_arg3.hpp',R/'src/pcmax_capacity.hpp',R/'src/pcmax_clause_hall.hpp',R/'src/hall3_guard.hpp',D/'math5_only.hpp',D/'solver.cpp',R/'build/drnas-unified-core1']
manifest={'git_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),'compiler':subprocess.check_output(['g++','--version'],text=True).splitlines()[0],'sha256':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
(D/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
