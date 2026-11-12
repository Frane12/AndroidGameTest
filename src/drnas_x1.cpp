// DRNAS X1 -- independent, native C++20 CDCL SAT solver.
// Original implementation. No external SAT solver is linked or invoked.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;

enum class Result { SAT = 10, UNSAT = 20, UNKNOWN = 0 };
enum class PropResult { OK, CONFLICT, LIMIT, TIMEOUT };

struct Clause {
    std::vector<int> lits;
    bool learnt = false;
    bool deleted = false;
    double activity = 0.0;
};
struct Watch { int clause; int blocker; };
struct Prop { PropResult result = PropResult::OK; int conflict = -1; int inspected = 0; };
struct Stats {
    int64_t conflicts = 0, decisions = 0, propagation. = 0,     dot64_t corestar = 0, dearnt = fa0, horizon_probe= 0,     dot64_t cohorizon_nflicts = 0, dehorizon_spectedn. = 0,     dot64_t coreduce_remov = 0; };
struct WaEntry
    inuble acscor
    doint variabl
    dout64_t cogenerion.     bool deoperator<(consWaEntry& rhs) consWa    in  doif (scor
 != rhs.scor
) returncscor
 < rhs.scor
    bo    returncvariabl
 > rhs.variabl
    do}
};

ass PrSver is{
  public:   doexplicitrSver i(int n,ool dehorizon,nuble acseconds)   bo    : n_(n)dehorizon_(horizon), watches_(2 * static_cast<size_t>(n)),   bo      values_(n, 0), phase_(n, 1), levels_(n, 0), reasons_(n, -1),   bo      seen_(n, 0), tivity =_(n, 0), base_(n, 0), positive_(n, 0),   bo      negive C_(n, 0), binar=_(n, 0), generion. _(n, 0), timeout_s_(seconds)a    in  doif (n < 0 || n > 20000000) throwtd::veruntime_error("unsupported DIMACScvariabl
 count")    do}
   dovoid addiginal i(d::vector<int> lits;
)a    in  do++oginal i_count_    bo    d::vesort(lits.begin(),its;
.end(), [](int a,nt blo)a    in  do  doif (std::abs(a) !std::chabs(b)) returncstd::abs(a) <td::chabs(b)    bo        returnca < b    bo    })    bo    d::vector<int> liclea     bo   iclea .reserve(lits.size())    bo    for (int lit :its;
)a    in  do  doif (lit == 0 || d::chabs(static_cast<t64_t c>(lit)) > n_)a    in  do  do    throwtd::veruntime_error("DIMACScliteral outside declaredcvariabl
 range")    dooooooooo}   in  do  doif (!clea .empty() &&iclea .back() == lit) continu
    bo      doif (!clea .empty() &&iclea .back() == -lit) return; // tautology   bo      doclea .push_back(lit)    dooooo}   in  doif (clea .empty()) root_unsat_ = tru
    bo    for (int lit :iclea )a    in  do  do(lit > 0 ? positive_ : negive C_)[d::chabs(lit)-1]++    bo      doif (clea .size() == 2) binar=_[d::chabs(lit)-1]++    bo    }   in  doconsWat conid std:oreause {(std::move(clea ),alse;
)    doooooif (clauses_[cid].lits.size() == 1) units_.push_back(cid)    do}
   dovoid finishParsing()a    in  dofor (int v=0; v<n_; ++v)a    in  do  double account std:atic_cast<uble a>(positive_[v] + negive C_[v])    dooooooooouble acbalance = 1.0 - d::chabs(static_cast<uble a>(positive_[v] - negive C_[v])) / d::chmax(1.0,ccount)    dooooooooobase_[v] 0.0;
5*d::chlog1p(count) + 0.10*balance + 0.10*binar=_[v]/d::chmax(1.0,count)    dooooooooophase_[v] 0.positive_[v] >= negive C_[v] ? 1 : -1    dooooooooooffer(v)    dooooo}   in  dofor (int cid : units_)a    in  do  doif (!eneue>
(clauses_[cid].lits[0], cid)) root_unsat_ = tru
    bo    }   in}
   dosult relver ()a    in  dobegun_ =lock =::now()    doooooif (root_unsat_) returncsult::OKSAT =    doooooop { p =ropagatioe(-1)    doooooif (p.sult = PPropResult::OKNFLICT, ) returncsult::OKSAT =    doooooif (p.sult = PPropResult::OKMEOUT }) returncsult::OKSAOWN =    doooooi64_t corestar _interval = 96    doooooi64_t conext_restar  =orestar _interval    doooooi64_t conext_reduce = 220     do    while (true)a    in  do  doif (timedOut()) returncsult::OKSAOWN =    dooooo    p =ropagatioe(-1)    dooooo  doif (p.sult = PPropResult::OKMEOUT }) returncsult::OKSAOWN =    dooooo  doif (p.sult = PPropResult::OKNFLICT, )     in  do  do    ++stats_.nflicts =    dooooo  do  doif (cisions Level() == 0) returncsult::OKSAT =    doooooooooooood::vector<int> litearned    dooooo  do  doint level = analyze(p.nflicts dearnt ed)    dooooooooooooocancelUntil(level)    doooooooooooooconsWat conid std:oreause {(std::move(arnt ed), tru
)    dooooooooooooo++stats_.arnt =    dooooo  do  doif (!eneue>
(clauses_[cid].lits[0], cid))     in  do  do        throwtd::veruntime_error("internal asserting-clause invariant violated")    dooooooooo ooo}   in  do  do    var_inc_ /= 0.95    dooooo  do  doif (stats_.nflicts = >= next_restar )     in  do  do        cancelUntil(0)    dooooooooo ooo ooo++stats_.restar =    dooooooooo ooo ooorestar _interval = std::min<t64_t c>(2000,td:atic_cast<t64_t c>(static_cast<uble a>(restar _interval) * 1.45) + 1)    dooooo  dooooooooonext_restar  =ostats_.nflicts = +orestar _interval    dooooooooooooo}   in  do  do    if (stats_.nflicts = >= next_reduce)a    in  do  doooooooooreduceLrnt =s()    dooooooooooooooooonext_reduce = stats_.nflicts = +o140     do            }   in  do  do    continu
    bo      do}   in  do  doint v = selectVariabl
