// R181: CLEAN CaDiCaL 2.1 early conflict probe, separate from scored solvers.
// Three isolated runs (64/128/256), NEVER continuation of the measured solver.
// Probe cost including DIMACS ingestion is charged in retrospective replay.
#include "cadical.hpp"
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
int main(int argc,char**argv){
  try {
    if(argc!=3)throw std::runtime_error("usage: r181-probe CNF cutoff");
    int cutoff=std::stoi(argv[2]);
    if(cutoff!=64&&cutoff!=128&&cutoff!=256)
      throw std::runtime_error("bad cutoff");
    const auto start=std::chrono::steady_clock::now();
    CaDiCaL::Solver solver;
    int vars=0;
    const char* err=solver.read_dimacs(argv[1],vars,1);
    if(err)throw std::runtime_error(err);
    if(!solver.limit("conflicts",cutoff))
      throw std::runtime_error("CaDiCaL conflicts limit unavailable");
    int res=solver.solve();
    if(res!=0&&res!=10&&res!=20)
      throw std::runtime_error("unexpected solve code");
    const double elapsed=std::chrono::duration<double>(
      std::chrono::steady_clock::now()-start).count();
    std::cout<<"R181_PROBE cutoff="<<cutoff
             <<" status="<<(res==10?"SAT":res==20?"UNSAT":"UNKNOWN")
             <<" vars="<<vars<<" elapsed="<<elapsed<<"\n";
    std::cout<<"R181_STATS_BEGIN\n";
    solver.statistics();
    std::cout<<"R181_STATS_END\n"<<std::flush;
    return 0;
  }catch(const std::exception&e){
    std::cerr<<"R181_PROBE_FAILURE "<<e.what()<<"\n";
    return 2;
  }
}
