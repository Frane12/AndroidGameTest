#include "adaptive_gate.hpp"
#include <cassert>
#include <vector>
int main() {
  std::vector<std::vector<int>> cnf(100,{1,-2});
  auto control=drnas_v16::select(cnf,drnas_v16::Mode::Control);
  auto observe=drnas_v16::select(cnf,drnas_v16::Mode::Observe);
  auto adaptive=drnas_v16::select(cnf,drnas_v16::Mode::Adaptive);
  assert(control.features.clauses==0);
  assert(observe.features.clauses==100);
  assert(adaptive.decision.family==drnas_v16::Family::BinaryHeavy);
  assert(!control.switched && !observe.switched && !adaptive.switched);
  return 0;
}
