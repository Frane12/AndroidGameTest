#pragma once
#include "structure_probe.hpp"
#include <chrono>
#include <cstdint>
#include <vector>
namespace drnas_v16 {
enum class Mode { Control, Observe, Adaptive };
struct GateResult {
  Features features;
  Decision decision;
  uint64_t probe_ns=0;
  bool switched=false;
};
inline GateResult select(const std::vector<std::vector<int>>& cnf, Mode mode) {
  GateResult result;
  if (mode==Mode::Control) return result;
  const auto start=std::chrono::steady_clock::now();
  result.features=inspect(cnf);
  result.decision=decide(result.features);
  const auto stop=std::chrono::steady_clock::now();
  result.probe_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(stop-start).count();
  // Adaptive currently behaves like Observe until strategies are validated.
  // This prevents unmeasured, potentially harmful heuristic switching.
  return result;
}
} // namespace drnas_v16
