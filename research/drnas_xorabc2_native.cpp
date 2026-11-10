// DRNAS XORABC2: native exact source-XOR detection, GF(2) short consequence
// derivation and independently reconstructed original-CNF proof verification.
// No use of a GF(2) UNSAT shortcut: A/B/C is causal clause-only A/B testing.
// Source DIMACS immutable; derived clauses appear only in a temporary copy.
// All mathematical results are source-entailment claims, NOT LRAT.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
using namespace std;
namespace fs=std::filesystem;
using Clock=chrono::steady_clock;
static void need(bool ok,const string& why){if(!ok)throw runtime_error(why);}
struct VHash {
 size_t operator()(const vector<int>& v)const noexcept {
  size_t h=1469598103934665603ULL;
  for(int x:v){h^=(size_t)x;h*=1099511628211ULL;}return h;
 }
};
struct Cnf{int n=0;vector<vector<int>> clauses;};
struct Eq{vector<int> vs;int rhs;};
struct Row{vector<int> vs;int rhs=0;vector<uint64_t> proof;};
struct Prep{
 int equations=0,rank=0,candidates=0,derived=0,added=0,contradiction=0;
 bool abstain=false;string gate="unmodified";
 double ms=0.0;vector<Row> lemmas;
};
static constexpr int MAX_EQUATIONS=3500,MAX_CLAUSES=1000000,MAX_VARS=100000;
static constexpr int MAX_DERIVED=96,MAX_LEMMAS=384,MAX_PAIRS=110000;
static constexpr double MAX_CPU_PREP_MS=250.0;
static double elapsed_ms(Clock::time_point t){
 return chrono::duration<double,milli>(Clock::now()-t).count();
}
static Cnf read_cnf(const string& path) {
 ifstream f(path);need(bool(f),"cannot open original CNF: "+path);
 Cnf cnf;int declared=-1;vector<int> cl;string line;
 while(getline(f,line)){
  istringstream in(line);string tok;if(!(in>>tok))continue;
  if(tok=="c"||tok=="%")continue;
  if(tok=="p"){
   string kind;need(declared<0&&cl.empty()&&bool(in>>kind>>cnf.n>>declared)
    &&kind=="cnf"&&cnf.n>=1&&cnf.n<=MAX_VARS
    &&declared>=0&&declared<=MAX_CLAUSES,"invalid DIMACS header");
   continue;
  }
  do{
   need(declared>=0,"clause before header");
   size_t consumed=0;long long x=stoll(tok,&consumed);
   need(consumed==tok.size()&&x>=-cnf.n&&x<=cnf.n,"invalid DIMACS literal");
   if(x!=0)cl.push_back(int(x));
   else{
    cnf.clauses.push_back(move(cl));cl.clear();
    need(int(cnf.clauses.size())<=declared,"extra CNF clause");
   }
  }while(in>>tok);
 }
 need(declared>=0&&cl.empty()&&int(cnf.clauses.size())==declared,
      "incomplete original DIMACS");
 return cnf;
}
static vector<Eq> extract_fast(const Cnf& cnf){
 unordered_map<vector<int>,uint16_t,VHash> seen;
 for(const auto& cl:cnf.clauses){
  if(cl.size()<2||cl.size()>4)continue;
  vector<int> vs;for(int l:cl)vs.push_back(abs(l));
  sort(vs.begin(),vs.end());
  if(adjacent_find(vs.begin(),vs.end())!=vs.end())continue;
  int mask=0;
  for(size_t i=0;i<vs.size();i++)
   if(find(cl.begin(),cl.end(),-vs[i])!=cl.end())mask|=1<<i;
  if(seen.size()<100000 || seen.find(vs)!=seen.end())
   seen[vs]|=uint16_t(1u<<mask);
 }
 vector<Eq> eqs;
 for(auto& [vs,masks]:seen){
  for(int p=0;p<2;p++){
   uint16_t required=0;
   for(unsigned m=0;m<(1u<<vs.size());m++)
    if((__builtin_popcount(m)&1)==p)required|=uint16_t(1u<<m);
   if((masks&required)==required)eqs.push_back({vs,1-p});
  }
 }
 sort(eqs.begin(),eqs.end(),[](const Eq&a,const Eq&b){
  return a.vs==b.vs?a.rhs<b.rhs:a.vs<b.vs;
 });
 return eqs;
}
// Independent extractor deliberately uses std::map+std::set and is separate
// from the fast bit-mask detector. Replay is on original clauses, not helper
// reported equations.
static vector<Eq> extract_independent(const Cnf& source){
 map<vector<int>,set<int>> patterns;
 for(const auto& cl:source.clauses){
  if(cl.size()<2||cl.size()>4)continue;
  vector<int> vars;for(int lit:cl)vars.push_back(abs(lit));
  sort(vars.begin(),vars.end());
  if(unique(vars.begin(),vars.end())!=vars.end())continue;
  int mask=0;
  for(size_t i=0;i<vars.size();++i)
   for(int lit:cl)if(lit==-vars[i]){mask|=1<<i;break;}
  patterns[vars].insert(mask);
 }
 vector<Eq> eqs;
 for(auto& [vs,found]:patterns){
  for(int forbidden_parity=0;forbidden_parity<2;forbidden_parity++){
   bool complete=true;
   for(int mask=0;mask<(1<<int(vs.size()));mask++)
    if((__builtin_popcount(unsigned(mask))&1)==forbidden_parity
       &&!found.count(mask)){complete=false;break;}
   if(complete)eqs.push_back({vs,1-forbidden_parity});
  }
 }
 return eqs;
}
static vector<int> difference(const vector<int>& a,const vector<int>& b){
 vector<int> result;result.reserve(a.size()+b.size());
 set_symmetric_difference(a.begin(),a.end(),b.begin(),b.end(),
                          back_inserter(result));
 return result;
}
static Row sum(const Row& a,const Row& b){
 need(a.proof.size()==b.proof.size(),"proof length mismatch");
 Row out;out.vs=difference(a.vs,b.vs);out.rhs=a.rhs^b.rhs;
 out.proof=a.proof;
 for(size_t i=0;i<out.proof.size();i++)out.proof[i]^=b.proof[i];
 return out;
}
static Row from_eq(const Eq& e,int id,size_t words){
 Row r;r.vs=e.vs;r.rhs=e.rhs;r.proof.assign(words,0);
 r.proof[size_t(id)/64]|=1ULL<<(id%64);return r;
}
static int term_count(const vector<uint64_t>& p){
 int n=0;for(uint64_t w:p)n+=__builtin_popcountll(w);return n;
}
static vector<vector<int>> parity_clauses(const vector<int>& vars,int rhs){
 vector<vector<int>> out;int k=int(vars.size());
 need(k>=1&&k<=3&&(rhs==0||rhs==1),"invalid short parity lemma");
 for(int m=0;m<(1<<k);m++){
  if((__builtin_popcount(unsigned(m))&1)==rhs)continue;
  vector<int> cl;
  for(int i=0;i<k;i++)cl.push_back((m&(1<<i))?-vars[i]:vars[i]);
  out.push_back(move(cl));
 }
 return out;
}
static void replay(const vector<Eq>& original,const Row& claim){
 need(claim.proof.size()==(original.size()+63)/64,
      "certificate dimension mismatch");
 vector<int> vs;int rhs=0;int terms=0;
 for(size_t i=0;i<original.size();i++){
  if(!(claim.proof[i/64]&(1ULL<<(i%64))))continue;
  vs=difference(vs,original[i].vs);rhs^=original[i].rhs;terms++;
 }
 need(terms>0&&claim.vs==vs&&claim.rhs==rhs,
      "GF2 certificate does not imply advertised short equation");
}
static void write_cnf(const string& output,const Cnf& original,
                      const vector<Row>& chosen){
 ofstream f(output);need(bool(f),"cannot open augmented output");
 size_t additional=0;
 for(const Row& row:chosen)additional+=size_t(1)<<(row.vs.size()-1);
 f<<"p cnf "<<original.n<<" "<<original.clauses.size()+additional<<"\n";
 auto write_clause=[&](const vector<int>& cl){
  for(int lit:cl)f<<lit<<" ";f<<"0\n";
 };
 for(const auto& cl:original.clauses)write_clause(cl);
 for(const Row& r:chosen)
  for(auto& cl:parity_clauses(r.vs,r.rhs))write_clause(cl);
 need(bool(f),"cannot write output CNF");
}
static void write_ledger(const string& output,const vector<Row>& chosen){
 ofstream f(output);need(bool(f),"cannot open certificate ledger");
 f<<"p xorproof "<<chosen.size()<<"\n";
 for(const Row& r:chosen){
  f<<"r "<<r.rhs<<" "<<r.vs.size();
  for(int v:r.vs)f<<" "<<v;
  f<<" "<<term_count(r.proof);
  for(size_t i=0;i<r.proof.size()*64;i++)
   if((r.proof[i/64]>>(i%64))&1ULL)f<<" "<<i;
  f<<"\n";
 }
 need(bool(f),"cannot write certificate ledger");
}
static vector<Row> read_ledger(const string& path,size_t eqs){
 ifstream f(path);need(bool(f),"missing ledger");
 string p,kind;int count=-1;
 need(bool(f>>p>>kind>>count)&&p=="p"&&kind=="xorproof"&&count>=0
      &&count<=MAX_DERIVED,"bad ledger header");
 vector<Row> rows;size_t words=(eqs+63)/64;
 for(int t=0;t<count;t++){
  string code;int rhs=-1,k=0,terms=0;
  need(bool(f>>code>>rhs>>k)&&code=="r"&&rhs>=0&&rhs<=1
       &&k>=1&&k<=3,"bad proof row");
  Row row;row.rhs=rhs;row.vs.resize(k);row.proof.assign(words,0);
  for(int& v:row.vs)need(bool(f>>v)&&v>0,"bad variable index");
  need(is_sorted(row.vs.begin(),row.vs.end())&&
       adjacent_find(row.vs.begin(),row.vs.end())==row.vs.end(),
       "noncanonical proof variables");
  need(bool(f>>terms)&&terms>=1&&terms<=int(eqs),"bad proof term count");
  for(int j=0;j<terms;j++){
   int id=-1;need(bool(f>>id)&&id>=0&&id<int(eqs),"invalid source eq id");
   auto& word=row.proof[size_t(id)/64];uint64_t mask=1ULL<<(id%64);
   need(!(word&mask),"duplicate proof term");word|=mask;
  }
  rows.push_back(move(row));
 }
 string extra;need(!(f>>extra),"ledger contains extra tokens");
 return rows;
}
static void independent_verify(const string& source,const string& target,
                               const string& ledger){
 Cnf original=read_cnf(source);
 vector<Eq> eqs=extract_independent(original);
 vector<Row> rows=read_ledger(ledger,eqs.size());
 for(const auto& r:rows)replay(eqs,r);
 Cnf augmented=read_cnf(target);
 need(augmented.n==original.n,"augmented header n changed");
 size_t count=original.clauses.size();
 need(augmented.clauses.size()>=count,"lost original clauses");
 for(size_t i=0;i<count;i++)
  need(augmented.clauses[i]==original.clauses[i],
       "augmented CNF altered an original clause");
 size_t at=count;
 for(auto& r:rows)for(auto& cl:parity_clauses(r.vs,r.rhs)){
  need(at<augmented.clauses.size()&&augmented.clauses[at++]==cl,
       "appended clause does not match proven XOR row");
 }
 need(at==augmented.clauses.size(),"unproven appended clauses");
 cout<<"XORABC2_CHECK_PASS {\"rows\":"<<rows.size()
     <<",\"added_clauses\":"<<at-count
     <<",\"source_equations\":"<<eqs.size()<<"}"<<endl;
}
static Prep derive(const Cnf& cnf,int maxwidth,Clock::time_point started){
 Prep result;result.gate="no_new_lemmas";
 vector<Eq> eqs=extract_fast(cnf);
 result.equations=int(eqs.size());
 if(eqs.size()>MAX_EQUATIONS){result.gate="too_many_equations";result.abstain=true;return result;}
 if(elapsed_ms(started)>MAX_CPU_PREP_MS){
  result.gate="time_budget";result.abstain=true;return result;
 }
 const size_t words=(eqs.size()+63)/64;
 map<int,Row> basis;bool contradiction=false;
 for(size_t i=0;i<eqs.size();i++){
  Row row=from_eq(eqs[i],int(i),words);
  while(!row.vs.empty()){
   int pivot=row.vs.back();auto it=basis.find(pivot);
   if(it==basis.end()){basis.emplace(pivot,move(row));break;}
   row=sum(row,it->second);
  }
  if(row.vs.empty()&&row.rhs){contradiction=true;break;}
  if(i%64==0&&elapsed_ms(started)>MAX_CPU_PREP_MS){
   result.abstain=true;result.gate="time_budget";return result;
  }
 }
 result.rank=int(basis.size());result.contradiction=contradiction?1:0;
 // Contradiction is telemetry ONLY, no proof shortcut or new clauses in ABC2.
 if(contradiction){result.gate="GF2_unsat_no_shortcut";return result;}
 map<pair<vector<int>,int>,Row> candidates;
 auto propose=[&](const Row& r){
  if(r.vs.empty()||r.vs.size()>size_t(maxwidth)
     ||term_count(r.proof)<2)return;
  auto key=make_pair(r.vs,r.rhs);
  auto it=candidates.find(key);
  if(it==candidates.end()||term_count(r.proof)<term_count(it->second.proof))
   candidates[key]=r;
 };
 // Echelon and reduced echelon short consequences.
 for(const auto& [p,r]:basis)propose(r);
 map<int,Row> reduced;
 for(const auto& [p,original]:basis){
  Row r=original;
  while(true){
   int pivot=0;
   for(int v:r.vs)if(v!=p&&reduced.count(v))pivot=max(pivot,v);
   if(!pivot)break;
   r=sum(r,reduced.at(pivot));
  }
  reduced[p]=r;propose(r);
  if(elapsed_ms(started)>MAX_CPU_PREP_MS){
   result.gate="time_budget";result.abstain=true;return result;
  }
 }
 // New part: pairwise combinations of *source* XOR equations. This finds
 // short implications even when row-echelon representations are long.
 unordered_map<int,vector<int>> inverted;
 for(int i=0;i<int(eqs.size());i++)
  for(int v:eqs[i].vs)inverted[v].push_back(i);
 unordered_set<uint64_t> pairs;int checked=0;
 bool limit_hit=false;
 for(size_t i=0;i<eqs.size()&&!limit_hit;i++){
  for(int v:eqs[i].vs){
   for(int j:inverted[v]){
    if(j<=int(i))continue;
    uint64_t key=(uint64_t(i)<<32)|uint32_t(j);
    if(!pairs.insert(key).second)continue;
    if(++checked>MAX_PAIRS){limit_hit=true;break;}
    auto vv=difference(eqs[i].vs,eqs[j].vs);
    if(!vv.empty()&&vv.size()<=size_t(maxwidth)){
     Row row;row.vs=move(vv);row.rhs=eqs[i].rhs^eqs[j].rhs;
     row.proof.assign(words,0);
     row.proof[i/64]^=1ULL<<(i%64);
     row.proof[size_t(j)/64]^=1ULL<<(j%64);
     propose(row);
    }
    if((checked&2047)==0&&elapsed_ms(started)>MAX_CPU_PREP_MS){
     limit_hit=true;break;
    }
   }
   if(limit_hit)break;
  }
 }
 result.candidates=int(candidates.size());
 // A truncated search still yields sound candidates; no false completeness claim.
 vector<Row> ordered;
 for(auto& [k,v]:candidates)ordered.push_back(v);
 sort(ordered.begin(),ordered.end(),[](const Row&a,const Row&b){
  if(a.vs.size()!=b.vs.size())return a.vs.size()<b.vs.size();
  if(term_count(a.proof)!=term_count(b.proof))
   return term_count(a.proof)<term_count(b.proof);
  return a.vs==b.vs?a.rhs<b.rhs:a.vs<b.vs;
 });
 set<vector<int>> clauses_seen;
 for(const auto& c:cnf.clauses){
  vector<int> sorted=c;sort(sorted.begin(),sorted.end());
  clauses_seen.insert(move(sorted));
 }
 // Replay certificates from independently rebuilt original clause groups.
 vector<Eq> independent=extract_independent(cnf);
 need(independent.size()==eqs.size(),"native fast and independent extraction differ");
 for(size_t i=0;i<eqs.size();i++)
  need(eqs[i].vs==independent[i].vs&&eqs[i].rhs==independent[i].rhs,
       "original XOR source equation mismatch");
 int clauses=0;
 for(auto& r:ordered){
  if(int(result.lemmas.size())>=MAX_DERIVED)break;
  vector<vector<int>> generated=parity_clauses(r.vs,r.rhs);
  bool changes=false;
  for(auto c:generated){
   sort(c.begin(),c.end());
   if(!clauses_seen.count(c))changes=true;
  }
  if(!changes)continue;
  // No partial parity group: add all parity clauses for this derived row,
  // then independently verify exact appended text in a second process.
  if(clauses+int(generated.size())>MAX_LEMMAS)break;
  replay(independent,r);
  for(auto c:generated){sort(c.begin(),c.end());clauses_seen.insert(move(c));}
  result.lemmas.push_back(r);clauses+=int(generated.size());
  if(elapsed_ms(started)>MAX_CPU_PREP_MS){
   // Discard any incomplete prepass instead of contaminating solver input.
   result.lemmas.clear();result.gate="time_budget";result.abstain=true;return result;
  }
 }
 result.derived=int(result.lemmas.size());result.added=clauses;
 result.gate=clauses?"verified_derived_clauses":limit_hit?"pair_search_capped":"no_new_lemmas";
 return result;
}
static void print_report(const Prep& r){
 cout<<"XORABC2_NATIVE {\"gate\":\""<<r.gate<<"\",\"xor_equations\":"
     <<r.equations<<",\"GF2_rank\":"<<r.rank
     <<",\"derived_rows\":"<<r.derived<<",\"lemmas_added\":"<<r.added
     <<",\"candidate_rows\":"<<r.candidates
     <<",\"contradiction_seen\":"<<(r.contradiction?"true":"false")
     <<",\"abstained\":"<<(r.abstain?"true":"false")
     <<",\"native_ms\":"<<r.ms<<"}"<<endl;
}
int main(int argc,char** argv){
 try{
  need(argc>=2,"usage: xorabc2 derive [b|c] source augmented ledger | verify source augmented ledger");
  const string action=argv[1];
  if(action=="verify"){
   need(argc==5,"verify needs original, augmented, proof");
   independent_verify(argv[2],argv[3],argv[4]);return 0;
  }
  need(action=="derive"&&argc==6,"derive needs mode, original, augmented, ledger");
  string mode=argv[2];need(mode=="b"||mode=="c","invalid width");
  string src=argv[3],target=argv[4],ledger=argv[5];
  need(src!=target&&src!=ledger&&target!=ledger,
       "original must be immutable; output paths must differ");
  auto start=Clock::now();Prep p;
  if(fs::file_size(src)>6*1024*1024){
   p.gate="geometry_skip";p.abstain=true;
   fs::copy_file(src,target,fs::copy_options::overwrite_existing);
   write_ledger(ledger,{});p.ms=elapsed_ms(start);print_report(p);return 0;
  }
  Cnf cnf=read_cnf(src);
  p=derive(cnf,mode=="b"?2:3,start);
  write_cnf(target,cnf,p.lemmas);write_ledger(ledger,p.lemmas);
  p.ms=elapsed_ms(start);print_report(p);return 0;
 }catch(const exception& e){
  cerr<<"XORABC2_NATIVE_FAIL_CLOSED "<<e.what()<<endl;return 2;
 }
}