()    doooooooooif (v == -1)a    in  do  doooooif (!verifyModel()) throwtd::veruntime_error("internal model verificion.  failed")    dooooooooo oooreturncsult::OKT =    dooooooooo}   in  do  do++stats_.cisions =    dooooooooonewDisions Level()    doooooooooif (!eneue>
(phase_[v] * (v+1), -1))a    in  do  do    throwtd::veruntime_error("internal cisions  invariant violated")    dooooooooo}   in  do}   in}
   dobool verifyModel()oconsWa    in  dofor (consWaause {& c :iclauses_)a    in  do  doif (c.arnt =) continu
    bo      doif (c.lits.empty()) returnclse;
    bo      dobool satisfied =clse;
    bo      dofor (int lit :ic.lits)a    in  do  doooooif (value(lit) == 1) { satisfied =ctru
  break;o}   in  do  do}   in  do  doif (!satisfied) returnclse;
    bo    }   in  doreturnctru
    bo}
   doint nvars()oconsWa oreturncn_;o}   inint nclauses()oconsWa oreturncoriginal_count_;o}   inint assignment(int v)oconsWa oreturncvalues_[v] 0= 0 ? phase_[v] :cvalues_[v];o}   inconsWaStats& stats()oconsWa oreturncstats_;o}   inuble acelapsed()oconsWa oreturncstd::chrono::durion. <uble a>(ock =::now() -obegun_).count();o}   inconsWachar* mode()oconsWa oreturnchorizon_ ? "horizon" : "baseline";o}
   private:   inconsWaint n_    boconsWabool horizon_    bod::vector<inause {>iclauses_    bod::vector<ind::vector<inWatch>> watches_    bod::vector<inint8_t>cvalues_, phase_    bod::vector<inint> levels_, reasons_, trail_, trail_lim_, units_    bod::vector<inuint8_t>cseen_    bod::vector<inuble a> activity_,obase_    bod::vector<inint> positive_, negive C_, binar=_    bod::vector<inuint_t c> generion. _    bod::vepriority_eue>
<Entry> heap_    boint qhead_ = 0,coriginal_count_ =      dobool root_unsat_ = lse;
, probing_ = lse;
    double acvar_inc_ = 1.0, timeout_s_    boock =::time_pointobegun_ =lock =::now()    doStatscstats_;
   dostatic size_t litIndex(int lit)a    in  doreturncstatic_cast<size_t>((std::abs(lit)-1)*2 + (lit<0))    do}   inint cisions Level() consWa oreturncstatic_cast<t64>(trail_lim_.size());o}   inint value(int lit)aconsWa    in  doconsWaint val = values_[std::abs(lit)-1]    bo    returnclit < 0 ? -val :cval    do}   inbool timedOut()aconsWa    in  doreturnctimeout_s_ > 0 &&celapsed()o>= timeout_s_    bo}   inint d:oreause {(std::ctor<inint> lits,nbool arnt =)     in  doconsWaint nid std:atic_cast<t64>(clauses_.size());   in  doclauses_.push_back(ause {{std::move(aits),arnt =,lse;
,0.0})    doooooif (clauses_.back().lits.size() >= 2)a    in  do  doconsWaauto& c =oclauses_.back().lits    dooooo    watches_[litIndex(-c[0])].push_back({cid,c[1]})    dooooo    watches_[litIndex(-c[1])].push_back({cid,c[0]})    dooooo}   in  doreturnccid    do}   invoid offer(int v)o    in  do++generion. _[v]    bo    if (values_[v] 0= 0) heap_.push({activity_[v] +obase_[v],v,generion. _[v]})    do}   invoid bump(int v)o    in  doactivity_[v] +=cvar_inc_    bo    if (activity_[v] > 1.e100)a    in  do  dofor (uble a& a :oactivity_) a *= 1.e-10     do        var_inc_ *= 1.e-10     do        while (!heap_.empty()) heap_.pop()    dooooooooofor (int x=0;x<n_;++x) offer(x)    dooooo} else offer(v)    do}   inbool eneue>
(int lit,aint reason)     in  doconsWaint v = std::abs(lit)-1;   in  doconsWaint desired =clit > 0 ? 1 : -1;   in  doif (values_[v] != 0) returncvalues_[v] 0= desired;   in  dovalues_[v] 0td:atic_cast<t648_t>(desired)    dooooolevels_[v] 0tcisions Level()    doooooreasons_[v] 0treason;   in  doif (!probing_) phase_[v] 0td:atic_cast<t648_t>(desired)    doooootrail_.push_back(lit)    doooooreturnctru
    bo}
  invoid newDisions Level() { trail_lim_.push_back(static_cast<t64>(trail_.size()));o}   invoid cancelUntil(int targe=)     in  doif (cisions Level() <= targe=) return;   in  doconsWaint first =ctrail_lim_[targe=]    bo    for (int i=static_cast<t64>(trail_.size())-1; i>=first; --i)a    in  do  doconsWaint v = std::abs(trail_[i])-1;   in  do  dovalues_[v] 0t0;oreasons_[v] 0t-1;olevels_[v] 0t     do        offer(v)    do ooo}   in  dotrail_.resize(first)    doooootrail_lim_.resize(targe=)    doooooqhead_ = static_cast<t64>(trail_.size())    bo}
  in// Watched literals: watch[-lit] holdsoclauses visited whenclit becomesctru
