// DRNAS R152: single-process deterministic stratified structural sampling.
// Original CNF is never modified. At most 3*64KiB and 3*1024 clauses are read.
// A confidence bound on full PAR-2 regret determines whether to abstain to Kissat.
// Modes: features-only for historical 400, or risk prediction on frozen model.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <string>
#include <utility>
#include <vector>
using namespace std;
static constexpr size_t DIM=24,WINDOW=65536,MAX_CLAUSES=1024;
double clip(double x,double hi=1.) {return max(0.,min(hi,x));}
double div0(double x,double y) {return y>0.?x/y:0.;}
struct Window {
 double binary=0,horn=0,ternary=0,positive=0,length=0,coverage=0;
};
Window scan(const filesystem::path &path,uint64_t start,uint64_t bytes,uint64_t vars){
 ifstream f(path,ios::binary);
 if(!f){throw runtime_error("unable_to_open_source");}
 f.seekg(static_cast<streamoff>(start),ios::beg);
 if(start>0){
   string discard;
   getline(f,discard); // Skip possibly incomplete leading DIMACS line.
 }
 uint64_t used=0,clauses=0,binary=0,horn=0,ternary=0,total_pos=0,total_lits=0;
 uint64_t len=0,pos=0;
 string line;
 while(used<bytes && clauses<MAX_CLAUSES && getline(f,line)){
   used+=line.size()+1;
   if(used>bytes)break;
   if(line.empty())continue;
   if(line[0]=='c'||line[0]=='p'||line[0]=='%')continue;
   istringstream in(line);
   long long lit=0;
   while(in>>lit){
     if(lit!=0){
       if(lit>static_cast<long long>(vars)||lit < -static_cast<long long>(vars))
           throw runtime_error("literal_out_of_declared_range");
       ++len;
       if(lit>0)++pos;
     }else{
       ++clauses;
       binary+=(len==2);
       ternary+=(len==3);
       horn+=(pos<=1);
       total_lits+=len;
       total_pos+=pos;
       len=pos=0;
       if(clauses>=MAX_CLAUSES)break;
     }
   }
 }
 Window w;
 w.binary=clip(div0(binary,clauses));
 w.horn=clip(div0(horn,clauses));
 w.ternary=clip(div0(ternary,clauses));
 w.length=clip(div0(total_lits,clauses)/10.);
 w.positive=clip(div0(total_pos,total_lits));
 w.coverage=clip(div0(clauses,MAX_CLAUSES));
 return w;
}
int main(int argc,char **argv){
 try {
   if(argc!=2 && argc!=4){cerr<<"usage: r152_selector ORIGINAL.cnf [frozen24.model z]\n";return 2;}
   const filesystem::path src=argv[1];
   error_code ec;
   uint64_t bytes=filesystem::file_size(src,ec);
   if(ec||bytes==0){cerr<<"R152_SOURCE_STAT_FAILED\n";return 3;}
   ifstream f(src,ios::binary);
   if(!f){cerr<<"R152_SOURCE_UNREADABLE\n";return 3;}
   string line;uint64_t vars=0,declared=0;
   size_t header_scan=0;bool got=false;
   while(getline(f,line)){
      header_scan+=line.size()+1;
      if(header_scan>131072){cerr<<"R152_HEADER_TOO_DEEP\n";return 4;}
      if(line.empty()||line[0]=='c')continue;
      istringstream in(line);string p,cnf;
      if(!(in>>p>>cnf>>vars>>declared)||p!="p"||cnf!="cnf"||!vars||!declared){
         cerr<<"R152_INVALID_HEADER\n";return 4;
      }
      got=true;break;
   }
   if(!got){cerr<<"R152_NO_HEADER\n";return 4;}
   uint64_t tail=(bytes>WINDOW?bytes-WINDOW:0);
   uint64_t mid=tail/2;
   vector<Window> w;
   w.push_back(scan(src,0,WINDOW,vars));
   w.push_back(scan(src,mid,WINDOW,vars));
   w.push_back(scan(src,tail,WINDOW,vars));
   vector<double>x={clip(log1p(double(bytes))/15.),
     clip(log1p(double(vars))/15.),clip(log1p(double(declared))/15.),
     clip(div0(declared,vars)/5.)};
   for(auto &a:w) {
     x.push_back(a.binary);x.push_back(a.horn);
     x.push_back(a.ternary);x.push_back(a.length);
     x.push_back(a.positive);x.push_back(a.coverage);
   }
   auto lo_b=min({w[0].binary,w[1].binary,w[2].binary});
   auto hi_b=max({w[0].binary,w[1].binary,w[2].binary});
   auto lo_h=min({w[0].horn,w[1].horn,w[2].horn});
   auto hi_h=max({w[0].horn,w[1].horn,w[2].horn});
   x.push_back(hi_b-lo_b);x.push_back(hi_h-lo_h);
   if(x.size()!=DIM)throw runtime_error("internal_feature_dimension");
   cout<<fixed<<setprecision(9)<<"c R152_FEATURE x=";
   for(size_t i=0;i<DIM;i++)cout<<(i?",":"")<<x[i];
   cout<<" sampled_windows=3 bytes="<<bytes<<" declared="<<declared;
   if(argc==4){
     ifstream model(argv[2]);
     string magic;size_t count=0,k=0,dim=0;
     if(!(model>>magic>>count>>k>>dim)||magic!="R152_KNN24_V1"||
        count!=400||k<8||k>count||dim!=DIM)
        throw runtime_error("bad_frozen_model_header");
     vector<double> sigma(DIM);
     for(double &v:sigma)if(!(model>>v)||!isfinite(v)||v<0.025||v>2.)
         throw runtime_error("bad_feature_scale");
     vector<std::pair<double,double>> dists;
     dists.reserve(count);
     for(size_t j=0;j<count;j++){
       double ds=0;
       for(size_t i=0;i<DIM;i++){
         double v=0;
         if(!(model>>v)||!isfinite(v)||v<0||v>1)
             throw runtime_error("bad_training_feature");
         const double z=(x[i]-v)/sigma[i];
         ds+=z*z;
       }
       double delta=0;
       if(!(model>>delta)||!isfinite(delta)||abs(delta)>61.)
           throw runtime_error("bad_training_cost");
       dists.emplace_back(ds,delta);
     }
     string extra;
     if(model>>extra)throw runtime_error("trailing_frozen_model");
     const double confidence=stod(argv[3]);
     if(!isfinite(confidence)||confidence<.25||confidence>2.)
         throw runtime_error("invalid_confidence");
     partial_sort(dists.begin(),dists.begin()+k,dists.end());
     double mean=0,var=0;
     for(size_t i=0;i<k;i++)mean+=dists[i].second;
     mean/=double(k);
     for(size_t i=0;i<k;i++)var+=pow(dists[i].second-mean,2.);
     var/=double(k-1);
     double se=sqrt(var/double(k));
     bool cadical=mean+confidence*se < -0.5;
     cout<<" route="<<(cadical?"CADICAL":"KISSAT")
         <<" risk_delta="<<mean<<" risk_se="<<se
         <<" abstained="<<(cadical?0:1)<<" neighbors="<<k;
   }
   cout<<"\n";
   return 0;
 }catch(const exception&ex){
   cerr<<"R152_SELECTOR_ERROR "<<ex.what()<<"\n";return 6;
 }
}
