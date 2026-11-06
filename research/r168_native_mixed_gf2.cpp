// DRNAS R168: native C++ two-way GF2 <-> CaDiCaL mixed-CNF cooperation.
// Original CNF never removed or rewritten. Only source-complete XOR patterns
// and their exact GF(2) sums may propagate; every implied literal supplies a
// cached CNF reason to IPASIR-UP on request. CDCL decisions/backtracks update
// the incremental XOR row state through previously audited R164 bridge.
// This is research-only: native UNSAT lacks independent LRAT/FRAT verification.
//
// Include two previously audited source implementations; rename their mains.
#define main r168_legacy_r167_main
#include "r167_native_exact_gf2.cpp"
#undef main
#include "r168_proven_gf2_bridge.cpp"

static void r168_check(bool ok,const string& msg){
    if(!ok)throw runtime_error("R168_FAIL_CLOSED: "+msg);
}
struct R168Opts {
    string source,mode="mixed",proof;
    double cap=20.0;
    size_t max_source=384,max_extra=64;
};
static R168Opts r168_args(int argc,char**argv){
    R168Opts opt;
    r168_check(argc>=2,"usage: native source.cnf --mode mixed|clean --cap 20 [--proof path]");
    opt.source=argv[1];
    for(int i=2;i<argc;i++){
        string x=argv[i];
        if(x=="--mode"&&i+1<argc)opt.mode=argv[++i];
        else if(x=="--force-clean")opt.mode="clean";
        else if(x=="--cap"&&i+1<argc)opt.cap=stod(argv[++i]);
        else if(x=="--proof"&&i+1<argc)opt.proof=argv[++i];
        else if(x=="--max-source"&&i+1<argc)opt.max_source=stoul(argv[++i]);
        else if(x=="--max-derived"&&i+1<argc)opt.max_extra=stoul(argv[++i]);
        else throw runtime_error("R168_BAD_OPTION "+x);
    }
    r168_check(opt.mode=="mixed"||opt.mode=="clean","invalid mode");
    r168_check(isfinite(opt.cap)&&opt.cap>=0.1&&opt.cap<=3600,"invalid cap");
    // A deliberately bounded pilot: no unbounded GF2 callback incidence.
    r168_check(opt.max_source>=1&&opt.max_source<=512 &&
               opt.max_extra<=128,"unsafe row budget");
    return opt;
}
static vector<XorRow> r168_import(const Detection& d,size_t limit){
    // Source-only import. No profiling, no runtime hints, no CNF edits.
    // A singleton XOR is already a source unit that CDCL handles directly.
    vector<XorRow> candidates;
    set<pair<vector<int>,int>> seen;
    for(const Row& r:d.rows){
        if(r.vars.size()<2||r.vars.size()>6)continue;
        if(seen.insert({r.vars,int(r.rhs)}).second)
            candidates.push_back({r.vars,int(r.rhs)});
    }
    stable_sort(candidates.begin(),candidates.end(),
         [](const XorRow&a,const XorRow&b){
             if(a.vars.size()!=b.vars.size())return a.vars.size()<b.vars.size();
             return a.vars<b.vars;
         });
    if(candidates.size()>limit)candidates.resize(limit);
    return candidates;
}
static bool r168_source_witness(const CNF& cnf,CaDiCaL::Solver& solver){
    for(const auto& clause:cnf.clauses){
        bool hit=false;
        for(int l:clause){
            int v=solver.val(abs(l));
            if((l>0&&v>0)||(l<0&&v<0)){hit=true;break;}
        }
        if(!hit)return false;
    }
    return true;
}
static void r168_print_model(const CNF&cnf,CaDiCaL::Solver* solver,
                             const vector<unsigned char>* exact_model){
    cout<<"v ";
    for(int v=1;v<=cnf.n;v++){
        bool truth=exact_model?(*exact_model)[size_t(v-1)]!=0:solver->val(v)>0;
        cout<<(truth?v:-v)<<" ";
        if((v%64)==0)cout<<"0\nv ";
    }
    cout<<"0\n";
}
static int r168_run(const R168Opts&opt){
    begin_time=Clock::now();
    CNF cnf=load_dimacs(opt.source);
    const string source_sha=sha256_file(opt.source);
    const bool control=(opt.mode=="clean");
    Detection d;
    GF2Answer exact;
    bool fast=false;
    string route="CDCL_CLEAN",status="TIMEOUT";
    double detection_sec=0;
    long imported=0,derived=0;
    // When force-clean is selected, no GF(2) preprocessing is performed.
    if(!control&&seconds()<opt.cap){
        d=detect(cnf,opt.cap);
        detection_sec=seconds();
        if(d.exact&&seconds()<opt.cap){
            exact=gaussian(cnf,d.rows,opt.cap);
            if(exact.status!="TIMEOUT"){
                fast=true;
                route="NATIVE_EXACT_GF2";
                status=exact.status;
                if(!opt.proof.empty())proof_json(opt.proof,source_sha,cnf,d,exact);
            }
        }
    }

    unique_ptr<CaDiCaL::Solver> solver;
    unique_ptr<R162Bridge> bridge;
    size_t observed=0;
    long external_source=0;
    if(!fast&&seconds()<opt.cap){
        solver=make_unique<CaDiCaL::Solver>();
        for(const auto& clause:cnf.clauses){
            for(int lit:clause)solver->add(lit);
            solver->add(0);
        }
        if(!control && seconds()<opt.cap){
            vector<XorRow> rows=r168_import(d,opt.max_source);
            external_source=long(rows.size());
            if(!rows.empty()&&opt.max_extra){
                rows=gf2_pairwise_closure(rows,opt.max_extra);
            }
            imported=external_source;
            derived=long(rows.size())-imported;
            if(!rows.empty()){
                bridge=make_unique<R162Bridge>(move(rows),cnf.n,R162Bridge::DIRECT);
                bridge->incremental_enabled=true;
                bridge->initialize_incremental();
                // Per component abstention never removes original clauses;
                // preserve a conservative gate for futile repeated scans.
                bridge->component_feedback=true;
                bridge->component_scan_gate=32768;
                solver->connect_external_propagator(bridge.get());
                set<int> vars;
                for(const XorRow&r:bridge->rows)
                    for(int v:r.vars)vars.insert(v);
                for(int v:vars)solver->add_observed_var(v);
                observed=vars.size();
                route="MIXED_GF2_CDCL";
            }else route="CDCL_NO_CERTIFIED_XOR";
        }
        if(seconds()<opt.cap){
            Deadline clock(opt.cap);
            solver->connect_terminator(&clock);
            int code=solver->solve();
            solver->disconnect_terminator();
            r168_check(code==0||code==10||code==20,"bad CaDiCaL status");
            if(code==10){
                r168_check(r168_source_witness(cnf,*solver),
                           "CDCL model invalid on untouched original CNF");
                status="SAT";
            }else if(code==20)status="UNSAT";
        }
    }
    r168_check(!bridge||!bridge->disabled,"GF2 callback invariant failed");
    double wall=seconds();
    if(wall>opt.cap&&status!="TIMEOUT"){status="TIMEOUT";route+="_OVER_CAP";}
    cout<<fixed<<setprecision(8)
        <<"R168_RESULT {\"status\":\""<<status
        <<"\",\"route\":\""<<route
        <<"\",\"mode\":\""<<opt.mode
        <<"\",\"wall_s\":"<<wall
        <<",\"cap_s\":"<<opt.cap
        <<",\"detect_s\":"<<detection_sec
        <<",\"source_sha256\":\""<<source_sha
        <<"\",\"nvars\":"<<cnf.n
        <<",\"clauses\":"<<cnf.clauses.size()
        <<",\"exact\":"<<(d.exact?"true":"false")
        <<",\"certified_rows\":"<<d.rows.size()
        <<",\"source_rows_imported\":"<<imported
        <<",\"derived_rows\":"<<derived
        <<",\"observed_vars\":"<<observed
        <<",\"gf2_proposals\":"<<(bridge?bridge->direct_proposals:0)
        <<",\"gf2_completed_reasons\":"<<(bridge?bridge->reason_clauses_completed:0)
        <<",\"gf2_reason_literals\":"<<(bridge?bridge->direct_reason_lits:0)
        <<",\"gf2_incremental_events\":"<<(bridge?bridge->incremental_row_events:0)
        <<",\"gf2_scans\":"<<(bridge?bridge->rows_scanned:0)
        <<",\"gf2_suppressed\":"<<(bridge?bridge->suppressed_rows:0)
        <<",\"gf2_blocked_components\":"<<(bridge?bridge->blocked_components():0)
        <<",\"gf2_propagate_ns\":"<<(bridge?bridge->propagate_ns:0)
        <<",\"gf2_disabled\":"<<(bridge&&bridge->disabled?1:0)
        <<"}\n"<<flush;
    cout<<"s "<<(status=="SAT"?"SATISFIABLE":
                    status=="UNSAT"?"UNSATISFIABLE":"UNKNOWN")<<"\n";
    if(status=="SAT"){
        r168_print_model(cnf,solver.get(),fast?&exact.model:nullptr);
    }
    return status=="SAT"?10:status=="UNSAT"?20:0;
}
int main(int argc,char**argv){
    try{
        if(argc==2&&string(argv[1])=="selftest"){
            DrnasBridge::watch_selftest();
            R162Bridge::selftest();
            // Direct incrementality must remain reversible for 0/1 parity.
            R162Bridge bridge({{{1,2,3},0}},3,R162Bridge::DIRECT);
            bridge.incremental_enabled=true;
            bridge.initialize_incremental();
            bridge.notify_new_decision_level();
            bridge.notify_assignment({1,2});
            r168_check(bridge.cb_propagate()==-3,"incremental GF2 propagation");
            bridge.notify_backtrack(0);
            r168_check(bridge.row_unassigned[0]==3&&
                       bridge.row_parity[0]==0,
                       "incremental rollback parity");
            cout<<"R168_NATIVE_MIXED_SELFTEST_PASS"<<endl;
            return 0;
        }
        return r168_run(r168_args(argc,argv));
    }catch(const exception&e){
        cerr<<"R168_ERROR "<<e.what()<<"\n";return 2;
    }
}
