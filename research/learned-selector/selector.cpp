// Experimental offline-trained formula selector. Requires explicit invocation.
#include <cerrno>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <unistd.h>

int main(int argc, char **argv) {
  if (argc != 5) {
    std::cerr << "usage: selector MONITOR STABLE ORIGINAL_KISSAT FORMULA.cnf\n";
    return 2;
  }
  std::ifstream file(argv[4]);
  if (!file) { std::cerr << "cannot read formula\n"; return 2; }
  std::string line, p, cnf;
  unsigned long long n = 0, m = 0;
  bool valid = false;
  while (std::getline(file, line)) {
    std::istringstream in(line);
    if (!(in >> p) || p == "c") continue;
    if (p == "p" && (in >> cnf >> n >> m) && cnf == "cnf" && n > 0 && m > 0)
      valid = true;
    break;
  }
  // Frozen R9 development tree: stable leaf when m/n <= 3.2039999961853027.
  const bool stable = valid && static_cast<double>(m) / n <= 3.2039999961853027;
  std::cerr << "c DRNAS_SELECTOR route=" << (stable ? "stable_v1531" : "monitor") << "\n";
  if (stable) {
    char *args[] = {argv[2], argv[4], argv[3], const_cast<char *>("1"), nullptr};
    execv(args[0], args);
  } else {
    char *args[] = {argv[1], const_cast<char *>("-s"), argv[4], nullptr};
    execv(args[0], args);
  }
  std::cerr << "cannot execute selected solver: " << std::strerror(errno) << "\n";
  return 127;
}
