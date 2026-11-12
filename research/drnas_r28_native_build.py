#!/usr/bin/env python3
"""Build isolated R28/R153 + LTM8/LTM13 native composite; frozen binaries unchanged."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess
ROOT=Path('mre_r28_native');ROOT.mkdir(exist_ok=True)
def one(s,a,b):
    assert s.count(a)==1,('patch drift',a[:80],s.count(a))
    return s.replace(a,b,1)
def run(args):subprocess.run(args,check=True)
if not Path('mre_atlas23/native_certificate.cpp').exists():
    run(['python3','research/drnas_ltm9_cert_compile.py'])
frozen={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('mre_atlas23/bin').glob('*') if p.is_file()}
for p in Path('mre_atlas23').glob('*.hpp'):shutil.copy2(p,ROOT/p.name)
policy=Path('research/drnas_ltm13_policy.hpp').read_text()
policy=one(policy, '"explore-or-UCB")<<"\\n";', '"explore-or-UCB")<<"\\n"<<std::flush;')
(ROOT/'ltm8_policy.hpp').write_text(policy)
s=(ROOT/'ltm8_members.hpp').read_text()
s=one(s,'atlas36_quota_pct_=ltm8_.quota;',
    'atlas36_quota_pct_=(std::getenv("DRNAS_R28_KEEP50") && std::string(std::getenv("DRNAS_R28_KEEP50"))=="1")?50:ltm8_.quota;')
(ROOT/'ltm8_members.hpp').write_text(s)
s=Path('mre_atlas23/native_certificate.cpp').read_text()
s=one(s,'int main(int argc,char**argv){','int drnas_native_entry(int argc,char**argv){')
s=one(s,'   if(use_gf2&&(!use_gauss||gauss.source>=4))\n    solver.enable_gf2_from_original(orig);',
    '''   if(use_gf2&&(!use_gauss||gauss.source>=4)){
    solver.enable_gf2_from_original(orig);
    if(std::getenv("DRNAS_R28_SELECTIVE") && std::string(std::getenv("DRNAS_R28_SELECTIVE"))=="1")solver.ltm7_enable_selective();
   }''')
(ROOT/'native.cpp').write_text(s)
s=Path('research/r28_native_vendor/r153_exact_units_gf2.cpp').read_text()
# Preserve exact source derivations; only bound the work and replace external fallback with abstention.
start=s.index('  char* args[]={',s.index('static int fallback('));end=s.index('\n}',start)
s=s[:start]+'  return 0; // composite continues with its own native CDCL'+s[end:]
s=one(s,'int main(int argc,char** argv){','int entry(int argc,char** argv){')
s=one(s,'static bool read_cnf(','''static chrono::steady_clock::time_point deadline;
static bool exhausted(){return chrono::steady_clock::now()>=deadline;}
static bool read_cnf(''')
s=one(s,'  while(in>>t) {','  while(in>>t) {\n    if(exhausted())return false;')
for anchor in ('  for(const auto& clause:clauses) {','  for(auto& kv:groups){','  for(size_t idx=0;idx<eqs.size();idx++){','  for(int p=n;p>=1;p--)if(basis[p].valid){'):
    s=one(s,anchor,anchor+'\n    if(exhausted())return 0;')
s=one(s,'    for(;;){','    for(;;){\n      if(exhausted())return 0;')
lines=s.splitlines();headers='\n'.join(l for l in lines if l.startswith('#include'))
body='\n'.join(l for l in lines if not l.startswith('#include'))
s=headers+'\nnamespace drnas_exact {\n'+body+'\n}\n'+'''
int drnas_math_entry(const char* file,double budget){
  drnas_exact::deadline=std::chrono::steady_clock::now()+std::chrono::duration_cast<std::chrono::steady_clock::duration>(std::chrono::duration<double>(budget));
  char name[]="r153_embedded",unused[]="NO_EXTERNAL_BACKEND";
  char* argv[]={name,const_cast<char*>(file),unused,nullptr};
  return drnas_exact::entry(3,argv);
}
'''
assert 'execv(' not in s
(ROOT/'exact.cpp').write_text(s)
cxx=os.getenv('CXX','g++');flags=[cxx,'-O3','-std=c++17','-Iresearch','-Imre_r28_native','-Imre_atlas15']
run(flags+['research/drnas_r28_native_main.cpp',str(ROOT/'exact.cpp'),str(ROOT/'native.cpp'),'-o',str(ROOT/'drnas_r28_native')])
run([cxx,'-O3','-std=c++17','research/r28_native_vendor/r28_exact_gf2.cpp','-o',str(ROOT/'r28_reference')])
run([cxx,'-O3','-std=c++17','research/r28_native_vendor/r153_exact_units_gf2.cpp','-o',str(ROOT/'r153_reference')])
assert frozen=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('mre_atlas23/bin').glob('*') if p.is_file()}
pins={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'drnas_r28_native',ROOT/'r28_reference',ROOT/'r153_reference',*ROOT.glob('*.cpp'),*ROOT.glob('*.hpp')]}
(ROOT/'pins.json').write_text(json.dumps(pins,indent=2)+'\n')
print('R28_NATIVE_BUILD_PASS single_executable=true external_backend=false frozen_baselines_unchanged=true',flush=True)
