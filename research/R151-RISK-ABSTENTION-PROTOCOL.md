# R151: simetrični rizikom vođeni SAT portfolio — unaprijed definiran eksperiment

Datum: 2026-11-05

## Hipoteza

R150 je ostvario mali dobitak prema R148, ali je ukupno izgubio od čistog Kissata jer su dvije stare R148 odluke CaDiCaL umjesto Kissata proizvele timeout (official2026-000 i official2025-004). R150 je mijenjao samo Kissat→CaDiCaL i na 13 promijenjenih formula dobio stvarne koristi na samo dvije. Cilj R151 je **isključiti nepouzdanu selekciju**, posebno skupe timeout-regresije, modelom koji može promijeniti izbor u oba smjera i koji se vraća na Kissat kada nemamo dovoljno dokaza.

Nije uvedena nikakva izmjena izvornog CNF-a, Kissata, CaDiCaL-a, R148 ni stabilnih grana.

## Model koji se testira

- Povijesno treniranje: 400 SHA-identificiranih ranije korištenih formula iz R135S/R135 mjerenja, bez novih mjerenja za treniranje.
- 16 bounded strukturnih značajki iz najviše 256 KiB / 4096 klauzula.
- Standardizirana udaljenost i K=24 najbliža povijesna uzorka; bez clippinga regresijskog cilja.
- Cilj regresije/odluke: **ΔPAR-2 = PAR-2(CaDiCaL) − PAR-2(Kissat)** za dvije povijesne repeticije.
- Iz K lokalnih uzoraka računa se procijenjena srednja razlika, standardna pogreška i odluka:
  CaDiCaL samo ako `mean_delta + z × SE < −0.5 s`; inače Kissat (abstention).
- Dvije **prije holdouta zamrznute** vrijednosti z: R151_05 = 0.5; R151_15 = 1.5.
- Dvosmjernost se mjeri relativno prema frozen R148 izboru (promjene Kissat→CaDiCaL i CaDiCaL→Kissat).
- C++ obrada i odabir izvršavaju se u **jednom izvornom procesu**; detekcija je uključena u 15-sekundni cap.
- Validacija na povijesti: *leave-entire-cohort-out* (official, external_application, external_xor, external_nonxor). Ovi retrospektivni rezultati nisu neovisna potvrda.

## Pre-registriran neviđeni test

Testni slučajevi zamrzavaju se **prije** prvog solver timinga.

- 4 uravnotežene skupine po ciljano 10 formula: službeni katalog SAT2026, službeni SAT2025, miter i cryptography.
- Protokol prihvaća 32–40 formula uz najmanje tri skupine ako neki izvori nisu dohvatljivi; nema selekcije po brzini, ishodu ili strukturnim značajkama.
- SHA, URL i izvorni identifikatori isključuju ranijih 400, R132 125, R135 56, R135S 21, R148 novih 50 i R150 novih 55; provenijencija i manifest-hashevi ostaju u artefaktu.
- Pet pariranih modova: Kissat, CaDiCaL, R148, R151_05, R151_15.
- Dvije ponovljene probe, isti originalni CNF, 15 s po pokušaju (timeout PAR-2=30 s), randomiziran poredak modova po SHA/repeticiji, osam shardova.
- Za svaku formulu: izvorni SHA, odluka, rizik i pouzdanost modela, trošak detektora, stvarni solver, ishod, vrijeme, SAT provjera originalnog modela.
- Završni audit: kompletni upareni podaci, solved/timeout, PAR-2, medijan riješenih, SHA provenijencija, kontradikcije, regresije ≥2×, stratificirani bootstrap 95 %, skupine i dvije promjene smjera selektora.
- GitHub runner CPU modeli razlikuju se između shardova; zato se uspoređuju isti solveri unutar istog sharda, ali milisekundne razlike imaju ograničenu statističku težinu.
- UNSAT odgovori nemaju neovisni LRAT/FRAT certifikat. Nema promocije verzije bez potvrđene ponovljivosti, ispravnosti i statistički značajnog, nerizičnog dobitka.

## Povijest implementacije i rezultata

- R150 retrospektivni audit: https://github.com/Frane12/AndroidGameTest/actions/runs/42088721067
- R150 dubinska analiza: https://github.com/Frane12/AndroidGameTest/blob/experiment/drnas-r150-forensics-20261105/research/R150-DEEP-FORENSICS-20261105.md
- R151 prvi CI run 42094600345 nije prošao C++ kompilaciju zbog lokalnog simbola `pair` koji je zaklonio `std::pair`; nijedna formula nije testirana.
- Minimalni C++ ispravak na eksperimentalnoj grani: 036ee17634fc8fe0be4a3ae00eba7867906026c5.
- R151 ponovno pokretanje nakon CI fixa: https://github.com/Frane12/AndroidGameTest/actions/runs/42094754907

Svaki negativni rezultat ostaje u auditu. Ni jedan dio koda ne podešava model prema rezultatima novih holdout formula. Ostale ranije testirane formule, izvan navedenih ledgera, nisu iscrpno isključene i ne tvrdimo globalnu povijesnu neviđenost.
