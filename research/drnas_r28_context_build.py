#!/usr/bin/env python3
"""Add context memory only in a new binary; frozen R28 native remains unchanged."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess
base=Path('mre_r28_native');root=Path('mre_r28_context');root.mkdir(exist_ok=True)
if not (base/'native.cpp').exists():subprocess.run(['python3','research/drnas_r28_native_build.py'],check=True)
def one(s,a,b):
    assert s.count(a)==1,('context patch drift',a[:70],s.count(a))
    return s.replace(a,b,1)
frozen=hashlib.sha256((base/'drnas_r28_native').read_bytes()).hexdigest()
for p in base.glob('*.hpp'):shutil.copy2(p,root/p.name)
shutil.copy2('research/drnas_r28_context_state.hpp',root/'context_state.hpp')
s=(base/'ltm8_policy.hpp').read_text()
s=one(s,'namespace ltm8 {','#include "context_state.hpp"\nnamespace ltm8 {')
s=one(s,'struct Policy {','struct Policy {\n    drnas_context::State context_;')
s=one(s,'        arm=0;\n        if(direct){','        const int warm=context_.initial_arm();\n        arm=0;\n        if(direct){')
s=one(s,'            else if(fixed>=0)arm=fixed;','            else if(fixed>=0)arm=fixed;\n            else if(warm>=0)arm=warm;')
s=one(s,'        choose();\n    }\n    bool observe(','''        context_.init(bucket,direct && fixed<0);
        if(context_.enabled){context_.enter(0,count,mean);loaded=context_.loaded;}
        choose();
        if(context_.enabled)std::cout<<"c R28_CONTEXT_START arm="<<arm<<" key="<<bucket<<"\\n"<<std::flush;
    }
    bool observe(''')
s=one(s,'        auto& n=count[arm];auto& m=mean[arm];','        context_.observe(arm,reward);\n        auto& n=count[arm];auto& m=mean[arm];')
s=one(s,'        samples=0;quality=0;last_work=work;choose();','''        samples=0;quality=0;last_work=work;
        // Early-search and established-search priors are distinct; online feedback continues.
        if(context_.enabled && windows==4){context_.enter(1,count,mean);best_reward=0;bad_windows=0;}
        choose();''')
s=one(s,'    void save(){','    void save(){\n        context_.emit();')
(root/'ltm8_policy.hpp').write_text(s)
s=(root/'ltm8_members.hpp').read_text()
s=one(s,'        size_t binary=0,ternary=0;','        size_t binary=0,ternary=0,units=0,observed=0,prefix_literals=0,prefix_binary=0,prefix_horn=0;')
s=one(s,'binary+=c.size()==2;ternary+=c.size()==3;', '''binary+=c.size()==2;ternary+=c.size()==3;units+=c.size()==1;
            if(observed<2000 && prefix_literals+c.size()<=16384){
                ++observed;prefix_literals+=c.size();prefix_binary+=c.size()==2;
                unsigned pos=0;for(int lit:c){pos+=lit>0;if(pos>1)break;}
                prefix_horn+=pos<=1;
            }''')
s=one(s,'        const int bucket=(src.vars>1000?4:0)+(binary*2>src.clauses.size()?1:ternary*4>src.clauses.size()*3?2:0);', '''        // 3 size tiers x 4 clause mixes x 3 density tiers x 2 unit-presence states.
        const size_t m=src.clauses.size(),n=std::max(1,src.vars);
        const int size=src.vars<128?0:src.vars<1024?1:2;
        // R160/R135 binary/Horn rule is a context feature, not an external solver selector.
        const bool r160_low=observed>=32 && prefix_binary*5<observed && prefix_horn*2<observed;
        const int mix=binary*2>m?0:r160_low?1:ternary*4>m*3?2:3;
        const int density=m<n*3?0:m<n*6?1:2;
        const int bucket=((size*4+mix)*3+density)*2+(units?1:0);''')
(root/'ltm8_members.hpp').write_text(s)
flags=[os.getenv('CXX','g++'),'-O3','-std=c++17','-Iresearch','-Imre_r28_context','-Imre_atlas15']
# Quoted includes must resolve in the isolated directory before the old directory.
for name in ('native.cpp','exact.cpp'):shutil.copy2(base/name,root/name)
subprocess.run(flags+['research/drnas_r28_native_main.cpp',str(root/'exact.cpp'),str(root/'native.cpp'),'-o',str(root/'drnas_r28_context')],check=True)
assert frozen==hashlib.sha256((base/'drnas_r28_native').read_bytes()).hexdigest()
(root/'pins.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file() and p.name!='pins.json'},indent=2)+'\n')
print('R28_CONTEXT_BUILD_PASS frozen_native_unchanged=true sqlite_inside_search=false',flush=True)
