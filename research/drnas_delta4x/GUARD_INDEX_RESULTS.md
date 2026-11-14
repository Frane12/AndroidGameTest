# DRNAS DELTA4X — indeksiranje guard-varijabli, originalni SAT2024 audit

**Status: CI PASS; originalni solveri i main nisu mijenjani.**
GitHub Actions: https://github.com/Frane12/AndroidGameTest/actions/runs/43600620351

## Matematička semantika, bez promjene dokaza

DELTA4X izvodi originalno-RUP-provjerene kratke klauzule koje predstavljaju uvjetovane ekvivalencije. Nova optimizacija **ne mijenja** izdvajanje rezolvenata, uvjetovanost, BCP/watch propagaciju, CDCL trail, učene klauzule, SAT odluke ni UNSAT dokaz. Samo ažurira *read-only* promatrača aktivnih alias-veza.

Prije: pri većini dodjela `trailChange` skenira sve alias zapise; pri backtrackingu `refresh` skenira sve alias zapise.

Poslije: `xguard_index[abs(guard)]` vodi do relevantnih aliasa; `trailChange` radi jedan lookup, a `backtrackRefresh` pregledava samo trenutno aktivne guard-varijable, jer poništavanje dodjela ne može samo od sebe aktivirati prethodno neaktivan guard. Pri novoj klauzuli ostaje potpuni `refresh` radi održanja semantike; samo je **česti put** indeksiran.

Kod: `research/drnas_delta4x/guard_index_audit.py` automatski izvodi indeksirani header iz zamrznutog referentnog headera; jedina C++ promjena je zamjena ažuriranja promatrača i backtrack poziva u privatnoj izgrađenoj verziji.

## Reproducibilnost i sigurnost

* Referentni DELTA4X SHA256: `bbc4943a123a8752625e8fa04a9359f1aca7f4158dd60a69b70f522c434e0ef6`.
* Indeksirani DELTA4X SHA256: `941daa4daa2f9263369562dc0e4bf21b67abb0aa70fcd127e4cfcd502d6e76e0`.
* Observer-OFF SHA256: `8ed910baed0e66e52b9e649c9f79537eb7d2cb807421f36bef0f20d21a86cac6`.
* Originalni 60-CNF manifest: `d714d58cce595b6f5a5b67703a773d0adc8530fe83b12f1b736ffe0b9ce79597`; šest unaprijed odabranih izvora (ID8,19,25,26,28,38).
* Preflight: **11 sintetičkih SAT/UNSAT oracle formula × 3 ruke = 33 pokušaja**, originalni SAT modeli, UNSAT DRAT provjere, originalni RUP događaji i CDCL uzročni razlozi PASS. Aktivacije/deaktivacije, broj ugrađenih klauzula i broj uzročnih dodjela isti u originalnom i indeksiranom promatraču na tim slučajevima.
* Poseban C++ lifecycle PASS: unassignment, reactivation, true guard ostaje neaktivan, nepovezana dodjela ne pregledava alias, backtracking ne pregledava neaktivne guard-veze.
* Svaki solver koristi **1 logičku CPU jezgru**, ruke izvršavane serijski, ponavljanja u deterministički izmiješanom redoslijedu.
* Retrospektivna dijagnostika, **nije blind holdout** i ne implicira promotivni izbor builda.

## Rezultati: 6 originalnih formula × 3 ponavljanja × 5 ruku = 90 pokušaja

Limit **3 sekunde** po solveru. Svi pokušaji na ovih 6 formula završili su bez certificiranog SAT/UNSAT rješenja. Zato su prikazani konflikti **propusnost izvršavanja**, ne dobitak u vremenu do rješenja.

| Formula | X_ACTIVE konflikti | X_GUARD_INDEX konflikti | X_OBSERVER_OFF konflikti | Indeks više od originala | Indeks / bez promatrača |
|---|---:|---:|---:|---:|---:|
| ID8 circuit-multiplier | 204.616 | 232.616 | 255.242 | +13,7 % | 91,1 % |
| ID19 sted | 104.843 | 118.787 | 123.007 | +13,3 % | 96,6 % |
| ID25 atco | 88.381 | 89.645 | 91.748 | +1,4 % | 97,7 % |
| ID26 j-mdd | 59.098 | 68.906 | 68.981 | +16,6 % | 99,9 % |
| ID28 fermat | 57.010 | 67.293 | 67.513 | +18,0 % | 99,7 % |
| ID38 dltm-twitter | 14.551 | 25.525 | 25.435 | **+75,4 %** | **100,4 %** |

Ukupna propusnost po svim slučajevima: X_ACTIVE **528.499** konflikata; X_GUARD_INDEX **602.772**, X_OBSERVER_OFF **631.926**. Ponderirana agregacija je +14,1 % više konflikata u indeksiranom modu u istom ukupnom vremenskom limitu, uz napomenu da odabranih šest formula nisu statistički reprezentativna populacija i da promjene putanje pretrage mogu utjecati na brojeve.

**Sve tri aktivne ruke umetnule su po izvoru jednak broj originalno verificiranih klauzula**: ukupno **354 umetanja** tijekom tri ponavljanja šest formula (ne 354 jedinstvena matematička otkrića). Indeksirana verzija zabilježila je **89.638 CDCL propagacija** čiji je neposredni razlog X klauzula, uključujući ponovljene propagacije pri povratku pretrage.

ID38 posebno: original 14.551 konflikata, indeks 25.525, bez promatrača 25.435 kroz tri pokusa. Dokaziva klauzula i njena upotreba ostaju, a indeks uklanja velik dio troška promatrača. Razlika +0,35 % u odnosu na Observer-OFF nema uvjerljivu statističku značajnost i nije namijenjena kao tvrdnja prednosti indeksa nad potpuno isključenim promatračem.

ID28: indeks i original svaki umetnu 42 klauzule kroz tri pokusa, ali X klauzule nisu dale nijednu zabilježenu propagaciju. Propusnost +18,0 % stoga ilustrira čisti trošak bookkeeping-a čak i bez uzročnog BCP učinka.

## Što eksperiment ne dokazuje

Ne pokazuje da indeksirani DELTA4X rješava nepoznatu formulu brže od Kissata/CaDiCaL-a ili od starog DELTA4X-a; niti da bi u dužem vremenskom limitu isporučio manji PAR2. Ne dokazuje novu teoremsku matematiku. Ovo je kvalitetno lokalno mjerenje troška jednog semantički read-only modula.

**Sljedeći korak nakon ove dijagnostike:** na novom SHA-disjunktnom holdoutu i duljem limitu uparenih solvera provjeriti verificirani PAR2, broj riješenih problema, broj odluka, potrošnju memorije, te po mogućnosti pokazati statistički pouzdanu korist bez premještanja na `main` dok kriteriji nisu zadovoljeni.

## Pristup

Grana: `experiment/drnas-delta4x-guard-index-20261114`

CI: https://github.com/Frane12/AndroidGameTest/actions/runs/43600620351

Izvor: `research/drnas_delta4x/guard_index_audit.py`

Safety: `research/drnas_delta4x/guard_index_lifecycle.cpp`

Workflow: `.github/workflows/drnas-delta4x-guard-index.yml`
