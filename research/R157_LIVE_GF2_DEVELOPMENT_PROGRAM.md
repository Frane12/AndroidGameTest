# DRNAS R157 — live GF(2) / CDCL razvojni program

Datum 2026-11-05. Grana `experiment/drnas-r157-live-xor-cdcl-20261105`.

## Motivacija / nalazi koje treba sačuvati

- R155 izvorna GF(2) short-CNF ruta **jest aktivirala** 128/54/128/21 posljedica na 4 real mixed formulas; stari audit pogrešno je zapisivao 0 jer je subprocess.TimeoutExpired izgubio metadata.
- R156 4/4 audit i 100 pokušaja na 10 poznatih formula: R156 solved 8/20 PAR2 360.070897s, R153 8/20 PAR2 360.0716s, R155 8/20 PAR2 360.072709s, CryptoMiniSat 8/20 PAR2 417.156495s, Kissat 0/20 PAR2 600s. Na 4 mixed originala **R156 i R155 8/8 aktivacija, ali svi solveri 0/8 riješeno**. Stoga statički CNF injection nije donio dokazanu korist.
- R157 zato mjeri in-process CDCL XOR unit-propagation, direktno preko CaDiCaL 2.1.0 IPASIR-UP. Ovo je eksperimenat, ne promovirana nova stabilna verzija.

## Implementacija i sigurnost

- Izvor: originalni R154 SHA-zamrznuti 4 mixed CNF (kriptografija i miter); ni jedna formula nije umjetno modificirana za cilj benchmarka.
- `research/r157_source_certified_xor.py`: izvodi samo **potpuno** izvorno potvrđene CNF XOR k2–k6. Koristi izvorne jedinične klauzule za algebraičko skraćivanje dokazano ekvivalentnih pariteta, odbacuje k<2, deduplicira, rangira prema relevantnosti za rezidualne CNF klauzule; maksimalno 180 redova. Pohranjuje izvornu SHA, broj jednadžbi, zamjenskih jedinica i svaku dokazanu jednadžbu.
- `research/r157_live_gf2_bridge.cpp`: originalni validirani R148/R133c CaDiCaL ExternalPropagator, reverzibilne watched-list strukture i LIFO rollback; izravna propagacija vraća doslovnu klauzulu objašnjenja koja vrijedi za sve dodjele zadovoljavajuće izvornu XOR jednadžbu. CaDiCaL obrađuje konflikte. `R157_START`, `R157_PROGRESS`, `R157_RESULT` s provjerom izvornog SAT modela.
- Upareni pravi workflow `.github/workflows/drnas-r157-live-gf2.yml`: isti CaDiCaL source commit 2.1.0, `clean/freeze/watch/clause/direct`, 2 ponavljanja, 15 s, 4 sharda, 40 pokušaja. Trošak ekstrakcije se uračunava u sve XOR načine, ali ne u clean; original source SHA provjeren.
- Benchmark `research/r157_live_gf2_benchmark.py` na timeout čuva najnoviji checkpoint: `direct_proposals`, `reason_requests`, `rows_scanned`, assignments/backtracks, budget_off/disabled. Četiri sharda/40 pokušaja i konačni izvorni audit obavezni.
- Izvorni R28/R153/R155/R156 i svi natjecateljski rezultati ostaju netaknuti. Rezultati R157 **nisu** novi blind holdout.

## Go / No-Go

1. Nijedna neprovjerena izvorna GF(2) posljedica, nijedan neispravan SAT model, nijedan invalid backtracking reason.
2. Potvrditi da `direct_proposals>0` i `reason_requests>0` u pravim hard mixed; bez toga ne može postojati praktični doprinos live GF2 propagacije.
3. Tek ako je barem jedna mixed formula brže riješena ili je realna metrike CDCL poboljšana, povećati limit 30–120s i broj SHAs, uz paralelnu baseline mjernu skupinu i regresije. Ne brojati source proof aktivaciju kao ubrzanje.
4. Za UNSAT imati LRAT/DRAT ili jasno navesti nedostajući nezavisni proof, bez tvrdnje da je poznato konačno ispravan samo na temelju statusa vanjskog solvera.
5. Ako nema koristi, profilirati trail/XOR incidence, konflikte i reduciranu vezu između XOR redova i preostalih CNF klauzula; ne promovirati verziju prije neviđenog originalnog SHA holdouta.

Run: https://github.com/Frane12/AndroidGameTest/actions/runs/42120573934
