#include "drnas_ltm13_policy.hpp"
#include <cassert>
int main(){setenv("DRNAS_LTM13_DIRECT","1",1);ltm8::Policy p;p.init(false,1,0);uint64_t work=0;for(int w=0;w<4;w++)for(int i=0;i<64;i++)p.observe(1,++work);for(int w=0;w<3;w++)for(int i=0;i<64;i++){work+=100000;p.observe(100,work);}assert(p.fallback&&p.arm==0);}
