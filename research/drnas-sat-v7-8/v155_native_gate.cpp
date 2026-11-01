// DRNAS V15.5: frozen conservative feature selector from 240 training and
// 120 validation formulas. No access to family labels or answers. This router
// does NOT claim novel SAT solving; it sends the original DIMACS unchanged to
// either frozen V15.3 or pinned Kissat. Additional holdout must measure the
// entire router, including scan and process startup.
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
static bool get_signature(const std::string& filename,std::string& signature){
 struct stat st{};
 if(stat(filename.c_str(),&st)!=0||st.st_size<=0||st.st_size>16*1024*1024)return false;
 std::ifstream in(filename);
 if(!in)return false;
 int n=0,header_m=-1,m=0,units=0,binary=0,negative=0,pos_wide=0,max_width=0;
 std::map<std::array<int,10>,int> xor_counts;
 std::vector<int> pending;
 std::string line;
 while(std::getline(in,line)){
  std::istringstream ss(line);
  std::string tok;
  if(!(ss>>tok)||tok=="c"||tok=="%")continue;
  if(tok=="p"){
   std::string format,more;
   if(n||!(ss>>format>>n>>header_m)||format!="cnf"||
      n<=0||n>4096||header_m<0||header_m>100000)return false;
   continue;
  }
  if(!n)return false;
  do{
   if(tok=="c")break;
   char* end=nullptr;
   errno=0;
   const long val=std::strtol(tok.c_str(),&end,10);
   if(errno||end==tok.c_str()||*end||std::labs(val)>n)return false;
   if(val){
    pending.push_back(int(val));
    if(pending.size()>8192)return false;
    continue;
   }
   const int width=int(pending.size());
   if(!width)return false;
   ++m;
   if(m>header_m)return false;
   max_width=std::max(max_width,width);
   if(width==1)units++;
   if(width==2){
    binary++;
    if(pending[0]<0&&pending[1]<0)negative++;
   }
   if(width>=3&&width<=32 &&
      std::all_of(pending.begin(),pending.end(),[](int x){return x>0;}))pos_wide++;
   if(width>=3&&width<=10){
    std::array<int,10> support{};
    std::vector<int> vars;vars.reserve(pending.size());
    for(int lit:pending)vars.push_back(std::abs(lit));
    std::sort(vars.begin(),vars.end());
    if(std::adjacent_find(vars.begin(),vars.end())==vars.end()){
     std::copy(vars.begin(),vars.end(),support.begin());
     xor_counts[support]++;
    }
   }
   pending.clear();
  }while(ss>>tok);
 }
 if(header_m!=m||!pending.empty()||m==0)return false;
 int xor_mass=0;
 for(const auto& [key,v]:xor_counts)if(v>=4)xor_mass+=v;
 const int b0=n<=48?0:n<=128?1:2;
 const int b1=units==0?0:units<=8?1:2;
 const int b2=double(binary)/m<.25?0:double(binary)/m<.75?1:2;
 const int b3=double(negative)/m<.12?0:double(negative)/m<.35?1:2;
 const int b4=pos_wide<3?0:1;
 const int b5=max_width<=3?0:max_width<=6?1:2;
 const int b6=xor_mass==0?0:double(xor_mass)/m<.40?1:2;
 signature=std::to_string(b0)+"-"+std::to_string(b1)+"-"+std::to_string(b2)+
           "-"+std::to_string(b3)+"-"+std::to_string(b4)+"-"+
           std::to_string(b5)+"-"+std::to_string(b6);
 return true;
}
static bool choose_kissat(const std::string& signature){
 // Frozen from v155-validation-120-and-frozen-selector, 2026-11-01.
 return signature=="0-0-1-2-1-1-0" ||
        signature=="0-0-2-2-1-0-0" ||
        signature=="1-0-0-0-1-1-0";
}
int main(int argc,char** argv){
 if(argc!=4 && !(argc==5&&std::string(argv[4])=="--classify-only")){
  std::cerr<<"Usage: v155_native CNF KISSAT_PATH V153_PATH [--classify-only]\n";
  return 2;
 }
 std::string signature;
 bool recognized=get_signature(argv[1],signature);
 bool choose=recognized&&choose_kissat(signature);
 if(argc==5){
  std::cout<<"DRNAS_V155_SIGNATURE\t"<<(recognized?signature:"UNKNOWN")<<"\t"
           <<(choose?"kissat":"v153")<<"\n";
  return 0;
 }
 std::cout<<"DRNAS_V155_ROUTE\t"<<(choose?"kissat":"v153")<<"\t"
          <<(recognized?signature:"UNKNOWN")<<"\n"<<std::flush;
 if(choose){
  char* args[]={argv[2],argv[1],nullptr};
  execv(argv[2],args);
 }else{
  char seed[]="1";
  char* args[]={argv[3],argv[1],argv[2],seed,nullptr};
  execv(argv[3],args);
 }
 std::cerr<<"V155_NATIVE_EXEC_FAILED "<<errno<<"\n";
 return 3;
}