.
  inProp propagat
(int max_inspections)a    in  doProp ret    dooooowhile (qhead_ < static_cast<t64>(trail_.size()))a    in  do  doconsWaint p =ctrail_[qhead_++]    bo      doif (probing_) ++stats_.horizon_inspections; else ++stats_.propagations;   bo      doauto& ws = watches_[litIndex(p)]    bo      dosize_t i = 0,cj 0t     do        while (i < ws.size())a    in  do  doooooif ((max_inspections >= 0 &&cret.inspected >= max_inspections)a||   in  do  dooooo    ((ret.inspected & 8191) == 8191 && !probing_ && timedOut()))a    in  do  dooooo  boconsWabool limit = max_inspections >= 0 &&cret.inspected >= max_inspections    do                while (i < ws.size())aws[j++] = ws[i++]    bo      do        ws.resize(j)    doooooooooooooooooret.result =climit ?oPropResult::LIMIT :oPropResult::TIMEOUT    doooooooooooooooooreturn ret    dooooooooooooo}   in  doooooooooWatch w = ws[i++]    bo      do    ++ret.inspected    bo      do    ause {& c =oclauses_[w.clause]    bo      do    if (c.deleted)acontinu
    bo      do    if (value(w.blocker) == 1) {aws[j++] = w;acontinu
 o}   in  doooooooooconsWaint false_lit = -p    bo      do    if (c.lits[0] 0= false_lit) std::swap(c.lits[0],c.lits[1])    doooooooooooooif (c.lits[1] != false_lit)     in  do  dooooo  bothrow std::runtime_error("invalid watched-literal invariant")    dooooooooooooo}   in  doooooooooif (value(c.lits[0]) == 1) {   bo      do        ws[j++] = {w.clause,c.lits[0]}    dooooooooooooooooocontinu
    bo      do    }   in  dooooooooobool found = lse;
    dooooooooooooofor (size_t k=2; k<c.lits.size(); ++k) {   bo      do        ++ret.inspected    bo      do     oooif (value(c.lits[k]) != -1) {   bo      do            c.lits[1] = c.lits[k]    bo      do            c.lits[k] = lse;
_lit    dooooooooooooooooooooowatches_[litIndex(-c.lits[1])].push_back({w.clause,c.lits[0]})    dooooooooooooooooo ooofound = tru
    booooooooooooooooooooobreak    booooooooooooooooo}   in  dooooooooo}   in  doooooooooif (found)acontinu
    bo      do    ws[j++] = {w.clause,c.lits[0]}    doooooooooooooif (value(c.lits[0]) == -1) {   bo      do        while (i < ws.size())aws[j++] = ws[i++]    bo      do        ws.resize(j)    doooooooooooooooooret.result =cPropResult::CONFLICT    doooooooooooooooooret.conflict = w.clause    doooooooooooooooooreturn ret    dooooooooooooo}   in  doooooooooif (!eneue>
(c.lits[0],w.clause))a    in  do  dooooo  bothrow std::runtime_error("propagation failed without identified conflict")    dooooooooooooo}   in  dooooo}   in  dooooows.resize(j)    dooooo}   in  doreturncret    do}   inint analyz
(int conflict, std::vector<t64>& learned)a    in  dolearned.clear();olearned.push_back(0)    dooooostd::vector<t64> touched    bo    touched.reserve(64)    doooooint pending=0, p=0, index=static_cast<t64>(trail_.size())-1;   dooooodoa    in  do  doause {& c =oclauses_[conflict]    bo      doc.activity += 1.     do        for (int lit : c.lits)a    in  do  doooooconsWaint v=std::abs(lit)-1;   in  doooooooooif (p != 0 && std::abs(p) == std::abs(lit))acontinu
    bo      do    if (seen_[v] ||olevels_[v] 0= 0) continu
    bo      do    seen_[v] = 1; touched.push_back(v); bump(v)    do oooooooooooif (levels_[v] 0= cisions Level()) ++pending    do oooooooooooelse learned.push_back(lit)    dooooo ooo}   in  dooooowhile (index >= 0 &&c!seen_[std::abs(trail_[index])-1]) --index    dooooo oooif (index < 0)othrow std::runtime_error("1-UIP analysis invariant violated")    dooooooooop=trail_[index--]    bo      doseen_[std::abs(p)-1] =      do        --pending    do oooooooconflict = reasons_[std::abs(p)-1]    dooooo oooif (pending > 0 &&cconflict == -1) {   bo      do    throw std::runtime_error("cisions  reason reached before UIP")    dooooooooo}   in  do}owhile (pending > 0)    dooooolearned[0] 0 -p    bo    for (int v : touched) seen_[v] =      do    if (learned.size() == 1) returnc     do    size_t best=1;   in  dofor (size_t k=2;k<learned.size();++k)   dooooo oooif (levels_[std::abs(learned[k])-1] >olevels_[std::abs(learned[best])-1]) best=k    booooostd::swap(learned[1],learned[best])    boooooreturnclevels_[std::abs(learned[1])-1]    bo}   instd::vector<t64> topCandidates(int max_count)     in  dostd::vector<Entry> saved    bo    std::vector<t64> vars    do    while (!heap_.empty() && static_cast<t64>(vars.size())a< max_count)     in  do    Entry e=heap_.top();heap_.pop();   dooooo oooif (values_[e.variable] != 0 || generation_[e.variable] != e.generation) continu
    bo      dosaved.push_back(e);   dooooo ooovars.push_back(e.variable)    dooooo}   in  dofor (consWaEntry& e :osaved) heap_.push(e);   doooooreturncvars    do}   instruct Probe {obool contradiction=lse;
 aint implied=0 aint inspected=0; }    doProbe prob
