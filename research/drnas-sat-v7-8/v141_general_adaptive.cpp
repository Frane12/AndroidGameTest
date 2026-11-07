// DRNAS V14.1 - general SAT adaptive portfolio (not a novel SAT algorithm).
// 1. Reuse V14.0 structural recognizer for strictly proven XOR / PHP CNFs.
// 2. For genuinely general SAT, a bounded, noninvasive original V7.6 probe
//    only on modest-sized ternary-rich instances; otherwise run Kissat 4.0.4.
// 3. Unfinished V7.6 probes are killed/reaped; remaining time is for Kissat.
// All routing uses DIMACS bytes only. No label, benchmark filename or truth.
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>
using namespace std;
using Clock=chrono::steady_clock;

struct Result {
 int exit_code=-1;
 bool timed_out=false;
 string output;
};
Result run_bounded(const vector<string>& args,int timeout_ms) {
 Result result;int p[2]={-1,-1};
 if(pipe(p)!=0)throw runtime_error("pipe failure");
 pid_t pid=fork();
 if(pid<0) {
   close(p[0]);close(p[1]);throw runtime_error("fork failure");
 }
 if(pid==0) {
   close(p[0]);dup2(p[1],STDOUT_FILENO);close(p[1]);
   vector<char*> av;av.reserve(args.size()+1);
   for(const auto &s:args)av.push_back(const_cast<char*>(s.c_str()));
   av.push_back(nullptr);
   execv(av[0],av.data());
   _exit(127);
 }
 close(p[1]);
 int flags=fcntl(p[0],F_GETFL);
 if(flags>=0)fcntl(p[0],F_SETFL,flags|O_NONBLOCK);
 auto deadline=Clock::now()+chrono::milliseconds(timeout_ms);
 bool done=false;int status=0;
 while(Clock::now()<deadline) {
   char buf[4096];ssize_t n;
   while((n=read(p[0],buf,sizeof(buf)))>0) {
     if(result.output.size()+size_t(n)<=131072)result.output.append(buf,size_t(n));
   }
   pid_t w=waitpid(pid,&status,WNOHANG);
   if(w==pid){done=true;break;}
   if(w<0)break;
   usleep(500); // bounded scheduling overhead
 }
 if(!done) {
   result.timed_out=true;
   kill(pid,SIGKILL);
   while(waitpid(pid,&status,0)<0&&errno==EINTR){}
 }
 char buf[4096];ssize_t n;
 while((n=read(p[0],buf,sizeof(buf)))>0)
   if(result.output.size()+size_t(n)<=131072)result.output.append(buf,size_t(n));
 close(p[0]);
 if(done&&WIFEXITED(status))result.exit_code=WEXITSTATUS(status);
 return result;
}
string clean_line(string s) {
 while(!s.empty()&&(s.back()=='\r'||s.back()=='\n'))s.pop_back();
 return s;
}
string result_line(const string &content,const string &prefix) {
 istringstream in(content);string line,match;
 while(getline(in,line)) {
   line=clean_line(line);
   if(line.rfind(prefix,0)==0) {
     if(!match.empty())return ""; // reject duplicate or ambiguous solver output
     match=line;
   }
 }
 return match;
}
struct Features {
 bool supported=false;
 int vars=0,clauses=0,ternary=0,unit=0,binary=0,longer=0;
};
Features peek(const string &input) {
 Features f;struct stat st{};
 if(stat(input.c_str(),&st)!=0||st.st_size>4*1024*1024)return f;
 ifstream stream(input);
 if(!stream)return f;
 string line;
 int count=0,seen=0;
 while(getline(stream,line)) {
   if(line.empty()||line[0]=='c'||line[0]=='%')continue;
   istringstream iss(line);string first;
   if(!(iss>>first))continue;
   if(first=="p") {
     string kind;
     if(f.supported||!(iss>>kind>>f.vars>>f.clauses)||
        kind!="cnf"||f.vars<=0||f.clauses<=0)return Features{};
     f.supported=true;continue;
   }
   if(!f.supported)return Features{};
   // Count each DIMACS clause terminator, not line; tolerate multiline CNFs.
   auto parse_lit=[&](const string &str)->bool {
     char *end=nullptr;errno=0;long v=strtol(str.c_str(),&end,10);
     if(errno||end==str.c_str()||*end||v>f.vars||v< -f.vars)return false;
     if(v==0) {
       if(count==0)return false;
       ++seen;
       if(count==1)f.unit++;
       else if(count==2)f.binary++;
       else if(count==3)f.ternary++;
       else f.longer++;
       count=0;
     } else ++count;
     return true;
   };
   if(!parse_lit(first))return Features{};
   string value;while(iss>>value)if(!parse_lit(value))return Features{};
 }
 if(!f.supported||count||seen!=f.clauses)return Features{};
 return f;
}
int probe_budget(const Features &f) {
 // Fixed, preregistered and label-blind policy. A timed probe is a safety
 // experiment, not a learned predictor. Small ternary SAT is the target.
 if(!f.supported)return 0;
 if(f.vars<=400&&f.clauses<=1600&&f.ternary*5>=f.clauses*3)
   return 65; // 65 ms budget on compact, predominantly 3-CNF
 if(f.vars<=1200&&f.clauses<=6000&&f.ternary*5>=f.clauses*4)
   return 25; // 25 ms on medium predominantly 3-CNF
 return 0;
}
int main(int argc,char**argv) {
 if(argc!=6&&!(argc==7&&string(argv[6])=="--classify-only")) {
   cerr<<"Usage: general INPUT_CNF V140_NATIVE V76_SOLVER KISSAT_SOLVER SEED [--classify-only]\n";
   return 2;
 }
 try {
   string cnf=argv[1],exact=argv[2],v76=argv[3],kissat=argv[4],seed=argv[5];
   const bool classify=argc==7;
   // Exact route: strictly preserve V14.0's independently certified logic.
   Result certificate=run_bounded({exact,cnf,v76,seed,"--classify-only"},600);
   if(certificate.exit_code==0&&!certificate.timed_out) {
     string exactline=result_line(certificate.output,"DRNAS_HYBRID_RESULT\t");
     if(!exactline.empty()) {
       cout<<exactline<<"\n";return 0;
     }
   }
   Features f=peek(cnf);int budget=probe_budget(f);
   if(classify) {
     cout<<"DRNAS_GENERAL_CLASSIFY\t"<<(budget?"probe_v76_then_kissat":"kissat_direct")
         <<"\tbudget_ms="<<budget<<"\n";
     return 0;
   }
   if(budget) {
     Result first=run_bounded({v76,"adaptive_plain",cnf,seed},budget);
     if(first.exit_code==0&&!first.timed_out) {
       string line=result_line(first.output,"DRNAS_RESULT\t");
       if(!line.empty()) {
         istringstream parsed(line);string prefix,mode,status;
         getline(parsed,prefix,'\t');getline(parsed,mode,'\t');getline(parsed,status,'\t');
         if(mode=="adaptive_plain"&&(status=="SAT"||status=="UNSAT")) {
           cout<<"DRNAS_GENERAL_RESULT\t{\"status\":\""<<status
               <<"\",\"path\":\"v76_quick\",\"budget_ms\":"<<budget<<"}\n";
           return 0;
         }
       }
     }
   }
   // No global timeout restart: outer benchmark owns 20/30 s wall-time cap.
   cout<<"DRNAS_GENERAL_ROUTE\tkissat\tprobe_ms="<<budget<<"\n"<<flush;
   char *av[]={const_cast<char*>(kissat.c_str()),const_cast<char*>(cnf.c_str()),nullptr};
   execv(av[0],av);
   throw runtime_error("Cannot exec Kissat fallback");
 } catch(const exception &e) {
   cerr<<"DRNAS_GENERAL_ERROR "<<e.what()<<"\n";return 3;
 }
}
