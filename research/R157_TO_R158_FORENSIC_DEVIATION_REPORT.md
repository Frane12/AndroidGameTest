# DRNAS SAT — forenzička analiza R135–R157, 2026-11-06

## Rezultati: kontekst je obvezan

| Grana/benchmark (run ID) | Formula x ponavljanja | Usporedba | Izmjerena činjenica |
| --- | --- | --- | --- |
| R135 portfolio (42061060902) | 400 x 2 | R135 vs Kissat | PAR2 12889.822 vs 13198.925 s, +2.398%; 27 regresija >2x |
| R148 blind (42087820632) | 50 x 2 | R148 vs Kissat | PAR2 2462.158 vs 2385.923 s, -3.096%; znatna regresija u novom uzorku |
| R150 cost-aware (42088721067) | 55 x 2 | R150_02 vs Kissat | PAR2 2281.903 vs 2250.374 s, -1.382%; 26 selector override ne vraća širok dobitak |
| R151 risk (42094754907) | 40 x 2 | R151_05 vs Kissat | PAR2 1752.696 vs 1802.207 s, +2.747%; 95% bootstrap [-0.811,9.051] |
| R152 stratified selector (42101670182) | 64 x 2 | R152_05 vs Kissat | PAR2 3097.280 vs 3150.836 s, +1.700%; R151_05 u ISTOM RUNU bolji: 3084.306 s |
| R28 Full SATComp (42105963889) | 112 x 2 | R28 vs Kissat | PAR2 6910.873 vs 6990.857 s, +1.144%; CI [-0.014,3.594]. Izravni R28 GF2: 2 UNSAT pokušaja (jedna formula x2); 54 uspjeha preko Kissat fallbacka |
| R153/R154 GF2 holdout (42107642696) | 25 x 2 (odabrane XOR-obitelji) | R153 vs Kissat | 26/50 vs 0/50, PAR2 720.246 vs 1500 s: +51.98%. Dobitak je na complete XOR i XOR+units, ne na mixed residual |
| R155 six-way (42112755104) | ISTIH 25 x 2 | R155 vs R153 | R155 720.237353, R153 720.236580; nema dobitka. Svi 4 mixed residual slučaja timeout. Raniji audit pogrešno zaključio `entailed_equation_trials=0` jer timeout odbacuje stdout |
| R154 MIX 30s (42113671897) | 12 x 2 | R153 R28 Kissat CaDiCaL | svi 0/24; PAR2 1440 po solveru |
| R156 (42118586230) | 10 ranije viđenih x 2 | R156 vs R155/R153 | 8/20 svi, PAR2 360.070897 vs 360.072709/360.071600 s. R156 i R155 na mixed aktivirani 8/8, završeni 0/8 |
| R157 (42120573934) | 4 mixed x 2 | isti CaDiCaL clean/freeze/watch/clause/direct | svih pet načina 0/8, PAR2 240 s. Direktno: najmanje 1876 GF2 prijedloga, 1012 callback poziva reason-literal-a, 33,231,769 assignment events, 2,367,311 backtrack događaja iz checkpointa |
| R157 qualified audit replay (42128330408) | istih 40 pokušaja, bez reruna | izvorni SHA, XOR certifikati i per-shard binarna provenijencija | PASS s oznakom HETEROGENEOUS BINARIES. Četiri različita native SHA, ali isti R157 i CaDiCaL source commit; nije moguće tvrdili da je binary-identical cross-runner |

NIKAD ne izjednačiti "R152 selector" i "R152 Lights-Out", niti novu numeraciju benchmarka sa stvarnom verzijom solvera. Postoci između različitih uzoraka nisu ista liga.

## Gdje se izgubio smjer?

**A. Nepotvrđena široka selekcija.** R135 daje +2.4% na 400, ali bliski portfolio R148 gubi -3.1% na 50 novim formulama. R151_05 vraća +2.75% na novih 40, ali CI prelazi nulu. R152_05 na narednih 64 ostvaruje +1.7%, no *u istom* benchmarku stariji R151_05 daje +2.11%. Kompliciraniji selektor nije dokazani napredak.

