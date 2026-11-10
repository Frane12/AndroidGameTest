// XORABC3 native source-only, independently replayed complete-XOR extractor.
// The included XORABC2 implementation has its main renamed, preserving the
// exact original-CNF pattern check. No Python GF2 derivation and no outcome
// labels or SAT-solver timing influence the row selector.
// Output: certified CaDiCaL IPASIR-UP source rows: "arity rhs v1 v2 ...".
#define main xorabc2_internal_main
#include "drnas_xorabc2_native.cpp"
#undef main
#include <numeric>
#include <unistd.h>
#include <iomanip>
static void export_rows(const string& input,const string& output){
 auto started=Clock::now();
 need(input!=output,"source and exported rows path must differ");
 Cnf original=read_cnf(input);
 vector<Eq> fast=extract_fast(original);
 vector<Eq> independent=extract_independent(original);
 need(fast.size()==independent.size(),"native extractors disagree on XOR count");
 for(size_t i=0;i<fast.size();i++)
  need(fast[i].vs==independent[i].vs && fast[i].rhs==independent[i].rhs,
       "independent original-CNF parity replay FAILED");
 vector<int> freq(original.n+1,0);
 for(const auto& c:original.clauses){
  for(int lit:c)
   if(lit && freq[abs(lit)]<1000000)freq[abs(lit)]++;
 }
 struct Candidate{Eq eq;int relevance;};
 vector<Candidate> eligible;
 for(const auto& e:independent)if(e.vs.size()>=2&&e.vs.size()<=4){
  long relevance=0;
  for(int var:e.vs)relevance+=min(freq[var],1000);
  eligible.push_back({e,int(min(relevance,1000000L))});
 }
 // Causal selector, source statistics only. No SAT outcome/benchmark leakage.
 stable_sort(eligible.begin(),eligible.end(),[](const Candidate&a,const Candidate&b){
  if(a.relevance!=b.relevance)return a.relevance>b.relevance;
  if(a.eq.vs.size()!=b.eq.vs.size())return a.eq.vs.size()<b.eq.vs.size();
  if(a.eq.vs!=b.eq.vs)return a.eq.vs<b.eq.vs;
  return a.eq.rhs<b.eq.rhs;
 });
 ofstream out(output);
 need(bool(out),"cannot open certified TSV");
 const int max_rows=32;int rows=0;
 for(const auto& c:eligible){
  if(rows>=max_rows)break;
  out<<c.eq.vs.size()<<" "<<c.eq.rhs;
  for(int v:c.eq.vs)out<<" "<<v;
  out<<"\n";rows++;
 }
 need(bool(out),"failed to write certified row TSV");
 cout<<"XORABC3_EXPORT {\"equations\":"<<independent.size()
     <<",\"rows\":"<<rows<<",\"source_clauses\":"<<original.clauses.size()
     <<",\"vars\":"<<original.n
     <<",\"verified\":true,\"selector\":\"source_frequency_only\""
     <<",\"wall_s\":"<<fixed<<setprecision(6)<<elapsed_ms(started)/1000.0
     <<"}\n";
}
static vector<vector<int>> enc(const vector<int>& v,int rhs){
 vector<vector<int>> out;for(int mask=0;mask<(1<<int(v.size()));mask++){
  if((__builtin_popcount(unsigned(mask))&1)==rhs)continue;
  vector<int> clause;for(int i=0;i<int(v.size());i++)
   clause.push_back((mask&(1<<i))?-v[i]:v[i]);
  out.push_back(clause);
 }return out;
}
static void selftest(){
 const string base="/tmp/xorabc3-smoke-"+to_string(getpid());
 const string src=base+".cnf",rows=base+".tsv";
 {
  ofstream f(src);
  const auto a=enc({1,2,3},1);
  f<<"p cnf 3 "<<a.size()<<"\n";
  for(auto& c:a){for(int v:c)f<<v<<" ";f<<"0\n";}
 }
 export_rows(src,rows);
 {ifstream f(rows);string line;need(bool(getline(f,line))&&line=="3 1 1 2 3",
  "complete XOR selftest source mismatch");need(!bool(getline(f,line)),
  "duplicate native XOR result");}
 {
  ofstream f(src);
  const auto a=enc({1,2,3},1);
  f<<"p cnf 3 "<<a.size()-1<<"\n";
  for(size_t i=0;i<a.size()-1;i++){for(int v:a[i])f<<v<<" ";f<<"0\n";}
 }
 export_rows(src,rows);
 {ifstream f(rows);string line;need(!bool(getline(f,line)),
  "incomplete source XOR should not be exported");}
 fs::remove(src);fs::remove(rows);
 cout<<"XORABC3_SELFTEST_PASS independently_replayed=1 partial_negative=1\n";
}
int main(int argc,char**argv){
 try{
  if(argc==2 && string(argv[1])=="selftest"){selftest();return 0;}
  need(argc==4 && string(argv[1])=="export",
       "usage export ORIGINAL.cnf CERTIFIED.tsv");
  export_rows(argv[2],argv[3]);return 0;
 }catch(const exception&e){
  cerr<<"XORABC3_EXPORT_FAIL_CLOSED "<<e.what()<<"\n";
  return 2;
 }
}