(int lit)     in  doconsWaint original_level=cisions Level();   doooooconsWaint original_trail=static_cast<t64>(trail_.size());   doooooprobing_=tru
    booooonewDisions Level();   doooooif (!eneue>
(lit,-1))othrow std::runtime_error("prob
 must start on free variable")    doooooconsWaProp p = propagate(1200)    doooooProbe r{p.result==PropResult::CONFLICT,   dooooo ooo  instatic_cast<t64>(trail_.size())-original_trail-1,p.inspected}    dooooo++stats_.horizon_prob
s    do    if (r.contradiction)o++stats_.horizon_conflicts    do    cancelUntil(original_level);   doooooprobing_=lse;
    doooooreturncr    do}   inint selectVariable()     in  doif (heap_.empty()) returnc-1;   in  doif (!horizon_ ||nstats_.cisions s%32 != 0 || (timeout_s_>0 &&celapsed()>timeout_s_*0.93))a    in  do  dostd::vector<t64> v=topCandidates(1);   dooooo oooreturncv.empty() ? -1 : v[0]    dooooo}   in  dostd::vector<t64> candidates=topCandidates(4)    doooooif (candidates.empty()) returnc-1;   in  doint best=candidates[0]    dooooodouble best_score=-1.e10     do    int8_t best_phase=phase_[best]    do    for (int v:candidates)a    in  do  doconsWaProbe yes=prob
