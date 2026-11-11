# DRNAS ATLAS16 — stanje, hipoteze i revizija 2026-11-11

## Polazište (ATLAS15 i blokovi)
- ATLAS15: u kontrolnoj varijanti C5_CDCL redakcija naučenih klauzula dolazi svakih 500 konflikata; do 50% kandidata visokog LBD se uklanja iz liste nadzora. Originalne klauzule, implikacijski razlozi i snažne LBD klauzule ostaju.
- Stariji ATLAS15 uklanjanjem prazni vektor literala, ali zadržava poziciju klauzule; zbog toga broj dosadašnjih brisanja nije isto što i stvarno smanjivanje spremišta.
- ATLAS15 smoke je pokazao minimizacije klauzula, ali na testiranim jednostavnim problemima nije pokazao aktivno brisanje; zato je potrebno mjeriti duge hard slučajeve.
- Kod ranijeg DIAG2 profiliranja najveće usko grlo bio je BCP (~94% mjerenih faznih troškova), dok je cached-blocker eksperiment imao regresiju. To nije dokaz da je svaka cache-optimizacija loša, nego upozorenje da se propagacijski redoslijed može promijeniti.
- Neki stari benchmarki imaju veliki jaz prema Kissatu i CMS-u, osobito na SATLIB random-3SAT / pigeonhole, pa se nove varijante uspoređuju na IDENTIČNIM izvornim SHA i CPU ograničenjima.

## ATLAS16 hipoteza: manje brisanja može biti brže
Odlučeno je prvo provjeriti konzervativno, a ne agresivno čišćenje.

| Mjera | Kontrola ATLAS15 C5 | Novi ATLAS16 C6_KEEP |
|---|---|---|
| Interval reduciranog naučenog DB | svakih 500 konflikata | svakih 1500 konflikata |
| Udio brisanja kandidata | 50% | 12,5% |
| LBD za izbacivanje | >3 | >=7 |
| Dužina kandidata | >2 | >=4 |
| Zaštita aktivnih razloga | da | da, provjera pri kompakciji |
| Kompaktiranje rupa u spremištu | ne | da, nakon >=64 rupa i >=10% |
| Reindeksiranje watched klauzula | nije potrebno | nakon kompaktiranja |
| Reindeksiranje CDCL reasons | nije potrebno | provjera bez kompromisa |

**Važno:** C6 nije unaprijed proglašen bržim. Povećano zadržavanje klauzula može povećati BCP pregled i RSS. Potrebni su stvarni E2E rezultati, broj riješenih i PAR2.

## Izolirana implementacija
- `research/drnas_atlas16_build.py`: zasebni generirani izvor i izvršna datoteka; stabilni `main` i postojeća kontrola C5 nisu mijenjani.
- `research/drnas_atlas16_benchmark.py`: izvorno SHA zaključane SATLIB i sintetičke formule, 1CPU, seed paired, provjera svakog original SAT modela, GF2 core neovisno verificiran kada postoji.
- `research/drnas_atlas16_schema.sql`: trajna SQL shema za originalne izvore, pokušaje, obavijesti o završenim epizodama i odabrane politike.
- `research/drnas_atlas16_merge.py`: SQL agregacija, 20/20 shardova, potpuni SHA-parovi, odvojeni PAR2 verified i PAR2 reported, distribucija memorije i referentnih pobjeda.
- `.github/workflows/drnas-atlas16-megabench.yml`: automatski slijed build -> smoke -> pass1 -> merge1 -> pass2 -> merge2 -> pass3 -> merge3.

## Veliki benchmark (plan; rezultati nisu unaprijed poznati)
- Pass 1: 500 novih originalnih/determinističkih CNF, 20 kategorija × 25 slučajeva, indeksi 35-59.
- Pass 2: drugih 500 prethodno neviđenih CNF, indeksi 60-84; strategija se koristi samo iz predhodne, SHA-razdvojene skupine.
- Pass 3: ponovljena druga skupina uz naučenu strategiju, izričito **nonblind replay**.
- Svaki prolaz: 500 CNF × 2 ponavljanja × 6 varijanti = 6000 pokušaja; sveukupno 18 000.
- Varijante: DRNAS A, ATLAS15 C5_CDCL, ATLAS16 C6_KEEP, C6_KEEP_GAUSS, Kissat (zakačeni commit) i CryptoMiniSat5 (Ubuntu 24.04).
- 10s wall E2E po pokušaju, Linux resource limit, jedan logički CPU po solveru. Bez skrivenog višesolverskog portfelja.
- 125 originalnih SATLIB + 375 determinističkih sintetičkih formula po novoj kohorti. Novi indeksi, zaključani SHA provenijencije i arhive.
- UNSAT bez neovisnog dokaznog certifikata prikazuje se kao `UNSAT_UNVERIFIED`, a u **verified PAR2** računa kao 20 sekundi. `reported PAR2` se čuva odvojeno i ne predstavlja dokazanu brzinu.

## SQLite i naučeni događaji
Baza `ATLAS16_LEARNING.sqlite` nastaje u merge1, zatim putuje isključivo kroz merge2 i merge3. Tablice `cohort`, `trial`, `decision_event`, `family_policy` osiguravaju vezu ishoda, originalnog SHA, ponavljanja i predloženog modela. Izbornik policy upotrebljava **isključivo SHA-paired rezultate s verificiranim SAT modelima**, ne neprovjerene UNSAT. Zapisi iz replaya nisu novi slijepi dokaz.

Uz svaku C6/C5 probu zapisuje se broj minimizacija, uklonjenih naučenih klauzula, kompakcija, oslobođenih utora, preostalih utora, procjena zauzete memorije za watched klauzule i peak RSS (Linux `ru_maxrss`).

## Pravila autonomnog nadzora
Postojeća satna automatizacija DRNAS SAT (Europe/Zagreb) može pregledati GitHub logove, ciljano intervenirati na eksperimentalnoj grani i ponoviti provjere. Ne smije mijenjati zamrznute reference, originalne SHA, stare rezultate ili stabilni main. Neuspjela kompilacija ili smoke mora blokirati sve sljedeće benchmark faze.

## Ažuriranje rezultata
Rezultati 18 000 pokušaja nisu poznati dok Github Actions ne završi. Mjeriti PAR2 verificirani i prijavljeni, broj riješenih, omjere ubrzanja, sve regresije i maksimalnu RSS memoriju; **nemoj proizvoljno preslikavati vrijeme stare formula na nove pokuse**.
