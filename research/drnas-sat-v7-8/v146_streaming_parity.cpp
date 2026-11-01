// DRNAS V14.6 — bounded prefix-stream certified local parity reasoning.
// For CNFs larger than the former 96 KiB gate, inspect at most 2 MiB and
// 30000 COMPLETE clauses. Partial formulas are NEVER solved as SAT; the only
// allowed answer is UNSAT with a replayable subset of ORIGINAL clause IDs.
// Extra unseen clauses cannot invalidate a logical UNSAT subset proof.
// Source clauses are read from the front of the original input file, never
// from a name, label, prior timing or trained routing table.
#include "v145_propagated_parity.cpp"
#include <fstream>
#include <sstream>
#include <limits>
#include <cerrno>
#include <cstdlib>

static const long long STREAM_MIN_BYTES = 96LL * 1024;
static const long long STREAM_MAX_SCAN_BYTES = 2LL * 1024 * 1024;
static const size_t STREAM_MAX_CLAUSES = 30000;
static const size_t STREAM_MAX_PENDING_LITERALS = 64;
// An incomplete final line/clause is discarded. Only fully terminated clauses
// from valid prefix tokens may contribute to any GF(2) proof.
struct Prefix146 {
 Cnf partial;
 long long read_bytes=0;
 long long header_clauses=0;
 bool ok=false;
 bool clipped=false;
};
static bool parse_integer146(const string& s,long long& v) {
 if(s.empty())return false;
 char* end=nullptr;
 errno=0;
 v=strtoll(s.c_str(),&end,10);
 return errno==0 && end!=s.c_str() && *end=='\0';
}
static Prefix146 prefix146(const string& path) {
 Prefix146 p;
 ifstream in(path);
 if(!in)return p;
 string line;
 bool header=false;
 vector<int> pending;
 while(getline(in,line)) {
   p.read_bytes += (long long)line.size()+1;
   // Never consume this line when it crosses the fixed bounded budget.
   if(p.read_bytes>STREAM_MAX_SCAN_BYTES) {p.clipped=true;break;}
   istringstream words(line);
   string token;
   if(!(words>>token))continue;
   if(token=="c" || token=="%")continue;
   if(token=="p") {
     long long n=0,m=0;string kind,nstr,mstr,extra;
     if(header || !(words>>kind>>nstr>>mstr) || kind!="cnf" ||
        (words>>extra) || !parse_integer146(nstr,n) ||
        !parse_integer146(mstr,m) || n<1 || n>1000000 ||
        m<1 || m>10000000)return Prefix146{};
     header=true;
     p.partial.n=int(n);
     p.header_clauses=m;
     continue;
   }
   if(!header)return Prefix146{};
   do {
     long long val=0;
     if(!parse_integer146(token,val) ||
         val>p.partial.n || val< -p.partial.n)return Prefix146{};
     if(!val) {
       if(pending.empty())return Prefix146{};
       p.partial.clauses.push_back(move(pending));
       pending.clear();
       if(p.partial.clauses.size()>size_t(p.header_clauses))
         return Prefix146{};
       if(p.partial.clauses.size()>=STREAM_MAX_CLAUSES) {
         p.clipped=true;break;
       }
     } else {
       if(pending.size()>=STREAM_MAX_PENDING_LITERALS)
         return Prefix146{};
       pending.push_back(int(val));
     }
   } while(words>>token);
   if(p.clipped)break;
 }
 // Pending unclosed clause is intentionally ignored and cannot contribute.
 p.ok=header && !p.partial.clauses.empty();
 return p;
}
int main(int argc,char**argv) {
 if(!(argc==4 || (argc==5&&string(argv[4])=="--classify-only"))) {
   cerr<<"Usage: v146_stream_xor ORIGINAL_CNF KISSAT_BINARY SEED [--classify-only]\n";
   return 2;
 }
 try {
   const string filename=argv[1];
   struct stat st{};
   Prefix146 prefix;
   bool eligible=false;
   if(stat(filename.c_str(),&st)==0 && st.st_size>STREAM_MIN_BYTES) {
     // The previous V14.5 already handles smaller CNFs. Do not scan twice.
     prefix=prefix146(filename);
     if(prefix.ok) {
       vector<Parity144> eq=extract144(prefix.partial);
       eligible=eq.size()>=4;
       if(eligible && argc==4) {
         set<int> certificate;
         size_t operations=0;
         if(gf2_unsat144(eq,certificate,operations)) {
           bool proven=replay144(eq,certificate);
           for(int e:certificate) {
             if(!direct_witness144(prefix.partial,eq[e]))proven=false;
           }
           if(!proven)throw runtime_error("Partial-stream UNSAT proof failed");
           cout<<"DRNAS_V146_RESULT\t{\"status\":\"UNSAT\","
               <<"\"verified\":true,\"path\":\"streaming_bounded_parity\","
               <<"\"scanned_bytes\":"<<prefix.read_bytes
               <<",\"scanned_clauses\":"<<prefix.partial.clauses.size()
               <<",\"stream_clipped\":"<<(prefix.clipped?"true":"false")
               <<",\"equations\":"<<eq.size()
               <<",\"xor_operations\":"<<operations<<",\"proof\":[";
           bool first=true;
           for(int e:certificate) {
             const auto& row=eq[e];
             cout<<(first?"":",")<<"{\"variables\":[";
             first=false;
             for(size_t j=0;j<row.vars.size();j++)
               cout<<(j?",":"")<<row.vars[j];
             cout<<"],\"rhs\":"<<row.rhs<<",\"clause_indices\":[";
             for(size_t j=0;j<row.clauses.size();j++)
               cout<<(j?",":"")<<row.clauses[j];
             cout<<"]}";
           }
           cout<<"]}\n";
           return 0;
         }
       }
     }
   }
   if(argc==5) {
     cout<<"DRNAS_V146_GATE\t"<<(eligible?"prefix_parity_candidate":"bypass")
         <<"\tbytes="<<prefix.read_bytes
         <<"\tclauses="<<prefix.partial.clauses.size()<<"\n";
     return 0;
   }
   cout<<"DRNAS_V146_ROUTE\t"<<(eligible?"prefix_parity_then_v145":"v145_direct")
       <<"\n"<<flush;
   return v145_embedded_main(argc,argv);
 } catch(const exception& e) {
   cerr<<"DRNAS_V146_ERROR "<<e.what()<<"\n";return 3;
 }
}
