// R133: correctness-first GF(2) -> CDCL communication prototype.
// A propagated literal carries an exact CNF explanation clause.
// No SAT speedup claim; this is an isolated integration contract test.
#include <algorithm>
#include <cassert>
#include <iostream>
#include <vector>
using namespace std;
struct Eq { vector<int> vars; int rhs; };
struct Msg { enum Kind { NONE, UNIT, CONFLICT } kind=NONE; int lit=0; vector<int> reason; };
static bool satisfies(const Eq& e,const vector<int>& a) {
 int p=0; for(int v:e.vars){if(a[v]<0)return false;p^=a[v];}return p==e.rhs;
}
static Msg inspect(const Eq& e,const vector<int>& a) {
 int p=0,missing=0,unknown=0; vector<int> reason;
 for(int v:e.vars) {
  if(a[v]<0){missing++;unknown=v;}
  else {p^=a[v];reason.push_back(a[v] ? -v : v);}
 }
 if(missing>1)return {};
 if(missing==1) {
  int value=p^e.rhs, lit=value ? unknown : -unknown;
  reason.push_back(lit);
  return {Msg::UNIT,lit,reason};
 }
 if(p!=e.rhs)return {Msg::CONFLICT,0,reason};
 return {};
}
static bool clause_true(const vector<int>&cl,const vector<int>&a) {
 for(int lit:cl){int v=abs(lit);if(a[v]<0)continue;if((lit>0)==(a[v]==1))return true;}
 return false;
}
static void check_explanation(const Eq&e,const Msg&m,int n) {
 // Exhaustively prove each emitted clause is entailed by the XOR equation.
 for(int mask=0;mask<(1<<n);mask++){
  vector<int>a(n+1,0);for(int v=1;v<=n;v++)a[v]=(mask>>(v-1))&1;
  if(satisfies(e,a))assert(clause_true(m.reason,a));
 }
}
int main(){
 Eq e{{1,2,3},0};
 vector<int>a(4,-1);
 a[1]=1;a[2]=0;
 Msg m=inspect(e,a);
 assert(m.kind==Msg::UNIT && m.lit==-3);
 check_explanation(e,m,3);
 // CDCL applies implied assignment, then sees no conflict.
 a[3]=0;assert(inspect(e,a).kind==Msg::NONE);
 // Deliberate contradictory assignment generates a reason clause.
 a[3]=1;m=inspect(e,a);
 assert(m.kind==Msg::CONFLICT);check_explanation(e,m,3);
 // Backtrack restores unknown, and propagation remains valid.
 a[3]=-1;m=inspect(e,a);assert(m.kind==Msg::UNIT && m.lit==-3);
 // Purely mixed CNF is not decided here: only proven explanations exported.
 cout<<"R133_BRIDGE_UNIT_CONFLICT_BACKTRACK_PASS reason_literals="<<m.reason.size()<<"\n";
}