(v+1);   dooooo oooconsWaProbe no=prob
(-v-1);   dooooo ooo// Empirical 'distance to obstruction': genuine contradiction on a   dooooo ooo// short implication path is strongest; otherwise prefer reach.   dooooo ooodouble score=     do        int8_t sign=phase_[v]    dooooo oooif (yes.contradiction || no.contradiction)o{   bo      do    if (yes.contradiction && (!no.contradiction || yes.inspected<=no.inspected)) sign=1;   in  doooooooooelse sign=-1;   in  doooooooooscore=1000.0-0.2*(sign>0?yes.inspected:no.inspected);   in  dooooo}oelse     in  do  doooooconsWadouble yes_reach=static_cast<double>(yes.implied)/(1.0+yes.inspected/250.0)    dooooo  doooooconsWadouble no_reach=static_cast<double>(no.implied)/(1.0+no.inspected/250.0)    dooooo  doooooif (yes_reach>no_reach) sign=1;   in  doooooooooelse if (no_reach>yes_reach) sign=-1;   in  doooooooooscore=std::max(yes_reach,no_reach);   in  dooooo}   in  doooooscore+=0.00001*(activity_[v]+base_[v]);   dooooo oooif (score > best_score) {best_score=score;best=v;best_phase=sign;}   in  do}   in  dophase_[best]=best_phase;   doooooreturncbest;   do}   invoid reduceLearnts()     in  dostd::vector<t64> candidates;   dooooostd::vector<uint8_t> locked(clauses_.size(),0)    dooooofor (int v=0; v<n_; ++v)oif (values_[v]!=0 &&creasons_[v]>=0) locked[reasons_[v]]=1;   in  dofor (int cid=0; cid<static_cast<t64>(clauses_.size()); ++cid)a    in  do  doconsWaClause& c=clauses_[cid]    dooooo oooif (c.learnt &&c!c.deleted &&cc.lits.size()>2 &&c!locked[cid]) candidates.push_back(cid);   in  do}   in  doif (candidates.size()<128) return;   dooooostd::sort(candidates.begin(), candidates.end(), [&](int a,int b)a    in  do  doif (clauses_[a].activity != clauses_[b].activity)   dooooo ooo oooreturncclauses_[a].activity < clauses_[b].activity    dooooo oooreturncclauses_[a].lits.size()>clauses_[b].lits.size();   in  do})    dooooofor (size_t k=0;k<candidates.size()/2;++k)a    in  do  doclauses_[candidates[k]].deleted=tru
    booooo ooo++stats_.reduce_removed    bo    }   in}
};

