// Apples-to-apples control: same Cnf parser, same pinned libkissat.a,
// same native process, NO DRNAS preprocessing. Separate from Kissat CLI.
#define main v140_embedded_main
#include "v140_native_hybrid.cpp"
#undef main
#include "kissat_api_bridge.hpp"
int main(int argc,char**argv) {
 if(argc<2){std::cerr<<"Usage: kissat_api_control INPUT.cnf\n";return 2;}
 try {
   const Cnf f=parse(argv[1]);
   return drnas_kissat_inprocess(f,"kissat_api_control");
 } catch(const std::exception& e) {
   std::cerr<<"DRNAS_API_CONTROL_ERROR "<<e.what()<<"\n";
   return 3;
 }
}
