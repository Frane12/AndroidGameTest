// DRNAS R150: read-only bounded SATzilla-style cheap structural features.
// No CNF mutation, no clause injection, no SAT solver; optional frozen ridge score.
// Original R148/Kissat/CaDiCaL/V15.3.1 are not modified.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>
using namespace std;
static constexpr size_t MAX_BYTES=256*1024, MAX_CLAUSES=4096, DIM=16;
static double safe_div(double x,double y) {return y>0?x/y:0.0;}
static double clip(double x,double hi=1.0){return max(0.0,min(hi,x));}
int main(int argc,char**argv){
 if(argc!=2 && argc!=5){cerr<<"usage: r150_features input.cnf [model.txt BASE_ROUTE threshold]\n";return 2;}
 const filesystem::path path=argv[1];
 error_code ec;auto sz=filesystem::file_size(path,ec);
 if(ec){cerr<<"R150_BAD_INPUT_STAT\n";return 3;}
 ifstream file(path);
 if(!file){cerr<<"R150_BAD_INPUT_OPEN\n";return 3;}
 uint64_t vars=0,declared=0,n=0,bytes=0,len=0,pos=0,neg=0,total_lits=0,total_pos=0;
 uint64_t binary=0,ternary=0,horn=0,dual=0,units=0,mutex=0,atleast=0;
 uint64_t maxdeg=0,maxfan=0;
 unordered_map<int,uint32_t> degree,fan;
 degree.reserve(8192);fan.reserve(8192);
 vector<int> pair;
 bool header=false,partial=false;
 string line;
 while(getline(file,line)){
   bytes+=line.size()+1;
   if(bytes>MAX_BYTES){partial=true;break;}
   if(line.empty())continue;
   if(line[0]=='c'||line[0]=='%')continue;
   if(line[0]=='p'){
     istringstream h(line);string p,cnf;
     if(!(h>>p>>cnf>>vars>>declared)||p!="p"||cnf!="cnf"||!vars||!declared){cerr<<"R150_BAD_DIMACS_HEADER\n";return 4;}
     header=true;continue;
   }
   if(!header){cerr<<"R150_NO_HEADER\n";return 4;}
   istringstream in(line);
   int64_t lit=0;
   while(in>>lit){
     if(lit){
       if(lit > static_cast<int64_t>(vars)||lit < -static_cast<int64_t>(vars)){cerr<<"R150_LITERAL_RANGE\n";return 4;}
       ++len; if(lit>0)++pos;else++neg;
       if(pair.size()<2)pair.push_back(static_cast<int>(lit));
       if(degree.size()<300000||degree.count(static_cast<int>(abs(lit)))){
         auto &d=degree[static_cast<int>(abs(lit))];++d;maxdeg=max(maxdeg,static_cast<uint64_t>(d));
       }
     }else{
       ++n;
       total_lits+=len;total_pos+=pos;
       binary+=(len==2);ternary+=(len==3);units+=(len==1);
       horn+=(pos<=1);dual+=(neg<=1);
       if(len==2&&pair.size()==2&&pair[0]!=pair[1]&&pair[0]!=-pair[1]){
          mutex+=(pair[0]<0&&pair[1]<0);
          atleast+=(pair[0]>0&&pair[1]>0);
          if(fan.size()<200000||fan.count(-pair[0])){
             auto &d=fan[-pair[0]];++d;maxfan=max(maxfan,static_cast<uint64_t>(d));
          }
          if(fan.size()<200000||fan.count(-pair[1])){
             auto &d=fan[-pair[1]];++d;maxfan=max(maxfan,static_cast<uint64_t>(d));
          }
       }
       len=pos=neg=0;pair.clear();
       if(n>=MAX_CLAUSES){partial=true;break;}
     }
   }
   if(partial)break;
 }
 if(!header||n==0){cerr<<"R150_NO_COMPLETE_CLAUSES\n";return 4;}
 // 16 cheap, bounded, canonical features. Prefix observations are never
 // claimed to be whole-formula proportions.
 vector<double> x={
  clip(log1p(double(sz))/15.0),
  clip(log1p(double(vars))/15.0),
  clip(log1p(double(declared))/15.0),
  clip(safe_div(double(declared),double(vars))/5.0),
  clip(safe_div(binary,n)),clip(safe_div(ternary,n)),
  clip(safe_div(horn,n)),clip(safe_div(dual,n)),
  clip(safe_div(mutex,n)),clip(safe_div(atleast,n)),
  clip(safe_div(total_lits,n)/10.0),
  clip(safe_div(total_pos,n)/5.0),
  clip(safe_div(units,n)),clip(safe_div(n,declared)),
  clip(safe_div(maxfan,sqrt(double(n)+1))),
  clip(safe_div(maxdeg,sqrt(double(n)+1)))
 };
 if(x.size()!=DIM){cerr<<"R150_INTERNAL_FEATURE_COUNT\n";return 5;}
 cout<<fixed<<setprecision(9);
 cout<<"c R150_FEATURE dims="<<DIM<<" x=";
 for(size_t i=0;i<DIM;i++)cout<<(i?",":"")<<x[i];
 cout<<" observed="<<n<<" declared="<<declared<<" source_bytes="<<sz
     <<" sampled="<<(partial?1:0);
 if(argc==5){
   ifstream model(argv[2]);string magic;model>>magic;
   if(!model||magic!="R150_RIDGE16_V1"){cerr<<"\nR150_BAD_MODEL\n";return 6;}
   double intercept=0;model>>intercept;if(!model){cerr<<"\nR150_BAD_INTERCEPT\n";return 6;}
   double score=intercept;
   for(auto f:x){double w=0;model>>w;if(!model||!isfinite(w)){cerr<<"\nR150_BAD_WEIGHTS\n";return 6;}score+=f*w;}
   string extra;if(model>>extra){cerr<<"\nR150_MODEL_EXTRA\n";return 6;}
   string baseline=argv[3];
   if(baseline!="KISSAT"&&baseline!="CADICAL"){cerr<<"\nR150_INVALID_BASE\n";return 7;}
   double threshold=0;try{threshold=stod(argv[4]);}catch(...){cerr<<"\nR150_THRESHOLD\n";return 7;}
   if(!isfinite(threshold)||threshold<0||threshold>1){cerr<<"\nR150_THRESHOLD_RANGE\n";return 7;}
   string learned=score>0?"CADICAL":"KISSAT";
   string route=abs(score)>=threshold?learned:baseline;
   cout<<" score="<<score<<" route="<<route<<" baseline="<<baseline
       <<" changed="<<(route!=baseline?1:0)<<" threshold="<<threshold;
 }
 cout<<"\n";return 0;
}
