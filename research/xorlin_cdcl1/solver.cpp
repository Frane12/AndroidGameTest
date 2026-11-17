// DRNAS XORLIN-CDCL1: one process, serial bounded source-GF(2) proof gate
// followed (only on UNKNOWN) by unchanged intrinsic DRNAS X59 CDCL.
// CPython is EMBEDDED in this executable, not launched as a subprocess.
// The mathematical algorithms are the exact SHA-pinned XORLIN1 modules
// previously externally certified with VeriPB. Porting those to C++ is
// future work; this pilot measures integration without proof drift.
//
// A solver-originated UNSAT is NOT strict until the benchmark invokes
// a separate external VeriPB/DRAT checker on the unchanged input CNF.
// Solver and verifier run sequentially under the same E2E cap.
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#define main drnas_x59_unmodified_entrypoint
#include "../../src/drnas_x59.cpp"
#undef main

namespace xorlin_cdcl1 {
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;

struct Options {
    std::string cnf,proof,mode="core",gate="on",root;
    double seconds=8.0,gate_ms=700.0;
    bool stats=false;
};
struct InterpreterGuard {
    InterpreterGuard(){Py_Initialize();if(!Py_IsInitialized())throw std::runtime_error("Python initialization failed");}
    ~InterpreterGuard(){if(Py_IsInitialized())Py_Finalize();}
    InterpreterGuard(const InterpreterGuard&)=delete;
    InterpreterGuard& operator=(const InterpreterGuard&)=delete;
};
struct PyGuard {
    PyObject* p=nullptr;
    explicit PyGuard(PyObject* ref=nullptr):p(ref){}
    ~PyGuard(){Py_XDECREF(p);}
    PyGuard(const PyGuard&)=delete;
    PyGuard& operator=(const PyGuard&)=delete;
    PyObject* get()const{return p;}
};
struct GateResult {
    bool accepted=false;
    std::string status="SKIPPED";
    size_t proof_bytes=0;
    size_t source_bytes=0;
};

Options parse(int argc,char** argv) {
    Options o;
    for(int i=1;i<argc;i++){
        std::string a=argv[i];
        auto val=[&]()->std::string{
            if(i+1>=argc)throw std::runtime_error("missing value for "+a);
            return argv[++i];};
        if(a=="--gate")o.gate=val();
        else if(a=="--gate-ms")o.gate_ms=std::stod(val());
        else if(a=="--time")o.seconds=std::stod(val());
        else if(a=="--proof")o.proof=val();
        else if(a=="--mode")o.mode=val();
        else if(a=="--repo-root")o.root=val();
        else if(a=="--stats")o.stats=true;
        else if(a=="--help"){
            std::cout<<"DRNAS XORLIN-CDCL1 <file.cnf> --gate on|off "
                       "--time seconds --gate-ms milliseconds --proof file\n";
            std::exit(0);
        }
        else if(a.size()>0&&a[0]=='-')
            throw std::runtime_error("invalid hybrid argument: "+a);
        else if(o.cnf.empty())o.cnf=a;
        else throw std::runtime_error("multiple CNF inputs");
    }
    if(o.cnf.empty() || o.proof.empty() || (o.gate!="on"&&o.gate!="off") ||
       o.mode!="core" || !std::isfinite(o.seconds) || o.seconds<=0 ||
       o.seconds>3600 || !std::isfinite(o.gate_ms) || o.gate_ms<0 ||
       o.gate_ms>1500)
       throw std::runtime_error("invalid hybrid source, proof, mode or budget");
    if(o.root.empty())o.root=fs::current_path().string();
    o.root=fs::absolute(o.root).string();
    o.cnf=fs::absolute(o.cnf).string();
    o.proof=fs::absolute(o.proof).string();
    if(!fs::is_regular_file(o.cnf))
        throw std::runtime_error("CNF source missing");
    return o;
}
double elapsed(const Clock::time_point& start){
    return std::chrono::duration<double>(Clock::now()-start).count();
}
void add_python_path(const fs::path& path){
    PyObject* p=PySys_GetObject("path"); // borrowed
    if(!p)throw std::runtime_error("no Python sys.path");
    PyGuard value(PyUnicode_FromString(path.string().c_str()));
    if(!value.get()||PyList_Insert(p,0,value.get())!=0)
        throw std::runtime_error("embedded Python path setup failed");
}
bool safe_unknown_from_python(){
    if(PyErr_ExceptionMatches(PyExc_ValueError)||
       PyErr_ExceptionMatches(PyExc_OverflowError)||
       PyErr_ExceptionMatches(PyExc_UnicodeError)){
        PyErr_Clear();
        return true;
    }
    PyErr_Print();
    return false;
}
GateResult attempt_gate(const Options& o,const Clock::time_point& started){
    GateResult result;
    constexpr uintmax_t MAX_GATE_SOURCE=500000;
    const auto bytes=fs::file_size(o.cnf);
    result.source_bytes=static_cast<size_t>(bytes);
    if(bytes>MAX_GATE_SOURCE){result.status="SOURCE_TOO_LARGE";return result;}
    if(o.gate_ms<1){result.status="BUDGET_ZERO";return result;}
    const double soft_sec=std::min(o.gate_ms/1000.0,
                 std::max(0.0,o.seconds-elapsed(started)-0.03));
    if(soft_sec<0.01){result.status="NOT_ENOUGH_BUDGET";return result;}
    const Clock::time_point gate_started=Clock::now();
    std::ifstream in(o.cnf,std::ios::binary);
    if(!in)throw std::runtime_error("cannot open CNF for integrated gate");
    std::string raw((std::istreambuf_iterator<char>(in)),
                    std::istreambuf_iterator<char>());
    if(raw.size()!=bytes)throw std::runtime_error("CNF read truncated");
    result.status="NO_INCONSISTENT_GF2_SUBSET";
    InterpreterGuard interpreter;
    try {
        add_python_path(fs::path(o.root)/"research"/"xorlin1");
        add_python_path(fs::path(o.root)/"research"/"math5");
        PyGuard extraction(PyImport_ImportModule("extract"));
        if(!extraction.get()){
            PyErr_Print();
            throw std::runtime_error("certified XORLIN1 extract import failed");
        }
        PyGuard derive(PyObject_GetAttrString(extraction.get(),"derive"));
        PyGuard original(PyBytes_FromStringAndSize(raw.data(),static_cast<Py_ssize_t>(raw.size())));
        if(!derive.get()||!original.get())
            throw std::runtime_error("certified source extractor unavailable");
        PyGuard selection(PyObject_CallFunctionObjArgs(derive.get(),original.get(),nullptr));
        if(!selection.get()){
            if(safe_unknown_from_python()){result.status="SOURCE_UNSUPPORTED";return result;}
            throw std::runtime_error("source-GF2 extraction failure");
        }
        if(!PyTuple_Check(selection.get())||PyTuple_Size(selection.get())!=2)
            throw std::runtime_error("unexpected certified GF2 return");
        PyObject* cert=PyTuple_GetItem(selection.get(),0); // borrowed
        if(cert==Py_None){return result;}
        if(elapsed(gate_started)>=soft_sec){
            result.status="SCOUT_SOFT_BUDGET";return result;
        }
        PyGuard proof_module(PyImport_ImportModule("emit_veripb"));
        if(!proof_module.get()){
            PyErr_Print();throw std::runtime_error("certified XORLIN1 emitter import failed");
        }
        PyGuard compiler(PyObject_GetAttrString(proof_module.get(),"compile_source"));
        if(!compiler.get())
            throw std::runtime_error("certified proof emitter unavailable");
        PyGuard compiled(PyObject_CallFunctionObjArgs(compiler.get(),original.get(),cert,nullptr));
        if(!compiled.get()){
            if(safe_unknown_from_python()){
                result.status="CERTIFICATE_UNSUPPORTED";
                return result;
            }
            throw std::runtime_error("standard proof emission failure");
        }
        if(!PyTuple_Check(compiled.get())||PyTuple_Size(compiled.get())!=2)
            throw std::runtime_error("invalid standard proof result");
        PyObject* proof_text=PyTuple_GetItem(compiled.get(),0);
        Py_ssize_t n=0;
        const char* encoded=PyUnicode_AsUTF8AndSize(proof_text,&n);
        if(!encoded||n<=0||n>8000000)
            throw std::runtime_error("standard proof bytes invalid");
        if(elapsed(gate_started)>=soft_sec){
            result.status="SCOUT_SOFT_BUDGET";return result;
        }
        // No proof is visible to the benchmark before all in-process
        // source checks and the full RED/RUP/CP compiler succeed.
        fs::path p(o.proof),temp=o.proof+".part";
        std::ofstream out(temp,std::ios::binary|std::ios::trunc);
        if(!out)throw std::runtime_error("cannot write standard proof");
        out.write(encoded,n);
        out.close();
        if(!out){fs::remove(temp);throw std::runtime_error("truncated standard proof");}
        fs::rename(temp,p);
        result.accepted=true;
        result.status="PBP_EMITTED_EXTERNAL_CHECK_REQUIRED";
        result.proof_bytes=static_cast<size_t>(n);
        return result;
    }catch(...){
        // PyGuard objects may hold PyObjects; failing is fatal rather
        // than claiming an unverified UNSAT. The process exits here.
        throw;
    }
}
int fallback_cdcl(const Options& o,double remaining){
    if(remaining<=0.008){std::cout<<"s UNKNOWN\n";return 0;}
    std::vector<std::string> args={
        "drnas-x59-embedded",o.cnf,"--mode","core","--time",
        std::to_string(remaining),"--proof",o.proof
    };
    if(o.stats)args.push_back("--stats");
    std::vector<char*> argv;
    argv.reserve(args.size()+1);
    for(auto& value:args)argv.push_back(value.data());
    argv.push_back(nullptr);
    // This is a normal C++ function call into the unchanged CDCL
    // compilation unit, NEVER a subprocess or second solver process.
    return run(static_cast<int>(args.size()),argv.data());
}
int program(int argc,char** argv){
    auto started=Clock::now();
    const auto o=parse(argc,argv);
    std::error_code ec;
    fs::remove(o.proof,ec);
    fs::remove(o.proof+".part",ec);
    if(o.gate=="on"){
        GateResult g=attempt_gate(o,started);
        std::cerr<<"XORLIN_CDCL1_GATE {\"status\":\""<<g.status
                 <<"\",\"proof_bytes\":"<<g.proof_bytes
                 <<",\"source_bytes\":"<<g.source_bytes
                 <<",\"elapsed_s\":"<<elapsed(started)<<"}\n";
        if(g.accepted){
            std::cout<<"c XORLIN_CDCL1_ROUTE GATE_VERIPB\n"
                        "s UNSATISFIABLE\n";
            return 20;
        }
    }
    std::cout<<"c XORLIN_CDCL1_ROUTE CDCL_DRAT\n";
    return fallback_cdcl(o,o.seconds-elapsed(started));
}
} // namespace xorlin_cdcl1

int main(int argc,char** argv){
    try{return xorlin_cdcl1::program(argc,argv);}
    catch(const std::exception& e){
        std::cerr<<"XORLIN_CDCL1_CRITICAL_ERROR "<<e.what()<<"\n";
        return 1;
    }
}
