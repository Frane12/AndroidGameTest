# Zajednički obrazac skupog izbora pretrage

14. studenoga 2026. Opažačka dijagnostika postojećeg izvršnog programa, jedan CPU.

## Što je potvrđeno

- Prethodna usporedba BASE/INPLACE mijenja samo pripremu. Svih 50 native parova
  na pet lakših/srednjih originala ima iste brojače pretrage te identične modele
  ili UNSAT dokaze. Tu nije zabilježen novi izbor loše grane.
- U zasebnom kratkom tragu BASE naspram ranije odbačenog `inputs` režima, svih
  devet Simon formula s AND definicijama pokazuje isti obrazac: prioritet bira
  x225, x226, ..., x240, dok BASE kreće od bloka x1... ili x33....
- Na Simon r16 baza daje x1 ocjenu 0.28365, a x225 ocjenu 0.26397. Dodatak
  `0.25 * broj_AND_ulaza / (1 + broj_AND_izlaza)` dodaje x225 čak 0.5.
  Prethodno slabiji kandidat tako dobiva ukupno 0.76397 i prelazi ispred x1.
  Ovo je izravno očitan mehanizam promjene poretka, ne dokaz da je literal x225
  globalno nedopušten ili da je svako njegovo zadavanje loše.

## Lokalno poboljšanje nije pouzdan predznak završetka

Na r16 oba prva poteza daju 8 dodatnih BCP zaključaka, bez konflikta. Prvih
16 odluka u oba režima nema konflikta na svih devet izvora. Kontrola ipak
završi svih devet sa 32 odluke i 0 konflikata; prioritet u ovom opažačkom
100 ms prozoru ostaje UNKNOWN na svih devet. U ranijem punom pilotu na r16
ostao je UNKNOWN nakon 4.93 s i 56,968 konflikata.

Na osam od devet izvora prioritet nakon 16 odluka ima manje dodijeljenih
varijabli. Ali na r23-1 ima **764 prema 730** u kontroli, a svejedno ne završi
unutar opažačkog prozora. Zato ni veći broj dodjela ni odsutnost ranog konflikta
ne daju siguran kriterij za odbacivanje druge grane.

Tumačenje: statički dodatak za pojavnost u AND vezama nadjačava osnovni
redoslijed, a ne mjeri stvarnu korist preostalom problemu. Obrazac je potvrđen
na ovoj povezanoj Simon obitelji; prenosivost na druge obitelji nije utvrđena.

## Usporedba s Kissatom na duljem Break UNSAT-u

| Mjera | DRNAS BASE | Kissat |
|---|---:|---:|
| Odluke | 213,870 | 58,237 |
| Konflikti | 169,307 | 25,428 |
| Propagacije | 22,325,729 | 4,831,640 |

Kissat u istom logu prijavljuje 409 eliminiranih varijabli. Razlika je, prema
ovim brojačima, velikim dijelom u količini obavljenog rada. Ovo nije kontrolirani
pokus iste heuristike s istim pretprocesiranjem, pa uzrok ne možemo pripisati
samo biranju varijable. Na ostalim formulama omjeri nisu isti: DRNAS na nekima
ima manje odluka i propagacija od Kissata. Ne postoji potvrđen univerzalni
obrazac "više konflikata znači loš smjer"; osobito na UNSAT-u konflikti služe
izgradnji dokaza.

## Posljedica za MATH-GUARD

Prisutnost nelinearnog člana, kratkoročni broj propagacija i nedostatak ranog
konflikta mogu biti samo heuristički signali. Ne opravdavaju preskakanje grane.
Granu je dopušteno zatvoriti tek kada je pod njenim pretpostavkama izvedeno
provjerljivo proturječje ili valjana naučena klauzula koja je isključuje.
Ako ograničena analiza takav dokaz ne nađe, nema dokaza da je grana nemoguća.

`diagnose_branches.py` ponavlja opažanje. `branch_trace_report.json.gz` čuva
sve snimljene prijelaze, a `branch_diagnostic_summary.json` usporedni sažetak.
Stari trace meta-redak `x4_core_unmodified` je naslijeđena oznaka; stvarni
režim u ovom pokusu određuje `--nl-focus base|inputs`. Vrijeme i UNKNOWN iz
100 ms dijagnostike nisu usporedivi s prethodnim punim benchmarkom.
