// V15.5 in-process A/B: exactly the same frozen feature rules as
// v155_native_gate.cpp. Avoid a second executable startup for the V15.3 path.
// On unmatched inputs call V15.3's original main in this process directly.
// This is an ENGINEERING optimization, not an improvement of the SAT theorem.
#define main drnas_v153_embedded_main
#include "v153_unified.cpp"
#undef main
#define main drnas_v155_external_main
#include "v155_native_gate.cpp"
#undef main
int main(int argc,char** argv){
 if(argc!=4 && !(argc==5 && std::string(argv[4])=="--classify-only")){
  std::cerr<<"Usage: v155_inprocess CNF KISSAT_PATH V153_PATH [--classify-only]\n";
  return 2;
 }
 std::string signature;
 bool recognized=get_signature(argv[1],signature);
 bool choice=recognized&&choose_kissat(signature);
 if(argc==5){
  std::cout<<"DRNAS_V155_SIGNATURE\t"<<(recognized?signature:"UNKNOWN")
           <<"\t"<<(choice?"kissat":"v153")<<"\n";
  return 0;
 }
 std::cout<<"DRNAS_V155_ROUTE\t"<<(choice?"kissat":"v153")<<"\t"
          <<(recognized?signature:"UNKNOWN")<<"\n"<<std::flush;
 if(choice){
  char* args[]={argv[2],argv[1],nullptr};
  execv(argv[2],args);
  std::cerr<<"V155_INPROCESS_KISSAT_FAILED "<<errno<<"\n";
  return 3;
 }
 char seed[]="1";
 char* args[]={argv[0],argv[1],argv[2],seed,nullptr};
 return drnas_v153_embedded_main(4,args);
}
