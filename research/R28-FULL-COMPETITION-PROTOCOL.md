# DRNAS R28 — prošireni originalni SAT Competition 2025/2026 benchmark (5. 11. 2026.)

## Hipoteza
R28-ova certificirana detekcija potpunih XOR blokova i GF(2) eliminacija daje stvarnu korist na određenim SAT Competition formulama. Prošireni test mora pokazati je li efekt prenosiv i općenit, uz transparentno izvješće o usporenjima. R28 je zaseban **neizmijenjeni** `experiments/drnas_v16/r28_exact_gf2.cpp` koji na mješovitim formulama bez certificiranog zaključka izvršava izvorni Kissat; to nije natjecateljski rang niti novi osnovni CDCL solver.

## Zamrznuti izvori
- Službeni main 2026 URI katalog: cilj 32 formula.
- Službeni 2025 URI katalog: cilj 32 formula.
- GBD obitelj `xor-shifting`: cilj 16.
- GBD `cryptography`: cilj 16.
- GBD `miter`: cilj 16.
- Ukupni maksimum **112 različitih originalnih CNF formula**; minimalno prihvatljiv **65** sa ≥4 obitelji i ≥28 formula iz dvaju službenih kataloga.
- Fiksni deterministički poredak iz URL-kataloga, ograničenje izvorne formule na 12 MB, najviše 260 pokušaja preuzimanja po kohorti, bez filtriranja po mjerenoj brzini ili SAT ishodu. Odbijanja/ograničenja obavezno u manifestu.
- Iz dostupnih povijesnih originalnih manifesta isključuju se SHA-256, GBD ID i URL (R115, R132, R135, R135S, 400, R148, R150, R151, R152). Nema neistinita obećanja da su isključeni svi izvori iz svih povijesnih buildova.
- Najprije se zamrznu SHA izvornika i identiteti, **tek zatim** kreću vremena solvera.
- Objavljeni natjecateljski 2026 rezultati dodaju se **nakon odabira formula**, i prikazuju odvojeno, isključivo kao međuhardverski povijesni kontekst.

## Četiri stvarna builda, isti runner
1. **R28 originalni GF(2)**: C++ iz postojećeg R28 bez izmjena, fallback na pinani čisti Kissat.
2. **Čisti Kissat 4.0.4**: provjereni pinani `r52-three-pinned-solvers`.
3. **Čisti CaDiCaL 3.0.1**: isti pinani artefakt.
4. **Službeni izvor natjecatelja SATComp 2026**: `biere.tar.xz`, kompajlirani `kissat-sc2024` iz **originalnog službenog paketa**, s SHA256 arhive i binarnog builda, uz samostalne SAT i UNSAT smoke provjere. Ako službeni paket nije moguće izgraditi, test se ne predstavlja kao usporedba s natjecateljskim buildom. **Nema zamjene drugim softverom bez izvještaja i novog eksplicitnog protokola.**

Za sve: 20 sekundi wall-clock limita, 2 ponavljanja po formuli, deterministički izmiješan redoslijed modova, ista jezgra CPU-a po shardu, 8 shardova, najviše 4 istodobna. U punoj kvoti: **896 uparenih pokušaja**. Ukupni PAR-2 40 sekundi za timeout.

**Ograničenje:** 20-sekundni limit nije službeni SAT Competition 2026 limit od nekoliko tisuća sekundi. Ovo je test prenosivosti metoda, ne službeni natjecateljski rezultat. Solver buildovi moraju biti neovisno reproducibilni i pinani SHA-om.

## Stroga provjera
- Izvorni SHA i DIMACS count, SAT model provjeren na svim izvornim klauzulama.
- R28 dokaz UNSAT na certificiranom XOR skupu neovisno rekonstruiran iz izvornih klauzula. Ostali UNSAT rezultati nemaju LRAT certifikate, osim ako naknadno budu proizvedeni i neovisno verificirani; nikakva lažna tvrdnja o certifikaciji.
- Konflikt SAT/UNSAT bilo koja dva solverska builda = audit fail-closed.
- PAR-2, broj riješenih, SAT/UNSAT, timeout, medijan vremena riješenih, prednost i regresije ≥2×, kohorte te stratificirani bootstrap 95% iz zasebnih originalnih slučajeva.
- Čitljiv završni CSV, SHA manifest, strogi audit i per-shard logovi.
- **Nikakva automatska promocija niti svjetski rekord bez neovisne potvrde i robusnosti**.

### Reference
- Raniji ograničeni XOR rezultat: https://github.com/Frane12/AndroidGameTest/actions/runs/42102968838
- R151 neviđeni test: https://github.com/Frane12/AndroidGameTest/actions/runs/42094754907
- Natjecanje 2026 — objavljeni izvori i rezultati: https://satcompetition.github.io/2026/downloads.html
- Natjecanje 2026 — pravila: https://satcompetition.github.io/2026/rules.html
