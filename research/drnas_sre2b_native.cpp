// DRNAS SRE2-B: native CDCL + SRE1 certified GF2/SCC + SRE2A graph
// + exact source-CNF automorphism symmetry breaking (one leader).
#define DRNAS_SRE2B_EMBED
#include "drnas_sre2a_native.cpp"
#undef DRNAS_SRE2B_EMBED
#include "drnas_sre2b_symmetry.hpp"
namespace drnas {
static CNF sre2b_symmetric(bool unsat){
 CNF f;f.vars=6;
 // 1 and 2 are interchangeable, 3 and 4 too; 5/6 XOR.
 f.clauses={{1,2},{-1,-2},{3,4},{-3,-4},
            {5,6},{-5,-6},{-1,3},{-2,4},{-3,1},{-4,2}};
 if(unsat){f.clauses.push_back({1});f.clauses.push_back({2});}
 return f;
}
static void sre2b_selftest(){
 sre1_selftest();sre2a_selftest();
 auto f=sre2b_symmetric(false);
 CNF changed;auto x=sre2b_symmetry(f,changed,true);
 require(x.leader_added && changed.clauses.size()==f.clauses.size()+1,
         "SRE2B failed symmetric source CNF detection");
 require(brute_sat(f)==brute_sat(changed),"SRE2B symmetry changed SAT");
 std::mt19937 rng(0x2b202611);
 int tests=0, leaders=0;
 for(int n=2;n<=9;++n)for(int t=0;t<80;++t){
  CNF c;c.vars=n;
  for(int i=0,m=(int)(rng()%27);i<m;++i){
   std::vector<int> clause;
   for(int j=0,k=(int)(rng()%5);j<k;++j){
    int v=1+(int)(rng()%(unsigned)n);
    clause.push_back((rng()&1u)?v:-v);
   }
   c.clauses.push_back(std::move(clause));
  }
  CNF modified;
  auto scan=sre2b_symmetry(c,modified,true);
  if(scan.leader_added)++leaders;
  require(brute_sat(c)==brute_sat(modified),
          "SRE2B random symmetry not equisatisfiable");
  ++tests;
 }
 std::cout<<"SRE2B_SELFTEST_PASS random_originals="<<tests
  <<" certified_symmetry_examples="<<leaders
  <<" source_brute_equisat=true SRE1_SRE2A_retested=true\n";
}
}
#ifndef DRNAS_SRE2C_EMBED

int main(int argc,char**argv){
 try{
  if(argc==2 && std::string(argv[1])=="--selftest"){
   drnas::sre2b_selftest();return 0;
  }
  if(argc!=6 || std::string(argv[2])!="--mode" ||
                std::string(argv[4])!="--time"){
   std::cerr<<"usage: sre2b FILE --mode plain|sre1|sre2a|sre2b|sre2b_shadow --time SECONDS\n";
   return 2;
  }
  std::string mode=argv[3];
  drnas::require(mode=="plain"||mode=="sre1"||mode=="sre2a"||
     mode=="sre2b"||mode=="sre2b_shadow","bad mode");
  double cap=std::stod(argv[5]);
  drnas::require(cap>0 && cap<=120 && std::isfinite(cap),"bad cap");
  auto started=drnas::Clock::now();
  auto input=drnas::read_dimacs(argv[1]);
  drnas::CNF augmented;
  const bool symmetry_enabled=mode=="sre2b"||mode=="sre2b_shadow";
  auto sym=drnas::sre2b_symmetry(input,augmented,symmetry_enabled);
  auto graph=drnas::sre2a_scan(input);
  const bool use_sre=mode=="sre1"||mode=="sre2a"||mode=="sre2b";
  const bool leader=mode=="sre2b"&&sym.leader_added;
  const drnas::CNF& pre=leader?augmented:input;
  drnas::SRE1 reduction;
  if(use_sre)reduction=drnas::sre1_reduce(pre,true);
  const drnas::CNF& work=use_sre?reduction.reduced:pre;
  double prep=std::chrono::duration<double>(drnas::Clock::now()-started).count();
  const bool clique_used=(mode=="sre2a"||mode=="sre2b")&&graph.certified_unsat;
  int status=0;uint64_t conflicts=0,decisions=0;
  std::vector<int8_t> model;
  if(clique_used)status=20;
  else if(prep<cap){
   drnas::NativeCDCL solver(work.vars);
   solver.add_cnf(work);
   status=solver.solve(cap-prep);
   conflicts=solver.statistics().conflicts;
   decisions=solver.statistics().decisions;
   if(status==10){
    model=use_sre?reduction.lift(solver.assignments()):solver.assignments();
    drnas::require(drnas::sre1_verify_original(input,model),
                   "SRE2B lifted original SAT model invalid");
   }
  }
  double wall=std::chrono::duration<double>(drnas::Clock::now()-started).count();
  std::cout<<std::fixed<<std::setprecision(6)
   <<"SRE2B_TRIAL mode="<<mode
   <<" status="<<(status==10?"SAT":status==20?"UNSAT":"UNKNOWN")
   <<" e2e_s="<<wall<<" prep_s="<<prep
   <<" symmetry_pair_a="<<sym.symmetry_a
   <<" symmetry_pair_b="<<sym.symmetry_b
   <<" symmetry_probes="<<sym.probes
   <<" symmetry_leader_added="<<int(leader)
   <<" symmetry_shadow_found="<<int(sym.leader_added)
   <<" symmetry_abstained="<<int(sym.abstained)
   <<" exactly_one="<<graph.exact_one
   <<" graph_edges="<<graph.graph_edges
   <<" clique="<<graph.largest_clique
   <<" clique_used="<<int(clique_used)
   <<" sre_equivalences="<<reduction.equivalences
   <<" sre_gf2_pairs="<<reduction.gf2_pairs
   <<" sre_root_units="<<reduction.root_units
   <<" reduced_vars="<<work.vars
   <<" reduced_clauses="<<work.clauses.size()
   <<" conflicts="<<conflicts<<" decisions="<<decisions
   <<" original_SAT_verified="<<int(status==10)
   <<" original_UNSAT_independent_LRAT=0"
   <<" third_party_solver_calls=0\n";
  if(status==10){
   std::cout<<"s SATISFIABLE\nv ";
   for(int v=1;v<=input.vars;++v)std::cout<<(model[v]<0?-v:v)<<" ";
   std::cout<<"0\n";
  }else std::cout<<(status==20?"s UNSATISFIABLE\n":"s UNKNOWN\n");
  return status==10?10:status==20?20:0;
 }catch(const std::exception&e){
  std::cerr<<"SRE2B_FAIL_CLOSED "<<e.what()<<"\n";return 2;
 }
}

#endif // DRNAS_SRE2C_EMBED
