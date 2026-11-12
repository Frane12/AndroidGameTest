#include "drnas_ltm13_policy.hpp"
#include <cassert>
int main(){setenv("DRNAS_LTM13_DIRECT","1",1);ltm8::Policy p;p.init(false,17,0);assert(p.arm==0);for(int w=0;w<4;w++){for(int i=0;i<64;i++)p.observe(4,(w*64+i+1)*100); }for(auto n:p.count)assert(n>0);setenv("DRNAS_LTM13_FIXED","2",1);ltm8::Policy q;q.init(false,17,0);for(int i=0;i<1000;i++)q.observe(5,i*10);assert(q.arm==2);}