**B. R153 stvarni, uski mehanistički proboj.** Prepoznavanje potpunih XOR blokova i jediničnih klauzula daje izravno egzaktno GF2 rješenje. Nezavisna SAT model provjera i izvorni GF2 UNSAT replay dokazni su koraci. Ne poistovjećivati sa širokom slučajnom raspodjelom SAT.

**C. R155→R157 optimizirali smo posredne metrike.** R155 se zapravo aktivirao na mixed (128/54/128/21 posljedica u classify), ali timeout je izgubljeni stdout pretvorio u lažnu nulu. R156 residual-aware izabrao je 3/25/48/21 dodatnih redova i source proof; bez novog riješenog mixed. R157 izravna propagacija u CDCL-u: 1876 prijedloga na 33.2 milijuna assignment events (~0.00565%), a niti jedna mixed formula riješena. `reason_requests` brojač u R148/R157 broji callback pozive po literalu, **ne** jedinstvene potvrđene razloge/konflikte. Nezabilježeni su CaDiCaL konflikti, naučene klauzule i korisne propagacije baselinea. Aktivnost ne dokazuje skraćenje pretrage.

**D. Ista hipoteza bila je već slab rezultat.** R148 direct IPASIR-UP (42084256386, šest SATLIB development PARITY) dao je 226 direct proposals, ali PAR2 80.603 vs clean 80.268 s: -0.418%, što je unaprijed upozoravalo da propagacije nisu dovoljno korisne.

**E. Zasićen benchmark.** Već 6s i 30s mixed svi timeout; R155/R156 15s mixed svi timeout; R157 15s svi timeout. Svi PAR2 rezultati identični i ne mogu mjeriti poboljšanje unutarnjeg stanja. Potrebni su prediktori napretka ili instance kojima netko riješi unutar 120–300s.

**F. Reproducibilnost.** R157 izvorni audit zahtijevao je isti compiled SHA za sva 4 različita GitHub runnera, iako je source commit identičan. Qualified audit naknadno ispravno provjerava svaki per-shard pin i ne tvrdi jednakost različitih binarija. Za buduće full audite izgraditi jednu binariju i distribuirati je na sve shardove; CPU i dalje evidentirati.

## R158 smjer — predefinirani uvjeti

1. ZADRŽATI R153 egzaktni GF2 mehanizam kao nepromijenjenu specijalističku referencu; za generalističku osnovu Kissat/R151_05 uz zamrznute binarne hashove.
2. Uvesti *causal* mjerenje za 4 hard mixed formule: stvarni CDCL conflicts, decisions, propagations, learned clauses, CPU overhead, XOR row wakeups, accepted XOR implications (odvojeno od proposed), reason widths i broj backtracka. Isti kod/binarija na istom runneru za clean/direct. Nema uspjeha samo zbog >0 propagated.
3. Testirati prijenos na "boundary": koliko promatranih XOR varijabli sudjeluje u rezidualnim CNF klauzulama, koliko GF2 propagacija mijenja konfliktni graf i koliko je novih CDCL razloga zapravo korisno. Za miter s 21 redom i 0 predloženih propagacija najprije provjeriti uvjet aktivacije/strukturu; ne dodavati još klauzula.
4. Odabrati mali set stvarnih mješovitih formula na kojima barem jedan solver rješava za 30–300s, plus 4 hard timeout kontrole. **Prezamrznuti** izvore i podijeliti na razvoj i potpuno neviđeni test.
5. Odvojena ablacijska grana: clean / source rows / residual rows / direct GF2 / static injection, identični izvori i CPU, čvrste CPU/time budget granice.
6. Kriterij promocije: nema krivih SAT modela ni neprovjerljivih GF2 source implikacija; reproducibilna solved/PAR2 prednost na neviđenim mixed formulama, ne-regresija na 50+ general real CNFs, najmanje 2 ponovljena runa i CI ne prelazi nulu. Za certificirani UNSAT potreban LRAT/DRAT ili eksplicitna ograda.

Ovo je istraživačka procjena na temelju konkretnih GH audit logova, ne tvrdnja o službenom svjetskom poretku.
