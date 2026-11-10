// DRNAS SRE2-C: integrate original-certified GF2 rows into actual CDCL
// propagation and 1-UIP explanations. Source R3C already implements
// trail-incidence event scheduling, source-certified XOR reason clauses,
// and 500k check budget; this experiment measures it against shadow,
// reduced-SRE2B, and no-GF2 baselines. No external solver.
#define DRNAS_SRE2C_EMBED
#include "drnas_sre2b_native.cpp"
#undef DRNAS_SRE2C_EMBED
namespace drnas {
static CNF sre2c_xor_case(bool unsat){
 CNF f;f.vars=8;
 auto xor3=[&](int a,int b,int c,int rhs){
  for(int bits=0;bits<8;++bits){
   if((__builtin_popcount((unsigned)bits)&1)==rhs)continue;
   f.clauses.push_back({(bits&1)?-a:a,(bits&2)?-b:b,(bits&4)?-c:c});
  }
 };
 xor3(1,2,3,0);xor3(3,4,5,1);xor3(5,6,7,0);
 f.clauses.push_back({1});f.clauses.push_back({-2});
 f.clauses.push_back({4});f.clauses.push_back({-6});
 if(unsat){f.clauses.push_back({-7});}
 else {f.clauses.push_back({7});}
 return f;
}
static void sre2c_selftest(){
 sre2b_selftest();
 int checked=0;
 for(bool unsat:{false,true}){
  CNF f=sre2c_xor_case(unsat);
  bool expected=brute_sat(f);
  for(bool use_sre:{false,true}){
   SRE1 red;
   if(use_sre)red=sre1_reduce(f,true);
   const CNF& source=use_sre?red.reduced:f;
   for(bool live:{false,true}){
    NativeCDCL s(source.vars);s.add_cnf(source);
    if(live)s.enable_gf2_from_original(source);
    int st=s.solve(3.0);
    require(st==(expected?10:20),"SRE2C CDCL GF2 truth mismatch");
    if(st==10){
     auto model=use_sre?red.lift(s.assignments()):s.assignments();
     require(sre1_verify_original(f,model),"SRE2C original model invalid");
    }
    ++checked;
   }
  }
 }
 std::cout<<"SRE2C_SELFTEST_PASS modes="<<checked
  <<" SRE1_SRE2A_SRE2B_retested=true"
  <<" native_GF2_CDCL_reasons=true original_truth_exhaustive=true\n";
}
}
#ifndef DRNAS_FACTOR2_EMBED
int main(int argc,char**argv){
 try{
  if(argc==2 && std::string(argv[1])=="--selftest"){
   drnas::sre2c_selftest();return 0;
  }
  if(argc!=6 || std::string(argv[2])!="--mode"||
                std::string(argv[4])!="--time"){
   std::cerr<<"usage: sre2c FILE --mode plain|sre2b|live_raw|live_reduced|live_shadow --time SECONDS\n";
   return 2;
  }
  std::string mode=argv[3];
  drnas::require(mode=="plain"||mode=="sre2b"||mode=="live_raw"||
     mode=="live_reduced"||mode=="live_shadow","invalid mode");
  double cap=std::stod(argv[5]);
  drnas::require(std::isfinite(cap)&&cap>0&&cap<=120,"invalid time");
  auto started=drnas::Clock::now();
  auto input=drnas::read_dimacs(argv[1]);
  bool shadow=mode=="live_shadow";
  bool use_sre=mode=="sre2b"||mode=="live_reduced";
  bool use_live=mode=="live_raw"||mode=="live_reduced";
  drnas::CNF augmented;
  auto sym=drnas::sre2b_symmetry(input,augmented,use_sre||shadow);
  auto graph=drnas::sre2a_scan(input);
  const drnas::CNF& presource=(use_sre&&sym.leader_added)?augmented:input;
  drnas::SRE1 red;
  if(use_sre)red=drnas::sre1_reduce(presource,true);
  const drnas::CNF& work=use_sre?red.reduced:input;
  drnas::NativeCDCL solver(work.vars);
  solver.add_cnf(work);
  if(use_live)solver.enable_gf2_from_original(work);
  double prep=std::chrono::duration<double>(drnas::Clock::now()-started).count();
  int status=0;
  bool clique_used=use_sre&&graph.certified_unsat;
  if(clique_used)status=20;
  else if(prep<cap)status=solver.solve(cap-prep);
  std::vector<int8_t> model;
  if(status==10){
   model=use_sre?red.lift(solver.assignments()):solver.assignments();
   drnas::require(drnas::sre1_verify_original(input,model),
       "SRE2C reconstructed SAT witness fails original CNF");
  }
  const auto& st=solver.statistics();
  double elapsed=std::chrono::duration<double>(drnas::Clock::now()-started).count();
  std::cout<<std::fixed<<std::setprecision(6)
   <<"SRE2C_TRIAL mode="<<mode
   <<" status="<<(status==10?"SAT":status==20?"UNSAT":"UNKNOWN")
   <<" e2e_s="<<elapsed<<" prep_s="<<prep
   <<" original_vars="<<input.vars<<" reduced_vars="<<work.vars
   <<" source_rows="<<st.xor_source_rows
   <<" derived_rows="<<st.xor_derived_rows
   <<" gf2_checks="<<st.xor_checks
   <<" gf2_events="<<st.xor_events_processed
   <<" gf2_implications="<<st.xor_implications
   <<" gf2_conflicts="<<st.xor_conflicts
   <<" gf2_reasons="<<st.xor_reasons
   <<" gf2_budget_off="<<st.xor_budget_off
   <<" gf2_live="<<int(use_live)
   <<" gf2_shadow="<<int(shadow)
   <<" symmetry_found="<<int(sym.leader_added)
   <<" clique_used="<<int(clique_used)
   <<" decisions="<<st.decisions<<" conflicts="<<st.conflicts
   <<" original_SAT_verified="<<int(status==10)
   <<" original_UNSAT_independent_LRAT=0"
   <<" foreign_solver_calls=0\n";
  if(status==10){
   std::cout<<"s SATISFIABLE\nv ";
   for(int v=1;v<=input.vars;++v)std::cout<<(model[v]<0?-v:v)<<" ";
   std::cout<<"0\n";
  }else std::cout<<(status==20?"s UNSATISFIABLE\n":"s UNKNOWN\n");
  return status==10?10:status==20?20:0;
 }catch(const std::exception&e){
  std::cerr<<"SRE2C_FAIL_CLOSED "<<e.what()<<"\n";return 2;
 }
}

#endif // DRNAS_FACTOR2_EMBED
