#define DRNAS_V144_NO_MAIN
#include "v144_mixedxor_preprocess.cpp"
#include <cassert>

int main() {
  vector<LocalEq> equations={{{1,2,3},0},{{1,2,4},1},{{3,4,5},1}};
  vector<int> ids={0,1,2};
  Output144 out;
  assert(reduce_component144(equations,ids,out));
  assert(!out.derived.empty());
  for (int mask=0; mask<32; ++mask) {
    bool valid=true;
    for (const auto& eq:equations) {
      int parity=0;
      for (int v:eq.support) parity^=(mask>>(v-1))&1;
      valid &= parity==eq.rhs;
    }
    if (!valid) continue;
    for (const auto& d:out.derived) {
      int parity=0;
      for (int v:d.support) parity^=(mask>>(v-1))&1;
      assert(parity==d.rhs);
      assert(replay144(equations,d.provenance,d.support,d.rhs));
    }
  }
  Output144 capped;
  capped.ops=V144_TOTAL_ELIMINATIONS-1;
  assert(!reduce_component144(equations,ids,capped));
  assert(capped.ops==V144_TOTAL_ELIMINATIONS);
  assert(capped.derived.empty());
  assert(!reduce_component144(equations,ids,capped));
  assert(capped.ops==V144_TOTAL_ELIMINATIONS);
  cout<<"V144_BUDGET_AND_ENTAILMENT_PASS\n";
}
