// DRNAS SRE2-A proof-first graph structural screening and native CDCL.
// No foreign solver. A graph clique may prove UNSAT; native CDCL handles rest.
#define DRNAS_SRE2A_EMBED
#include "drnas_sre1_native.cpp"
#undef DRNAS_SRE2A_EMBED
#include "drnas_sre2a_structure.hpp"
namespace drnas {
static void sre2a_selftest(){
 auto sat=sre1_radio(false),unsat=sre1_radio(true);
 auto a=sre2a_scan(sat),b=sre2a_scan(unsat);
 require(a.exact_one==5 && a.graph_vertices==5 && a.graph_edges==8 &&
         a.colors==3 && !a.certified_unsat,"radio SAT structure recognition");
 require(b.exact_one==5 && b.graph_vertices==5 && b.graph_edges==9 &&
         b.colors==3 && b.certified_unsat && b.largest_clique>=4,
         "radio K4 UNSAT obstruction");
 auto circ=sre2a_scan(sre1_circuit(false));
 require(!circ.certified_unsat,"circuit false graph contradiction");
 std::mt19937 rng(0x5e2a2026);
 int checked=0;
 for(int n=2;n<=8;++n)for(int t=0;t<90;++t){
  CNF f;f.vars=n;
  for(int i=0,m=1+(int)(rng()%24);i<m;++i){
   std::vector<int> clause;
   for(int j=0,w=1+(int)(rng()%5);j<w;++j){
    int v=1+(int)(rng()%(unsigned)n);
    clause.push_back((rng()&1u)?v:-v);
   }
   f.clauses.push_back(clause);
  }
  auto scan=sre2a_scan(f);
  if(scan.certified_unsat)
   require(!brute_sat(f),"SRE2A unsound clique contradiction");
  ++checked;
 }
 std::cout<<"SRE2A_SELFTEST_PASS random="<<checked
   <<" radio_sat_groups="<<a.exact_one<<" radio_sat_edges="<<a.graph_edges
   <<" radio_unsat_edges="<<b.graph_edges
   <<" radio_unsat_clique="<<b.largest_clique
   <<" independent_brute=true\n";
}
}
int main(int argc,char**argv){
 try{
  if(argc==2 && std::string(argv[1])=="--selftest"){
   drnas::sre2a_selftest();return 0;
  }
  if(argc!=6 || std::string(argv[2])!="--mode" ||
                std::string(argv[4])!="--time"){
   std::cerr<<"usage: sre2a FILE --mode plain|sre1|sre2a|sre2a_shadow --time SECONDS\n";
   return 2;
  }
  std::string mode=argv[3];
  drnas::require(mode=="plain"||mode=="sre1"||mode=="sre2a"||
                 mode=="sre2a_shadow","bad mode");
  double cap=std::stod(argv[5]);
  drnas::require(cap>0 && cap<=120 && std::isfinite(cap),"bad cap");
  auto start=drnas::Clock::now();
  auto input=drnas::read_dimacs(argv[1]);
  auto scan=drnas::sre2a_scan(input);
  drnas::SRE1 reduction;
  bool use_reduction=(mode=="sre1"||mode=="sre2a");
  if(use_reduction)reduction=drnas::sre1_reduce(input,true);
  const drnas::CNF& work=use_reduction?reduction.reduced:input;
  double prep=std::chrono::duration<double>(drnas::Clock::now()-start).count();
  int status=0;
  std::vector<int8_t> model;
  uint64_t conflicts=0,decisions=0;
  bool clique_used=mode=="sre2a" && scan.certified_unsat;
  if(clique_used)status=20;
  else if(prep<cap){
   drnas::NativeCDCL solver(work.vars);
   solver.add_cnf(work);
   status=solver.solve(cap-prep);
   conflicts=solver.statistics().conflicts;
   decisions=solver.statistics().decisions;
   if(status==10){
    model=use_reduction?reduction.lift(solver.assignments()):solver.assignments();
    drnas::require(drnas::sre1_verify_original(input,model),
                   "original SAT witness invalid");
   }
  }
  double wall=std::chrono::duration<double>(drnas::Clock::now()-start).count();
  std::cout<<std::fixed<<std::setprecision(6)
   <<"SRE2A_TRIAL mode="<<mode
   <<" status="<<(status==10?"SAT":status==20?"UNSAT":"UNKNOWN")
   <<" e2e_s="<<wall<<" prep_s="<<prep
   <<" groups="<<scan.exact_one<<" vertices="<<scan.graph_vertices
   <<" edges="<<scan.graph_edges<<" components="<<scan.components
   <<" clique="<<scan.largest_clique<<" colors="<<scan.colors
   <<" clique_certified="<<int(scan.certified_unsat)
   <<" clique_used="<<int(clique_used)
   <<" scan_abstained="<<int(scan.abstained)
   <<" removed_vars="<<(input.vars-work.vars)
   <<" conflicts="<<conflicts<<" decisions="<<decisions
   <<" original_SAT_witness_verified="<<int(status==10)
   <<" original_UNSAT_independent_LRAT=0"
   <<" foreign_solver_calls=0\n";
  if(status==10){
   std::cout<<"s SATISFIABLE\nv ";
   for(int v=1;v<=input.vars;++v)std::cout<<(model[v]<0?-v:v)<<" ";
   std::cout<<"0\n";
  }else std::cout<<(status==20?"s UNSATISFIABLE\n":"s UNKNOWN\n");
  return status==10?10:status==20?20:0;
 }catch(const std::exception& e){
  std::cerr<<"SRE2A_FAIL_CLOSED "<<e.what()<<"\n";return 2;
 }
}
