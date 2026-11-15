#!/usr/bin/env python3
"""Binary DRAT by default; --proof-text is an explicit diagnostic override."""
from pathlib import Path
import subprocess,sys,os,hashlib,json,shutil
R=Path(__file__).resolve().parents[2]
subprocess.run([sys.executable,str(R/'research/math5_proofio/build_legacy.py')],check=True,cwd=R)
shutil.copy2(R/'build/drnas-math5',R/'build/drnas-math5-text')
p=R/'build/math5-src/drnas_math5.cpp';s=p.read_text()
def replace(old,new):
 global s
 assert s.count(old)==1,(old,s.count(old))
 s=s.replace(old,new)
replace('bool restarts, std::ostream* proof) {','bool restarts, std::ostream* proof, bool binary=true) {')
replace('x5_restarts_=restarts; proof_=proof;','x5_restarts_=restarts; proof_=proof; proof_binary_=binary;')
replace('        for (int lit:lits) *proof_ << lit << \' \';\n        *proof_ << "0\\n";', '''        if (proof_binary_) {
            proof_bytes_.clear();
            proof_bytes_.push_back('a');
            for (int lit : lits) {
                uint32_t u = uint32_t(2 * std::abs(int64_t(lit)) + (lit < 0));
                while (u >= 128) {
                    proof_bytes_.push_back(char((u & 127) | 128));
                    u >>= 7;
                }
                proof_bytes_.push_back(char(u));
            }
            proof_bytes_.push_back(char(0));
            proof_->write(proof_bytes_.data(),std::streamsize(proof_bytes_.size()));
        } else {
            for (int lit:lits) *proof_ << lit << ' ';
            *proof_ << "0\\n";
        }''')
replace('    std::ostream* proof_=nullptr;', '    bool proof_binary_=true;\n    std::string proof_bytes_;\n    std::ostream* proof_=nullptr;')
replace('    std::string x46_model_path,x47_guard_path,proof_path;', '    bool proof_binary=true;\n    std::string x46_model_path,x47_guard_path,proof_path;')
replace('        else if (opt=="--proof" && i+1<argc)', '        else if (opt=="--proof-binary") proof_binary=true;\n        else if (opt=="--proof-text") proof_binary=false;\n        else if (opt=="--proof" && i+1<argc)')
replace('        proof.open(proof_path);', '        proof.open(proof_path,std::ios::out|std::ios::binary);')
replace('                                proof_path.empty()?nullptr:&proof);', '                                proof_path.empty()?nullptr:&proof,proof_binary);')
replace('[--proof FILE] [--x5-no-minimize]', '[--proof FILE] [--proof-binary|--proof-text] [--x5-no-minimize]')
p=R/'build/math5-src/drnas_math5_proofio.cpp';p.write_text(s)
out=R/'build/drnas-math5-proofio'
subprocess.run([os.environ.get('CXX','g++'),'-std=c++20','-O3','-DNDEBUG','-Wall','-Wextra','-Wpedantic','-Werror','-DDRNAS_PCMAX_MODULE','-I'+str(R/'src'),str(p),'-lcrypto','-o',str(out)],check=True)
shutil.copy2(out,R/'build/drnas-math5')
print('PROOFIO_BUILD '+json.dumps({str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [p,out]}))
