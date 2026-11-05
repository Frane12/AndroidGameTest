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
 if(argc!=4){cerr<<"usage: r151_selector input.cnf model.txt confidence_z\n";return 2;}
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
 cout<<"c R151_SELECTOR dims="<<DIM<<" x=";
 for(size_t i=0;i<DIM;i++)cout<<(i?",":"")<<x[i];
 cout<<" observed="<<n<<" declared="<<declared<<" source_bytes="<<sz
     <<" sampled="<<(partial?1:0);

 // A single process computes bounded structural features and the entire
 // risk-aware decision. No additional R148 subprocess on this route.
 ifstream model(argv[2]);
 string magic;size_t ntrain=0,k=0;
 if(!(model>>magic>>ntrain>>k)||magic!="R151_KNN16_V1"||ntrain<30||ntrain>10000||k<8||k>ntrain){
   cerr<<"R151_BAD_MODEL_HEADER\n";return 6;
 }
 vector<double> sigma(DIM);
 for(size_t i=0;i<DIM;i++){
   if(!(model>>sigma[i])||!isfinite(sigma[i])||sigma[i]<0.025||sigma[i]>2){
     cerr<<"R151_BAD_MODEL_SCALE\n";return 6;
   }
 }
 vector<pair<double,double>> dists;
 dists.reserve(ntrain);
 for(size_t j=0;j<ntrain;j++){
   double distance=0.0;
   for(size_t i=0;i<DIM;i++){
      double v;
      if(!(model>>v)||!isfinite(v)||v<0||v>1){cerr<<"R151_BAD_TRAIN_FEATURE\n";return 6;}
      const double diff=(x[i]-v)/sigma[i];
      distance+=diff*diff;
   }
   double delta=0;
   if(!(model>>delta)||!isfinite(delta)||abs(delta)>61){cerr<<"R151_BAD_TRAIN_COST\n";return 6;}
   dists.emplace_back(distance,delta);
 }
 string leftover;
 if(model>>leftover){cerr<<"R151_TRAILING_MODEL_DATA\n";return 6;}
 const double confidence=stod(argv[3]);
 if(!isfinite(confidence)||confidence<0.25||confidence>3){cerr<<"R151_BAD_CONFIDENCE\n";return 7;}
 partial_sort(dists.begin(),dists.begin()+k,dists.end());
 double mean=0.0;
 for(size_t i=0;i<k;i++)mean+=dists[i].second;
 mean/=double(k);
 double var=0.0;
 for(size_t i=0;i<k;i++){
    double diff=dists[i].second-mean;
    var+=diff*diff;
 }
 var/=(k>1?double(k-1):1.0);
 const double se=sqrt(max(0.0,var/double(k)));
 // Delta = CaDiCaL PAR2 - Kissat PAR2, over 2 historical repetitions.
 // A positive expected risk or insufficient confidence abstains to Kissat.
 const bool use_cadical=mean+confidence*se < -0.5;
 cout<<" risk_mean_delta="<<mean<<" risk_se="<<se
     <<" confidence_z="<<confidence
     <<" neighbors="<<k<<" route="<<(use_cadical?"CADICAL":"KISSAT")
     <<" abstained="<<(use_cadical?0:1);
 cout<<"\n";
 return 0;
}
