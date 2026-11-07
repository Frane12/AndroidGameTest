#include "structure_probe.hpp"
#include <cassert>
#include <vector>
int main() {
  using namespace drnas_v16;
  std::vector<std::vector<int>> binary(100, {1,-2});
  auto b=decide(inspect(binary));
  assert(b.family==Family::BinaryHeavy && !b.enable_experimental);
  std::vector<std::vector<int>> horn(100, {-1,-2,3});
  auto h=decide(inspect(horn));
  assert(h.family==Family::HornHeavy && !h.enable_experimental);
  assert(decide(inspect({{}})).family==Family::Unknown);
  assert(inspect(binary,10).truncated);
  assert(decide(inspect(binary,10)).family==Family::Unknown);
  return 0;
}
