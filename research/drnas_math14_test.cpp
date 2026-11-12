#include "drnas_math14.hpp"
#include <cassert>
#include <random>
struct CNF{std::vector<std::vector<int>> clauses;};
void row(CNF&c,std::array<int,3> v,int rhs){for(int m=0;m<8;m++)if((__builtin_popcount(unsigned(m))&1)!=rhs){std::vector<int>cl;for(int i=0;i<3;i++)cl.push_back((m>>i&1)?-v[i]:v[i]);c.clauses.push_back(cl);}}
bool sat(const CNF&c,int m){for(auto cl:c.clauses){bool ok=false;for(int v:cl)ok|=bool(m>>(std::abs(v)-1)&1)==(v>0);if(!ok)return false;}return true;}
int main(){std::mt19937 r(14);for(int k=0;k<500;k++){CNF c;for(int i=0;i<6;i++){std::array<int,3>v={1+int(r()%6),1+int(r()%6),1+int(r()%6)};std::sort(v.begin(),v.end());if(v[0]!=v[1]&&v[1]!=v[2])row(c,v,r()%2);}CNF before=c;math14::enrich(c);for(int m=0;m<64;m++)assert(sat(before,m)==sat(c,m));assert(math14::enrich(c)==0);}CNF c;row(c,{1,2,3},0);row(c,{1,2,4},1);assert(math14::enrich(c)==2);CNF incomplete;row(incomplete,{1,2,3},0);incomplete.clauses.pop_back();row(incomplete,{1,2,4},1);assert(math14::enrich(incomplete)==0);}