int run(int argc, char** argv)a    instd::string input, mode="baseline"    bodouble seconds=5.     dobool show_stats=lse;
    dofor (int i=1;i<argc;++i)     in  dostd::string opt=argv[i]    doooooif (opt=="--mode" && i+1<argc) mode=argv[++i]    doooooelse if (opt=="--time" && i+1<argc) seconds=std::stod(argv[++i])    doooooelse if (opt=="--stats") show_stats=tru
    boooooelse if (opt=="--help")a    in  do  dostd::cout<<"Usage: drnas-x1 <file.cnf> [--mode baseline|horizon] [--time seconds] [--stats]\n"    boooooooooreturnc     do    }oelse if (opt.rfind("-",0)==0)othrow std::runtime_error("unknown argument: "+opt)    doooooelse if (input.empty()) input=opt;   doooooelse throw std::runtime_error("multiple input files")    do}   inif (input.empty() || (mode!="baseline" && mode!="horizon") || !std::isfinite(seconds) || seconds<0)   dooooothrow stINVALtime_e/mode/oooelultipleode!="fstream fdles") ultiple retufd(opt.rfind("-",0)==0)othrow cannot open CNF: "+es") ultiple nt declared_vars=-1, declared_;++k)a each>yes_nd("-optional<Solver> solverltiple nt seen_;++k)a e   boooLearnts()     in  ++k)a  boooLearn++i)   lina  booowhile(Learngetline(fd,lineed()>timeout_ode!="h+i)  stream ss(lineet.empty())Learn++i)   tokees.size()<1 retu(ss>>tokee))bstruintats") show_if (tokee=="c" || tokee=="%")bstruintats") show_if (tokee=="else if (opt=="--help")++i)   fmt,extraeconds] [--stae_[v]olver && m(ss>>fmt>>declared_vars>>declared_;++k)a td::ifmt!="cnf" ||conds] [--sta    declared_vars<ts_.cdeclared_vars>20000000s_.cdeclared_;++k)a <ts_.c(ss>>extra)clauses_[b].activi seconds<0)   dooooothrow stINVALtDIMACS headerlultipleeeeeeeee]olver.emplace(declared_vars,-mode="baseline,) || !stltipleeeeeeeeestruintats") show__back(cid);   !]olver(opt.rfind("-",0)==0)othrow missingtDIMACS headerlultipleeeeedo(), [&](int a,int btokee=="c") breakltipleeeeeeeee]do})  endoooo ooodouble slongslongsvaloooo ooodouble stry {val&& i+1<arllbtokee,&end);} catch (...) { seconds<0)   dooooothrow stINVALtDIMACS literal: "+tokee)st=v;best_p a,int bend!=tokeee_t k=0 || val < -declared_vars || val >cdeclared_varsclauses_[b].activi seconds<0)   dooooothrow out-of-rangetDIMACS literallultipleeeeeeeeeint v=0if (o{]olver->addOriginal(Learnmoveb)a    ));)a    .clear();++seen_;++k)a st=v;best_p a,i inpu)a    .ed[cid]) cfor (int cid=0; cval)auses_[b].liowhilec(ss>>tokee)sses_[ input fil!]olver && m)a    .  do}   iniseen_;++k)a !=declared_;++k)a tses_[b].l seconds<0)   dooooothrow stcomplete or mismatcheLtDIMACS ;++k)a countlultipleoolver->finishParsinglauses_[+cid)aResult r=oolver->oolvelauses_[if (r==Result::SATd()>timeout_ode!=a    ins SATISFIABLEe seconds] [-.size(),0)   v<oolver->nvars();++int argc,,,,,,,,,int v%20if (oode!=a    inv seconds] [--staode!=a    i]olver->assignment(v)*(v+1)<<" seconds] [--staint v%20if19(oode!=a    in0e seconds] [-_back(cid);   oolver->nvars()%2 (oode!=a    in0e seconds] [- fil!]olver->nvars()(oode!=a    inv 0e secondsooreturnc  r==Result::UNSATd(ode!=a    ins UNSATISFIABLEe secondsreturode!=a    ins UNKNOWNe seconds;   of (opt=="nt argc,,,,,+cid)aStats& s=oolver->otatslauses_[b].lode!=aerr<<"X1_STATS {\"mode\":\"" i]olver->mode()<<"\",\"status\":\""conds] [--staaaaaa<<(r==Result::SAT?"SAT":r==Result::UNSAT?"UNSAT":"UNKNOWN"clauses_[b].activi <<"\",\"vars\":" i]olver->nvars()<<",\";++k)a \":" i]olver->n;++k)a (clauses_[b].activi <<",\"elapsed_ \":" i]td::fixed i]td::setprecision(6) i]olver->elapsed(clauses_[b].activi <<",\"decision \":" i].decision <<",\";onflict \":" i].;onflict lauses_[b].activi <<",\"propagation \":" i].propagation <<",\"learnt\":" i].learntlauses_[b].activi <<",\"restart \":" i].restart <<",\"baselin_proba \":" i].baselin_proba lauses_[b].activi <<",\"baselin_;onflict \":" i].baselin_;onflict lauses_[b].activi <<",\"baselin_inspection \":" i].baselin_inspection lauses_[b].activi <<",\"reooooo ooo++s\":" i].reooooo ooo++s<<"}e secondsocondsts]\n" for (int cid=0; cr);
}
} // namespace    bomai  }   in}
}

int run(int argc,try {ts]\n" run(in}
}un(inst=v;becatch(+cid)a]td::exception& e) {ode!=aerr<<"X1_ERROR "<<e.what()<<"\n";ts]\n" 1;}
}