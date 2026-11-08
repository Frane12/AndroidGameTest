# DRNAS MRE6e/MRE6f — certificirana redukcija i stvarni CDCL učinak

**Datum:** 2026-11-08  
**Status:** MRE6e PASS 56/56 i MRE6f PASS 72/72; rezultati su **razvojna dijagnostika**, a ne dokaz ubrzanja rješavanja SAT/UNSAT niti neviđeni blind holdout.  
**Referentni runovi:** [MRE6d](https://github.com/Frane12/AndroidGameTest/actions/runs/42496742982), [MRE6e](https://github.com/Frane12/AndroidGameTest/actions/runs/42499473274), [MRE6f](https://github.com/Frane12/AndroidGameTest/actions/runs/42499854392).

## Matematički i implementacijski audit

- MRE6d originalni SHA-locked SAT2026: sedam formula, četiri armova, dva ponavljanja, limit 90 s; svih 56 pokušaja su timeout; PAR-2 2520 s po armu, 0 riješenih. To **ne** mjeri ubrzanje.
- Dvije od sedam formula imaju direktno certificirane pozitivne jednakosti. U `2fcd8533…` transitive equality quotient smanjuje 11.072 klauzule na 9.728 (−12,14 %) i uklanja 672 varijable. U `a45aefde…` samo 22.688 -> 22.679 klauzula (−0,04 %) i 4 varijable.
- MRE6e koristi **isti izvorni CMS commit** `3b709118fd08eb1d15f25e0e239dbc596f967b60`, SHA-zaključane originalne CNF ulaze, isti seed u svakom paru i native `SATSolver::set_max_confl`. Bounded UNKNOWN sa stvarnim konflikt/decision/propagation brojačima **nije SAT/UNSAT riješena instanca**.
- MRE6e svih 56/56 bounded pokušaja završava BUDGET, ne TIMEOUT; nema riješenih formula. MRE6f koristi ISTI izgrađeni native bridge iz MRE6e i 72 paired pokušaja, tri ponavljanja na tri unaprijed izabrane razvojne formule. Svi auditi PASS; oba protokola izričito zabranjuju promociju.

## MRE6f: vrijeme cijelog puta, uključujući Python pripremu

| Originalna SAT2026 formula | Testni limit | Geomean CMS / all_no_xor | Medijan uštede propagacija | Zaključak |
|---|---:|---:|---:|---|
| `2fcd8533…` (post-hoc pozitivan signal) | 1.000 konflikata | 0,94748× | 35,556 % | priprema još košta više nego što štedi |
| `2fcd8533…` | 5.000 konflikata | **1,20892×** | **35,087 %** | 3/3 ponavljanja ukupno brže |
| `a45aefde…` (malo jednakosti) | 1.000 konflikata | 0,36180× | ~0,0048 % | značajna regresija |
| `a45aefde…` | 5.000 konflikata | 0,50071× | ~0,0006 % | ~2× sporije zbog pripreme |
| `de8c42d5…` (bez jednakosti) | 1.000 konflikata | 1,03213× | 0 % | bez promjene stvarne CDCL putanje; vrijeme šumi |
| `de8c42d5…` | 5.000 konflikata | 0,98709× | 0 % | bez mjerljivog uzročno-posljedičnog dobitka |

**Prvotni MRE6e par na 5.000 konflikata, `2fcd8533…`:** 6.147.559 prema 3.990.542 propagacije (−35,087 %); 6.047 prema 6.195 odluka (više odluka); 0,642810 prema 0,543998 s ukupno uključujući pripremu. Bounded rezultat nije SAT/UNSAT.

**Ponovljeni MRE6f parovi, ista formula, 5.000 konflikata:** 0,433338/0,365060 s; 0,432385/0,349957 s; 0,440878/0,365971 s (baseline/all). Propagacije su u svakom paru iste 6.147.559/3.990.542. Različiti seedovi nisu promijenili CDCL brojila u ovom ranom odsječku; te replike zato potvrđuju timing, ali **ne tri nezavisne pretraživačke putanje**. Niti jedna od 72 MRE6f proba nije potvrdila SAT/UNSAT.

## Što čuvati, što ne promovirati

1. **Zadržati** matematički sigurnu relaciju dvaju originalnih binarnih CNF klauzula i tranzitivne razrede ekvivalencije, SHA identitet, model-lifting provjeru te fallback.
2. **Ne uključivati globalno** `all_no_xor`, `all_xor` ili skupi single-principle quotient bez gatea. `a45aefde…` pokazuje da sitne jednakosti mogu pokvariti ukupno vrijeme.
3. **Ne tumačiti** fixed-conflict propagacije kao riješeni SAT/UNSAT, niti audit službenog UNSAT statusa kao nezavisni LRAT.
4. **Ne uzimati** post-hoc `2fcd8533…` kao dokaz generalizacije ili svjetski rekord.

## Sljedeći test, strogo odvojen od razvojnih formula

- Izvan ovog seta unaprijed zamrznuti 20+ izvornih, SHA-disjoint lakše rješivih SAT/UNSAT formula. Odabir po neovisnoj unaprijed definiranoj težini referentnog solverskog prolaza (npr. 0,1–5 s) *prije* mjerenja predloženog gatea, bez izbacivanja formula po uspjehu DRNAS-a.
- Cheap front-end samo za direct equality classes i procjenu stvarnog smanjenja klauzula/varijabli; compute gate odluku prije CMS mjerenja bez korištenja trajanja ili rješivosti holdouta. Formula s ogromnim smanjenjem i očekivano ne-trivijalnim CDCL-om je razvojna hipoteza, **ne** već validiran prediktor.
- Usporediti native CMS, all equality bez XOR-a, all+XOR, gate-selected i Kissat pod jednakim izvorima, seedovima, CPU pravilima i wall capom; prikazati broj riješenih, SAT provjere na originalu, neovisni UNSAT dokaz gdje je dostupan, PAR-2 i regresije.
- Odvojiti vrijeme pripreme, inprocessing, CDCL i ukupni wall; testirati zbroj koristi umjesto samog `propagations` broja.
- Ako gate ne ostvari ponovljivu pozitivnu ukupnu PAR-2 korist na neviđenom skupu, ostaviti ga disabled. 
